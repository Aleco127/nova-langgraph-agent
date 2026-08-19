"""When to stop answering and hand the conversation to a person.

Escalation is cheap and de-escalation is not: a lead handed to a human early
costs a few minutes of someone's time, while a lead the bot argued with for
four turns is usually gone. The thresholds here lean toward handing over.
"""

from __future__ import annotations

import re

from nova_agent.state import ConversationState

# Asking for a human, in the ways people actually ask.
_HUMAN_REQUEST_RE = re.compile(
    r"hablar\s+con\s+(?:una\s+)?(?:persona|humano|alguien|asesor)"
    r"|me\s+pasas?\s+con\s+|quiero\s+un\s+(?:asesor|ejecutivo|gerente)"
    r"|eres\s+un\s+bot",
    re.IGNORECASE,
)

# Words that mean the conversation has stopped being a sale.
_COMPLAINT_RE = re.compile(
    r"\b(?:queja|reclamo|demanda|abogado|estafa|fraude|reembolso)\b",
    re.IGNORECASE,
)

# Repeating yourself twice is a bad turn; three times is the bot failing to
# understand, and a fourth attempt will not fix it.
MAX_REPEATED_TURNS = 3


def wants_human(message: str | None) -> bool:
    """True when the customer has asked for a person, however they phrased it."""
    if not message:
        return False
    return _HUMAN_REQUEST_RE.search(message) is not None


def is_complaint(message: str | None) -> bool:
    """True when the message is a complaint rather than a sales conversation."""
    if not message:
        return False
    return _COMPLAINT_RE.search(message) is not None


def count_repeats(history: list[dict[str, str]]) -> int:
    """How many times in a row the customer has sent essentially the same thing.

    Compared on a normalised form, because someone who repeats themselves
    rarely types it identically the second time.
    """
    customer_turns = [t["content"] for t in history if t.get("role") == "user"]
    if not customer_turns:
        return 0
    normalised = [re.sub(r"\W+", " ", t).strip().lower() for t in customer_turns]
    latest = normalised[-1]
    repeats = 0
    for turn in reversed(normalised):
        if turn != latest:
            break
        repeats += 1
    return repeats


def should_escalate(state: ConversationState) -> bool:
    """The single call a graph node makes to decide whether to hand over."""
    message = state.get("message")
    if wants_human(message) or is_complaint(message):
        return True
    return count_repeats(state.get("history") or []) >= MAX_REPEATED_TURNS
