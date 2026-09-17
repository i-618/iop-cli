import os
import subprocess
import sys
import textwrap

import pytest


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo_and_home(tmp_path):
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git("init", "--bare", cwd=remote)

    work = tmp_path / "work"
    work.mkdir()
    _git("init", cwd=work)
    _git("config", "user.email", "test@example.com", cwd=work)
    _git("config", "user.name", "Test", cwd=work)
    _git("remote", "add", "origin", str(remote), cwd=work)
    (work / "file.txt").write_text("v1", encoding="utf-8")
    _git("add", "-A", cwd=work)
    _git("commit", "-m", "initial", cwd=work)
    # Rename the default branch to 'main'. Without this, `git push` (with no
    # explicit refspec) fails under git's push.default=simple policy: the
    # upstream branch name ('main') doesn't match the local branch name
    # ('master', or whatever git init produces on this system).
    _git("branch", "-M", "main", cwd=work)
    _git("push", "-u", "origin", "HEAD:main", cwd=work)

    home = tmp_path / "home"
    home.mkdir()
    (home / ".iop").mkdir()
    (home / ".iop" / "recipes.toml").write_text(
        textwrap.dedent(
            """
            [push]
            desc  = "pull, stage everything, commit, push"
            vars  = ["msg"]
            steps = [
              "git pull",
              "git add -A",
              { run = "git commit -m {msg}", ok_fail = true },
              "git push",
            ]
            """
        ),
        encoding="utf-8",
    )
    return remote, work, home


def _run_iop(args, home, cwd):
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    return subprocess.run(
        [sys.executable, "-m", "iop", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
    )


def test_push_recipe_commits_and_pushes_a_real_change(repo_and_home):
    remote, work, home = repo_and_home
    (work / "file.txt").write_text("v2", encoding="utf-8")
    result = _run_iop(["push", "updated the file"], home, work)
    assert result.returncode == 0

    # Verify the change was committed locally
    log = subprocess.run(
        ["git", "log", "-1", "--format=%s"], cwd=work, capture_output=True, text=True, check=True
    )
    assert log.stdout.strip() == "updated the file"

    # Verify the change reached the remote (this is the critical test)
    remote_log = subprocess.run(
        ["git", "log", "-1", "--format=%s", "refs/heads/main"],
        cwd=remote,
        capture_output=True,
        text=True,
        check=True
    )
    assert remote_log.stdout.strip() == "updated the file"


def test_push_recipe_tolerates_an_empty_commit(repo_and_home):
    # No file changes since the last push: `git commit` exits non-zero
    # ("nothing to commit"). Without ok_fail this would abort before
    # `git push` -- exactly the trap that motivated the feature.
    remote, work, home = repo_and_home
    result = _run_iop(["push", "no changes here"], home, work)
    assert result.returncode == 0
    assert "tolerated" in result.stderr

    # Verify push actually ran. With no changes to push, the remote's log
    # would be identical whether push ran or not, so we can't verify by
    # checking remote state. Instead, verify execution flow reached the push
    # step by checking for its step banner (printed by iop's runner before
    # each step executes). If ok_fail were broken and the recipe aborted
    # after the failed commit, this banner would never be printed.
    assert "> git push" in result.stderr
