"""The entry point the container runs."""

from __future__ import annotations

import json

import pytest

from nova_agent.__main__ import build_state, main
from nova_agent.intent import Directive, LeadFocus, SalesStage


def test_a_web_lead_is_assembled_end_to_end() -> None:
    state = build_state("quiero una pagina web, mi cel 33 1234 5678", channel="whatsapp")
    assert state["focus"] is LeadFocus.WEB
    assert state["directive"] is Directive.WEB_SALES
    assert state["contact"].phone == "+5213312345678"
    assert state["channel"] == "whatsapp"


def test_the_ad_focus_overrides_what_the_message_looks_like() -> None:
    state = build_state("quiero una pagina web", known_focus=LeadFocus.BOT)
    assert state["directive"] is Directive.BOT_SALES


def test_a_later_stage_switches_the_script() -> None:
    state = build_state("ya lo vi, cuanto seria?", stage=SalesStage.PREVIEW_DELIVERED)
    assert state["stage"] is SalesStage.PREVIEW_DELIVERED


def test_main_prints_one_json_object(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["quiero una pagina web", "--channel", "web"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["focus"] == "paginas-web"
    assert payload["directive"] == "web_sales"
    assert payload["contact"] == {"phone": None, "email": None}


def test_main_accepts_focus_and_stage_flags(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(
        ["hola", "--focus", "bot-whatsapp", "--stage", "negociacion", "--channel", "whatsapp"]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["directive"] == "bot_sales"
    assert payload["stage"] == "negociacion"


def test_output_keeps_accents_readable_rather_than_escaping_them(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # ensure_ascii=False, so a human reading CI logs sees the message they sent.
    main(["quiero una página web"])
    assert "página" in capsys.readouterr().out


def test_an_unknown_focus_selects_no_directive(capsys: pytest.CaptureFixture[str]) -> None:
    main(["hola, cuanto cuesta?"])
    assert json.loads(capsys.readouterr().out)["directive"] == "none"


# --------------------------------------------------------------------------
# Replay and diagram, the two modes that build the graph
# --------------------------------------------------------------------------


def test_replay_runs_the_whole_graph_and_reports_the_reply(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["cuanto cuesta", "--replay", "El setup es de $2,499."]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["reply"] == "El setup es de $2,499."
    assert payload["outbound"] == ["El setup es de $2,499."]
    assert payload["attempts"] == 1
    assert payload["awaiting_human"] is False


def test_replay_reports_a_turn_that_stopped_for_a_human(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``needs_human`` comes from the node that is still waiting, so on a paused
    turn the state says False. The pause itself is the answer, and the output
    has to say so or an operator reads "handled"."""
    main(["quiero hablar con una persona", "--replay", "x"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["awaiting_human"] is True
    assert payload["needs_human"] is True
    assert payload["escalation_reason"] == "asked_for_human"
    assert payload["outbound"] == []


def test_replay_drives_the_retry_loop(capsys: pytest.CaptureFixture[str]) -> None:
    """Reproducing a reported conversation is the point of the mode: same graph,
    same validator, same loop, with the one non-deterministic part pinned."""
    main(["cuanto cuesta", "--replay", "Somos una IA.", "--replay", "Son $2,499."])
    payload = json.loads(capsys.readouterr().out)
    assert payload["attempts"] == 2
    assert payload["reply"] == "Son $2,499."


def test_the_diagram_is_generated_from_the_compiled_graph(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--diagram"]) == 0
    mermaid = capsys.readouterr().out
    for node in ["classify", "generate", "tools", "validate", "revise", "give_up", "escalate"]:
        assert node in mermaid
    # The cycle, which is the whole reason this is a graph.
    assert "revise --> generate" in mermaid


def test_a_message_is_required_unless_the_diagram_was_asked_for() -> None:
    with pytest.raises(SystemExit) as exit_info:
        main([])
    assert exit_info.value.code == 2


def test_the_deterministic_mode_reports_no_graph_fields(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Without --replay nothing has been generated, and reporting an empty reply
    would read as an agent that answered with silence."""
    main(["quiero una pagina web"])
    payload = json.loads(capsys.readouterr().out)
    assert "reply" not in payload
    assert "awaiting_human" not in payload
