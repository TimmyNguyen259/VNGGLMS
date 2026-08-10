# LMS Core — Setup Note

Standalone repo. Xem [`../../README.md`](../../README.md) cho cách chạy nhanh.

## Cấu trúc

```
app/
  main.py          Flask entry, mount 4 Blueprints, redirect / -> /lms/, init_sso()
  shared.py        get_db(), BASE_STYLE, BASE_JS. DB = lms.db in repo root.
modules/lms/
  routes.py        Course Management + shared helpers (require_login/staff/admin, require_course_access)
  enrollment.py    Learners, Login (dev dropdown), My Courses, Learn, Admin view-learner
  reports.py       Reports dashboard + CSV export
  sso.py           Microsoft Entra OIDC — env-driven; no-op nếu env chưa đủ
  schema.sql       lms_programs / lms_courses (owner_id!) / lms_lessons / lms_quiz_questions
                   / lms_users / lms_enrollments / lms_lesson_progress
```

## Roles & quyền

| Route | Learner | Instructor | Admin |
|---|:-:|:-:|:-:|
| `/lms/`, `/lms/login` | ✓ | ✓ | ✓ |
| `/lms/my-courses`, `/lms/courses/<id>/learn*` | ✓ (enroll gated) | ✓ | ✓ |
| `/lms/courses` (list) | 403 | Only own (owner_id = self) | All |
| `/lms/courses/<id>` (edit lessons) | 403 | Only if owner | All |
| `/lms/lessons/<id>/questions` | 403 | Only if owner of parent course | All |
| `/lms/courses/<id>/learners` (assign) | 403 | Only if owner | All |
| `/lms/reports`, `.csv` | 403 | Scoped to own courses | All |
| `/lms/programs`, `/lms/learners`, `/lms/learners/<id>` | 403 | 403 | ✓ |

Instructor không thấy Programs/Learners tabs trong nav. Nav Courses/Reports tabs
đổi tên thành "My Courses (Teach)" / "Reports" cho instructor.

## Auth

### Dev dropdown
Mặc định `/lms/login` hiển thị dropdown pick 1 `lms_users` row → set `session["lms_user_id/name/role"]`. Dùng khi build/test local.

### Microsoft Entra SSO (production)
Set 3 env vars → nút "Đăng nhập bằng Microsoft" hiện trên `/lms/login`, dropdown vẫn còn dùng làm dev fallback:

```bash
export SSO_TENANT_ID="<Entra tenant GUID>"          # vd 72f988bf-... hoặc "common"
export SSO_CLIENT_ID="<Application (client) ID>"
export SSO_CLIENT_SECRET="<Client secret>"
# tuỳ chọn:
export SSO_REDIRECT_URI="https://lms.vng.com.vn/lms/sso/callback"
export SSO_ALLOWED_DOMAIN="vng.com.vn"
export SSO_ADMIN_EMAILS="cto@vng.com.vn,hr-head@vng.com.vn"
export VNGG_LMS_SECRET_KEY="<long random string>"    # bắt buộc đổi ở prod
```

Đăng ký app ở Entra:
1. Azure Portal → Entra ID → App registrations → New registration
2. Redirect URI (Web): `https://<host>/lms/sso/callback`
3. Certificates & secrets → New client secret
4. API permissions → Add: `openid`, `profile`, `email` (Delegated, Microsoft Graph)
5. Copy Tenant ID / Client ID / Secret vào env

Lần đầu login: tự động tạo row trong `lms_users` (email + name từ Entra),
role='learner' (hoặc 'admin' nếu email nằm trong `SSO_ADMIN_EMAILS`).

## Test checklist

```
Admin flow:
1. /lms/login → SSO hoặc dropdown pick admin
2. /lms/programs → tạo Program
3. /lms/courses → tạo Course (owner_id = NULL)
4. /lms/learners → thêm learner
5. /lms/courses/<id>/learners → gán learner vào course
6. /lms/reports → xem tất cả progress + export CSV

Instructor flow:
7. Login as instructor → chỉ thấy Courses/Reports (không thấy Programs/Learners)
8. Tạo Course → owner_id = self
9. Không mở được course của instructor khác (403)
10. Reports chỉ show course của mình

Learner flow:
11. Login as learner → chỉ thấy Dashboard + My Courses
12. /lms/my-courses → xem course được gán
13. Học từng lesson (text/video/pdf/quiz), video YouTube+Vimeo embed inline, PDF viewer inline
14. Logout, đăng nhập account khác → progress không mix
```
