# Study_Gateway AI

Liquid-glass study site: class-wise PDF library, study planner, focus timer, AI Creator (UI only).
Flask + Supabase (Google sign-in, Postgres, private file storage). Deploys to Vercel or any Python host.

- Security audit, protections, risks: **SECURITY.md**
- Setup and deployment: **DEPLOY.md**
- Database: **schema.sql** · Settings template: **.env.example** · Tests: `python -m pytest`

Layout: `app.py` (entry), `sg_app/` (code), `templates/`, `static/`, `tests/`.
Code map: `access.py` login/role checks · `routes.py` all URLs · `providers.py` Supabase · `security.py` validation/headers.
