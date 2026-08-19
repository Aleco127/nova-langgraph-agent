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
