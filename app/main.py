"""VNGG LMS — standalone Learning Management System.

Extracted from VNGG_ATS-. Runs as its own Flask app with its own SQLite DB
(lms.db in repo root). All LMS routes live under /lms/* so no changes to
existing hard-coded links were needed; root / redirects to /lms/.
"""
import os
import sys

# Make repo root importable so `from app.shared` and `from modules.lms.*` resolve
# regardless of where Python was launched from.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from flask import Flask, redirect  # noqa: E402

from modules.lms.routes import lms_bp, init_lms_db  # noqa: E402
from modules.lms.enrollment import enrollment_bp  # noqa: E402
from modules.lms.reports import reports_bp  # noqa: E402
from modules.lms.sso import sso_bp, init_sso  # noqa: E402

app = Flask(__name__)
# Dev-only secret for session cookies. Override via env var in real deployments.
app.secret_key = os.environ.get("VNGG_LMS_SECRET_KEY", "vngg-lms-dev-secret-change-me")

init_lms_db()
sso_enabled = init_sso(app)  # no-op nếu env SSO_* chưa đủ

app.register_blueprint(lms_bp)
app.register_blueprint(enrollment_bp)
app.register_blueprint(reports_bp)
app.register_blueprint(sso_bp)


@app.route("/")
def home():
    return redirect("/lms/")


@app.route("/health")
def health():
    return {"status": "ok", "app": "vngg-lms", "version": "0.1.0"}


if __name__ == "__main__":
    app.run(debug=True, port=5000)
