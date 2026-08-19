"""The state object every graph node will read and write."""

from __future__ import annotations

from nova_agent.contacts import Contact
from nova_agent.intent import Directive, LeadFocus, SalesStage
from nova_agent.state import MAX_HISTORY_MESSAGES, new_state, trim_history


def test_a_fresh_thread_starts_with_nothing_assumed() -> None:
    state = new_state("hola", channel="web")
    assert state["message"] == "hola"
    assert state["channel"] == "web"
    assert state["conversation_id"] == ""
    assert state["history"] == []
    assert state["contact"] == Contact()
    assert state["focus"] is LeadFocus.UNKNOWN
    assert state["stage"] is SalesStage.NEW
    assert state["directive"] is Directive.NONE
    assert state["reply"] == ""
    assert state["needs_human"] is False


def test_conversation_id_is_carried_when_the_thread_already_exists() -> None:
    assert new_state("hola", channel="whatsapp", conversation_id="abc")["conversation_id"] == "abc"


def _turns(count: int) -> list[dict[str, str]]:
    return [{"role": "user", "content": str(i)} for i in range(count)]


def test_short_history_is_returned_untouched() -> None:
    history = _turns(5)
    assert trim_history(history) == history


def test_history_at_the_limit_is_not_trimmed() -> None:
    assert len(trim_history(_turns(MAX_HISTORY_MESSAGES))) == MAX_HISTORY_MESSAGES


def test_long_history_keeps_the_most_recent_turns() -> None:
    trimmed = trim_history(_turns(MAX_HISTORY_MESSAGES + 10))
    assert len(trimmed) == MAX_HISTORY_MESSAGES
    # Oldest dropped first: the last turn must survive, the first must not.
    assert trimmed[-1]["content"] == str(MAX_HISTORY_MESSAGES + 9)
    assert trimmed[0]["content"] == "10"


def test_trim_returns_a_copy_so_callers_cannot_mutate_the_original() -> None:
    history = _turns(3)
    trim_history(history).append({"role": "user", "content": "x"})
    assert len(history) == 3
