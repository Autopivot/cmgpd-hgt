"""Unit tests for `server.mas.llm_helpers`.

`chat_json` is exercised by patching `openai.AsyncOpenAI` so the tests do not
need a live DASHSCOPE_API_KEY. Pure helpers (events_block / income_block /
render_prompt / is_llm_available) are tested directly.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.mas import llm_helpers


@pytest.fixture(autouse=True)
def _reset_client_cache():
    """Drop the cached AsyncOpenAI client between tests so each test starts
    from a clean slate and `patch("openai.AsyncOpenAI", ...)` actually wins.
    """
    llm_helpers._client_cache.clear()
    yield
    llm_helpers._client_cache.clear()


# ── render_prompt ─────────────────────────────────────────────────────────

def test_render_prompt_persona_returns_nonempty_string():
    out = llm_helpers.render_prompt(
        "persona",
        events_block="(no events on register)",
        income_block="(no income on register)",
        person_id="P1",
        role="target",
        sex="M",
        birth_year=1860,
        banner_id=4,
        community_id=117,
        household_id="X",
        pre_score=2.0,
        year=1882,
        ablation="ablated",
        hint_block="",
    )
    assert isinstance(out, str)
    assert out
    assert "P1" in out
    assert "target" in out
    assert "1882" in out
    assert "ablated" in out


def test_render_prompt_query_supports_query_fields():
    out = llm_helpers.render_prompt(
        "query",
        asker_id="P10",
        asker_role="target",
        round_focus="banner endogamy",
        asker_resume="resume text",
        candidate_block="cand block",
        hint_block="",
    )
    assert "P10" in out
    assert "banner endogamy" in out
    assert "cand block" in out


def test_render_prompt_answer_supports_answer_fields():
    out = llm_helpers.render_prompt(
        "answer",
        answerer_id="P20",
        answerer_role="candidate",
        round_focus="age compatibility",
        answerer_resume="my resume",
        asker_resume="their resume",
        asker_id="P10",
        question_text="why?",
        hint_block="",
    )
    assert "P20" in out
    assert "P10" in out
    assert "why?" in out


def test_render_prompt_score_supports_score_fields():
    out = llm_helpers.render_prompt(
        "score",
        scorer_id="P30",
        scorer_role="target",
        round_focus="final ranking",
        prior_scores_block="prior",
        exchanges_block="exch",
        hint_block="",
    )
    assert "P30" in out
    assert "prior" in out
    assert "exch" in out


def test_render_prompt_missing_field_raises_keyerror():
    with pytest.raises(KeyError):
        llm_helpers.render_prompt(
            "persona",
            # Deliberately omit several fields.
            person_id="P1",
        )


def test_render_prompt_unknown_template_raises():
    with pytest.raises(FileNotFoundError):
        llm_helpers.render_prompt("does_not_exist", x=1)


# ── events_block ──────────────────────────────────────────────────────────

def test_events_block_empty_returns_fallback():
    out = llm_helpers.events_block([])
    assert "no events" in out.lower()


def test_events_block_formats_rows_per_line():
    rows = [
        {"year": 1862, "event_1": "Birth", "event_2": None},
        {"year": 1880, "event_1": "In-Marriage", "event_2": None},
    ]
    out = llm_helpers.events_block(rows)
    lines = out.splitlines()
    assert len(lines) == 2
    assert "1862" in lines[0]
    assert "Birth" in lines[0]
    assert "1880" in lines[1]
    assert "In-Marriage" in lines[1]


def test_events_block_combines_event_1_and_event_2():
    rows = [{"year": 1880, "event_1": "In-Marriage", "event_2": "Returned after absconding"}]
    out = llm_helpers.events_block(rows)
    assert "In-Marriage" in out
    assert "Returned after absconding" in out


def test_events_block_drops_rows_with_only_nones():
    rows = [
        {"year": 1862, "event_1": "Birth", "event_2": None},
        {"year": 1870, "event_1": None, "event_2": None},
    ]
    out = llm_helpers.events_block(rows)
    lines = out.splitlines()
    assert len(lines) == 1
    assert "1862" in lines[0]


# ── income_block ──────────────────────────────────────────────────────────

def test_income_block_empty_returns_fallback():
    out = llm_helpers.income_block([])
    assert "no income" in out.lower()


def test_income_block_formats_rows_per_line():
    rows = [
        {"year": 1862, "income": 24, "level": "mid"},
        {"year": 1880, "income": 0, "level": "low"},
    ]
    out = llm_helpers.income_block(rows)
    lines = out.splitlines()
    assert len(lines) == 2
    assert "1862" in lines[0] and "24" in lines[0] and "mid" in lines[0]
    assert "1880" in lines[1] and "0" in lines[1] and "low" in lines[1]


def test_income_block_handles_float_amounts():
    rows = [{"year": 1862, "income": 24.5, "level": "mid"}]
    out = llm_helpers.income_block(rows)
    assert "1862" in out
    assert "24.5" in out


# ── is_llm_available ──────────────────────────────────────────────────────

def test_is_llm_available_returns_bool():
    out = llm_helpers.is_llm_available()
    assert isinstance(out, bool)


def test_is_llm_available_reflects_cfg(monkeypatch):
    from server.mas import agent
    monkeypatch.setitem(agent._cfg, "api_key", "")
    assert llm_helpers.is_llm_available() is False
    monkeypatch.setitem(agent._cfg, "api_key", "fake-key")
    assert llm_helpers.is_llm_available() is True


# ── chat_json ─────────────────────────────────────────────────────────────

def _mock_openai_response(content: str) -> MagicMock:
    """Build a fake AsyncOpenAI client whose chat.completions.create returns
    a response with `choices[0].message.content == content`."""
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)
    return client


def test_chat_json_returns_empty_when_no_api_key(monkeypatch):
    from server.mas import agent
    monkeypatch.setitem(agent._cfg, "api_key", "")
    out = asyncio.run(llm_helpers.chat_json([{"role": "user", "content": "hi"}]))
    assert out == {}


def test_chat_json_parses_valid_json(monkeypatch):
    from server.mas import agent
    monkeypatch.setitem(agent._cfg, "api_key", "fake-key")
    client = _mock_openai_response('{"ok": true, "n": 3}')
    with patch("openai.AsyncOpenAI", return_value=client):
        out = asyncio.run(
            llm_helpers.chat_json([
                {"role": "system", "content": "Return JSON only."},
                {"role": "user", "content": 'Reply with {"ok": true, "n": 3}.'},
            ])
        )
    assert out == {"ok": True, "n": 3}


def test_chat_json_retries_on_parse_failure(monkeypatch):
    """First call returns invalid JSON, second call succeeds."""
    from server.mas import agent
    monkeypatch.setitem(agent._cfg, "api_key", "fake-key")

    bad_resp = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="not json"))]
    )
    good_resp = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))]
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=[bad_resp, good_resp])

    with patch("openai.AsyncOpenAI", return_value=client):
        out = asyncio.run(
            llm_helpers.chat_json(
                [{"role": "user", "content": "hi"}],
                max_retries=2,
            )
        )
    assert out == {"ok": True}
    assert client.chat.completions.create.await_count == 2


def test_chat_json_returns_empty_after_max_retries(monkeypatch):
    from server.mas import agent
    monkeypatch.setitem(agent._cfg, "api_key", "fake-key")
    client = _mock_openai_response("still not json")
    with patch("openai.AsyncOpenAI", return_value=client):
        out = asyncio.run(
            llm_helpers.chat_json(
                [{"role": "user", "content": "hi"}],
                max_retries=2,
            )
        )
    assert out == {}
    # 1 initial attempt + max_retries = 3 calls.
    assert client.chat.completions.create.await_count == 3


def test_chat_json_includes_schema_hint_in_system_message(monkeypatch):
    from server.mas import agent
    monkeypatch.setitem(agent._cfg, "api_key", "fake-key")
    client = _mock_openai_response('{"ok": true}')
    with patch("openai.AsyncOpenAI", return_value=client):
        asyncio.run(
            llm_helpers.chat_json(
                [{"role": "system", "content": "sysprompt"},
                 {"role": "user", "content": "hi"}],
                json_schema_hint={"ok": "bool"},
            )
        )
    call_kwargs = client.chat.completions.create.await_args.kwargs
    sent_messages = call_kwargs["messages"]
    assert sent_messages[0]["role"] == "system"
    assert "sysprompt" in sent_messages[0]["content"]
    assert "ok" in sent_messages[0]["content"]


def test_chat_json_returns_empty_on_api_exception(monkeypatch):
    from server.mas import agent
    monkeypatch.setitem(agent._cfg, "api_key", "fake-key")
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=RuntimeError("boom"))
    with patch("openai.AsyncOpenAI", return_value=client):
        out = asyncio.run(
            llm_helpers.chat_json(
                [{"role": "user", "content": "hi"}],
                max_retries=1,
            )
        )
    assert out == {}
