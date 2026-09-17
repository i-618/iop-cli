import os
import subprocess
import sys
import textwrap

import pytest


@pytest.fixture
def fake_home(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".iop").mkdir()
    (home / ".iop" / "recipes.toml").write_text(
        textwrap.dedent(
            """
            [greet]
            desc  = "print a greeting"
            vars  = ["name"]
            steps = ["echo hello {name}"]
            """
        ),
        encoding="utf-8",
    )
    return home


def _run_iop(args, home, cwd, stdin_data=None):
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)  # Windows honors this one
    return subprocess.run(
        [sys.executable, "-m", "iop", *args],
        cwd=cwd,
        env=env,
        input=stdin_data,
        capture_output=True,
        text=True,
    )


def test_end_to_end_runs_a_recipe_with_a_value(fake_home, tmp_path):
    result = _run_iop(["greet", "world"], fake_home, tmp_path)
    assert result.returncode == 0
    assert "hello world" in result.stdout


def test_end_to_end_passes_a_dash_prefixed_value_through_untouched(fake_home, tmp_path):
    result = _run_iop(["greet", "--wip"], fake_home, tmp_path)
    assert result.returncode == 0
    assert "hello --wip" in result.stdout


def test_end_to_end_dry_run_does_not_execute(fake_home, tmp_path):
    result = _run_iop(["--dry-run", "greet", "world"], fake_home, tmp_path)
    assert result.returncode == 0
    assert "echo hello world" in result.stdout


def test_end_to_end_unknown_recipe_is_exit_2(fake_home, tmp_path):
    result = _run_iop(["nope"], fake_home, tmp_path)
    assert result.returncode == 2


def test_end_to_end_too_many_values_is_exit_2(fake_home, tmp_path):
    result = _run_iop(["greet", "a", "b"], fake_home, tmp_path)
    assert result.returncode == 2


def test_end_to_end_seeds_a_default_config_on_first_run(tmp_path):
    # No ~/.iop/recipes.toml exists yet -- the very first `iop` invocation,
    # for any recipe- or list-consuming action, seeds the starter config
    # rather than erroring. "greet" isn't in that starter config, so the
    # seeded file gets created and THEN the (correct) "no such recipe"
    # error follows -- proving the seed happened, not that config loading
    # was skipped.
    empty_home = tmp_path / "empty_home"
    empty_home.mkdir()
    result = _run_iop(["greet", "world"], empty_home, tmp_path)
    assert result.returncode == 2
    assert "no such recipe" in result.stderr
    assert (empty_home / ".iop" / "recipes.toml").exists()


def test_end_to_end_seeded_default_config_is_immediately_usable(tmp_path):
    # The starter config's own recipe is "push" -- running it against a
    # truly fresh HOME (no .iop directory at all) must work on the first
    # try, with no separate "create the file" step.
    empty_home = tmp_path / "empty_home"
    empty_home.mkdir()
    result = _run_iop(["--dry-run", "push", "first commit"], empty_home, tmp_path)
    assert result.returncode == 0
    assert "git pull" in result.stdout
    assert "git commit -m 'first commit'" in result.stdout


def test_end_to_end_missing_value_with_piped_stdin_is_exit_2_not_a_hang(fake_home, tmp_path):
    # A pipe is not a TTY, so iop must refuse to block waiting for input
    # that will never arrive interactively -- this is what keeps
    # `iop push` safe to run inside a script or CI step.
    result = _run_iop(["greet"], fake_home, tmp_path, stdin_data="world\n")
    assert result.returncode == 2
    assert "not a terminal" in result.stderr
