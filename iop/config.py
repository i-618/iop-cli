"""Load and validate ~/.iop/recipes.toml into Recipe / Step objects.

All TOML reading happens here; no other module ever sees a raw dict
(design spec section 4).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib  # Python 3.11+, stdlib
except ModuleNotFoundError:
    import tomli as tomllib  # Python 3.8-3.10, identical API

from iop.template import TemplateError, placeholders, tokenize

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_STEP_KEYS = {"run", "ok_fail", "shell"}
_RECIPE_KEYS = {"desc", "vars", "steps"}


class ConfigError(Exception):
    """recipes.toml is missing or does not describe valid recipes."""


@dataclass(frozen=True)
class Step:
    run: str
    ok_fail: bool = False
    shell: bool = False


@dataclass(frozen=True)
class Recipe:
    name: str
    desc: str = ""
    vars: tuple = ()
    steps: tuple = ()


def default_path() -> Path:
    """~/.iop/recipes.toml -- Path.home() honors $HOME (and $USERPROFILE
    on Windows), which is how tests point iop at a fixture config."""
    return Path.home() / ".iop" / "recipes.toml"


def load(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(_missing_config_message(path))

    try:
        with path.open("rb") as fh:
            raw = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} is not valid TOML: {exc}") from exc

    return {name: _load_recipe(name, table) for name, table in raw.items()}


def _missing_config_message(path: Path) -> str:
    return (
        f"no config file at {path}\n"
        "iop looked there and found nothing. Create it with, e.g.:\n\n"
        "[push]\n"
        'desc  = "pull, stage everything, commit, push"\n'
        'vars  = ["msg"]\n'
        "steps = [\n"
        '  "git pull",\n'
        '  "git status",\n'
        '  "git add -A",\n'
        '  { run = "git commit -m {msg}", ok_fail = true },\n'
        '  "git push",\n'
        "]\n"
    )


def _load_recipe(name: str, table: Any) -> Recipe:
    if not _valid_name(name):
        raise ConfigError(
            f"invalid recipe name {name!r}: must match [A-Za-z0-9_-]+ "
            "and not start with '-'"
        )
    if not isinstance(table, dict):
        raise ConfigError(f"recipe [{name}] must be a table")

    unknown = set(table) - _RECIPE_KEYS
    if unknown:
        raise ConfigError(f"recipe [{name}] has unknown key(s): {sorted(unknown)}")

    desc = table.get("desc", "")
    if not isinstance(desc, str):
        raise ConfigError(f"recipe [{name}]: desc must be a string")

    raw_vars = table.get("vars", [])
    if not isinstance(raw_vars, list) or not all(
        isinstance(v, str) for v in raw_vars
    ):
        raise ConfigError(f"recipe [{name}]: vars must be a list of strings")
    if len(set(raw_vars)) != len(raw_vars):
        raise ConfigError(f"recipe [{name}]: vars contains duplicate names")
    declared_vars = tuple(raw_vars)

    raw_steps = table.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ConfigError(f"recipe [{name}]: steps must be a non-empty list")

    steps = tuple(
        _load_step(name, i, declared_vars, s) for i, s in enumerate(raw_steps)
    )
    return Recipe(name=name, desc=desc, vars=declared_vars, steps=steps)


def _load_step(recipe_name: str, index: int, declared_vars: tuple, raw_step: Any) -> Step:
    if isinstance(raw_step, str):
        run, ok_fail, shell = raw_step, False, False
    elif isinstance(raw_step, dict):
        unknown = set(raw_step) - _STEP_KEYS
        if unknown:
            raise ConfigError(
                f"recipe [{recipe_name}] step {index}: unknown key(s): {sorted(unknown)}"
            )
        if "run" not in raw_step or not isinstance(raw_step["run"], str):
            raise ConfigError(
                f"recipe [{recipe_name}] step {index}: table step needs a string 'run'"
            )
        run = raw_step["run"]
        ok_fail = raw_step.get("ok_fail", False)
        shell = raw_step.get("shell", False)
        if not isinstance(ok_fail, bool):
            raise ConfigError(f"recipe [{recipe_name}] step {index}: ok_fail must be a bool")
        if not isinstance(shell, bool):
            raise ConfigError(f"recipe [{recipe_name}] step {index}: shell must be a bool")
    else:
        raise ConfigError(
            f"recipe [{recipe_name}] step {index}: must be a string or a table"
        )

    if "\\" in run:
        raise ConfigError(
            f"recipe [{recipe_name}] step {index}: contains a backslash: {run!r}\n"
            "Windows paths must use forward slashes (git and Windows both "
            "accept them) -- a single backslash is silently eaten by "
            "argument splitting."
        )

    try:
        tokens = tokenize(run)
        used = placeholders(tokens)
    except TemplateError as exc:
        raise ConfigError(f"recipe [{recipe_name}] step {index}: {exc}") from exc

    undeclared = used - set(declared_vars)
    if undeclared:
        raise ConfigError(
            f"recipe [{recipe_name}] step {index}: uses undeclared "
            f"variable(s) {sorted(undeclared)}; add them to vars = [...]"
        )

    return Step(run=run, ok_fail=ok_fail, shell=shell)


def _valid_name(name: str) -> bool:
    return bool(_NAME_RE.fullmatch(name)) and not name.startswith("-")
