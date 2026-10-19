import pytest

API_ROUTES = [("get", "/api/me"), ("get", "/api/planner"), ("post", "/api/tasks"),
              ("patch", "/api/tasks/00000000-0000-0000-0000-000000000000"),
              ("delete", "/api/tasks/00000000-0000-0000-0000-000000000000"), ("post", "/api/focus")]


@pytest.mark.parametrize("method,path", API_ROUTES)
def test_unauthenticated_api_access_is_401(env, method, path):
    r = getattr(env.client(), method)(path, json={})
    assert r.status_code == 401 and r.json["error"] == "authentication_required"


def test_student_a_cannot_touch_student_b_tasks(env):
    a, _ = env.sign_in("a@example.com")
    b, _ = env.sign_in("b@example.com")
    task = a.post("/api/tasks", json={"title": "A private task", "subject": "Math"}).json
    assert b.get("/api/planner").json["tasks"] == []                         # not listed
    assert b.patch(f"/api/tasks/{task['id']}", json={"done": True}).status_code == 404
    assert b.delete(f"/api/tasks/{task['id']}").status_code == 404
    assert a.get("/api/planner").json["tasks"][0]["done"] is False           # unchanged and still there


def test_user_id_in_request_body_is_ignored(env):
    a, uid_a = env.sign_in("a@example.com")
    _, uid_b = env.sign_in("b@example.com")
    t = a.post("/api/tasks", json={"title": "x", "user_id": uid_b, "role": "admin"}).json
    assert env.store.tasks[t["id"]]["user_id"] == uid_a
    assert env.store.profiles[uid_a]["role"] == "student"


@pytest.mark.parametrize("bad", ["1 OR 1=1", "../x", "eq.1&user_id=neq.0", "' OR ''='"])
def test_malicious_task_ids_are_rejected(env, bad):
    a, _ = env.sign_in("a@example.com")
    assert a.patch(f"/api/tasks/{bad}", json={"done": True}).status_code in (404, 405)


def test_input_validation(env):
    a, _ = env.sign_in("a@example.com")
    assert a.post("/api/tasks", json={"title": ""}).status_code == 400
    assert a.post("/api/tasks", json={"title": "x" * 201}).status_code == 400
    assert a.post("/api/tasks", data="title=x").status_code == 415
    assert a.post("/api/focus", json={"minutes": 99999}).status_code == 400
    assert a.post("/api/focus", json={"minutes": True}).status_code == 400
    assert a.post("/api/focus", json={"minutes": 25}).json["focusMinutes"] == 25


def test_html_in_titles_is_returned_as_data_not_markup(env):
    a, _ = env.sign_in("a@example.com")
    a.post("/api/tasks", json={"title": "<script>alert(1)</script>"})
    r = a.get("/api/planner")
    assert r.mimetype == "application/json" and "<script>" in r.json["tasks"][0]["title"]


ADMIN_ROUTES = [("get", "/admin"), ("post", "/admin/upload"), ("post", "/admin/delete/1")]


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
def test_admin_routes_need_login_then_admin_role(env, method, path):
    anon = getattr(env.client(), method)(path)
    assert anon.status_code == 302 and "/login" in anon.headers["Location"]
    student, _ = env.sign_in("student@example.com")
    assert getattr(student, method)(path).status_code == 403
    boss, _ = env.sign_in("boss@example.com")
    assert getattr(boss, method)(path).status_code != 403


def test_role_demotion_takes_effect_immediately(env):
    boss, uid = env.sign_in("boss@example.com")
    assert boss.get("/admin").status_code == 200
    env.store.profiles[uid]["role"] = "student"
    assert boss.get("/admin").status_code == 403


def test_admin_session_is_shorter(env):
    import time
    boss, _ = env.sign_in("boss@example.com")
    with boss.session_transaction() as s:
        s["iat"] = int(time.time()) - 3 * 3600   # fine for students (24h), too old for admins (2h)
    assert boss.get("/admin").status_code == 302
