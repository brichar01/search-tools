from pathlib import Path

from search_tool.candidates import build_candidates
from search_tool.fusion import score_targets
from search_tool.runner import Result, Search
from search_tool.tools.fzf import rank_paths
from search_tool.tools.ripgrep import parse_paths


def ranked(query, *paths):
    hits = rank_paths(parse_paths("\n".join(paths)), query)
    return {hit.key: hit.score for hit in hits}


def result(tool, stdout, query, directory=Path("/src")):
    search = Search("source", tool, "files", directory, [["fake"]], None, query)
    return Result(search, 0, stdout, "")


def test_an_exact_path_and_a_typo_both_score_almost_a_whole_vote():
    scores = ranked("fusion", "/src/fusion.py", "/src/fusiom.py")
    assert scores["/src/fusion.py"] == 1.0
    assert round(scores["/src/fusiom.py"], 3) == 0.929


def test_a_path_further_out_falls_away():
    scores = ranked("connect", "/src/collect.py", "/src/parser.py")
    assert round(scores["/src/collect.py"], 3) == 0.871
    assert scores["/src/parser.py"] < 0.4


def test_one_edit_costs_a_short_term_more_than_a_long_one():
    short = ranked("tui", "/src/tua.py")["/src/tua.py"]
    long = ranked("candidates", "/src/candidatos.py")["/src/candidatos.py"]
    assert short < long
    assert round(short, 3) == 0.845
    assert round(long, 3) == 0.959


def test_a_term_nothing_matches_is_worth_nothing():
    assert ranked("tui", "/abc/def.md")["/abc/def.md"] == 0.0


def test_a_term_is_measured_against_the_part_of_the_path_it_matched():
    scores = ranked("fusion", "/src/fusion.py", "/home/user/src/tests/test_fusion.py")
    assert set(scores.values()) == {1.0}


def test_a_negated_term_does_not_score():
    scores = ranked("fusion !test", "/src/fusion.py")
    assert scores["/src/fusion.py"] == 1.0


def test_the_nearest_term_of_an_alternative_scores():
    scores = ranked("parser | fusion", "/src/fusion.py")
    assert scores["/src/fusion.py"] == 1.0


def test_a_weak_run_of_paths_is_not_spread_over_the_whole_scale():
    results = [result("fzf", "/src/xylophone.py\n/src/zimbabwe.py", "connect")]
    targets = score_targets(build_candidates(results), results, prior=0.0)
    assert all(target.relevance < 0.7 for target in targets)


def test_fzf_agreeing_on_a_poor_path_counts_for_less_than_on_a_good_one():
    good = result("fzf", "/src/connect.py", "connect")
    poor = result("fzf", "/src/xylophone.py", "connect")
    (best,) = score_targets(build_candidates([good]), [good], prior=0.0)
    (worst,) = score_targets(build_candidates([poor]), [poor], prior=0.0)
    assert best.relevance > worst.relevance
