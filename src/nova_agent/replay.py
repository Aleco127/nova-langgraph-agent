"""A chat model that reads its answers from a script instead of a provider.

This is not a test double that leaked into ``src``. Replaying a fixed sequence
of model outputs is how you reproduce a conversation that went wrong: the graph,
the prompts, the tools and the validator all run exactly as they do in
production, and the one non-deterministic component is pinned. Without it,
"the agent quoted a price that does not exist" is a bug report you can only
investigate by paying for calls and hoping it happens again.

It is also what the container's smoke test runs, which is the point at which a
graph that fails to assemble stops being something CI can miss.

``langchain_core`` ships fake chat models, and they were the obvious candidate.
They raise ``NotImplementedError`` from ``bind_tools``, so a graph that binds its
tools -- as this one does, and as any real deployment must -- cannot be driven
by them at all.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


class ScriptedModel(BaseChatModel):
    """Returns the next scripted message on every call.

    The last entry repeats once the script runs out. That is deliberate: a
    script shorter than the graph's retry budget would otherwise fail with
    ``IndexError`` in the middle of a run, which reads as a graph bug when it is
    only a short script.
    """

    responses: list[AIMessage]
    # Every prompt this model was handed, in order. Kept because the most
    # useful question about a retry is not "did it retry" but "what did the
    # redraft actually get told", and that is only answerable from the prompt.
    calls: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> ScriptedModel:
        """Accept the binding and ignore it.

        The scripted answers already contain whatever tool calls the replay is
        meant to make, so there is nothing to bind. Accepting the call rather
        than raising is what lets this model drive the real graph instead of a
        stripped-down copy of it.
        """
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.calls.append(list(messages))
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return ChatResult(generations=[ChatGeneration(message=self.responses[index])])


def scripted(texts: Iterable[str]) -> ScriptedModel:
    """A model that answers with these strings, in order."""
    return ScriptedModel(responses=[AIMessage(content=text) for text in texts], calls=[])
