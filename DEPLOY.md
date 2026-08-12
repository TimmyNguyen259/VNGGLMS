# Deploy VNGG_LMS lên Fly.io

Fly.io free tier đủ cho 1 app nhỏ (256MB RAM, shared CPU, 1GB volume).
`fly.toml` đã cấu hình sẵn, chỉ cần chạy CLI.

## Bước 1 — Cài flyctl

Windows PowerShell:
```powershell
iwr https://fly.io/install.ps1 -useb | iex
```

macOS/Linux:
```bash
curl -L https://fly.io/install.sh | sh
```

Sau khi cài, khởi động lại terminal để `flyctl` vào PATH. Xác nhận:
```bash
flyctl version
```

## Bước 2 — Login (mở browser)

```bash
flyctl auth login
```

Lần đầu chưa có account thì `flyctl auth signup`. Free tier không yêu cầu credit card
cho các plan cơ bản, nhưng có thể cần verify SMS.

## Bước 3 — Tạo app

```bash
cd VNGG_LMS
flyctl launch --no-deploy
```

flyctl sẽ:
- Đọc `fly.toml`, hỏi có muốn giữ config không → **Y**
- Hỏi tên app (mặc định `vngg-lms`; nếu bị trùng, thêm hậu tố như `vngg-lms-vng`)
- Hỏi region → giữ `sin` (Singapore, gần VN nhất)
- Hỏi có tạo Postgres/Redis không → **N**
- Không deploy vì có `--no-deploy` (mình muốn tạo volume trước)

Nếu app tên khác `vngg-lms`, mở `fly.toml` sửa dòng `app = ...` cho khớp.

## Bước 4 — Tạo volume cho SQLite

```bash
flyctl volumes create vngg_lms_data --region sin --size 1
```

`fly.toml` đã mount volume này vào `/data` (nơi SQLite lưu `lms.db`). Không có
volume thì mỗi lần deploy sẽ mất data.

## Bước 5 — Set secrets

```bash
flyctl secrets set VNGG_LMS_SECRET_KEY="$(openssl rand -hex 32)"
```

Nếu bật SSO Entra:
```bash
flyctl secrets set \
  SSO_TENANT_ID="<tenant>" \
  SSO_CLIENT_ID="<client_id>" \
  SSO_CLIENT_SECRET="<secret>" \
  SSO_ALLOWED_DOMAIN="vng.com.vn"
```

Nhớ đăng ký callback URL ở Entra: `https://<app-name>.fly.dev/lms/sso/callback`.

## Bước 6 — Deploy

```bash
flyctl deploy
```

Fly build Docker image, push lên registry của họ, provision máy, mount volume, start.
Log realtime trực tiếp trong terminal. Xong sẽ hiện `--> Machine started successfully`.

## Bước 7 — Kiểm tra

```bash
flyctl status
flyctl logs
flyctl open       # mở browser vào https://<app-name>.fly.dev
```

`/health` phải trả `{"status":"ok","app":"vngg-lms","version":"0.1.0"}`.

## Update sau deploy đầu

Sau mỗi commit local:
```bash
flyctl deploy
```

Fly rebuild image + rolling update. Volume `/data/lms.db` giữ nguyên.

## Xoá / tạm dừng để không tốn tài nguyên

```bash
flyctl scale count 0            # tắt hết máy (data giữ nguyên trên volume)
flyctl scale count 1            # bật lại
flyctl apps destroy vngg-lms    # xoá hoàn toàn app + volume (irreversible)
```
