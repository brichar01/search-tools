"""Search locations, built in and loaded from a YAML config file."""

from dataclasses import dataclass
from os.path import expanduser, expandvars
from pathlib import Path

import yaml

from search_tool.tools import resolve_tool


class ConfigError(ValueError):
    """The config file does not describe a set of search locations."""


@dataclass(frozen=True)
class Location:
    """A named place to search and the tools that search it.

    Attributes:
        name: Leaf name from the config file, or a built-in name.
        tools: Canonical tool names, in the order they run.
        directory: Root that directory tools search, or `None` where every tool
            searches a system or remote source.
    """

    name: str
    tools: tuple[str, ...]
    directory: Path | None = None


def expand(directory: str) -> Path:
    """Return an absolute path with `~` and environment variables resolved."""
    return Path(expanduser(expandvars(directory))).absolute()


def builtin_locations(tldr_dir: Path) -> dict[str, Location]:
    """Return the locations that need no config file.

    Args:
        tldr_dir: The `pages` directory of the tldr cheatsheets submodule.
    """
    return {
        "tldr": Location("tldr", ("rg", "ck"), tldr_dir),
        "man": Location("man", ("man",)),
        "confluence": Location("confluence", ("rovo",)),
    }


def parse_config(document: object) -> dict[str, Location]:
    """Return the locations a parsed config document describes.

    Args:
        document: The object `yaml.safe_load` returned, or `None` for an empty file.

    Raises:
        ConfigError: A leaf is missing `tools`, or names a tool that needs a
            directory without giving one.
    """
    if document is None:
        return {}
    if not isinstance(document, dict):
        raise ConfigError("The config file must map a location name to its settings")

    locations = {}
    for name, leaf in document.items():
        if not isinstance(leaf, dict):
            raise ConfigError(f"Location {name!r} must be a mapping")
        raw_tools = leaf.get("tools")
        if not raw_tools:
            raise ConfigError(f"Location {name!r} lists no tools")
        directory = leaf.get("directory")
        tools = []
        for raw_tool in raw_tools:
            try:
                tool = resolve_tool(raw_tool)
            except KeyError as error:
                raise ConfigError(f"Location {name!r}: {error.args[0]}") from error
            if tool.needs_directory and directory is None:
                raise ConfigError(
                    f"Location {name!r} uses {tool.name!r}, which needs a directory"
                )
            tools.append(tool.name)
        locations[str(name)] = Location(
            name=str(name),
            tools=tuple(tools),
            directory=expand(directory) if directory is not None else None,
        )
    return locations


def load_config(path: Path) -> dict[str, Location]:
    """Return the locations a config file describes, or none where it is absent.

    Args:
        path: The YAML file to read.

    Raises:
        ConfigError: The file is not valid YAML, or describes something else.
    """
    if not path.is_file():
        return {}
    try:
        document = yaml.safe_load(path.read_text())
    except yaml.YAMLError as error:
        raise ConfigError(f"{path}: {error}") from error
    try:
        return parse_config(document)
    except ConfigError as error:
        raise ConfigError(f"{path}: {error.args[0]}") from error


def select_locations(
    locations: dict[str, Location], names: list[str]
) -> list[Location]:
    """Return the locations to search.

    Args:
        locations: Every known location, keyed by name.
        names: Names given on the command line. Empty selects every location.

    Raises:
        ConfigError: A name matches no location.
    """
    if not names:
        return list(locations.values())
    chosen = []
    for name in names:
        if name not in locations:
            known = ", ".join(locations)
            raise ConfigError(f"Unknown location {name!r}. Known locations: {known}")
        chosen.append(locations[name])
    return chosen
