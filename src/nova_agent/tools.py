"""The tools the agent may call mid-turn.

Both read from the catalog and neither touches the network. That is a design
choice, not a simplification: a tool that can hang is a tool that turns one slow
dependency into a conversation the customer watches time out, and the retry loop
in this graph exists to fix bad content, not to paper over an unavailable
service.
"""

from __future__ import annotations

from langchain_core.tools import tool

from nova_agent.catalog import CATALOG, find_plan


@tool
def consultar_precio(plan: str) -> str:
    """Precio de un plan del catalogo. Usa el slug: bot-whatsapp o paginas-web."""
    found = find_plan(plan)
    if found is None:
        available = ", ".join(item.slug for item in CATALOG)
        return f"No existe el plan '{plan}'. Planes disponibles: {available}."
    parts = [
        f"{found.name}: {found.setup_mxn} de instalacion",
        f"{found.monthly_mxn} al mes",
    ]
    if found.notes:
        parts.append(found.notes)
    return ". ".join(parts)


@tool
def listar_planes() -> str:
    """Todos los planes del catalogo con sus slugs."""
    return "; ".join(f"{plan.slug} ({plan.name})" for plan in CATALOG)


# The list the graph binds to the model. Kept here so adding a tool is one edit
# and the graph does not need to know what is in it.
AGENT_TOOLS = [consultar_precio, listar_planes]
