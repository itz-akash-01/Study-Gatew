"""Talks to Supabase: Auth (Google sign-in), Postgres (REST) and private Storage.

All secrets come from environment variables. Nothing here is exposed to the browser.
"""
import base64
import hashlib
from urllib.parse import urlencode

import requests

from .security import STORAGE_PATH, valid_uuid

TIMEOUT = 10  # seconds; never wait forever on a network call


class StoreError(Exception):
    """Database/storage failure. Message never contains response bodies."""


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# ---------------------------------------------------------------- Auth -----
class SupabaseAuth:
    def __init__(self, url, anon_key, service_key):
        self.url = url.rstrip("/")
        self.anon_key = anon_key
        self.service_key = service_key

    def authorize_url(self, redirect_to, challenge):
        query = urlencode(
            {
                "provider": "google",
                "redirect_to": redirect_to,
                "code_challenge": challenge,
                "code_challenge_method": "s256",
            }
        )
        return f"{self.url}/auth/v1/authorize?{query}"

    def exchange_code(self, code, verifier):
        """Swap the one-time code for the signed-in user. Returns a dict or None."""
        try:
            r = requests.post(
                f"{self.url}/auth/v1/token",
                params={"grant_type": "pkce"},
                json={"auth_code": code, "code_verifier": verifier},
                headers={"apikey": self.anon_key},
                timeout=TIMEOUT,
            )
        except requests.RequestException:
            return None
        if r.status_code != 200:
            return None
        data = r.json()
        user = data.get("user") or {}
        meta = user.get("user_metadata") or {}
        self._drop_supabase_session(data.get("access_token"))
        return {
            "id": user.get("id"),
            "email": (user.get("email") or "").strip().lower(),
            "name": meta.get("full_name") or meta.get("name") or "",
            "email_verified": bool(user.get("email_confirmed_at") or meta.get("email_verified")),
        }

    def _drop_supabase_session(self, access_token):
        """We run our own session cookie, so revoke Supabase's tokens right away."""
        if not access_token:
            return
        try:
            requests.post(
                f"{self.url}/auth/v1/logout",
                headers={"apikey": self.anon_key, "Authorization": f"Bearer {access_token}"},
                timeout=TIMEOUT,
            )
        except requests.RequestException:
            pass

    def delete_user(self, uid):
        uid = valid_uuid(uid)
        if not uid:
            return False
        try:
            r = requests.delete(
                f"{self.url}/auth/v1/admin/users/{uid}",
                headers={"apikey": self.service_key, "Authorization": f"Bearer {self.service_key}"},
                timeout=TIMEOUT,
            )
        except requests.RequestException:
            return False
        return r.status_code in (200, 204)


# ------------------------------------------------------------ Database -----
class SupabaseStore:
    """Every per-user query below filters by user_id *and* the record id."""

    PROFILE_WRITABLE = {"display_name", "email", "role", "session_epoch"}

    def __init__(self, url, service_key):
        self.base = url.rstrip("/") + "/rest/v1"
        self.http = requests.Session()
        self.http.headers.update({"apikey": service_key, "Authorization": f"Bearer {service_key}"})

    def _call(self, method, path, params=None, body=None, prefer=None):
        headers = {"Content-Type": "application/json"}
        if prefer:
            headers["Prefer"] = prefer
        try:
            r = self.http.request(method, f"{self.base}/{path}", params=params, json=body, headers=headers, timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise StoreError("database unreachable") from exc
        if r.status_code >= 400:
            raise StoreError(f"database returned {r.status_code}")
        return r.json() if r.content else []

    # profiles
    def get_profile(self, uid):
        uid = valid_uuid(uid)
        if not uid:
            return None
        rows = self._call("GET", "profiles", {"id": f"eq.{uid}", "select": "*", "limit": 1})
        return rows[0] if rows else None

    def create_profile(self, uid, email, name):
        uid = valid_uuid(uid)
        self._call(
            "POST", "profiles", {"on_conflict": "id"},
            {"id": uid, "email": email, "display_name": name[:120] or None},
            prefer="resolution=ignore-duplicates,return=minimal",
        )
        return self.get_profile(uid)

    def update_profile(self, uid, fields):
        uid = valid_uuid(uid)
        fields = {k: v for k, v in fields.items() if k in self.PROFILE_WRITABLE}
        if uid and fields:
            self._call("PATCH", "profiles", {"id": f"eq.{uid}"}, fields, prefer="return=minimal")

    def add_focus(self, uid, minutes):
        uid = valid_uuid(uid)
        row = self._call("POST", "rpc/add_focus", None, {"p_user": uid, "p_minutes": int(minutes)})
        return row[0] if isinstance(row, list) else row

    # books (public library records; files live in private storage)
    def list_books(self):
        return self._call("GET", "books", {"select": "id,title,class_name,subject,description,created_at", "order": "id.desc"})

    def get_book(self, book_id):
        rows = self._call("GET", "books", {"id": f"eq.{int(book_id)}", "select": "*", "limit": 1})
        return rows[0] if rows else None

    def add_book(self, row):
        return self._call("POST", "books", None, row, prefer="return=representation")[0]

    def delete_book(self, book_id):
        rows = self._call("DELETE", "books", {"id": f"eq.{int(book_id)}"}, prefer="return=representation")
        return rows[0] if rows else None

    # planner tasks (owner-scoped)
    def list_tasks(self, uid):
        uid = valid_uuid(uid)
        return self._call("GET", "tasks", {"user_id": f"eq.{uid}", "select": "id,title,subject,done", "order": "created_at.desc", "limit": 500})

    def create_task(self, uid, title, subject):
        uid = valid_uuid(uid)
        rows = self._call("POST", "tasks", None, {"user_id": uid, "title": title, "subject": subject}, prefer="return=representation")
        return {k: rows[0][k] for k in ("id", "title", "subject", "done")}

    def update_task(self, uid, task_id, done):
        uid, task_id = valid_uuid(uid), valid_uuid(task_id)
        if not uid or not task_id:
            return None
        rows = self._call("PATCH", "tasks", {"id": f"eq.{task_id}", "user_id": f"eq.{uid}"}, {"done": bool(done)}, prefer="return=representation")
        return {k: rows[0][k] for k in ("id", "title", "subject", "done")} if rows else None

    def delete_task(self, uid, task_id):
        uid, task_id = valid_uuid(uid), valid_uuid(task_id)
        if not uid or not task_id:
            return False
        rows = self._call("DELETE", "tasks", {"id": f"eq.{task_id}", "user_id": f"eq.{uid}"}, prefer="return=representation")
        return bool(rows)

    def delete_user_data(self, uid):
        uid = valid_uuid(uid)
        for table, column in (("tasks", "user_id"), ("ai_history", "user_id"), ("profiles", "id")):
            self._call("DELETE", table, {column: f"eq.{uid}"}, prefer="return=minimal")


# ------------------------------------------------------ Private storage ----
class SupabaseStorage:
    def __init__(self, url, service_key, bucket):
        self.base = url.rstrip("/") + "/storage/v1"
        self.bucket = bucket
        self.headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}

    @staticmethod
    def _check(path):
        if not STORAGE_PATH.match(path or ""):
            raise StoreError("invalid storage path")

    def put(self, path, data, content_type="application/pdf"):
        self._check(path)
        try:
            r = requests.post(
                f"{self.base}/object/{self.bucket}/{path}", data=data,
                headers={**self.headers, "Content-Type": content_type, "x-upsert": "false"}, timeout=60,
            )
        except requests.RequestException as exc:
            raise StoreError("storage unreachable") from exc
        if r.status_code >= 400:
            raise StoreError(f"storage returned {r.status_code}")

    def signed_url(self, path, seconds=60):
        self._check(path)
        try:
            r = requests.post(f"{self.base}/object/sign/{self.bucket}/{path}", json={"expiresIn": int(seconds)}, headers=self.headers, timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise StoreError("storage unreachable") from exc
        if r.status_code != 200:
            return None
        signed = r.json().get("signedURL")
        return f"{self.base}{signed}" if signed else None

    def delete(self, path):
        self._check(path)
        try:
            requests.delete(f"{self.base}/object/{self.bucket}/{path}", headers=self.headers, timeout=TIMEOUT)
        except requests.RequestException:
            pass
