"""Nodes called directly, for the cases the graph cannot reach on its own."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage

from nova_agent.contacts import Contact
from nova_agent.intent import Directive, LeadFocus
from nova_agent.nodes import (
    RETRY_BACKOFF_SECONDS,
    _prompt_messages,
    _text_of,
    classify,
    deliver,
    escalation_reason,
    give_up,
    make_revise,
    validate,
)
from nova_agent.outbound import WHATSAPP_LIMIT
from nova_agent.prompts import BASE_PROMPT, system_prompt
from nova_agent.state import ConversationState, new_state, turn_input


def test_a_reply_that_arrives_as_content_blocks_is_read_as_text() -> None:
    """Providers that support mixed content return a list, not a string. Handed
    to the validator unflattened it arrives as "[{'type': 'text', ...}]", which
    fails for a reason that has nothing to do with what the agent said."""
    blocks = AIMessage(
        content=[
            {"type": "text", "text": "El setup "},
            {"type": "text", "text": "es de $2,499."},
        ]
    )
    assert _text_of(blocks) == "El setup es de $2,499."


def test_content_blocks_that_are_not_text_are_skipped() -> None:
    message = AIMessage(content=[{"type": "image", "url": "x"}, {"type": "text", "text": "hola"}])
    assert _text_of(message) == "hola"


def test_classify_keeps_a_phone_collected_in_an_earlier_turn() -> None:
    """A turn that mentions an email must not erase the number from turn one."""
    state = ConversationState(
        message="mi correo es ricardo@zook.mx",
        contact=Contact(phone="+5213312345678"),
    )
    updated = classify(state)
    assert updated["contact"].phone == "+5213312345678"
    assert updated["contact"].email == "ricardo@zook.mx"


def test_classify_clears_the_previous_turns_scratchpad() -> None:
    updated = classify(ConversationState(message="hola"))
    assert updated["messages"][0].id == "__remove_all__"
    assert updated["attempts"] == 0
    assert updated["pending_tool_calls"] == 0


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (ConversationState(message="quiero hablar con un asesor"), "asked_for_human"),
        (ConversationState(message="voy a pedir un reembolso"), "complaint"),
        (ConversationState(message="hola"), ""),
        (ConversationState(), ""),
    ],
)
def test_escalation_reason_names_the_rule_that_fired(
    state: ConversationState, expected: str
) -> None:
    assert escalation_reason(state) == expected


def test_the_prompt_puts_history_before_this_turns_scratchpad() -> None:
    state = ConversationState(
        directive=Directive.WEB_SALES,
        history=[
            {"role": "user", "content": "hola"},
            {"role": "assistant", "content": "que tal"},
        ],
        messages=[AIMessage(content="borrador")],
    )
    contents = [message.content for message in _prompt_messages(state)]
    assert contents == [system_prompt(Directive.WEB_SALES), "hola", "que tal", "borrador"]


def test_a_history_turn_with_no_role_is_treated_as_the_customer() -> None:
    """Anything that reached the transcript without a role came from an ingest
    path, and those only ever write inbound messages."""
    state = ConversationState(directive=Directive.NONE, history=[{"content": "sin rol"}])
    assert _prompt_messages(state)[1].content == "sin rol"


def test_validate_clears_the_instruction_once_a_draft_passes() -> None:
    """Left behind, it would be handed to the next redraft as a correction for a
    rule the reply no longer breaks."""
    updated = validate(ConversationState(reply="Todo bien.", revision_instruction="vieja"))
    assert updated["validation_error"] == ""
    assert updated["revision_instruction"] == ""


def test_validate_reports_the_rule_and_how_to_fix_it() -> None:
    updated = validate(ConversationState(reply="Somos una IA."))
    assert updated["validation_error"] == "ai_jargon"
    assert "inteligencia artificial" in updated["revision_instruction"]


def test_revise_falls_back_to_a_generic_correction() -> None:
    """Unreachable through the graph, since ``validate`` always sets one. A node
    that raised here would take down a turn that was already recovering."""
    updated = make_revise(lambda _: None)(ConversationState(attempts=1))
    assert "Corrige" in updated["messages"][0].content


def test_revise_backs_off_further_on_each_attempt() -> None:
    waits: list[float] = []
    revise = make_revise(waits.append)
    for attempt in (1, 2, 3):
        revise(ConversationState(attempts=attempt))
    assert waits == [
        RETRY_BACKOFF_SECONDS,
        RETRY_BACKOFF_SECONDS * 2,
        RETRY_BACKOFF_SECONDS * 4,
    ]


def test_deliver_splits_a_reply_the_channel_would_reject() -> None:
    long_reply = "palabra " * 1200
    updated = deliver(ConversationState(message="hola", reply=long_reply))
    assert len(updated["outbound"]) > 1
    assert all(len(part) <= WHATSAPP_LIMIT for part in updated["outbound"])


def test_give_up_names_the_rule_that_defeated_the_model() -> None:
    updated = give_up(ConversationState(validation_error="invented_price"))
    assert updated["escalation_reason"] == "validation_failed:invented_price"
    assert updated["reply"] == ""


def test_give_up_still_says_something_when_the_rule_is_missing() -> None:
    assert give_up(ConversationState())["escalation_reason"] == "validation_failed:unknown"


def test_turn_input_carries_only_what_the_turn_brings() -> None:
    assert turn_input("hola") == {"message": "hola"}


def test_turn_input_keeps_the_channel_and_thread_when_given() -> None:
    state = turn_input("hola", channel="whatsapp", conversation_id="c-9")
    assert state == {"message": "hola", "channel": "whatsapp", "conversation_id": "c-9"}


def test_new_state_starts_a_thread_with_nothing_assumed() -> None:
    state = new_state("hola", channel="web")
    assert state["focus"] is LeadFocus.UNKNOWN
    assert state["pending_tool_calls"] == 0
    assert state["revision_instruction"] == ""


def test_every_directive_has_its_own_instruction_block() -> None:
    """A missing block would silently run the generic agent, which is how a lead
    gets the wrong conversation without anything looking broken."""
    blocks = {system_prompt(directive) for directive in Directive}
    assert len(blocks) == len(Directive)
    for prompt in blocks:
        assert prompt.startswith(BASE_PROMPT)
