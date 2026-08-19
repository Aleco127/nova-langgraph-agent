"""The price list and the tools that read it."""

from __future__ import annotations

from nova_agent.catalog import CATALOG, QUOTABLE_AMOUNTS, find_plan
from nova_agent.intent import LeadFocus
from nova_agent.tools import AGENT_TOOLS, consultar_precio, listar_planes
from nova_agent.validation import invented_amounts


def test_slugs_match_the_focus_values() -> None:
    """The classifier's focus is what selects a plan. If the two vocabularies
    drift apart, a correctly classified lead gets told its plan does not
    exist."""
    focus_values = {focus.value for focus in LeadFocus} - {LeadFocus.UNKNOWN.value}
    assert {plan.slug for plan in CATALOG} == focus_values


def test_every_catalog_figure_is_quotable() -> None:
    """The validator and the catalog have to agree, or the agent rejects its own
    correct prices and redrafts until it gives up."""
    for plan in CATALOG:
        assert plan.setup_mxn in QUOTABLE_AMOUNTS
        assert plan.monthly_mxn in QUOTABLE_AMOUNTS


def test_what_the_price_tool_returns_passes_validation() -> None:
    """The loop this closes: the tool is the only sanctioned source of prices,
    so a reply repeating it verbatim must not be flagged as invented."""
    for plan in CATALOG:
        answer = consultar_precio.invoke({"plan": plan.slug})
        assert invented_amounts(answer) == []


def test_find_plan_returns_none_for_something_that_is_not_sold() -> None:
    assert find_plan("consultoria-lunar") is None


def test_an_unknown_plan_is_answered_not_raised() -> None:
    """A tool that raises takes the turn down. One that lists the alternatives
    gives the model something to recover from."""
    answer = consultar_precio.invoke({"plan": "consultoria-lunar"})
    assert "no existe" in answer.lower()
    for plan in CATALOG:
        assert plan.slug in answer


def test_the_price_tool_reports_setup_monthly_and_notes() -> None:
    answer = consultar_precio.invoke({"plan": "bot-whatsapp"})
    assert "2499" in answer
    assert "650" in answer
    assert "299" in answer


def test_a_plan_with_no_notes_does_not_trail_a_separator() -> None:
    answer = consultar_precio.invoke({"plan": "paginas-web"})
    assert not answer.endswith(". ")
    assert "6900" in answer


def test_listing_plans_gives_the_model_the_slugs_it_has_to_use() -> None:
    answer = listar_planes.invoke({})
    for plan in CATALOG:
        assert plan.slug in answer


def test_the_bound_tool_list_is_what_the_module_exposes() -> None:
    assert {tool.name for tool in AGENT_TOOLS} == {"consultar_precio", "listar_planes"}
