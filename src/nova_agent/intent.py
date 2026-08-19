"""Which sales script the agent should be running, and when it changes.

A lead arrives either from the website-building ads or from the chatbot ads, and
the two want opposite conversations: one wants to see a preview of their site,
the other wants to know what the bot would answer for them. Running the wrong
script is not a cosmetic error -- it asks the customer questions they already
answered in the ad they clicked.
"""

from __future__ import annotations

import re
from enum import Enum, StrEnum


class LeadFocus(StrEnum):
    """What the lead came for."""

    WEB = "paginas-web"
    BOT = "bot-whatsapp"
    UNKNOWN = "unknown"


class SalesStage(StrEnum):
    """How far along the conversation is. Set by the agent, not by the customer."""

    NEW = "new"
    PREVIEW_REQUESTED = "preview_solicitado"
    PREVIEW_DELIVERED = "preview_entregado"
    NEGOTIATION = "negociacion"
    CLOSED = "cerrado"


class Directive(Enum):
    """The extra instruction block appended to the system prompt."""

    NONE = "none"
    WEB_SALES = "web_sales"
    WEB_SALES_AWAITING_PREVIEW = "web_sales_awaiting_preview"
    POST_PREVIEW_CLOSE = "post_preview_close"
    BOT_SALES = "bot_sales"


# Matches the way people ask for a site: "una pagina web", "sitios web",
# "mi sitio". Accent-tolerant because half the traffic types from a phone
# keyboard with autocorrect off.
_WEB_FOCUS_RE = re.compile(
    r"p[aá]ginas?\s+web|sitios?\s+web|mi\s+sitio\b|una\s+web\b",
    re.IGNORECASE,
)

# Stages at which the preview is already in the customer's hands, so the script
# switches from "let me show you" to "let us close".
_POST_PREVIEW_STAGES = frozenset(
    {SalesStage.PREVIEW_DELIVERED, SalesStage.NEGOTIATION, SalesStage.CLOSED}
)


def classify_focus(message: str | None, known: LeadFocus = LeadFocus.UNKNOWN) -> LeadFocus:
    """Resolve the lead's focus, preferring what is already known.

    ``known`` wins whenever it is set, and that ordering is the whole point. It
    comes from the ad the customer clicked, which is hard evidence; the message
    text is an inference. Letting a later message re-classify the thread makes
    the agent switch scripts mid-conversation, which reads as amnesia.
    """
    if known is not LeadFocus.UNKNOWN:
        return known
    if message and _WEB_FOCUS_RE.search(message):
        return LeadFocus.WEB
    return LeadFocus.UNKNOWN


def select_directive(focus: LeadFocus, stage: SalesStage = SalesStage.NEW) -> Directive:
    """Pick the prompt directive for a (focus, stage) pair.

    Stage is ignored for bot leads on purpose: that funnel has no preview step,
    so it has no stage-dependent branch to take.
    """
    if focus is LeadFocus.BOT:
        return Directive.BOT_SALES
    if focus is not LeadFocus.WEB:
        return Directive.NONE
    if stage in _POST_PREVIEW_STAGES:
        return Directive.POST_PREVIEW_CLOSE
    if stage is SalesStage.PREVIEW_REQUESTED:
        return Directive.WEB_SALES_AWAITING_PREVIEW
    return Directive.WEB_SALES
