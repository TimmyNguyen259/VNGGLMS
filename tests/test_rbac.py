"""RBAC + instructor scoping — tuyến phòng thủ chính. Nếu regression ở đây,
người ta có thể xem/sửa Course của người khác."""
import pytest


# ---------- Anon (no login) redirects to /lms/login ----------

@pytest.mark.parametrize("path", [
    "/lms/my-courses",
    "/lms/programs",
    "/lms/courses",
    "/lms/learners",
    "/lms/reports",
])
def test_anon_redirects_to_login(client, seed, path):
    r = client.get(path)
    assert r.status_code == 302
    assert "/lms/login" in r.headers["Location"]


# ---------- Learner blocked from staff routes with 403 ----------

@pytest.mark.parametrize("path", [
    "/lms/programs",
    "/lms/courses",
    "/lms/learners",
    "/lms/reports",
    "/lms/reports/export.csv",
])
def test_learner_gets_403_on_staff_routes(client, seed, login, path):
    login(user_id=4, role="learner")
    r = client.get(path)
    assert r.status_code == 403


def test_learner_sees_only_dashboard_and_mycourses_in_nav(client, seed, login):
    login(user_id=4, role="learner")
    body = client.get("/lms/").data.decode()
    nav = body.split('<div class="nav-links">', 1)[1].split("</div>", 1)[0]
    assert "/lms/my-courses" in nav
    assert "/lms/programs" not in nav
    assert "/lms/courses" not in nav
    assert "/lms/learners" not in nav
    assert "/lms/reports" not in nav


# ---------- Admin can access everything ----------

@pytest.mark.parametrize("path", [
    "/lms/programs",
    "/lms/courses",
    "/lms/learners",
    "/lms/reports",
])
def test_admin_access_ok(client, seed, login, path):
    login(user_id=1, role="admin")
    r = client.get(path)
    assert r.status_code == 200


def test_admin_nav_shows_all_staff_links(client, seed, login):
    login(user_id=1, role="admin")
    body = client.get("/lms/").data.decode()
    nav = body.split('<div class="nav-links">', 1)[1].split("</div>", 1)[0]
    for link in ("/lms/programs", "/lms/courses", "/lms/learners", "/lms/reports"):
        assert link in nav


# ---------- Programs + Learners are admin-only (instructor 403) ----------

@pytest.mark.parametrize("path", [
    "/lms/programs",
    "/lms/learners",
    "/lms/learners/4",
])
def test_instructor_blocked_from_admin_only_routes(client, seed, login, path):
    login(user_id=2, role="instructor")
    r = client.get(path)
    assert r.status_code == 403


# ---------- Instructor scoping on Courses ----------

def _create_course(client, program_id, title):
    return client.post("/lms/courses", data={"program_id": str(program_id), "title": title})


def test_instructor_only_sees_own_courses_in_list(client, seed, login):
    # T1 creates C1, T2 creates C2, Admin creates C3
    login(user_id=2, role="instructor"); _create_course(client, 1, "C1_t1")
    login(user_id=3, role="instructor"); _create_course(client, 1, "C2_t2")
    login(user_id=1, role="admin");      _create_course(client, 1, "C3_admin")

    login(user_id=2, role="instructor")
    body = client.get("/lms/courses").data.decode()
    assert "C1_t1" in body
    assert "C2_t2" not in body
    assert "C3_admin" not in body


def test_admin_sees_all_courses_in_list(client, seed, login):
    login(user_id=2, role="instructor"); _create_course(client, 1, "C1_t1")
    login(user_id=3, role="instructor"); _create_course(client, 1, "C2_t2")

    login(user_id=1, role="admin")
    body = client.get("/lms/courses").data.decode()
    assert "C1_t1" in body
    assert "C2_t2" in body


def test_instructor_cannot_view_others_course(client, seed, login):
    login(user_id=2, role="instructor"); _create_course(client, 1, "C1_t1")  # id=1
    login(user_id=3, role="instructor"); _create_course(client, 1, "C2_t2")  # id=2

    login(user_id=2, role="instructor")
    r = client.get("/lms/courses/2")  # T2's course
    assert r.status_code == 403


def test_instructor_cannot_add_lesson_to_others_course(client, seed, login):
    login(user_id=2, role="instructor"); _create_course(client, 1, "C1_t1")
    login(user_id=3, role="instructor"); _create_course(client, 1, "C2_t2")

    login(user_id=2, role="instructor")
    r = client.post("/lms/courses/2/lessons", data={"title": "hijack", "content_type": "text"})
    assert r.status_code == 403


def test_instructor_can_edit_own_course(client, seed, login):
    login(user_id=2, role="instructor")
    _create_course(client, 1, "C1_t1")
    assert client.get("/lms/courses/1").status_code == 200
    r = client.post("/lms/courses/1/lessons", data={"title": "L1", "content_type": "text"})
    assert r.status_code == 302  # redirect after success


def test_instructor_reports_scoped_to_own_courses(client, seed, login, app):
    login(user_id=2, role="instructor"); _create_course(client, 1, "C1_t1")  # id=1
    login(user_id=3, role="instructor"); _create_course(client, 1, "C2_t2")  # id=2
    # Enroll Alice into both, so reports has rows
    from app.shared import get_db
    conn = get_db()
    conn.execute("INSERT INTO lms_enrollments (user_id, course_id, progress_pct) VALUES (4, 1, 50)")
    conn.execute("INSERT INTO lms_enrollments (user_id, course_id, progress_pct) VALUES (4, 2, 80)")
    conn.commit(); conn.close()

    login(user_id=2, role="instructor")
    body = client.get("/lms/reports").data.decode()
    assert "C1_t1" in body
    assert "C2_t2" not in body

    # CSV export scoped: 1 header + 1 data row
    csv = client.get("/lms/reports/export.csv").data.decode()
    lines = [l for l in csv.splitlines() if l.strip()]
    assert len(lines) == 2  # header + 1 row for C1_t1
    assert "C1_t1" in csv
    assert "C2_t2" not in csv
