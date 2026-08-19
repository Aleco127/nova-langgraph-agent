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
