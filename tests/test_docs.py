"""The README's diagram has to be the graph the code compiles.

A hand-maintained architecture diagram is wrong within a month, and a wrong
diagram is worse than none: it is the thing a reader trusts instead of reading
the code. Making that a build failure is cheap here, because the graph can draw
itself.
"""

from __future__ import annotations

import re
from pathlib import Path

from nova_agent.__main__ import diagram

README = Path(__file__).resolve().parent.parent / "README.md"
_MERMAID_BLOCK = re.compile(r"```mermaid\n(.*?)```", re.DOTALL)


def _readme_diagram() -> str:
    blocks = _MERMAID_BLOCK.findall(README.read_text(encoding="utf-8"))
    assert len(blocks) == 1, f"expected exactly one mermaid block, found {len(blocks)}"
    return blocks[0].strip()


def _generated_diagram() -> str:
    # draw_mermaid() prepends a YAML front matter block that GitHub's renderer
    # does not accept inside a fenced ```mermaid block, so the README carries
    # the graph body only.
    return diagram().split("graph TD;", 1)[1].strip()


def test_the_readme_diagram_matches_the_compiled_graph() -> None:
    assert _readme_diagram().split("graph TD;", 1)[1].strip() == _generated_diagram()


def test_the_diagram_shows_the_retry_cycle() -> None:
    """The one edge the README argues the whole design around. A diagram that
    lost it would still match the code -- and the code would be wrong."""
    body = _readme_diagram()
    assert "revise --> generate" in body
    assert "validate -.-> revise" in body


def test_the_diagram_shows_that_exhaustion_reaches_a_person() -> None:
    body = _readme_diagram()
    assert "validate -.-> give_up" in body
    assert "give_up --> escalate" in body
    assert "give_up --> __end__" not in body
