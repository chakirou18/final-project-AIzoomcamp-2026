# T09 Docker restart readiness and data safety

Observed 2026-11-10, 15:55-16:04 UTC. Branch `feature/t09-observability`; published T08 HEAD remains `fcc5bf7090d248fb667b4e26169f3bf76f24b151`. Existing changes preserved. No engine/service restart, stop, process termination, resource deletion, branch modification, commit, push or T09 test execution occurred.

**Latest verdict: owner Windows restart completed outside this task; Docker recovered and T09 worker restoration is verified.** This task did not restart Docker Desktop. All 123 recovered source ZIP files matched SHA256; existing web/worker containers were started, with no healthy telemetry recreation or historical DB restore. Fresh 13/13 observability, 403 backend, four lifecycle and eighteen Chromium cases pass. Final database has 173 delivered events/173 inbox rows and no duplicates/missing inbox; heartbeat advanced through 21:03:29.439728Z. See [fresh recovery evidence](t09-validation.md#source-recovery-and-fresh-acceptance-2026-11-10-after-owner-windows-restart). Earlier inventory/hold decisions below are historical, not a current request to restart. No further restart is authorized or needed.

## Inventory

The Docker container-list API reports **44 running / 248 exited**, total 292 containers, across fifteen running projects. The daemon info endpoint reports **53 running / 239 stopped** for the same total. This nine-container discrepancy is an unresolved Docker state-accounting inconsistency, not evidence of nine additional identified workloads. No paused/restarting containers were listed. Use the per-container list below for identified workloads and retain the discrepancy during recovery verification.

Container names are `<project>-<service>-1`. All listed containers were running according to Docker's list; the T09 worker's cached running state remains unreliable. Full IDs, exact names, storage mappings, restart policies and resource limits are in ignored `artifacts/t09-restart-inventory.json`. The known hung T09 worker was deliberately excluded from inspection and statistics requests.

| Compose project | Containers | Services | PostgreSQL storage |
|---|---:|---|---|
| fieldops-t09 | 10 | web, worker, db, prometheus, grafana, loki, alloy, otel-collector, jaeger, alertmanager | Named volume |
| fieldops-t08-audit | 2 | browser-db, test-db | Both tmpfs |
| fieldops-t08-clean | 2 | browser-db, test-db | Both tmpfs |
| fieldops-t08 | 2 | browser-db, test-db | Both tmpfs |
| fieldops-t07-audit | 4 | web, worker, db, test-db | db named volume; test-db tmpfs |
| fieldops-t07 | 3 | web, worker, db | Named volume |
| fieldops-t05-audit | 4 | web, worker, db, test-db | db named volume; test-db tmpfs |
| fieldops-t05 | 3 | web, worker, db | Named volume |
| fieldops-t06-validation | 3 | web, worker, db | Named volume |
| fieldops-t04-audit | 2 | web, db | Named volume |
| fieldops-t04-validation | 2 | web, db | Named volume |
| fieldops-t03-review-app | 2 | web, db | Named volume |
| fieldops-t03-bootstrap | 2 | web, db | Named volume |
| fieldops | 2 | web, db | Named volume |
| mlops_course_project_6 | 1 | incident-ingestor | No PostgreSQL in this running project |

There are **43 identified running FieldOps containers** and **one identified unrelated running container**. All other FieldOps phases are historical stacks; none was stopped on the assumption that its owner no longer needs it.

All **eleven persistent FieldOps PostgreSQL instances** have `PGDATA=/var/lib/postgresql/data` covered by `<project>_postgres_data` local named volumes, with separate read-only credential-volume mounts. T09 specifically uses `fieldops-t09_postgres_data` and `fieldops-t09_db_credentials`. Their restart policy is `unless-stopped`. No PostgreSQL data directory among these eleven is backed only by a writable container layer.

Eight running test PostgreSQL instances have tmpfs at that same PGDATA path and restart policy `no`. The six T08 instances each have an explicit 512MiB tmpfs size; the older T07/T05 audit test instances have no explicit tmpfs size. Their contents must be treated as lost from live storage when containers/VM stop, with recovery requiring the backups. They must not be silently discarded or automatically repopulated as empty test databases in place of the saved state.

The volume API lists **125 existing named volumes**, including volumes belonging to stopped projects. None was removed or altered. T09 telemetry/log positions and data use named volumes; configuration files use read-only repository bind mounts. Volume names, local mountpoints and Compose ownership are recorded in the inventory. An ordinary Desktop restart should preserve named volumes, bind mounts and writable container layers; this is not a guarantee against engine reset, VM disk corruption or removal, none of which is authorized. Stopped containers were inventoried by name/state; their private writable layers were not audited or backed up individually.

The unrelated `mlops_course_project_6-incident-ingestor-1` has a read/write bind mount:

`C:\Users\chaki\MLOPS_COURSE_PROJECT_6\data` -> `/app/data`.

A filename/size-only listing found a SQLite database, predictions JSONL file, reports directory and a credential settings file. No contents or credentials were read. Host files persist across Docker restart; SQLite transaction/application shutdown behavior, in-memory ingestion buffers, upstream retry/replay and lossless restart are **NOT VERIFIED**. These unrelated files were not copied or modified. Its restart policy is `unless-stopped`. Owner coordination is required before interrupting ingestion.

## Logical backups

Protected Windows destination, **outside the Git repository**:

`C:\Users\chaki\FieldOps-backups\t09-pre-restart-20261110T155800Z`

Windows ACL inheritance is disabled; only `MATHUSALEM\chaki` and SYSTEM have FullControl. Files inherit those restrictions. This is access control, not a claim of encrypted storage. Dumps and manifest were never staged, printed, uploaded or placed in Git.

**Nineteen of nineteen running FieldOps PostgreSQL clusters were backed up**, including all eight tmpfs clusters. Commands ran sequentially from `15:58:18.864793Z` through `15:59:44.896365Z`:

```text
pg_dumpall --no-role-passwords --quote-all-identifiers -U <existing cluster user>
```

Each dump was streamed directly to a host `.sql.gz` file. There was no temporary dump copy in a memory-constrained database container. The per-cluster stream deadline was ninety seconds. All nineteen commands exited zero with zero stderr bytes. The largest cluster completed in approximately 59.1 seconds. Logical backups take per-database consistent snapshots; the nineteen clusters do not share one atomic snapshot and writers were not paused.

| Protected data | Clusters | Non-template databases, including postgres |
|---|---:|---:|
| Persistent FieldOps clusters | 11 | 22 |
| Six T08 tmpfs clusters | 6 | 12 |
| T07 audit tmpfs cluster | 1 | 319 |
| T05 audit tmpfs cluster | 1 | 76 |
| Total | 19 | **429** |

The **407 volatile databases** occupy approximately **3,367,245,461 bytes** according to `pg_database_size`, excluding template databases/WAL/other cluster files. Logical dumps are small because sparse fixture databases have substantial physical catalog overhead. All nineteen dump files together are **802,041 compressed bytes**, expanding to **13,015,688 bytes** of SQL. The dump also includes globals and template1 output; template databases are not counted among the 429 inventory entries.

Verification performed:

- Read every gzip stream to EOF, checking gzip CRC/trailer and strict UTF-8 decoding; checked cluster dump header and completion marker.
- Recorded SHA256 per file in the host `manifest.json`, then reread all files and matched all nineteen hashes.
- Matched all **429 enumerated database names** to actual database-connect sections in the dumps; **zero missing**.
- Confirmed role password clauses were excluded. Aggregate role queries found zero password-bearing roles other than each cluster's initial configured user; password hashes were never returned to the host report. Initial credentials remain in existing container configuration/credential volumes and must be supplied through existing secret handling when restoring.

Readability/coverage verification is **PASS**. A restore into another PostgreSQL instance is **NOT TESTED**; no database restore or new test stack was authorized or performed. `pg_dumpall` output includes role/database creation statements and must not be blindly applied over an initialized or live cluster. Restoration needs an explicitly approved destination and handling of pre-existing bootstrap roles/databases. Physical WAL/PITR, sessions/in-flight transactions, original pg_hba.conf/postgresql.conf and live filesystem state are not captured by a logical dump. Existing source/configuration/credential storage is retained separately, not copied into the dump directory.

These backups protect the observed snapshots, **not subsequent writes**. Before a no-data-loss restart, coordinate a brief write freeze and refresh any database whose state changed, especially tmpfs clusters. Keep the verified original backups; write refreshed backups to a new protected directory. Do not restore all historical tmpfs fixtures into RAM automatically: that would recreate the memory pressure. Agree whether their saved state should remain archived or be restored later into suitable persistent isolated storage. No such restore, storage conversion or test-data deletion has been performed.

Evidence: host `manifest.json`; ignored `artifacts/t09-restart-databases.json`, `t09-restart-backup-summary.json`, `t09-restart-backup-verification.json` and `t09-restart-role-safety.json`.

## Current resources and diagnostic limitations

Docker exposes twelve CPUs and **7,978,242,048 bytes RAM**. At `16:02:24Z`, VM available memory is **763,720KiB (about 746MiB)**; total swap is 2,097,152KiB and **free swap is zero**. Memory full-pressure avg10/avg60/avg300 is **8.10/6.20/2.61%**; CPU some-pressure is **10.19/7.76/3.95%**. This post-backup sample shows active memory pressure. C: free storage is **120,088,358,912 bytes**. It does not establish memory pressure as the cause of the earlier Docker lifecycle failure.

Docker per-container stats produced no usable first sample in 43 bounded requests with two-second IO deadlines. First-stage exception types were not retained by that diagnostic; second-stage KeyError records indicate missing samples. Aggregate zero placeholders were corrected to null, not reported as idle utilization. No failed stats endpoint was retried. Thus Docker stats-based per-container CPU percentages are **NOT VERIFIED**. Direct reads through five responsive containers provided cgroup memory instead:

| Container | Cgroup memory bytes | Cgroup swap bytes |
|---|---:|---:|
| fieldops-t09-web-1 | 86,138,880 | 299,008 |
| fieldops-t09-db-1 | 50,216,960 | 1,056,768 |
| fieldops-t07-audit-test-db-1 | **3,448,725,504** | **715,571,200** |
| fieldops-t05-audit-test-db-1 | **782,618,624** | **492,273,664** |
| fieldops-t09-grafana-1 | 344,653,824 | 29,642,752 |

These are cgroup usage snapshots, not process RSS. The two historical audit databases account for approximately **3.94GiB memory plus 1.12GiB swap**. Releasing that memory would require stopping those containers, which would erase their live tmpfs state. Verified backups now exist, but no stop/cleanup or change to their restart policy is authorized or performed. After approval, prefer keeping unused historical test stacks inactive and preserving their backups over recreating all stacks. Do not increase resource limits or alter WSL/Desktop settings automatically.

Evidence: `artifacts/t09-restart-resources.json` and `t09-restart-direct-memory.json`. The hung worker was not inspected again. Named-pipe diagnostics use per-request IO deadlines and cancel/close only their own client connection on timeout; **no process was force-killed**.

## Recommended procedure, pending explicit approval

1. Coordinate a maintenance window with the unrelated incident-ingestor workload; verify its checkpoint/replay policy or accept its explicit interruption risk. Confirm no other user is creating workloads after this inventory.
2. Quiesce FieldOps writers with an approved, bounded graceful process/service stop plan. Do not retry the known blocked T09 worker lifecycle API or force-kill anything. Confirm no active test harness is modifying the eight tmpfs clusters. Preserve every original backup and refresh changed logical snapshots to another protected directory.
3. Agree how the eight tmpfs clusters' 407 saved databases will be retained/restored after the restart. Do not treat empty auto-initialized test databases as recovery. Historical stacks should remain inactive unless needed and approved; preserve all named volumes, bind files and container configurations.
4. Use Docker Desktop's normal **Restart** operation. No factory reset, reset engine, clean/purge, prune, removal, `down -v`, WSL termination or forced process kill. If graceful restart itself hangs, stop and ask for separate owner guidance.
5. Validate engine response and container accounting, inspect persistent PostgreSQL mounts/readiness/data and confirm unrelated ingestor recovery. Recover only the existing T09 services; do not blindly start every retained project or create a duplicate stack.
6. Confirm advancing T09 worker heartbeat and one correctly persisted, duplicate-free synthetic delivery. Obtain/retain authorization before any database restoration. Observability tests remain a subsequent task; none was run during this preparation.

Docker restart remains a reasonable recovery option for the independently documented worker-specific lifecycle stall and inconsistent accounting; a restart is not guaranteed to fix the underlying defect. An immediate restart is **NO-GO** because unrelated ingestion has not been coordinated, writers were not frozen and live tmpfs state would require an agreed restoration/deferment plan. Backup preparation removes the earlier lack of host copies, but does not remove these operational prerequisites. Await explicit owner approval for the coordinated procedure; do not restart automatically.

## Commands and state preservation

Read-only inventory and resource API access plus logical-export exec commands were issued by ignored `artifacts/t09_restart_safety.py`. The helper deliberately filters container environment values to POSTGRES_DB, POSTGRES_USER and PGDATA; no full inspect/environment response is persisted. No credential values or database rows were printed. Backup contents reside only in the protected host directory.

```powershell
git branch --show-current
git status --short
.venv/Scripts/python.exe artifacts/t09_restart_safety.py
.venv/Scripts/python.exe artifacts/t09_restart_safety.py databases
.venv/Scripts/python.exe artifacts/t09_restart_safety.py backup C:\Users\chaki\FieldOps-backups\t09-pre-restart-20261110T155800Z
.venv/Scripts/python.exe artifacts/t09_restart_safety.py verify-backups
.venv/Scripts/python.exe artifacts/t09_restart_safety.py role-safety
.venv/Scripts/python.exe artifacts/t09_restart_safety.py resources
.venv/Scripts/python.exe artifacts/t09_restart_safety.py direct-memory
git diff --check
git status --short
```

The host backup directory was created with an owner/SYSTEM-only protected Windows ACL before exports. Docker named-pipe access and writes outside the workspace required approved sandbox escalation. This granted read/export/filesystem access only; it did not authorize restarting Desktop. No global cleanup or mutation of the retained containers/volumes was performed. Existing T09 test evidence and NO-GO status remain unchanged.

## Execution of conditional safety authorization (2026-11-10, 17:46-18:04 UTC)

The latest owner authorization permits one graceful Desktop restart **only after all safety checks pass**, and specifically requires STOP if unrelated workloads cannot safely be interrupted. The restart allowance remains unused. Docker's normal `docker desktop restart --timeout <seconds>` command is available; only its help was executed. No restart command, forced termination, factory reset, prune, database/volume deletion or Git branch mutation occurred.

### Verified backups and isolated restoration

Original nineteen host archives passed SHA256 and database-section verification again. A database-only section from the original T09 cluster archive was restored with `psql --single-transaction -v ON_ERROR_STOP=1` into the **new** database `fieldops_t09_restore_probe_20261110175220_test` in the responsive persistent T09 PostgreSQL instance. Cluster-level CREATE/ALTER DATABASE and reconnect commands were excluded from the restore payload; it could not target an existing application database. No database was overwritten or dropped. The restore probe and its restricted temporary SQL file were retained.

Actual restored state: **11 public tables**, Alembic **0003_t07_controls**, **134 outbox rows**, **134 inbox rows**, **zero duplicate mappings** and **one matching notification** for the existing Grafana trace event. Restore exited zero, stderr zero. This is actual restoration evidence for the T09 database section, not a restoration of every database/global setting or a simulated archive-read test. The remaining 428 original database instances were not individually restored.

Refreshed all nineteen running PostgreSQL cluster archives conservatively, rather than assuming databases had not changed. The new protected directory is:

`C:\Users\chaki\FieldOps-backups\t09-final-safety-20261110T175300Z`

Owner/SYSTEM-only protected ACL was set before writing. Dumps span `17:54:02.623141Z` to `17:55:12.367208Z`; all commands exited zero with zero stderr. The refreshed inventory covers **430 non-template databases**: the original 429 plus the retained restore probe. All nineteen gzip integrity/readability/completion checks, all SHA256 rereads and all 430 database-section comparisons pass. The **407 volatile databases** remain covered and running; none was stopped or erased. At `17:56:22Z` and again `17:57:47Z`, all eight tmpfs clusters had **zero other connected clients**. Original backups remain intact in the earlier directory.

The same protected directory contains a consistent SQLite backup made through the unrelated ingestor's read-only connection; host reread `PRAGMA quick_check` returns **ok**, with **two incidents and two decisions**. A verified ZIP of **123 tracked/nonignored untracked source files** and a SHA256 source manifest preserve the pre-shutdown FieldOps work. These files are outside Git. No credential file was copied or printed; database/application data remains restricted host backup material.

### Unrelated workload and graceful stop blocker

The unrelated running workload remains `mlops_course_project_6-incident-ingestor-1`. Read-only checks showed:

- Running `monitoring/incident_ingestor.py` and `review/store.py` hashes match host source; no unrelated code was modified.
- Original SQLite quick_check **ok**, DELETE journal mode; two incidents, two decisions, one stream record.
- Last persisted stream observation `2026-10-19T15:29:01.499503Z`; summary evaluated at `2026-10-19T15:24:27.556619Z`; its Prometheus request returns URLError. No current incoming signal was established.
- Host bind storage persists outside Docker and now also has the verified logical SQLite backup. These checks support persisted-data safety but do not by themselves prove process shutdown.

At `17:57:49.521710Z`, the approved writer-quiescence sequence first requested a normal stop for that ingestor with **`t=-1`**, so no automatic SIGKILL escalation was enabled. The client IO deadline was twelve seconds. The stop request **timed out**; only client IO was cancelled. The sequence stopped before issuing any FieldOps writer stop. Runtime logs show the stop request and `stopping restart-manager`, but the inspected range did not contain a matching task-delete/shim-disconnect event for this shutdown. No second stop request was sent.

A bounded read-only signal check showed PID 1 is Python, has a registered SIGINT handler and no registered SIGTERM handler. The first signal-readiness helper printed and saved those valid results, then raised a local NameError from a misplaced helper block; the ignored helper's block placement was corrected without changing any application code or issuing another stop. Absence of a SIGTERM handler is a relevant shutdown limitation; it does **not** prove the cause of the separate T09 worker/Docker lifecycle stall.

At `18:02:36.862696Z`, a single supported **SIGINT / Python KeyboardInterrupt** was requested through an exec child, after checking the handler and backup. This is a graceful interrupt, not SIGKILL or forced Docker process termination. The request completed, but immediate Docker state still reported running. A separate deterministic `wait?condition=not-running` at `18:03:36.195008Z` **timed out after eight seconds**. No additional signal, wait retry or lifecycle probe was issued afterward. The unrelated service's actual shutdown/restoration is **NOT VERIFIED**; cached running state alone cannot prove it is healthy or stopped. The earlier graceful stop request may remain pending inside Docker even though the client has disconnected.

Because unrelated workload shutdown could not be confirmed, the conditional restart safety gate remains **BLOCKED**. There were **zero Docker Desktop restart attempts**, no remaining FieldOps writer shutdowns, no post-restart recovery, no T09 acceptance invocation and no publication. No essential data loss was observed; the new host backups protect the recorded snapshots, not later writes. The database/volume preservation and restoration limits above still apply.

### Latest safety matrix

| Safety requirement | Actual result |
|---|---|
| Existing backups present/integrity | PASS: nineteen original archives verified |
| Refresh changed data | PASS: all nineteen conservatively refreshed, 430 databases covered |
| Refreshed integrity | PASS: gzip/readability/completion/hash/database-section checks |
| Small isolated restore | PASS: real T09 schema/data restoration into retained new database |
| Identify active unrelated workloads | PASS: ingestor identified; read-only source/data/upstream checks |
| Confirm safe unrelated shutdown | BLOCKED: graceful stop and one subsequent graceful interrupt did not establish stopped state |
| Identify/protect tmpfs data | PASS for snapshots: eight clusters / 407 databases; no other clients in two pre-stop samples |
| Essential persisted data protected | PASS for recorded snapshots; no blanket claim about subsequent activity/in-memory state |
| Preserve FieldOps source/Git state | PASS: 123-file verified host ZIP; branch/HEAD/worktree retained |
| Perform one graceful Desktop restart | NOT EXECUTED: conditional shutdown prerequisite blocked |
| Post-restart worker/data/service recovery | NOT TESTED: no restart |
| All thirteen T09 checks / publication | NOT EXECUTED: recovery prerequisite blocked |

Evidence lives in ignored `artifacts/t09-restart-isolated-restore.json`, `t09-restart-backup-verification.json`, `t09-restart-unrelated-safety.json`, `t09-restart-unrelated-backup.json`, `t09-restart-final-activity.json`, `t09-restart-quiescence.json`, `t09-restart-ingestor-signal-readiness.json`, `t09-restart-ingestor-interrupt.json` and `t09-restart-ingestor-wait.json`. The full pre-stop container inventory is included in `t09-restart-quiescence.json`; old manifests and original archives remain preserved.

Next action is for the unrelated workload's operator to establish and confirm a graceful quiescent state, or for the owner to explicitly revise the shutdown condition with an accepted interruption plan. Do not interpret the existing conditional restart permission as a waiver. Do not retry the pending stop, force-kill, modify the unrelated application or spend the single restart allowance while this prerequisite remains unverified. T09 remains PARTIAL / NO-GO.

## Read-only ingestor diagnosis (2026-11-10, 18:12-18:18 UTC)

The owner requested diagnosis only and explicitly prohibited another SIGINT, process termination, Docker restart, data/volume deletion, branch changes and T09 tests. All checks in this follow-up were read-only. No new lifecycle request, signal, restart or test invocation was made. Git branch/HEAD and T09 source were preserved.

### Process state: STOPPED by runtime evidence, Docker metadata inconsistent

Exact container: `mlops_course_project_6-incident-ingestor-1`, Compose project `mlops_course_project_6`, container ID `398f6d9f4c46e241f7aab265300e4b85b1887c2d71a2b2e8d8d6c576324df3d4`.

The list API still reports running/Up seventeen hours. One state inspection timed out at its four-second deadline; a separate live-process/storage exec probe also timed out. Neither was retried. Cached Docker status is therefore not trusted as proof of a running Python process. The new positive evidence is in the host Docker VM runtime log for that exact container:

| UTC | Runtime record |
|---|---|
| 18:02:37.951894989 | Received task-delete event from containerd |
| 18:02:37.979250038 | Container shim disconnected |
| 18:02:37.992534282 | Cleaning up after shim disconnected |
| 18:02:37.992599656 | Cleaning up dead shim |

These events occurred about one second after the previously authorized SIGINT request, not in response to a new signal. Container task deletion followed by its shim disconnection/cleanup supports **STOPPED** process state despite unreconciled Docker running metadata. The inspected later runtime records contain no subsequent startup for the container. The earlier bounded wait failed to observe a coherent Docker terminal state; it is not proof that the Python process survived. Engine bookkeeping remains unhealthy and is not declared repaired.

The current PID/CPU/IO/open-file probes are **NOT VERIFIED**, since their live exec could not complete. No process inspection debugger or signal-based stack dump was used. Process-local memory or historical Python stack contents were not recovered. This runtime exit evidence, rather than an assumption that stale SQLite means an idle live process, clears the ingestor-specific interruption question.

### New writes, pending work and storage safety

Read-only host SQLite checks at **18:16:24.041697Z** and **18:17:51.073773Z**, separated by **87.032076 seconds**, both returned:

- `PRAGMA quick_check`: **ok**; journal mode DELETE; 45,056-byte database.
- Two incidents, two decisions, one incident_stream record. Full row contents were hashed locally and never printed; logical hashes for all three tables match the protected verified SQLite backup exactly.
- Live file SHA256/mtime/size unchanged between samples; no `-journal`, `-wal` or `-shm` files present.
- One historical active-stream flag, latest observation **2026-10-19T15:29:01.499503Z**. An active incident flag is not a queued processing job.
- Predictions JSONL metadata and summary metadata unchanged. Summary evaluated at **2026-10-19T15:24:27.556619Z**. Raw prediction/incident/credential values were not exposed.

The SQLite backup in `C:\Users\chaki\FieldOps-backups\t09-final-safety-20261110T175300Z\unrelated-ingestor-review.sqlite3` also passes quick_check and its recorded SHA256 still matches. Its raw file hash differs from the live file because it is a logical SQLite backup; equality was correctly checked through all three tables' logical contents, not assumed from file layout. The live database is on the Windows bind path `C:\Users\chaki\MLOPS_COURSE_PROJECT_6\data`, not tmpfs or an ephemeral Docker layer.

**No new committed data was observed** in the 87-second window, and the runtime task has exited. The source is a periodic poller with a thirty-second interval, no HTTP ingestion listener and no application-owned durable job queue. It reads a recent Evidently summary and a fixed Prometheus alerts endpoint, then persists incidents/stream markers in SQLite. Model calls are disabled (`model=None`). A normal engine restart cannot discard additional ingestor heap state after task deletion.

**Pending-work result:** no running process-local work remains. Whether an individual poll had transient uncommitted information at the original 18:02 interruption is **UNKNOWN**; it cannot be reconstructed from the exit event or database snapshot. No durable queue is represented as drained merely because row counts are unchanged. Possible lost observations of short-lived monitoring signals during downtime remain a historical coverage gap, not evidence of deleted committed incidents or a new volatile-data risk from restarting the already-exited ingestor.

### Dependencies and interruption impact

Docker labels identify **no Compose service depending on incident-ingestor**. Current project listing has its upstream Evidently, Prometheus, Iris and Grafana containers exited; the ingestor alone has stale running metadata. Source/configuration review agrees: ingestor depends on Evidently/Prometheus, not vice versa. No workload was started to check those dependencies.

The separately launched Windows review UI reads/writes the same SQLite file. It does not require a live ingestor to show saved incidents/decisions; it would lack new monitoring incidents while ingestion is down. A successful Windows listener enumeration found **neither documented review port 5050 nor upstream Prometheus port 9090 listening**. This does not prove that no application on another machine/port uses the files, but no active synchronous dependent was identified. The reviewed host source hashes match the earlier confirmed deployed hashes; no unrelated source/configuration was modified.

### Decision and remaining permission

**Ingestor-specific restart safety: GO**, with scope limited to the observed task exit and intact persisted data. There is no additional ingestor heap/queue left to protect before an engine restart. No owner waiver for interrupting a still-running ingestor is needed based on this evidence. Its monitoring remains unavailable until the engine is repaired and the service is deliberately restored; cached Up is not healthy ingestion.

**Whole-engine restart: not executed or globally approved by this diagnostic result.** The owner previously allowed one graceful restart after all safety gates, but the latest instruction explicitly says **do not restart Docker Desktop yet**. Obtain the owner's go-ahead to lift that current hold, then revalidate remaining FieldOps backup freshness, writer quiescence and the preservation/restoration plan for 407 tmpfs databases before using the existing single-restart allowance. Do not send another ingestor signal or change its code. T09 publication stays NO-GO until worker recovery and a completed thirteen-case observability run.

Commands/evidence:

```powershell
.venv/Scripts/python.exe artifacts/t09_ingestor_readonly.py first
.venv/Scripts/python.exe artifacts/t09_ingestor_readonly.py host first
.venv/Scripts/python.exe artifacts/t09_ingestor_readonly.py host second
.venv/Scripts/python.exe artifacts/t09_ingestor_readonly.py host-compare
```

The first live sample records its actual timeouts in `artifacts/t09-ingestor-readonly-first.json`. Host snapshots and sanitized per-container runtime exit records are in `artifacts/t09-ingestor-host-first.json` and `t09-ingestor-host-second.json`; exact 87-second comparison and backup checks are in `t09-ingestor-host-comparison.json`. Windows listener metadata and source/Compose review were read-only. Diagnostic access outside the workspace/sandbox used approved escalation; no credential file or row contents were printed. Only FieldOps evidence/authorization documents and ignored local diagnostics changed in this follow-up.
