import pytest

from iop.template import TemplateError, placeholders, render, tokenize


def test_tokenize_splits_on_whitespace():
    assert tokenize("git commit -m {msg}") == ["git", "commit", "-m", "{msg}"]


def test_tokenize_keeps_quoted_placeholder_as_one_token():
    assert tokenize('git commit -m "{msg}"') == ["git", "commit", "-m", "{msg}"]


def test_tokenize_keeps_placeholder_inside_a_flag_as_one_token():
    assert tokenize("git commit --message={msg}") == [
        "git",
        "commit",
        "--message={msg}",
    ]


def test_tokenize_raises_on_unbalanced_quotes():
    with pytest.raises(TemplateError):
        tokenize('git commit -m "unterminated')


def test_placeholders_finds_a_single_name():
    assert placeholders(["git", "commit", "-m", "{msg}"]) == {"msg"}


def test_placeholders_finds_a_name_embedded_in_a_flag():
    assert placeholders(["git", "commit", "--message={msg}"]) == {"msg"}


def test_placeholders_ignores_escaped_braces():
    assert placeholders(["echo", "literal {{brace}} stays"]) == set()


def test_placeholders_finds_multiple_names_across_tokens():
    tokens = tokenize("cp {src} {dest}")
    assert placeholders(tokens) == {"src", "dest"}


def test_placeholders_rejects_non_identifier_field():
    with pytest.raises(TemplateError):
        placeholders(["echo", "{0}"])


def test_render_substitutes_a_value():
    tokens = tokenize("git commit -m {msg}")
    assert render(tokens, {"msg": "fixed the parser"}) == [
        "git",
        "commit",
        "-m",
        "fixed the parser",
    ]


def test_render_keeps_a_hostile_value_as_one_argument():
    # This is the property the whole module exists for: a value can
    # never become a new argument or shell metacharacter, because no
    # shell and no re-splitting ever sees it.
    tokens = tokenize("git commit -m {msg}")
    hostile = "fix; rm -rf /"
    result = render(tokens, {"msg": hostile})
    assert result == ["git", "commit", "-m", hostile]
    assert len(result) == 4  # not 6 -- the semicolon did not create new tokens


def test_render_substitutes_mid_token():
    tokens = tokenize("git commit --message={msg}")
    assert render(tokens, {"msg": "wip"}) == ["git", "commit", "--message=wip"]


def test_render_keeps_embedded_quotes_intact():
    tokens = tokenize("git commit -m {msg}")
    value = 'has "double" and \'single\' quotes'
    assert render(tokens, {"msg": value}) == ["git", "commit", "-m", value]


def test_render_accepts_empty_string_value():
    tokens = tokenize("echo {msg}")
    assert render(tokens, {"msg": ""}) == ["echo", ""]


def test_render_unescapes_literal_braces():
    tokens = tokenize('echo "literal {{brace}} stays"')
    assert render(tokens, {}) == ["echo", "literal {brace} stays"]


def test_render_raises_on_missing_value():
    tokens = tokenize("git commit -m {msg}")
    with pytest.raises(TemplateError):
        render(tokens, {})
