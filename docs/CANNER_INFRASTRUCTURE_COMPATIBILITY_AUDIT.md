# Canner infrastructure compatibility audit (jds-branded-ordering)

**Date:** 2026-09-10 (America/Toronto)  
**Nature:** Documentation-only audit. No Canner account, no spend, no deploy, no PR #5 merge.  
**Inspected tip:** `m2.5/controlled-demo-launch` @ `ecb1636fcf637e296a6193d7c0019150e13d1f5d`  
**Base feature tip:** `feature-production-image-foundation` @ `a96df60` (M2 merged)  
**Primary sources:** https://canner.ca/ · https://canner.ca/pricing · https://canner.ca/llms.txt · https://canner.ca/docs/* · https://canner.ca/sovereignty · Supabase regions docs

---

## 1. Executive summary

Canner Live at **CA$9/month** can host the **application runtime** we care about for a controlled pilot: always-on FastAPI + Vite SPA + managed Postgres + HTTPS, on **Montreal, Quebec**, CAD billing, Canadian-owned operator.

It does **not** replace our **email/password Supabase Auth** without a major rewrite (Canner Auth is passkey-oriented, not a drop-in for `SupabaseIdentityProvider`). Media today only supports `local` | `supabase`; Canner’s S3-compatible object store is viable later but needs a **new adapter** (out of scope for this audit).

**Recommendation: B — Canner hybrid** for the next pilot spend decision:

| Layer | Host |
| --- | --- |
| Frontend (Vite SPA) | Canner Live project #1 |
| Backend (FastAPI) | Canner Live project #2 (uses Live’s 2 always-on slots) |
| App Postgres | Canner managed Postgres on the API project |
| Auth + email verify | **Keep Supabase Free**, region **Canada (Central) `ca-central-1`** |
| Media (pilot) | **Keep Supabase Storage** on that same Free project (existing adapter) **or** temporary `local` only if Canner documents durable app disk (not verified — prefer Supabase Storage) |

Approx. monthly: **CA$9 + tax** for Canner + **CA$0** Supabase Free ≈ **CA$10–11** in Quebec after GST/QST — typically **cheaper than** the ~US$13.25 / ~CA$18 Render+disk stack, with better Canadian residency for app+DB.

---

## 2. Repo / branch inspected

| Item | Value |
| --- | --- |
| Repo | `mjacquot82-svg/jds-branded-ordering` |
| Branch | `m2.5/controlled-demo-launch` |
| SHA | `ecb1636` |
| PR #5 | Open, **not merged** — audit compatible with PR #5 contents |
| Prior pilot package | `render.pilot.yaml`, `netlify.pilot.toml`, `docs/CONTROLLED_DEMO_PILOT_DEPLOYMENT.md` |

---

## 3. Canner — verified facts (current public docs)

| Topic | Finding | Source |
| --- | --- | --- |
| Ownership | Canadian-owned & operated; Montreal/Quebec; no US parent/affiliate claimed | canner.ca, /sovereignty |
| Data location | App code, env vars, Postgres on disks in Montreal; Cloudflare DNS/TLS issuance only (no US edge for app traffic claimed) | canner.ca, llms.txt |
| Billing | **CAD exclusively**; GST/QST by province | /pricing |
| Live price | **CA$9/mo** or **CA$99/yr** (new subs) | /pricing |
| Always-on | Live: **2** projects always-on; extras sleep after **3h** idle (~1–4s wake on Starter) | /pricing, homepage FAQ |
| App memory | Live: **2 GB** application memory (org pool) | /pricing |
| Storage pool | Live: **25 GB** pooled (apps + builds + DBs + Data Workshop + object storage) | /pricing, llms.txt |
| Bandwidth | Live: unlimited subject to AUP | /pricing |
| Postgres | Isolated DB per project; `DATABASE_URL` injected; PG 17/18; nightly backups; connectable externally | /docs/databases |
| Object storage | Private S3-compatible (MinIO); credentials work **from Canner runtime only**; keys prefixed by project slug | /docs/object-storage |
| Git/GitHub | GitHub App, CLI, drag-drop; Vite SPA + Python FastAPI documented | /docs |
| Env/secrets | Dashboard env vars; sensitive write-only; present at build+runtime | /docs/env-vars |
| HTTPS / domains | `.canner.app` HTTPS; custom domains + auto-TLS on **paid** plans | /docs |
| Scheduled jobs | Cron **webhooks** to your URL (retries/history) | /docs |
| WebSockets | Not highlighted as a first-class limit; app is HTTP API + SPA (fine for us) | — |
| Health checks | Python docs: health hits **`/`** by default — our API uses `/health/ready` (config/root route may be needed) | /docs/python |
| Canner Auth | Passkeys-as-a-service + JWT; **not** email/password Supabase replacement | /docs/passkeys, llms.txt |

---

## 4. Current application infrastructure map

| Dependency | Role today | Coupling |
| --- | --- | --- |
| **Netlify** | Vite SPA host; `/api` + `/health` proxy to API | Config only (`netlify*.toml`); not in app code |
| **Render** | FastAPI + migrate pre-deploy + optional disk | Config (`render*.yaml`); uvicorn `app.main:app` |
| **PostgreSQL** | All tenants, catalog, design, orders, demo tables | Hard requirement (`DATABASE_URL`) |
| **Supabase Auth** | Email/password register, verify, login for prospects/owners | **Hard** — `SupabaseIdentityProvider` in production path |
| **Supabase Storage** | Private tenant media when `JDS_MEDIA_STORAGE=supabase` | Adapter exists; production refuses local |
| **Local disk** | Dev/pilot media when not production | `LocalMediaStorage`; Render disk in pilot yaml |
| **Email** | Via Supabase Auth templates → `/build/verify` | No separate SES/Postmark today |
| **HTTPS** | Required for cookies/OAuth in real deploy | — |
| **Env secrets** | Auth pepper, Supabase keys, optional `CLOVER_*` | — |
| **Payment webhooks / OAuth** | Clover callbacks on **API** public URL (`PUBLIC_APP_URL`); M1 port ready for future providers | Needs stable HTTPS API hostname |
| **Frontend URL** | `FRONTEND_URL` / CORS / cookies | Must match SPA origin |

---

## 5. Can Canner replace Netlify?

| Concern | Assessment |
| --- | --- |
| Vite SPA build + SPA fallback | **Yes** — first-class (/docs/vite) |
| Deep links / React Router | **Yes** — SPA fallback documented |
| HTTPS | **Yes** on `.canner.app`; custom domain on Live |
| Same-origin `/api` proxy | **Not Netlify-style.** Two projects = two hosts unless we add a reverse proxy later. CORS + cookie `SameSite` must be set correctly (already required patterns in app). |
| CDN / edge | Canner origin in Montreal (no Cloudflare edge caching for app traffic) — fine for pilot scale |
| Cost | Netlify Free is **$0** and works; keeping it is not “worse,” but Canner SPA uses one of Live’s **2 always-on** slots and consolidates Canadian hosting |

**Verdict:** **PARTIAL → YES for hosting.** Prefer Canner SPA for Canadian-first pilot **if** spending Live anyway for the API. Keeping Netlify Free remains a valid $0 frontend if desired (hybrid still).

---

## 6. Can Canner replace Render API + Postgres + disk?

| Piece | Replace? | Notes |
| --- | --- | --- |
| Always-on API | **YES** | Live always-on; 2 GB RAM > Render Starter 512 MB |
| Postgres | **YES** | Managed, isolated, `DATABASE_URL`, nightly backups |
| Persistent disk (1 GB Render) | **PARTIAL** | No documented Render-style mount. Object storage is S3 from **in-cluster** runtime only — needs **new media adapter**. Until then keep Supabase Storage or carefully validate durable local paths (not assumed). |
| Pre-deploy migrate | **YES** | DB reachable at build; run Alembic in build/start |
| Logs / env | **YES** | Documented |
| Health path | **PARTIAL** | May need `/` → health or Canner health override |

**Verdict:** **YES for API+DB**; **PARTIAL for media disk** until S3 adapter or confirmed durable local volume.

---

## 7. Do we still need Supabase?

| Option | Pilot risk | Canadian posture |
| --- | --- | --- |
| **A. Keep Supabase Auth (+ Storage) Free, `ca-central-1`** | **Lowest** — no auth rewrite; email verify works | App+DB on Canner (QC); Auth/Storage on AWS Canada Central (Canadian region, **US-owned** operator — CLOUD Act risk differs from Canner) |
| **B. Replace Supabase with Canner Auth** | **High** — passkey model ≠ current email/password flows; rewrite + new tests | Fully Canadian |
| **C. Other Canadian IdP** | Unknown lead time | — |

**Immediate pilot:** **A**. Document Canadian-first roadmap: evaluate Canner Auth / Canadian email later **after** funnel proof — do not block pilot.

Supabase Free caveats remain: pause after ~1 week idle; 2 active projects; use **one** dedicated pilot project for Auth+Storage.

---

## 8. Media / Design Studio

Pilot quotas (25 products / 8 cats / 20 files / 25 MiB / 5 MB/file) fit easily in Live’s **25 GB** pool **or** Supabase Free **1 GB** storage.

**Security:** Keep existing server-side tenant paths + signed/private reads. Do not public-bucket Design Studio assets.

**Recommendation for pilot:** Supabase Storage on Free `ca-central-1` project (existing code path). Later: Canner object-storage adapter implementing `MediaStorage`.

---

## 9. Auth / email verification

| Concern | Hybrid answer |
| --- | --- |
| Who owns auth | Supabase Auth |
| Who sends verify email | Supabase (built-in) |
| Redirect | `https://<canner-spa>/build/verify` |
| Extra paid email | **Not required** for Free-tier volume |
| Canner Live alone | Does **not** give email/password verify without rewrite |

---

## 10. Payment architecture / webhooks

Canner HTTPS API project can expose:

- `/api/v1/clover/oauth/callback`
- Clover webhooks
- Future Square/Stripe/Moneris webhooks on same public API host

Set `PUBLIC_APP_URL` / `FRONTEND_URL` to Canner URLs. No infrastructure blocker identified. **Do not implement new providers in this milestone.**

Scheduled jobs on Canner can later hit internal drain URLs if needed.

---

## 11. Cost comparison (approx. CAD, before tax)

Assume ~1.37 CAD/USD for US list prices; confirm FX at purchase.

### OPTION A — Prior proposed pilot (Netlify + Render + Supabase)

| Service | Tier | ~CAD/mo |
| --- | --- | --- |
| Netlify | Free | 0 |
| Render Hobby workspace | Free | 0 |
| Render web Starter | US$7 | ~10 |
| Render disk 1 GB | US$0.25 | ~0.35 |
| Render Postgres Basic-256mb | US$6 | ~8 |
| Supabase Auth+Storage | Free | 0 |
| **Total** | | **~CA$18–19** |

Cold starts: none on paid Render. DB durable. US companies for compute/DB. Supabase Free pause risk if idle.

### OPTION B — Recommended: Canner Live hybrid + Supabase Free

| Service | Tier | ~CAD/mo |
| --- | --- | --- |
| Canner Live (SPA + API always-on) | CA$9 | **9** |
| Canner Postgres (on API project) | included in pool | 0 |
| Supabase Free Auth+Storage `ca-central-1` | Free | 0 |
| Netlify | not needed | 0 |
| Render | not needed | 0 |
| **Total** | | **~CA$9 + tax (~CA$10–11 QC)** |

Cold starts: **none** for the 2 Live always-on projects. Durable Postgres with nightly backups. Media via Supabase Free. Auth emails via Supabase.

### OPTION C — Keep Netlify Free + Canner API only

| Service | ~CAD/mo |
| --- | --- | --- |
| Netlify Free SPA | 0 |
| Canner Live (only 1 always-on used for API+DB; 2nd slot spare) | 9 |
| Supabase Free | 0 |
| **Total** | **~CA$9 + tax** |

Slightly more CORS/cookie complexity (split origins). Still good. Canadian compute/DB; US Netlify CDN for static (acceptable per “don’t make architecture worse for ideology” if preferred).

### OPTION D — All-in Canner including Auth

Not recommended for **immediate** pilot: requires auth rewrite to Canner Auth/passkeys or custom email stack → not “lowest risk.”

---

## 12. Scaling / longer term

| Scale | Hybrid Live outlook |
| --- | --- |
| 5 demo prospects | Comfortable |
| 25 demos | Comfortable if storage watched (25 GB pool) |
| 10 paying merchants | Likely OK; watch RAM/CPU; add performance block (CA$69) if needed |
| 50 paying merchants | Expect add-ons or Studio; first bottlenecks: **app memory / DB size in storage pool / Auth MAU if still on Free** |

**First bottleneck guess:** pooled **storage** (DB growth + media) or **API memory** under concurrent owner+storefront load — not Netlify credits.

**Lock-in:** Low. Postgres dump portable; FastAPI/Vite portable; media adapter boundary already exists; Auth is the stickiest (Supabase) until intentionally migrated.

Leaving Canner later is straightforward (standard containers/PaaS).

---

## 13. Canadian-first policy (adopted)

For **new** JDS infra: evaluate Canadian providers first when cost/reliability/capability are competitive. Do not harm security or ops; do not force-migrate existing Guest House/Ladel’s.

Canner Live hybrid beats Render on cost + Canadian compute/DB residency for this greenfield pilot.

---

## 14. Deployment caveats (no work done)

Before any future Canner deploy (after Marc approves):

1. Deploy **two** projects from monorepo: `frontend` root vs `backend/` (or CLI path scoping).
2. Confirm uvicorn module path `app.main:app` and `PORT`.
3. Align health check with `/` or platform setting.
4. CORS / cookie domains across SPA + API hosts (or later same-origin gateway).
5. Supabase redirect URLs → Canner SPA `/build/verify`.
6. Never copy Guest House/Ladel’s secrets or DBs.
7. `JDS_OUTBOUND_INTEGRATIONS_ENABLED=false` / payment review mode for demo prospects.
8. Invite code gate remains.

---

## 15. Final recommendation

### **B — USE CANNER HYBRID ARCHITECTURE**

**Why not A (all Canner):** Auth rewrite risk too high for pilot.  
**Why not C (keep Netlify/Render/Supabase paid Render):** Higher CAD cost; US compute/DB; weaker fit to Canadian-first for **new** pilot.  
**Why not D:** Canner **is** suitable for API+DB+SPA.

**Hybrid wins:** Canadian always-on app+DB at CA$9; keep battle-tested Supabase Auth/Storage Free in `ca-central-1` until funnel is proven; optional later move of media to Canner object storage and auth to a Canadian IdP.

---

## Terminal summary

```text
CANNER COMPATIBILITY AUDIT COMPLETE

Repo: jds-branded-ordering
Branch/SHA inspected: m2.5/controlled-demo-launch @ ecb1636
PR #5 compatibility: Compatible (docs-only; not merged)

Canner ownership/location: Canadian-owned; Montreal, QC
Canner Live current CAD price: CA$9/mo (or CA$99/yr)
Always awake: YES (2 projects on Live)
Postgres: YES (managed, DATABASE_URL)
Storage: YES (25 GB pooled on Live)
Object storage: YES (S3/MinIO, runtime-only credentials)
Git deployment: YES
HTTPS: YES
Custom domains: YES (paid)
Webhooks/OAuth: YES (HTTPS API + scheduled webhook jobs)
Secrets/env vars: YES

Can replace Render API: YES
Can replace Render Postgres: YES
Can replace Render disk/storage: PARTIAL (needs media adapter or keep Supabase Storage)
Can replace Netlify: YES (or keep Free Netlify — optional)
Can replace Supabase Auth: NO for pilot without rewrite (PARTIAL long-term via Canner Auth)

Recommended pilot architecture: Canner Live (Vite + FastAPI + Postgres) + Supabase Free Auth/Storage ca-central-1
Services required: Canner Live; Supabase Free project; optional custom domain later
Total monthly CAD cost: ~CA$9 + tax (~CA$10–11 QC); Supabase $0
Cold-start risk: Low (Live always-on for 2 projects)
Data-loss/expiry risk: Low for Canner Postgres (nightly backups); Supabase Free may pause if idle ~1 week
Security concerns: Split US-owned Auth (Canada region) vs Canadian app — acceptable interim; don’t weaken tenant/media isolation
Operational concerns: Two Canner projects + CORS; health check path; monorepo deploy paths

Suitable for Marc's personal test: YES
Suitable for 5–10 private prospects: YES
Suitable for Jen social-media test: YES (with invite gate / noindex)
Suitable for first paying merchants: YES with monitoring; plan add-ons before ~50

Expected first scaling bottleneck: Pooled storage or API memory
Vendor lock-in risk: Low (Postgres + portable app); Auth stickiest until migrated

FINAL RECOMMENDATION: B — USE CANNER HYBRID ARCHITECTURE
```
