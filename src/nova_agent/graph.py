"""The graph itself: which node runs next, and why.

The shape that matters is the cycle. ``generate -> validate -> revise ->
generate`` is not decoration; it is the reason this is a graph. A chain runs
each step once and hands you whatever came out the end, so enforcing "the reply
must not quote a price that is not in the catalog" leaves two options: check
after the fact and send it anyway, or wrap the chain in a Python loop and
reimplement, by hand, the state carrying and the step limit that the graph
already gives you.

There are three cycles here, each with its own ceiling:

* ``generate -> tools -> generate``, bounded by ``MAX_TOOL_ROUNDS``
* ``generate -> validate -> revise -> generate``, bounded by
  ``MAX_GENERATION_ATTEMPTS``
* neither, when the first draft passes -- the common case

Every ceiling has somewhere to go when it is reached, and none of them is
``END``. A turn that runs out of attempts goes to a human, because the draft it
would otherwise send is the one that just failed.
"""

from __future__ import annotations

import time
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from nova_agent import nodes
from nova_agent.state import MAX_GENERATION_ATTEMPTS, ConversationState
from nova_agent.tools import AGENT_TOOLS

# A model that keeps asking for the same lookup is not going to answer on the
# next round either, and each round is a paid call plus latency the customer
# sees. Two is enough for the real case -- look up a plan, look up the one the
# customer compared it to.
MAX_TOOL_ROUNDS = 2


def route_after_classify(state: ConversationState) -> str:
    """Straight to a human, or on to the model."""
    return "escalate" if state.get("escalation_reason") else "generate"


def route_after_generate(state: ConversationState) -> str:
    """Run the tools the draft asked for, unless it has asked too often.

    Reads a count that ``generate`` recorded rather than inspecting the last
    element of ``messages``. The list is maintained by ``add_messages``, which
    merges by message id instead of appending blindly -- so a redraft can land
    back in the position the first draft occupied and leave a tool result at the
    end. Routing off the tail then sends a turn that did ask for tools straight
    to validation, and the tool ceiling silently becomes one.
    """
    if not state.get("pending_tool_calls"):
        return "validate"
    messages = state.get("messages") or []
    rounds = sum(1 for message in messages if isinstance(message, ToolMessage))
    if rounds >= MAX_TOOL_ROUNDS:
        # Validation still runs. The draft is judged on what it says, and a
        # model cut off from its tools usually says something checkable.
        return "validate"
    return "tools"


def route_after_validate(state: ConversationState) -> str:
    """Send it, redraft it, or stop trying."""
    if not state.get("validation_error"):
        return "deliver"
    if state.get("attempts", 0) >= MAX_GENERATION_ATTEMPTS:
        return "give_up"
    return "revise"


def build_graph(
    model: BaseChatModel,
    *,
    tools: list[Any] | None = None,
    checkpointer: Any | None = None,
    sleeper: nodes.Sleeper = time.sleep,
) -> Any:
    """Compile the agent.

    ``model`` is bound to the tools here rather than by the caller so the graph
    and the tool node can never disagree about what is callable -- a mismatch
    that shows up as a tool call the tool node has no handler for, halfway
    through a conversation.
    """
    agent_tools = AGENT_TOOLS if tools is None else tools

    graph = StateGraph(ConversationState)
    graph.add_node("classify", nodes.classify)
    graph.add_node("generate", nodes.make_generate(model.bind_tools(agent_tools)))
    graph.add_node("tools", ToolNode(agent_tools))
    graph.add_node("validate", nodes.validate)
    graph.add_node("revise", nodes.make_revise(sleeper))
    graph.add_node("give_up", nodes.give_up)
    graph.add_node("deliver", nodes.deliver)
    graph.add_node("escalate", nodes.escalate)

    graph.add_edge(START, "classify")
    graph.add_conditional_edges(
        "classify",
        route_after_classify,
        {"escalate": "escalate", "generate": "generate"},
    )
    graph.add_conditional_edges(
        "generate",
        route_after_generate,
        {"tools": "tools", "validate": "validate"},
    )
    graph.add_edge("tools", "generate")
    graph.add_conditional_edges(
        "validate",
        route_after_validate,
        {"deliver": "deliver", "revise": "revise", "give_up": "give_up"},
    )
    graph.add_edge("revise", "generate")
    # Not straight to END: running out of attempts is an escalation like any
    # other, and it reaches the same person through the same interrupt.
    graph.add_edge("give_up", "escalate")
    graph.add_edge("deliver", END)
    graph.add_edge("escalate", END)

    return graph.compile(checkpointer=checkpointer)
