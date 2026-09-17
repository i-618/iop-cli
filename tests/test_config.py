from pathlib import Path

import pytest

from iop.config import ConfigError, Recipe, Step, load


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "recipes.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_parses_the_push_recipe(tmp_path):
    path = _write(
        tmp_path,
        """
        [push]
        desc  = "pull, stage everything, commit, push"
        vars  = ["msg"]
        steps = [
          "git pull",
          "git status",
          "git add -A",
          { run = "git commit -m {msg}", ok_fail = true },
          "git push",
        ]
        """,
    )
    recipes = load(path)
    assert set(recipes) == {"push"}
    push = recipes["push"]
    assert push == Recipe(
        name="push",
        desc="pull, stage everything, commit, push",
        vars=("msg",),
        steps=(
            Step(run="git pull"),
            Step(run="git status"),
            Step(run="git add -A"),
            Step(run="git commit -m {msg}", ok_fail=True),
            Step(run="git push"),
        ),
    )


def test_load_raises_on_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="no config file"):
        load(tmp_path / "does_not_exist.toml")


def test_load_raises_on_malformed_toml(tmp_path):
    path = _write(tmp_path, "this is not [ valid toml")
    with pytest.raises(ConfigError, match="not valid TOML"):
        load(path)


def test_load_raises_on_unknown_recipe_key(tmp_path):
    path = _write(tmp_path, '[push]\nsteps = ["git push"]\nbogus = 1\n')
    with pytest.raises(ConfigError, match="unknown key"):
        load(path)


def test_load_raises_on_step_that_is_neither_string_nor_table(tmp_path):
    path = _write(tmp_path, "[push]\nsteps = [42]\n")
    with pytest.raises(ConfigError, match="must be a string or a table"):
        load(path)


def test_load_raises_on_table_step_without_run(tmp_path):
    path = _write(tmp_path, '[push]\nsteps = [{ ok_fail = true }]\n')
    with pytest.raises(ConfigError, match="needs a string 'run'"):
        load(path)


def test_load_raises_on_empty_steps(tmp_path):
    path = _write(tmp_path, "[push]\nsteps = []\n")
    with pytest.raises(ConfigError, match="non-empty list"):
        load(path)


def test_load_raises_on_duplicate_vars(tmp_path):
    path = _write(
        tmp_path,
        '[push]\nvars = ["msg", "msg"]\nsteps = ["git commit -m {msg}"]\n',
    )
    with pytest.raises(ConfigError, match="duplicate"):
        load(path)


def test_load_raises_on_undeclared_placeholder(tmp_path):
    path = _write(tmp_path, '[push]\nsteps = ["git commit -m {msg}"]\n')
    with pytest.raises(ConfigError, match="undeclared"):
        load(path)


def test_load_raises_on_backslash_in_step(tmp_path):
    path = _write(tmp_path, "[push]\nsteps = ['cd C:\\Users\\likhi']\n")
    with pytest.raises(ConfigError, match="Windows paths must use forward slashes"):
        load(path)


def test_load_raises_on_invalid_recipe_name(tmp_path):
    path = _write(tmp_path, '["-bad"]\nsteps = ["echo hi"]\n')
    with pytest.raises(ConfigError, match="invalid recipe name"):
        load(path)


def test_load_validates_placeholders_even_in_shell_steps(tmp_path):
    path = _write(
        tmp_path,
        '[push]\nsteps = [{ run = "git commit -m {msg}", shell = true }]\n',
    )
    with pytest.raises(ConfigError, match="undeclared"):
        load(path)
