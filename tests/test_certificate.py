"""Certificate PDF — /lms/my-courses/<enrollment_id>/certificate.pdf.

Gating: chỉ phát khi progress_pct=100 AND status='completed'. Learner tự tải
của mình, admin tải hộ ai cũng được, ai khác 403. Non-existent 404."""


def _setup_completed_enrollment(app):
    """Trong seed: user 4 (Alice, learner). Tạo course, lesson, enrollment
    completed để test happy path."""
    from app.shared import get_db
    conn = get_db()
    conn.execute("INSERT INTO lms_courses (id, program_id, title) VALUES (10, 1, 'FlaskCourse')")
    conn.execute("INSERT INTO lms_lessons (id, course_id, title, content_type, order_index) "
                 "VALUES (100, 10, 'L1', 'text', 1)")
    conn.execute("INSERT INTO lms_enrollments (id, user_id, course_id, progress_pct, status, completed_at) "
                 "VALUES (500, 4, 10, 100, 'completed', '2026-08-11T10:00:00')")
    conn.execute("INSERT INTO lms_lesson_progress (enrollment_id, lesson_id, status) VALUES (500, 100, 'done')")
    conn.commit(); conn.close()


def _setup_inprogress_enrollment(app):
    from app.shared import get_db
    conn = get_db()
    conn.execute("INSERT INTO lms_courses (id, program_id, title) VALUES (11, 1, 'HalfDoneCourse')")
    conn.execute("INSERT INTO lms_enrollments (id, user_id, course_id, progress_pct, status) "
                 "VALUES (501, 4, 11, 50, 'in_progress')")
    conn.commit(); conn.close()


# ------------------------------------------------------------------
# Happy path
# ------------------------------------------------------------------

def test_learner_gets_pdf_bytes_when_completed(client, seed, login, app):
    _setup_completed_enrollment(app)
    login(user_id=4, role="learner")
    r = client.get("/lms/my-courses/500/certificate.pdf")
    assert r.status_code == 200
    assert r.mimetype == "application/pdf"
    assert r.data[:4] == b"%PDF"  # PDF magic bytes
    assert len(r.data) > 500  # Non-trivial size


def test_pdf_content_disposition_has_filename(client, seed, login, app):
    _setup_completed_enrollment(app)
    login(user_id=4, role="learner")
    r = client.get("/lms/my-courses/500/certificate.pdf")
    disp = r.headers.get("Content-Disposition", "")
    assert "attachment" in disp
    assert ".pdf" in disp


# ------------------------------------------------------------------
# Gating
# ------------------------------------------------------------------

def test_in_progress_enrollment_returns_400(client, seed, login, app):
    _setup_inprogress_enrollment(app)
    login(user_id=4, role="learner")
    r = client.get("/lms/my-courses/501/certificate.pdf")
    assert r.status_code == 400


def test_nonexistent_enrollment_returns_404(client, seed, login):
    login(user_id=4, role="learner")
    r = client.get("/lms/my-courses/9999/certificate.pdf")
    assert r.status_code == 404


def test_other_learner_gets_403(client, seed, login, app):
    """Alice completed course 10. Bob (learner id=2 as learner role) không được tải cert của Alice."""
    _setup_completed_enrollment(app)
    # Tạo learner Bob với id=99 để không nhầm với instructor seed id=2
    from app.shared import get_db
    conn = get_db()
    conn.execute("INSERT INTO lms_users (id, email, name, role) VALUES (99, 'bob@x.com', 'Bob', 'learner')")
    conn.commit(); conn.close()

    login(user_id=99, role="learner")
    r = client.get("/lms/my-courses/500/certificate.pdf")
    assert r.status_code == 403


def test_admin_can_pull_any_learners_cert(client, seed, login, app):
    _setup_completed_enrollment(app)
    login(user_id=1, role="admin")
    r = client.get("/lms/my-courses/500/certificate.pdf")
    assert r.status_code == 200
    assert r.data[:4] == b"%PDF"


def test_anon_redirects_to_login(client, seed, app):
    _setup_completed_enrollment(app)
    r = client.get("/lms/my-courses/500/certificate.pdf")
    assert r.status_code == 302
    assert "/lms/login" in r.headers["Location"]
