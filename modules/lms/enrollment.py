"""
LMS Core — Module: Enrollment Engine (UC-02, UC-03, UC-04, UC-07)
Blueprint riêng, tái dùng lms_page()/lms_nav() từ routes.py (Course Management)
để không lặp lại code shell. Cùng DB (ats.db), cùng bảng lms_* đã tạo ở schema.sql.

Auth: stopgap Flask session — trang /lms/login cho phép chọn 1 learner rồi lưu
vào session["lms_user_id"]. Không phải SSO thật, nhưng đủ để URL tampering
không tick lesson hộ được người khác. Cần thay bằng SSO thật trước khi launch.
"""
import csv
import html
import io
import re
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
from flask import Blueprint, request, redirect, url_for, session, Response, abort

from app.shared import get_db
from .routes import lms_page, require_staff, require_admin, require_course_access
from .sso import is_sso_configured


def _youtube_video_id(url):
    """Trả về video_id nếu URL là YouTube, ngược lại None."""
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    host = (parsed.hostname or "").lower().lstrip("www.")
    if host in ("youtu.be",):
        vid = parsed.path.strip("/").split("/")[0]
        return vid if re.fullmatch(r"[A-Za-z0-9_-]{6,20}", vid) else None
    if host in ("youtube.com", "m.youtube.com", "youtube-nocookie.com"):
        if parsed.path == "/watch":
            vid = parse_qs(parsed.query).get("v", [""])[0]
            return vid if re.fullmatch(r"[A-Za-z0-9_-]{6,20}", vid) else None
        if parsed.path.startswith("/embed/"):
            vid = parsed.path[len("/embed/"):].split("/")[0]
            return vid if re.fullmatch(r"[A-Za-z0-9_-]{6,20}", vid) else None
    return None


def _vimeo_video_id(url):
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    host = (parsed.hostname or "").lower().lstrip("www.")
    if host in ("vimeo.com", "player.vimeo.com"):
        vid = parsed.path.strip("/").split("/")[0]
        return vid if vid.isdigit() else None
    return None


def _render_lesson_media(content_type, content_url):
    """Render iframe/embed cho video/PDF nếu URL nhận diện được, fallback về link."""
    if not content_url:
        return ""
    if not re.match(r"^https?://", content_url, re.IGNORECASE):
        return ""  # chặn javascript:… và schema lạ
    safe_url = html.escape(content_url, quote=True)

    if content_type == "video":
        yt = _youtube_video_id(content_url)
        if yt:
            return (f'<div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;'
                    f'border-radius:var(--radius);margin-bottom:1rem;">'
                    f'<iframe src="https://www.youtube-nocookie.com/embed/{html.escape(yt, quote=True)}" '
                    f'style="position:absolute;top:0;left:0;width:100%;height:100%;border:0;" '
                    f'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" '
                    f'allowfullscreen loading="lazy"></iframe></div>')
        vm = _vimeo_video_id(content_url)
        if vm:
            return (f'<div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;'
                    f'border-radius:var(--radius);margin-bottom:1rem;">'
                    f'<iframe src="https://player.vimeo.com/video/{html.escape(vm, quote=True)}" '
                    f'style="position:absolute;top:0;left:0;width:100%;height:100%;border:0;" '
                    f'allow="autoplay; fullscreen; picture-in-picture" '
                    f'allowfullscreen loading="lazy"></iframe></div>')

    if content_type == "pdf" or content_url.lower().split("?")[0].endswith(".pdf"):
        return (f'<iframe src="{safe_url}" '
                f'style="width:100%;height:70vh;border:1px solid var(--border);'
                f'border-radius:var(--radius);margin-bottom:1rem;" loading="lazy"></iframe>')

    return (f'<p><a class="btn btn-blue" href="{safe_url}" target="_blank" rel="noopener">'
            f'Mở nội dung ({html.escape(content_type)})</a></p>')

enrollment_bp = Blueprint("lms_enrollment", __name__, url_prefix="/lms")


def _current_learner_id():
    """Session-backed learner id. None nếu chưa login."""
    return session.get("lms_user_id")


def _require_login():
    """Trả về (user_id, None) nếu đã login, ngược lại (None, redirect_response)."""
    uid = _current_learner_id()
    if uid is None:
        return None, redirect(url_for("lms_enrollment.login", next=request.path))
    return uid, None


def recompute_progress(conn, enrollment_id):
    """Tính lại % progress của 1 enrollment dựa trên lesson_progress đã done.
    Nếu đạt 100% -> tự chuyển status='completed' (UC-07)."""
    total = conn.execute(
        """SELECT COUNT(*) c FROM lms_lessons l
           JOIN lms_enrollments e ON e.course_id = l.course_id
           WHERE e.id = ?""",
        (enrollment_id,),
    ).fetchone()["c"]

    done = conn.execute(
        """SELECT COUNT(*) c FROM lms_lesson_progress
           WHERE enrollment_id = ? AND status = 'done'""",
        (enrollment_id,),
    ).fetchone()["c"]

    pct = int(round((done / total) * 100)) if total else 0
    status = "completed" if pct >= 100 and total > 0 else "in_progress"
    completed_at = datetime.now(timezone.utc).isoformat() if status == "completed" else None

    conn.execute(
        """UPDATE lms_enrollments
           SET progress_pct = ?, status = ?,
               completed_at = CASE WHEN ? IS NOT NULL THEN ? ELSE completed_at END
           WHERE id = ?""",
        (pct, status, completed_at, completed_at, enrollment_id),
    )
    conn.commit()
    return pct, status


# ------------------------------------------------------------------
# Learners — quản lý danh sách lms_users (MVP, chưa có auth thật)
# ------------------------------------------------------------------

@enrollment_bp.route("/learners", methods=["GET", "POST"])
def learners():
    gate = require_admin()
    if gate: return gate
    conn = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        role = request.form.get("role", "learner")
        if name and email:
            try:
                conn.execute(
                    "INSERT INTO lms_users (name, email, role) VALUES (?, ?, ?)",
                    (name, email, role),
                )
                conn.commit()
            except Exception:
                pass  # email trùng (UNIQUE) -> bỏ qua, không tạo trùng
        conn.close()
        return redirect(url_for("lms_enrollment.learners"))

    rows = conn.execute("SELECT * FROM lms_users ORDER BY name").fetchall()
    conn.close()

    rows_html = "".join(
        f"""<tr>
              <td><div class="cand-info"><span class="name">{r['name']}</span></div></td>
              <td>{r['email']}</td>
              <td><span class="badge badge-pending">{r['role']}</span></td>
              <td><a class="btn btn-ghost btn-sm" href="/lms/learners/{r['id']}">Xem tiến độ</a></td>
            </tr>"""
        for r in rows
    ) or '<tr><td colspan="4"><div class="empty"><p>Chưa có Learner nào</p></div></td></tr>'

    content = f"""
    <div class="page">
      <div class="page-header">
        <h1>Learners</h1>
        <p>Danh sách nhân sự có thể được gán vào Course</p>
      </div>

      <div class="card">
        <form method="POST">
          <div class="form-row-3">
            <div class="form-group">
              <label class="form-label">Họ tên</label>
              <input class="form-control" name="name" required>
            </div>
            <div class="form-group">
              <label class="form-label">Email</label>
              <input class="form-control" name="email" type="email" required>
            </div>
            <div class="form-group">
              <label class="form-label">Vai trò</label>
              <select class="form-control" name="role">
                <option value="learner">learner</option>
                <option value="instructor">instructor</option>
                <option value="admin">admin</option>
              </select>
            </div>
          </div>
          <div style="display:flex;gap:.5rem;align-items:center;">
            <button class="btn btn-primary" type="submit">+ Thêm Learner</button>
            <a class="btn btn-ghost" href="/lms/learners/import">⬆ Import từ CSV</a>
          </div>
        </form>
      </div>

      <div class="card table-wrap">
        <table>
          <thead><tr><th>Tên</th><th>Email</th><th>Role</th><th></th></tr></thead>
          <tbody>{rows_html}</tbody>
        </table>
      </div>
    </div>
    """
    return lms_page(content, active="learners", title="Learners")


# ------------------------------------------------------------------
# Bulk import learners từ CSV
# ------------------------------------------------------------------

_VALID_ROLES = ("learner", "instructor", "admin")


def _parse_learners_csv(text):
    """Parse CSV text. Trả về (rows, error). rows là list dict {name,email,role}.
    Yêu cầu header 'name,email,role' (không phân biệt hoa thường, thứ tự cột tuỳ).
    Cột 'role' có thể thiếu -> default 'learner'."""
    try:
        reader = csv.DictReader(io.StringIO(text))
    except Exception as e:
        return [], f"CSV không parse được: {e}"
    if not reader.fieldnames:
        return [], "CSV trống hoặc thiếu header."
    fieldmap = {f.strip().lower(): f for f in reader.fieldnames if f}
    if "name" not in fieldmap or "email" not in fieldmap:
        return [], f"CSV cần có ít nhất 2 cột 'name' và 'email'. Đang có: {reader.fieldnames}"
    rows = []
    for r in reader:
        rows.append({
            "name": (r.get(fieldmap["name"]) or "").strip(),
            "email": (r.get(fieldmap["email"]) or "").strip().lower(),
            "role": (r.get(fieldmap.get("role", ""), "") or "learner").strip().lower(),
        })
    return rows, None


@enrollment_bp.route("/learners/import", methods=["GET", "POST"])
def learners_import():
    gate = require_admin()
    if gate: return gate

    summary_html = ""
    if request.method == "POST":
        f = request.files.get("csv_file")
        if not f or not f.filename:
            summary_html = '<div class="card"><div class="empty"><p>Chưa chọn file CSV.</p></div></div>'
        else:
            text = f.stream.read().decode("utf-8-sig", errors="replace")
            rows, err = _parse_learners_csv(text)
            if err:
                summary_html = f'<div class="card"><div class="empty"><p style="color:var(--red)">{html.escape(err)}</p></div></div>'
            else:
                inserted, skipped_dup, errored = [], [], []
                conn = get_db()
                for r in rows:
                    if not r["name"] or not r["email"] or "@" not in r["email"]:
                        errored.append((r, "thiếu name/email hoặc email không hợp lệ"))
                        continue
                    if r["role"] not in _VALID_ROLES:
                        errored.append((r, f"role không hợp lệ ({r['role']!r})"))
                        continue
                    try:
                        conn.execute("INSERT INTO lms_users (name, email, role) VALUES (?, ?, ?)",
                                     (r["name"], r["email"], r["role"]))
                        inserted.append(r)
                    except Exception:
                        skipped_dup.append(r)  # UNIQUE(email) constraint
                conn.commit(); conn.close()

                def _list_rows(items, label_col=None):
                    if not items: return "—"
                    def one(it):
                        r = it if isinstance(it, dict) else it[0]
                        reason = f" — {html.escape(it[1])}" if isinstance(it, tuple) else ""
                        return f'<li>{html.escape(r["name"])} &lt;{html.escape(r["email"])}&gt; ({html.escape(r["role"])}){reason}</li>'
                    return f'<ul style="margin-left:1.2rem;">{"".join(one(x) for x in items[:20])}</ul>' + \
                           (f'<div style="color:var(--muted);font-size:.8rem;">…và {len(items)-20} nữa</div>' if len(items)>20 else "")

                summary_html = f"""
                <div class="card">
                  <h2 style="font-size:1rem;margin-bottom:.75rem;">Kết quả import</h2>
                  <div class="stats-row">
                    <div class="stat-pill green"><div class="val">{len(inserted)}</div><div class="lbl">Đã thêm</div></div>
                    <div class="stat-pill amber"><div class="val">{len(skipped_dup)}</div><div class="lbl">Skip (trùng email)</div></div>
                    <div class="stat-pill orange"><div class="val">{len(errored)}</div><div class="lbl">Lỗi</div></div>
                  </div>
                  <details style="margin-top:1rem;"><summary style="cursor:pointer;font-weight:600;">Đã thêm ({len(inserted)})</summary>{_list_rows(inserted)}</details>
                  <details style="margin-top:.5rem;"><summary style="cursor:pointer;font-weight:600;">Skip trùng email ({len(skipped_dup)})</summary>{_list_rows(skipped_dup)}</details>
                  <details style="margin-top:.5rem;"><summary style="cursor:pointer;font-weight:600;">Lỗi ({len(errored)})</summary>{_list_rows(errored)}</details>
                  <p style="margin-top:1rem;"><a class="btn btn-primary" href="/lms/learners">← Về Learners</a></p>
                </div>
                """

    content = f"""
    <div class="page">
      <div class="page-header">
        <h1>Import Learners từ CSV</h1>
        <p>File CSV cần header 'name,email,role' (role tuỳ chọn, default 'learner').</p>
      </div>
      {summary_html}
      <div class="card">
        <form method="POST" enctype="multipart/form-data">
          <div class="form-group">
            <label class="form-label">File CSV</label>
            <input class="form-control" type="file" name="csv_file" accept=".csv,text/csv" required>
          </div>
          <div style="display:flex;gap:.5rem;">
            <button class="btn btn-primary" type="submit">Import</button>
            <a class="btn btn-ghost" href="/lms/learners">Huỷ</a>
          </div>
        </form>
        <details style="margin-top:1rem;">
          <summary style="cursor:pointer;color:var(--muted);font-size:.85rem;">Ví dụ CSV</summary>
          <pre style="background:var(--surface2);padding:.75rem;border-radius:6px;font-size:.8rem;margin-top:.5rem;">name,email,role
Alice Nguyen,alice@vng.com.vn,learner
Bob Tran,bob@vng.com.vn,learner
Carol Le,carol@vng.com.vn,instructor</pre>
        </details>
      </div>
    </div>
    """
    return lms_page(content, active="learners", title="Import Learners")


# ------------------------------------------------------------------
# Admin view — xem tiến độ chi tiết của 1 learner (read-only)
# ------------------------------------------------------------------

@enrollment_bp.route("/learners/<int:user_id>")
def learner_detail(user_id):
    gate = require_admin()
    if gate: return gate
    conn = get_db()
    learner = conn.execute("SELECT * FROM lms_users WHERE id = ?", (user_id,)).fetchone()
    if not learner:
        conn.close()
        return lms_page(
            '<div class="page"><div class="empty"><p>Learner không tồn tại</p></div></div>',
            active="learners", title="Not found"), 404

    enrollments = conn.execute(
        """SELECT e.*, c.title course_title, p.name program_name
           FROM lms_enrollments e
           JOIN lms_courses c ON c.id = e.course_id
           JOIN lms_programs p ON p.id = c.program_id
           WHERE e.user_id = ? ORDER BY e.enrolled_at DESC""",
        (user_id,),
    ).fetchall()

    course_blocks = []
    for e in enrollments:
        lessons = conn.execute(
            """SELECT l.id, l.title, l.content_type, l.order_index,
                      lp.status, lp.score
               FROM lms_lessons l
               LEFT JOIN lms_lesson_progress lp
                 ON lp.lesson_id = l.id AND lp.enrollment_id = ?
               WHERE l.course_id = ?
               ORDER BY l.order_index, l.id""",
            (e["id"], e["course_id"]),
        ).fetchall()

        def lesson_row(l):
            done = l["status"] == "done"
            badge = ('<span class="badge badge-qualified">Đã học</span>' if done
                     else '<span class="badge badge-pending">Chưa học</span>')
            score = f"{l['score']}%" if l["score"] is not None else "—"
            return (f"<tr><td>{l['order_index']}</td>"
                    f"<td><strong>{l['title']}</strong>"
                    f"<br><span style=\"color:var(--muted);font-size:.8rem;\">{l['content_type']}</span></td>"
                    f"<td>{badge}</td><td>{score}</td></tr>")

        rows_html = "".join(lesson_row(l) for l in lessons) or \
            '<tr><td colspan="4"><div class="empty"><p>Course chưa có Lesson</p></div></td></tr>'

        status_badge_cls = ("badge-completed" if e["status"] == "completed" else "badge-scheduled")
        status_label = "Hoàn thành" if e["status"] == "completed" else "Đang học"

        course_blocks.append(f"""
        <div class="card">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:1rem;flex-wrap:wrap;gap:.75rem;">
            <div>
              <h2 style="font-size:1.05rem;margin-bottom:.25rem;">{e['course_title']}</h2>
              <div style="color:var(--muted);font-size:.82rem;">{e['program_name']} · enrolled {e['enrolled_at']}</div>
            </div>
            <span class="badge {status_badge_cls}">{status_label}</span>
          </div>
          <div class="score-bar" style="margin-bottom:1rem;">
            <div class="score-bar-track"><div class="score-bar-fill" style="width:{e['progress_pct']}%"></div></div>
            <div class="score-num">{e['progress_pct']}%</div>
          </div>
          <div class="table-wrap">
            <table>
              <thead><tr><th>#</th><th>Lesson</th><th>Trạng thái</th><th>Điểm</th></tr></thead>
              <tbody>{rows_html}</tbody>
            </table>
          </div>
        </div>
        """)

    conn.close()

    enrollments_html = "".join(course_blocks) or \
        '<div class="card"><div class="empty"><p>Learner này chưa được gán Course nào</p></div></div>'

    content = f"""
    <div class="page">
      <div class="page-header">
        <h1>{learner['name']}</h1>
        <p>{learner['email']} · <span class="badge badge-pending">{learner['role']}</span>
           · <a href="/lms/learners">← Về Learners</a></p>
      </div>
      {enrollments_html}
    </div>
    """
    return lms_page(content, active="learners", title=learner["name"])


# ------------------------------------------------------------------
# UC-02 — Gán học viên vào Course (Enrollment)
# ------------------------------------------------------------------

@enrollment_bp.route("/courses/<int:course_id>/learners", methods=["GET", "POST"])
def course_learners(course_id):
    gate = require_course_access(course_id)
    if gate: return gate
    conn = get_db()

    if request.method == "POST":
        user_ids = request.form.getlist("user_ids")
        for uid in user_ids:
            try:
                conn.execute(
                    "INSERT INTO lms_enrollments (user_id, course_id) VALUES (?, ?)",
                    (uid, course_id),
                )
            except Exception:
                pass  # đã enroll trước đó (UNIQUE user_id+course_id) -> bỏ qua, không tạo trùng
        conn.commit()
        conn.close()
        return redirect(url_for("lms_enrollment.course_learners", course_id=course_id))

    course = conn.execute("SELECT * FROM lms_courses WHERE id = ?", (course_id,)).fetchone()

    enrolled = conn.execute(
        """SELECT e.*, u.name, u.email FROM lms_enrollments e
           JOIN lms_users u ON u.id = e.user_id
           WHERE e.course_id = ? ORDER BY e.enrolled_at DESC""",
        (course_id,),
    ).fetchall()

    enrolled_ids = {r["user_id"] for r in enrolled}
    available = [
        u for u in conn.execute("SELECT * FROM lms_users ORDER BY name").fetchall()
        if u["id"] not in enrolled_ids
    ]
    conn.close()

    options_html = "".join(
        f'<option value="{u["id"]}">{u["name"]} ({u["email"]})</option>' for u in available
    )

    rows_html = "".join(
        f"""<tr>
              <td>{r['name']}<br><span style="color:var(--muted);font-size:.8rem;">{r['email']}</span></td>
              <td>
                <div class="score-bar">
                  <div class="score-bar-track"><div class="score-bar-fill" style="width:{r['progress_pct']}%"></div></div>
                  <div class="score-num">{r['progress_pct']}%</div>
                </div>
              </td>
              <td><span class="badge {'badge-qualified' if r['status']=='completed' else 'badge-scheduled'}">{r['status']}</span></td>
            </tr>"""
        for r in enrolled
    ) or '<tr><td colspan="3"><div class="empty"><p>Chưa gán Learner nào vào Course này</p></div></td></tr>'

    content = f"""
    <div class="page">
      <div class="page-header">
        <h1>{course['title'] if course else 'Course'} — Learners</h1>
        <p>Gán học viên và theo dõi tiến độ</p>
      </div>

      <div class="card">
        <form method="POST">
          <div class="form-group">
            <label class="form-label">Chọn Learner để gán (giữ Ctrl/Cmd để chọn nhiều)</label>
            <select class="form-control" name="user_ids" multiple size="5">{options_html}</select>
          </div>
          <button class="btn btn-primary" type="submit">+ Gán vào Course</button>
        </form>
      </div>

      <div class="card table-wrap">
        <table>
          <thead><tr><th>Learner</th><th>Progress</th><th>Status</th></tr></thead>
          <tbody>{rows_html}</tbody>
        </table>
      </div>
    </div>
    """
    return lms_page(content, active="courses", title="Course Learners")


# ------------------------------------------------------------------
# UC-03 — Learner xem course được gán ("My Courses")
# ------------------------------------------------------------------

@enrollment_bp.route("/login", methods=["GET", "POST"])
def login():
    conn = get_db()
    if request.method == "POST":
        uid = request.form.get("user_id", "").strip()
        row = conn.execute("SELECT id, name, role FROM lms_users WHERE id = ?", (uid,)).fetchone() if uid else None
        if row:
            session["lms_user_id"] = int(row["id"])
            session["lms_user_name"] = row["name"]
            session["lms_user_role"] = row["role"]
            conn.close()
            next_url = request.args.get("next") or url_for("lms_enrollment.my_courses")
            return redirect(next_url)
        # fall through and re-render
    users = conn.execute("SELECT id, name, email FROM lms_users ORDER BY name").fetchall()
    conn.close()

    options = "".join(
        f'<option value="{u["id"]}">{u["name"]} ({u["email"]})</option>' for u in users
    )
    next_arg = request.args.get("next", "")
    sso_html = ""
    if is_sso_configured():
        sso_next = f"?next={next_arg}" if next_arg else ""
        sso_html = f"""
        <div class="card" style="text-align:center;">
          <p style="margin-bottom:.75rem;color:var(--muted);font-size:.85rem;">Đăng nhập bằng tài khoản công ty</p>
          <a class="btn btn-primary" href="/lms/sso/login{sso_next}"
             style="display:inline-flex;align-items:center;gap:.5rem;">
            <span style="font-size:1.1rem;">🪟</span> Đăng nhập bằng Microsoft
          </a>
        </div>
        <div style="text-align:center;color:var(--muted);font-size:.8rem;margin:1rem 0;">— hoặc dùng dropdown (dev) —</div>
        """
    content = f"""
    <div class="page">
      <div class="page-header">
        <h1>LMS Login</h1>
        <p>{'Chọn tài khoản để đăng nhập.' if is_sso_configured() else 'Chọn learner để bắt đầu học (dev fallback, chưa phải SSO thật).'}</p>
      </div>
      {sso_html}
      <div class="card">
        <form method="POST" action="/lms/login?next={next_arg}">
          <div class="form-group">
            <label class="form-label">Learner (dev dropdown)</label>
            <select class="form-control" name="user_id" required>
              <option value="">-- Chọn learner --</option>
              {options}
            </select>
          </div>
          <button class="btn btn-ghost" type="submit">Đăng nhập</button>
        </form>
      </div>
    </div>
    """
    return lms_page(content, active="my-courses", title="Login")


@enrollment_bp.route("/logout", methods=["POST"])
def logout():
    session.pop("lms_user_id", None)
    session.pop("lms_user_name", None)
    session.pop("lms_user_role", None)
    return redirect(url_for("lms_enrollment.login"))


@enrollment_bp.route("/my-courses")
def my_courses():
    user_id, resp = _require_login()
    if resp:
        return resp

    conn = get_db()
    rows = conn.execute(
        """SELECT e.*, c.title, c.description, c.due_date, p.name program_name
           FROM lms_enrollments e
           JOIN lms_courses c ON c.id = e.course_id
           JOIN lms_programs p ON p.id = c.program_id
           WHERE e.user_id = ? ORDER BY e.enrolled_at DESC""",
        (user_id,),
    ).fetchall()
    conn.close()

    from datetime import date
    today = date.today().isoformat()
    def _due_line(r):
        d = r["due_date"]
        if not d: return ""
        if r["status"] == "completed": return f'<div style="color:var(--muted);font-size:.78rem;margin-top:.35rem;">Deadline: {d}</div>'
        overdue = d < today
        color = "var(--red)" if overdue else "var(--muted)"
        prefix = "OVERDUE — deadline: " if overdue else "Deadline: "
        return f'<div style="color:{color};font-size:.78rem;font-weight:600;margin-top:.35rem;">{prefix}{d}</div>'

    def _cert_link(r):
        if r["status"] != "completed": return ""
        return (f'<a class="btn btn-primary btn-sm" href="/lms/my-courses/{r["id"]}/certificate.pdf" '
                f'style="margin-top:.6rem;display:inline-flex;align-items:center;gap:.35rem;" '
                f'onclick="event.stopPropagation();">🎓 Tải Certificate</a>')

    cards_html = "".join(
        f"""<div class="mod-card live" style="display:block;">
              <a href="/lms/courses/{r['course_id']}/learn" style="color:inherit;text-decoration:none;display:block;">
                <div class="mod-ico">📚</div>
                <h2>{r['title']}</h2>
                <p>{r['program_name']}</p>
                <div class="score-bar" style="margin-top:.75rem;">
                  <div class="score-bar-track"><div class="score-bar-fill" style="width:{r['progress_pct']}%"></div></div>
                  <div class="score-num">{r['progress_pct']}%</div>
                </div>
                <div class="status-line">{'HOÀN THÀNH' if r['status']=='completed' else 'ĐANG HỌC'}</div>
                {_due_line(r)}
              </a>
              {_cert_link(r)}
            </div>"""
        for r in rows
    ) or '<div class="empty"><p>Chưa được gán Course nào</p></div>'

    content = f"""
    <div class="page">
      <div class="page-header"><h1>My Courses</h1><p>Course bạn đang/đã học</p></div>
      <div class="module-grid">{cards_html}</div>
    </div>
    """
    return lms_page(content, active="my-courses", title="My Courses")


# ------------------------------------------------------------------
# Certificate PDF — chỉ phát khi enrollment đã completed
# ------------------------------------------------------------------

def _render_certificate_pdf(learner_name, course_title, program_name, completed_at):
    """Trả bytes PDF cert 1 trang, A4 landscape."""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import cm
    from reportlab.lib.colors import HexColor

    buf = io.BytesIO()
    W, H = landscape(A4)
    c = canvas.Canvas(buf, pagesize=landscape(A4))

    # Background cream
    c.setFillColor(HexColor("#faf7f2"))
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # Outer border (orange)
    c.setStrokeColor(HexColor("#e8632b"))
    c.setLineWidth(3)
    c.rect(1*cm, 1*cm, W - 2*cm, H - 2*cm, fill=0)
    # Inner border (subtle)
    c.setStrokeColor(HexColor("#d9d1c4"))
    c.setLineWidth(0.6)
    c.rect(1.3*cm, 1.3*cm, W - 2.6*cm, H - 2.6*cm, fill=0)

    # Title
    c.setFillColor(HexColor("#e8632b"))
    c.setFont("Helvetica-Bold", 40)
    c.drawCentredString(W/2, H - 4*cm, "Certificate of Completion")

    c.setFillColor(HexColor("#7a6f5f"))
    c.setFont("Helvetica", 14)
    c.drawCentredString(W/2, H - 5*cm, "This is to certify that")

    # Learner name
    c.setFillColor(HexColor("#1e1b16"))
    c.setFont("Helvetica-Bold", 32)
    c.drawCentredString(W/2, H - 7*cm, learner_name)

    # Description
    c.setFillColor(HexColor("#7a6f5f"))
    c.setFont("Helvetica", 14)
    c.drawCentredString(W/2, H - 8.3*cm, "has successfully completed the course")

    c.setFillColor(HexColor("#1e1b16"))
    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(W/2, H - 9.7*cm, course_title)

    if program_name:
        c.setFillColor(HexColor("#7a6f5f"))
        c.setFont("Helvetica-Oblique", 12)
        c.drawCentredString(W/2, H - 10.5*cm, f"— program: {program_name}")

    # Date line
    c.setFillColor(HexColor("#1e1b16"))
    c.setFont("Helvetica", 12)
    date_str = (completed_at or "").split("T")[0]
    c.drawCentredString(W/2, 3*cm, f"Completed on {date_str}")

    # Footer brand
    c.setFillColor(HexColor("#e8632b"))
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(W/2, 1.9*cm, "VNGG LMS")

    c.showPage()
    c.save()
    return buf.getvalue()


@enrollment_bp.route("/my-courses/<int:enrollment_id>/certificate.pdf")
def certificate(enrollment_id):
    user_id, resp = _require_login()
    if resp:
        return resp

    conn = get_db()
    row = conn.execute(
        """SELECT e.*, u.name learner_name, c.title course_title, p.name program_name
           FROM lms_enrollments e
           JOIN lms_users u ON u.id = e.user_id
           JOIN lms_courses c ON c.id = e.course_id
           JOIN lms_programs p ON p.id = c.program_id
           WHERE e.id = ?""",
        (enrollment_id,),
    ).fetchone()
    conn.close()

    if not row:
        abort(404)
    # Learner tự tải cert của mình; admin có thể tải cho bất kỳ ai
    is_admin_ = session.get("lms_user_role") == "admin"
    if not is_admin_ and row["user_id"] != user_id:
        abort(403)
    if row["status"] != "completed" or row["progress_pct"] < 100:
        return lms_page(
            '<div class="page"><div class="card"><div class="empty">'
            '<div class="icon">🎓</div>'
            '<p>Certificate chỉ được cấp khi course đã hoàn thành 100%.</p>'
            '<p><a class="btn btn-ghost btn-sm" href="/lms/my-courses" style="margin-top:.75rem;">← Về My Courses</a></p>'
            '</div></div></div>',
            active="my-courses", title="Certificate not ready"), 400

    pdf_bytes = _render_certificate_pdf(
        row["learner_name"], row["course_title"], row["program_name"], row["completed_at"] or ""
    )
    safe_slug = re.sub(r"[^A-Za-z0-9]+", "_", row["course_title"]).strip("_") or "course"
    filename = f"certificate_{safe_slug}.pdf"
    return Response(pdf_bytes, mimetype="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# ------------------------------------------------------------------
# UC-03/04 — Xem 1 Course, học từng Lesson, làm quiz nếu có
# ------------------------------------------------------------------

@enrollment_bp.route("/courses/<int:course_id>/learn")
def learn_course(course_id):
    user_id, resp = _require_login()
    if resp:
        return resp
    conn = get_db()

    enrollment = conn.execute(
        "SELECT * FROM lms_enrollments WHERE course_id = ? AND user_id = ?",
        (course_id, user_id),
    ).fetchone()
    if not enrollment:
        conn.close()
        return lms_page('<div class="page"><div class="empty"><p>Bạn chưa được gán vào Course này</p></div></div>',
                         active="my-courses"), 403

    course = conn.execute("SELECT * FROM lms_courses WHERE id = ?", (course_id,)).fetchone()
    lessons = conn.execute(
        "SELECT * FROM lms_lessons WHERE course_id = ? ORDER BY order_index, id",
        (course_id,),
    ).fetchall()
    progress_map = {
        p["lesson_id"]: p
        for p in conn.execute(
            "SELECT * FROM lms_lesson_progress WHERE enrollment_id = ?", (enrollment["id"],)
        ).fetchall()
    }
    conn.close()

    def lesson_row(l):
        prog = progress_map.get(l["id"])
        done = prog and prog["status"] == "done"
        badge = '<span class="badge badge-qualified">Đã hoàn thành</span>' if done else '<span class="badge badge-pending">Chưa học</span>'
        action = f'<a class="btn btn-ghost btn-sm" href="/lms/courses/{course_id}/learn/{l["id"]}">{"Xem lại" if done else "Bắt đầu học"}</a>'
        return f"""<tr><td>{l['order_index']}</td><td><strong>{l['title']}</strong>
                   <br><span style="color:var(--muted);font-size:.8rem;">{l['content_type']}</span></td>
                   <td>{badge}</td><td>{action}</td></tr>"""

    lessons_html = "".join(lesson_row(l) for l in lessons) or '<tr><td colspan="4"><div class="empty"><p>Course chưa có Lesson</p></div></td></tr>'

    content = f"""
    <div class="page">
      <div class="page-header">
        <h1>{course['title']}</h1>
        <p>Progress hiện tại: {enrollment['progress_pct']}% — {enrollment['status']}</p>
      </div>
      <div class="card table-wrap">
        <table>
          <thead><tr><th>#</th><th>Lesson</th><th>Trạng thái</th><th></th></tr></thead>
          <tbody>{lessons_html}</tbody>
        </table>
      </div>
    </div>
    """
    return lms_page(content, active="my-courses", title=course["title"])


@enrollment_bp.route("/courses/<int:course_id>/learn/<int:lesson_id>", methods=["GET", "POST"])
def learn_lesson(course_id, lesson_id):
    user_id, resp = _require_login()
    if resp:
        return resp
    conn = get_db()

    enrollment = conn.execute(
        "SELECT * FROM lms_enrollments WHERE course_id = ? AND user_id = ?",
        (course_id, user_id),
    ).fetchone()
    lesson = conn.execute("SELECT * FROM lms_lessons WHERE id = ?", (lesson_id,)).fetchone()

    if not enrollment or not lesson:
        conn.close()
        return lms_page('<div class="page"><div class="empty"><p>Không truy cập được Lesson này</p></div></div>',
                         active="my-courses"), 403

    quiz_questions = []
    if lesson["content_type"] == "quiz":
        quiz_questions = conn.execute(
            "SELECT * FROM lms_quiz_questions WHERE lesson_id = ? ORDER BY order_index, id",
            (lesson_id,),
        ).fetchall()

    if request.method == "POST":
        score = None
        if lesson["content_type"] == "quiz" and quiz_questions:
            correct = 0
            for q in quiz_questions:
                selected = request.form.get(f"answer_{q['id']}", "").strip()
                if selected == q["correct_answer"]:
                    correct += 1
            score = round(correct * 100 / len(quiz_questions))

        conn.execute(
            """INSERT INTO lms_lesson_progress (enrollment_id, lesson_id, status, score)
               VALUES (?, ?, 'done', ?)
               ON CONFLICT(enrollment_id, lesson_id)
               DO UPDATE SET status='done', score=excluded.score""",
            (enrollment["id"], lesson_id, score),
        )
        conn.commit()
        recompute_progress(conn, enrollment["id"])
        conn.close()
        return redirect(url_for("lms_enrollment.learn_course", course_id=course_id))

    conn.close()

    if lesson["content_type"] == "quiz" and quiz_questions:
        blocks = []
        for i, q in enumerate(quiz_questions, start=1):
            choices = [q["correct_answer"]] + [
                c.strip() for c in (q["wrong_choices"] or "").split("|") if c.strip()
            ]
            choices_html = "".join(
                f'<label style="display:block;margin-bottom:.4rem;">'
                f'<input type="radio" name="answer_{q["id"]}" value="{c}" required> {c}</label>'
                for c in choices
            )
            blocks.append(
                f'<div style="margin-bottom:1.25rem;">'
                f'<p style="margin-bottom:.6rem;font-weight:600;">{i}. {q["question_text"]}</p>'
                f'{choices_html}</div>'
            )
        body = f"""
          <div class="card">
            <form method="POST">
              {''.join(blocks)}
              <button class="btn btn-primary" type="submit" style="margin-top:.5rem;">Nộp bài</button>
            </form>
          </div>
        """
    elif lesson["content_type"] == "quiz":
        body = """
          <div class="card">
            <div class="empty"><p>Quiz này chưa có câu hỏi nào — nhờ instructor thêm câu hỏi trước.</p></div>
          </div>
        """
    else:
        media_html = _render_lesson_media(lesson["content_type"], lesson["content_url"])
        text_html = f'<p>{lesson["content_body"]}</p>' if lesson["content_body"] else ""
        body = f"""
          <div class="card">
            {media_html}
            {text_html}
            <form method="POST" style="margin-top:1.5rem;">
              <button class="btn btn-primary" type="submit">✓ Đánh dấu hoàn thành</button>
            </form>
          </div>
        """

    content = f"""
    <div class="page">
      <div class="page-header"><h1>{lesson['title']}</h1></div>
      {body}
    </div>
    """
    return lms_page(content, active="my-courses", title=lesson["title"])
