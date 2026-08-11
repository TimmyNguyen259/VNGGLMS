"""Quiz scoring, legacy migration, progress recomputation."""
import pytest
from app.shared import get_db
from modules.lms.routes import init_lms_db


# ------------------------------------------------------------------
# Quiz scoring — % correct across all questions
# ------------------------------------------------------------------

def _setup_course_with_quiz(client, login, admin_id=1):
    login(user_id=admin_id, role="admin")
    client.post("/lms/courses", data={"program_id": "1", "title": "C1"})  # course id=1
    client.post("/lms/courses/1/lessons", data={"title": "Q", "content_type": "quiz"})  # lesson id=1
    client.post("/lms/lessons/1/questions", data={
        "question_text": "2+2?", "correct_answer": "4", "wrong_choices": "3 | 5"})
    client.post("/lms/lessons/1/questions", data={
        "question_text": "Cap of VN?", "correct_answer": "Hanoi", "wrong_choices": "Saigon | Hue"})
    client.post("/lms/lessons/1/questions", data={
        "question_text": "Sky color?", "correct_answer": "Blue", "wrong_choices": "Green | Red"})
    client.post("/lms/courses/1/learners", data={"user_ids": "4"})


def test_quiz_score_all_correct(client, seed, login):
    _setup_course_with_quiz(client, login)
    login(user_id=4, role="learner")
    client.post("/lms/courses/1/learn/1", data={"answer_1": "4", "answer_2": "Hanoi", "answer_3": "Blue"})
    conn = get_db()
    score = conn.execute("SELECT score FROM lms_lesson_progress WHERE lesson_id=1").fetchone()["score"]
    conn.close()
    assert score == 100


def test_quiz_score_two_of_three(client, seed, login):
    _setup_course_with_quiz(client, login)
    login(user_id=4, role="learner")
    client.post("/lms/courses/1/learn/1", data={"answer_1": "4", "answer_2": "Hanoi", "answer_3": "Green"})
    conn = get_db()
    score = conn.execute("SELECT score FROM lms_lesson_progress WHERE lesson_id=1").fetchone()["score"]
    conn.close()
    assert score == 67  # round(2/3*100) = 67


def test_quiz_score_all_wrong(client, seed, login):
    _setup_course_with_quiz(client, login)
    login(user_id=4, role="learner")
    client.post("/lms/courses/1/learn/1", data={"answer_1": "3", "answer_2": "Saigon", "answer_3": "Red"})
    conn = get_db()
    score = conn.execute("SELECT score FROM lms_lesson_progress WHERE lesson_id=1").fetchone()["score"]
    conn.close()
    assert score == 0


# ------------------------------------------------------------------
# Legacy migration — content_body pipe-string -> lms_quiz_questions
# ------------------------------------------------------------------

def test_legacy_quiz_body_migrated_to_questions_table(app):
    """Quiz cũ lưu 'Q ||| correct ||| A | B' trong content_body — init phải lift lên bảng câu hỏi."""
    conn = get_db()
    conn.execute("INSERT INTO lms_programs (id, name) VALUES (1, 'P')")
    conn.execute("INSERT INTO lms_courses (id, program_id, title) VALUES (1, 1, 'C')")
    conn.execute(
        "INSERT INTO lms_lessons (id, course_id, title, content_type, content_body) "
        "VALUES (99, 1, 'legacy', 'quiz', 'Which framework? ||| Flask ||| Django | FastAPI')"
    )
    conn.commit(); conn.close()

    init_lms_db()  # migration runs again — should pick up legacy row

    conn = get_db()
    rows = conn.execute(
        "SELECT question_text, correct_answer, wrong_choices FROM lms_quiz_questions WHERE lesson_id = 99"
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0]["question_text"] == "Which framework?"
    assert rows[0]["correct_answer"] == "Flask"
    assert rows[0]["wrong_choices"] == "Django | FastAPI"


def test_legacy_migration_is_idempotent(app):
    """Chạy init_lms_db() nhiều lần không được double-insert."""
    conn = get_db()
    conn.execute("INSERT INTO lms_programs (id, name) VALUES (1, 'P')")
    conn.execute("INSERT INTO lms_courses (id, program_id, title) VALUES (1, 1, 'C')")
    conn.execute(
        "INSERT INTO lms_lessons (id, course_id, title, content_type, content_body) "
        "VALUES (99, 1, 'legacy', 'quiz', 'Q ||| A ||| B | C')"
    )
    conn.commit(); conn.close()

    init_lms_db(); init_lms_db(); init_lms_db()

    conn = get_db()
    n = conn.execute("SELECT COUNT(*) c FROM lms_quiz_questions WHERE lesson_id = 99").fetchone()["c"]
    conn.close()
    assert n == 1


# ------------------------------------------------------------------
# Progress recomputation — auto-flip to 'completed' at 100%
# ------------------------------------------------------------------

def test_progress_recomputes_to_100_and_completed(client, seed, login):
    """Learner học xong tất cả lesson -> progress_pct=100, status='completed'."""
    login(user_id=1, role="admin")
    client.post("/lms/courses", data={"program_id": "1", "title": "C1"})  # id=1
    client.post("/lms/courses/1/lessons", data={"title": "L1", "content_type": "text"})
    client.post("/lms/courses/1/lessons", data={"title": "L2", "content_type": "text"})
    client.post("/lms/courses/1/learners", data={"user_ids": "4"})

    login(user_id=4, role="learner")
    client.post("/lms/courses/1/learn/1", data={})  # mark done
    conn = get_db()
    e = conn.execute("SELECT progress_pct, status FROM lms_enrollments WHERE user_id=4").fetchone()
    assert e["progress_pct"] == 50
    assert e["status"] == "in_progress"
    conn.close()

    client.post("/lms/courses/1/learn/2", data={})  # mark done -> hits 100%
    conn = get_db()
    e = conn.execute("SELECT progress_pct, status, completed_at FROM lms_enrollments WHERE user_id=4").fetchone()
    conn.close()
    assert e["progress_pct"] == 100
    assert e["status"] == "completed"
    assert e["completed_at"] is not None
