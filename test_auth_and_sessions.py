import time

from tests.conftest import Env


def test_sign_in_creates_student_profile_and_session(env):
    client, uid = env.sign_in("a@example.com")
    assert env.store.profiles[uid]["role"] == "student"
    assert client.get("/api/me").json["email"] == "a@example.com"


def test_failed_sign_in_cases_all_look_the_same(env):
    c = env.client()
    c.get("/auth/google")
    bad_code = c.get("/auth/callback?code=nope", follow_redirects=True)
    c2 = env.client()                                    # no /auth/google first -> no PKCE verifier
    env.auth.register("good", "a@example.com")
    no_verifier = c2.get("/auth/callback?code=good", follow_redirects=True)
    c3 = env.client()
    c3.get("/auth/google")
    env.auth.register("unv", "u@example.com", verified=False)
    unverified = c3.get("/auth/callback?code=unv", follow_redirects=True)
    for r in (bad_code, no_verifier, unverified):
        assert b"Sign-in failed" in r.data
    assert c.get("/api/me").status_code == 401


def test_pkce_code_is_single_use(env):
    c = env.client()
    c.get("/auth/google")
    env.auth.register("once", "a@example.com")
    assert c.get("/auth/callback?code=once").status_code == 302
    c.get("/logout")
    c.get("/auth/google")
    assert b"Sign-in failed" in c.get("/auth/callback?code=once", follow_redirects=True).data


def test_garbage_or_forged_cookie_is_unauthenticated(env):
    c = env.client()
    c.set_cookie("sg_session", "not-a-real-session")
    assert c.get("/api/me").status_code == 401


def test_session_with_tampered_user_id_is_rejected(env):
    c, uid = env.sign_in("a@example.com")
    with c.session_transaction() as s:
        s["uid"] = "../../etc/passwd"
    assert c.get("/api/me").status_code == 401


def test_absolute_expiry(env):
    c, _ = env.sign_in("a@example.com")
    with c.session_transaction() as s:
        s["iat"] = int(time.time()) - 25 * 3600
    assert c.get("/api/me").status_code == 401


def test_idle_expiry(env):
    c, _ = env.sign_in("a@example.com")
    with c.session_transaction() as s:
        s["last"] = int(time.time()) - 3 * 3600
    assert c.get("/api/me").status_code == 401


def test_sign_out_everywhere_revokes_other_devices(env):
    phone, uid = env.sign_in("a@example.com")
    laptop, _ = env.sign_in("a@example.com")
    assert laptop.post("/account/sign-out-everywhere").status_code == 302
    assert phone.get("/api/me").status_code == 401
    assert laptop.get("/api/me").status_code == 401


def test_logout_clears_session(env):
    c, _ = env.sign_in("a@example.com")
    c.post("/logout")
    assert c.get("/api/me").status_code == 401


def test_deleted_account_cookie_stops_working(env):
    c, uid = env.sign_in("a@example.com")
    stolen = env.client()
    with c.session_transaction() as s:
        snapshot = dict(s)
    with stolen.session_transaction() as s:
        s.update(snapshot)
    c.post("/account/delete", data={"confirm": "DELETE"})
    assert stolen.get("/api/me").status_code == 401


def test_account_deletion_needs_exact_confirmation_and_removes_data(env):
    c, uid = env.sign_in("a@example.com")
    c.post("/api/tasks", json={"title": "secret plan"})
    c.post("/account/delete", data={"confirm": "nope"})
    assert uid in env.store.profiles and env.auth.deleted == []
    c.post("/account/delete", data={"confirm": "DELETE"})
    assert uid not in env.store.profiles and not env.store.tasks and env.auth.deleted == [uid]


def test_admin_cannot_self_delete(env):
    c, uid = env.sign_in("boss@example.com")
    c.post("/account/delete", data={"confirm": "DELETE"})
    assert uid in env.store.profiles


def test_only_listed_emails_become_admin(env):
    _, a = env.sign_in("boss@example.com")
    _, b = env.sign_in("student@example.com")
    assert env.store.profiles[a]["role"] == "admin" and env.store.profiles[b]["role"] == "student"


def test_production_refuses_to_start_without_secrets(monkeypatch):
    import pytest
    from sg_app import create_app
    for name in ("SECRET_KEY", "SITE_URL", "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError, match="Missing required"):
        create_app({"APP_ENV": "production"})
    with pytest.raises(RuntimeError, match="https"):
        create_app({"APP_ENV": "production", "SECRET_KEY": "k" * 40, "SITE_URL": "http://x.com",
                    "SUPABASE_URL": "u", "SUPABASE_ANON_KEY": "a", "SUPABASE_SERVICE_ROLE_KEY": "s"})
