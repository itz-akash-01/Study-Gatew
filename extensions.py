"""Shared Flask extensions (created once, attached to the app in create_app)."""
from flask import session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect()


def client_key():
    """Rate-limit signed-in users by account, everyone else by IP address.

    The session cookie is cryptographically signed, so a visitor cannot fake
    another user's id to dodge or hijack their limit.
    """
    uid = session.get("uid")
    return f"user:{uid}" if uid else f"ip:{get_remote_address()}"


limiter = Limiter(key_func=client_key, default_limits=["120 per minute"])
ip_key = get_remote_address
