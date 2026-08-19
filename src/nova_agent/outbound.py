"""Splitting a reply into messages the channel will actually accept."""

# WhatsApp rejects anything longer than this, and rejects it silently from the
# sender's point of view: the API call succeeds and the customer sees nothing.
WHATSAPP_LIMIT = 4096


def split_outbound(text, limit=WHATSAPP_LIMIT):
    """Break a reply into chunks no longer than ``limit``, splitting on spaces."""
    parts = []
    while len(text) > limit:
        cut = text.rfind(" ", 0, limit)
        parts.append(text[:cut])
        text = text[cut:]
    return [*parts, text]
