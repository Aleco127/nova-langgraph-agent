"""The graph's nodes.

Every node here is a wrapper. The classification rules, the escalation
thresholds, the phone normalisation and the message splitting all live in the
modules that were written and tested before the graph existed, and they stay
there: a node's job is to read the state, call one of those functions, and
return what changed. That division is what lets the interesting logic be tested
with plain function calls, and leaves the graph tests free to check the thing
only a graph can get wrong -- which edge was taken.

The two nodes that need something from outside (a model, a clock) are built by
factories that take it as an argument. Nothing in this module reaches for a
global.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
)
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.types import interrupt

from nova_agent.contacts import Contact, extract_contact, merge_contacts
from nova_agent.escalation import (
    MAX_REPEATED_TURNS,
    count_repeats,
    is_complaint,
    wants_human,
)
from nova_agent.intent import LeadFocus, SalesStage, classify_focus, select_directive
from nova_agent.outbound import split_outbound
from nova_agent.prompts import system_prompt
from nova_agent.state import ConversationState, trim_history
from nova_agent.validation import validate_reply

Sleeper = Callable[[float], None]
Node = Callable[[ConversationState], ConversationState]

# First retry waits this long and each one after doubles it. The numbers are
# small because the customer is watching a chat window, not a job queue: the
# point of waiting at all is to let a rate limit or a blip clear, and past a
# couple of seconds a silent agent costs more than a retried one saves.
RETRY_BACKOFF_SECONDS = 0.5


def classify(state: ConversationState) -> ConversationState:
    """Everything decidable about this turn before the model is involved.

    Also resets the per-turn scratchpad. Without the explicit clear the
    checkpointer hands the next turn every tool call and rejected draft from the
    previous one, and the prompt grows without bound across a conversation.
    """
    message = state.get("message") or ""
    focus = classify_focus(message, known=state.get("focus") or LeadFocus.UNKNOWN)
    stage = state.get("stage") or SalesStage.NEW
    known = state.get("contact") or Contact()
    return ConversationState(
        contact=merge_contacts(known, extract_contact(message)),
        focus=focus,
        stage=stage,
        directive=select_directive(focus, stage),
        messages=[RemoveMessage(id=REMOVE_ALL_MESSAGES), HumanMessage(content=message)],
        attempts=0,
        validation_error="",
        revision_instruction="",
        pending_tool_calls=0,
        reply="",
        outbound=[],
        needs_human=False,
        escalation_reason=escalation_reason(state),
    )


def escalation_reason(state: ConversationState) -> str:
    """Why this turn should go to a person, or an empty string if it should not.

    Returning the reason rather than a boolean is what lets the router and the
    escalation node agree without evaluating the rules twice, and what puts
    something useful in front of whoever picks the conversation up.
    """
    message = state.get("message")
    if wants_human(message):
        return "asked_for_human"
    if is_complaint(message):
        return "complaint"
    if count_repeats(state.get("history") or []) >= MAX_REPEATED_TURNS:
        return "repeated_turns"
    return ""


def _text_of(message: BaseMessage) -> str:
    """The plain text of a reply.

    Content arrives as a string from most providers and as a list of blocks from
    the ones that support mixed content. A draft that came back as blocks would
    otherwise reach the validator as ``"[{'type': 'text', ...}]"`` and be
    rejected for the wrong reason.
    """
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(block.get("text", "") for block in content if isinstance(block, dict))


def _prompt_messages(state: ConversationState) -> list[BaseMessage]:
    """System prompt, then the conversation so far, then this turn's scratchpad."""
    messages: list[BaseMessage] = [SystemMessage(content=system_prompt(state["directive"]))]
    for turn in trim_history(state.get("history") or []):
        content = turn.get("content", "")
        if turn.get("role") == "assistant":
            messages.append(AIMessage(content=content))
        else:
            messages.append(HumanMessage(content=content))
    messages.extend(state.get("messages") or [])
    return messages


def make_generate(model: BaseChatModel) -> Node:
    """Build the node that asks the model for a draft.

    The model arrives as an argument instead of being constructed here, which is
    what makes the whole graph runnable in CI with no API key and no network.
    """

    def generate(state: ConversationState) -> ConversationState:
        answer = model.invoke(_prompt_messages(state))
        tool_calls = getattr(answer, "tool_calls", None) or []
        return ConversationState(
            messages=[answer],
            reply=_text_of(answer),
            attempts=state.get("attempts", 0) + 1,
            # Recorded here rather than rediscovered by the router, which would
            # have to guess which element of ``messages`` this draft became.
            pending_tool_calls=len(tool_calls),
        )

    return generate


def validate(state: ConversationState) -> ConversationState:
    """Check the draft against the rules a prompt cannot enforce on its own."""
    verdict = validate_reply(state.get("reply") or "")
    if verdict.ok:
        return ConversationState(validation_error="", revision_instruction="")
    return ConversationState(
        validation_error=verdict.reason,
        revision_instruction=verdict.instruction,
    )


def make_revise(sleeper: Sleeper = time.sleep) -> Node:
    """Build the node that sends a rejected draft back with a correction.

    ``sleeper`` is injected so a test can assert that a backoff happened, and
    how long it would have been, without spending that time. A test that really
    slept would be measuring ``time.sleep``.
    """

    def revise(state: ConversationState) -> ConversationState:
        attempts = state.get("attempts", 1)
        sleeper(RETRY_BACKOFF_SECONDS * (2 ** (attempts - 1)))
        instruction = state.get("revision_instruction") or "Corrige la respuesta anterior."
        return ConversationState(
            messages=[HumanMessage(content=f"[correccion] {instruction}")],
            reply="",
        )

    return revise


def deliver(state: ConversationState) -> ConversationState:
    """Commit an approved reply: split it for the channel and record the turn."""
    reply = state.get("reply") or ""
    return ConversationState(
        outbound=split_outbound(reply),
        history=_record(state, reply),
        needs_human=False,
    )


def escalate(state: ConversationState) -> ConversationState:
    """Hand the thread to a person and stop.

    ``interrupt`` suspends the graph rather than returning a value, so the turn
    ends here with the state durable in the checkpointer. A human answers, the
    same thread resumes with ``Command(resume=...)``, and what they wrote is
    recorded as the reply -- so the next turn's history reads as one
    conversation rather than two.
    """
    human_reply = str(
        interrupt(
            {
                "reason": state.get("escalation_reason") or "unknown",
                "conversation_id": state.get("conversation_id", ""),
                "channel": state.get("channel", ""),
                "message": state.get("message", ""),
            }
        )
    )
    return ConversationState(
        needs_human=True,
        reply=human_reply,
        outbound=split_outbound(human_reply),
        history=_record(state, human_reply),
    )


def give_up(state: ConversationState) -> ConversationState:
    """Mark a turn the model could not get right within its attempts.

    Reached only from the retry loop's exhaustion edge, and it deliberately does
    not send the last draft: that draft is the one that just failed validation,
    and sending a reply known to quote an invented price is worse than sending
    nothing while a human is fetched.
    """
    return ConversationState(
        escalation_reason=f"validation_failed:{state.get('validation_error') or 'unknown'}",
        reply="",
    )


def _record(state: ConversationState, reply: str) -> list[dict[str, str]]:
    """The history with this turn appended, trimmed to the window."""
    history = list(state.get("history") or [])
    history.append({"role": "user", "content": state.get("message") or ""})
    history.append({"role": "assistant", "content": reply})
    return trim_history(history)
