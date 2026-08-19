"""Whether a draft reply is fit to send, and what to tell the model if not.

This is the module that gives the retry loop something to loop on. Both rules
below come from mistakes that cost real conversations, and both share a shape
worth noticing: the model produces fluent, plausible text that violates a
business constraint the prompt already stated. Restating the constraint louder
does not fix that. Checking the output does.

Every failure carries an ``instruction``: the redraft is told exactly what was
wrong, because a bare "try again" tends to produce the same reply with the
adjectives moved around.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from nova_agent.catalog import QUOTABLE_AMOUNTS


@dataclass(frozen=True)
class Verdict:
    """The outcome of checking one draft."""

    ok: bool
    reason: str = ""
    instruction: str = ""


# The sales rule is to talk about outcomes -- replies at 2am, booked
# appointments -- and never about the machinery. Leads who are told they are
# speaking to an AI start testing it instead of buying.
#
# The bare acronym is matched case-sensitively and with word boundaries on
# purpose: lowercased and unbounded it fires inside ordinary Spanish words like
# "familia" and "diario", and a validator with false positives sends the model
# into a retry loop it cannot escape.
_AI_ACRONYM_RE = re.compile(r"\bIA\b")
_AI_PHRASE_RE = re.compile(
    r"inteligencia\s{1,3}artificial"
    r"|modelo\s{1,3}de\s{1,3}lenguaje"
    r"|soy\s{1,3}un\s{1,3}(?:bot|robot|asistente\s{1,3}virtual)"
    r"|machine\s{1,3}learning",
    re.IGNORECASE,
)

# Amounts, in the three shapes replies actually use: "$2,499", "2499 pesos",
# "650 MXN". Quantifiers are bounded so the pattern stays linear on text a
# stranger controls -- a lesson this repository already paid for once.
#
# The grouped branch requires at least one separator. Written as "{0,3}" it
# matched "249" out of "$2499" and stopped there: the branch succeeded on the
# first three digits, and alternation does not keep looking for a longer match
# once one branch fits. A validator that reads $2,499 correctly and $2499 as
# $249 rejects the agent's own catalog prices.
_AMOUNT = r"\d{1,3}(?:[,.]\d{3}){1,3}|\d{1,7}"
_CURRENCY_RE = re.compile(
    rf"\$\s{{0,2}}({_AMOUNT})|({_AMOUNT})\s{{0,2}}(?:pesos|mxn)\b",
    re.IGNORECASE,
)


def mentions_ai(reply: str) -> bool:
    """True when the draft breaks the no-machinery rule."""
    if not reply:
        return False
    return bool(_AI_ACRONYM_RE.search(reply) or _AI_PHRASE_RE.search(reply))


def quoted_amounts(reply: str) -> list[int]:
    """Every currency figure the draft states, normalised to whole pesos."""
    if not reply:
        return []
    amounts: list[int] = []
    for with_symbol, with_word in _CURRENCY_RE.findall(reply):
        raw = with_symbol or with_word
        digits = raw.replace(",", "").replace(".", "")
        if digits:
            amounts.append(int(digits))
    return amounts


def invented_amounts(reply: str) -> list[int]:
    """Figures the draft quotes that are not in the catalog.

    A wrong price is the most expensive thing this agent can say: the customer
    holds the business to it, and finding out later costs either the margin or
    the sale.
    """
    return [amount for amount in quoted_amounts(reply) if amount not in QUOTABLE_AMOUNTS]


def validate_reply(reply: str) -> Verdict:
    """Check one draft. The first failure wins -- the redraft only needs one
    thing to fix at a time, and stacking corrections tends to produce a reply
    that satisfies the last one and forgets the first."""
    if not reply or not reply.strip():
        return Verdict(
            ok=False,
            reason="empty",
            instruction="La respuesta llego vacia. Escribe una respuesta breve y concreta.",
        )
    if mentions_ai(reply):
        return Verdict(
            ok=False,
            reason="ai_jargon",
            instruction=(
                "No menciones inteligencia artificial, bots ni modelos. "
                "Habla del resultado para el cliente: atencion a cualquier hora, "
                "citas agendadas, respuestas inmediatas."
            ),
        )
    invented = invented_amounts(reply)
    if invented:
        listed = ", ".join(str(amount) for amount in sorted(invented))
        return Verdict(
            ok=False,
            reason="invented_price",
            instruction=(
                f"Estas cifras no estan en el catalogo: {listed}. "
                "Usa unicamente los precios del catalogo o no des cifras."
            ),
        )
    return Verdict(ok=True)
