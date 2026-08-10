# VNGG LMS

Standalone Learning Management System, extracted from `VNGG_ATS-` in 2026-08.

## Chạy local

```bash
pip install -r app/requirements.txt
python -c "from app.main import app; app.run(port=5000)"
```

Mở `http://127.0.0.1:5000/` → tự redirect về `/lms/`.

## Cấu trúc

```
VNGG_LMS/
  app/
    main.py         Flask entry point, mount 3 Blueprints, redirect / -> /lms/
    shared.py       get_db(), BASE_STYLE, BASE_JS. DB file = lms.db in repo root.
    requirements.txt
  modules/
    lms/
      __init__.py
      routes.py     Course Management (Dashboard/Programs/Courses/Lessons/Quiz editor)
      enrollment.py Enrollment Engine (Learners/Enroll/My Courses/Learn/Login/Logout)
      reports.py    Reporting (progress dashboard + CSV export)
      schema.sql    lms_programs / lms_courses / lms_lessons / lms_quiz_questions
                    / lms_users / lms_enrollments / lms_lesson_progress
      SETUP.md      chi tiết setup + trạng thái/còn nợ
```

## Điểm khác biệt so với bản trong ATS

- DB file `lms.db` (không dùng chung `ats.db` nữa).
- Env var cấu hình secret: `VNGG_LMS_SECRET_KEY` (thay cho `VNGG_SECRET_KEY`).
- Nav brand đổi từ "VNGG ATS / LMS" → "VNGG LMS".
- Không còn phụ thuộc/import gì từ ATS.

Chi tiết flow test xem [modules/lms/SETUP.md](modules/lms/SETUP.md).
