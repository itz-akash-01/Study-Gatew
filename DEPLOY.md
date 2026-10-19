# Deploy guide (beginner friendly)

Do the steps in order. Never paste real keys into GitHub, chats or screenshots.

## 1. Run the tests locally
```
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest
```
You should see `57 passed`.

## 2. Create the Supabase project (free)
1. supabase.com → New project. Save the database password in a password manager.
2. SQL Editor → New query → paste all of `schema.sql` → Run.
3. Project Settings → API: note **Project URL**, **anon key**, **service_role key** (secret!).

## 3. Turn on Google sign-in
1. console.cloud.google.com → create a project → APIs & Services → OAuth consent screen (External) → fill basics.
2. Credentials → Create credentials → OAuth client ID → *Web application*.
   Authorized redirect URI: `https://YOUR-PROJECT-REF.supabase.co/auth/v1/callback`
3. Copy the Client ID and Client secret.
4. Supabase → Authentication → Providers → Google → enable → paste both → Save.
5. Supabase → Authentication → URL Configuration:
   - Site URL: `https://your-domain.com`
   - Redirect URLs: `https://your-domain.com/auth/callback` and `http://localhost:5000/auth/callback`

## 4. Local test
Copy `.env.example` to `.env`, fill it in, then (Mac/Linux) `set -a; source .env; set +a; python app.py`
and open `http://localhost:5000` (use `localhost`, not `127.0.0.1`).
Sign in with Google; your email in `ADMIN_EMAILS` becomes admin.

## 5. GitHub
```
git init && git add . && git status     # check: no .env, no private_data, no keys listed
git commit -m "Secure Study_Gateway"
```
Create an empty **private** repo on github.com, then run the two commands it shows (`git remote add ...`, `git push`).

## 6. Vercel
1. vercel.com → Add New → Project → import the repo. Framework: Other/Flask (auto-detected from `app.py`).
2. Settings → Environment Variables (Production): add every variable from `.env.example`
   with `APP_ENV=production`, `SITE_URL=https://your-domain.com`,.
3. Deploy. Add your domain under Settings → Domains, then make sure `SITE_URL` and the Supabase
   Redirect URLs match it exactly.

**Upload size:** PDFs from 1 MB to 20 MB are accepted. Vercel rejects requests above about 4.5 MB, so for the full range deploy the Flask app on Render/Railway/Fly (`gunicorn app:app`), or set `MAX_UPLOAD_MB=4` on Vercel.

## 7. Rate limiting storage
Create a free Redis at upstash.com, copy its `rediss://...` URL into `RATELIMIT_STORAGE_URI`, redeploy.
(The `redis` package is already in requirements.txt.)

## 8. Public vs private values
| Variable | Secret? |
|---|---|
| `SUPABASE_URL` | Not secret, but used only on the server here |
| `SUPABASE_ANON_KEY` | Low risk, server only here |
| `SUPABASE_SERVICE_ROLE_KEY`, `SECRET_KEY`, `RATELIMIT_STORAGE_URI` | **Secret.** Dashboard only |
| `SITE_URL`, `ADMIN_EMAILS`, limits | Not secret |

## 9. Manual checks on the live site (these were NOT automated)
- [ ] Sign in with Google works; Profile shows your name; Sign out works.
- [ ] As admin, upload a small PDF; it appears in the library; "Read PDF" opens it.
- [ ] Signed out in a private window: `/admin` redirects to sign-in; `/read/1` asks you to sign in.
- [ ] Second Google account: cannot open `/admin` (403) and does not see your tasks.
- [ ] Supabase → Storage: bucket `study-pdfs` shows **Private**.
- [ ] Add a task, reload: it persists. Delete a test account: its tasks disappear.
