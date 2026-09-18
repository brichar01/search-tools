"""Turn the machine-readable output of each tool into hits."""

import json
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Hit:
    """One result a tool reported.

    Attributes:
        key: What the hit identifies, either an absolute path or a URL. Hits
            that share a key are candidates for merging.
        kind: `file`, `manual` or `remote`.
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


def _records(stdout: str) -> list[dict]:
    """Return the objects of a JSON lines document, skipping broken lines."""
    records = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def parse_ripgrep(stdout: str) -> list[Hit]:
    """Return the matches of `rg --json`."""
    hits = []
    for record in _records(stdout):
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


def parse_ck(stdout: str) -> list[Hit]:
    """Return the chunks of `ck --jsonl`."""
    hits = []
    for record in _records(stdout):
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
        for record in _records(stdout)
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


def parse_paths(stdout: str) -> list[Hit]:
    """Return one whole-file hit per path listed."""
    return [
        Hit(key=line, kind="file", line=None, end_line=None, text=line)
        for line in stdout.splitlines()
        if line.strip()
    ]


def parse_man(stdout: str) -> list[Hit]:
    """Return one hit per manual page path, named the way `man` is called."""
    hits = []
    for line in stdout.splitlines():
        path = line.strip()
        if not path:
            continue
        name = Path(path).name
        name = name.removesuffix(".gz")
        stem, _, section = name.rpartition(".")
        hits.append(
            Hit(
                key=path,
                kind="manual",
                line=None,
                end_line=None,
                text=f"{stem}({section})" if stem else name,
            )
        )
    return hits


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
