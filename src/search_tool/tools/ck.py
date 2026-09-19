"""Semantic and lexical search with ck."""

from pathlib import Path

from search_tool.query import Lowered, Query, no_paths, to_words
from search_tool.tools.tools_base import Build, Command, Hit, Tool, records

SHARED_INDEX = 0.6
"""Weight of one ck search. Semantic and lexical ck read the one index, so the
two of them agreeing says less than two tools that looked for different things.
"""


def _ck_excludes(ignore: tuple[str, ...]) -> list[str]:
    """Return the ck flags that prune each ignored directory name."""
    return [argument for name in ignore for argument in ("--exclude", name)]


def _ck_case(case_sensitive: bool) -> list[str]:
    """Return the ck case flag. ck matches case already, so it has no flag for it."""
    return [] if case_sensitive else ["-i"]


def _lower(query: Query) -> Lowered:
    """Return the query as words. ck 0.7 excludes paths but cannot keep only some."""
    return Lowered(to_words(query), no_paths(query))


def _search(mode: str, json: bool) -> Build:
    """Return the builder for one ck search mode.

    Args:
        mode: The mode flag, `--sem` or `--lex`.
        json: Ask for JSON lines rather than the text output.
    """

    def build(
        lowered: Lowered, directory: Path | None, ignore: tuple[str, ...], case: bool
    ) -> Command:
        return [
            [
                "ck",
                mode,
                *(["--jsonl"] if json else []),
                *_ck_case(case),
                *_ck_excludes(ignore),
                lowered.query,
                str(directory),
            ]
        ]

    return build


def parse_ck(stdout: str) -> list[Hit]:
    """Return the chunks of `ck --jsonl`."""
    hits = []
    for record in records(stdout):
        span = record.get("span", {})
        hits.append(
            Hit(
                key=record["path"],
                kind="file",
                line=span.get("line_start"),
                end_line=span.get("line_end", span.get("line_start")),
                text=record.get("snippet", ""),
                score=record.get("score"),
            )
        )
    return hits


CK = Tool(
    "ck",
    "semantic",
    "file",
    True,
    _lower,
    _search("--sem", False),
    _search("--sem", True),
    parse_ck,
    weight=SHARED_INDEX,
)
CK_LEX = Tool(
    "ck-lex",
    "lexical",
    "file",
    True,
    _lower,
    _search("--lex", False),
    _search("--lex", True),
    parse_ck,
    weight=SHARED_INDEX,
)
