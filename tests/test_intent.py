"""Which script the agent runs, and the rule that keeps it from switching."""

from __future__ import annotations

import pytest

from nova_agent.intent import Directive, LeadFocus, SalesStage, classify_focus, select_directive


@pytest.mark.parametrize(
    "message",
    [
        "quiero una pagina web",
        "quiero una página web",  # accented, same intent
        "me interesan los sitios web que hacen",
        "puedo actualizar mi sitio?",
        "ando viendo una web para mi negocio",
        "QUIERO UNA PAGINA WEB",  # shouted, still a web lead
    ],
)
def test_web_intent_is_recognised_however_it_is_typed(message: str) -> None:
    assert classify_focus(message) is LeadFocus.WEB


@pytest.mark.parametrize(
    "message",
    [
        "hola",
        "cuanto cuestan?",
        "quiero un bot",
        "",
        None,
    ],
)
def test_ambiguous_openers_stay_unknown_rather_than_guessing(message: str | None) -> None:
    assert classify_focus(message) is LeadFocus.UNKNOWN


def test_known_focus_survives_a_message_that_says_otherwise() -> None:
    # The ad the customer clicked is evidence; the sentence they typed is an
    # inference. Re-classifying here is what makes the agent change scripts
    # halfway through a conversation.
    assert classify_focus("quiero una pagina web", known=LeadFocus.BOT) is LeadFocus.BOT


def test_known_web_focus_is_kept_for_an_off_topic_message() -> None:
    assert classify_focus("y cuanto tardan?", known=LeadFocus.WEB) is LeadFocus.WEB


def test_unknown_known_focus_falls_through_to_the_message() -> None:
    assert classify_focus("quiero una pagina web", known=LeadFocus.UNKNOWN) is LeadFocus.WEB


@pytest.mark.parametrize(
    ("focus", "stage", "expected"),
    [
        (LeadFocus.WEB, SalesStage.NEW, Directive.WEB_SALES),
        (LeadFocus.WEB, SalesStage.PREVIEW_REQUESTED, Directive.WEB_SALES_AWAITING_PREVIEW),
        (LeadFocus.WEB, SalesStage.PREVIEW_DELIVERED, Directive.POST_PREVIEW_CLOSE),
        (LeadFocus.WEB, SalesStage.NEGOTIATION, Directive.POST_PREVIEW_CLOSE),
        (LeadFocus.WEB, SalesStage.CLOSED, Directive.POST_PREVIEW_CLOSE),
        (LeadFocus.UNKNOWN, SalesStage.NEW, Directive.NONE),
        (LeadFocus.UNKNOWN, SalesStage.NEGOTIATION, Directive.NONE),
    ],
)
def test_directive_matrix(focus: LeadFocus, stage: SalesStage, expected: Directive) -> None:
    assert select_directive(focus, stage) is expected


@pytest.mark.parametrize("stage", list(SalesStage))
def test_bot_leads_get_one_script_at_every_stage(stage: SalesStage) -> None:
    # That funnel has no preview step, so it has no stage-dependent branch.
    assert select_directive(LeadFocus.BOT, stage) is Directive.BOT_SALES


def test_stage_defaults_to_new() -> None:
    assert select_directive(LeadFocus.WEB) is Directive.WEB_SALES
