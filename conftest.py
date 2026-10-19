import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from sg_app import create_app  # noqa: E402
from tests.fakes import FakeAuth, MemoryStorage, MemoryStore  # noqa: E402

GOOD_PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


class Env:
    """Bundles an app, its fake services and helpers to sign people in."""

    def __init__(self, **overrides):
        self.store, self.storage, self.auth = MemoryStore(), MemoryStorage(), FakeAuth()
        cfg = {"APP_ENV": "testing", "SECRET_KEY": "x" * 40, "SITE_URL": "http://localhost",
               "WTF_CSRF_ENABLED": "False", "MIN_UPLOAD_MB": "0", "RATELIMIT_ENABLED": "False", "ADMIN_EMAILS": "boss@example.com"}
        cfg.update(overrides)
        self.app = create_app(cfg, store=self.store, storage=self.storage, auth=self.auth)

    def client(self):
        return self.app.test_client()

    def sign_in(self, email, name="Test User", client=None):
        client = client or self.client()
        known = next((u for u, prof in self.store.profiles.items() if prof["email"] == email), None)
        user = self.auth.register(f"code-{email}-{id(client)}", email, name, uid=known)
        client.get("/auth/google")
        r = client.get(f"/auth/callback?code=code-{email}-{id(client)}")
        assert r.status_code == 302, r.data
        return client, user["id"]


@pytest.fixture
def env():
    return Env()


@pytest.fixture
def make_env():
    return Env
