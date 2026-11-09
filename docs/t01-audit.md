# T01 documentation audit

Publication authorization update (2026-11-09): owner approved T01 documentation commit/push on feature/t01-project-specification and public T01–T15 Issue creation after final Git validation. Separate manager/technician synthetic identities and authenticated/audited paused-loop recovery are decided. Historical "no publication authorization" and pending scenario/identity statements below describe earlier review states; [current readiness](t01-readiness.md) supersedes them. T02, deployment, paid infrastructure and API purchases remain unauthorized.

**Historical review record.** The original findings/validation below describe the prior audit and retain its then-current 19.5/20-hour estimate and NO-GO verdict for traceability. The final-correction addendum at the end and [T01 readiness summary](t01-readiness.md) supersede those estimates/readiness statements. They do not retroactively turn proposed behavior into passed runtime tests.

Review date: 2026-11-09. Scope: actual checkout documents, design consistency, supplied rubric mapping and public course source verification. This is a second-pass QA/architecture review by the current assistant, not evidence of a separate human or separately delegated reviewer. No application, deployment or runtime tests exist. PASS in this report refers only to the named documentation property, never implemented behavior or awarded course points.

## Executive summary

**Overall: PARTIAL. T02 recommendation: NO-GO pending owner review of this corrected baseline, seeded identity boundary and budget re-estimation plan.** There is no remaining identified critical design contradiction after corrections, but owner acceptance is not present. Once those gates are accepted, T02 foundation work is technically suitable to begin without waiting for hosting/model credentials. This audit does not authorize implementation.

Problem, users, transactional persistence and the core workflow are clear. The architecture connects server-rendered frontend, shared backend services and PostgreSQL; no broker, SPA or unnecessary business microservices are proposed. The full observability stack is operationally heavy: eleven Compose services plus a TLS proxy. Twenty hours is an unvalidated, high-risk budget, especially after this audit. No assurance of maximum course score is justified without the authenticated cohort rubric and implementation evidence.

## Findings ranked by severity

| ID | Severity | File / section | Evidence and impact | Correction / status |
| --- | --- | --- | --- | --- |
| C01 | Critical | architecture: Observability and incident flow; specification F08 | Original closure rule required delivery verification but did not explicitly require a successful recovery action. Natural drain or pause expiry could falsely count as agent recovery. | Corrected: resolved requires durable successful authorized action for matching generation plus verification; external recovery gets separate outcome. Runtime tests still required. |
| M01 | Major | rubric-evidence: Source discrepancy | Supplied 12/24 baseline differs from publicly documented draft 19/41; exact score bands and authenticated dashboard version absent. | Versions separated; names/weights verified only against supplied text. Dashboard confirmation remains open, owned by project owner. |
| M02 | Major | specification F06/F07 vs architecture outbox lifecycle | Dashboard used pending-only language while metrics included processing/failed events. Poison events could disappear from UI or produce inconsistent evidence. | Corrected to undelivered including all three states; F07 budget ends at authenticated receipt. |
| M03 | Major | architecture: outbox lifecycle | Five-failure retry limit did not explicitly bound repeated crash/lease-expiry claims. | Each claim consumes an attempt; expiry at fifth claim marks failed. Concurrency/crash tests added to drafts. |
| M04 | Major | architecture: incident flow/data model | Replay after closure, agent restart, action timeout and audit transaction boundaries were underspecified. | Unique alert episode, durable incident lease, atomic resume/result, bounded timeouts/retries and reconciliation specified. Not yet implemented. |
| M05 | Major | specification F01–F04; architecture API boundaries | Optional assignee on create, editability of terminal jobs, duplicate history and API JSON bodies were unclear; inbox JSON path conflicted with HTML path. | Creation/history/version semantics, allowed edits, timestamps, historical inbox access, JSON prefix/payload/error/pagination contracts added. Executable OpenAPI remains T03 work. |
| M06 | Major | specification F10 and assumptions | Signed seeded-persona sessions do not establish real identity; unrestricted operator selection would expose pause controls. | Demo identity limitation explicit; operator secret gate, cookie/session/CSRF requirements added. Owner approval of public-demo identity model remains open. |
| M07 | Major | architecture Component choices; backlog estimate | Eleven services + proxy, real model integration, deployment and robust tests in 20 hours has no measured basis. README called this implementation time while backlog included T01. | Budget wording aligned, base/profile plan added and actual-time re-estimation required. Resource/cost feasibility remains unverified. |
| M08 | Major | backlog T02/T03/T05/T10/T12 | T02 required seeded users before schema task; inbox UI preceded worker dependency; T10 required an agent receiver before T11; final CI omitted dependency on rules/agent. | Foundation scope split, worker dependency added, T10 explicitly uses test receiver, T12 depends on T08/T10/T11. Acyclic draft order verified separately. |
| M09 | Major | architecture telemetry; backlog quality | Tracing/SQL/log exports could capture free text/secrets despite broad omission statements; N03 benchmark lacked explicit task acceptance. | Field allowlist/retention/sentinel tests added; N03 benchmark assigned to T08. No real telemetry redaction evidence exists. |
| M10 | Major | architecture A03; specification F08 | Delivery pause does not terminate worker process; a killed-container requirement would not be satisfied by resume. | Scope now explicit and incident steps mapped below. Owner/course acceptance of blocked-worker variant remains open; no restart capability claimed. |
| m01 | Minor | README architecture diagram | Arrow suggested web pushes metrics to Prometheus. | Corrected to scrape direction. |
| m02 | Minor | architecture data model | Outbox referenced event_type/trace metadata without listing fields; incident lease/episode fields absent. | Fields explicitly added. |
| m03 | Minor | backlog and AGENTS context map | No ready-to-copy Issue bodies; context map lacked audit/draft links. | Local drafts added and linked; no remote Issues created. |
| m04 | Minor | backlog estimate | Arithmetic validation found listed tasks total 19.5 hours, not the asserted 20-hour total. | Corrected to 20-hour budget with 19.5 allocated and 0.5 unallocated contingency; actual audit effort still requires re-estimation. |

## Requirement-by-requirement assessment

PASS = documented clearly with concrete acceptance basis. PARTIAL = a material decision or executable proof is missing. FAIL = absent or contradictory and not corrected. All runtime acceptance results remain NOT RUN. No final score is asserted.

| Requirement | Documentation verdict | Supporting file / section | Remaining verification |
| --- | --- | --- | --- |
| Clear problem and users | PASS | README introduction and journeys; specification Users | User workflow demonstration after implementation |
| F01 create/list/view/edit | PASS | specification F01 + Contract clarifications; architecture Minimum JSON contract | Field boundaries, filters, pagination, restart persistence |
| F02 assignment | PASS | specification F02 + creation/no-op rules | Atomic creation/assignment, concurrent versions and role checks |
| F03 start/close/cancel | PASS | specification F03 + transition/timestamp rules | Full transition matrix and resolution tests |
| F04 priority/history | PASS | specification F04; architecture entities | Immutable audit and correct old/new changes/timestamps |
| F05 persistent inbox | PASS | specification F05 + historical scope; outbox lifecycle | Deduplication, read idempotency and crash tests |
| F06 dashboard | PASS | specification F06; architecture impact gauges | Fixture totals including failed/processing events |
| F07 impact alert | PASS | specification F07; architecture alert expression | promtool, no-data cases and actual receipt <=110s |
| F08 safe incident recovery | PARTIAL | specification F08 + closure clarification; architecture durable incident flow | Owner accepts pause variant; real successful action, delivery and negative tests |
| F09 API/health | PASS | architecture boundaries + Minimum JSON contract | Executable OpenAPI and real DB outage behavior |
| F10 roles/access | PARTIAL | specification Contract clarifications | Owner approves demo identity boundary; direct-route/session/CSRF tests |
| N01 transaction/retry reliability | PASS | specification N01; architecture lifecycle and fencing | Real PostgreSQL injected crashes/rollback, no SQLite substitution |
| N02 delivery time | PASS | specification N02; T06 draft | 20-event observed timing report |
| N03 performance | PASS | specification N03; T08 draft | Recorded host, dataset/concurrency and p95 |
| N04 security | PARTIAL | architecture boundaries/redaction; specification N04 | Permission/isolation/secret tests and approved identity model |
| N05 operability | PASS | architecture Observability and incident flow | Correlated evidence, no blocked assignment on telemetry failure |
| N06 reproducibility | PARTIAL | architecture profiles/seed; T02/T12/T13 drafts | Docker availability, runnable commands, hosted pipeline/demo |
| N07 usability | PASS | specification N07; T05/T08 drafts | Browser widths, keyboard and full-page fallback evidence |
| Frontend/backend/database connected | PASS | README diagram; architecture Component choices/lifecycle | Shared-service integration and browser persistence proof |
| API and persistence design | PASS | architecture data model + minimum JSON contract | Schema migrations/OpenAPI implementation deferred to T03 |
| Development roles and collaboration | PASS | agent-team role matrix/tracker/handoff | Real handoffs; no invented agent execution |
| Backlog/specification alignment | PASS | backlog corrected dependencies; drafts T01–T15 | Actual task acceptance/time tracking |
| Modular context links | PASS | AGENTS Context map; local link validation | Keep links accurate as implementation evolves |
| Cross-file consistency | PARTIAL | corrections above | Scope/identity/rubric/provider/host decisions still proposed |
| 20-hour feasibility | PARTIAL | backlog estimate; architecture A06 | Actual time, resource spike and revised remaining estimate |
| Production-like deployment/CI/CD | PARTIAL | architecture Deployment; T12/T13 drafts | Available host, secrets, HTTPS and exercised rollback/gates |
| Seeded reproducible demo | PASS | architecture local profiles/demo procedure | Repeated measured demo from clean seed |
| Supplied rubric mapping | PASS | rubric-evidence two tables | Every name/weight mapped; score-band evidence not supplied |
| Authenticated current rubric confirmation | FAIL | rubric-evidence Source discrepancy | Owner obtains dashboard version; do not infer missing criteria |

## Ten-step incident-response review

All steps below are design assessments only. **No incident has been executed.**

| Step | Design assessment | Required evidence/test |
| --- | --- | --- |
| 1 Assign intervention | PASS: versioned role-checked command | Assignment response and history |
| 2 Persist event | PASS: same transaction as assignment | Commit/rollback assertions and durable event ID |
| 3 Worker stops | PARTIAL: delivery loop pauses; process remains alive | Pause acknowledgement; separate dead-process escalation test; owner accepts variant |
| 4 Delivery latency grows | PASS: DB-derived undelivered age includes failed/processing | Event timestamp and metric samples while paused |
| 5 Monitoring alerts | PASS: threshold/for/scrape/group wait specified | Rule tests and actual receipt timestamps |
| 6 Agent receives | PASS: authenticated durable 202; DB failure 503 | Invalid-auth tests, replay and receipt persistence |
| 7 Inspect telemetry | PASS: bounded private queries and model deadline | Redacted telemetry snapshot/tool transcript |
| 8 Authorized remediation | PASS: guarded resume CAS with key/generation | Successful durable action, negative/replay/timeout tests |
| 9 Delivery resumes | PASS: poller materializes inbox rows | Specific affected event IDs mapped to inbox rows |
| 10 Verify and audit | PASS: action required, two fresh samples, 120s deadline | Persisted state progression, resolved audit and failure escalation |

Faults with no safe automated response—dead container, unreachable DB, missing telemetry, provider outage, exhausted notification retries and changed generation—must escalate. A successful explanation without action is never resolved. Natural recovery is recorded separately. Incident restart/replay and inability to persist audit must not create extra actions or success claims.

## Corrections applied and review scope

Updated README, AGENTS, specification, architecture, backlog and rubric evidence. agent-team.md was read in full and retained because its roles, authorization boundaries and handoff model were already consistent. Created this audit and local Issue drafts. All original content was inspected, including untracked planning files. No application files, dependencies, remote Issues, commits or pushes were created.

## Unresolved risks and gates

- **Owner, before T02:** accept reviewed baseline, seeded persona/privileged operator boundary and actual-time/re-estimation plan. No user acceptance has been recorded by this audit.
- **Owner, before maximum-score assurance / final scope freeze:** authenticated cohort dashboard confirmation of P01. Public FAQ was checked; authenticated dashboard was not. The supplied 12/24 names/weights are verified against conversation text only; no separate supplied rubric README exists in the checkout.
- **Owner + SRE, before T11:** accept blocked-delivery scenario, choose real model/provider and cap spend. CI mocks cannot substitute for successful real-provider action evidence.
- **Owner + SRE, before T13:** hosting resources/budget, HTTPS, private network exposure, demo access and rubric scope. No purchase or account action authorized.
- **Integration lead, each timebox:** measure actual effort; telemetry profile/resource spike and robust failure tests may exceed the 20-hour budget. No mandatory reliability evidence should be cut silently.

## Validation record

Exact inspection/validation commands and observed results are recorded below. Commands were run in PowerShell from the repository root, with login disabled. Initial terminal output using Get-Content without -Encoding UTF8 displayed mojibake for Unicode; explicit UTF8 reads were used for follow-up inspection. This was an output-decoding issue, not evidence that file contents were corrupted.

Initial command (exit 0):

```powershell
git status --short; Get-Content README.md; Get-Content AGENTS.md; Get-Content docs/specification.md; Get-Content docs/architecture.md; Get-Content docs/agent-team.md; Get-Content docs/backlog.md; Get-Content docs/rubric-evidence.md
```

Initial status: README modified; AGENTS.md and docs/ untracked. Combined tool output was truncated; follow-up commands read affected documents explicitly:

```powershell
Get-Content -Encoding UTF8 docs/architecture.md; Get-Content -Encoding UTF8 docs/agent-team.md; Get-Content -Encoding UTF8 docs/backlog.md
Get-Content -Encoding UTF8 docs/rubric-evidence.md; Get-Content -Encoding UTF8 docs/specification.md
```

Both exited 0. Public verification used web tool open on the official FAQ and course project page and find("41 points"); FAQ states a provisional 19-criterion/41-point rubric and 24-point pass threshold. No authenticated dashboard access occurred. Sources: [FAQ](https://datatalksclub.github.io/faq/ai-dev-tools-zoomcamp.html), [project page](https://datatalksclub.github.io/docs/courses/ai-dev-tools-zoomcamp/project/).

Final all-file inspection, local Markdown link scan, untracked-inclusive whitespace validation, DAG/arithmetic checks and git status/diff results are recorded after execution below. No application tests are run in this documentation-only phase.


Final inspection commands (all exit 0):

```powershell
Get-Content -Encoding UTF8 docs/github-issue-drafts.md; Get-Content -Encoding UTF8 docs/t01-audit.md
Get-Content -Encoding UTF8 README.md; Get-Content -Encoding UTF8 AGENTS.md; Get-Content -Encoding UTF8 docs/specification.md; Get-Content -Encoding UTF8 docs/rubric-evidence.md
Get-Content -Encoding UTF8 docs/architecture.md; Get-Content -Encoding UTF8 docs/backlog.md
```

Exact final repository checks (exit 0):

```powershell
git status --short; git diff --check; git diff --stat; git ls-files --others --exclude-standard
```

Observed: README.md modified; AGENTS.md and docs/ untracked. The untracked list contains AGENTS.md and seven docs: agent-team, architecture, backlog, github-issue-drafts, rubric-evidence, specification and t01-audit (eight untracked files total). `git diff --stat` covers tracked README only, not the untracked documents. `git diff --check` reports no whitespace errors; Git emits an LF-to-CRLF conversion warning for README, which is not a failed check. No unrelated files were reported.

Exact all-Markdown validation command (includes untracked files):

```powershell
$docFiles = @(Get-Item README.md, AGENTS.md) + @(Get-ChildItem docs -Filter *.md)
$docErrors = @()
foreach ($docFile in $docFiles) {
  $docText = Get-Content -LiteralPath $docFile.FullName -Encoding UTF8 -Raw
  foreach ($docMatch in [regex]::Matches($docText, '\]\(([^)]+)\)')) {
    $docTarget = $docMatch.Groups[1].Value
    if ($docTarget -notmatch '^https?://' -and -not (Test-Path -LiteralPath (Join-Path $docFile.DirectoryName $docTarget))) {
      $docErrors += "$($docFile.Name): broken link $docTarget"
    }
  }
  if ($docText -match '(?m)[\t ]+\r?$') { $docErrors += "$($docFile.Name): trailing whitespace" }
  if (([regex]::Matches($docText, '(?m)^```')).Count % 2) { $docErrors += "$($docFile.Name): unbalanced fences" }
  Write-Output "$($docFile.Name): inspected $($docText.Length) characters"
}
$taskOrder = @('T01','T02','T03','T04','T06','T05','T07','T08','T09','T10','T11','T12','T13','T14','T15')
$taskTotal = 0.0
$taskCount = 0
foreach ($taskLine in Get-Content docs/backlog.md -Encoding UTF8) {
  if ($taskLine -match '^\| [^|]* (T\d{2}) \|') {
    $taskId = $Matches[1]
    $taskCells = $taskLine.Split('|')
    $taskTotal += [double]::Parse($taskCells[3].Trim(), [cultureinfo]::InvariantCulture)
    $taskCount++
    foreach ($depMatch in [regex]::Matches($taskCells[4], 'T\d{2}')) {
      if ([array]::IndexOf($taskOrder, $depMatch.Value) -ge [array]::IndexOf($taskOrder, $taskId)) {
        $docErrors += "Invalid dependency $taskId -> $($depMatch.Value)"
      }
    }
  }
}
$scoreTotal = 0
$scoreCount = 0
foreach ($scoreLine in Get-Content docs/rubric-evidence.md -Encoding UTF8) {
  if ($scoreLine -match '^\| [^|]+ \| ([123]) \|') {
    $scoreTotal += [int]$Matches[1]
    $scoreCount++
  }
}
if ($taskCount -ne 15 -or $taskTotal -ne 19.5 -or $scoreCount -ne 12 -or $scoreTotal -ne 24) {
  $docErrors += "Arithmetic mismatch: tasks=$taskCount hours=$taskTotal criteria=$scoreCount points=$scoreTotal"
}
if ($docErrors.Count) { $docErrors; exit 1 }
Write-Output "PASS: $($docFiles.Count) Markdown files; local links, whitespace and fences valid; $taskCount tasks allocate $taskTotal hours; dependencies acyclic; $scoreCount criteria total $scoreTotal points."
```

Result: exit 0; nine Markdown files checked; all local file links resolve; no trailing whitespace or unmatched fences; 15 task rows allocate 19.5 hours with acyclic dependencies; 12 supplied criteria total 24 points. This simple link scan checks file targets, not rendered Mermaid, remote URL availability, or executable OpenAPI. An earlier one-line version of this scan expected 20 allocated hours and exited 1 with `Task or rubric arithmetic mismatch`; inspection found the real total was 19.5. The budget wording was corrected and the final check uses 19.5, preserving rather than hiding the allocation. Required runtime tests remain NOT RUN.

## Final T01 correction addendum — 2026-11-09

Current verdict: **GO for T02 documentation/design readiness, awaiting owner review and explicit implementation authorization.** No application development is started. The historical NO-GO budget/readiness statement above is superseded by this addendum and [final readiness summary](t01-readiness.md). Identity acceptance, deployment/model credentials, provider/spend decisions and authenticated rubric confirmation remain phase-specific gates. Readiness is not a runtime PASS or scoring guarantee.

| Requested correction | Documentation result / supporting sections | Unimplemented verification |
| --- | --- | --- |
| Supplied 3-point CI/CD criterion | PASS: architecture CI/CD contract, backlog/drafts T12–T13 and rubric mapping explicitly require automatic PR tests, automatic main→development CD, separate development DB and manual production dispatch + environment approval | Real PR/main/development/production runs, approval record, immutable digest identity, smoke/rollback and isolation tests |
| Exact trace correlation | PASS: architecture W3C inject/persist/extract remote-parent flow; specification N05; T09 same-trace acceptance test | Separate-process trace IDs/parentage, inbox row, web/worker logs, concurrent/retry isolation and no high-cardinality metric/stream labels |
| Single-command reproducibility | PASS as proposed design only: four identical README/architecture command contracts with profiles, DB/bootstrap readiness and isolated runners | Commands cannot run yet; actual Compose/Dockerfiles/tests do not exist |
| Time/resource estimate | PASS as explicit estimate: backlog 62 planned + 16 contingency = 78 remaining hours; low/high totals 58–117; historical T01 time unmeasured | Track actual time; measure CPU/RSS/disk at T09 and two-environment capacity at T13; no cost/resource claim is measured |
| Public Issue preparation | PASS: all 15 local drafts specify dependencies, acceptance, roles, tests and evidence; agent-team defines Codex reference/update/review/closure protocol | Owner authorization, real public URLs, actual implementation comments and artifacts; no remote Issues exist |
| Successful On-Call repair | PASS as contract: genuine absent inbox >60s, alert received, diagnosis, authorized action, affected-ID verification and durable incident/action audit; paused loop only | Complete real-provider repair plus replay/denial/failure tests. Explanation-only/natural recovery earns no repair credit |
| Rubric-version separation | PASS for supplied 12/24 mapping and separate provisional 19/41 flag; no extra criteria invented | Authenticated cohort dashboard remains unverified; exact supplied CI/CD band newly clarified, other score bands unavailable |

The former 20-hour target is deliberately superseded because the owner prioritizes coverage. Planned final regression work (T15) is distinct from contingency. Estimates include real PostgreSQL and browser testing, telemetry/Alertmanager, model recovery and development/production delivery. The public task tracker protocol does not grant current permission to publish. T09 verifies telemetry without the future real agent; T11 verifies complete-stack startup, preventing hidden dependency cycles. T12 provisions/configures only subsequently approved development targets and tests automatic CD; T13 exercises production promotion and rollback.

Public-source checks used official OpenTelemetry Python propagation and GitHub environment-protection documentation for the proposed context/approval mechanisms. Public FAQ was revisited; authenticated dashboard was not accessed. Links are in architecture and rubric evidence. No dependency, workflow, container, remote Issue, infrastructure purchase, commit or push was created.

Final validation commands/results follow after execution; all runtime acceptance remains NOT RUN.


### Final correction validation record

All inspections used UTF8 reads, including untracked Markdown. Original files were read using Get-Content in grouped calls; revised architecture, Issue drafts, backlog, team protocol, rubric mapping and readiness summary were reinspected. Search for stale budget/deployment/trace wording used:

```powershell
rg -n '20.hour|19\.5|single.host|one host|span link|manual|automatic|78|58.117|contingency' README.md AGENTS.md docs
```

The command exited 0. Old 19.5/20-hour arithmetic remains only as explicitly superseded history or comparison, not an active deadline. New commands match between README and architecture. Manual review confirms the new CI/CD sequence, same-trace parent contract and real-action-only closure requirements agree across the specification/backlog/drafts/rubric. Automated checks below validate structure, not runtime correctness.

Exact final validation command (PowerShell, repository root, exit 0):

```powershell
$ErrorActionPreference = 'Stop'
$docFiles = @(Get-Item README.md, AGENTS.md) + @(Get-ChildItem docs -Filter *.md)
$docProblems = @()
foreach ($docFile in $docFiles) {
  $docText = Get-Content -LiteralPath $docFile.FullName -Encoding UTF8 -Raw
  foreach ($linkMatch in [regex]::Matches($docText, '\]\(([^)]+)\)')) {
    $linkTarget = $linkMatch.Groups[1].Value
    if ($linkTarget -notmatch '^https?://' -and -not (Test-Path -LiteralPath (Join-Path $docFile.DirectoryName $linkTarget))) {
      $docProblems += "$($docFile.Name): broken link $linkTarget"
    }
  }
  if ($docText -match '(?m)[\t ]+\r?$') { $docProblems += "$($docFile.Name): trailing whitespace" }
  if (([regex]::Matches($docText, '(?m)^```')).Count % 2) { $docProblems += "$($docFile.Name): unbalanced fences" }
  Write-Output "$($docFile.Name): inspected $($docText.Length) characters"
}
$taskOrder = @('T01','T02','T03','T04','T06','T05','T07','T08','T09','T10','T11','T12','T13','T14','T15')
$backlogText = Get-Content docs/backlog.md -Encoding UTF8 -Raw
$taskGraph = @{}
$plannedHours = 0
foreach ($taskMatch in [regex]::Matches($backlogText, '(?m)^\| [^|]* (T\d{2}) \|[^|]+\| (\d+) \| ([^|]+)\|')) {
  $taskId = $taskMatch.Groups[1].Value
  $plannedHours += [int]$taskMatch.Groups[2].Value
  $taskGraph[$taskId] = @([regex]::Matches($taskMatch.Groups[3].Value, 'T\d{2}') | ForEach-Object { $_.Value })
  foreach ($taskDep in $taskGraph[$taskId]) {
    if (-not ($taskOrder -contains $taskDep) -or [array]::IndexOf($taskOrder, $taskDep) -ge [array]::IndexOf($taskOrder, $taskId)) {
      $docProblems += "Invalid dependency $taskId -> $taskDep"
    }
  }
}
$draftText = Get-Content docs/github-issue-drafts.md -Encoding UTF8 -Raw
$issueDrafts = [regex]::Matches($draftText, '(?ms)^## (T\d{2}) [^\r\n]+\r?\n(.*?)(?=^## |\z)')
foreach ($issueDraft in $issueDrafts) {
  $draftId = $issueDraft.Groups[1].Value
  $draftBody = $issueDraft.Groups[2].Value
  foreach ($draftField in @('Description','Dependencies','Role','Acceptance criteria','Tests required','Reviewer evidence')) {
    if ($draftBody -notmatch ([regex]::Escape("**" + $draftField + ":**") + '\s*\S')) {
      $docProblems += "$draftId missing field $draftField"
    }
  }
  $dependencyLine = [regex]::Match($draftBody, '\*\*Dependencies:\*\*([^\r\n]*?)(?=\s*\*\*Role:)').Groups[1].Value
  $draftDeps = @([regex]::Matches($dependencyLine, 'T\d{2}') | ForEach-Object { $_.Value })
  if (($draftDeps -join ',') -ne ($taskGraph[$draftId] -join ',')) { $docProblems += "$draftId dependency mismatch" }
}
$rangeRows = [regex]::Matches($backlogText, '(?m)^\| T\d{2} \| (\d+) \| (\d+) \| (\d+) \|')
$lowHours = 0; $likelyHours = 0; $highHours = 0
foreach ($rangeRow in $rangeRows) {
  $lowHours += [int]$rangeRow.Groups[1].Value
  $likelyHours += [int]$rangeRow.Groups[2].Value
  $highHours += [int]$rangeRow.Groups[3].Value
}
$rubricText = Get-Content docs/rubric-evidence.md -Encoding UTF8 -Raw
$rubricRows = [regex]::Matches($rubricText, '(?m)^\| [^|]+ \| ([123]) \|')
$rubricTotal = 0
foreach ($rubricRow in $rubricRows) { $rubricTotal += [int]$rubricRow.Groups[1].Value }
$commandPattern = [char]96 + '(docker compose[^' + [char]96 + ']+)' + [char]96
$readmeCommands = @([regex]::Matches((Get-Content README.md -Encoding UTF8 -Raw), $commandPattern) | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique)
$architectureCommands = @([regex]::Matches((Get-Content docs/architecture.md -Encoding UTF8 -Raw), $commandPattern) | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique)
if (($readmeCommands -join '|') -ne ($architectureCommands -join '|') -or $readmeCommands.Count -ne 4) { $docProblems += 'Proposed command mismatch' }
if ($taskGraph.Count -ne 15 -or $issueDrafts.Count -ne 15 -or $plannedHours -ne 62 -or $rangeRows.Count -ne 14 -or $lowHours -ne 46 -or $likelyHours -ne 62 -or $highHours -ne 93 -or $rubricRows.Count -ne 12 -or $rubricTotal -ne 24) {
  $docProblems += "Count/arithmetic mismatch: tasks=$($taskGraph.Count), drafts=$($issueDrafts.Count), planned=$plannedHours, ranges=$lowHours/$likelyHours/$highHours, criteria=$($rubricRows.Count), points=$rubricTotal"
}
if ($docProblems.Count) { $docProblems; exit 1 }
Write-Output 'PASS: 10 Markdown files; local links/whitespace/fences; 15 complete Issue drafts; matching acyclic dependencies; 4 matching proposed commands; 62 planned hours with 46/62/93 range; 12 criteria/24 points.'
Write-Output 'With rounded-up 25% contingency: 58/78/117 hours. Runtime acceptance: NOT RUN.'
```

Observed: **10 Markdown files** read, including all untracked documents; local links resolve; no trailing whitespace or unbalanced fences; **15 Issue drafts** contain all six required fields; draft dependencies match backlog and are acyclic; all **four proposed Compose commands** agree; **62 planned hours**, low/likely/high work totals **46/62/93**, and contingency totals **58/78/117** agree; **12 supplied criteria total 24 points**. Nonempty acceptance/test/evidence fields are structural checks; manual review supplies the semantic consistency assessment. No Compose, test, workflow, trace, deployment or incident command was executed.

Exact Git checks (exit 0):

```powershell
git status --short; git diff --check; git ls-files --others --exclude-standard
```

Status: modified README.md, untracked AGENTS.md and docs/. Untracked list: AGENTS.md plus agent-team.md, architecture.md, backlog.md, github-issue-drafts.md, rubric-evidence.md, specification.md, t01-audit.md and t01-readiness.md under docs/. git diff --check found no whitespace errors; Git emitted only its existing README LF-to-CRLF conversion warning. Since git diff excludes untracked files, the all-Markdown scan above separately checks their whitespace/links/fences. No other files were reported. Final checks are repeated after recording this addendum.
