# nova-langgraph-agent

[![CI](https://github.com/Aleco127/nova-langgraph-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Aleco127/nova-langgraph-agent/actions/workflows/ci.yml)
[![coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)](docs/quality-gates.md)
[![gate](https://img.shields.io/badge/coverage%20floor-95%25-blue)](.github/workflows/ci.yml)
[![trivy](https://img.shields.io/badge/trivy-HIGH%2FCRITICAL%20blocking-blue)](.github/workflows/ci.yml)
[![Quality gate](https://sonarcloud.io/api/project_badges/measure?project=Aleco127_nova-langgraph-agent&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=Aleco127_nova-langgraph-agent)

A conversational sales agent modelled as an explicit state machine, and a
pipeline whose quality gates actually block a merge.

The agent replaces a production WhatsApp and web chatbot that handles inbound
sales across five channels. This repository reimplements its flow rather than
porting it: the production service is an 80k-line monolith whose configuration
carries live API credentials, so it can neither be made public nor brought into
the green.

## What is here

Milestone 1 of 2: the deterministic half of a conversation turn, and the
pipeline that guards it.

| Module | What it decides |
|---|---|
| `contacts.py` | The phone and email hidden in free text, normalised to one canonical form |
| `intent.py` | Which sales script applies, and why a later message must not change it |
| `escalation.py` | When to stop answering and hand over to a person |
| `state.py` | The state object each graph node will read and write |
| `__main__.py` | One turn's deterministic work, runnable without an API key |

Every one of these is a pure function, which is what lets a coverage gate hold
them to a real standard, and what lets the graph nodes wrap them unchanged
instead of replacing them.

```console
$ docker run --rm nova-agent "quiero una pagina web, mi cel 33 1234 5678"
{"channel": "web", "contact": {"email": null, "phone": "+5213312345678"},
 "directive": "web_sales", "focus": "paginas-web", "stage": "new"}
```

## The gates

**Coverage.** `pytest --cov-fail-under=95`, enforced on the runner with no
external service involved. The suite reports 100%; the floor sits at 95 because
pinning a gate to the current number turns every guard clause into a build
failure, and a team that cannot add one without writing a ceremonial test
learns to bypass the gate instead.

Coverage is gated twice, and the two catch different things. The floor above is
absolute and cannot see a repository that sits comfortably above it while
absorbing untested code; SonarQube Cloud measures Coverage on New Code, which is
computed against the change rather than the total. `sonar.qualitygate.wait=true`
makes the workflow block on the verdict instead of firing the analysis and
moving on.

**Vulnerabilities.** Trivy, `--severity HIGH,CRITICAL --exit-code 1
--ignore-unfixed`. That last flag is the difference between a gate people
respect and one they route around: without it a CVE with no released patch
keeps the pipeline red indefinitely. `.trivyignore` is empty, and every entry it
ever gains must carry a justification and a review date.

The image scan also uploads SARIF to GitHub code scanning. Two scans run, not
one: the reporting scan cannot fail, so a run that trips the gate still produces
the report explaining why.

## Evidence

A pipeline that has only ever been green proves nothing about its gates.
[`docs/quality-gates.md`](docs/quality-gates.md) records three real runs:

1. **Unplanned.** The first scan of this repository found **11 HIGH findings**,
   all with released fixes -- nine in `util-linux` from a base image older than
   the security archive, two from pip's vendored `msgpack` and `setuptools`.
   Fixed by upgrading at build time and removing pip from the runtime image, so
   the count went to **0** with `.trivyignore` still empty.
2. **Planned.** [PR #1](../../pull/1) shipped a module with no tests and a
   pinned `setuptools==70.3.0`. Coverage fell to 81% and the scan found the CVE;
   both gates blocked, while lint, formatting, build and the container smoke
   test passed -- each gate failed for its own reason and nothing else.
3. **Green.** The same PR, after writing the tests and removing the dependency.
   Neither threshold was lowered.

## Running it

```console
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
ruff check . && ruff format --check .
pytest --cov=nova_agent --cov-fail-under=95
```

The container, and the same scan CI runs:

```console
docker build -t nova-agent .
docker run --rm nova-agent "quiero hablar con un asesor"
trivy image --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 nova-agent
```

## Notes on the runtime image

It carries no package manager. Removing pip took out its vendored `msgpack` and
`setuptools` -- two of the eleven findings above -- and it also means a process
that gets code execution here has nothing to fetch its next stage with. Nothing
in the runtime path imports pip, so there is no cost to this.

## Next

The LangGraph milestone: typed state, conditional edges, a retry cycle with
backoff, a checkpointer for memory, and an interrupt for the hand-over that
`escalation.py` already decides. The nodes wrap the functions above, which is
why the state shape exists already.
