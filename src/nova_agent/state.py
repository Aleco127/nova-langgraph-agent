"""The conversation state the agent carries between turns.

Modelled as a TypedDict rather than free-floating arguments because the next
milestone turns these functions into graph nodes, and a graph needs one explicit
state object that every node reads and writes. Keeping the shape here now means
the nodes arrive as thin wrappers instead of a rewrite.
"""

from __future__ import annotations

from typing import TypedDict

from nova_agent.contacts import Contact
from nova_agent.intent import Directive, LeadFocus, SalesStage

# How much history goes into the prompt. Ten was the original figure and it was
# too short: the model lost the thread and re-opened the qualifying questions it
# had already asked, which customers read as being handed to a new agent.
MAX_HISTORY_MESSAGES = 40


class ConversationState(TypedDict, total=False):
    """Everything a turn needs. ``total=False`` because a brand-new thread has
    almost none of it yet."""

    conversation_id: str
    channel: str
    message: str
    history: list[dict[str, str]]
    contact: Contact
    focus: LeadFocus
    stage: SalesStage
    directive: Directive
    reply: str
    needs_human: bool


def new_state(message: str, channel: str, conversation_id: str = "") -> ConversationState:
    """A state for a thread nothing is known about yet."""
    return ConversationState(
        conversation_id=conversation_id,
        channel=channel,
        message=message,
        history=[],
        contact=Contact(),
        focus=LeadFocus.UNKNOWN,
        stage=SalesStage.NEW,
        directive=Directive.NONE,
        reply="",
        needs_human=False,
    )


def trim_history(history: list[dict[str, str]]) -> list[dict[str, str]]:
    """Keep the most recent turns, oldest dropped first."""
    if len(history) <= MAX_HISTORY_MESSAGES:
        return list(history)
    return list(history[-MAX_HISTORY_MESSAGES:])
