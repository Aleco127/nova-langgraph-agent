"""Run a turn and print what came out, in one of three modes.

Default is the deterministic half of a turn -- normalise the contact details,
pick the sales script, assemble the state -- with no model involved at all.
``--replay`` runs the whole graph against scripted model output, which is how a
reported conversation gets reproduced without paying for it. ``--diagram``
prints the compiled graph.

All three run with no API key, which is what lets the container be smoke-tested
in CI. The two that build the graph are the ones that would catch it failing to
assemble.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections.abc import Sequence

from nova_agent.checkpointing import build_checkpointer
from nova_agent.contacts import extract_contact
from nova_agent.graph import build_graph
from nova_agent.intent import LeadFocus, SalesStage, classify_focus, select_directive
from nova_agent.replay import scripted
from nova_agent.state import ConversationState, new_state


def build_state(
    message: str,
    channel: str = "web",
    known_focus: LeadFocus = LeadFocus.UNKNOWN,
    stage: SalesStage = SalesStage.NEW,
) -> ConversationState:
    """Everything that can be decided about a turn without asking the model."""
    state = new_state(message, channel=channel)
    state["contact"] = extract_contact(message)
    state["focus"] = classify_focus(message, known=known_focus)
    state["stage"] = stage
    state["directive"] = select_directive(state["focus"], stage)
    return state


def run_replay(state: ConversationState, responses: Sequence[str]) -> ConversationState:
    """Drive the full graph with scripted model output."""
    graph = build_graph(scripted(responses), checkpointer=build_checkpointer())
    config = {"configurable": {"thread_id": state.get("conversation_id") or "replay"}}
    return graph.invoke(state, config)


def diagram() -> str:
    """The compiled graph as Mermaid.

    Generated from the graph rather than maintained by hand, so a diagram that
    disagrees with the code is not a state this repository can reach.
    """
    return build_graph(scripted(["placeholder"])).get_graph().draw_mermaid()


def _as_json(state: ConversationState) -> str:
    payload: dict[str, object] = {
        "channel": state["channel"],
        "message": state["message"],
        "contact": dataclasses.asdict(state["contact"]),
        "focus": state["focus"].value,
        "stage": state["stage"].value,
        "directive": state["directive"].value,
    }
    interrupts = state.get("__interrupt__")
    if state.get("outbound") or interrupts:
        payload["reply"] = state.get("reply", "")
        payload["outbound"] = state.get("outbound", [])
        payload["attempts"] = state.get("attempts", 0)
        payload["escalation_reason"] = state.get("escalation_reason", "")
        # A turn that stopped at the interrupt has not been answered yet, and
        # reporting needs_human from the state would say False -- the node that
        # sets it is the one still waiting. The pause itself is the answer.
        payload["awaiting_human"] = bool(interrupts)
        payload["needs_human"] = bool(interrupts) or state.get("needs_human", False)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nova-agent", description=__doc__)
    parser.add_argument("message", nargs="?", default="", help="the customer's message")
    parser.add_argument("--channel", default="web", help="where it arrived from")
    parser.add_argument(
        "--focus",
        type=LeadFocus,
        choices=list(LeadFocus),
        default=LeadFocus.UNKNOWN,
        help="focus already established by the ad the lead clicked",
    )
    parser.add_argument(
        "--stage",
        type=SalesStage,
        choices=list(SalesStage),
        default=SalesStage.NEW,
        help="how far along the conversation is",
    )
    parser.add_argument(
        "--replay",
        action="append",
        metavar="REPLY",
        help="scripted model reply; repeat for each draft the run should produce",
    )
    parser.add_argument(
        "--diagram",
        action="store_true",
        help="print the compiled graph as Mermaid and exit",
    )
    return parser


# A turn that stopped for a person did not fail -- the graph did exactly what it
# was built to do -- but it did not answer the customer either, and a script
# replaying conversations in bulk needs to tell those two apart without parsing
# the JSON. 3 rather than 1, which reads as a crash, or 2, which argparse owns.
EXIT_AWAITING_HUMAN = 3


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)

    if args.diagram:
        print(diagram())
        return 0

    if not args.message:
        parser.error("a message is required unless --diagram is given")

    state = build_state(args.message, args.channel, args.focus, args.stage)
    if args.replay:
        state = run_replay(state, args.replay)
    print(_as_json(state))
    return EXIT_AWAITING_HUMAN if state.get("__interrupt__") else 0


if __name__ == "__main__":  # pragma: no cover - exercised through the container
    sys.exit(main())
