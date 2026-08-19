"""The rules that decide whether a draft reply is fit to send."""

from __future__ import annotations

import time

import pytest

from nova_agent.catalog import QUOTABLE_AMOUNTS
from nova_agent.validation import (
    invented_amounts,
    mentions_ai,
    quoted_amounts,
    validate_reply,
)


@pytest.mark.parametrize(
    "reply",
    [
        "Somos una IA de ultima generacion",
        "uso inteligencia artificial para responder",
        "Inteligencia   Artificial aplicada",
        "es un modelo de lenguaje entrenado",
        "soy un bot, pero te ayudo",
        "soy un asistente virtual",
        "hacemos machine learning",
    ],
)
def test_machinery_talk_is_rejected(reply: str) -> None:
    assert mentions_ai(reply) is True


@pytest.mark.parametrize(
    "reply",
    [
        "tengo familia en Guadalajara",
        "lo vemos a diario",
        "la garantia es amplia",
        "IAM no es lo mismo",
        "",
    ],
)
def test_ordinary_spanish_is_not_mistaken_for_the_acronym(reply: str) -> None:
    """The bare acronym has to be bounded and case-sensitive.

    Matched loosely it fires inside "familia" and "diario", and a validator with
    false positives puts the agent in a retry loop it cannot escape: every
    redraft in Spanish trips the same rule.
    """
    assert mentions_ai(reply) is False


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("son $2,499", [2499]),
        ("son $ 2499 en total", [2499]),
        ("cuesta 650 pesos al mes", [650]),
        ("son 6900 MXN", [6900]),
        ("$2,499 de setup y 650 pesos al mes", [2499, 650]),
        ("son $2.499 con punto", [2499]),
        ("sin cifras aqui", []),
        ("", []),
        ("te llamo el 15 y somos 40 personas", []),
    ],
)
def test_amounts_are_read_out_of_the_shapes_replies_actually_use(
    reply: str, expected: list[int]
) -> None:
    assert quoted_amounts(reply) == expected


def test_a_bare_number_without_a_currency_marker_is_not_a_price() -> None:
    """Otherwise every "responde en 30 segundos" becomes an invented price and
    the agent redrafts a reply that was correct."""
    assert invented_amounts("respondemos en 30 segundos, 24 horas al dia") == []


def test_catalog_prices_pass() -> None:
    for amount in QUOTABLE_AMOUNTS:
        assert invented_amounts(f"son ${amount}") == []


def test_a_price_that_is_not_in_the_catalog_is_flagged() -> None:
    assert invented_amounts("te lo dejo en $1,800") == [1800]


def test_the_first_failure_wins() -> None:
    """A draft that breaks two rules is corrected one at a time.

    Stacking corrections tends to produce a redraft that satisfies the last
    instruction and forgets the first.
    """
    verdict = validate_reply("Somos una IA y te lo dejo en $1,800")
    assert verdict.reason == "ai_jargon"


@pytest.mark.parametrize(("reply", "reason"), [("", "empty"), ("   \n ", "empty")])
def test_an_empty_draft_is_rejected(reply: str, reason: str) -> None:
    verdict = validate_reply(reply)
    assert verdict.ok is False
    assert verdict.reason == reason


def test_a_clean_reply_passes_with_no_instruction() -> None:
    verdict = validate_reply("El setup es de $2,499 y son 650 pesos al mes.")
    assert verdict.ok is True
    assert verdict.instruction == ""


def test_every_rejection_says_what_to_fix() -> None:
    """A bare "try again" produces the same reply with the adjectives moved."""
    for draft in ["", "somos una IA", "te lo dejo en $1,800"]:
        verdict = validate_reply(draft)
        assert verdict.instruction, f"no instruction for {draft!r}"


def test_the_invented_price_instruction_names_the_figures() -> None:
    verdict = validate_reply("son $1,800 o $3,300")
    assert "1800" in verdict.instruction
    assert "3300" in verdict.instruction


def test_amount_matching_stays_linear_on_a_long_run_of_digits() -> None:
    """The reply is model output, but the history it is drafted from is not.

    A pattern that backtracks super-linearly here is reachable from anything a
    customer can get echoed back, which is the same class of bug the contact
    patterns in this repository were already fixed for.
    """
    hostile = "$" + "1" * 4000 + "!"
    started = time.perf_counter()
    quoted_amounts(hostile)
    assert time.perf_counter() - started < 1.0
