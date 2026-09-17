"""Execute a recipe's resolved steps as subprocesses.

Every step already carries a finished command; this module parses
nothing. It owns process execution, per-step failure tolerance, and
exit-code propagation (design spec sections 4 and 8).

Streams are inherited, never captured (a captured stdout/stderr would
silently break an interactive credential prompt from e.g. `git push`),
and `cwd` is never set -- the child inherits the current directory for
free, which is the "same path" requirement.
"""
from __future__ import annotations

import shlex
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional, Tuple

_RESET = "\033[0m"
_DIM = "\033[2m"
_WARN = "\033[33m"


@dataclass(frozen=True)
class ResolvedStep:
    """A step ready to execute: either argv (direct exec) or a shell
    command string (subprocess shell=True) -- never both."""

    argv: Optional[Tuple[str, ...]]
    shell_command: Optional[str]
    ok_fail: bool

    def display(self) -> str:
        if self.shell_command is not None:
            return self.shell_command
        return shlex.join(self.argv)


def run(steps, *, use_color: bool = True) -> int:
    for step in steps:
        _echo(f"> {step.display()}", use_color)
        try:
            if step.shell_command is not None:
                result = subprocess.run(step.shell_command, shell=True)
            else:
                result = subprocess.run(list(step.argv))
        except FileNotFoundError:
            code = 127
        else:
            code = result.returncode

        if code == 0:
            continue
        if step.ok_fail:
            _echo(f"! {step.display()} -> exit {code} (tolerated)", use_color, warn=True)
            continue
        return code
    return 0


def _echo(line: str, use_color: bool, *, warn: bool = False) -> None:
    if not use_color:
        print(line, file=sys.stderr)
        return
    color = _WARN if warn else _DIM
    print(f"{color}{line}{_RESET}", file=sys.stderr)
