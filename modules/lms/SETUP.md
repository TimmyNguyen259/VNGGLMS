# LMS Core — Setup Note

## Cấu trúc file trong repo `VNGG_ATS-`

```
modules/
  lms/
    __init__.py       (rỗng)
    schema.sql
    routes.py         Course Management (Dashboard/Programs/Courses/Lessons/Quiz editor)
    enrollment.py     Enrollment Engine (Learners/Enroll/My Courses/Learn/Login)
    reports.py        Reporting (Dashboard progress + Export CSV)
```

## Đăng ký Blueprint trong `app/main.py`

```python
from modules.lms.routes import lms_bp, init_lms_db
from modules.lms.enrollment import enrollment_bp
from modules.lms.reports import reports_bp

app.secret_key = os.environ.get("VNGG_SECRET_KEY", "vngg-ats-dev-secret-change-me")

app.register_blueprint(lms_bp)
app.register_blueprint(enrollment_bp)
app.register_blueprint(reports_bp)

init_lms_db()  # tạo bảng lms_* + migrate quiz cũ (nếu có)
```

Landing card `E — LMS` đã có sẵn trong `MODULES` list.

## Trạng thái hiện tại

### Đã xong

1. **Import path** — `from app.shared import ...` khớp với cấu trúc thật (repo root đã prepend vào `sys.path` trong `main.py`).
2. **Session-based auth (stopgap)** — `/lms/login` chọn learner từ dropdown, lưu vào `session["lms_user_id"]`. Ba route `my-courses` / `learn` / `learn/<lesson>` gọi `_require_login()` → 302 về `/lms/login?next=…` nếu chưa login. URL tampering không còn tick lesson hộ người khác được.
3. **Light theme (cream + orange)** — token trong `app/shared.py:19-38`. Heading font `Space Grotesk`, body `DM Sans`. Áp dụng chung cho cả `scheduling` module.
4. **Multi-question quiz** — bảng `lms_quiz_questions` (schema.sql:65). 1 quiz lesson chứa nhiều câu hỏi, mỗi câu có đáp án đúng + lựa chọn sai (phân cách `|`). Điểm = `correct / total * 100`. Editor tại `/lms/lessons/<id>/questions`.
5. **Legacy quiz migration** — `_migrate_legacy_quiz_body()` chạy trong `init_lms_db()`: quiz cũ lưu dạng chuỗi `"Q ||| correct ||| A | B"` trong `content_body` được lift sang bảng câu hỏi mới. Idempotent — chạy lại nhiều lần không double.
6. **Admin view-learner** — `/lms/learners/<user_id>` (read-only) hiển thị tiến độ chi tiết từng lesson cho 1 learner, dùng cho admin không muốn login-as.

### Còn nợ trước khi launch thật

1. **SSO thay cho session dropdown** — hiện `/lms/login` chỉ liệt kê tất cả learner cho ai vào cũng chọn được. Cần thay bằng auth thật (OAuth/SAML/etc.) trước production. Session cookie đang dùng dev secret key — set `VNGG_SECRET_KEY` env var trong deployment.
2. **RBAC cho admin routes** — `/lms/programs`, `/lms/courses`, `/lms/learners`, `/lms/reports` hiện không có gate. Ai vào cũng tạo/sửa/xoá được. Cần role check khi có SSO.
3. **Light theme là do Claude Code phác** — mockup Dashboard/Jobs/Pipeline gốc không có trong repo. Nếu design team có file CSS/hình ảnh chính thức, thay giá trị token trong `shared.py:19-38` cho khớp.

## Test nhanh (checklist)

```
Setup:
1. /lms/programs        → tạo Program "NextGen 2026"
2. /lms/courses         → tạo Course thuộc Program đó
3. /lms/courses/<id>    → thêm 2-3 Lesson (text + 1 quiz)
4. /lms/lessons/<id>/questions  → thêm nhiều câu hỏi cho quiz lesson
5. /lms/learners        → thêm 2 Learner
6. /lms/courses/<id>/learners   → gán cả 2 Learner vào Course

Learner flow:
7. /lms/login           → chọn learner 1 (Alice)
8. /lms/my-courses      → thấy course được gán
9. Học từng lesson, mark done, làm quiz
10. Logout → đăng nhập learner 2 (Bob) → xác nhận Bob progress vẫn = 0
    (chứng tỏ URL tampering không tick hộ được)

Admin flow:
11. /lms/learners/1     → xem tiến độ chi tiết Alice (progress bar + per-lesson status + quiz score)
12. /lms/reports        → xem % progress cấp Program/Course
13. /lms/reports/export.csv → tải CSV
```
