import pytest
import yaml

from search_tool.config import (
    ConfigError,
    Location,
    builtin_locations,
    load_config,
    parse_config,
    select_locations,
)


def test_parse_config_resolves_aliases_and_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("NOTES", str(tmp_path))
    locations = parse_config(
        {
            "source": {"directory": "$NOTES/src", "tools": ["ast", "ripgrep"]},
            "wiki": {"tools": ["confluence"]},
        }
    )
    assert locations["source"].tools == ("ast", "rg")
    assert locations["source"].directory == tmp_path / "src"
    assert locations["wiki"] == Location("wiki", ("rovo",), None)


def test_parse_config_accepts_an_empty_document():
    assert parse_config(None) == {}


@pytest.mark.parametrize(
    "document",
    [
        {"source": {"directory": "/tmp", "tools": []}},
        {"source": {"directory": "/tmp", "tools": ["nope"]}},
        {"source": {"tools": ["rg"]}},
        {"source": ["rg"]},
        ["source"],
    ],
)
def test_parse_config_rejects_a_broken_leaf(document):
    with pytest.raises(ConfigError):
        parse_config(document)


def test_load_config_without_a_file(tmp_path):
    assert load_config(tmp_path / "absent.yml") == {}


def test_load_config_reads_a_file(tmp_path):
    path = tmp_path / "config.yml"
    path.write_text(yaml.safe_dump({"notes": {"directory": "/tmp", "tools": ["ck"]}}))
    assert load_config(path)["notes"].tools == ("ck",)


def test_load_config_rejects_broken_yaml(tmp_path):
    path = tmp_path / "config.yml"
    path.write_text("notes: [unclosed\n")
    with pytest.raises(ConfigError, match=str(path)):
        load_config(path)


def test_builtin_locations(tmp_path):
    builtins = builtin_locations(tmp_path)
    assert builtins["tldr"].directory == tmp_path
    assert builtins["man"].directory is None
    assert set(builtins) == {"tldr", "man", "confluence"}


def test_select_locations_defaults_to_every_location(tmp_path):
    known = builtin_locations(tmp_path)
    assert select_locations(known, []) == list(known.values())
    assert select_locations(known, ["man"]) == [known["man"]]


def test_select_locations_rejects_an_unknown_name(tmp_path):
    with pytest.raises(ConfigError, match="notes"):
        select_locations(builtin_locations(tmp_path), ["notes"])
