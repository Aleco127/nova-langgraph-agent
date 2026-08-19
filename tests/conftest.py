"""Shared machinery for the graph tests.

The helper below is the whole reason these tests are cheap: it runs a real
compiled graph, with the real nodes, the real routers and the real validator,
and replaces exactly two things -- the model and the clock. Nothing is mocked
out that could hide a wiring bug, and nothing that would make the suite slow or
paid is left in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage

from nova_agent.checkpointing import build_checkpointer
from nova_agent.graph import build_graph
from nova_agent.replay import ScriptedModel, scripted
from nova_agent.state import ConversationState, new_state, turn_input


@dataclass
class TurnResult:
    """What one invocation produced, plus what it did on the way."""

    state: ConversationState
    waits: list[float] = field(default_factory=list)
    model: ScriptedModel | None = None
    graph: Any = None
    config: dict[str, Any] = field(default_factory=dict)

    @property
    def interrupted(self) -> bool:
        """True when the turn stopped at the hand-over instead of replying."""
        return bool(self.state.get("__interrupt__"))

    @property
    def interrupt_payload(self) -> dict[str, Any]:
        """What the escalation node put in front of the human."""
        return dict(self.state["__interrupt__"][0].value)

    def resume(self, human_reply: str) -> TurnResult:
        """Answer as the human and let the same thread finish."""
        from langgraph.types import Command

        self.state = self.graph.invoke(Command(resume=human_reply), self.config)
        return self


class Turn:
    """A conversation you can drive one message at a time.

    Holds on to the graph and the thread id between calls, which is what makes
    the memory assertions possible: turn two has to reach the same checkpointer
    under the same ``thread_id`` or it proves nothing.
    """

    def __init__(
        self,
        replies: list[str] | list[AIMessage],
        *,
        thread_id: str = "test-thread",
        tools: list[Any] | None = None,
    ) -> None:
        self.waits: list[float] = []
        self.model = (
            ScriptedModel(responses=replies)
            if replies and isinstance(replies[0], AIMessage)
            else scripted(replies)  # type: ignore[arg-type]
        )
        self.graph = build_graph(
            self.model,
            tools=tools,
            checkpointer=build_checkpointer(),
            sleeper=self.waits.append,
        )
        self.config = {"configurable": {"thread_id": thread_id}}
        self.turns = 0

    def send(self, message: str, **state_overrides: Any) -> TurnResult:
        # First turn seeds the thread, later ones bring only what is new.
        # Sending a full state again would overwrite the checkpointed history
        # with the empty list ``new_state`` initialises it to.
        self.turns += 1
        state = (
            new_state(message, channel="whatsapp", conversation_id="conv-1")
            if self.turns == 1
            else turn_input(message)
        )
        state.update(state_overrides)  # type: ignore[typeddict-item]
        return TurnResult(
            state=self.graph.invoke(state, self.config),
            waits=self.waits,
            model=self.model,
            graph=self.graph,
            config=self.config,
        )


def run_turn(replies: list[str] | list[AIMessage], message: str, **overrides: Any) -> TurnResult:
    """One message through a fresh graph. The common case."""
    return Turn(replies).send(message, **overrides)
