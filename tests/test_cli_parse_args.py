import pytest

from iop.cli import ParsedArgs, UsageError, parse_args


def test_bare_invocation_lists():
    assert parse_args([]) == ParsedArgs(action="list")


def test_list_flag():
    assert parse_args(["--list"]) == ParsedArgs(action="list")
    assert parse_args(["-l"]) == ParsedArgs(action="list")


def test_where_flag():
    assert parse_args(["--where"]) == ParsedArgs(action="where")


def test_edit_flag():
    assert parse_args(["--edit"]) == ParsedArgs(action="edit")
    assert parse_args(["-e"]) == ParsedArgs(action="edit")


def test_version_flag():
    assert parse_args(["--version"]) == ParsedArgs(action="version")


def test_help_flag():
    assert parse_args(["--help"]) == ParsedArgs(action="help")
    assert parse_args(["-h"]) == ParsedArgs(action="help")


def test_recipe_with_one_value():
    assert parse_args(["push", "fixed the parser"]) == ParsedArgs(
        action="run", recipe="push", values=("fixed the parser",)
    )


def test_recipe_with_no_values():
    assert parse_args(["test"]) == ParsedArgs(action="run", recipe="test", values=())


def test_dash_prefixed_value_is_passed_through_not_reparsed():
    # the exact case from the design spec section 7
    assert parse_args(["push", "--wip"]) == ParsedArgs(
        action="run", recipe="push", values=("--wip",)
    )


def test_dry_run_flag_takes_the_recipe_name():
    assert parse_args(["--dry-run", "push", "msg"]) == ParsedArgs(
        action="run", recipe="push", values=("msg",), dry_run=True
    )
    assert parse_args(["-n", "push"]) == ParsedArgs(
        action="run", recipe="push", values=(), dry_run=True
    )


def test_dry_run_without_a_recipe_name_is_a_usage_error():
    with pytest.raises(UsageError):
        parse_args(["--dry-run"])


def test_unknown_flag_is_a_usage_error():
    with pytest.raises(UsageError):
        parse_args(["--bogus"])


def test_recipe_named_list_is_not_confused_with_the_list_flag():
    assert parse_args(["list"]) == ParsedArgs(action="run", recipe="list", values=())
