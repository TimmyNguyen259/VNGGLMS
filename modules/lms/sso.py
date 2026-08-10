"""
LMS Core — Module: SSO (Microsoft Entra / Azure AD via OIDC)

Kích hoạt khi 3 env var được set:
  SSO_TENANT_ID       — Entra tenant GUID
  SSO_CLIENT_ID       — Application (client) ID
  SSO_CLIENT_SECRET   — Client secret (đăng ký ở "Certificates & secrets")

Env var tuỳ chọn:
  SSO_REDIRECT_URI    — mặc định lấy từ url_for('lms_sso.callback', _external=True).
                        Set khi deploy sau reverse proxy để tránh https/http mismatch.
  SSO_ALLOWED_DOMAIN  — chặn login nếu email không nằm trong domain này (vd 'vng.com.vn').
                        Nên set khi dùng tenant multi-tenant hoặc cho khách vãng lai.
  SSO_ADMIN_EMAILS    — csv các email được auto-promote role='admin' khi provision lần đầu.

Không set env -> SSO tắt, /lms/login vẫn hoạt động với dropdown cũ.
Khi bật, /lms/login xuất hiện thêm nút "Đăng nhập bằng Microsoft".
"""
import os
from flask import Blueprint, redirect, url_for, session, request

from app.shared import get_db
from .routes import lms_page

sso_bp = Blueprint("lms_sso", __name__, url_prefix="/lms/sso")

_oauth = None  # authlib OAuth registry, init trong init_sso()


def is_sso_configured():
    return all(os.environ.get(k) for k in ("SSO_TENANT_ID", "SSO_CLIENT_ID", "SSO_CLIENT_SECRET"))


def init_sso(app):
    """Đăng ký provider 'entra' với authlib. Gọi từ main.py sau khi Flask() được tạo.
    No-op nếu env chưa đủ hoặc authlib chưa cài."""
    global _oauth
    if not is_sso_configured():
        return False
    try:
        from authlib.integrations.flask_client import OAuth
    except ImportError:
        app.logger.warning("SSO env đã set nhưng authlib chưa cài — pip install Authlib để bật SSO.")
        return False

    tenant = os.environ["SSO_TENANT_ID"]
    _oauth = OAuth(app)
    _oauth.register(
        name="entra",
        client_id=os.environ["SSO_CLIENT_ID"],
        client_secret=os.environ["SSO_CLIENT_SECRET"],
        server_metadata_url=f"https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration",
        client_kwargs={"scope": "openid profile email"},
    )
    return True


def _entra_client():
    if _oauth is None:
        return None
    return _oauth.create_client("entra")


@sso_bp.route("/login")
def login():
    client = _entra_client()
    if client is None:
        return _error_page("SSO chưa được cấu hình. Set SSO_TENANT_ID/SSO_CLIENT_ID/SSO_CLIENT_SECRET rồi restart app.")
    redirect_uri = os.environ.get("SSO_REDIRECT_URI") or url_for("lms_sso.callback", _external=True)
    # Lưu next để callback biết redirect về đâu sau khi provision
    next_url = request.args.get("next", "")
    if next_url:
        session["lms_sso_next"] = next_url
    return client.authorize_redirect(redirect_uri)


@sso_bp.route("/callback")
def callback():
    client = _entra_client()
    if client is None:
        return _error_page("SSO chưa được cấu hình.")

    try:
        token = client.authorize_access_token()
    except Exception as e:
        return _error_page(f"OIDC callback lỗi: {e}")

    userinfo = token.get("userinfo") or {}
    if not userinfo:
        # Fallback: gọi userinfo endpoint
        try:
            userinfo = client.userinfo(token=token)
        except Exception:
            userinfo = {}

    email = (userinfo.get("email") or userinfo.get("preferred_username") or "").lower().strip()
    name = userinfo.get("name") or email.split("@")[0] if email else ""
    if not email:
        return _error_page("Không lấy được email từ tài khoản Microsoft. Kiểm tra scope 'email' ở Entra app.")

    allowed = os.environ.get("SSO_ALLOWED_DOMAIN", "").lower().strip()
    if allowed and not email.endswith("@" + allowed):
        return _error_page(f"Tài khoản {email} không thuộc domain @{allowed}. Liên hệ admin để được cấp quyền.")

    user_id, role = _provision_user(email, name)

    session["lms_user_id"] = user_id
    session["lms_user_name"] = name
    session["lms_user_role"] = role

    next_url = session.pop("lms_sso_next", "") or url_for("lms_enrollment.my_courses")
    return redirect(next_url)


def _provision_user(email, name):
    """Lookup lms_users by email. Nếu chưa có -> tạo mới với role='learner'
    (trừ khi email nằm trong SSO_ADMIN_EMAILS -> role='admin').
    Trả về (user_id, role)."""
    admin_emails = {e.strip().lower() for e in os.environ.get("SSO_ADMIN_EMAILS", "").split(",") if e.strip()}
    default_role = "admin" if email in admin_emails else "learner"

    conn = get_db()
    row = conn.execute("SELECT id, name, role FROM lms_users WHERE lower(email) = ?", (email,)).fetchone()
    if row is None:
        cur = conn.execute(
            "INSERT INTO lms_users (email, name, role) VALUES (?, ?, ?)",
            (email, name or email.split("@")[0], default_role),
        )
        conn.commit()
        user_id, role = cur.lastrowid, default_role
    else:
        user_id, role = row["id"], row["role"]
        # Cập nhật tên nếu Entra trả về tên mới hơn tên đang lưu
        if name and name != row["name"]:
            conn.execute("UPDATE lms_users SET name = ? WHERE id = ?", (name, user_id))
            conn.commit()
    conn.close()
    return user_id, role


def _error_page(msg):
    return lms_page(
        f'<div class="page"><div class="card"><div class="empty">'
        f'<div class="icon">🚫</div>'
        f'<p>Đăng nhập thất bại — {msg}</p>'
        f'<p><a href="/lms/login" class="btn btn-ghost btn-sm" style="margin-top:.75rem;">← Quay lại</a></p>'
        f'</div></div></div>',
        active="", title="SSO error"), 401
