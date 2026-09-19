import pytest

from search_tool.query import (
    QueryError,
    Unsupported,
    parse,
    to_cql,
    to_fzf,
    to_regex,
    to_text,
    to_words,
    words,
)


def test_a_bare_word_is_one_literal_clause():
    query = parse("saturation")
    assert query.features == {"literal"}
    assert query.text == "saturation"
    assert to_regex(query) == "saturation"


def test_quotes_hold_a_phrase_and_slashes_hold_a_regex():
    assert parse('"open file"').features == {"phrase"}
    assert parse(r"/def\s.*:/").features == {"regex"}
    assert parse("/def/").clauses[0].atoms[0].text == "def"


def test_a_regex_holds_no_space_because_a_space_starts_a_term():
    assert parse("/def .*:/").features == {"literal", "and"}


def test_a_path_filter_is_kept_apart_from_the_terms():
    query = parse("path:*.py file:src/** cache")
    assert query.paths == ("*.py", "**/src/**")
    assert query.text == "cache"
    assert query.features == {"literal", "path"}


def test_or_joins_one_clause_and_a_dash_negates_another():
    query = parse("read OR write -test")
    assert [len(clause.atoms) for clause in query.clauses] == [2, 1]
    assert [clause.negated for clause in query.clauses] == [False, True]
    assert query.features == {"literal", "and", "or", "not"}


@pytest.mark.parametrize(
    "query",
    ['"unclosed', "OR alone", "alone OR", "-path:*.py", "-", '""'],
)
def test_an_unwritable_query_is_refused(query):
    with pytest.raises(QueryError):
        parse(query)


def test_a_literal_term_is_escaped_for_the_regex_tools():
    assert to_regex(parse("build.*plan")) == r"build\.\*plan"
    assert to_regex(parse("/build.*plan/")) == "build.*plan"


def test_terms_are_permuted_because_a_line_may_hold_them_either_way():
    assert to_regex(parse("open close")) == "(open).*(close)|(close).*(open)"


def test_the_regex_tools_refuse_negation_and_too_many_terms():
    with pytest.raises(Unsupported, match="negation"):
        to_regex(parse("open -close"))
    with pytest.raises(Unsupported, match="more than 3"):
        to_regex(parse("one two three four"))


def test_an_identifier_becomes_the_words_it_holds():
    assert words("build_candidates") == ["build", "candidates"]
    assert words("buildCandidates") == ["build", "Candidates"]
    assert words("HTTPServer") == ["HTTP", "Server"]


def test_the_semantic_tools_take_words_and_flatten_the_operators():
    assert to_words(parse("build_candidates OR planSearches")) == (
        "build candidates plan Searches"
    )
    assert to_words(parse("cache cache")) == "cache"


def test_the_semantic_tools_refuse_negation_and_a_regex():
    with pytest.raises(Unsupported, match="negation"):
        to_words(parse("cache -test"))
    with pytest.raises(Unsupported, match="regular expression"):
        to_words(parse("/ca.he/"))


def test_fzf_keeps_a_word_fuzzy_and_makes_a_phrase_exact():
    assert to_fzf(parse("reading")) == "reading"
    assert to_fzf(parse('"reading.py"')) == "'reading.py"
    assert to_fzf(parse("read OR write -test")) == "read | write !test"


def test_fzf_refuses_a_regex_and_a_term_holding_a_space():
    with pytest.raises(Unsupported, match="regular expression"):
        to_fzf(parse("/read/"))
    with pytest.raises(Unsupported, match="space"):
        to_fzf(parse('"open file"'))


def test_confluence_takes_the_operators_it_writes_itself():
    assert to_cql(parse('"open file" read OR write -test')) == (
        '"open file" AND (read OR write) AND NOT test'
    )
    with pytest.raises(Unsupported, match="regular expression"):
        to_cql(parse("/read/"))


def test_a_raw_tool_takes_the_query_as_typed_and_refuses_the_rest():
    allowed = frozenset({"literal", "and", "path"})
    assert to_text(parse("path:*.py def $F()"), allowed) == "def $F()"
    with pytest.raises(Unsupported, match="negation and a quoted phrase"):
        to_text(parse('-"open file"'), allowed)


def test_a_path_glob_naming_a_directory_is_read_at_any_depth():
    assert parse("path:src/** cache").paths == ("**/src/**",)
    assert parse("path:**/tests/* cache").paths == ("**/tests/*",)
    assert parse("path:*.py cache").paths == ("*.py",)
