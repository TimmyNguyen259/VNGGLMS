"""Bulk-import learners từ CSV — /lms/learners/import."""
import io


def _upload(client, csv_text, filename="users.csv"):
    return client.post(
        "/lms/learners/import",
        data={"csv_file": (io.BytesIO(csv_text.encode("utf-8")), filename)},
        content_type="multipart/form-data",
    )


# ------------------------------------------------------------------
# Access control
# ------------------------------------------------------------------

def test_learner_cannot_access_import_page(client, seed, login):
    login(user_id=4, role="learner")
    assert client.get("/lms/learners/import").status_code == 403


def test_instructor_cannot_access_import_page(client, seed, login):
    login(user_id=2, role="instructor")
    assert client.get("/lms/learners/import").status_code == 403


def test_admin_can_open_import_page(client, seed, login):
    login(user_id=1, role="admin")
    r = client.get("/lms/learners/import")
    assert r.status_code == 200
    assert b"Import Learners" in r.data


# ------------------------------------------------------------------
# Happy path
# ------------------------------------------------------------------

def test_import_happy_path_inserts_all_valid_rows(client, seed, login):
    login(user_id=1, role="admin")
    csv = (
        "name,email,role\n"
        "New Alice,new-alice@x.com,learner\n"
        "New Bob,new-bob@x.com,learner\n"
        "New Carol,new-carol@x.com,instructor\n"
    )
    r = _upload(client, csv)
    assert r.status_code == 200

    from app.shared import get_db
    conn = get_db()
    emails = [row["email"] for row in conn.execute("SELECT email FROM lms_users ORDER BY email").fetchall()]
    conn.close()
    for expected in ("new-alice@x.com", "new-bob@x.com", "new-carol@x.com"):
        assert expected in emails


# ------------------------------------------------------------------
# Edge cases
# ------------------------------------------------------------------

def test_import_dedupes_by_email(client, seed, login):
    login(user_id=1, role="admin")
    # Alice đã tồn tại trong seed (email=alice@x.com)
    csv = "name,email,role\nAlice Copy,alice@x.com,learner\n"
    _upload(client, csv)

    from app.shared import get_db
    conn = get_db()
    n = conn.execute("SELECT COUNT(*) c FROM lms_users WHERE email='alice@x.com'").fetchone()["c"]
    conn.close()
    assert n == 1  # không tạo trùng


def test_import_rejects_invalid_role(client, seed, login):
    login(user_id=1, role="admin")
    csv = "name,email,role\nBad Role,badrole@x.com,superuser\n"
    r = _upload(client, csv)
    body = r.data.decode()
    assert "Lỗi" in body or "lỗi" in body  # có counter lỗi
    from app.shared import get_db
    conn = get_db()
    n = conn.execute("SELECT COUNT(*) c FROM lms_users WHERE email='badrole@x.com'").fetchone()["c"]
    conn.close()
    assert n == 0  # không insert user với role sai


def test_import_rejects_missing_email(client, seed, login):
    login(user_id=1, role="admin")
    csv = "name,email,role\nNo Email,,learner\n"
    _upload(client, csv)
    from app.shared import get_db
    conn = get_db()
    n = conn.execute("SELECT COUNT(*) c FROM lms_users WHERE name='No Email'").fetchone()["c"]
    conn.close()
    assert n == 0


def test_import_defaults_role_to_learner_when_column_missing(client, seed, login):
    login(user_id=1, role="admin")
    csv = "name,email\nRoleless User,roleless@x.com\n"
    _upload(client, csv)
    from app.shared import get_db
    conn = get_db()
    row = conn.execute("SELECT role FROM lms_users WHERE email='roleless@x.com'").fetchone()
    conn.close()
    assert row is not None
    assert row["role"] == "learner"


def test_import_rejects_csv_missing_required_columns(client, seed, login):
    login(user_id=1, role="admin")
    csv = "foo,bar\nx,y\n"  # thiếu name và email
    r = _upload(client, csv)
    assert r.status_code == 200
    body = r.data.decode()
    assert "name" in body and "email" in body  # error message nêu tên cột thiếu
