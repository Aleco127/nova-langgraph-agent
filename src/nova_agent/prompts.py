"""The system prompt, assembled from the directive the classifier picked.

Split out of the nodes because the prompt is the part most likely to be edited
by someone who is not going to read the graph, and because a directive that has
no block here should fail loudly rather than silently produce a generic agent.
"""

from __future__ import annotations

from nova_agent.intent import Directive

BASE_PROMPT = (
    "Eres Alex, del equipo de ventas. Escribes por chat, en espanol de Mexico, "
    "de tu, breve y concreto.\n"
    "Habla siempre del resultado para el cliente: atencion a cualquier hora, "
    "citas agendadas, clientes que no se pierden. Nunca hables de la tecnologia "
    "que hay detras.\n"
    "Los precios salen unicamente de la herramienta consultar_precio. Si no la "
    "has consultado, no des cifras."
)

_DIRECTIVE_BLOCKS: dict[Directive, str] = {
    Directive.NONE: (
        "Aun no sabes que busca el lead. Averigualo en una sola pregunta antes de proponer nada."
    ),
    Directive.WEB_SALES: (
        "El lead quiere una pagina web. Ofrecele una vista previa gratis y "
        "pidele el nombre del negocio y el giro."
    ),
    Directive.WEB_SALES_AWAITING_PREVIEW: (
        "Ya pidio la vista previa y sigue pendiente. No la vuelvas a ofrecer: "
        "confirma que esta en camino y usa el tiempo para calificar."
    ),
    Directive.POST_PREVIEW_CLOSE: (
        "Ya vio su vista previa. Deja de vender la idea y cierra: precio, que "
        "incluye y cuando arranca."
    ),
    Directive.BOT_SALES: (
        "El lead quiere el bot de WhatsApp. Pregunta cuantos mensajes recibe al "
        "dia y que se le esta escapando por no contestar a tiempo."
    ),
}


def system_prompt(directive: Directive) -> str:
    """The full system prompt for a directive.

    Raises on an unknown directive instead of falling back to the base prompt.
    A missing block means someone added a sales script and forgot to write it,
    and an agent that quietly runs the generic version hides that until a
    customer gets the wrong conversation.
    """
    block = _DIRECTIVE_BLOCKS.get(directive)
    if block is None:  # pragma: no cover - every Directive has a block
        raise KeyError(f"no prompt block for directive {directive!r}")
    return f"{BASE_PROMPT}\n\n{block}"
