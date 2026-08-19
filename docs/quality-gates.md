# Evidence that the gates block

Three runs, in the order they happened. Raw excerpts from the CI logs;
run ids are real and the runs are public.

---

## 1. Unplanned: the vulnerability gate caught the base image

Run 32217122867, first push. Nothing was fabricated here -- the very first
scan of a hello-world-sized image found eleven HIGH findings, all with
released fixes: nine in the util-linux family from a base image older than
the security archive, and two from pip's vendored msgpack and setuptools.

```
Total: 9 (HIGH: 9, CRITICAL: 0)
│ bsdutils      │ CVE-2026-53615 │ HIGH     │ fixed  │ 1:2.41-5                │ 2.41.5-0+deb13u1 │ [Integer Overflow or Wraparound in         │
Total: 2 (HIGH: 2, CRITICAL: 0)
```

Fixed by upgrading packages at build time and dropping pip from the runtime
image, not by adding nine lines to `.trivyignore`. That file is still empty.

---

## 2. Planned: both gates, on pull request #1

Run 32217585750. A module shipped without tests and a pinned
`setuptools==70.3.0`. Lint, formatting, image build and the container smoke
test all passed, so each gate failed for its own reason and nothing else.

```
src/nova_agent/__init__.py         1      0   100%
src/nova_agent/__main__.py        29      0   100%
src/nova_agent/contacts.py        45      0   100%
src/nova_agent/escalation.py      31     31     0%   8-71
src/nova_agent/intent.py          37      0   100%
src/nova_agent/state.py           22      0   100%
TOTAL                            165     31    81%
FAIL Required test coverage of 95% not reached. Total coverage: 81.21%
65 passed in 0.16s

## Coverage gate
```

```
Total: 1 (HIGH: 1, CRITICAL: 0)
│ setuptools (METADATA) │ CVE-2025-47273 │ HIGH     │ fixed  │ 70.3.0            │ 78.1.1        │ setuptools: Path Traversal Vulnerability in setuptools │
```

---

## 3. Green, after fixing the causes

Run 32217693986, same pull request. Coverage back to 100% because the tests
were written, and the scan clean because the dependency came out. Neither
threshold was lowered.

```
TOTAL                            165      0   100%
Required test coverage of 95% reached. Total coverage: 100.00%
95 passed
```

```
Report Summary

┌───────────────────────────────────────────────────────────────────────────┬────────────┬─────────────────┬─────────┐
│                                  Target                                   │    Type    │ Vulnerabilities │ Secrets │
├───────────────────────────────────────────────────────────────────────────┼────────────┼─────────────────┼─────────┤
│ nova-agent:369a2e63969177270867aff733ec969e83f56740 (debian 13.6)         │   debian   │        0        │    -    │
├───────────────────────────────────────────────────────────────────────────┼────────────┼─────────────────┼─────────┤
│ opt/venv/lib/python3.12/site-packages/nova_agent-0.1.0.dist-info/METADATA │ python-pkg │        0        │    -    │
└───────────────────────────────────────────────────────────────────────────┴────────────┴─────────────────┴─────────┘
Legend:
- '-': Not scanned
- '0': Clean (no security findings detected)
```

---

## 4. The case the absolute floor cannot see

Run 32268728097, [PR #2](../../pull/2). Eight new lines with no tests, in a
repository whose overall coverage was already at 100%. The total lands at
**95.38%**, above the 95% floor, so `--cov-fail-under` passes and reports
nothing wrong. That is not a flaw in the floor -- it is arithmetic. A codebase
comfortably above its threshold absorbs untested code without ever dipping
below it, and the larger the codebase the more it can absorb.

Coverage on New Code is measured against the change instead of the total, which
is why both gates exist:

```
new_lines_to_cover = 8    new_uncovered_lines = 8    new_coverage = 0.0
ERROR  new_coverage  LT  80  actual=0.0
QUALITY GATE STATUS: FAILED  (sonar-scanner exit code 3)
```

### It did not block on the first attempt

The first run of this same pull request passed, with the API reporting the
contradiction plainly:

```
new_coverage  status=OK  comparator=LT  errorThreshold=80  actualValue=0.0
"ignoredConditions": true
```

The cause is a SonarQube Cloud default: conditions on coverage and duplication
are ignored until a change reaches **20 new lines**. This change had 16. The
setting is inherited from the organisation and applies to every new project, so
a gate can look configured, report a green check, and quietly let untested code
through as long as it arrives in small enough commits -- which is the size of an
ordinary commit.

Switched off under Quality Gate, "Ignore duplication and coverage on small
changes". `ignoredConditions` then reads `false` and the gate blocks. Worth
knowing that it is on by default, because the failure mode is a gate that
reports success.

### Green

Run 32268987420, after writing the tests. Coverage on New Code 0% -> 100%.
Writing them also turned up two real bugs in the splitter: `str.rfind` returns
-1 when the window contains no space, so a word longer than the limit produced a
chunk of `text[:-1]` and a leftover single character; and the break character
was carried into the following chunk, so every message after the first began
with a space.

---

## 5. What the gate found once it was actually enforcing

With the exemption off, the first clean analysis reported one MAJOR issue
(`python:S8786`): super-linear backtracking in the email pattern, and then the
same in the phone pattern once the first was fixed.

```python
# before
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]{2,}")
_PHONE_CANDIDATE_RE = re.compile(r"\+?\d[\d\s().-]{8,18}\d")
```

Both had a class overlapping with what follows it -- `.` on both sides of the
literal dot in the first, `\d` on both sides of the trailing digit in the second
-- so one input has many valid divisions and the engine walks through them. The
input reaching these patterns is a chat message typed by a stranger, which makes
this a denial-of-service vector rather than a style preference. Neither `ruff`
nor 100% test coverage says anything about it: the tests all pass, quickly,
because none of them sends the shape that triggers it.

The phone pattern lost its trailing `\d`, which costs nothing because
`canonical_phone` strips non-digits before validating. The email pattern took
two attempts:

```python
# attempt 1 -- less backtracking, still flagged: a repeated group with its own
# quantifier inside still admits many divisions
r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"

# attempt 2 -- linear, still flagged: Sonar's analyser appears to predate
# Python 3.11 and read '++' as a nested quantifier rather than a possessive one
r"[\w.+-]++@[\w-]++(?:\.[\w-]++)++"

# final -- bounded, and bounded for a reason that outlives the analyser
r"[\w.+-]{1,64}@[\w-]{1,63}(?:\.[\w-]{1,63}){1,8}"
```

RFC 5321 caps a local part at 64 characters and RFC 1035 caps each label at 63,
so the bounds exclude nothing valid and the worst case is bounded by
construction. Both forms measure identically on the pathological input, which
two tests now assert.

Final state on `main`: 0 bugs, 0 vulnerabilities, 0 code smells, 0 security
hotspots, 100% coverage, and both `ignoredConditions: false`.

---

## 6. The LangGraph milestone: what the gates said, and what they did not

Worth recording honestly, because the interesting result is a negative one.

**The vulnerability gate did not fire, and it was expected to.** Adding
`langgraph` and `langchain-core` pulled 33 transitive packages into the runtime
image -- `pydantic`, `pydantic-core`, `httpx`, `langsmith`, `orjson`,
`ormsgpack`, `requests`, `urllib3`, `zstandard` and the rest -- and the image
grew from 188 MB to 278 MB. The plan listed "Trivy finds CVEs in the new
dependency tree" as the second most likely risk, with the mitigation being a
version bump rather than a suppression.

It came back clean on the first scan: 0 HIGH, 0 CRITICAL, `.trivyignore` still
empty. Current releases of that tree simply have no unpatched high-severity
findings today. The gate is unchanged and will catch the next one; this entry
exists so the absence is on the record rather than reported as a save.

**The coverage gate held without being touched.** The milestone added eight
modules (`graph`, `nodes`, `validation`, `catalog`, `tools`, `prompts`,
`replay`, `checkpointing`) and grew two more. The floor stayed at 95 and the
suite went from 110 tests to 225, ending at 100% across 464 statements.

**What actually found the defects was the test suite.** Four, all of them
behavioural rather than anything a linter reports:

| Defect | Found by |
|---|---|
| Tool router read the tail of a list `add_messages` reorders, silently halving the tool ceiling | `test_a_model_stuck_asking_for_tools_is_cut_off` |
| A full state sent into an existing thread erases its checkpointed history, silently | `test_the_second_turn_can_see_the_first` |
| `$2499` parsed as `$249`, so the validator rejected the agent's own catalog prices | `test_amounts_are_read_out_of_the_shapes_replies_actually_use` |
| Escalation matched "hablar con una persona" but not "hablar con un asesor" | `test_escalation_reason_names_the_rule_that_fired` |

The third and fourth are the ones worth dwelling on. Both are in pure functions
that already had 100% line coverage before the milestone started -- the lines
ran, the branch that mattered was never given the input that exposes it. A
coverage gate proves that code was executed; it says nothing about whether it
was executed with the values that break it. That is the honest limit of the
number in the badge.

## 7. A finding the scanners were never going to report

While wiring the checkpointer, LangGraph logged this on every turn:

```
Deserializing unregistered type nova_agent.contacts.Contact from checkpoint.
This will be blocked in a future version. Set LANGGRAPH_STRICT_MSGPACK=true to
block now, or add to allowed_msgpack_modules to allow explicitly.
```

Following it to `JsonPlusSerializer` turns up the reason, in the library's own
docstring:

> It should not be used on untrusted python objects. If an attacker can write
> directly to your checkpoint database, they may be able to trigger code
> execution when data is deserialized.

The default is permissive: the deserialiser rebuilds whatever type the stored
record names. For this agent the checkpoint store is a database of customer
conversations, which is not a component worth assuming stays trusted -- it is
reachable from an application bug, a leaked connection string, or a backup
restored from the wrong place.

`checkpointing.py` now passes an explicit allowlist of the four project types
that ever enter a checkpoint. A test proves the restriction is real rather than
decorative: a type outside the list comes back as a plain dict, with its
constructor never called.

```python
permissive = JsonPlusSerializer()
blob = permissive.dumps_typed({"x": NotOurs("rm -rf /")})

assert isinstance(permissive.loads_typed(blob)["x"], NotOurs)  # rebuilt
assert build_serializer().loads_typed(blob)["x"] == {"payload": "rm -rf /"}  # inert
```

Neither Trivy nor SonarCloud reports this. It is not a CVE -- the library is
behaving as documented -- and it is not a code smell. It surfaced because a log
line was read instead of filtered out, which is the part of "DevSecOps" that no
gate performs for you.
