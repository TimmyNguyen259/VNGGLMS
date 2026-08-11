"""SSO env on/off routing — không thực sự nói chuyện với Entra, chỉ xác nhận:
- Khi env unset: /lms/sso/* trả 401 'chưa cấu hình', nút SSO không hiện
- Khi env set:   /lms/sso/login redirect đến login.microsoftonline.com với đúng
                 tenant/client_id/scope; nút SSO hiện trên /lms/login
"""


# ------------------------------------------------------------------
# SSO OFF (env unset — default trong test)
# ------------------------------------------------------------------

def test_sso_off_login_page_hides_button(client, seed, monkeypatch):
    for k in ("SSO_TENANT_ID", "SSO_CLIENT_ID", "SSO_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    body = client.get("/lms/login").data.decode()
    assert "Đăng nhập bằng Microsoft" not in body
    assert "-- Chọn learner --" in body  # dropdown vẫn còn


def test_sso_off_sso_login_returns_error(client, seed, monkeypatch):
    for k in ("SSO_TENANT_ID", "SSO_CLIENT_ID", "SSO_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    r = client.get("/lms/sso/login")
    assert r.status_code == 401
    assert b"ch\xc6\xb0a \xc4\x91\xc6\xb0\xe1\xbb\xa3c c\xe1\xba\xa5u h\xc3\xacnh" in r.data or \
           "chưa được cấu hình".encode() in r.data


# ------------------------------------------------------------------
# SSO ON
# ------------------------------------------------------------------

def test_sso_on_login_page_shows_button(client, seed, monkeypatch):
    monkeypatch.setenv("SSO_TENANT_ID", "common")
    monkeypatch.setenv("SSO_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("SSO_CLIENT_SECRET", "test-secret")
    # init_sso() đã chạy khi import app.main. Test này chỉ verify nút hiển thị
    # dựa vào is_sso_configured() — điều kiện kiểm tra env, không cần re-init.
    body = client.get("/lms/login").data.decode()
    assert "Đăng nhập bằng Microsoft" in body
    assert "-- Chọn learner --" in body  # dropdown vẫn giữ làm dev fallback


def test_sso_on_login_redirects_to_entra(client, seed, monkeypatch):
    """Khi env set, /lms/sso/login redirect về endpoint OIDC của Entra với đúng
    tenant/client_id trong URL. Cần re-init OAuth registry với env test."""
    monkeypatch.setenv("SSO_TENANT_ID", "common")
    monkeypatch.setenv("SSO_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("SSO_CLIENT_SECRET", "test-secret")

    from modules.lms import sso as sso_mod
    from app.main import app
    sso_mod.init_sso(app)

    r = client.get("/lms/sso/login")
    assert r.status_code == 302
    loc = r.headers["Location"]
    assert "login.microsoftonline.com" in loc
    assert "/common/" in loc
    assert "client_id=test-client-id" in loc
    assert "openid" in loc  # scope


def test_sso_provisions_new_user_as_learner_by_default(app, monkeypatch):
    """First-time SSO login tạo lms_users row với role='learner' (trừ khi email
    ∈ SSO_ADMIN_EMAILS). Test hàm _provision_user trực tiếp — không đi qua OIDC flow."""
    from modules.lms.sso import _provision_user
    from app.shared import get_db

    monkeypatch.delenv("SSO_ADMIN_EMAILS", raising=False)
    uid, role = _provision_user("new-user@vng.com.vn", "New User")
    assert role == "learner"

    conn = get_db()
    row = conn.execute("SELECT * FROM lms_users WHERE id = ?", (uid,)).fetchone()
    conn.close()
    assert row["email"] == "new-user@vng.com.vn"
    assert row["role"] == "learner"


def test_sso_admin_emails_env_promotes_to_admin(app, monkeypatch):
    from modules.lms.sso import _provision_user
    monkeypatch.setenv("SSO_ADMIN_EMAILS", "boss@vng.com.vn, cto@vng.com.vn")

    _, role_boss = _provision_user("boss@vng.com.vn", "Boss")
    _, role_reg = _provision_user("nobody@vng.com.vn", "Reg User")

    assert role_boss == "admin"
    assert role_reg == "learner"


def test_sso_repeat_login_reuses_user_no_duplicate(app, monkeypatch):
    from modules.lms.sso import _provision_user
    from app.shared import get_db

    uid1, _ = _provision_user("dup@vng.com.vn", "Dup User")
    uid2, _ = _provision_user("dup@vng.com.vn", "Dup User Renamed")
    assert uid1 == uid2

    conn = get_db()
    n = conn.execute("SELECT COUNT(*) c FROM lms_users WHERE email='dup@vng.com.vn'").fetchone()["c"]
    updated_name = conn.execute("SELECT name FROM lms_users WHERE email='dup@vng.com.vn'").fetchone()["name"]
    conn.close()
    assert n == 1
    assert updated_name == "Dup User Renamed"  # tên mới được cập nhật
