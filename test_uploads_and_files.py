import io

from tests.conftest import GOOD_PDF, Env

FORM = {"title": "Maths", "class_name": "Class 10", "subject": "Maths", "description": "ncert"}


def upload(client, content=GOOD_PDF, filename="book.pdf", **extra):
    return client.post("/admin/upload", data={**FORM, **extra, "pdf": (io.BytesIO(content), filename)},
                       content_type="multipart/form-data", follow_redirects=True)


def test_valid_pdf_goes_to_private_random_path(env):
    boss, _ = env.sign_in("boss@example.com")
    assert b"Resource uploaded" in upload(boss, filename="../../etc/passwd.pdf").data
    (path,) = env.storage.files
    assert path.startswith("books/") and "passwd" not in path and path.endswith(".pdf")
    assert "/" not in env.store.books[1]["original_filename"] and ".." not in env.store.books[1]["original_filename"]


def test_rejects_wrong_type_signature_and_broken_files(env):
    boss, _ = env.sign_in("boss@example.com")
    assert b"Only .pdf" in upload(boss, filename="evil.exe").data
    assert b"not a real PDF" in upload(boss, content=b"MZ\x90\x00 not a pdf", filename="fake.pdf").data
    assert b"not a real PDF" in upload(boss, content=b"PK\x03\x04zipdata", filename="archive.pdf").data
    assert b"incomplete" in upload(boss, content=b"%PDF-1.4 truncated").data
    assert b"scripts or embedded" in upload(boss, content=b"%PDF-1.4\n/JavaScript (app.alert(1))\n%%EOF").data
    assert not env.storage.files and not env.store.books


def test_oversized_upload_is_refused():
    env = Env(MAX_UPLOAD_MB="0.001")                        # ~1 KB limit for the test
    boss, _ = env.sign_in("boss@example.com")
    r = upload(boss, content=GOOD_PDF + b"0" * 5000)
    assert r.status_code in (200, 413) and not env.storage.files


def test_bad_form_values_refused(env):
    boss, _ = env.sign_in("boss@example.com")
    assert b"Enter valid details" in upload(boss, class_name="Class 99").data
    assert not env.storage.files


def test_pdf_requires_sign_in_by_default_and_redirects_to_short_lived_link(env):
    boss, _ = env.sign_in("boss@example.com")
    upload(boss)
    anon = env.client().get("/read/1")
    assert anon.status_code == 302 and "/login" in anon.headers["Location"]
    student, _ = env.sign_in("s@example.com")
    r = student.get("/read/1")
    assert r.status_code == 302 and r.headers["Location"].startswith("https://fake-storage.test/books/")
    assert "exp=60" in r.headers["Location"] and r.headers["Cache-Control"] == "no-store"


def test_public_reading_can_be_enabled_explicitly():
    env = Env(PUBLIC_PDF_READING="true")
    boss, _ = env.sign_in("boss@example.com")
    upload(boss)
    assert env.client().get("/read/1").status_code == 302
    assert "login" not in env.client().get("/read/1").headers["Location"]


def test_no_way_to_fetch_private_files_from_static_or_guessable_urls(env):
    boss, _ = env.sign_in("boss@example.com")
    upload(boss)
    (path,) = env.storage.files
    c = env.client()
    for url in (f"/static/{path}", f"/{path}", "/static/../app.py", "/static/..%2fapp.py", "/private_data/library.sqlite3"):
        assert c.get(url).status_code == 404
    assert env.client().get("/read/999").status_code in (302, 404)


def test_delete_book_removes_file(env):
    boss, _ = env.sign_in("boss@example.com")
    upload(boss)
    boss.post("/admin/delete/1")
    assert not env.storage.files and not env.store.books


def padded_pdf(megabytes):
    return b"%PDF-1.4\n" + b"0" * int(megabytes * 1024 * 1024) + b"\n%%EOF\n"


def test_default_size_window_is_1mb_to_20mb():
    env = Env(MIN_UPLOAD_MB="1", MAX_UPLOAD_MB="20")
    boss, _ = env.sign_in("boss@example.com")
    assert b"too small" in upload(boss, content=GOOD_PDF).data
    assert b"too small" in upload(boss, content=padded_pdf(0.9)).data
    assert b"Resource uploaded" in upload(boss, content=padded_pdf(1.0)).data
    assert b"Resource uploaded" in upload(boss, content=padded_pdf(19.5)).data
    assert b"too large" in upload(boss, content=padded_pdf(20.5)).data
    assert len(env.storage.files) == 2


def test_defaults_are_1mb_minimum_and_20mb_maximum(monkeypatch):
    monkeypatch.delenv("MIN_UPLOAD_MB", raising=False)
    monkeypatch.delenv("MAX_UPLOAD_MB", raising=False)
    from sg_app import create_app
    app = create_app({"APP_ENV": "testing", "SECRET_KEY": "x" * 40})
    assert app.config["MIN_UPLOAD_BYTES"] == 1024 * 1024
    assert app.config["MAX_UPLOAD_BYTES"] == 20 * 1024 * 1024
