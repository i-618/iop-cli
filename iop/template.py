"""Pure token-level command templating.

No filesystem or subprocess access lives here: this module's only job is
splitting a command template into argv tokens and substituting values into
those tokens, so a value can never introduce a new argument or a shell
metacharacter (design spec section 6). Splitting always happens before
substitution -- that ordering is the entire safety property.
"""
from __future__ import annotations

import shlex
from string import Formatter


class TemplateError(Exception):
    """A command template could not be tokenized or rendered."""


def tokenize(template: str) -> list[str]:
    """Split a command template into argv tokens using POSIX shlex rules."""
    try:
        return shlex.split(template)
    except ValueError as exc:
        raise TemplateError(f"could not tokenize {template!r}: {exc}") from exc


def placeholders(tokens: list[str]) -> set[str]:
    """Return the variable names referenced across all tokens.

    Uses string.Formatter's own parser, so a literal `{{` / `}}` is
    correctly treated as text rather than a placeholder -- the same
    parser that render() relies on for substitution, so the two never
    disagree about what counts as a placeholder.
    """
    names: set[str] = set()
    formatter = Formatter()
    for token in tokens:
        for _, field_name, _, _ in formatter.parse(token):
            if field_name is None:
                continue
            if not field_name.isidentifier():
                raise TemplateError(
                    f"invalid placeholder {{{field_name}}} in {token!r}: "
                    "only bare names like {msg} are allowed"
                )
            names.add(field_name)
    return names


def render(tokens: list[str], values: dict[str, str]) -> list[str]:
    """Substitute values into tokens.

    Each token is formatted at most once, in a single pass. A value is
    inserted whole and is never re-scanned for further placeholders, so
    a value that happens to contain literal `{like_this}` text cannot
    trigger a second substitution.
    """
    rendered = []
    for token in tokens:
        if "{" in token:
            try:
                rendered.append(token.format(**values))
            except KeyError as exc:
                raise TemplateError(
                    f"missing value for placeholder {exc} in {token!r}"
                ) from exc
        else:
            rendered.append(token)
    return rendered
