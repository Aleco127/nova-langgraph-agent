"""State transitions: which edge was taken, and why.

These are the tests that could only be written against a graph. Everything they
assert -- that the retry loop stops, that an exhausted turn reaches a human
instead of sending its last draft, that a second turn can see the first -- is a
property of the wiring, not of any one function. The functions themselves are
tested elsewhere, by calling them.

No test here reaches the network or needs an API key. The model is scripted and
the clock is a list.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from conftest import Turn, run_turn
from nova_agent.graph import (
    MAX_TOOL_ROUNDS,
    route_after_classify,
    route_after_generate,
    route_after_validate,
)
from nova_agent.intent import LeadFocus, SalesStage
from nova_agent.nodes import RETRY_BACKOFF_SECONDS
from nova_agent.state import MAX_GENERATION_ATTEMPTS, ConversationState, new_state

GOOD = "Con gusto, el setup es de $2,499 y son 650 pesos al mes."
AI_JARGON = "Somos una IA de ultima generacion."
BAD_PRICE = "Te lo dejo en $1,800, precio especial."


def _tool_call_draft(plan: str = "bot-whatsapp") -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "consultar_precio",
                "args": {"plan": plan},
                "id": "call-1",
                "type": "tool_call",
            }
        ],
    )


# --------------------------------------------------------------------------
# The common case
# --------------------------------------------------------------------------


def test_a_clean_first_draft_is_delivered_without_looping() -> None:
    result = run_turn([GOOD], "cuanto cuesta el bot")
    assert result.state["reply"] == GOOD
    assert result.state["outbound"] == [GOOD]
    assert result.state["attempts"] == 1
    assert result.waits == []
    assert result.interrupted is False


def test_the_delivered_turn_is_recorded_in_history() -> None:
    result = run_turn([GOOD], "cuanto cuesta")
    assert result.state["history"] == [
        {"role": "user", "content": "cuanto cuesta"},
        {"role": "assistant", "content": GOOD},
    ]


# --------------------------------------------------------------------------
# The cycle
# --------------------------------------------------------------------------


def test_a_rejected_draft_is_redrafted_and_the_second_one_ships() -> None:
    result = run_turn([AI_JARGON, GOOD], "cuanto cuesta")
    assert result.state["reply"] == GOOD
    assert result.state["attempts"] == 2
    assert result.state["validation_error"] == ""


def test_each_retry_waits_longer_than_the_last() -> None:
    """Backoff is asserted through the injected clock. A test that really slept
    would be measuring ``time.sleep``."""
    result = run_turn([AI_JARGON, BAD_PRICE, GOOD], "cuanto cuesta")
    assert result.waits == [RETRY_BACKOFF_SECONDS, RETRY_BACKOFF_SECONDS * 2]


def test_the_redraft_is_told_what_was_wrong() -> None:
    """A bare "try again" tends to return the same reply with the adjectives
    moved around, so the correction has to name the rule that was broken."""
    result = run_turn([BAD_PRICE, GOOD], "cuanto cuesta")
    second_prompt = result.model.calls[1]
    correction = [
        m for m in second_prompt if isinstance(m, HumanMessage) and "[correccion]" in m.content
    ]
    assert correction, "the redraft was not given a correction"
    assert "1800" in correction[0].content


def test_the_loop_stops_at_the_attempt_ceiling() -> None:
    """The ceiling is the point of the whole exercise. Without it a model stuck
    on the same mistake bills for calls until the recursion limit trips, and the
    customer waits through every one of them."""
    result = run_turn([AI_JARGON] * 10, "cuanto cuesta")
    assert result.state["attempts"] == MAX_GENERATION_ATTEMPTS
    assert len(result.model.calls) == MAX_GENERATION_ATTEMPTS


def test_an_exhausted_turn_goes_to_a_human_and_sends_nothing() -> None:
    """The draft it would otherwise send is the one that just failed. Sending a
    reply known to quote an invented price is worse than a pause."""
    result = run_turn([BAD_PRICE] * 10, "cuanto cuesta")
    assert result.interrupted is True
    assert result.state["outbound"] == []
    assert result.state["reply"] == ""
    assert result.state["escalation_reason"] == "validation_failed:invented_price"


def test_the_human_sees_why_the_turn_reached_them() -> None:
    payload = run_turn([AI_JARGON] * 10, "cuanto cuesta").interrupt_payload
    assert payload["reason"] == "validation_failed:ai_jargon"
    assert payload["message"] == "cuanto cuesta"
    assert payload["channel"] == "whatsapp"


# --------------------------------------------------------------------------
# Escalation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "reason"),
    [
        ("quiero hablar con una persona", "asked_for_human"),
        ("esto es un fraude, voy a poner una queja", "complaint"),
    ],
)
def test_the_model_is_never_called_when_the_turn_should_go_to_a_person(
    message: str, reason: str
) -> None:
    """Routed before ``generate``, not after. Answering a complaint with a sales
    pitch and *then* handing it over is worse than not answering."""
    result = run_turn([GOOD], message)
    assert result.interrupted is True
    assert result.state["escalation_reason"] == reason
    assert result.model.calls == []


def test_repeating_yourself_enough_times_reaches_a_person() -> None:
    history = [{"role": "user", "content": "no entiendo"} for _ in range(3)]
    result = run_turn([GOOD], "no entiendo", history=history)
    assert result.interrupted is True
    assert result.state["escalation_reason"] == "repeated_turns"


def test_the_human_reply_finishes_the_turn_and_lands_in_history() -> None:
    """Resuming has to leave the transcript looking like one conversation. A
    hand-over that drops the human's answer makes the next turn's prompt read as
    if the customer was ignored."""
    result = run_turn([GOOD], "quiero hablar con alguien")
    result.resume("Soy Ricardo, yo te ayudo.")
    assert result.state["needs_human"] is True
    assert result.state["reply"] == "Soy Ricardo, yo te ayudo."
    assert result.state["history"][-1] == {
        "role": "assistant",
        "content": "Soy Ricardo, yo te ayudo.",
    }


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------


def test_a_tool_call_runs_and_comes_back_for_a_second_draft() -> None:
    result = run_turn([_tool_call_draft(), AIMessage(content=GOOD)], "precio del bot")
    assert result.state["reply"] == GOOD
    tool_messages = [m for m in result.state["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_messages) == 1
    assert "2499" in tool_messages[0].content


def test_the_tool_result_is_in_front_of_the_model_on_the_next_draft() -> None:
    result = run_turn([_tool_call_draft(), AIMessage(content=GOOD)], "precio del bot")
    second_prompt = result.model.calls[1]
    assert any(isinstance(m, ToolMessage) for m in second_prompt)


def test_a_model_stuck_asking_for_tools_is_cut_off() -> None:
    """Same failure as the retry loop, different cycle: each round is a paid
    call and latency the customer sees."""
    result = run_turn([_tool_call_draft("bot-whatsapp") for _ in range(10)], "precio")
    tool_messages = [m for m in result.state["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_messages) == MAX_TOOL_ROUNDS
    # Cut off from its tools, the empty draft fails validation and the turn ends
    # up with a person -- it does not spin.
    assert result.interrupted is True


def test_an_unknown_plan_comes_back_as_an_answer_not_an_exception() -> None:
    """A tool that raises takes the graph down mid-conversation. One that
    explains itself gives the model something to recover from."""
    result = run_turn([_tool_call_draft("no-existe"), AIMessage(content=GOOD)], "precio")
    tool_messages = [m for m in result.state["messages"] if isinstance(m, ToolMessage)]
    assert "no existe" in tool_messages[0].content.lower()
    assert result.state["reply"] == GOOD


# --------------------------------------------------------------------------
# Memory
# --------------------------------------------------------------------------


def test_the_second_turn_can_see_the_first() -> None:
    conversation = Turn([GOOD, "Perfecto, te agendo el jueves."])
    conversation.send("cuanto cuesta")
    second = conversation.send("va, me interesa")

    prompt = conversation.model.calls[-1]
    assert any(isinstance(m, AIMessage) and m.content == GOOD for m in prompt)
    assert len(second.state["history"]) == 4


def test_the_scratchpad_does_not_leak_into_the_next_turn() -> None:
    """Tool calls and rejected drafts are per-turn. Left in the state they ride
    along in every later prompt, growing it without bound and re-showing the
    model text it was told to stop producing."""
    conversation = Turn([AI_JARGON, GOOD, "Listo."])
    conversation.send("cuanto cuesta")
    second = conversation.send("gracias")

    assert not any(AI_JARGON in str(m.content) for m in second.state["messages"])
    last_prompt = conversation.model.calls[-1]
    assert not any(AI_JARGON in str(m.content) for m in last_prompt)


def test_the_prompt_starts_with_the_system_message_for_the_current_directive() -> None:
    result = run_turn([GOOD], "quiero una pagina web")
    first_prompt = result.model.calls[0]
    assert isinstance(first_prompt[0], SystemMessage)
    assert "vista previa" in first_prompt[0].content


def test_the_focus_from_the_ad_survives_a_message_that_says_otherwise() -> None:
    """Hard evidence beats inference: the ad the lead clicked is known, the
    message is a guess. A thread that switches scripts mid-conversation reads
    as amnesia to the customer."""
    result = run_turn([GOOD], "quiero una pagina web", focus=LeadFocus.BOT)
    assert result.state["focus"] is LeadFocus.BOT
    assert "WhatsApp" in result.model.calls[0][0].content


# --------------------------------------------------------------------------
# Routers, called directly
# --------------------------------------------------------------------------


def test_route_after_classify_prefers_the_human() -> None:
    assert route_after_classify(ConversationState(escalation_reason="complaint")) == "escalate"
    assert route_after_classify(ConversationState(escalation_reason="")) == "generate"


def test_route_after_generate_ignores_a_draft_with_no_tool_calls() -> None:
    assert (
        route_after_generate(ConversationState(messages=[AIMessage(content="hola")])) == "validate"
    )


def test_route_after_generate_survives_an_empty_scratchpad() -> None:
    """Unreachable through the graph, since ``classify`` always seeds a message.
    Asserted anyway: an ``IndexError`` in a router takes the turn down, and this
    router is one refactor away from being called somewhere else."""
    assert route_after_generate(ConversationState()) == "validate"
    assert (
        route_after_generate(ConversationState(messages=[HumanMessage(content="x")])) == "validate"
    )


def test_route_after_validate_covers_its_three_outcomes() -> None:
    assert route_after_validate(ConversationState(validation_error="")) == "deliver"
    assert (
        route_after_validate(ConversationState(validation_error="ai_jargon", attempts=1))
        == "revise"
    )
    assert (
        route_after_validate(
            ConversationState(validation_error="ai_jargon", attempts=MAX_GENERATION_ATTEMPTS)
        )
        == "give_up"
    )


def test_the_stage_selects_the_closing_script() -> None:
    result = run_turn(
        [GOOD], "ya vi mi pagina", focus=LeadFocus.WEB, stage=SalesStage.PREVIEW_DELIVERED
    )
    assert "cierra" in result.model.calls[0][0].content


def test_a_full_state_on_a_later_turn_would_erase_the_history() -> None:
    """The reason ``turn_input`` exists, pinned so it cannot regress quietly.

    A graph input is merged field by field into the checkpointed state, so a
    fully-populated state sent into an existing thread overwrites ``history``
    with the empty list it was initialised with. The agent then greets a
    customer it has been talking to for ten minutes, with the transcript intact
    in the database one field away. Nothing raises; the conversation just
    restarts.
    """
    conversation = Turn([GOOD, "Segunda."])
    conversation.send("cuanto cuesta")

    clobbered = conversation.graph.invoke(
        new_state("va, me interesa", channel="whatsapp"), conversation.config
    )
    assert clobbered["history"] == [
        {"role": "user", "content": "va, me interesa"},
        {"role": "assistant", "content": "Segunda."},
    ]

    incremental = Turn([GOOD, "Segunda."], thread_id="incremental")
    incremental.send("cuanto cuesta")
    assert len(incremental.send("va, me interesa").state["history"]) == 4
