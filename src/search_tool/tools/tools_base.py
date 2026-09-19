"""The pieces every wrapped search tool shares."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

Command = list[list[str]]
"""A pipeline of argument lists, each stage reading the stdout of the one before."""

Build = Callable[[str, Path | None, tuple[str, ...], bool], Command]
"""Takes the query, the directory, the ignored names and whether to match case."""


@dataclass(frozen=True)
class Hit:
    """One result a tool reported.

    Attributes:
        key: What the hit identifies, either an absolute path or a URL. Hits
            that share a key are candidates for merging.
        kind: `file`, `command`, `manual` or `remote`.
        line: First line of the match, or `None` where the tool matched a whole
            file or page.
        end_line: Last line of the match, or `None` alongside a `None` line.
        text: The matched text, for a later ranking stage to score.
        score: Relevance the tool reported, where it reports one.
    """

    key: str
    kind: str
    line: int | None
    end_line: int | None
    text: str
    score: float | None = None


Parser = Callable[[str], list[Hit]]
"""Takes the standard output of a tool and returns its hits."""


@dataclass(frozen=True)
class Tool:
    """One wrapped search program.

    Attributes:
        name: Canonical name, as a config file writes it.
        kind: Search kind, used by the `--kind` filter.
        needs_directory: Whether the tool searches a directory on disk.
        build: Takes the query, the directory, the directory names to ignore
            and whether to match case, and returns the command pipeline.
        build_json: The same for the machine-readable mode of the tool. Tools
            that only ever list paths use the one command for both.
        parse: Turns the standard output of `build_json` into hits.
    """

    name: str
    kind: str
    needs_directory: bool
    build: Build
    build_json: Build
    parse: Parser


def records(stdout: str) -> list[dict]:
    """Return the objects of a JSON lines document, skipping broken lines."""
    found = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            found.append(record)
    return found
