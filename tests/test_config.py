import pytest
import yaml

from search_tool.config import (
    ConfigError,
    Location,
    load_config,
    load_weights,
    parse_config,
    parse_weights,
    select_locations,
    starter_config,
    write_starter_config,
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


def test_parse_config_reads_the_ignore_list():
    locations = parse_config(
        {"source": {"directory": "/tmp", "tools": ["rg"], "ignore": [".venv", "dist"]}}
    )
    assert locations["source"].ignore == (".venv", "dist")


def test_parse_config_defaults_the_ignore_list_to_empty():
    locations = parse_config({"source": {"directory": "/tmp", "tools": ["rg"]}})
    assert locations["source"].ignore == ()


def test_parse_config_accepts_an_empty_document():
    assert parse_config(None) == {}


@pytest.mark.parametrize(
    "document",
    [
        {"source": {"directory": "/tmp", "tools": []}},
        {"source": {"directory": "/tmp", "tools": ["nope"]}},
        {"source": {"directory": "/tmp", "tools": "rg"}},
        {"source": {"directory": "/tmp", "tools": None}},
        {"source": {"tools": ["rg"]}},
        {"source": ["rg"]},
        {"source": {"directory": "/tmp", "tools": ["rg"], "ignore": ".venv"}},
        {"source": {"directory": "/tmp", "tools": ["rg"], "ignore": [3]}},
        {"source": {"directory": "/tmp", "tools": ["rg"], "ignore": [" "]}},
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


KNOWN = {
    "man": Location("man", ("man",)),
    "notes": Location("notes", ("rg",), None),
}


def test_select_locations_defaults_to_every_location():
    assert select_locations(KNOWN, []) == list(KNOWN.values())
    assert select_locations(KNOWN, ["man"]) == [KNOWN["man"]]


def test_select_locations_rejects_an_unknown_name():
    with pytest.raises(ConfigError, match="wiki"):
        select_locations(KNOWN, ["wiki"])


def test_select_locations_rejects_a_config_naming_nothing():
    with pytest.raises(ConfigError, match="--init"):
        select_locations({}, [])


def test_the_starter_config_declares_every_location_it_mentions():
    locations = parse_config(yaml.safe_load(starter_config()))
    assert {"man", "history", "tldr", "confluence"} <= set(locations)
    assert locations["man"].tools == ("man",)
    assert locations["history"].tools == ("hist",)


def test_write_starter_config_creates_the_parent_directory(tmp_path):
    path = tmp_path / "nested" / "config.yml"
    write_starter_config(path)
    assert parse_config(yaml.safe_load(path.read_text()))


def test_write_starter_config_refuses_to_overwrite(tmp_path):
    path = tmp_path / "config.yml"
    path.write_text("notes: {tools: [rg]}\n")
    with pytest.raises(ConfigError, match="already exists"):
        write_starter_config(path)
    assert path.read_text() == "notes: {tools: [rg]}\n"


def test_parse_weights_resolves_aliases_and_numbers():
    assert parse_weights({"weights": {"ripgrep": 2, "ck": 0.5}}) == {
        "rg": 2.0,
        "ck": 0.5,
    }


def test_parse_weights_defaults_to_none_set():
    assert parse_weights({"notes": {"tools": ["ck"]}}) == {}
    assert parse_weights(None) == {}


@pytest.mark.parametrize(
    "document",
    [
        {"weights": ["ck"]},
        {"weights": {"ck": "heavy"}},
        {"weights": {"ck": -1}},
        {"weights": {"nope": 1}},
    ],
)
def test_parse_weights_rejects_a_broken_weight(document):
    with pytest.raises(ConfigError):
        parse_weights(document)


def test_weights_are_not_a_location():
    document = {"weights": {"ck": 0.5}, "notes": {"directory": "/tmp", "tools": ["ck"]}}
    assert list(parse_config(document)) == ["notes"]


def test_load_weights_reads_a_file(tmp_path):
    path = tmp_path / "config.yml"
    path.write_text("weights:\n  ck: 0.5\nnotes:\n  directory: /tmp\n  tools: [ck]\n")
    assert load_weights(path) == {"ck": 0.5}


def test_load_weights_without_a_file(tmp_path):
    assert load_weights(tmp_path / "absent.yml") == {}
