# Study_Gateway AI — Security audit and status

> No website is "100% secure". This document says what was found, what was changed, what was
> tested, and what is still your responsibility. Anything not listed under "Tested" was **not** tested.

## 1. What the original project was
Flask + SQLite + local PDF folder, one shared admin username/password, planner stored only in the
browser, profile page was a visual placeholder, AI Creator was UI-only. So there were **no student
accounts, no AI history and no server-side planner data** to protect yet. Ownership checks (IDOR
protection) were therefore built into the new account features rather than patched into old ones.

## 2. Findings in the original code
| # | Severity | Finding | Status |
|---|----------|---------|--------|
| 1 | High | SQLite file and PDFs on local disk: lost or inconsistent on Vercel (serverless disk is temporary) | Fixed: Supabase Postgres + private Storage |
| 2 | High | No CSRF protection on login, upload, delete, logout | Fixed (token + Origin check) |
| 3 | High | No rate limit on admin login (password guessing) | Fixed; admin password login removed entirely |
| 4 | Medium | Random `SECRET_KEY` fallback: logins break across server instances | Fixed: app refuses to start in production without one |
| 5 | Medium | Cookie flags not set, admin session never expired | Fixed: Secure, HttpOnly, SameSite=Lax, `__Host-` prefix, idle + absolute timeouts |
| 6 | Medium | One shared admin password: no individual accountability, no MFA | Fixed: admins are individual Google accounts (Google 2-step applies), role checked on the server every request |
| 7 | Medium | No CSP / HSTS / Permissions-Policy | Fixed |
| 8 | Medium | Upload saved before validation; only a 5-byte check | Fixed: validated in memory (signature, complete file, no scripts/embedded files), random storage name |
| 9 | Medium | PDFs readable by anyone, IDs guessable | Changed: sign-in required by default; files private; 60-second signed links |
| 10 | Low | No security logging; inline `onsubmit` handler blocks a strict CSP | Fixed |
| 11 | Low | `__pycache__` shipped in the ZIP | Fixed (.gitignore, removed) |
| — | None found | XSS (Jinja auto-escapes; JS uses `textContent`), SQL injection (all queries parameterised / ID-validated) | n/a |

## 3. Protections now in place
- **Google Sign-In** through Supabase Auth, server-side PKCE flow. Google passwords never reach this site. Tokens never reach the browser; Supabase's own session is revoked right after sign-in.
- **Email/password was deliberately not added**: it adds password storage, reset and enumeration risks you do not need. Google covers it.
- **Auth on every protected route** (`login_required` / `admin_required`), re-checked against the database each request, so deleted accounts, role changes and "sign out everywhere" take effect at once.
- **Ownership**: every planner query filters by `user_id` taken from the session *and* the record id; foreign or malformed ids return 404. IDs are validated as UUIDs before reaching the database.
- **Admin separation**: role stored in the database; only emails in `ADMIN_EMAILS` are promoted at sign-in; no endpoint can change a role; shorter admin sessions (2 h, 30 min idle).
- **Database**: RLS enabled on all tables, `anon`/`authenticated` roles have **no** privileges, only the server's service key can read/write. See limitation in section 6.
- **Files**: private bucket, no storage policies, 60-second signed links, strict path pattern, PDF-only, size cap, upload rate limit, library size cap.
- **Web**: CSRF tokens, Origin check, no CORS, HTTPS redirect + HSTS, CSP, rate limits (sign-in by IP, API by user), generic error pages, JSON security log without emails or tokens.
- **Account deletion**: `/account/delete` removes planner, profile and the Supabase login.

## 4. Tests (run `python -m pytest`)
**Result: 57 passed, 0 failed.** `pip-audit` on `requirements.txt`: no known vulnerabilities (date of run: Oct 18 2026; re-run before every deploy).

Covered: unauthenticated API/admin access, student A vs student B, mass-assignment (`user_id`/`role` in body), malicious ids, admin-only routes, role demotion, expired/idle/forged/tampered/revoked sessions, sign-out-everywhere, deleted-account cookies, PKCE failures and single-use codes, upload type/signature/size/script/filename cases, no public file paths, CSRF (missing/forged/valid), foreign Origin, no CORS, rate limits, security headers, production cookie flags/HSTS/redirect, error leakage, log content, and that the real database client always sends owner filters.

**Not tested (be honest with yourself about these):**
- A real Supabase project: the Google login round trip, RLS in real Postgres, Storage endpoints and the `add_focus` function were written from Supabase's documented API but **never run against a live project**. Do the manual checks in DEPLOY.md step 9.
- Vercel deployment itself, and how the Flask static files behave there.
- Visual check of the profile page and planner in a real browser (JS syntax was checked; behaviour with the server API was not).
- Load, penetration and malware-scanning tests. PDF checks are sanity checks, not antivirus.

## 5. Procedures
**Backups.** Supabase's free plan, as far as I know, has no automatic downloadable backups (check your plan). Monthly: Supabase → Database → Backups (if available) or `pg_dump "<connection string>" > backup.sql` from your computer, plus download the `study-pdfs` bucket. Keep copies **outside GitHub**, ideally encrypted. Test a restore once.
**Rotating secrets.** `SECRET_KEY`: put the new value in `SECRET_KEY`, the old in `SECRET_KEY_FALLBACKS`, redeploy, remove the fallback after 24 h. Supabase service key: Project Settings → API → regenerate, update Vercel, redeploy. If a secret was ever committed to GitHub, rotate it immediately (deleting the commit is not enough).
**Account deletion requests.** Students use Profile → Delete account. For manual cases: delete the user in Supabase → Authentication → Users (rows cascade). Admins must be demoted first (`update public.profiles set role='student' where email='...'`).
**Making/removing an admin.** Add/remove email in `ADMIN_EMAILS` (promotes at next sign-in); to demote, also run the SQL above.
**Reading logs.** Vercel → project → Logs; search `SECURITY`. Watch for `login_failed`, `admin_denied`, `rate_limited`, `csrf_failed`, `session_rejected`.

## 6. Remaining risks
1. **The server uses the Supabase service key**, which bypasses RLS. Your real protection today is the server-side owner filtering (tested) plus the fact that browsers get no database access at all. RLS policies are a safety net, not the main wall. If the service key leaks, everything is exposed: guard it.
2. **Rate limits need Redis in production.** With the default in-memory store each serverless instance counts separately, so limits are weak. Use a free Upstash Redis URL in `RATELIMIT_STORAGE_URI`.
3. **Vercel request size limit (about 4.5 MB)** blocks PDF uploads above that size. The site accepts 1–20 MB (`MIN_UPLOAD_MB`/`MAX_UPLOAD_MB`), so host Flask on Render/Railway/Fly (same code); on Vercel you must lower `MAX_UPLOAD_MB` to 4. Direct-to-storage signed uploads would remove the limit but are not built.
4. **Signed links** can be shared for up to 60 seconds, and a signed-in student can download then share the PDF. DRM is out of scope.
5. **Focus minutes** are reported by the browser; the server only caps each report (1–180 min, 30/hour). Treat as non-authoritative.
6. **PDF content checks are heuristic.** Only trusted admins upload, which is the real control.
7. **Admin MFA** depends on the admin's Google account having 2-Step Verification on. Turn it on.
8. **Google/Supabase/Vercel outages or account takeover** are outside this code.
9. **Not yet built:** AI Creator backend and AI history (table and RLS reserved; add owner-scoped routes the same way as tasks, and keep provider keys in env vars), ZIP upload handling (the server accepts no ZIPs; if you add them, extract nothing without path checks and size limits), email/password sign-in.
10. Dependencies need re-checking regularly (`pip-audit`, GitHub Dependabot is free).

## 7. Paid services
None required. Free tiers: Supabase, Vercel Hobby, Upstash Redis. Likely limits: Supabase pauses idle free projects and has small storage; Vercel Hobby is non-commercial; check current terms.
