"""The conversation state the agent carries between turns.

Modelled as a TypedDict rather than free-floating arguments because the graph
needs one explicit state object that every node reads and writes.

Two collections live here and they are not the same thing. ``history`` is the
business record of the conversation: what the customer said and what was sent
back, trimmed to a bounded window, and the only part worth persisting between
turns. ``messages`` is the current turn's scratchpad -- it holds tool calls,
tool results and rejected drafts, none of which belong in a transcript anyone
reads. Collapsing them into one list is the shortcut that makes a retry loop
leak its failed attempts into the next turn's prompt.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from nova_agent.contacts import Contact
from nova_agent.intent import Directive, LeadFocus, SalesStage

# How much history goes into the prompt. Ten was the original figure and it was
# too short: the model lost the thread and re-opened the qualifying questions it
# had already asked, which customers read as being handed to a new agent.
MAX_HISTORY_MESSAGES = 40

# How many times the agent may redraft a reply that failed validation before it
# gives up. Three is not a rounding of "a few": the first retry fixes a slip,
# the second fixes a slip the first introduced, and a model that has missed the
# same instruction three times in a row is not going to get it on the fourth.
MAX_GENERATION_ATTEMPTS = 3


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

    # The only field with a reducer. ToolNode appends its results rather than
    # returning the whole list, so this one has to accumulate; everything else
    # is replaced wholesale by the node that owns it, which is what keeps
    # ``history`` bounded by ``trim_history`` instead of growing forever.
    messages: Annotated[list[AnyMessage], add_messages]

    # Retry bookkeeping. ``attempts`` counts drafts produced, not retries taken,
    # so a reply that passes on the first try still leaves it at 1.
    attempts: int
    validation_error: str

    # How many tools the latest draft asked for. Recorded by the node that
    # produced the draft, because the router cannot reliably find that draft
    # again once ``add_messages`` has merged it into the list.
    pending_tool_calls: int

    # What the redraft is told to fix. Carried in the state rather than
    # regenerated from ``validation_error`` so the wording stays with the rule
    # that produced it, in the module that owns the rule.
    revision_instruction: str

    # Set when the graph hands over. Carrying the reason means the human picking
    # the thread up knows why it reached them without rereading the transcript.
    escalation_reason: str

    # The reply as the channel will actually receive it: one entry per message.
    outbound: list[str]


def turn_input(message: str, channel: str = "", conversation_id: str = "") -> ConversationState:
    """The input for a turn on a thread that already exists.

    Only the fields this turn actually brings. That restraint is the whole
    point: a graph input is merged into the checkpointed state field by field,
    so passing a fully-populated state to turn two overwrites turn one's history
    with the empty list it was initialised with. The agent then answers as if it
    had never spoken to the customer -- with the transcript sitting in the
    database, intact, one field away.

    Use :func:`new_state` for the first turn, or when there is no checkpointer.
    """
    state = ConversationState(message=message)
    if channel:
        state["channel"] = channel
    if conversation_id:
        state["conversation_id"] = conversation_id
    return state


def new_state(message: str, channel: str, conversation_id: str = "") -> ConversationState:
    """A state for a thread nothing is known about yet.

    Every field is populated, which makes this the wrong thing to send into a
    thread that already has state -- see :func:`turn_input`.
    """
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
        messages=[],
        attempts=0,
        pending_tool_calls=0,
        validation_error="",
        revision_instruction="",
        escalation_reason="",
        outbound=[],
    )


def trim_history(history: list[dict[str, str]]) -> list[dict[str, str]]:
    """Keep the most recent turns, oldest dropped first."""
    if len(history) <= MAX_HISTORY_MESSAGES:
        return list(history)
    return list(history[-MAX_HISTORY_MESSAGES:])
