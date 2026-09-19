"""Structural search with ast-grep.

An ast-grep pattern is code holding metavariables, a language of its own rather
than a subset of the query language, so nothing lowers into it. `ast` is a
second class search here and takes the query as typed: a quoted phrase, a
regex, a negated term or an OR skips it, and a path filter is the only part of
the language it takes. ast-grep has no case option either, so the case setting
of a run does not reach it.
"""

import json
from pathlib import Path

from search_tool.query import Lowered, Query, to_text
from search_tool.tools.tools_base import Command, Hit, Tool

RAW = frozenset({"literal", "and", "path"})
"""What an ast-grep pattern may be handed whole. Everything else skips the tool."""


def _ast_globs(ignore: tuple[str, ...]) -> list[str]:
    """Return the ast-grep globs that prune each ignored directory name."""
    return [f"--globs=!{name}/" for name in ignore]


def _ast_include(globs: tuple[str, ...]) -> list[str]:
    """Return the ast-grep globs that keep only what a path filter names."""
    return [f"--globs={glob}" for glob in globs]


def _lower(query: Query) -> Lowered:
    return Lowered(to_text(query, RAW), query.paths)


def _ast_grep(
    lowered: Lowered, directory: Path | None, ignore: tuple[str, ...], case: bool
) -> Command:
    return [
        [
            "ast-grep",
            "run",
            "--color",
            "never",
            *_ast_globs(ignore),
            *_ast_include(lowered.globs),
            "--pattern",
            lowered.query,
            str(directory),
        ]
    ]


def _ast_grep_json(
    lowered: Lowered, directory: Path | None, ignore: tuple[str, ...], case: bool
) -> Command:
    return [
        [
            "ast-grep",
            "run",
            "--json=compact",
            *_ast_globs(ignore),
            *_ast_include(lowered.globs),
            "--pattern",
            lowered.query,
            str(directory),
        ]
    ]


def parse_ast_grep(stdout: str) -> list[Hit]:
    """Return the matches of `ast-grep run --json=compact`.

    ast-grep counts lines from zero, the other tools from one.
    """
    try:
        matches = json.loads(stdout or "[]")
    except json.JSONDecodeError:
        return []
    hits = []
    for match in matches:
        span = match["range"]
        hits.append(
            Hit(
                key=match["file"],
                kind="file",
                line=span["start"]["line"] + 1,
                end_line=span["end"]["line"] + 1,
                text=match.get("text", ""),
            )
        )
    return hits


AST = Tool(
    "ast", "ast", "file", True, _lower, _ast_grep, _ast_grep_json, parse_ast_grep
)
