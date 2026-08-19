"""Phone and email extraction, exercised with the shapes real customers send."""

from __future__ import annotations

import pytest

from nova_agent.contacts import Contact, canonical_phone, extract_contact, phone_variants

CANONICAL = "+5213312345678"


@pytest.mark.parametrize(
    "raw",
    [
        "3312345678",  # bare national number, the most common by far
        "+5213312345678",  # already canonical
        "+523312345678",  # country code without the WhatsApp mobile prefix
        "+52 33 1234 5678",  # spaced, as WhatsApp itself displays it
        "(33) 1234-5678",  # copied off a business card
        "33.1234.5678",  # dots, typed on a phone keypad
        "  +52 33 1234 5678  ",  # pasted with surrounding whitespace
    ],
)
def test_every_spelling_collapses_to_one_canonical_form(raw: str) -> None:
    assert canonical_phone(raw) == CANONICAL


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "   ",
        "12345",  # too short to be a phone number
        "+1 415 555 0132",  # valid, but not Mexican
        "441234567890",  # twelve digits, wrong country code
        "5211234567890123",  # too long
        "no traigo numero",
    ],
)
def test_non_mexican_mobiles_are_rejected_rather_than_coerced(raw: str | None) -> None:
    assert canonical_phone(raw) is None


def test_national_number_starting_with_one_is_not_mistaken_for_the_mobile_prefix() -> None:
    # 52 + 1234567890: the leading 1 belongs to the national number here, and
    # trimming it as a mobile prefix would produce a nine-digit number.
    assert canonical_phone("+521234567890") == "+5211234567890"


def test_variants_lists_canonical_first_then_the_legacy_spelling() -> None:
    assert phone_variants("3312345678") == [CANONICAL, "+523312345678"]


def test_variants_of_an_unusable_number_is_empty_not_a_list_of_junk() -> None:
    assert phone_variants("hola") == []
    assert phone_variants(None) == []


def test_extracts_phone_and_email_from_one_sentence() -> None:
    text = "Perfecto, mandame la propuesta a Hola@Zook.MX o al 33 1234 5678 porfa"
    assert extract_contact(text) == Contact(phone=CANONICAL, email="hola@zook.mx")


def test_trailing_full_stop_is_not_part_of_the_address() -> None:
    # Without the rstrip this address bounces, and the bounce is silent.
    assert extract_contact("escribeme a hola@zook.mx.").email == "hola@zook.mx"


def test_first_plausible_number_wins_when_the_message_carries_two() -> None:
    # The 2026 is a year, not a phone number, and the 8500 is a price. Taking
    # the first parseable ten-digit run is the documented behaviour.
    text = "en 2026 quiero mi sitio, presupuesto 8500, mi cel 33 1234 5678"
    assert extract_contact(text).phone == CANONICAL


def test_message_with_no_contact_details_yields_an_empty_contact() -> None:
    contact = extract_contact("hola, cuanto cuesta?")
    assert contact.is_empty
    assert contact == Contact()


@pytest.mark.parametrize("text", [None, ""])
def test_missing_text_is_not_an_error(text: str | None) -> None:
    assert extract_contact(text).is_empty


def test_a_contact_with_only_an_email_is_not_empty() -> None:
    assert not Contact(email="hola@zook.mx").is_empty
