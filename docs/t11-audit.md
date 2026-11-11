# T11 independent audit

Scope is the local `feature/t11-oncall-agent` working tree at T10 baseline `7b6889cfdc5116266c3bcbc8d572c4bd3a76931b` (PR #24 open/unmerged), taken over from the Codex implementation on 2026-11-11 and audited independently against [Issue #11](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/11), the specification, the architecture and the [Codex validation record](t11-validation.md). The Codex working tree was checkpointed outside the repository before any change (`C:\Users\chaki\project2-aiDTC\checkpoints\t11-codex-handover-20261111-094506`). All T09/T10 source, evidence, application data, backups and the retained fixture databases were preserved. Nothing was committed, pushed or published.

## Real-model acceptance: PASSED with the only approved zero-cost provider

No cloud API credit exists and none was purchased. The owner's machine already had Ollama 0.40.16 with `llama3.2:3b` (3.2B, Q4_K_M, 2,019,377,376-byte weights) downloaded. Codex could not use it because the `C:\Users\chaki\.ollama` folder had lost the owner's own access-control entry, so the server fails to create `models\manifests-v2` and answers HTTP 500 on every model endpoint. Repairing that entry was outside what this session was permitted to do; the owner can run `icacls C:\Users\chaki\.ollama /grant "chaki:(OI)(CI)F" /T`. Instead a second `ollama.exe serve` was started on `127.0.0.1:11435` with `OLLAMA_MODELS` pointing at a scratch directory whose `blobs` folder is a junction to the existing weights, `OLLAMA_NOPRUNE=1`, `OLLAMA_NO_CLOUD=1`. Nothing was downloaded, copied or modified in the owner's folder. Containers reach it as `host.docker.internal:11435`. Claude Code later stopped that server for host memory pressure; the evidence below was already durable.

Structured-output (grammar-constrained) sampling crashes the llama.cpp runner on this machine's Radeon RX 5500M Vulkan backend with `Unexpected empty grammar stack`, even in plain JSON mode; CPU-only inference (`OLLAMA_VULKAN=0`) works. Evidence: `artifacts/claude/preflight-schema-probe.log`. A full diagnosis takes about 20 s on the idle Ryzen 5 5600H (6 cores) and 29 s while test suites compete for CPU.

### Live result

`agent_tests/test_real_model.py` ran the unmodified runtime (`python -m fieldops.oncall.runtime`) in a one-off `oncall-agent` container with `FIELDOPS_ONCALL_PROVIDER=ollama`, `FIELDOPS_ONCALL_MODEL=llama3.2:3b`, `FIELDOPS_ONCALL_PROVIDER_APPROVED=true`, `FIELDOPS_ONCALL_MAX_CALLS=1`, `FIELDOPS_ONCALL_PROVIDER_TIMEOUT=30` against the synthetic `fieldops-t09` stack (real Prometheus, Alertmanager, authenticated intake, PostgreSQL, Loki, Jaeger, worker). [JUnit](../artifacts/t11-real-model-live.xml), [evidence](../artifacts/t11-real-5bd8899d1d424a9ab234acf3b3f405a1/evidence.json), [agent log](../artifacts/t11-real-5bd8899d1d424a9ab234acf3b3f405a1/real-agent.log).

| Correlation | Value |
|---|---|
| Incident | cfa129e9-274c-4040-9319-3777025e7da0 |
| Outbox | d922fc79-fd48-4302-b16b-d5e13ba203b5 |
| Pause generation | 26 |
| Operator grant | 4a7d29a7-c932-4663-bcad-2283ff5817c2 |
| Stable action key | 7143ad6b-64ca-5ba1-945b-12cda412c2f6 |
| Inbox | 87e6325b-6c96-4332-bdc9-fd5fb0cd376e |
| Provider / model | ollama / llama3.2:3b (one durable `model_intent` reservation) |

| Event | UTC on 2026-11-11 |
|---|---|
| Durable incident received | 09:22:03.633157 |
| Model intent reserved | 09:22:04.807497 |
| Real diagnosis persisted (DIAGNOSED) | 09:22:34.161475 |
| Operator grant persisted | 09:22:36.708225 |
| Authorized application resume recorded (`resumed`, success) | 09:22:38.386222 |
| Inbox delivery | 09:22:38.423006 |
| First healthy verification sample | 09:22:40.520817 |
| RESOLVED after six healthy samples ≥5 s apart | 09:22:45.920611 |

The alert was observed **100.719 s** monotonic after the assignment request, with the inbox empty throughout the pause. The model returned `PAUSED_DELIVERY`, `resume_notification_worker`, risk `low`, confidence `0.8`, `escalate=false`, all four evidence references, and an explanation that restated the observed evidence. The deterministic policy, the operator grant, the scoped bearer, the application execution guard, the resume result, the delivered outbox row, the single correct-recipient inbox row and the healthy queue/heartbeat samples were all verified independently of the model text. Exactly one `worker_resume_actions` row exists for the incident. The one-off container used 57.55 MiB / 192 MiB. A correlated real web/worker trace was retrieved for the outbox event.

The first live attempt (`artifacts/t11-real-01574d2b862e4eb9bbdde0348d76abb2/`) failed for a harness reason only: the one-off container inherited a shell without the synthetic project's `POSTGRES_DB`/subnet variables and connected to the wrong database name. That incident (`c74d60f0-…`) made no model call and escalated as `unsupported_or_resolved_alert` after the test's cleanup resume resolved the alert. Both live tests now build the Compose environment explicitly and fail fast on startup errors.

### Model quality

Pre-flight calls through the production adapter with synthetic snapshots (`artifacts/claude/preflight-probe-1…7.json`) show that llama3.2:3b diagnoses the genuine paused-delivery evidence correctly once the prompt carries the runbook meaning of each field, but mislabels counterfactual dead-worker and database-down evidence as `PAUSED_DELIVERY`, and once restated a true value as false in its explanation. **The deterministic policy denied every counterfactual.** The model is advisory; `policy()` and the application's `execution_guard` are the controls, exactly as the architecture requires. Reviewers should not read the explanation text as evidence of correctness.

## Findings

| Severity | Finding and reproduction | Correction and verification |
|---|---|---|
| HIGH | After the model call, `Processor.process` re-evaluated `policy()` on the pre-model snapshot with `paused_evidence`'s 15-second freshness rule measured at evaluation time. Any provider slower than 15 s, including the only approved local provider, was always escalated as `diagnosis_policy_denied`. Reproduced by pre-flight probes 3–5 (`policy_would_permit: false` after a 17–20 s call). | `paused_evidence`/`policy` take an `at` anchor; the diagnosis stage anchors it to the capture time so bounded model latency cannot stale fresh evidence, while action time still re-captures fresh evidence with the default anchor. Tests `test_policy_freshness_is_anchored_to_capture_time_not_model_latency` and `test_bounded_model_latency_over_15s_does_not_deny_fresh_diagnosis`. |
| MEDIUM | The durable provider budget (`model_intent`) was reserved before the read-only evidence pre-check. A dead worker, expired pause or drained queue escalated without any model call yet consumed the single configured call for the whole deployment. | `Processor.reserve` runs after `paused_evidence` passes and still commits before the model call; interrupted attempts and exhausted budgets keep their escalation reasons. Test `test_rejected_precheck_never_consumes_the_durable_model_budget`. |
| MEDIUM | The 20 s request timeout was a hard-coded constant and timeouts/HTTP failures collapsed into `provider_failed`, losing the audit distinction. | Bounded setting `FIELDOPS_ONCALL_PROVIDER_TIMEOUT` (5–30 s, default 20, always inside the 45 s stage lease); typed `provider_timeout`/`provider_http_failure`; escalation events record the typed code only. Tests in `tests/test_t11_audit.py`. |
| MEDIUM | The system prompt gave the model no meaning for the evidence fields; the first real call labelled the paused gate `DATABASE_UNAVAILABLE` with confidence 0.5 (probe 2). | The prompt now states the operational meaning of each field, the category/action rules and the operator-authorization requirement; `Diagnosis` orders `explanation` before `category` so the model restates evidence before deciding. The prompt still contains no URLs, shell, SQL or tool language and policy remains independent. |
| LOW | `agent_tests/test_live.py` and the new real-model test launched `docker compose run` with the inherited shell, so a shell without the synthetic project variables pointed the agent at the wrong database. | Both tests set `COMPOSE_PROJECT_NAME`, `POSTGRES_DB` and the port/subnet defaults explicitly and assert the runtime logged no failure within its first seconds. |
| INFO | Worst-case stage latency: a snapshot can issue up to fifteen 3 s HTTP calls, plus a 30 s model call, exceeding the 45 s lease in theory. The web execution guard checks `ACTION_IN_PROGRESS` under row lock but not the lease token. | Not changed; measured stage time was 29.4 s. Recorded as a known limitation for a slower host. |
| INFO | The legacy recovery bearer keeps T07's unconditional resume for unknown incident ids; the agent bearer cannot use it (`oncall_incident_required`). Any operator may revoke any grant. | By design; documented. |

No critical finding remains. All corrections are covered by regression tests and the live real-model run exercised the corrected code.

## Executed checks

```powershell
git status --short --branch
gh issue view 11 --repo chakirou18/final-project-AIzoomcamp-2026
.venv/Scripts/python.exe -m pytest tests -m "not integration and not container" -p no:cacheprovider --junitxml=artifacts/claude/t11-audit-unit.xml
.venv/Scripts/python.exe .../preflight_probe.py http://127.0.0.1:11435 llama3.2:3b 30 positive dead_worker database_down injected_logs
. ./artifacts/t10-env.ps1
$env:FIELDOPS_RUN_REAL_MODEL_TESTS='1'; $env:FIELDOPS_ONCALL_PROVIDER_APPROVED='true'
$env:FIELDOPS_ONCALL_PROVIDER_URL='http://host.docker.internal:11435'; $env:FIELDOPS_ONCALL_MODEL='llama3.2:3b'
$env:FIELDOPS_ONCALL_PROVIDER_TIMEOUT='30'; $env:FIELDOPS_ONCALL_MAX_CALLS='1'
.venv/Scripts/python.exe -m pytest agent_tests/test_real_model.py -v -s -p no:cacheprovider --junitxml=artifacts/t11-real-model-live.xml
powershell -NoProfile -File artifacts/claude/t11-audit-postgres.ps1 tests/test_t11.py tests/test_t11_audit_processing.py tests/test_t11_audit.py -m integration --junitxml=artifacts/claude/t11-audit-postgres.xml
powershell -NoProfile -File artifacts/claude/t11-audit-postgres.ps1 tests -m integration -k "not owned_cleanup_preserves_unrelated_marker_and_cleans_failed_scope" --junitxml=artifacts/claude/t11-audit-full-postgres.xml
.venv/Scripts/ruff.exe check . ; .venv/Scripts/ruff.exe format --check .
```

## Acceptance matrix

| Issue #11 criterion | Verification and evidence | Verdict |
|---|---|---|
| Actual Alertmanager event received and persisted | Live incident cfa129e9 received 100.719 s after the paused assignment | PASS |
| Real model diagnoses paused delivery | llama3.2:3b via Ollama, durable `model_intent`, DIAGNOSED with `PAUSED_DELIVERY` | PASS |
| Authorized resume succeeds | Operator grant, scoped bearer, execution guard, one `resumed` result | PASS |
| Specific affected outbox IDs and correct inbox rows | Affected `[d922fc79…]`, delivered, one inbox row for the expected recipient; 105-event PostgreSQL case retained | PASS |
| Healthy queue and heartbeat before resolution | Six healthy samples, ≥5 s apart, zero backlog, fresh worker, matching generation | PASS |
| Incident, action and verification persist | PostgreSQL incident, events, affected, grant, action rows; survived the test's process stop | PASS |
| Explanation-only/natural drain/auto-expiry cannot resolve | Policy, DB trigger and negative tests unchanged; counterfactual model outputs denied | PASS |
| Episode/key replay and process restart | Retained concurrent/replay/restart tests; real run used one key | PASS |
| Blocked diagnosis escalates | Provider failure codes, missing telemetry, budget exhaustion, pre-check escalation tests | PASS |
| Full-stack command starts agent and monitoring | `--profile observability --profile incident` stack running throughout; provider configuration documented | PASS (local) |
| Concurrent incidents, wrong generation, expired/revoked grant, ambiguous timeout, failed audit, malicious logs, dead worker, failed verification, >100 events | Retained Codex suites rerun on the corrected code (ledger below) | PASS |

## Security review

The agent role still reads only its own tables plus grants (`SELECT` on `incident_grants`, no `UPDATE` on `incident_actions`, no business-table access); the one-off real container had no published port, dropped capabilities, a read-only root and the scoped bearer only. The prompt carries operational aggregates only: no recipient, job, label, raw log or trace text; injected log instructions in probe 4–5 never reached the model and could not change the policy. The provider adapter sends a fixed model name to a configured endpoint with structured output, a 16 KiB request cap, a 32 KiB response cap and a bounded timeout; it cannot choose URLs, SQL, shell or tools. Secret scan (`scripts/ci/secret_scan.py`) found no credential-shaped strings in 130 tracked files. The two Ollama instances listened on loopback only.

## Verdict

**CONDITIONAL GO for T11 feature publication after owner review.** Every live Issue #11 criterion has real evidence, including a genuine model invocation with zero spend. Conditions: the owner confirms the local Ollama/llama3.2 provider as the approved existing provider (no purchase was made), the remaining suite ledger in [T11 validation](t11-validation.md) is reviewed, and the worker-stop/database-deletion cases stay excluded as before. Publication (commit, push, PR against `feature/t10-alerting`) remains unauthorized until the owner says so.
