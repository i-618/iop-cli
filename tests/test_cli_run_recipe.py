import sys

import pytest

from iop.cli import _run_recipe
from iop.config import Recipe, Step

# resolve_step tokenizes `run` with shlex (POSIX rules), which treats a
# backslash as an escape character and silently drops it -- exactly the
# hazard iop.config._load_step's own backslash check warns about. On
# Windows, sys.executable contains backslashes, so any test that embeds
# it directly in a `run` template needs the forward-slash form (Windows
# accepts both) or the interpreter path gets corrupted before exec.
_PYTHON = sys.executable.replace("\\", "/")


def _capture_stdout(capsys):
    return capsys.readouterr().out


def test_run_recipe_reports_unknown_recipe(capsys):
    code = _run_recipe({}, "nope", (), dry_run=False)
    assert code == 2
    assert "no such recipe" in capsys.readouterr().err


def test_run_recipe_reports_too_many_values(capsys):
    recipes = {"push": Recipe(name="push", vars=("msg",), steps=(Step(run="echo {msg}"),))}
    code = _run_recipe(recipes, "push", ("a", "b"), dry_run=False)
    assert code == 2
    assert "takes 1 value" in capsys.readouterr().err


def test_run_recipe_dry_run_prints_resolved_argv_without_executing(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    marker = tmp_path / "hello.txt"
    recipes = {
        "touch": Recipe(
            name="touch",
            vars=("path",),
            steps=(Step(run=f"{_PYTHON} -c \"import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('x')\" {{path}}"),),
        )
    }
    code = _run_recipe(recipes, "touch", (str(marker),), dry_run=True)
    assert code == 0
    out = capsys.readouterr().out
    assert str(marker) in out
    assert not marker.exists()  # nothing was executed


def test_run_recipe_executes_when_not_dry_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    marker = tmp_path / "ran.txt"
    recipes = {
        "touch": Recipe(
            name="touch",
            vars=("path",),
            steps=(Step(run=f"{_PYTHON} -c \"import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('x')\" {{path}}"),),
        )
    }
    code = _run_recipe(recipes, "touch", (str(marker),), dry_run=False)
    assert code == 0
    assert marker.exists()


def test_run_recipe_prompts_for_missing_values_when_stdin_is_a_tty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    marker = tmp_path / "prompted.txt"
    recipes = {
        "touch": Recipe(
            name="touch",
            vars=("path",),
            steps=(Step(run=f"{_PYTHON} -c \"import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('x')\" {{path}}"),),
        )
    }
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: str(marker))
    code = _run_recipe(recipes, "touch", (), dry_run=False)
    assert code == 0
    assert marker.exists()


def test_run_recipe_errors_when_stdin_is_not_a_tty_and_a_value_is_missing(monkeypatch, capsys):
    recipes = {"touch": Recipe(name="touch", vars=("path",), steps=(Step(run="echo {path}"),))}
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    code = _run_recipe(recipes, "touch", (), dry_run=False)
    assert code == 2
    assert "not a terminal" in capsys.readouterr().err


def test_run_recipe_runs_earlier_steps_before_prompting_for_a_later_ones_value(
    tmp_path, monkeypatch
):
    # A step that doesn't reference {msg} must run without waiting for a
    # prompt; only the step that actually needs {msg} should block on it.
    # This is the property that lets `iop push` start `git pull`/`git add`
    # immediately instead of pausing before anything runs at all.
    monkeypatch.chdir(tmp_path)
    early_marker = tmp_path / "early.txt"
    late_marker = tmp_path / "late.txt"

    def _write(path_arg: str) -> str:
        return f"{_PYTHON} -c \"import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('x')\" {path_arg}"

    recipes = {
        "seq": Recipe(
            name="seq",
            vars=("msg",),
            steps=(
                # no {msg} -- must run unprompted. Path normalized to
                # forward slashes: it's embedded directly in the template
                # (not substituted via {}), so it goes through the same
                # shlex tokenization as the rest of the template and a raw
                # backslash would be silently eaten.
                Step(run=_write(str(early_marker).replace("\\", "/"))),
                Step(run=_write("{msg}")),  # needs {msg} -- this is where it should block
            ),
        )
    }

    prompted_before_early_step_ran = []

    def _fake_input(prompt):
        # By the time input() is called, the earlier step must already
        # have executed -- proving resolution didn't wait on the prompt
        # before running anything.
        prompted_before_early_step_ran.append(not early_marker.exists())
        return str(late_marker)

    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", _fake_input)

    code = _run_recipe(recipes, "seq", (), dry_run=False)

    assert code == 0
    assert early_marker.exists()
    assert late_marker.exists()
    assert prompted_before_early_step_ran == [False]  # early step had already run


def test_run_recipe_does_not_prompt_at_all_when_no_step_needs_the_value(monkeypatch):
    # A recipe can declare a var that no step actually uses -- lazy
    # resolution means it's simply never asked for.
    recipes = {
        "noop": Recipe(name="noop", vars=("unused",), steps=(Step(run="echo hi"),))
    }
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)  # would error if ever consulted

    def _fail_if_called(prompt):
        raise AssertionError("input() should never be called for an unused var")

    monkeypatch.setattr("builtins.input", _fail_if_called)
    code = _run_recipe(recipes, "noop", (), dry_run=False)
    assert code == 0
