"""Build the semantic index of every directory a semantic search would read.

`ck` builds its index during the first semantic search, which makes that search
slow. This walks the same locations as the search command and pre-builds the
index of each directory, so the search that follows only queries it.
"""

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from search_tool.config import (
    ConfigError,
    Location,
    default_config_path,
    load_config,
    select_locations,
)
from search_tool.runner import Search, run_search, targets
from search_tool.tools import TOOLS, Command


def _ck_index(directory: Path, ignore: tuple[str, ...]) -> Command:
    # ck --index reads its first positional as a pattern and the rest as paths.
    excludes = [argument for name in ignore for argument in ("--exclude", name)]
    return [["ck", "--index", "", *excludes, str(directory)]]


INDEXED_TOOLS: dict[str, Callable[[Path, tuple[str, ...]], Command]] = {"ck": _ck_index}
"""The tools that keep an index, and the command that builds it."""


def plan_indexes(locations: list[Location], subdir: str | None) -> list[Search]:
    """Return one index build per directory, in location then tool order.

    Args:
        locations: The selected locations.
        subdir: Glob limiting each location to matching subdirectories.

    Returns:
        A build for each directory an indexed tool searches. A directory named
        by several locations is built once.
    """
    indexes = []
    seen = set()
    for location in locations:
        for name in location.tools:
            build = INDEXED_TOOLS.get(name)
            if build is None:
                continue
            for directory in targets(location, subdir):
                if directory is None or directory in seen:
                    continue
                seen.add(directory)
                indexes.append(
                    Search(
                        location=location.name,
                        tool=name,
                        kind=TOOLS[name].kind,
                        directory=directory,
                        command=build(directory, location.ignore),
                    )
                )
    return indexes


def parse_args() -> argparse.Namespace:
    """Return the parsed command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "locations", nargs="*", help="Config leaves to index, all of them by default"
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
        "-n",
        "--dry-run",
        action="store_true",
        help="Write the directories that need indexing without indexing them",
    )
    return parser.parse_args()


def main(
    locations: list[str],
    config: Path,
    subdir: str | None,
    dry_run: bool,
) -> int:
    """Index every directory a semantic search would read.

    Args:
        locations: Config leaves to index. Empty indexes every location.
        config: YAML config file naming each location and its tools.
        subdir: Glob limiting each location to matching subdirectories.
        dry_run: Write the directories without running the index builds.

    Returns:
        2 where an index build failed, otherwise 0.
    """
    try:
        known: dict[str, Location] = load_config(config)
        chosen = select_locations(known, locations)
    except ConfigError as error:
        sys.exit(error.args[0])

    failed = False
    for index in plan_indexes(chosen, subdir):
        print(f"== [{index.location}] {index.tool} {index.directory} ==", flush=True)
        if dry_run:
            continue
        result = run_search(index)
        for line in result.lines:
            print(line)
        if result.exit_code != 0:
            failed = True
            if result.stderr:
                print(result.stderr.strip(), file=sys.stderr)
    return 2 if failed else 0


def run() -> None:
    """Parse the command line and exit with the status of the index builds."""
    arguments = parse_args()
    sys.exit(
        main(
            locations=arguments.locations,
            config=arguments.config,
            subdir=arguments.subdir,
            dry_run=arguments.dry_run,
        )
    )


if __name__ == "__main__":
    run()
