"""All URLs of the site, grouped: public pages, sign-in, planner API, admin."""
import base64
import secrets
import time
import uuid

from flask import abort, current_app, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

from .access import admin_required, current_user, login_required, start_session
from .extensions import ip_key, limiter
from .providers import StoreError, pkce_challenge
from .security import CLASS_NAMES, clean_text, log_event, valid_uuid, validate_pdf

MAX_TASKS_PER_USER = 500


def register(app):
    store = lambda: app.extensions["sg_store"]      # noqa: E731
    storage = lambda: app.extensions["sg_storage"]  # noqa: E731
    auth = lambda: app.extensions["sg_auth"]        # noqa: E731

    # ------------------------------------------------------ public pages --
    @app.route("/")
    def home():
        return render_template("index.html", books=store().list_books())

    @app.route("/book/<int:i>")
    def book(i):
        b = store().get_book(i)
        if not b:
            abort(404)
        return render_template("book.html", b=b)

    @app.route("/read/<int:i>")
    @limiter.limit("60 per minute")
    def read(i):
        if not app.config["PUBLIC_PDF_READING"] and not current_user():
            flash("Please sign in to read study resources.")
            return redirect(url_for("login"))
        b = store().get_book(i)
        if not b:
            abort(404)
        link = storage().signed_url(b["storage_path"], app.config["SIGNED_URL_SECONDS"])
        if not link:
            abort(404)
        return redirect(link, 302)  # short-lived link; the file itself stays private

    @app.route("/login")
    def login():
        if current_user():
            return redirect(url_for("home"))
        return render_template("login.html")

    @app.route("/admin/login")
    def admin_login():
        return redirect(url_for("login"))

    # ------------------------------------------------------------ sign-in --
    @app.route("/auth/google")
    @limiter.limit("10 per minute", key_func=ip_key)
    def google_start():
        verifier = secrets.token_urlsafe(64)
        session.clear()
        session["pkce"] = verifier
        session["pkce_t"] = int(time.time())
        session.permanent = True
        return redirect(auth().authorize_url(app.config["SITE_URL"] + "/auth/callback", pkce_challenge(verifier)))

    def _sign_in_failed(reason):
        log_event("login_failed", reason=reason)
        session.clear()
        flash("Sign-in failed. Please try again.")
        return redirect(url_for("login"))

    @app.route("/auth/callback")
    @limiter.limit("20 per minute", key_func=ip_key)
    def google_callback():
        code = request.args.get("code", "")
        verifier = session.pop("pkce", None)
        started = session.pop("pkce_t", 0)
        if request.args.get("error") or not code or len(code) > 512:
            return _sign_in_failed("provider_error")
        if not verifier or time.time() - started > 600:
            return _sign_in_failed("missing_or_old_verifier")
        user = auth().exchange_code(code, verifier)
        uid = valid_uuid(user.get("id")) if user else None
        if not user or not uid or not user["email"] or not user["email_verified"]:
            return _sign_in_failed("exchange_rejected")

        profile = store().get_profile(uid) or store().create_profile(uid, user["email"], user["name"])
        if not profile:
            return _sign_in_failed("profile_unavailable")
        if user["email"] in app.config["ADMIN_EMAILS"] and profile["role"] != "admin":
            store().update_profile(uid, {"role": "admin"})
            profile = store().get_profile(uid)
            log_event("admin_bootstrap", target=uid)
        start_session(profile)
        log_event("login_success", role=profile["role"])
        return redirect(url_for("home"))

    @app.route("/logout", methods=["POST"])
    def logout():
        log_event("logout")
        session.clear()
        return redirect(url_for("home"))

    @app.route("/account/sign-out-everywhere", methods=["POST"])
    @login_required
    def sign_out_everywhere():
        user = current_user()
        store().update_profile(user["id"], {"session_epoch": uuid.uuid4().hex})
        log_event("sign_out_everywhere")
        session.clear()
        flash("Signed out on all devices.")
        return redirect(url_for("home"))

    @app.route("/account/delete", methods=["POST"])
    @limiter.limit("3 per hour")
    @login_required
    def delete_account():
        user = current_user()
        if user["role"] == "admin":
            flash("Admin accounts must be demoted before deletion.")
            return redirect(url_for("home"))
        if request.form.get("confirm", "").strip() != "DELETE":
            flash('Type DELETE in the box to confirm account deletion.')
            return redirect(url_for("home"))
        store().delete_user_data(user["id"])      # data first, then the login itself
        removed = auth().delete_user(user["id"])
        log_event("account_deleted", auth_removed=removed)
        session.clear()
        flash("Your account and data were deleted." if removed else
              "Your data was deleted. Contact the site owner to finish removing your login.")
        return redirect(url_for("home"))

    # -------------------------------------------------------- planner API --
    def _json():
        data = request.get_json(silent=True) if request.is_json else None
        return data if isinstance(data, dict) else None

    @app.route("/api/me")
    @login_required
    def api_me():
        u = current_user()
        return jsonify(name=u["name"], email=u["email"], role=u["role"])

    @app.route("/api/planner")
    @login_required
    def api_planner():
        u = current_user()
        return jsonify(tasks=store().list_tasks(u["id"]), focusMinutes=u["focus_minutes"], sessions=u["sessions"])

    @app.route("/api/tasks", methods=["POST"])
    @limiter.limit("60 per minute")
    @login_required
    def api_task_create():
        body = _json()
        if body is None:
            return jsonify(error="json_required"), 415
        title = clean_text(body.get("title"), 200)
        subject = clean_text(body.get("subject", "General"), 80)
        if not title or not subject:
            return jsonify(error="invalid_input"), 400
        u = current_user()  # owner comes from the session, never from the request body
        if len(store().list_tasks(u["id"])) >= MAX_TASKS_PER_USER:
            return jsonify(error="task_limit_reached"), 400
        return jsonify(store().create_task(u["id"], title, subject)), 201

    @app.route("/api/tasks/<task_id>", methods=["PATCH"])
    @login_required
    def api_task_update(task_id):
        body = _json()
        if body is None or not isinstance(body.get("done"), bool):
            return jsonify(error="invalid_input"), 400
        task = store().update_task(current_user()["id"], task_id, body["done"])
        if not task:
            log_event("task_not_found", task=str(task_id)[:40])
            return jsonify(error="not_found"), 404
        return jsonify(task)

    @app.route("/api/tasks/<task_id>", methods=["DELETE"])
    @login_required
    def api_task_delete(task_id):
        if not store().delete_task(current_user()["id"], task_id):
            log_event("task_not_found", task=str(task_id)[:40])
            return jsonify(error="not_found"), 404
        return "", 204

    @app.route("/api/focus", methods=["POST"])
    @limiter.limit("30 per hour")
    @login_required
    def api_focus():
        body = _json()
        minutes = body.get("minutes") if body else None
        if not isinstance(minutes, int) or isinstance(minutes, bool) or not 1 <= minutes <= 180:
            return jsonify(error="invalid_input"), 400
        row = store().add_focus(current_user()["id"], minutes)
        return jsonify(focusMinutes=row["focus_minutes"], sessions=row["sessions"])

    # -------------------------------------------------------------- admin --
    @app.route("/admin")
    @admin_required
    def admin():
        return render_template("admin.html", books=store().list_books())

    @app.route("/admin/upload", methods=["POST"])
    @limiter.limit("10 per hour")
    @admin_required
    def upload():
        def refuse(message, reason):
            log_event("upload_rejected", reason=reason)
            flash(message)
            return redirect(url_for("admin"))

        title = clean_text(request.form.get("title"), 160)
        subject = clean_text(request.form.get("subject"), 80)
        desc = clean_text(request.form.get("description", ""), 1000, min_len=0)
        class_name = request.form.get("class_name")
        f = request.files.get("pdf")
        if not title or not subject or desc is None or class_name not in CLASS_NAMES or not f:
            return refuse("Enter valid details and select a PDF.", "bad_form")
        if not (f.filename or "").lower().endswith(".pdf"):
            return refuse("Only .pdf files are accepted.", "bad_extension")
        limit = app.config["MAX_UPLOAD_BYTES"]
        data = f.stream.read(limit + 1)
        if len(data) > limit:
            return refuse(f"PDF too large. Maximum size is {limit // (1024 * 1024)} MB.", "too_large")
        minimum = app.config["MIN_UPLOAD_BYTES"]
        if len(data) < minimum:
            return refuse(f"PDF too small. Minimum size is {minimum / (1024 * 1024):g} MB.", "too_small")
        problem = validate_pdf(data)
        if problem:
            return refuse(problem, "invalid_pdf")
        if len(store().list_books()) >= app.config["MAX_BOOKS"]:
            return refuse("The library is full. Delete something first.", "library_full")

        original = secure_filename(f.filename)[:120] or "document.pdf"
        path = f"books/{secrets.token_hex(16)}.pdf"   # random name: users never choose paths
        storage().put(path, data, "application/pdf")
        try:
            store().add_book({"title": title, "class_name": class_name, "subject": subject,
                              "description": desc, "storage_path": path, "original_filename": original})
        except StoreError:
            storage().delete(path)
            raise
        log_event("upload_ok", size=len(data))
        flash("Resource uploaded.")
        return redirect(url_for("admin"))

    @app.route("/admin/delete/<int:i>", methods=["POST"])
    @limiter.limit("30 per hour")
    @admin_required
    def delete(i):
        row = store().delete_book(i)
        if row:
            storage().delete(row["storage_path"])
            log_event("book_deleted", book=i)
        return redirect(url_for("admin"))
