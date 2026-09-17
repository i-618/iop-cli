import os

import pytest

from iop.cli import resolve_step
from iop.config import Step
from iop.template import TemplateError


def test_resolve_step_direct_exec_renders_argv():
    step = Step(run="git commit -m {msg}")
    resolved = resolve_step(step, {"msg": "fixed the parser"})
    assert resolved.shell_command is None
    assert resolved.argv == ("git", "commit", "-m", "fixed the parser")


def test_resolve_step_direct_exec_keeps_hostile_value_as_one_token():
    step = Step(run="git commit -m {msg}")
    resolved = resolve_step(step, {"msg": "fix; rm -rf /"})
    assert resolved.argv == ("git", "commit", "-m", "fix; rm -rf /")


def test_resolve_step_shell_true_quotes_the_value():
    step = Step(run="git commit -m {msg}", shell=True)
    resolved = resolve_step(step, {"msg": "fix; rm -rf /"})
    assert resolved.argv is None
    assert resolved.shell_command is not None
    # Round-trip through the real POSIX shell-word parser: if quoting is
    # correct, the hostile value comes back as exactly one shell word,
    # identical to the original -- not split on the semicolon.
    import shlex as _shlex
    tokens = _shlex.split(resolved.shell_command)
    assert tokens == ["git", "commit", "-m", "fix; rm -rf /"]


def test_resolve_step_shell_true_does_not_double_substitute_a_colliding_placeholder():
    # Two variables where the FIRST variable's value is literally the text
    # of the SECOND variable's placeholder. A correct single-`.format()`-pass
    # substitution leaves that text alone; a buggy sequential str.replace
    # implementation would re-substitute it a second time. One variable
    # cannot distinguish these two behaviors -- this needs two.
    step = Step(run="echo {a} {other}", shell=True)
    resolved = resolve_step(step, {"a": "{other}", "other": "INJECTED"})
    assert "{other}" in resolved.shell_command
    assert resolved.shell_command.count("INJECTED") == 1


def test_resolve_step_shell_true_carries_ok_fail_through():
    step = Step(run="echo {msg}", shell=True, ok_fail=True)
    resolved = resolve_step(step, {"msg": "hi"})
    assert resolved.ok_fail is True
