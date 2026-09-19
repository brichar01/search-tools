"""Regex search with ripgrep, over file contents and over path names."""

from pathlib import Path

from search_tool.query import Lowered, Query, to_regex
from search_tool.tools.tools_base import Command, Hit, Tool, records


def rg_globs(ignore: tuple[str, ...]) -> list[str]:
    """Return the ripgrep globs that prune each ignored directory name."""
    return [f"--glob=!{name}/" for name in ignore]


def rg_include(globs: tuple[str, ...]) -> list[str]:
    """Return the ripgrep globs that keep only what a path filter names."""
    return [f"--glob={glob}" for glob in globs]


def rg_case(case_sensitive: bool) -> list[str]:
    """Return the ripgrep flag that sets case matching.

    Both flags are passed, never left out, because a `RIPGREP_CONFIG_PATH` file
    can set smart case and a later flag wins.
    """
    return ["--case-sensitive" if case_sensitive else "--ignore-case"]


def lower_regex(query: Query) -> Lowered:
    """Return the query as one regular expression, with its path filters."""
    return Lowered(to_regex(query), query.paths)


def _ripgrep(
    lowered: Lowered, directory: Path | None, ignore: tuple[str, ...], case: bool
) -> Command:
    return [
        [
            "rg",
            "--color",
            "never",
            "--line-number",
            "--with-filename",
            *rg_case(case),
            *rg_globs(ignore),
            *rg_include(lowered.globs),
            "--",
            lowered.query,
            str(directory),
        ]
    ]


def _ripgrep_json(
    lowered: Lowered, directory: Path | None, ignore: tuple[str, ...], case: bool
) -> Command:
    return [
        [
            "rg",
            "--json",
            *rg_case(case),
            *rg_globs(ignore),
            *rg_include(lowered.globs),
            "--",
            lowered.query,
            str(directory),
        ]
    ]


def _ripgrep_files(
    lowered: Lowered, directory: Path | None, ignore: tuple[str, ...], case: bool
) -> Command:
    return [
        [
            "rg",
            "--files",
            *rg_globs(ignore),
            *rg_include(lowered.globs),
            str(directory),
        ],
        ["rg", "--color", "never", *rg_case(case), "--", lowered.query],
    ]


def parse_ripgrep(stdout: str) -> list[Hit]:
    """Return the matches of `rg --json`."""
    hits = []
    for record in records(stdout):
        if record.get("type") != "match":
            continue
        data = record["data"]
        text = data.get("lines", {}).get("text")
        if text is None:
            continue
        line = data["line_number"]
        hits.append(
            Hit(
                key=data["path"]["text"],
                kind="file",
                line=line,
                end_line=line,
                text=text.rstrip("\n"),
            )
        )
    return hits


def parse_paths(stdout: str) -> list[Hit]:
    """Return one whole-file hit per path listed."""
    return [
        Hit(key=line, kind="file", line=None, end_line=None, text=line)
        for line in stdout.splitlines()
        if line.strip()
    ]


RG = Tool(
    "rg",
    "regex",
    "file",
    True,
    lower_regex,
    _ripgrep,
    _ripgrep_json,
    parse_ripgrep,
)
RG_FILES = Tool(
    "rg-files",
    "files",
    "file",
    True,
    lower_regex,
    _ripgrep_files,
    _ripgrep_files,
    parse_paths,
)
