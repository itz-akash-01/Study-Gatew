"""Checks the REAL database client builds owner-scoped queries (no network used)."""
import pytest

from sg_app.providers import StoreError, SupabaseStorage, SupabaseStore

UID_A = "11111111-1111-1111-1111-111111111111"
TASK = "22222222-2222-2222-2222-222222222222"


class Recorder:
    def __init__(self):
        self.calls = []

    def request(self, method, url, params=None, json=None, headers=None, timeout=None):
        self.calls.append({"method": method, "url": url, "params": params or {}, "json": json, "timeout": timeout})

        class R:
            status_code, content = 200, b"[]"

            def json(self):
                return []
        return R()


@pytest.fixture
def store():
    s = SupabaseStore("https://x.supabase.co", "service-key")
    s.http = Recorder()
    return s


def test_every_task_query_filters_by_owner(store):
    store.list_tasks(UID_A)
    store.update_task(UID_A, TASK, True)
    store.delete_task(UID_A, TASK)
    for call in store.http.calls:
        assert call["params"]["user_id"] == f"eq.{UID_A}", call
        assert call["timeout"]
    assert store.http.calls[1]["params"]["id"] == f"eq.{TASK}"


def test_invalid_ids_never_reach_the_database(store):
    assert store.update_task(UID_A, "1 OR 1=1", True) is None
    assert store.delete_task("not-a-uuid", TASK) is False
    assert store.get_profile("x&role=eq.admin") is None
    assert store.http.calls == []


def test_profile_updates_only_allowed_columns(store):
    store.update_profile(UID_A, {"role": "admin", "focus_minutes": 10**9, "id": "other"})
    assert store.http.calls[0]["json"] == {"role": "admin"}


def test_storage_refuses_unexpected_paths():
    storage = SupabaseStorage("https://x.supabase.co", "k", "study-pdfs")
    for bad in ("../secrets.txt", "books/../x.pdf", "books/ABC.pdf", "other/file.pdf", ""):
        with pytest.raises(StoreError):
            storage.signed_url(bad)
