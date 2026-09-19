"""Semantic search with ck."""

from pathlib import Path

from search_tool.tools.tools_base import Command, Hit, Tool, records


def _ck_excludes(ignore: tuple[str, ...]) -> list[str]:
    """Return the ck flags that prune each ignored directory name."""
    return [argument for name in ignore for argument in ("--exclude", name)]


def _ck_case(case_sensitive: bool) -> list[str]:
    """Return the ck case flag. ck matches case already, so it has no flag for it."""
    return [] if case_sensitive else ["-i"]


def _ck_semantic(
    query: str, directory: Path | None, ignore: tuple[str, ...], case_sensitive: bool
) -> Command:
    return [
        [
            "ck",
            "--sem",
            *_ck_case(case_sensitive),
            *_ck_excludes(ignore),
            query,
            str(directory),
        ]
    ]


def _ck_semantic_json(
    query: str, directory: Path | None, ignore: tuple[str, ...], case_sensitive: bool
) -> Command:
    return [
        [
            "ck",
            "--sem",
            "--jsonl",
            *_ck_case(case_sensitive),
            *_ck_excludes(ignore),
            query,
            str(directory),
        ]
    ]


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


CK = Tool("ck", "semantic", True, _ck_semantic, _ck_semantic_json, parse_ck)
