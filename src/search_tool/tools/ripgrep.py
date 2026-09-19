"""Regex search with ripgrep, over file contents and over path names."""

from pathlib import Path

from search_tool.tools.tools_base import Command, Hit, Tool, records


def rg_globs(ignore: tuple[str, ...]) -> list[str]:
    """Return the ripgrep globs that prune each ignored directory name."""
    return [f"--glob=!{name}/" for name in ignore]


def rg_case(case_sensitive: bool) -> list[str]:
    """Return the ripgrep flag that sets case matching.

    Both flags are passed, never left out, because a `RIPGREP_CONFIG_PATH` file
    can set smart case and a later flag wins.
    """
    return ["--case-sensitive" if case_sensitive else "--ignore-case"]


def _ripgrep(
    query: str, directory: Path | None, ignore: tuple[str, ...], case_sensitive: bool
) -> Command:
    return [
        [
            "rg",
            "--color",
            "never",
            "--line-number",
            "--with-filename",
            *rg_case(case_sensitive),
            *rg_globs(ignore),
            "--",
            query,
            str(directory),
        ]
    ]


def _ripgrep_json(
    query: str, directory: Path | None, ignore: tuple[str, ...], case_sensitive: bool
) -> Command:
    return [
        [
            "rg",
            "--json",
            *rg_case(case_sensitive),
            *rg_globs(ignore),
            "--",
            query,
            str(directory),
        ]
    ]


def _ripgrep_files(
    query: str, directory: Path | None, ignore: tuple[str, ...], case_sensitive: bool
) -> Command:
    return [
        ["rg", "--files", *rg_globs(ignore), str(directory)],
        ["rg", "--color", "never", *rg_case(case_sensitive), "--", query],
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


RG = Tool("rg", "regex", True, _ripgrep, _ripgrep_json, parse_ripgrep)
RG_FILES = Tool("rg-files", "files", True, _ripgrep_files, _ripgrep_files, parse_paths)
