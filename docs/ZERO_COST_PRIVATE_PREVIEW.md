# $0 private preview (Marc only)

Runs on Grok Bot's computer — no paid Netlify/Render/Supabase.

## How to open

1. Open this agent's computer (chat header name → computer preview / full screen).
2. In the box browser go to: `http://127.0.0.1:5173/build`
3. Create an account with any email (auto-verified locally; no real email sent).
4. Password ≥ 10 characters.
5. You should land in Design Studio on Harbor & Hearth.

## Platform admin (activation leads)

- URL: `http://127.0.0.1:5173/owner/login` (or admin login path used by the app)
- Email: `owner@local.jds.test`
- Password: `local-review-password`

## Limitations (expected)

- Not a public URL — only on this agent computer
- No real email verification
- Disposable Postgres: `jds_demo_preview_local_review`
- No Clover / real payments (locked for prospects)
- Data wiped when preview DB is dropped

## Stop / cleanup

Kill uvicorn + vite; `DROP DATABASE jds_demo_preview_local_review;`
