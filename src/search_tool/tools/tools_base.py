"""The pieces every wrapped search tool shares."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from search_tool.query import Lowered, Query

Command = list[list[str]]
"""A pipeline of argument lists, each stage reading the stdout of the one before."""

Build = Callable[[Lowered, Path | None, tuple[str, ...], bool], Command]
"""Takes the lowered query, the directory, the ignored names and the case setting."""

Lowering = Callable[[Query], Lowered]
"""Takes the parsed query and writes it the way one tool takes it."""


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

Ranker = Callable[[list[Hit], str], list[Hit]]
"""Takes the hits of a search and the lowered query, and scores the hits."""


@dataclass(frozen=True)
class Tool:
    """One wrapped search program.

    Attributes:
        name: Canonical name, as a config file writes it.
        kind: Search kind, used by the `--kind` filter.
        finds: Kind of hit the parser reports, one of `file`, `command`,
            `manual` or `remote`. A search is only ever scored against the
            candidates of the kind it finds.
        needs_directory: Whether the tool searches a directory on disk.
        lower: Writes the parsed query in the syntax of this tool, or raises
            `Unsupported` where it cannot be written at all.
        build: Takes the lowered query, the directory, the directory names to
            ignore and whether to match case, and returns the command pipeline.
        build_json: The same for the machine-readable mode of the tool. Tools
            that only ever list paths use the one command for both.
        parse: Turns the standard output of `build_json` into hits.
        rank: Scores the hits of a tool that reports no score of its own,
            reading the lowered query. A synthesised score already runs from
            zero to one, so the run does not rescale it.
        weight: What one vote of this tool is worth against the other tools,
            counted into its reach as well as its vote. Below one for a tool
            that reads the same evidence as another, so the two together say
            less than two independent tools agreeing. A config file overrides
            it under `weights`.
    """

    name: str
    kind: str
    finds: str
    needs_directory: bool
    lower: Lowering
    build: Build
    build_json: Build
    parse: Parser
    weight: float = 1.0
    rank: Ranker | None = None


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
