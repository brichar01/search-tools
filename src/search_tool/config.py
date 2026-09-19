"""Search locations, built in and loaded from a YAML config file."""

from dataclasses import dataclass
from importlib.resources import files
from os import environ
from os.path import expanduser, expandvars
from pathlib import Path

import yaml

from search_tool.tools import resolve_tool


class ConfigError(ValueError):
    """The config file does not describe a set of search locations."""


WEIGHTS = "weights"
"""Top-level key holding the tool weights, so no location can take the name."""


@dataclass(frozen=True)
class Location:
    """A named place to search and the tools that search it.

    Attributes:
        name: Leaf name from the config file.
        tools: Canonical tool names, in the order they run.
        directory: Root that directory tools search, or `None` where every tool
            searches a system or remote source.
        ignore: Directory names every tool prunes, matched at any depth.
    """

    name: str
    tools: tuple[str, ...]
    directory: Path | None = None
    ignore: tuple[str, ...] = ()


def default_config_path() -> Path:
    """Return the config file to read where `--config` is not given."""
    override = environ.get("SEARCH_TOOL_CONFIG")
    if override:
        return Path(override)
    return Path.home() / ".config" / "search-tool" / "config.yml"


def starter_config() -> str:
    """Return the example config file that ships with the package."""
    return (files("search_tool") / "config.example.yml").read_text()


def write_starter_config(path: Path) -> None:
    """Write the example config file, for a machine that has none yet.

    Args:
        path: Where to write it. Parent directories are created.

    Raises:
        ConfigError: The path is already taken, so writing would lose whatever
            is there.
    """
    if path.exists():
        raise ConfigError(f"{path} already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(starter_config())


def expand(directory: str) -> Path:
    """Return an absolute path with `~` and environment variables resolved."""
    return Path(expanduser(expandvars(directory))).absolute()


def parse_ignore(name: object, raw: object) -> tuple[str, ...]:
    """Return the directory names a leaf prunes.

    Args:
        name: Location name, used in the error message.
        raw: The `ignore` value, or `None` where the leaf has none.

    Raises:
        ConfigError: The value is not a list of non-empty directory names.
    """
    if raw is None:
        return ()
    if isinstance(raw, str) or not isinstance(raw, list):
        raise ConfigError(f"Location {name!r}: ignore must be a list of names")
    names = []
    for entry in raw:
        if not isinstance(entry, str) or not entry.strip():
            raise ConfigError(f"Location {name!r}: {entry!r} is not a directory name")
        names.append(entry)
    return tuple(names)


def parse_weights(document: object) -> dict[str, float]:
    """Return the tool weights a parsed config document sets.

    Args:
        document: The object `yaml.safe_load` returned.

    Returns:
        Each named tool and what one of its votes is worth, keyed by canonical
        name. A tool left out keeps the weight the tool itself declares.

    Raises:
        ConfigError: The `weights` key is not a mapping of known tools to
            numbers that are zero or more.
    """
    if not isinstance(document, dict):
        return {}
    raw = document.get(WEIGHTS)
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{WEIGHTS} must map a tool name to a number")
    weights = {}
    for name, value in raw.items():
        try:
            tool = resolve_tool(name)
        except KeyError as error:
            raise ConfigError(f"{WEIGHTS}: {error.args[0]}") from error
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ConfigError(f"{WEIGHTS}: {name!r} must be a number")
        if value < 0:
            raise ConfigError(f"{WEIGHTS}: {name!r} cannot be negative")
        weights[tool.name] = float(value)
    return weights


def parse_config(document: object) -> dict[str, Location]:
    """Return the locations a parsed config document describes.

    Args:
        document: The object `yaml.safe_load` returned, or `None` for an empty file.

    Raises:
        ConfigError: A leaf is missing `tools`, gives something other than a
            list of tools, names a tool that needs a directory without giving
            one, or lists something other than directory names under `ignore`.
            The `weights` key holds the tool weights, not a location.
    """
    if document is None:
        return {}
    if not isinstance(document, dict):
        raise ConfigError("The config file must map a location name to its settings")

    locations = {}
    for name, leaf in document.items():
        if name == WEIGHTS:
            continue
        if not isinstance(leaf, dict):
            raise ConfigError(f"Location {name!r} must be a mapping")
        raw_tools = leaf.get("tools")
        if not raw_tools:
            raise ConfigError(f"Location {name!r} lists no tools")
        if not isinstance(raw_tools, list):
            raise ConfigError(f"Location {name!r} must list its tools")
        directory = leaf.get("directory")
        ignore = parse_ignore(name, leaf.get("ignore"))
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
            ignore=ignore,
        )
    return locations


def load_weights(path: Path) -> dict[str, float]:
    """Return the tool weights a config file sets, or none where it is absent.

    Args:
        path: The YAML file to read.

    Raises:
        ConfigError: The file is not valid YAML, or sets a weight that is not a
            number against a known tool.
    """
    if not path.is_file():
        return {}
    try:
        document = yaml.safe_load(path.read_text())
    except yaml.YAMLError as error:
        raise ConfigError(f"{path}: {error}") from error
    try:
        return parse_weights(document)
    except ConfigError as error:
        raise ConfigError(f"{path}: {error.args[0]}") from error


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
        ConfigError: The config file names no location, or a name matches none.
    """
    if not locations:
        raise ConfigError(
            "The config file names no location. Run search-tool --init to "
            "write the example one."
        )
    if not names:
        return list(locations.values())
    chosen = []
    for name in names:
        if name not in locations:
            known = ", ".join(locations)
            raise ConfigError(f"Unknown location {name!r}. Known locations: {known}")
        chosen.append(locations[name])
    return chosen
