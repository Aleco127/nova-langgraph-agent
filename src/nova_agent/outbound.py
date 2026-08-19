"""Splitting a reply into messages the channel will actually accept."""

from __future__ import annotations

# WhatsApp rejects anything longer than this, and rejects it silently from the
# sender's point of view: the API call succeeds and the customer sees nothing.
WHATSAPP_LIMIT = 4096


def split_outbound(text: str, limit: int = WHATSAPP_LIMIT) -> list[str]:
    """Break a reply into chunks of at most ``limit`` characters, on word breaks.

    Splitting mid-word is worse than it sounds on a chat channel: the two halves
    arrive as separate bubbles and the reader sees a typo, so word boundaries
    are preferred wherever one exists inside the window.
    """
    if not text:
        return [""]

    parts: list[str] = []
    while len(text) > limit:
        # limit + 1 so a space sitting exactly at the boundary still counts as a
        # break; searching only up to limit would push it into the next chunk.
        cut = text.rfind(" ", 0, limit + 1)
        if cut <= 0:
            # A single word longer than the whole window. Nothing to break on,
            # so it gets cut mid-word -- which beats the alternative of leaving
            # the message oversized and having the channel drop it silently.
            cut = limit
        parts.append(text[:cut].rstrip())
        text = text[cut:].lstrip()

    parts.append(text)
    return parts
