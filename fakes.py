"""In-memory stand-ins for Supabase so tests never touch real services or real data."""
import itertools
import uuid


class FakeAuth:
    def __init__(self):
        self.codes, self.deleted = {}, []

    def register(self, code, email, name="Test User", verified=True, uid=None):
        user = {"id": uid or str(uuid.uuid4()), "email": email, "name": name, "email_verified": verified}
        self.codes[code] = user
        return user

    def authorize_url(self, redirect_to, challenge):
        return f"https://fake-supabase.test/authorize?challenge={challenge}"

    def exchange_code(self, code, verifier):
        return self.codes.pop(code, None)  # codes are single-use, like the real thing

    def delete_user(self, uid):
        self.deleted.append(uid)
        return True


class MemoryStore:
    def __init__(self):
        self.profiles, self.tasks, self.books = {}, {}, {}
        self._book_ids = itertools.count(1)

    def get_profile(self, uid):
        p = self.profiles.get(uid)
        return dict(p) if p else None

    def create_profile(self, uid, email, name):
        self.profiles.setdefault(uid, {"id": uid, "email": email, "display_name": name, "role": "student",
                                       "session_epoch": uuid.uuid4().hex, "focus_minutes": 0, "sessions": 0})
        return self.get_profile(uid)

    def update_profile(self, uid, fields):
        self.profiles[uid].update(fields)

    def add_focus(self, uid, minutes):
        p = self.profiles[uid]
        p["focus_minutes"] += minutes
        p["sessions"] += 1
        return dict(p)

    def list_books(self):
        return sorted(self.books.values(), key=lambda b: -b["id"])

    def get_book(self, i):
        return self.books.get(i)

    def add_book(self, row):
        row = {**row, "id": next(self._book_ids)}
        self.books[row["id"]] = row
        return row

    def delete_book(self, i):
        return self.books.pop(i, None)

    def list_tasks(self, uid):
        return [self._public(t) for t in self.tasks.values() if t["user_id"] == uid]

    @staticmethod
    def _public(t):
        return {k: t[k] for k in ("id", "title", "subject", "done")}

    def create_task(self, uid, title, subject):
        t = {"id": str(uuid.uuid4()), "user_id": uid, "title": title, "subject": subject, "done": False}
        self.tasks[t["id"]] = t
        return self._public(t)

    def update_task(self, uid, tid, done):
        t = self.tasks.get(tid)
        if not t or t["user_id"] != uid:
            return None
        t["done"] = done
        return self._public(t)

    def delete_task(self, uid, tid):
        t = self.tasks.get(tid)
        if not t or t["user_id"] != uid:
            return False
        del self.tasks[tid]
        return True

    def delete_user_data(self, uid):
        self.tasks = {k: v for k, v in self.tasks.items() if v["user_id"] != uid}
        self.profiles.pop(uid, None)


class MemoryStorage:
    def __init__(self):
        self.files = {}

    def put(self, path, data, content_type="application/pdf"):
        self.files[path] = data

    def signed_url(self, path, seconds=60):
        return f"https://fake-storage.test/{path}?token=abc&exp={seconds}" if path in self.files else None

    def delete(self, path):
        self.files.pop(path, None)
