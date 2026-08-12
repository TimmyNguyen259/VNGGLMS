# VNGG LMS

Standalone Learning Management System, extracted from `VNGG_ATS-` in 2026-08.

## Chạy local

```bash
pip install -r app/requirements.txt
python -c "from app.main import app; app.run(port=5000)"
```

Mở `http://127.0.0.1:5000/` → tự redirect `/lms/`. Login dùng dropdown ở `/lms/login`
(pick 1 learner đã seed).

## Chạy test

```bash
pip install -r app/requirements-dev.txt
pytest
```

51 test cover: RBAC + instructor scoping (17), quiz scoring/migration/progress (6), media embed (13), SSO on/off routing + user provisioning (7), + 8 anon-redirect params.

CI: `.github/workflows/test.yml` chạy pytest tự động trên push + PR.

## Chạy bằng Docker

```bash
cp .env.example .env             # điền secret, SSO config nếu cần
docker compose up --build
```

Mở `http://localhost:8000/`. Container:
- Base image `python:3.12-slim`
- gunicorn 2 workers, bind `0.0.0.0:8000`
- SQLite DB ở `/data/lms.db` (volume `lms-data` persist qua restart)
- Env var `LMS_DB_PATH` override được nếu cần path khác

Build image tay không dùng compose:

```bash
docker build -t vngg-lms .
docker run --rm -p 8000:8000 -v vngg-lms-data:/data --env-file .env vngg-lms
```

## Deploy lên Fly.io

`fly.toml` cấu hình sẵn (Singapore region, 256MB, volume cho SQLite). Xem [DEPLOY.md](DEPLOY.md) cho từng bước:
- Cài `flyctl`
- `flyctl auth login` (browser)
- `flyctl launch --no-deploy`
- `flyctl volumes create vngg_lms_data --region sin --size 1`
- `flyctl secrets set VNGG_LMS_SECRET_KEY=...`
- `flyctl deploy`

## Bật Microsoft Entra SSO ở production

Set 3 env vars → nút "Đăng nhập bằng Microsoft" hiện trên `/lms/login`:

```bash
export SSO_TENANT_ID="<Entra tenant GUID>"
export SSO_CLIENT_ID="<Application (client) ID>"
export SSO_CLIENT_SECRET="<Client secret>"
export SSO_ALLOWED_DOMAIN="vng.com.vn"                       # tuỳ chọn
export SSO_ADMIN_EMAILS="a@vng.com.vn,b@vng.com.vn"          # tuỳ chọn
export VNGG_LMS_SECRET_KEY="<long random string>"            # đổi khi prod
```

Đăng ký app ở Entra (Azure Portal → Entra ID → App registrations); redirect URI phải trỏ đến `https://<host>/lms/sso/callback`. Chi tiết + role matrix xem [`modules/lms/SETUP.md`](modules/lms/SETUP.md).

## Cấu trúc

```
VNGG_LMS/
  app/
    main.py         Flask entry, mount 4 Blueprints, redirect / -> /lms/
    shared.py       get_db(), BASE_STYLE, BASE_JS. DB file = lms.db in repo root.
    requirements.txt
  modules/
    lms/
      routes.py     Course Management + auth helpers (require_login/staff/admin/course_access)
      enrollment.py Learners, Login/Logout, My Courses, Learn, Admin view-learner
      reports.py    Reporting dashboard + CSV export (scoped by owner for instructors)
      sso.py        Microsoft Entra OIDC integration (env-driven)
      schema.sql    7 tables — lms_programs, lms_courses (with owner_id), lms_lessons,
                    lms_quiz_questions, lms_users, lms_enrollments, lms_lesson_progress
      SETUP.md      Role matrix + full test checklist
```

## Các điểm khác so với bản trong ATS

- DB file `lms.db` (không dùng chung `ats.db` nữa)
- Env var cấu hình secret: `VNGG_LMS_SECRET_KEY` (thay cho `VNGG_SECRET_KEY`)
- Nav brand đổi "VNGG ATS / LMS" → "VNGG LMS"
- Có thêm SSO integration (`modules/lms/sso.py`)
- Instructor-scoped RBAC (`owner_id` column trên `lms_courses`)
- Không còn phụ thuộc gì từ ATS
