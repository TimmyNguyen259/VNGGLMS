"""
LMS Core — Module: Course Management
Blueprint tương tự cấu trúc modules/scheduling — tái dùng get_db(), BASE_STYLE,
BASE_JS từ app/shared.py. Route đầu tiên: quản lý Program / Course / Lesson.

Import giả định repo root nằm trên PYTHONPATH (giống cách main.py hiện đang
load các module khác). Nếu main.py dùng cách import khác, chỉnh dòng import
bên dưới cho khớp — báo tao nội dung main.py để sửa chính xác.
"""
import os
from flask import Blueprint, request, redirect, url_for, session

from app.shared import get_db, BASE_STYLE, BASE_JS

lms_bp = Blueprint("lms", __name__, url_prefix="/lms")

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def init_lms_db():
    """Chạy 1 lần khi app khởi động để đảm bảo bảng lms_* đã tồn tại."""
    conn = get_db()
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    _migrate_add_course_owner(conn)
    _migrate_legacy_quiz_body(conn)
    conn.commit()
    conn.close()


def _migrate_add_course_owner(conn):
    """SQLite CREATE TABLE IF NOT EXISTS không thêm column vào bảng có sẵn.
    Bảng lms_courses đã ship trước khi có owner_id -> ALTER TABLE nếu thiếu."""
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(lms_courses)").fetchall()]
    if "owner_id" not in cols:
        conn.execute("ALTER TABLE lms_courses ADD COLUMN owner_id INTEGER REFERENCES lms_users(id)")


def _migrate_legacy_quiz_body(conn):
    """Nhất lần chuyển các quiz cũ (content_body dạng 'Q ||| correct ||| A | B | C')
    sang bảng lms_quiz_questions. Chỉ chạy cho lesson chưa có row nào trong bảng
    câu hỏi — an toàn với mọi lần khởi động lại."""
    legacy = conn.execute(
        """SELECT l.id, l.content_body
           FROM lms_lessons l
           WHERE l.content_type = 'quiz'
             AND l.content_body IS NOT NULL
             AND instr(l.content_body, '|||') > 0
             AND NOT EXISTS (SELECT 1 FROM lms_quiz_questions q WHERE q.lesson_id = l.id)"""
    ).fetchall()
    for row in legacy:
        parts = [p.strip() for p in row["content_body"].split("|||")]
        if len(parts) < 2:
            continue
        question_text = parts[0]
        correct_answer = parts[1]
        wrong_choices = parts[2] if len(parts) > 2 else ""
        conn.execute(
            """INSERT INTO lms_quiz_questions
               (lesson_id, question_text, correct_answer, wrong_choices, order_index)
               VALUES (?, ?, ?, ?, 1)""",
            (row["id"], question_text, correct_answer, wrong_choices),
        )


# ------------------------------------------------------------------
# Nav + page shell — cùng khuôn với scheduling_nav()/scheduling_page()
# ------------------------------------------------------------------

STAFF_ROLES = ("admin", "instructor")


def is_admin():
    return session.get("lms_user_role") == "admin"


def is_instructor():
    return session.get("lms_user_role") == "instructor"


def is_staff():
    return session.get("lms_user_role") in STAFF_ROLES


def _forbid(msg):
    return lms_page(
        f'<div class="page"><div class="card"><div class="empty">'
        f'<div class="icon">🚫</div><p>403 — {msg}</p></div></div></div>',
        active="", title="403 Forbidden"), 403


def require_login():
    if session.get("lms_user_id") is None:
        return redirect(url_for("lms_enrollment.login", next=request.path))
    return None


def require_staff():
    """Trả None nếu OK, ngược lại response để caller `return` thẳng."""
    gate = require_login()
    if gate: return gate
    if not is_staff():
        return _forbid("chỉ admin hoặc instructor mới truy cập được trang này.")
    return None


def require_admin():
    gate = require_login()
    if gate: return gate
    if not is_admin():
        return _forbid("chỉ admin mới truy cập được trang này.")
    return None


def require_course_access(course_id):
    """Admin: pass. Instructor: pass nếu owner. Ai khác: 403.
    Trả response 403/redirect nếu không có quyền, ngược lại None."""
    gate = require_staff()
    if gate: return gate
    if is_admin():
        return None
    conn = get_db()
    row = conn.execute("SELECT owner_id FROM lms_courses WHERE id = ?", (course_id,)).fetchone()
    conn.close()
    if row is None:
        return None  # Course không tồn tại — để route riêng xử lý 404
    if row["owner_id"] == session.get("lms_user_id"):
        return None
    return _forbid("bạn không phải owner của Course này.")


def lms_nav(active=""):
    def cls(k):
        return "class='active'" if active == k else ""
    user_name = session.get("lms_user_name")
    user_role = session.get("lms_user_role", "")
    if user_name:
        role_pill = (f'<span class="badge badge-pending" style="margin-right:.5rem;">{user_role}</span>'
                     if user_role else "")
        auth_html = (
            f'{role_pill}'
            f'<span style="color:var(--muted);font-size:.82rem;margin-right:.6rem;">'
            f'<strong style="color:var(--text)">{user_name}</strong></span>'
            f'<form method="POST" action="/lms/logout" style="display:inline;">'
            f'<button class="btn btn-ghost btn-sm" type="submit">Đăng xuất</button></form>'
        )
    else:
        auth_html = '<a class="btn btn-ghost btn-sm" href="/lms/login">Đăng nhập</a>'

    if is_admin():
        staff_links = (
            f'<a href="/lms/programs" {cls("programs")}>Programs</a>'
            f'<a href="/lms/courses" {cls("courses")}>Courses</a>'
            f'<a href="/lms/learners" {cls("learners")}>Learners</a>'
            f'<a href="/lms/reports" {cls("reports")}>Reports</a>'
        )
    elif is_instructor():
        staff_links = (
            f'<a href="/lms/courses" {cls("courses")}>My Courses (Teach)</a>'
            f'<a href="/lms/reports" {cls("reports")}>Reports</a>'
        )
    else:
        staff_links = ""

    return f"""
    <nav class="topnav">
      <div class="brand">
        <a href="/"><span class="accent">VNGG</span>LMS</a>
      </div>
      <div class="nav-links">
        <a href="/lms/" {cls('home')}>Dashboard</a>
        {staff_links}
        <a href="/lms/my-courses" {cls('my-courses')}>My Courses</a>
      </div>
      <div style="display:flex;align-items:center;gap:.4rem;">{auth_html}</div>
    </nav>
    """


def lms_page(content, active="", title="LMS"):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{title} — VNGG LMS</title>
  {BASE_STYLE}
</head>
<body>
  {lms_nav(active)}
  {content}
  <div id="notif-container" class="notif"></div>
  {BASE_JS}
</body>
</html>"""


# ------------------------------------------------------------------
# Dashboard
# ------------------------------------------------------------------

@lms_bp.route("/")
def dashboard():
    conn = get_db()
    program_count = conn.execute("SELECT COUNT(*) c FROM lms_programs").fetchone()["c"]
    course_count = conn.execute("SELECT COUNT(*) c FROM lms_courses").fetchone()["c"]
    lesson_count = conn.execute("SELECT COUNT(*) c FROM lms_lessons").fetchone()["c"]
    enrollment_count = conn.execute("SELECT COUNT(*) c FROM lms_enrollments").fetchone()["c"]
    conn.close()

    content = f"""
    <div class="page">
      <div class="page-header">
        <h1>LMS Dashboard</h1>
        <p>Tổng quan Program / Course / Lesson đang quản lý</p>
      </div>
      <div class="stats-row">
        <div class="stat-pill orange"><div class="val">{program_count}</div><div class="lbl">Programs</div></div>
        <div class="stat-pill blue"><div class="val">{course_count}</div><div class="lbl">Courses</div></div>
        <div class="stat-pill amber"><div class="val">{lesson_count}</div><div class="lbl">Lessons</div></div>
        <div class="stat-pill green"><div class="val">{enrollment_count}</div><div class="lbl">Enrollments</div></div>
      </div>
      <div class="card">
        <p>Bắt đầu bằng cách tạo 1 <a href="/lms/programs">Program</a>, sau đó thêm Course bên trong.
        Xem tiến độ chi tiết theo Program/Course tại <a href="/lms/reports">Reports</a>.</p>
      </div>
    </div>
    """
    return lms_page(content, active="home", title="Dashboard")


# ------------------------------------------------------------------
# Programs — list + create
# ------------------------------------------------------------------

@lms_bp.route("/programs", methods=["GET", "POST"])
def programs():
    gate = require_admin()
    if gate: return gate
    conn = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        if name:
            conn.execute(
                "INSERT INTO lms_programs (name, description) VALUES (?, ?)",
                (name, description),
            )
            conn.commit()
        conn.close()
        return redirect(url_for("lms.programs"))

    rows = conn.execute(
        """SELECT p.*, COUNT(c.id) course_count
           FROM lms_programs p
           LEFT JOIN lms_courses c ON c.program_id = p.id
           GROUP BY p.id ORDER BY p.created_at DESC"""
    ).fetchall()
    conn.close()

    rows_html = "".join(
        f"""<tr>
              <td><strong>{r['name']}</strong><br>
                  <span style="color:var(--muted);font-size:.82rem;">{r['description'] or ''}</span></td>
              <td>{r['course_count']}</td>
              <td><a class="btn btn-ghost btn-sm" href="/lms/courses?program_id={r['id']}">Xem Course</a></td>
            </tr>"""
        for r in rows
    ) or '<tr><td colspan="3"><div class="empty"><p>Chưa có Program nào</p></div></td></tr>'

    content = f"""
    <div class="page">
      <div class="page-header">
        <h1>Programs</h1>
        <p>Nhóm các Course theo chương trình (vd: NextGen 2026, AI in Action)</p>
      </div>

      <div class="card">
        <form method="POST">
          <div class="form-row">
            <div class="form-group">
              <label class="form-label">Tên Program</label>
              <input class="form-control" name="name" required placeholder="vd: NextGen 2026">
            </div>
            <div class="form-group">
              <label class="form-label">Mô tả</label>
              <input class="form-control" name="description" placeholder="Tuỳ chọn">
            </div>
          </div>
          <button class="btn btn-primary" type="submit">+ Tạo Program</button>
        </form>
      </div>

      <div class="card table-wrap">
        <table>
          <thead><tr><th>Program</th><th>Số Course</th><th></th></tr></thead>
          <tbody>{rows_html}</tbody>
        </table>
      </div>
    </div>
    """
    return lms_page(content, active="programs", title="Programs")


# ------------------------------------------------------------------
# Courses — list (filter theo program) + create
# ------------------------------------------------------------------

@lms_bp.route("/courses", methods=["GET", "POST"])
def courses():
    gate = require_staff()
    if gate: return gate
    conn = get_db()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        program_id = request.form.get("program_id")
        if title and program_id:
            # Instructor tự động owner course họ tạo; admin có thể tạo course không owner.
            owner_id = session.get("lms_user_id") if is_instructor() else None
            conn.execute(
                "INSERT INTO lms_courses (program_id, title, description, owner_id) VALUES (?, ?, ?, ?)",
                (program_id, title, description, owner_id),
            )
            conn.commit()
        conn.close()
        return redirect(url_for("lms.courses", program_id=program_id))

    program_id = request.args.get("program_id")
    programs_list = conn.execute("SELECT id, name FROM lms_programs ORDER BY name").fetchall()

    query = """SELECT c.*, p.name program_name,
                      (SELECT COUNT(*) FROM lms_lessons l WHERE l.course_id = c.id) lesson_count,
                      (SELECT COUNT(*) FROM lms_enrollments e WHERE e.course_id = c.id) learner_count
               FROM lms_courses c JOIN lms_programs p ON p.id = c.program_id"""
    where_clauses = []
    params = []
    if program_id:
        where_clauses.append("c.program_id = ?")
        params.append(program_id)
    if is_instructor():
        # Instructor chỉ thấy Course họ own.
        where_clauses.append("c.owner_id = ?")
        params.append(session.get("lms_user_id"))
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
    query += " ORDER BY c.created_at DESC"
    rows = conn.execute(query, tuple(params)).fetchall()
    conn.close()

    program_options = "".join(
        f'<option value="{p["id"]}" {"selected" if str(p["id"]) == str(program_id) else ""}>{p["name"]}</option>'
        for p in programs_list
    )

    rows_html = "".join(
        f"""<tr>
              <td><a href="/lms/courses/{r['id']}"><strong>{r['title']}</strong></a><br>
                  <span style="color:var(--muted);font-size:.82rem;">{r['program_name']}</span></td>
              <td>{r['lesson_count']}</td>
              <td>{r['learner_count']}</td>
              <td><a class="btn btn-ghost btn-sm" href="/lms/courses/{r['id']}">Quản lý Lesson</a></td>
            </tr>"""
        for r in rows
    ) or '<tr><td colspan="4"><div class="empty"><p>Chưa có Course nào</p></div></td></tr>'

    content = f"""
    <div class="page">
      <div class="page-header">
        <h1>Courses</h1>
        <p>Danh sách Course{" theo Program đã chọn" if program_id else ""}</p>
      </div>

      <div class="card">
        <form method="POST">
          <div class="form-row-3">
            <div class="form-group">
              <label class="form-label">Program</label>
              <select class="form-control" name="program_id" required>
                <option value="">-- Chọn Program --</option>
                {program_options}
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">Tên Course</label>
              <input class="form-control" name="title" required placeholder="vd: Stakeholder Management">
            </div>
            <div class="form-group">
              <label class="form-label">Mô tả</label>
              <input class="form-control" name="description" placeholder="Tuỳ chọn">
            </div>
          </div>
          <button class="btn btn-primary" type="submit">+ Tạo Course</button>
        </form>
      </div>

      <div class="card table-wrap">
        <table>
          <thead><tr><th>Course</th><th>Lessons</th><th>Learners</th><th></th></tr></thead>
          <tbody>{rows_html}</tbody>
        </table>
      </div>
    </div>
    """
    return lms_page(content, active="courses", title="Courses")


# ------------------------------------------------------------------
# Course detail — quản lý Lesson bên trong 1 Course
# ------------------------------------------------------------------

@lms_bp.route("/courses/<int:course_id>", methods=["GET"])
def course_detail(course_id):
    gate = require_course_access(course_id)
    if gate: return gate
    conn = get_db()
    course = conn.execute(
        """SELECT c.*, p.name program_name FROM lms_courses c
           JOIN lms_programs p ON p.id = c.program_id WHERE c.id = ?""",
        (course_id,),
    ).fetchone()
    if not course:
        conn.close()
        return lms_page('<div class="page"><div class="empty"><p>Course không tồn tại</p></div></div>',
                         active="courses", title="Not found"), 404

    lessons = conn.execute(
        "SELECT * FROM lms_lessons WHERE course_id = ? ORDER BY order_index, id",
        (course_id,),
    ).fetchall()
    quiz_counts = {
        r["lesson_id"]: r["c"]
        for r in conn.execute(
            """SELECT lesson_id, COUNT(*) c FROM lms_quiz_questions
               WHERE lesson_id IN (SELECT id FROM lms_lessons WHERE course_id = ?)
               GROUP BY lesson_id""",
            (course_id,),
        ).fetchall()
    }
    conn.close()

    type_badge = {
        "video": "badge-scheduled", "pdf": "badge-completed",
        "text": "badge-pending", "quiz": "badge-qualified",
    }

    def lesson_action(l):
        if l["content_type"] == "quiz":
            n = quiz_counts.get(l["id"], 0)
            return f'<a class="btn btn-ghost btn-sm" href="/lms/lessons/{l["id"]}/questions">Sửa câu hỏi ({n})</a>'
        return l["content_url"] or "—"

    lessons_html = "".join(
        f"""<tr>
              <td>{l['order_index']}</td>
              <td><strong>{l['title']}</strong></td>
              <td><span class="badge {type_badge.get(l['content_type'], 'badge-pending')}">{l['content_type']}</span></td>
              <td>{lesson_action(l)}</td>
            </tr>"""
        for l in lessons
    ) or '<tr><td colspan="4"><div class="empty"><p>Chưa có Lesson nào</p></div></td></tr>'

    content = f"""
    <div class="page">
      <div class="page-header">
        <h1>{course['title']}</h1>
        <p>{course['program_name']} · {course['description'] or ''}</p>
      </div>

      <div class="card">
        <form method="POST" action="/lms/courses/{course_id}/lessons">
          <div class="form-row-3">
            <div class="form-group">
              <label class="form-label">Tên Lesson</label>
              <input class="form-control" name="title" required>
            </div>
            <div class="form-group">
              <label class="form-label">Loại nội dung</label>
              <select class="form-control" name="content_type">
                <option value="text">text</option>
                <option value="video">video</option>
                <option value="pdf">pdf</option>
                <option value="quiz">quiz</option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">Link nội dung (Drive/YouTube)</label>
              <input class="form-control" name="content_url" placeholder="https://...">
            </div>
          </div>
          <button class="btn btn-primary" type="submit">+ Thêm Lesson</button>
        </form>
      </div>

      <div class="card table-wrap">
        <table>
          <thead><tr><th>#</th><th>Lesson</th><th>Loại</th><th>Link</th></tr></thead>
          <tbody>{lessons_html}</tbody>
        </table>
      </div>
    </div>
    """
    return lms_page(content, active="courses", title=course["title"])


@lms_bp.route("/courses/<int:course_id>/lessons", methods=["POST"])
def add_lesson(course_id):
    gate = require_course_access(course_id)
    if gate: return gate
    title = request.form.get("title", "").strip()
    content_type = request.form.get("content_type", "text")
    content_url = request.form.get("content_url", "").strip()

    conn = get_db()
    if title:
        next_order = conn.execute(
            "SELECT COALESCE(MAX(order_index), 0) + 1 n FROM lms_lessons WHERE course_id = ?",
            (course_id,),
        ).fetchone()["n"]
        conn.execute(
            """INSERT INTO lms_lessons (course_id, title, content_type, content_url, order_index)
               VALUES (?, ?, ?, ?, ?)""",
            (course_id, title, content_type, content_url, next_order),
        )
        conn.commit()
    conn.close()
    return redirect(url_for("lms.course_detail", course_id=course_id))


# ------------------------------------------------------------------
# Quản lý câu hỏi cho 1 lesson quiz
# ------------------------------------------------------------------

@lms_bp.route("/lessons/<int:lesson_id>/questions", methods=["GET", "POST"])
def lesson_questions(lesson_id):
    gate = require_staff()
    if gate: return gate
    conn = get_db()
    lesson = conn.execute("SELECT * FROM lms_lessons WHERE id = ?", (lesson_id,)).fetchone()
    if not lesson or lesson["content_type"] != "quiz":
        conn.close()
        return lms_page(
            '<div class="page"><div class="empty"><p>Lesson này không phải quiz</p></div></div>',
            active="courses", title="Not found"), 404
    # Ownership check trên course chứa lesson này
    access = require_course_access(lesson["course_id"])
    if access:
        conn.close()
        return access

    if request.method == "POST":
        delete_id = request.form.get("delete_id")
        if delete_id:
            conn.execute(
                "DELETE FROM lms_quiz_questions WHERE id = ? AND lesson_id = ?",
                (delete_id, lesson_id),
            )
        else:
            question_text = request.form.get("question_text", "").strip()
            correct_answer = request.form.get("correct_answer", "").strip()
            wrong_choices = request.form.get("wrong_choices", "").strip()
            if question_text and correct_answer:
                next_order = conn.execute(
                    "SELECT COALESCE(MAX(order_index), 0) + 1 n FROM lms_quiz_questions WHERE lesson_id = ?",
                    (lesson_id,),
                ).fetchone()["n"]
                conn.execute(
                    """INSERT INTO lms_quiz_questions
                       (lesson_id, question_text, correct_answer, wrong_choices, order_index)
                       VALUES (?, ?, ?, ?, ?)""",
                    (lesson_id, question_text, correct_answer, wrong_choices, next_order),
                )
        conn.commit()
        conn.close()
        return redirect(url_for("lms.lesson_questions", lesson_id=lesson_id))

    course_id = lesson["course_id"]
    questions = conn.execute(
        "SELECT * FROM lms_quiz_questions WHERE lesson_id = ? ORDER BY order_index, id",
        (lesson_id,),
    ).fetchall()
    conn.close()

    def q_row(q):
        wrong_display = q["wrong_choices"] or "—"
        return f"""<tr>
          <td>{q['order_index']}</td>
          <td><strong>{q['question_text']}</strong></td>
          <td>{q['correct_answer']}</td>
          <td>{wrong_display}</td>
          <td>
            <form method="POST" style="display:inline;" onsubmit="return confirm('Xoá câu hỏi này?');">
              <input type="hidden" name="delete_id" value="{q['id']}">
              <button class="btn btn-danger btn-sm" type="submit">Xoá</button>
            </form>
          </td>
        </tr>"""

    rows_html = "".join(q_row(q) for q in questions) or \
        '<tr><td colspan="5"><div class="empty"><p>Chưa có câu hỏi nào</p></div></td></tr>'

    content = f"""
    <div class="page">
      <div class="page-header">
        <h1>{lesson['title']}</h1>
        <p><a href="/lms/courses/{course_id}">← Về Course</a> · Quản lý câu hỏi trong quiz</p>
      </div>

      <div class="card">
        <form method="POST">
          <div class="form-group">
            <label class="form-label">Câu hỏi</label>
            <input class="form-control" name="question_text" required placeholder="vd: Decorator nào khai báo route trong Flask?">
          </div>
          <div class="form-row">
            <div class="form-group">
              <label class="form-label">Đáp án đúng</label>
              <input class="form-control" name="correct_answer" required placeholder="vd: @app.route">
            </div>
            <div class="form-group">
              <label class="form-label">Lựa chọn sai (ngăn bằng |)</label>
              <input class="form-control" name="wrong_choices" placeholder="vd: @app.get | @flask.route">
            </div>
          </div>
          <button class="btn btn-primary" type="submit">+ Thêm câu hỏi</button>
        </form>
      </div>

      <div class="card table-wrap">
        <table>
          <thead><tr><th>#</th><th>Câu hỏi</th><th>Đáp án đúng</th><th>Lựa chọn sai</th><th></th></tr></thead>
          <tbody>{rows_html}</tbody>
        </table>
      </div>
    </div>
    """
    return lms_page(content, active="courses", title=f"Quiz: {lesson['title']}")
