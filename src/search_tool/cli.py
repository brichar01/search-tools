"""Search several places with several tools from one command line.

Reads a YAML config file that names each place to search and the tools that
search it, then runs every selected tool and labels its output.
"""

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from search_tool.candidates import Candidate, build_candidates
from search_tool.config import (
    ConfigError,
    Location,
    default_config_path,
    load_config,
    select_locations,
    write_starter_config,
)
from search_tool.precache import main as run_precache
from search_tool.runner import Result, plan_searches, run_search
from search_tool.tools import KIND_FLAGS, KINDS

ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def parse_args() -> argparse.Namespace:
    """Return the parsed command line."""
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Every location comes from the config file. Run --init to write "
            "the example one, then edit it."
        ),
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="Text, regular expression or AST pattern. A location with --precache",
    )
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
        choices=KIND_FLAGS,
        dest="kinds",
        default=[],
        metavar="KIND",
        help=(
            "Only run tools of this kind, repeatable. Prefix with ! to drop a "
            f"kind instead, as in !remote. One of: {', '.join(KINDS)}"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Write JSON records for each search and each merged candidate",
    )
    parser.add_argument(
        "-p",
        "--precache",
        action="store_true",
        help="Build the index of every semantic tool and search nothing",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Write the example config file to --config and search nothing",
    )
    arguments = parser.parse_args()
    if arguments.init:
        arguments.query = None
    elif arguments.precache:
        if arguments.query is not None:
            arguments.locations.insert(0, arguments.query)
            arguments.query = None
    elif arguments.query is None:
        parser.error("a query is required")
    return arguments


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
    query: str | None,
    locations: list[str],
    config: Path,
    subdir: str | None,
    kinds: list[str],
    json_output: bool,
    precache: bool,
    init: bool,
) -> int:
    """Run every selected search and write the results to stdout.

    Args:
        query: Text, regular expression or AST pattern to search for. Ignored
            where `precache` is set.
        locations: Config leaves to search. Empty searches every location.
        config: YAML config file naming each location and its tools.
        subdir: Glob limiting each location to matching subdirectories.
        kinds: Search kinds to run, each optionally negated with `!`. Empty
            runs every kind.
        json_output: Write JSON records for each search and each candidate,
            rather than the labelled output of each tool.
        precache: Build the index of every semantic tool instead of searching.
        init: Write the example config file instead of searching.

    Returns:
        2 where a tool failed, 0 where anything matched, otherwise 1. Where
        `precache` is set, 2 where an index build failed, otherwise 0. Where
        `init` is set, 0 where the file was written.
    """
    if init:
        try:
            write_starter_config(config)
        except (ConfigError, OSError) as error:
            sys.exit(str(error.args[0]))
        print(f"Wrote {config}")
        return 0

    if precache:
        return run_precache(
            locations=locations,
            config=config,
            subdir=subdir,
            dry_run=False,
        )

    try:
        known: dict[str, Location] = load_config(config)
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
            precache=arguments.precache,
            init=arguments.init,
        )
    )


if __name__ == "__main__":
    run()
