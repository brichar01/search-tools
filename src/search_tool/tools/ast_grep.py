"""Structural search with ast-grep.

A pattern matches syntax nodes, and ast-grep has no case option, so the case
setting of a run does not reach it.
"""

import json
from pathlib import Path

from search_tool.tools.tools_base import Command, Hit, Tool


def _ast_globs(ignore: tuple[str, ...]) -> list[str]:
    """Return the ast-grep globs that prune each ignored directory name."""
    return [f"--globs=!{name}/" for name in ignore]


def _ast_grep(
    query: str, directory: Path | None, ignore: tuple[str, ...], case_sensitive: bool
) -> Command:
    return [
        [
            "ast-grep",
            "run",
            "--color",
            "never",
            *_ast_globs(ignore),
            "--pattern",
            query,
            str(directory),
        ]
    ]


def _ast_grep_json(
    query: str, directory: Path | None, ignore: tuple[str, ...], case_sensitive: bool
) -> Command:
    return [
        [
            "ast-grep",
            "run",
            "--json=compact",
            *_ast_globs(ignore),
            "--pattern",
            query,
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


AST = Tool("ast", "ast", True, _ast_grep, _ast_grep_json, parse_ast_grep)
