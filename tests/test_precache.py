from search_tool.config import Location
from search_tool.precache import plan_indexes


def test_plan_indexes_covers_every_indexed_directory_once(tmp_path):
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    locations = [
        Location("source", ("rg", "ck"), tmp_path),
        Location("notes", ("ck",), tmp_path),
        Location("confluence", ("rovo",)),
    ]
    indexes = plan_indexes(locations, "*")
    assert [(index.location, index.directory) for index in indexes] == [
        ("source", tmp_path / "one"),
        ("source", tmp_path / "two"),
    ]
    assert indexes[0].command == [["ck", "--index", "", str(tmp_path / "one")]]


def test_plan_indexes_skips_locations_without_an_indexed_tool(tmp_path):
    assert plan_indexes([Location("man", ("man",))], None) == []
    assert plan_indexes([Location("source", ("rg",), tmp_path)], None) == []
