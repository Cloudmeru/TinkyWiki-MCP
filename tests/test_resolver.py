from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from tinkywiki_mcp import resolver


def _result(owner: str, repo: str, stars: int = 0) -> resolver.SearchResult:
    return resolver.SearchResult(
        owner=owner,
        repo=repo,
        description=f"{owner}/{repo}",
        stars=stars,
        tinkywiki_url=f"https://codewiki.google/github.com/{owner}/{repo}",
    )


@pytest.fixture(autouse=True)
def _clean_resolver_caches():
    resolver._resolve_cache.clear()
    resolver._github_cache.clear()
    yield
    resolver._resolve_cache.clear()
    resolver._github_cache.clear()


def test_is_bare_keyword_variants():
    assert resolver.is_bare_keyword("vue")
    assert resolver.is_bare_keyword("react-native")
    assert not resolver.is_bare_keyword("")
    assert not resolver.is_bare_keyword("microsoft/vscode")
    assert not resolver.is_bare_keyword("https://github.com/microsoft/vscode")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", 0),
        ("52", 52),
        ("1.3k", 1300),
        ("2m", 2_000_000),
        ("1,234", 1234),
        ("bad", 0),
    ],
)
def test_parse_stars(text: str, expected: int):
    assert resolver._parse_stars(text) == expected


def test_extract_trailing_stars():
    assert resolver._extract_trailing_stars("repo description 12.4k") == 12_400
    assert resolver._extract_trailing_stars("repo description") == 0


def test_select_best_match_priority():
    rows = [
        _result("vue", "vue", stars=1),
        _result("vuejs", "vue", stars=10),
        _result("someone", "something", stars=999),
    ]
    best = resolver._select_best_match("vue", rows)
    assert best is not None
    assert best.full_name == "vue/vue"


def test_select_best_match_fallbacks():
    rows = [_result("abc", "hello-vue", 3), _result("other", "x", 1)]
    best_vue = resolver._select_best_match("vue", rows)
    assert best_vue is not None
    assert best_vue.full_name == "abc/hello-vue"
    best_none = resolver._select_best_match("none", rows)
    assert best_none is not None
    assert best_none.full_name == "abc/hello-vue"
    assert resolver._select_best_match("none", []) is None


@pytest.mark.asyncio
async def test_parse_search_result_link_absolute_and_relative():
    class _Link:
        def __init__(self, href: str, text: str):
            self._href = href
            self._text = text

        async def get_attribute(self, _name: str):
            return self._href

        async def inner_text(self):
            return self._text

    parsed = await resolver._parse_search_result_link(
        _Link("https://codewiki.google/github.com/microsoft/vscode", "vscode 10k")
    )
    assert parsed is not None
    assert parsed.full_name == "microsoft/vscode"
    assert parsed.stars == 10_000

    parsed2 = await resolver._parse_search_result_link(
        _Link("/github.com/pallets/flask", "flask 5")
    )
    assert parsed2 is not None
    assert parsed2.tinkywiki_url.startswith("https://")

    assert await resolver._parse_search_result_link(_Link("/nope", "x")) is None


def test_fetch_search_results_cache_hit(mocker):
    resolver._resolve_cache["vue"] = [_result("vuejs", "vue", 1)]
    mocked = mocker.patch("tinkywiki_mcp.resolver.run_in_browser_loop")
    out = resolver._fetch_search_results("vue")
    assert len(out) == 1
    mocked.assert_not_called()


def test_fetch_search_results_handles_errors(mocker):
    mocker.patch(
        "tinkywiki_mcp.resolver.run_in_browser_loop", side_effect=RuntimeError("boom")
    )
    assert resolver._fetch_search_results("vue") == []
    assert resolver._resolve_cache["vue"] == []


def test_github_search_success_and_cache(mocker):
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            payload = {
                "items": [
                    {
                        "full_name": "vuejs/vue",
                        "description": "Vue framework",
                        "stargazers_count": 200000,
                    }
                ]
            }
            return json.dumps(payload).encode()

    urlopen = mocker.patch("urllib.request.urlopen", return_value=_Resp())
    out = resolver._github_search("veu")
    assert out[0].full_name == "vuejs/vue"
    assert out[0].stars == 200000

    out2 = resolver._github_search("veu")
    assert out2[0].full_name == "vuejs/vue"
    assert urlopen.call_count == 1


def test_github_search_failure_returns_empty(mocker):
    mocker.patch("urllib.request.urlopen", side_effect=TimeoutError("timeout"))
    assert resolver._github_search("veu") == []


def test_resolve_keyword_paths(mocker):
    mocker.patch("tinkywiki_mcp.resolver._fetch_search_results", return_value=[])
    chosen, rows = resolver.resolve_keyword("vue")
    assert chosen is None
    assert rows == []

    rows = [_result("vuejs", "vue", 99), _result("other", "vue", 1)]
    mocker.patch("tinkywiki_mcp.resolver._fetch_search_results", return_value=rows)
    chosen, all_rows = resolver.resolve_keyword("vue")
    assert chosen == "vuejs/vue"
    assert len(all_rows) == 2


def test_format_and_canonical_helpers():
    assert resolver._format_stars(999) == "999"
    assert resolver._format_stars(1200) == "1.2k"
    assert resolver._format_stars(1_300_000) == "1.3M"

    rows = [_result("openclaw", "openclaw", 1), _result("x", "y", 1)]
    canonical = resolver._has_canonical_match("openclaw", rows)
    assert canonical is not None
    assert canonical.full_name == "openclaw/openclaw"
    assert resolver._has_canonical_match("none", rows) is None


def test_build_repo_choice_model_contains_enum_options():
    rows = [_result("microsoft", "vscode", 10), _result("microsoft", "terminal", 5)]
    model = resolver.build_repo_choice_model(rows)
    schema = model.model_json_schema()
    enum_values = schema["properties"]["selected_repo"]["enum"]
    assert enum_values == ["microsoft/vscode", "microsoft/terminal"]


@pytest.mark.asyncio
async def test_elicit_repo_choice_accept_and_decline():
    class _CtxAccept:
        async def elicit(self, **_kwargs):
            return SimpleNamespace(
                action="accept", data=SimpleNamespace(selected_repo="microsoft/vscode")
            )

    class _CtxDecline:
        async def elicit(self, **_kwargs):
            return SimpleNamespace(action="decline", data=None)

    rows = [_result("microsoft", "vscode", 10), _result("microsoft", "terminal", 5)]
    chosen = await resolver._elicit_repo_choice("vscode", rows, _CtxAccept())
    assert chosen == "microsoft/vscode"

    chosen2 = await resolver._elicit_repo_choice("vscode", rows, _CtxDecline())
    assert chosen2 is None


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
def test_resolve_keyword_interactive_branches(mocker):
    rows = [_result("microsoft", "vscode", 10), _result("microsoft", "terminal", 5)]

    mocker.patch("tinkywiki_mcp.resolver._fetch_search_results", return_value=[])
    mocker.patch("tinkywiki_mcp.resolver._github_search", return_value=[])
    chosen, out = resolver.resolve_keyword_interactive("vscode")
    assert chosen is None and out == []

    mocker.patch("tinkywiki_mcp.resolver._fetch_search_results", return_value=[rows[0]])
    chosen, out = resolver.resolve_keyword_interactive("vscode")
    assert chosen == "microsoft/vscode"
    assert len(out) == 1

    canonical = [_result("openclaw", "openclaw", 7), _result("x", "y", 1)]
    mocker.patch("tinkywiki_mcp.resolver._fetch_search_results", return_value=canonical)
    chosen, _ = resolver.resolve_keyword_interactive("openclaw")
    assert chosen == "openclaw/openclaw"


def test_resolve_keyword_interactive_elicitation_and_fallback(mocker):
    rows = [_result("microsoft", "vscode", 10), _result("ms", "vscode-docs", 1)]
    mocker.patch("tinkywiki_mcp.resolver._fetch_search_results", return_value=rows)
    mocker.patch(
        "tinkywiki_mcp.resolver.from_thread.run", return_value="microsoft/vscode"
    )
    chosen, _ = resolver.resolve_keyword_interactive("vscode", ctx=object())
    assert chosen == "microsoft/vscode"

    mocker.patch("tinkywiki_mcp.resolver.from_thread.run", return_value=None)
    chosen, _ = resolver.resolve_keyword_interactive("vscode", ctx=object())
    assert chosen == "microsoft/vscode"

    mocker.patch(
        "tinkywiki_mcp.resolver.from_thread.run", side_effect=RuntimeError("no elicit")
    )
    chosen, _ = resolver.resolve_keyword_interactive("vscode", ctx=object())
    assert chosen == "microsoft/vscode"
