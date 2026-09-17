"""argv parsing, recipe dispatch, and prompting for missing values."""
from __future__ import annotations

import os
import shlex
from dataclasses import dataclass

from iop.config import Step
from iop.runner import ResolvedStep
from iop.template import TemplateError, placeholders, render, tokenize


class UsageError(Exception):
    """Bad CLI invocation; maps to exit code 2."""


@dataclass(frozen=True)
class ParsedArgs:
    action: str
    recipe: str = None
    values: tuple = ()
    dry_run: bool = False


def parse_args(args: list) -> ParsedArgs:
    """The only argument-scanning pass. Because every global flag fully
    determines the action by itself (none combine), only the first token
    needs inspecting: it is either a known flag, or it is the recipe name
    and everything after it is that recipe's values, passed through
    untouched -- so `iop push --wip` commits the message "--wip" rather
    than failing on an unrecognized option (design spec section 7)."""
    if not args:
        return ParsedArgs(action="list")

    token = args[0]
    if token in ("-l", "--list"):
        return ParsedArgs(action="list")
    if token == "--where":
        return ParsedArgs(action="where")
    if token in ("-e", "--edit"):
        return ParsedArgs(action="edit")
    if token == "--version":
        return ParsedArgs(action="version")
    if token in ("-h", "--help"):
        return ParsedArgs(action="help")
    if token in ("-n", "--dry-run"):
        if len(args) < 2:
            raise UsageError("--dry-run requires a recipe name")
        return ParsedArgs(
            action="run", recipe=args[1], values=tuple(args[2:]), dry_run=True
        )
    if token.startswith("-"):
        raise UsageError(f"unknown option {token!r}")
    return ParsedArgs(action="run", recipe=token, values=tuple(args[1:]))


def resolve_step(step: Step, values: dict) -> ResolvedStep:
    if step.shell:
        quoted = {name: _quote_for_shell(value) for name, value in values.items()}
        try:
            rendered = step.run.format(**quoted)
        except KeyError as exc:
            raise TemplateError(
                f"missing value for placeholder {exc} in {step.run!r}"
            ) from exc
        return ResolvedStep(argv=None, shell_command=rendered, ok_fail=step.ok_fail)

    tokens = tokenize(step.run)
    argv = render(tokens, values)
    return ResolvedStep(argv=tuple(argv), shell_command=None, ok_fail=step.ok_fail)


def _quote_for_shell(value: str) -> str:
    """Quote a value for insertion into a shell = true template.

    POSIX gets shlex.quote. Windows shell=True runs through cmd.exe,
    whose quoting rules are not POSIX's; wrapping in double quotes and
    doubling any embedded double quote covers the common case. Neither
    path attempts to neutralize cmd.exe's own % expansion -- shell = true
    steps are explicitly the escape hatch that trades away some of
    template.py's guarantee (design spec section 6), and are not
    portable between platforms.
    """
    if os.name == "nt":
        return '"' + value.replace('"', '""') + '"'
    return shlex.quote(value)


import sys

from iop.config import ConfigError, default_path, load
from iop.runner import run as run_steps

_DEFAULT_RECIPES_CONTENT = (
    '[whoami]\n'
    'desc  = "set your git identity (name and email) for this machine"\n'
    'vars  = ["name", "email"]\n'
    'steps = [\n'
    '  "git config --global user.name {name}",\n'
    '  "git config --global user.email {email}",\n'
    ']\n'
    '\n'
    '[push]\n'
    'desc  = "pull, stage everything, commit, push"\n'
    'vars  = ["msg"]\n'
    'steps = [\n'
    '  "git pull",\n'
    '  "git status",\n'
    '  "git add -A",\n'
    '  { run = "git commit -m {msg}", ok_fail = true },\n'
    '  "git push",\n'
    ']\n'
    '\n'
    '[undo]\n'
    'desc  = "take back the last commit but keep its changes staged"\n'
    'steps = [\n'
    '  "git reset --soft HEAD~1",\n'
    '  "git status",\n'
    ']\n'
    '\n'
    '[serve]\n'
    'desc  = "serve the current directory over HTTP"\n'
    'vars  = ["port"]\n'
    'steps = ["python -m http.server {port}"]\n'
    '\n'
    '[docker]\n'
    'desc  = "build an image and run it"\n'
    'vars  = ["tag"]\n'
    'steps = [\n'
    '  "docker build -t {tag} .",\n'
    '  "docker run --rm -it {tag}",\n'
    ']\n'
)


def _seed_default_config(path) -> None:
    """Write the starter recipes.toml if nothing is there yet. Never
    overwrites an existing file. Shared by main()'s list/run dispatch
    (so a fresh install just works on the very first `iop push ...`)
    and by _edit() (so `iop -e` has something real to open)."""
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_DEFAULT_RECIPES_CONTENT, encoding="utf-8")


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        parsed = parse_args(args)
    except UsageError as exc:
        print(f"iop: {exc}", file=sys.stderr)
        return 2

    if parsed.action == "version":
        from iop import __version__

        print(__version__)
        return 0
    if parsed.action == "help":
        print(_help_text())
        return 0
    if parsed.action == "where":
        print(default_path())
        return 0

    path = default_path()
    _seed_default_config(path)
    try:
        recipes = load(path)
    except ConfigError as exc:
        print(f"iop: {exc}", file=sys.stderr)
        return 3

    if parsed.action == "list":
        _print_list(recipes)
        return 0
    if parsed.action == "edit":
        return _edit(default_path())

    return _run_recipe(recipes, parsed.recipe, parsed.values, dry_run=parsed.dry_run)


def _run_recipe(recipes: dict, recipe_name: str, values: tuple, *, dry_run: bool) -> int:
    recipe = recipes.get(recipe_name)
    if recipe is None:
        print(f"iop: no such recipe {recipe_name!r} (see `iop --list`)", file=sys.stderr)
        return 2

    if len(values) > len(recipe.vars):
        wanted = ", ".join(recipe.vars) or "none"
        print(
            f"iop: {recipe_name!r} takes {len(recipe.vars)} value(s) ({wanted}), "
            f"got {len(values)}",
            file=sys.stderr,
        )
        return 2

    resolved = dict(zip(recipe.vars, values))

    try:
        if dry_run:
            for step in _resolve_steps_lazily(recipe, resolved):
                print(step.display())
            return 0

        use_color = sys.stdout.isatty() and "NO_COLOR" not in os.environ
        return run_steps(_resolve_steps_lazily(recipe, resolved), use_color=use_color)
    except TemplateError as exc:
        print(f"iop: {exc}", file=sys.stderr)
        return 2


def _resolve_steps_lazily(recipe, resolved: dict):
    """Yield each step's ResolvedStep one at a time, prompting only when a
    step actually references a value that isn't known yet.

    This is what lets `iop push` start `git pull`/`git add -A` immediately
    and only pause at the `git commit -m {msg}` step that actually needs
    a message -- rather than blocking on a prompt before anything runs,
    which is what resolving every step's values upfront would do. A step
    that needs nothing new is resolved and handed to the caller (for
    printing in a dry run, or execution in a real one) without ever
    touching stdin.

    Prompting order therefore follows step order, not `vars` declaration
    order -- whichever step is reached first that needs a given name is
    when it gets asked for.
    """
    for step in recipe.steps:
        for name in placeholders(tokenize(step.run)):
            if name in resolved:
                continue
            if not sys.stdin.isatty():
                raise TemplateError(
                    f"missing value for {name} and stdin is not a "
                    "terminal to prompt"
                )
            resolved[name] = input(f"{name}: ")
        yield resolve_step(step, resolved)


def _print_list(recipes: dict) -> None:
    if not recipes:
        print("no recipes defined")
        return
    for name in sorted(recipes):
        recipe = recipes[name]
        marker = " [shell]" if any(step.shell for step in recipe.steps) else ""
        line = f"{name}{marker}"
        if recipe.desc:
            line += f" - {recipe.desc}"
        print(line)


def _help_text() -> str:
    return (
        "usage: iop <recipe> [values...]\n"
        "       iop [-l|--list]\n"
        "       iop -n|--dry-run <recipe> [values...]\n"
        "       iop --where\n"
        "       iop -e|--edit\n"
        "       iop --version\n"
    )


def _edit(path) -> int:
    """Open recipes.toml in $EDITOR (notepad on Windows, vi elsewhere if
    $EDITOR is unset). On first use, seeds the file with a default
    recipes.toml example (same helper main() uses for list/run) so
    there's something real to open; never overwrites an existing file."""
    import subprocess

    _seed_default_config(path)

    editor = os.environ.get("EDITOR") or ("notepad" if os.name == "nt" else "vi")
    try:
        # Split editor command, handling both POSIX and Windows paths
        parts = shlex.split(editor, posix=(os.name != "nt"))
        return subprocess.run(parts + [str(path)]).returncode
    except FileNotFoundError:
        print(f"iop: editor {editor!r} not found; set $EDITOR", file=sys.stderr)
        return 127
