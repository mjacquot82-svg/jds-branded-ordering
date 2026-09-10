# M2.5 Controlled Demo Launch — Implementation Report

**Date:** 2026-09-10 (America/Toronto)  
**Branch:** `m2.5/controlled-demo-launch`  
**Base:** `feature-production-image-foundation` @ `a96df600ac0b4078b62c3dc8780b47ab7b526352`  
**Production deploy:** none  
**PR merge:** not performed (open PR only)  
**Customer envs affected:** NO  
**Paid infra created by agent:** NO

---

## 1. Executive summary

M2.5 is launch-hardening for a **controlled pilot** of the M2 self-service demo funnel. It polishes Build Your Store Free landing + verification UX, tightens abuse limits for ~5–10 invitees, adds optional invite-code gating, wires prospect media quotas into upload paths (fail-closed), re-proves commerce lockouts with targeted tests, and ships a **non-deployed** dedicated pilot deployment package. No production deploy, no Guest House/Ladel's changes, no payment adapters, no automated C$150 billing, no public announcement.

**Success gate:** Marc is **not** yet ready for a personal end-to-end browser test on a controlled URL until he completes the pilot infra checklist (verdict **B**).

## 2. Starting-state verification

| Check | Result |
| --- | --- |
| Path | `/workspace/jds-branded-ordering` |
| Base SHA | `a96df600ac0b4078b62c3dc8780b47ab7b526352` (clean) |
| Branch | `m2.5/controlled-demo-launch` created from that SHA |
| M2 | Merged on foundation (Harbor & Hearth, commercial_mode, activation leads) |

## 3. Scope respected / non-goals

- No auto-merge; no production deploy  
- No Square/Stripe/Moneris; no new Clover features  
- No automated billing; ~C$150 + JDS 0% sales unchanged  
- No ads / broad exposure  
- No auth rewrite; no Design Studio/catalog/orders redesign; no SMS  
- No permanently free live ecommerce  
- No paid infra created without Marc approval  

## 4. Landing / CTA

`/build` copy now clearly states:

- **Build Your Store Free** primary CTA  
- Branded storefront: logo, colours, fonts, menu  
- Preview, save/return, **no credit card to build**  
- ~C$150/mo to go live; **JDS 0% of sales**  
- Real orders/payments locked until activation  
- No Clover headline  
- Harbor & Hearth spelling aligned with starter (was “Harbour” on landing)

## 5. Email / account UX

- Clearer verification_required payload with next steps  
- `/build/verify` route guides returning users to **I already started**  
- Resend verification API + UI button  
- Password length hint on signup  
- Explicit “one email = one demo workspace” guidance  
- Better error mapping (invite_required, account_exists, auth failed)  
- Existing IdentityProvider / session architecture unchanged  

## 6. Abuse protection (pilot)

| Control | M2.5 |
| --- | --- |
| Signup / IP | 5 / hour (was 8) |
| Signup / email | 3 / day (new) |
| Enter / IP | 15 / hour (was 20) |
| Tenant create / IP | 5 / day (new) |
| Upload / org (prospects) | 30 / hour (new) |
| Media quotas | **Now enforced on upload/create** (was imported but unwired — fixed) |
| Invite code | Optional `JDS_DEMO_INVITE_CODE` gate |
| CAPTCHA | Config hooks + Marc steps only; **no vendor keys required** |

## 7. Harbor & Hearth first impression

Only obvious fix: landing spelling Harbor. No storefront redesign. Starter remains fictional, not Guest House/Ladel's.

## 8. Admin prospect visibility + funnel events

Platform Admin shows prospects, recent funnel event names, activation leads, promote-to-live with preservation confirmation. Documented in `docs/CONTROLLED_DEMO_PILOT_DEPLOYMENT.md` (Marc usage section).

## 9. Controlled-pilot deployment package

New artifacts (docs/blueprints only — **not applied**):

- `docs/CONTROLLED_DEMO_PILOT_DEPLOYMENT.md`  
- `docs/DEMO_PILOT_CAPTCHA_CONFIG.md`  
- `render.pilot.yaml`  
- `netlify.pilot.toml`  
- `.env.example` pilot vars  

Target: dedicated Netlify + Render API + Postgres + media disk/bucket + Supabase Auth project. Isolated from customer envs.

## 10. Expected recurring cost (reported before spend)

| Item | Ballpark |
| --- | --- |
| Reusing free tiers | ~$0–20 USD/mo |
| New paid Render web + Postgres | ~$15–25 USD/mo |
| CAPTCHA | Usually free tier |

**Agent did not create paid resources.** Marc must approve cost before provisioning.

## 11. Test matrix (real results)

| Suite | Result |
| --- | --- |
| Backend full pytest | **386 passed**, 0 failed |
| `test_self_service_demo_funnel.py` | **20 passed** |
| `test_m25_controlled_demo_launch.py` | **10 passed** |
| Frontend `npm run test:frontend` | **397/397 pass** |
| `npm run build` | **pass** (~526ms) |

M2.5 coverage includes: invite gate, workspace reuse, commerce/payment fail-closed, media quota helper, pilot-config, Harbor starter identity, pricing 0% take, tightened signup limit.

## 12. Isolation / customer safety

- Customer envs affected: **NO**  
- Production deployed: **NO**  
- Guest House / Ladel's not modified  
- Prospect lockouts re-proven fail-closed  

## 13. Success gate answer

**No — not ready for Marc’s personal E2E on a controlled URL yet.**  
He needs the config/secrets/DNS (or dedicated pilot stack) steps in §14 first.

## 14. Exact Marc action checklist (verdict B)

1. Approve expected cost (~$0–25 USD/mo depending on free vs paid Render).  
2. Create dedicated Supabase Auth project (pilot only); set verification redirect to `https://<pilot>/build/verify`.  
3. Create dedicated Render Postgres + web from `render.pilot.yaml` (`autoDeploy: false`); set env vars from deployment doc + `.env.example` pilot section.  
4. Run migrations via pre-deploy; confirm `/health/ready`.  
5. Create dedicated Netlify site with `netlify.pilot.toml`; set API origin; deploy this branch manually.  
6. Set `JDS_DEMO_INVITE_CODE`; share only `https://<pilot>/build?invite=<code>` with 5–10 people.  
7. Bootstrap Marc platform grant on pilot; verify Platform Admin prospects/activations.  
8. Personal E2E: signup → verify → Design Studio → preview (checkout off) → activation request → admin visibility.  
9. Confirm Guest House / Ladel's URLs untouched; robots noindex.

Optional later: CAPTCHA keys per `docs/DEMO_PILOT_CAPTCHA_CONFIG.md`.

## 15. Stop reasons

- Deployment needs new paid infra / DNS / secrets / could confuse customer isolation → prepared package only, did not deploy (by design).  

## 16. Verdict

**B** — Code + docs + tests ready for controlled pilot; Marc must provision/configure isolated pilot URL before personal E2E browser test.

## 17. Terminal summary

```
Base SHA: a96df600ac0b4078b62c3dc8780b47ab7b526352
M2.5 branch: m2.5/controlled-demo-launch
Backend: 386 passed (incl. 20 M2 + 10 M2.5)
Frontend: 397/397 pass
Build: pass
Invite gate: optional JDS_DEMO_INVITE_CODE
Media quotas: wired on upload (fail closed)
Commerce lockout: re-proven
Deployment URL: none (Marc checklist)
Expected cost: ~$0–25 USD/mo (not spent)
Customer envs affected: NO
Production deployed: NO
Verdict: B
Merge: none (PR only)
```
