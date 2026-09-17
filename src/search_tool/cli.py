"""Search several places with several tools from one command line.

Reads a YAML config file that names each place to search and the tools that
search it, then runs every selected tool and labels its output.
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from search_tool.candidates import Candidate, build_candidates
from search_tool.config import (
    ConfigError,
    Location,
    builtin_locations,
    load_config,
    select_locations,
)
from search_tool.runner import Result, plan_searches, run_search
from search_tool.tools import KINDS

ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def default_config_path() -> Path:
    """Return the config file to read where `--config` is not given."""
    override = os.environ.get("SEARCH_TOOL_CONFIG")
    if override:
        return Path(override)
    config_home = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(config_home) / "search-tool" / "config.yml"


def default_tldr_dir() -> Path:
    """Return the cheatsheet directory where `--tldr-dir` is not given.

    The tldr cheatsheets are a submodule of this repository, so the default is
    the checkout the package was installed from.
    """
    override = os.environ.get("SEARCH_TOOL_TLDR_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "tldr" / "pages"


def parse_args() -> argparse.Namespace:
    """Return the parsed command line."""
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Locations default to every leaf of the config file plus the "
            "built-in tldr, man and confluence locations."
        ),
    )
    parser.add_argument("query", help="Text, regular expression or AST pattern")
    parser.add_argument(
        "locations", nargs="*", help="Config leaves to search, all of them by default"
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=default_config_path(),
        help="YAML config file (default: %(default)s)",
    )
    parser.add_argument(
        "-s",
        "--subdir",
        help="Glob limiting each location to matching subdirectories",
    )
    parser.add_argument(
        "-k",
        "--kind",
        action="append",
        choices=KINDS,
        dest="kinds",
        default=[],
        metavar="KIND",
        help=f"Only run tools of this kind, repeatable. One of: {', '.join(KINDS)}",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Write JSON records for each search and each merged candidate",
    )
    parser.add_argument(
        "--tldr-dir",
        type=Path,
        default=default_tldr_dir(),
        help="Cheatsheet pages of the tldr submodule (default: %(default)s)",
    )
    return parser.parse_args()


def label(result: Result) -> str:
    """Return the header that names the tool and directory of a search."""
    parts = [f"[{result.search.location}]", result.search.tool]
    if result.search.directory is not None:
        parts.append(str(result.search.directory))
    return f"== {' '.join(parts)} =="


def write_text(result: Result, stream) -> None:
    """Write one result as a labelled block."""
    print(label(result), file=stream)
    for line in result.lines:
        print(line, file=stream)
    print(file=stream)


def write_search(result: Result, candidates: int, stream) -> None:
    """Write what one search ran and produced, as a single line of JSON."""
    search = result.search
    record = {
        "type": "search",
        "location": search.location,
        "tool": search.tool,
        "kind": search.kind,
        "directory": None if search.directory is None else str(search.directory),
        "command": search.command,
        "exit_code": result.exit_code,
        "candidates": candidates,
        "stderr": ANSI.sub("", result.stderr),
    }
    print(json.dumps(record), file=stream)


def write_candidate(candidate: Candidate, query: str, stream) -> None:
    """Write one merged candidate as a single line of JSON."""
    record = {"type": "candidate", "query": query} | asdict(candidate)
    record["text"] = ANSI.sub("", record["text"])
    print(json.dumps(record), file=stream)


def write_records(results: list[Result], query: str, stream) -> int:
    """Write a record per search and per candidate, and return the candidates.

    Every search is reported before the candidates, because a candidate merges
    hits from searches that ran at different times.
    """
    candidates = build_candidates(results)
    counts = Counter(
        (source.location, source.tool, source.directory)
        for candidate in candidates
        for source in candidate.sources
    )
    for result in results:
        search = result.search
        directory = None if search.directory is None else str(search.directory)
        key = (search.location, search.tool, directory)
        write_search(result, counts[key], stream)
    for candidate in candidates:
        write_candidate(candidate, query, stream)
    return len(candidates)


def main(
    query: str,
    locations: list[str],
    config: Path,
    subdir: str | None,
    kinds: list[str],
    json_output: bool,
    tldr_dir: Path,
) -> int:
    """Run every selected search and write the results to stdout.

    Args:
        query: Text, regular expression or AST pattern to search for.
        locations: Config leaves to search. Empty searches every location.
        config: YAML config file naming each location and its tools.
        subdir: Glob limiting each location to matching subdirectories.
        kinds: Search kinds to run. Empty runs every kind.
        json_output: Write JSON records for each search and each candidate,
            rather than the labelled output of each tool.
        tldr_dir: Cheatsheet pages of the tldr submodule.

    Returns:
        2 where a tool failed, 0 where anything matched, otherwise 1.
    """
    try:
        known: dict[str, Location] = load_config(config)
        for name, location in builtin_locations(tldr_dir).items():
            known.setdefault(name, location)
        chosen = select_locations(known, locations)
    except ConfigError as error:
        sys.exit(error.args[0])

    failed = False
    matched = False
    results = []
    for search in plan_searches(chosen, query, kinds, subdir, structured=json_output):
        result = run_search(search)
        results.append(result)
        if not json_output:
            write_text(result, sys.stdout)
            matched = matched or result.matched
        if result.exit_code > 1:
            failed = True
            if result.stderr:
                print(f"{label(result)} {result.stderr.strip()}", file=sys.stderr)
    if json_output:
        matched = write_records(results, query, sys.stdout) > 0
    if failed:
        return 2
    return 0 if matched else 1


def run() -> None:
    """Parse the command line and exit with the status of the search."""
    arguments = parse_args()
    sys.exit(
        main(
            query=arguments.query,
            locations=arguments.locations,
            config=arguments.config,
            subdir=arguments.subdir,
            kinds=arguments.kinds,
            json_output=arguments.json_output,
            tldr_dir=arguments.tldr_dir,
        )
    )


if __name__ == "__main__":
    run()
