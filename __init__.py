"""Study_Gateway AI: secure Flask application factory."""
import logging
import os
from datetime import timedelta
from urllib.parse import urlparse

from flask import Flask, abort, jsonify, render_template, request
from flask_limiter.errors import RateLimitExceeded
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from . import routes
from .access import current_user, wants_json
from .extensions import csrf, limiter
from .providers import StoreError, SupabaseAuth, SupabaseStorage, SupabaseStore
from .security import apply_security_headers, log_event

REQUIRED_IN_PRODUCTION = ("SECRET_KEY", "SITE_URL", "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY")


def _flag(env, name, default=False):
    return env.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def create_app(overrides=None, store=None, storage=None, auth=None):
    env = dict(os.environ)
    env.update({k: str(v) for k, v in (overrides or {}).items() if isinstance(v, (str, int))})
    mode = env.get("APP_ENV", "production").lower()
    production = mode == "production"

    if production:
        missing = [n for n in REQUIRED_IN_PRODUCTION if not env.get(n)]
        if missing:
            raise RuntimeError("Missing required environment variables: " + ", ".join(missing))
        if len(env["SECRET_KEY"]) < 32:
            raise RuntimeError("SECRET_KEY must be at least 32 characters.")
        if not env["SITE_URL"].startswith("https://"):
            raise RuntimeError("SITE_URL must start with https:// in production.")

    site_url = env.get("SITE_URL", "http://localhost:5000").rstrip("/")
    parsed = urlparse(site_url)
    max_upload = int(float(env.get("MAX_UPLOAD_MB", "20")) * 1024 * 1024)
    min_upload = int(float(env.get("MIN_UPLOAD_MB", "1")) * 1024 * 1024)
    secure_cookie = site_url.startswith("https://")

    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.config.update(
        SECRET_KEY=env.get("SECRET_KEY") or os.urandom(32).hex(),  # dev only; production requires one
        SECRET_KEY_FALLBACKS=[k for k in env.get("SECRET_KEY_FALLBACKS", "").split(",") if k],
        SITE_URL=site_url,
        SITE_ORIGIN=f"{parsed.scheme}://{parsed.netloc}",
        FORCE_HTTPS=production,
        PUBLIC_PDF_READING=_flag(env, "PUBLIC_PDF_READING"),
        ADMIN_EMAILS={e.strip().lower() for e in env.get("ADMIN_EMAILS", "").split(",") if e.strip()},
        MAX_UPLOAD_BYTES=max_upload,
        MIN_UPLOAD_BYTES=min_upload,
        MAX_CONTENT_LENGTH=max_upload + 512 * 1024,
        MAX_BOOKS=int(env.get("MAX_BOOKS", "500")),
        SIGNED_URL_SECONDS=int(env.get("SIGNED_URL_SECONDS", "60")),
        SESSION_ABSOLUTE_SECONDS=int(env.get("SESSION_ABSOLUTE_SECONDS", str(24 * 3600))),
        SESSION_IDLE_SECONDS=int(env.get("SESSION_IDLE_SECONDS", str(2 * 3600))),
        ADMIN_SESSION_SECONDS=int(env.get("ADMIN_SESSION_SECONDS", str(2 * 3600))),
        ADMIN_IDLE_SECONDS=int(env.get("ADMIN_IDLE_SECONDS", "1800")),
        SESSION_COOKIE_NAME="__Host-sg_session" if secure_cookie else "sg_session",
        SESSION_COOKIE_SECURE=secure_cookie,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",  # Lax (not Strict) so the Google redirect back to us keeps the cookie
        PERMANENT_SESSION_LIFETIME=timedelta(seconds=int(env.get("SESSION_ABSOLUTE_SECONDS", str(24 * 3600)))),
        WTF_CSRF_ENABLED=_flag(env, "WTF_CSRF_ENABLED", True),
        WTF_CSRF_TIME_LIMIT=None,
        RATELIMIT_ENABLED=_flag(env, "RATELIMIT_ENABLED", True),
        RATELIMIT_STORAGE_URI=env.get("RATELIMIT_STORAGE_URI", "memory://"),
        RATELIMIT_HEADERS_ENABLED=True,
        PROPAGATE_EXCEPTIONS=False,
    )
    app.logger.setLevel(logging.INFO)

    proxies = int(env.get("TRUSTED_PROXY_COUNT", "1" if production else "0"))
    if proxies:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxies, x_proto=proxies, x_host=proxies)

    url, service = env.get("SUPABASE_URL", ""), env.get("SUPABASE_SERVICE_ROLE_KEY", "")
    app.extensions["sg_store"] = store or SupabaseStore(url, service)
    app.extensions["sg_storage"] = storage or SupabaseStorage(url, service, env.get("SUPABASE_BUCKET", "study-pdfs"))
    app.extensions["sg_auth"] = auth or SupabaseAuth(url, env.get("SUPABASE_ANON_KEY", ""), service)

    csrf.init_app(app)
    limiter.init_app(app)
    try:
        limiter.reset()
    except Exception:  # noqa: BLE001  (storage backends without reset are fine)
        pass

    @app.before_request
    def force_https():
        if app.config["FORCE_HTTPS"] and not request.is_secure:
            from flask import redirect
            return redirect(request.url.replace("http://", "https://", 1), 301)

    @app.before_request
    def same_origin_only():
        """Extra CSRF layer: browsers tell us where a state-changing request came from."""
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("Origin")
            if origin and origin != app.config["SITE_ORIGIN"]:
                log_event("origin_rejected", origin=origin[:100])
                abort(403)

    app.after_request(apply_security_headers)

    @app.context_processor
    def inject_user():
        try:
            return {"user": current_user()}
        except StoreError:
            return {"user": None}

    messages = {
        400: ("Request rejected", "Your request could not be processed. Refresh the page and try again."),
        401: ("Sign in required", "Please sign in to continue."),
        403: ("Not allowed", "You do not have permission to do that."),
        404: ("Not found", "We could not find that page."),
        405: ("Not allowed", "That action is not supported here."),
        413: ("File too large", "That file is larger than the allowed size."),
        429: ("Slow down", "Too many requests. Please wait a moment and try again."),
        500: ("Something went wrong", "An unexpected error occurred. It has been logged."),
        503: ("Temporarily unavailable", "The service is busy. Please try again shortly."),
    }

    def respond(code):
        title, text = messages.get(code, messages[500])
        if wants_json():
            return jsonify(error=title.lower().replace(" ", "_")), code
        return render_template("error.html", code=code, title=title, message=text), code

    @app.errorhandler(CSRFError)
    def csrf_failed(_e):
        log_event("csrf_failed")
        return respond(400)

    @app.errorhandler(RateLimitExceeded)
    def rate_limited(_e):
        log_event("rate_limited")
        return respond(429)

    @app.errorhandler(StoreError)
    def store_failed(e):
        app.logger.error("store_error %s", e)  # message has no response body or secrets
        return respond(503)

    @app.errorhandler(Exception)
    def unexpected(e):
        if isinstance(e, HTTPException):
            return respond(e.code or 500)
        app.logger.exception("unhandled_error")  # full detail goes to server logs only
        return respond(500)

    routes.register(app)
    return app
