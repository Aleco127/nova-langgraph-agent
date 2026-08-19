"""Contact details recovered from whatever the customer happened to type.

Channels differ in what they know about the person on the other end. WhatsApp
hands over a verified phone number; the web widget, Instagram and Messenger hand
over nothing at all. For those, the only identity available is the one the
customer types mid-sentence -- "mandame la info al 33 1234 5678" -- so the agent
has to read it out of free text before it can follow up.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Mexican mobiles are NN-NNNN-NNNN once the country code is stripped.
_NATIONAL_DIGITS = 10
_COUNTRY_CODE = "52"
# WhatsApp routes Mexican mobiles with a '1' wedged between the country code and
# the national number. The same subscriber shows up as +52... in address books,
# in Meta webhooks, and in anything typed by hand.
_MOBILE_PREFIX = _COUNTRY_CODE + "1"

# Every quantifier is bounded, which is what keeps the runtime linear: an
# unbounded one lets a long domain be divided many ways and the engine walks
# through the divisions before giving up. The bounds are not arbitrary --
# RFC 5321 caps a local part at 64 characters and RFC 1035 caps each label at
# 63 -- so nothing valid is excluded by them. This matters because the input
# is a chat message typed by a stranger, which makes an unbounded pattern a
# denial-of-service vector rather than a style preference.
_EMAIL_RE = re.compile(r"[\w.+-]{1,64}@[\w-]{1,63}(?:\.[\w-]{1,63}){1,8}")
# A digit run long enough to be a phone number, tolerating the separators people
# actually type: spaces, dashes, dots, parentheses. It deliberately does not
# require a digit at the end: the class already contains digits, so a trailing
# \d would overlap with it and every near-miss would backtrack through all the
# ways to divide the run. Trailing separators are harmless here because
# canonical_phone strips everything that is not a digit before validating -- the
# pattern only has to find candidates, not judge them.
_PHONE_CANDIDATE_RE = re.compile(r"\+?\d[\d\s().-]{8,18}")


def canonical_phone(raw: str | None) -> str | None:
    """Return ``raw`` as ``+521NNNNNNNNNN``, or None if it is not a Mexican mobile.

    There is exactly one canonical form and it is the ``+521`` one, because that
    is the form WhatsApp routes on. Accepting both spellings as equally valid is
    how one human being ends up owning two conversation threads: the webhook
    stores ``+521...``, the customer later types ``+52...``, the lookup misses,
    and a second thread opens with none of the history.
    """
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)

    if len(digits) == _NATIONAL_DIGITS:
        return "+" + _MOBILE_PREFIX + digits
    if len(digits) == len(_COUNTRY_CODE) + _NATIONAL_DIGITS and digits.startswith(_COUNTRY_CODE):
        # 52 + ten national digits. Handled uniformly even when those ten happen
        # to start with a 1: no Mexican area code begins with 1, so a leading 1
        # here is part of the national number, not a stray mobile prefix.
        return "+" + _MOBILE_PREFIX + digits[len(_COUNTRY_CODE) :]
    if len(digits) == len(_MOBILE_PREFIX) + _NATIONAL_DIGITS and digits.startswith(_MOBILE_PREFIX):
        return "+" + digits
    return None


def phone_variants(raw: str | None) -> list[str]:
    """Every spelling of one subscriber, canonical first.

    Used to look up conversations stored before this normalisation existed. New
    rows only ever get the canonical form.
    """
    canonical = canonical_phone(raw)
    if canonical is None:
        return []
    national = canonical[len("+") + len(_MOBILE_PREFIX) :]
    return [canonical, "+" + _COUNTRY_CODE + national]


@dataclass(frozen=True)
class Contact:
    """What could be recovered from one message. Both fields are usually None."""

    phone: str | None = None
    email: str | None = None

    @property
    def is_empty(self) -> bool:
        return self.phone is None and self.email is None


def extract_contact(text: str | None) -> Contact:
    """Best-effort phone and email from free text.

    Deliberately returns the *first* plausible phone rather than all of them. A
    message carrying two numbers is almost always one number plus a price, a
    date or a street address, and guessing which is which is worse than taking
    the first and letting the human correct it.
    """
    if not text:
        return Contact()

    email = None
    match = _EMAIL_RE.search(text)
    if match:
        # rstrip('.') because "escribeme a hola@zook.mx." swallows the full stop
        # that ended the sentence, and the address then bounces.
        email = match.group(0).strip().lower().rstrip(".")

    phone = None
    for candidate in _PHONE_CANDIDATE_RE.findall(text):
        phone = canonical_phone(candidate)
        if phone is not None:
            break

    return Contact(phone=phone, email=email)
