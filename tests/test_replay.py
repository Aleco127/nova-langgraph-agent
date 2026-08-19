"""Deterministic replay, and what the checkpointer is allowed to rebuild."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from nova_agent.checkpointing import CHECKPOINT_TYPES, build_checkpointer, build_serializer
from nova_agent.contacts import Contact
from nova_agent.intent import Directive, LeadFocus, SalesStage
from nova_agent.replay import ScriptedModel, scripted
from nova_agent.tools import AGENT_TOOLS


@dataclass
class NotOurs:
    """Stands in for whatever an attacker would name in a tampered checkpoint.

    Declared at module level because a class defined inside a test function
    cannot be resolved by name on the way back in, which would make the
    permissive deserialiser look safe for the wrong reason.
    """

    payload: str


def test_answers_come_back_in_order() -> None:
    model = scripted(["uno", "dos"])
    assert model.invoke("a").content == "uno"
    assert model.invoke("b").content == "dos"


def test_the_last_answer_repeats_once_the_script_runs_out() -> None:
    """A script shorter than the retry budget would otherwise raise IndexError
    mid-run, which reads as a graph bug when it is only a short script."""
    model = scripted(["solo una"])
    assert [model.invoke("x").content for _ in range(3)] == ["solo una"] * 3


def test_every_prompt_is_recorded() -> None:
    """The useful question about a retry is not whether it happened but what the
    redraft was told, and that is only answerable from the prompt."""
    model = scripted(["uno", "dos"])
    model.invoke([HumanMessage(content="primero")])
    model.invoke([HumanMessage(content="segundo")])
    assert [call[0].content for call in model.calls] == ["primero", "segundo"]


def test_two_models_do_not_share_a_call_log() -> None:
    """A mutable default on a pydantic field shared between instances would make
    every assertion about call counts depend on test ordering."""
    first, second = scripted(["a"]), scripted(["b"])
    first.invoke("x")
    assert first.calls != []
    assert second.calls == []


def test_binding_tools_is_accepted_so_the_real_graph_can_be_driven() -> None:
    """``langchain_core``'s own fakes raise ``NotImplementedError`` here, which
    means a graph that binds its tools -- as any real deployment must -- cannot
    be tested with them at all."""
    model = scripted(["hola"])
    assert model.bind_tools(AGENT_TOOLS) is model


def test_tool_calls_can_be_scripted() -> None:
    draft = AIMessage(
        content="",
        tool_calls=[{"name": "listar_planes", "args": {}, "id": "c1", "type": "tool_call"}],
    )
    assert ScriptedModel(responses=[draft]).invoke("x").tool_calls[0]["name"] == "listar_planes"


def test_the_llm_type_is_declared() -> None:
    assert scripted(["x"])._llm_type == "scripted"


# --------------------------------------------------------------------------
# Checkpoint deserialisation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        Contact(phone="+5213312345678", email="a@b.mx"),
        LeadFocus.WEB,
        SalesStage.NEGOTIATION,
        Directive.POST_PREVIEW_CLOSE,
    ],
)
def test_the_types_this_project_checkpoints_survive_a_round_trip(value: object) -> None:
    serde = build_serializer()
    assert serde.loads_typed(serde.dumps_typed({"v": value}))["v"] == value


def test_the_allowlist_covers_every_project_type_in_the_state() -> None:
    assert set(CHECKPOINT_TYPES) == {Contact, LeadFocus, SalesStage, Directive}


def test_a_type_outside_the_allowlist_is_not_reconstructed() -> None:
    """The mitigation, stated as a test. LangGraph's deserialiser defaults to
    rebuilding whatever type the stored record names, and its own documentation
    warns that an attacker who can write to the checkpoint store may reach code
    execution that way. With an allowlist the payload arrives as inert data and
    the constructor is never called.
    """
    permissive = JsonPlusSerializer()
    blob = permissive.dumps_typed({"x": NotOurs("rm -rf /")})

    rebuilt = permissive.loads_typed(blob)["x"]
    assert isinstance(rebuilt, NotOurs)

    restricted = build_serializer().loads_typed(blob)["x"]
    assert not isinstance(restricted, NotOurs)
    assert restricted == {"payload": "rm -rf /"}


def test_the_checkpointer_is_built_with_the_restricted_serialiser() -> None:
    assert build_checkpointer().serde._allowed_msgpack_modules != True  # noqa: E712
