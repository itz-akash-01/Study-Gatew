import re

import pytest

from tests.conftest import Env


def token_from(client):
    html = client.get("/").data.decode()
    return re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)


def test_csrf_blocks_requests_without_token():
    env = Env(WTF_CSRF_ENABLED="True")
    c, _ = env.sign_in("a@example.com")
    assert c.post("/logout").status_code == 400
    assert c.post("/api/tasks", json={"title": "x"}).status_code == 400
    assert c.get("/api/me").status_code == 200           # reading needs no token


def test_csrf_accepts_valid_token_and_rejects_wrong_one():
    env = Env(WTF_CSRF_ENABLED="True")
    c, _ = env.sign_in("a@example.com")
    assert c.post("/api/tasks", json={"title": "x"}, headers={"X-CSRFToken": "forged"}).status_code == 400
    token = token_from(c)
    assert c.post("/api/tasks", json={"title": "x"}, headers={"X-CSRFToken": token}).status_code == 201
    assert c.post("/logout", data={"csrf_token": token}).status_code == 302


def test_foreign_origin_is_rejected_even_with_valid_session(env):
    c, _ = env.sign_in("a@example.com")
    assert c.post("/api/tasks", json={"title": "x"}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert c.post("/api/tasks", json={"title": "x"}, headers={"Origin": "http://localhost"}).status_code == 201


def test_no_cors_headers_are_ever_sent(env):
    r = env.client().get("/", headers={"Origin": "https://evil.example"})
    assert "Access-Control-Allow-Origin" not in r.headers


def test_login_rate_limit():
    env = Env(RATELIMIT_ENABLED="True")
    c = env.client()
    codes = [c.get("/auth/google").status_code for _ in range(12)]
    assert codes[:10] == [302] * 10 and codes[10:] == [429, 429]


def test_api_rate_limit_is_per_user():
    env = Env(RATELIMIT_ENABLED="True")
    a, _ = env.sign_in("a@example.com")
    b, _ = env.sign_in("b@example.com")
    codes = [a.post("/api/tasks", json={"title": "x"}).status_code for _ in range(62)]
    assert 429 in codes
    assert b.post("/api/tasks", json={"title": "x"}).status_code == 201


def test_security_headers_present(env):
    r = env.client().get("/")
    assert "script-src 'self'" in r.headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Content-Type-Options"] == "nosniff" and r.headers["X-Frame-Options"] == "DENY"
    assert "unsafe-inline" not in r.headers["Content-Security-Policy"].split("style-src-attr")[0]


def test_production_cookie_flags_hsts_and_https_redirect():
    env = Env(APP_ENV="production", SITE_URL="https://study.example.com", SUPABASE_URL="https://x.supabase.co",
              SUPABASE_ANON_KEY="a", SUPABASE_SERVICE_ROLE_KEY="s", TRUSTED_PROXY_COUNT="0")
    c = env.app.test_client()
    insecure = c.get("/", base_url="http://study.example.com")
    assert insecure.status_code == 301 and insecure.headers["Location"].startswith("https://")
    secure = c.get("/auth/google", base_url="https://study.example.com")
    cookie = secure.headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=Lax" in cookie and cookie.startswith("__Host-sg_session=")
    assert "Strict-Transport-Security" in secure.headers


def test_errors_do_not_leak_internals(env):
    @env.app.route("/boom")
    def boom():
        raise RuntimeError("db password is hunter2")

    r = env.client().get("/boom")
    body = r.data.decode()
    assert r.status_code == 500 and "hunter2" not in body and "Traceback" not in body
    assert env.client().get("/api/nope").json == {"error": "not_found"}


def test_storage_outage_gives_generic_503(env):
    from sg_app.providers import StoreError
    env.store.list_books = lambda: (_ for _ in ()).throw(StoreError("database returned 500"))
    r = env.client().get("/")
    assert r.status_code == 503 and b"database returned" not in r.data and b"Temporarily unavailable" in r.data


def test_security_events_are_logged_without_email(env, caplog):
    import logging
    caplog.set_level(logging.INFO)
    env.sign_in("private.person@example.com")
    text = caplog.text
    assert "login_success" in text and "private.person" not in text


def test_login_page_collects_no_passwords(env):
    html = env.client().get("/login").data.decode().lower()
    assert 'type="password"' not in html and "/auth/google" in html
