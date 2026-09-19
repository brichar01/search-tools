"""Confluence search through the Rovo command line.

Confluence matches the query its own way and `twg rovo search` has no case
option, so the case setting of a run does not reach it.
"""

import json
from pathlib import Path

import yaml

from search_tool.tools.tools_base import Command, Hit, Tool


def _rovo(
    query: str, directory: Path | None, ignore: tuple[str, ...], case_sensitive: bool
) -> Command:
    return [["twg", "rovo", "search", query, "--app", "confluence"]]


def _rovo_json(
    query: str, directory: Path | None, ignore: tuple[str, ...], case_sensitive: bool
) -> Command:
    return [[*_rovo(query, directory, ignore, case_sensitive)[0], "--output", "json"]]


def _rovo_items(stdout: str) -> list[dict]:
    """Return the items of `twg rovo search -o json`.

    Some versions write the payload to a file and print a YAML envelope naming
    it, so read that file where the output is not JSON itself. The envelope ends
    with an `---END---` sentinel, which is not YAML.
    """
    stripped = stdout.strip()
    if not stripped:
        return []
    if stripped.startswith(("{", "[")):
        try:
            document = json.loads(stripped)
        except json.JSONDecodeError:
            return []
        return document.get("items", []) if isinstance(document, dict) else document
    body = stripped.split("\n---END---", 1)[0]
    try:
        envelope = yaml.safe_load(body)
    except yaml.YAMLError:
        return []
    if not isinstance(envelope, dict):
        return []
    payload = envelope.get("output_files", {}).get("stdout")
    if payload and Path(payload).is_file():
        return json.loads(Path(payload).read_text()).get("items", [])
    return envelope.get("stdout_inline", {}).get("items", [])


def parse_rovo(stdout: str) -> list[Hit]:
    """Return the pages of `twg rovo search -o json`."""
    hits = []
    for item in _rovo_items(stdout):
        title = item.get("title", "")
        body = item.get("text") or item.get("snippet") or ""
        hits.append(
            Hit(
                key=item.get("url") or item["id"],
                kind="remote",
                line=None,
                end_line=None,
                text=f"{title}\n{body}".strip(),
            )
        )
    return hits


ROVO = Tool("rovo", "remote", False, _rovo, _rovo_json, parse_rovo)
