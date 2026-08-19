"""Run one turn's worth of deterministic work and print the resulting state.

This is every step of a turn that happens *before* the model is called:
normalise the contact details, decide which sales script applies, assemble the
state. Keeping it runnable on its own is what lets the container be smoke-tested
in CI without an API key, and it is the same state object the graph nodes will
receive once the model is wired in.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections.abc import Sequence

from nova_agent.contacts import extract_contact
from nova_agent.intent import LeadFocus, SalesStage, classify_focus, select_directive
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


def _as_json(state: ConversationState) -> str:
    payload = {
        "channel": state["channel"],
        "message": state["message"],
        "contact": dataclasses.asdict(state["contact"]),
        "focus": state["focus"].value,
        "stage": state["stage"].value,
        "directive": state["directive"].value,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nova-agent", description=__doc__)
    parser.add_argument("message", help="the customer's message")
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
    args = parser.parse_args(argv)

    state = build_state(args.message, args.channel, args.focus, args.stage)
    print(_as_json(state))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through the container
    sys.exit(main())
