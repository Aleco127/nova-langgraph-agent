"""When the agent should stop answering and fetch a person."""

from __future__ import annotations

import pytest

from nova_agent.escalation import (
    MAX_REPEATED_TURNS,
    count_repeats,
    is_complaint,
    should_escalate,
    wants_human,
)
from nova_agent.state import new_state


@pytest.mark.parametrize(
    "message",
    [
        "quiero hablar con una persona",
        "puedo hablar con alguien?",
        "me pasas con un asesor",
        "quiero un ejecutivo",
        "QUIERO UN GERENTE",
        "eres un bot verdad",
    ],
)
def test_a_request_for_a_person_is_recognised_however_it_is_phrased(message: str) -> None:
    assert wants_human(message)


@pytest.mark.parametrize("message", ["hola", "cuanto cuesta?", "", None])
def test_ordinary_messages_do_not_trigger_a_handover(message: str | None) -> None:
    assert not wants_human(message)


@pytest.mark.parametrize(
    "message",
    [
        "quiero poner una queja",
        "esto es un fraude",
        "quiero mi reembolso",
        "hablare con mi abogado",
    ],
)
def test_complaints_are_flagged(message: str) -> None:
    assert is_complaint(message)


@pytest.mark.parametrize("message", ["me gusta la propuesta", "", None])
def test_a_sales_conversation_is_not_a_complaint(message: str | None) -> None:
    assert not is_complaint(message)


def _user(*contents: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": c} for c in contents]


def test_no_history_means_no_repeats() -> None:
    assert count_repeats([]) == 0


def test_history_with_only_agent_turns_counts_nothing() -> None:
    assert count_repeats([{"role": "assistant", "content": "hola"}]) == 0


def test_a_single_message_counts_as_one() -> None:
    assert count_repeats(_user("cuanto cuesta")) == 1


def test_repeats_are_matched_after_normalising_punctuation_and_case() -> None:
    # Nobody retypes a question identically the second time.
    assert count_repeats(_user("Cuanto cuesta?", "cuanto cuesta", "CUANTO CUESTA!!")) == 3


def test_the_streak_stops_at_the_first_different_message() -> None:
    assert count_repeats(_user("hola", "cuanto cuesta", "cuanto cuesta")) == 2


def test_agent_turns_between_repeats_do_not_break_the_streak() -> None:
    history = [
        {"role": "user", "content": "cuanto cuesta"},
        {"role": "assistant", "content": "te explico"},
        {"role": "user", "content": "cuanto cuesta"},
    ]
    assert count_repeats(history) == 2


def test_asking_for_a_person_escalates_immediately() -> None:
    state = new_state("me pasas con un asesor", channel="whatsapp")
    assert should_escalate(state)


def test_a_complaint_escalates_immediately() -> None:
    assert should_escalate(new_state("esto es un fraude", channel="web"))


def test_a_normal_first_message_does_not_escalate() -> None:
    assert not should_escalate(new_state("quiero una pagina web", channel="web"))


def test_repeating_up_to_the_limit_escalates() -> None:
    state = new_state("cuanto cuesta", channel="web")
    state["history"] = _user(*["cuanto cuesta"] * MAX_REPEATED_TURNS)
    assert should_escalate(state)


def test_repeating_below_the_limit_does_not() -> None:
    state = new_state("cuanto cuesta", channel="web")
    state["history"] = _user(*["cuanto cuesta"] * (MAX_REPEATED_TURNS - 1))
    assert not should_escalate(state)


def test_a_state_with_no_history_key_is_handled() -> None:
    # Graph nodes receive partial states; a missing key is not an error.
    assert not should_escalate({"message": "hola"})


def test_a_state_with_no_message_key_is_handled() -> None:
    assert not should_escalate({})


@pytest.mark.parametrize(
    "message",
    [
        "quiero hablar con un asesor",
        "quiero hablar con una asesor",
        "puedo hablar con un ejecutivo?",
        "hablar con un gerente por favor",
        "quiero una persona real",
    ],
)
def test_the_article_does_not_decide_whether_a_person_is_sent(message: str) -> None:
    """The pattern accepted "hablar con una persona" and "hablar con asesor" but
    not "hablar con un asesor", which is how people actually type it. Those leads
    stayed with the sales script after asking twice to leave it."""
    assert wants_human(message) is True
