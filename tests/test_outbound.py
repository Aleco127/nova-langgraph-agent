"""Reply splitting, including the cases that have no clean word break."""

from __future__ import annotations

import pytest

from nova_agent.outbound import WHATSAPP_LIMIT, split_outbound


def test_a_short_reply_is_left_alone() -> None:
    assert split_outbound("hola, con gusto te ayudo") == ["hola, con gusto te ayudo"]


def test_a_reply_exactly_at_the_limit_is_not_split() -> None:
    text = "a" * WHATSAPP_LIMIT
    assert split_outbound(text) == [text]


def test_an_empty_reply_yields_one_empty_message() -> None:
    # Returning [] would make the caller send nothing at all, silently.
    assert split_outbound("") == [""]


def test_splitting_happens_on_a_word_break() -> None:
    assert split_outbound("uno dos tres", limit=7) == ["uno dos", "tres"]


def test_the_space_at_the_break_is_not_carried_into_either_chunk() -> None:
    for chunk in split_outbound("uno dos tres cuatro", limit=8):
        assert chunk == chunk.strip()


def test_a_space_sitting_exactly_on_the_boundary_still_counts_as_a_break() -> None:
    # "uno dos" is 7 characters and the space is the eighth.
    assert split_outbound("uno dos tres", limit=7) == ["uno dos", "tres"]


def test_a_word_longer_than_the_window_is_cut_mid_word() -> None:
    # No break exists, and an oversized message is dropped by the channel
    # without an error, so cutting is the lesser evil.
    assert split_outbound("a" * 25, limit=10) == ["a" * 10, "a" * 10, "a" * 5]


def test_every_chunk_respects_the_limit() -> None:
    text = " ".join(f"palabra{i}" for i in range(500))
    assert all(len(chunk) <= 120 for chunk in split_outbound(text, limit=120))


def test_no_content_is_lost_when_splitting() -> None:
    text = " ".join(f"palabra{i}" for i in range(200))
    assert " ".join(split_outbound(text, limit=100)) == text


@pytest.mark.parametrize("limit", [5, 17, 64, 500])
def test_splitting_is_stable_across_limits(limit: int) -> None:
    text = " ".join(f"w{i}" for i in range(300))
    chunks = split_outbound(text, limit=limit)
    assert all(len(c) <= limit for c in chunks)
    assert "".join(c.replace(" ", "") for c in chunks) == text.replace(" ", "")
