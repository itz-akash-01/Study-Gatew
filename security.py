"""Small, well-tested security helpers: validation, logging, headers."""
import json
import re
import time
import uuid

from flask import current_app, g, request, session
from flask_limiter.util import get_remote_address

CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
STORAGE_PATH = re.compile(r"^books/[0-9a-f]{32}\.pdf$")
ACTIVE_PDF_CONTENT = re.compile(
    rb"/JavaScript|/Launch|/EmbeddedFile|/RichMedia|/JS\s*[\(<]"
)
CLASS_NAMES = ("Class 9", "Class 10", "Class 11", "Class 12", "Other")


def valid_uuid(value):
    """Return the canonical UUID string, or None. Blocks filter-injection."""
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def clean_text(value, max_len, min_len=1):
    """Strip control characters; return None if missing/too short/too long."""
    if not isinstance(value, str):
        return None
    value = CONTROL_CHARS.sub("", value).strip()
    return value if min_len <= len(value) <= max_len else None


def validate_pdf(data: bytes):
    """Return an error message if `data` is not an acceptable PDF, else None.

    This is a sanity check, NOT a malware scanner. It checks the file
    signature, that the file is complete, and refuses PDFs that carry
    JavaScript, launch actions or embedded files.
    """
    if not data.startswith(b"%PDF-"):
        return "That file is not a real PDF."
    if b"%%EOF" not in data[-2048:]:
        return "The PDF looks incomplete or damaged."
    if ACTIVE_PDF_CONTENT.search(data):
        return "PDFs with scripts or embedded files are not allowed."
    return None


def log_event(event, **fields):
    """One-line JSON security log. Never pass tokens, emails or request bodies."""
    record = {
        "ts": int(time.time()),
        "event": event,
        "uid": session.get("uid") if request else None,
        "ip": get_remote_address() if request else None,
        "path": request.path if request else None,
    }
    record.update(fields)
    current_app.logger.info("SECURITY %s", json.dumps(record, default=str))


def build_csp():
    return "; ".join(
        [
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self' https://fonts.googleapis.com",
            "style-src-attr 'unsafe-inline'",  # only for the width/height bars
            "font-src https://fonts.gstatic.com",
            "img-src 'self' data:",
            "connect-src 'self'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]
    )


def apply_security_headers(response):
    h = response.headers
    h["Content-Security-Policy"] = build_csp()
    h["X-Content-Type-Options"] = "nosniff"
    h["X-Frame-Options"] = "DENY"
    h["Referrer-Policy"] = "strict-origin-when-cross-origin"
    h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    h["Cross-Origin-Opener-Policy"] = "same-origin"
    if current_app.config["FORCE_HTTPS"]:
        h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    # Pages and APIs may contain personal data: never let shared caches keep them.
    if request.path.startswith(("/api/", "/admin", "/auth", "/account", "/read")) or session.get("uid"):
        h["Cache-Control"] = "no-store"
    return response
