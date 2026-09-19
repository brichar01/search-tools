"""Semantic search with the bundled model2vec index."""

from pathlib import Path

from search_tool.tools.tools_base import Command, Hit, Tool, records


def _skips(ignore: tuple[str, ...]) -> list[str]:
    """Return the search-tool-semantic flags that prune each ignored name."""
    return [argument for name in ignore for argument in ("--skip", name)]


def _case(case_sensitive: bool) -> list[str]:
    """Return the search-tool-semantic case flag, which folds case by default."""
    return ["--case-sensitive"] if case_sensitive else []


def _semantic(
    query: str, directory: Path | None, ignore: tuple[str, ...], case_sensitive: bool
) -> Command:
    return [
        [
            "search-tool-semantic",
            *_case(case_sensitive),
            *_skips(ignore),
            query,
            str(directory),
        ]
    ]


def _semantic_json(
    query: str, directory: Path | None, ignore: tuple[str, ...], case_sensitive: bool
) -> Command:
    return [
        [
            "search-tool-semantic",
            "--json",
            *_case(case_sensitive),
            *_skips(ignore),
            query,
            str(directory),
        ]
    ]


def parse_semantic(stdout: str) -> list[Hit]:
    """Return the lines of `search-tool-semantic --json`."""
    return [
        Hit(
            key=record["path"],
            kind="file",
            line=record["line"],
            end_line=record["line"],
            text=record["text"],
            score=record["score"],
        )
        for record in records(stdout)
    ]


M2V = Tool("m2v", "semantic", True, _semantic, _semantic_json, parse_semantic)
