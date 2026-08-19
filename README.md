# nova-langgraph-agent

A conversational sales agent modelled as an explicit state machine, and a CI/CD
pipeline whose quality gates actually block a merge.

The agent replaces a production WhatsApp/web chatbot that handles inbound sales
conversations across five channels. This repository reimplements its flow as a
graph rather than porting the original: the production service is an 80k-line
monolith whose configuration carries live API credentials, so it cannot be made
public and its coverage could never be brought into the green.

## Status

Milestone 1 of 2. The deterministic half of a conversation turn is in place --
contact extraction, lead classification, script selection and the state object
the graph will carry -- together with the pipeline that guards it. The LangGraph
nodes are the next milestone, and they arrive as wrappers around these functions
rather than as a rewrite, which is why the state shape exists already.
