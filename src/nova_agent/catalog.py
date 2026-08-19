"""The prices the agent is allowed to say out loud.

This exists as data rather than as a paragraph in the system prompt because a
prompt is a suggestion and a lookup table is not. Everything the validator
checks a draft reply against comes from here, so adding a plan is one edit and
the gate that stops the agent inventing a number keeps working unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    """One sellable thing, at the prices actually quoted for it."""

    slug: str
    name: str
    setup_mxn: int
    monthly_mxn: int
    notes: str = ""


CATALOG: tuple[Plan, ...] = (
    Plan(
        slug="bot-whatsapp",
        name="Bot de WhatsApp",
        setup_mxn=2499,
        monthly_mxn=650,
        notes="Canal adicional: 299 al mes cada uno.",
    ),
    Plan(
        slug="paginas-web",
        name="Pagina web",
        setup_mxn=6900,
        monthly_mxn=390,
        notes="Mensualidad cubre hospedaje y mantenimiento.",
    ),
)

# Every figure a reply may legitimately contain. Built once from the catalog so
# it cannot drift away from it: a price that exists in one and not the other is
# the exact bug this module is here to prevent.
QUOTABLE_AMOUNTS: frozenset[int] = frozenset(
    amount for plan in CATALOG for amount in (plan.setup_mxn, plan.monthly_mxn)
) | {299}


def find_plan(slug: str) -> Plan | None:
    """The plan with this slug, or ``None``. Slugs match ``LeadFocus`` values."""
    for plan in CATALOG:
        if plan.slug == slug:
            return plan
    return None
