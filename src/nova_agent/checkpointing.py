"""Where a conversation's state lives between turns, and what it is allowed to
rebuild when it comes back.

The memory itself is the easy half: a checkpointer keyed by ``thread_id`` is
what lets turn four know what was agreed in turn one without the caller
resending the transcript.

The second half is why this module exists instead of a one-line
``InMemorySaver()`` at the call site. A checkpoint is serialised Python objects,
and LangGraph's deserialiser defaults to permissive: it will rebuild whatever
type the stored record names. Its own docstring is blunt about the consequence
-- an attacker who can write to the checkpoint store may be able to trigger code
execution when it is read back. For this agent that store is a database holding
customer conversations, which is not a component anyone should assume stays
trusted.

So the allowlist below is explicit. These four types are the only project types
that ever enter a checkpoint, and anything else arrives as plain data instead of
being instantiated. The cost is one line per new type in the state; the failure
mode without it is remote code execution reached through a database write.

Running this without the allowlist is not silently insecure, to be fair --
LangGraph warns on every unregistered type, and those warnings were what
surfaced this in the first place.
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from nova_agent.contacts import Contact
from nova_agent.intent import Directive, LeadFocus, SalesStage

# Every non-builtin type this project puts in the state. LangGraph's own safe
# list already covers str, datetime, Decimal and friends.
CHECKPOINT_TYPES: tuple[type, ...] = (Contact, LeadFocus, SalesStage, Directive)


def build_serializer() -> JsonPlusSerializer:
    """A serialiser that rebuilds this project's types and nothing else."""
    return JsonPlusSerializer(allowed_msgpack_modules=list(CHECKPOINT_TYPES))


def build_checkpointer() -> Any:
    """In-process memory for a conversation.

    In memory on purpose. A Postgres checkpointer is a two-line swap
    (``langgraph-checkpoint-postgres``) and the right answer in production, but
    it would put a database container between the test suite and every graph
    assertion -- which is how a fast suite becomes one nobody runs before
    pushing.
    """
    return InMemorySaver(serde=build_serializer())
