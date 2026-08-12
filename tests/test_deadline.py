"""due_date column + overdue badge on /lms/courses và /lms/my-courses."""
from datetime import date, timedelta


def _create_course(client, program_id, title, due_date=""):
    return client.post("/lms/courses", data={
        "program_id": str(program_id),
        "title": title,
        "due_date": due_date,
    })


def _yesterday(): return (date.today() - timedelta(days=1)).isoformat()
def _tomorrow(): return (date.today() + timedelta(days=1)).isoformat()


# ------------------------------------------------------------------
# Course list — Overdue badge
# ------------------------------------------------------------------

def test_course_list_shows_overdue_badge_for_past_due(client, seed, login):
    login(user_id=1, role="admin")
    _create_course(client, 1, "PastDueCourse", due_date=_yesterday())
    body = client.get("/lms/courses").data.decode()
    assert "PastDueCourse" in body
    # Overdue badge chỉ áp dụng khi due_date < today
    assert "Overdue" in body


def test_course_list_no_overdue_for_future_date(client, seed, login):
    login(user_id=1, role="admin")
    _create_course(client, 1, "FutureCourse", due_date=_tomorrow())
    body = client.get("/lms/courses").data.decode()
    assert "FutureCourse" in body
    assert "Overdue" not in body


def test_course_list_no_due_date_renders_dash(client, seed, login):
    login(user_id=1, role="admin")
    _create_course(client, 1, "NoDueCourse")
    body = client.get("/lms/courses").data.decode()
    assert "NoDueCourse" in body
    # Row hiển thị dấu '—' cho cột deadline
    assert "—" in body


# ------------------------------------------------------------------
# Learner /my-courses — OVERDUE trên card
# ------------------------------------------------------------------

def test_learner_mycourses_shows_overdue_for_past_due_in_progress(client, seed, login, app):
    """Enrollment in_progress + course past deadline -> card show 'OVERDUE'."""
    login(user_id=1, role="admin")
    _create_course(client, 1, "OverdueCourse", due_date=_yesterday())
    client.post("/lms/courses/1/learners", data={"user_ids": "4"})  # enroll Alice

    login(user_id=4, role="learner")
    body = client.get("/lms/my-courses").data.decode()
    assert "OverdueCourse" in body
    assert "OVERDUE" in body


def test_learner_mycourses_no_overdue_when_completed(client, seed, login, app):
    """Enrollment đã completed thì không show OVERDUE dù deadline đã qua."""
    login(user_id=1, role="admin")
    _create_course(client, 1, "CompletedPastDue", due_date=_yesterday())
    # Manually mark enrollment completed
    from app.shared import get_db
    conn = get_db()
    conn.execute("INSERT INTO lms_enrollments (user_id, course_id, progress_pct, status) "
                 "VALUES (4, 1, 100, 'completed')")
    conn.commit(); conn.close()

    login(user_id=4, role="learner")
    body = client.get("/lms/my-courses").data.decode()
    assert "CompletedPastDue" in body
    # Không có "OVERDUE" trong card (chỉ có "Deadline:" bình thường)
    assert "OVERDUE" not in body
