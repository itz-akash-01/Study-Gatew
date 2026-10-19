"""Who is making this request? Server-side checks used by every protected route."""
import hmac
import time
from functools import wraps

from flask import abort, current_app, g, jsonify, redirect, request, session, url_for

from .security import log_event, valid_uuid


def wants_json():
    return request.path.startswith("/api/")


def _reject(reason):
    log_event("session_rejected", reason=reason)
    session.clear()
    return None


def current_user():
    """Return the signed-in user's profile dict, or None. Cached per request.

    The browser only holds a signed cookie with an id and timestamps. Every
    request re-reads the profile from the database, so deleting an account,
    changing a role, or "sign out everywhere" takes effect immediately.
    """
    if "_user" not in g:
        g._user = _load_user()
    return g._user


def _load_user():
    if "uid" not in session:
        return None
    uid = valid_uuid(session.get("uid"))
    iat, last = session.get("iat"), session.get("last")
    if not uid or not isinstance(iat, int) or not isinstance(last, int):
        return _reject("malformed")

    profile = current_app.extensions["sg_store"].get_profile(uid)
    if not profile:
        return _reject("unknown_user")
    if not hmac.compare_digest(str(profile.get("session_epoch", "")), str(session.get("ep", ""))):
        return _reject("revoked")

    cfg = current_app.config
    is_admin = profile.get("role") == "admin"
    absolute = cfg["ADMIN_SESSION_SECONDS"] if is_admin else cfg["SESSION_ABSOLUTE_SECONDS"]
    idle = cfg["ADMIN_IDLE_SECONDS"] if is_admin else cfg["SESSION_IDLE_SECONDS"]
    now = int(time.time())
    if now - iat > absolute:
        return _reject("expired")
    if now - last > idle:
        return _reject("idle")

    session["last"] = now
    return {
        "id": uid,
        "email": profile.get("email", ""),
        "name": profile.get("display_name") or "",
        "role": profile.get("role", "student"),
        "focus_minutes": int(profile.get("focus_minutes") or 0),
        "sessions": int(profile.get("sessions") or 0),
    }


def start_session(profile):
    """Begin a fresh session (clearing the old one prevents session fixation)."""
    session.clear()
    now = int(time.time())
    session["uid"] = profile["id"]
    session["ep"] = profile["session_epoch"]
    session["iat"] = now
    session["last"] = now
    session.permanent = True


def _deny_unauthenticated():
    if wants_json():
        return jsonify(error="authentication_required"), 401
    return redirect(url_for("login"))


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            return _deny_unauthenticated()
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    """Separate role check: being signed in is NOT enough to be an admin."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            return _deny_unauthenticated()
        if user["role"] != "admin":
            log_event("admin_denied")
            if wants_json():
                return jsonify(error="forbidden"), 403
            abort(403)
        return view(*args, **kwargs)

    return wrapped
