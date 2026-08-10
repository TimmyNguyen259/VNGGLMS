"""
LMS Core — Module: Reporting (UC-05, UC-06)
Blueprint riêng, tái dùng lms_page() từ routes.py. Không thêm bảng mới —
chỉ query lms_enrollments/lms_courses/lms_programs đã có.
"""
import csv
import io
from flask import Blueprint, request, Response, session

from app.shared import get_db
from .routes import lms_page, require_staff, is_instructor

reports_bp = Blueprint("lms_reports", __name__, url_prefix="/lms")


def _scoped_owner_id():
    """Trả về user_id nếu request đến từ instructor (dùng để filter),
    None nếu là admin (không filter)."""
    return session.get("lms_user_id") if is_instructor() else None


def _fetch_report_rows(conn, program_id=None, owner_id=None):
    query = """
        SELECT p.id program_id, p.name program_name,
               c.id course_id, c.title course_title,
               COUNT(e.id) learner_count,
               SUM(CASE WHEN e.status = 'completed' THEN 1 ELSE 0 END) completed_count,
               COALESCE(ROUND(AVG(e.progress_pct)), 0) avg_progress
        FROM lms_programs p
        JOIN lms_courses c ON c.program_id = p.id
        LEFT JOIN lms_enrollments e ON e.course_id = c.id
    """
    where, params = [], []
    if program_id:
        where.append("p.id = ?"); params.append(program_id)
    if owner_id is not None:
        where.append("c.owner_id = ?"); params.append(owner_id)
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " GROUP BY c.id ORDER BY p.name, c.title"
    return conn.execute(query, tuple(params)).fetchall()


# ------------------------------------------------------------------
# UC-05 — Dashboard tiến độ theo Program/Course
# ------------------------------------------------------------------

@reports_bp.route("/reports")
def reports():
    gate = require_staff()
    if gate: return gate
    conn = get_db()
    program_id = request.args.get("program_id")
    programs_list = conn.execute("SELECT id, name FROM lms_programs ORDER BY name").fetchall()
    rows = _fetch_report_rows(conn, program_id, owner_id=_scoped_owner_id())
    conn.close()

    program_options = '<option value="">-- Tất cả Program --</option>' + "".join(
        f'<option value="{p["id"]}" {"selected" if str(p["id"]) == str(program_id) else ""}>{p["name"]}</option>'
        for p in programs_list
    )

    def fill_rate_class(pct):
        if pct >= 80:
            return "green"
        if pct >= 50:
            return "amber"
        return "red"

    rows_html = "".join(
        f"""<tr>
              <td>{r['program_name']}</td>
              <td><strong>{r['course_title']}</strong></td>
              <td>{r['learner_count']}</td>
              <td>{r['completed_count']}</td>
              <td>
                <div class="score-bar">
                  <div class="score-bar-track"><div class="score-bar-fill" style="width:{r['avg_progress']}%"></div></div>
                  <div class="score-num">{r['avg_progress']}%</div>
                </div>
              </td>
            </tr>"""
        for r in rows
    ) or '<tr><td colspan="5"><div class="empty"><p>Chưa có dữ liệu enrollment</p></div></td></tr>'

    total_learners = sum(r["learner_count"] for r in rows) if rows else 0
    total_completed = sum(r["completed_count"] for r in rows) if rows else 0
    overall_pct = int(round((total_completed / total_learners) * 100)) if total_learners else 0

    export_link = f"/lms/reports/export.csv" + (f"?program_id={program_id}" if program_id else "")

    content = f"""
    <div class="page">
      <div class="page-header">
        <h1>Reports</h1>
        <p>Tiến độ học tập theo Program/Course — dùng để báo cáo KPI H2</p>
      </div>

      <div class="stats-row">
        <div class="stat-pill blue"><div class="val">{total_learners}</div><div class="lbl">Tổng Enrollment</div></div>
        <div class="stat-pill green"><div class="val">{total_completed}</div><div class="lbl">Completed</div></div>
        <div class="stat-pill orange"><div class="val">{overall_pct}%</div><div class="lbl">Completion Rate</div></div>
      </div>

      <div class="card" style="display:flex;justify-content:space-between;align-items:center;gap:1rem;flex-wrap:wrap;">
        <form method="GET" style="display:flex;gap:.75rem;align-items:center;">
          <select class="form-control" name="program_id" onchange="this.form.submit()">{program_options}</select>
        </form>
        <a class="btn btn-primary" href="{export_link}">⬇ Export CSV</a>
      </div>

      <div class="card table-wrap">
        <table>
          <thead><tr><th>Program</th><th>Course</th><th>Learners</th><th>Completed</th><th>Avg Progress</th></tr></thead>
          <tbody>{rows_html}</tbody>
        </table>
      </div>
    </div>
    """
    return lms_page(content, active="reports", title="Reports")


# ------------------------------------------------------------------
# UC-06 — Export CSV phục vụ báo cáo KPI
# ------------------------------------------------------------------

@reports_bp.route("/reports/export.csv")
def export_csv():
    gate = require_staff()
    if gate: return gate
    program_id = request.args.get("program_id")
    conn = get_db()

    # Chi tiết từng learner (không chỉ tổng hợp theo course) — đúng field
    # cần cho KPI: tên học viên, course, % progress, trạng thái, ngày hoàn thành
    query = """
        SELECT p.name program_name, c.title course_title, u.name learner_name,
               u.email learner_email, e.progress_pct, e.status,
               e.enrolled_at, e.completed_at
        FROM lms_enrollments e
        JOIN lms_courses c ON c.id = e.course_id
        JOIN lms_programs p ON p.id = c.program_id
        JOIN lms_users u ON u.id = e.user_id
    """
    where, params = [], []
    if program_id:
        where.append("p.id = ?"); params.append(program_id)
    owner_id = _scoped_owner_id()
    if owner_id is not None:
        where.append("c.owner_id = ?"); params.append(owner_id)
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY p.name, c.title, u.name"
    rows = conn.execute(query, tuple(params)).fetchall()
    conn.close()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "Program", "Course", "Learner Name", "Learner Email",
        "Progress %", "Status", "Enrolled At", "Completed At",
    ])
    for r in rows:
        writer.writerow([
            r["program_name"], r["course_title"], r["learner_name"], r["learner_email"],
            r["progress_pct"], r["status"], r["enrolled_at"], r["completed_at"] or "",
        ])

    filename = "lms_report" + (f"_program_{program_id}" if program_id else "") + ".csv"
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
