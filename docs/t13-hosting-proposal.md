# T13 hosting proposal and deployment approval request

Prepared 2026-11-12 for [Issue #13](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/13). **Nothing has been purchased, provisioned or exposed.** This document is the approval request; deployment starts only after the owner explicitly approves one option and a monthly spending ceiling in a later message.

## Requirement-driven sizing

| Component (one environment) | Measured memory | Configured cap | Source |
|---|---|---|---|
| Prometheus, Grafana, Loki, Alloy, OTel collector, Jaeger, Alertmanager | ≈ 648 MiB active aggregate | 2,432 MiB | T09 resource evidence (`artifacts/t09-resources-*/resources.json`) |
| web, worker, alert-receiver, oncall-agent | ≈ 80 + 65 + 70 + 57 MiB | agent 192, receiver 128, web/worker unbounded | T11 final integrity sample |
| PostgreSQL 17, Caddy edge | not separately measured; PostgreSQL idles at tens of MiB | proxy 128 | estimate, to be measured on the host |
| **Environment total** | **≈ 1.1–1.3 GiB** | ≈ 3.2 GiB | |
| Ollama + `llama3.2:3b` Q4_K_M (shared by both environments, private network only) | ≈ 2.5–3 GiB while loaded (2.0 GB weights + 4k context) | — | weights size from the local model; one CPU diagnosis took 20–29 s on 6 local Ryzen 5600H cores |

Issue #13 requires development and production side by side, with separate databases and volumes, plus a measured capacity check. The T11 acceptance relies on a real model. So the full target is two environments plus one private model runtime: roughly **6 GiB in practice, 8 GiB to respect the caps**, and **4 vCPU** so a diagnosis stays inside the 30 s provider timeout. The model must never be published: Ollama would run only on the host's private Compose network, reachable by the two `oncall-agent` containers.

## Verified prices (2026-11-12)

Azure figures come from the public Azure Retail Prices API (EUR, pay-as-you-go, Linux, 730 h; saved in `artifacts/claude/azure-retail-prices.json`). Hetzner figures come from hetzner.com plan pages (EUR, excluding VAT, IPv4 included).

| Option | Plan | vCPU / RAM / disk | Compute €/month | IPv4 | Disk | Total excl. VAT | Fits? |
|---|---|---|---:|---:|---:|---:|---|
| Azure A1 | B1s, West Europe | 1 / 1 GiB | 7.88 | 3.28 | S4 32 GiB 1.38 | ≈ 12.54 | No: too small for one environment |
| Azure A2 | B2ats_v2, West Europe | 2 / 1 GiB | 7.08 | 3.28 | 1.38 | ≈ 11.74 | No: 1 GiB |
| Azure A3 | B2als_v2, West Europe | 2 / 4 GiB | 28.32 | 3.28 | 1.38 | ≈ 32.98 | One environment, no model |
| Hetzner B0 | CPX02, Helsinki | 1 / 1 GB / 20 GB | 5.49 | incl. | incl. | 5.49 | No: too small |
| Hetzner B1 | CX23 (cost-optimized) | 2 / 4 GB / 40 GB | 5.99 | incl. | incl. | 5.99 | One environment, no model; **currently unavailable** |
| **Hetzner B2** | **CX33 (cost-optimized)** | **4 / 8 GB / 80 GB** | **8.99** | incl. | incl. | **8.99** | **Full target**; **currently unavailable** |
| Hetzner B3 | CPX22 (regular), Helsinki | 2 / 4 GB / 80 GB | 16.99 | incl. | incl. | 16.99 | One environment, no model; available |
| Hetzner B4 | CPX32 (regular), Helsinki | 4 / 8 GB / 160 GB | 30.49 | incl. | incl. | 30.49 | Full target; available |

Additional charges:

- **VAT** is added to Hetzner prices for EU consumers at the owner's country rate. For example, at 20% CX33 becomes ≈ €10.79.
- **Backups:** Hetzner backups start at €1.098/month per server, and snapshots cost €0.0143/GB-month. The release script's own `pg_dump` backups cost nothing extra.
- **Traffic:** Hetzner includes 20 TB in the EU, which is irrelevant at demo scale. Azure egress beyond the free allowance is billed, though demo traffic is negligible.
- **DNS:** a free IP-derived hostname service such as sslip.io works with Let's Encrypt but shares its rate limits. An owner domain costs a registrar fee, which I did not verify. Using a subdomain of a domain the owner already holds costs nothing.

Sources: [Azure Retail Prices API](https://prices.azure.com/api/retail/prices), [Hetzner cost-optimized](https://www.hetzner.com/cloud/cost-optimized), [Hetzner regular performance](https://www.hetzner.com/cloud/regular-performance).

## Assessment against the €5/month target

**The full required system cannot run within €5/month.** The only plan at or near €5 (CPX02, €5.49 excl. VAT) has 1 GB RAM, while one environment needs about 1.2 GiB in practice before the model.

Azure subscription credits might change this, for example the free-account allowance of a B1s for 12 months. However, they could not be checked: the cached Azure CLI token expired on 2026-11-12 after 90 days of inactivity, and a B1s is too small regardless.

**Option D, a hybrid**, would put the public application on a VPS and keep inference on the owner's laptop. It is rejected: it would need either exposing the local Ollama, which is forbidden, or an inbound tunnel to it. It would also make incident recovery depend on the laptop being online, so it does not meet the acceptance criteria reliably.

## Recommendation

1. **Preferred: Hetzner CX33**, 4 vCPU, 8 GB, 80 GB NVMe, IPv4 included, EU region. It costs €8.99/month excl. VAT, about €10.79 at 20% VAT, plus optionally about €1.10 for backups. It runs development and production as separate Compose projects and one private Ollama runtime. It is currently listed as unavailable, so it must be checked at order time.
2. **Available today: Hetzner CPX32 Helsinki**, same capacity, €30.49/month excl. VAT.
3. **Budget fallback (does not satisfy Issue #13 fully): Hetzner CX23**, €5.99 excl. VAT when available. It runs production only, with the model provider unconfigured: incidents escalate safely, but there is no real-model recovery in public. Development would stay local. This must be documented as partial acceptance.

Azure is the most expensive path for the same capacity, because of the separate public-IP and disk charges and higher compute prices for 4–8 GiB.

## Deployment approval request (Hetzner CX33; same procedure for CPX32)

| Item | Value |
|---|---|
| Provider / instance / region | Hetzner Cloud CX33 (fallback CPX32), Nuremberg or Helsinki |
| Monthly price | €8.99 excl. VAT (CPX32: €30.49 excl. VAT); ceiling requested from owner |
| Additional charges | VAT; optional backups from €1.098/month; snapshots €0.0143/GB-month; domain if purchased |
| Public IP | one IPv4 included; firewall allows only 22 (owner IP), 80, 443 |
| Hostnames | `fieldops.<owner-domain>` (production), `dev.fieldops.<owner-domain>` (development), or sslip.io equivalents |
| Security | Caddy TLS edge (HSTS, edge 404 for metrics/internal/demo/OpenAPI), all other services on loopback or private networks, Ollama private, SSH key-only, `check_exposure.sh` must pass, synthetic data only, secrets generated on host |
| Backups | `deploy.sh` takes a `pg_dump -Fc` before every migration; `verify_backup.sh` checks it; optional provider backups |
| Rollback | automatic redeploy of the previous digest on smoke failure; manual `rollback-production.yml` behind approval; no schema downgrade or restore |
| Risks | shared host for both environments (mitigated by distinct projects, volumes, networks and capacity check); CPU-only diagnosis latency near the 30 s timeout on shared vCPU (measured after provisioning, one budgeted call); Let's Encrypt rate limits on shared DNS services |

Deployment commands after approval:

```bash
# 1. host bootstrap (Docker Engine + Compose plugin, deploy user, firewall)
# 2. per environment
sudo install -d /srv/fieldops/{bin,development,production}
sudo install -m 0755 scripts/deploy/deploy.sh /srv/fieldops/bin/deploy.sh
git clone --branch main https://github.com/chakirou18/final-project-AIzoomcamp-2026 /srv/fieldops/<env>/repo
cp deploy/environments/<env>.env.example /srv/fieldops/<env>/.env   # edit hostnames; no secrets inside
# 3. first release is driven by GitHub Actions (main-release → development; promote-production → production)
# 4. verification on the host
scripts/deploy/check_exposure.sh && scripts/deploy/check_capacity.sh fieldops-development fieldops-production
python3 scripts/smoke/smoke.py --base-url https://<host> --environment <env> --output smoke.json
```
