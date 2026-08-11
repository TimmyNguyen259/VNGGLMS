"""Shared infrastructure for VNGG LMS — used by app landing + module Blueprints."""
import os
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# LMS_DB_PATH env var cho phép Docker mount volume ở đường dẫn tuỳ ý (vd /data/lms.db).
# Không set -> mặc định lms.db trong repo root.
DB_PATH = os.environ.get("LMS_DB_PATH") or os.path.join(ROOT, "lms.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


BASE_STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=DM+Sans:wght@300;400;500;600;700&family=DM+Mono:wght@400;500&display=swap');

:root {
  --bg:        #faf7f2;
  --surface:   #ffffff;
  --surface2:  #f3ede4;
  --border:    #d9d1c4;
  --orange:    #e8632b;
  --amber:     #e9a306;
  --text:      #1e1b16;
  --muted:     #6f6558;
  --green:     #1e8a4a;
  --red:       #c81f2d;
  --blue:      #1f5fb0;
  --purple:    #6b4bcc;
  --radius:    10px;
  --shadow:    0 3px 12px rgba(30,27,22,.08);
  --shadow-lg: 0 6px 24px rgba(30,27,22,.14);
  --font-display: 'Space Grotesk', 'DM Sans', sans-serif;
}

* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'DM Sans',sans-serif; background:var(--bg); color:var(--text); min-height:100vh; font-size:14px; }
h1, h2, .brand, .page-header h1, .mod-card h2, .stat-pill .val {
  font-family:var(--font-display); letter-spacing:-.2px;
}

.topnav { background:var(--surface); border-bottom:1px solid var(--border);
  display:flex; align-items:center; justify-content:space-between;
  padding:.9rem 2rem; position:sticky; top:0; z-index:100; }
.topnav .brand { font-weight:700; font-size:1.1rem; letter-spacing:-.3px;
  display:flex; align-items:center; gap:.4rem; }
.topnav .brand a { color:inherit; text-decoration:none; display:flex; align-items:center; gap:.2rem; }
.topnav .brand .accent { color:var(--orange); }
.topnav .crumb { color:var(--muted); font-weight:500; font-size:.9rem; margin-left:.35rem; }
.topnav .crumb-sep { color:var(--border); margin:0 .35rem; }
.nav-links { display:flex; gap:.25rem; }
.nav-links a { color:var(--muted); text-decoration:none; padding:.45rem .85rem;
  border-radius:6px; font-weight:500; font-size:.85rem; transition:.15s; }
.nav-links a:hover, .nav-links a.active { color:var(--text); background:var(--surface2); }

.page { max-width:1120px; margin:0 auto; padding:2rem 1.5rem; }
.page-header { margin-bottom:1.75rem; }
.page-header h1 { font-size:1.6rem; font-weight:700; letter-spacing:-.4px; }
.page-header p { color:var(--muted); margin-top:.35rem; font-size:.9rem; }

.card { background:var(--surface); border:1px solid var(--border);
  border-radius:var(--radius); padding:1.5rem; box-shadow:var(--shadow); }
.card + .card { margin-top:1rem; }

.stats-row { display:flex; gap:1rem; margin-bottom:1.5rem; flex-wrap:wrap; }
.stat-pill { background:var(--surface); border:1px solid var(--border);
  border-radius:var(--radius); padding:.9rem 1.3rem; flex:1; min-width:130px; }
.stat-pill .val { font-size:1.8rem; font-weight:700; line-height:1; }
.stat-pill .lbl { color:var(--muted); font-size:.78rem; margin-top:.3rem; text-transform:uppercase; letter-spacing:.5px; }
.stat-pill.orange .val { color:var(--orange); }
.stat-pill.green  .val { color:var(--green); }
.stat-pill.blue   .val { color:var(--blue); }
.stat-pill.amber  .val { color:var(--amber); }

.table-wrap { overflow-x:auto; }
table { width:100%; border-collapse:collapse; }
th { font-weight:600; font-size:.78rem; color:var(--muted); text-transform:uppercase;
  letter-spacing:.5px; padding:.75rem 1rem; border-bottom:1px solid var(--border); text-align:left; }
td { padding:.85rem 1rem; border-bottom:1px solid var(--border); font-size:.88rem; vertical-align:middle; }
tr:last-child td { border-bottom:none; }
tr:hover td { background:rgba(232,99,43,.04); }

.badge { display:inline-flex; align-items:center; gap:.35rem; padding:.22rem .65rem;
  border-radius:20px; font-size:.75rem; font-weight:600; white-space:nowrap; }
.badge::before { content:''; width:6px; height:6px; border-radius:50%; background:currentColor; }
.badge-qualified  { background:#dcf5e4; color:var(--green); }
.badge-scheduled  { background:#dbe8ff; color:var(--blue); }
.badge-completed  { background:#e7dcff; color:var(--purple); }
.badge-cancelled  { background:#fde0e3; color:var(--red); }
.badge-pending    { background:#fff2cf; color:#8a6100; }
.badge-online     { background:#dcf5e4; color:var(--green); }
.badge-offline    { background:#fff2cf; color:#8a6100; }

.btn { display:inline-flex; align-items:center; gap:.4rem; padding:.5rem 1rem;
  border-radius:7px; font-size:.84rem; font-weight:600; cursor:pointer;
  border:none; text-decoration:none; transition:.15s; font-family:inherit; }
.btn:hover { opacity:.88; transform:translateY(-1px); }
.btn-primary { background:var(--orange); color:#fff; }
.btn-blue    { background:var(--blue);   color:#fff; }
.btn-green   { background:var(--green);  color:#fff; }
.btn-ghost   { background:var(--surface2); color:var(--text); border:1px solid var(--border); }
.btn-sm      { padding:.35rem .7rem; font-size:.78rem; }
.btn-danger  { background:var(--red); color:#fff; }
.btn-amber   { background:var(--amber); color:#0e1117; }

.form-group { margin-bottom:1.2rem; }
.form-label { display:block; font-size:.82rem; font-weight:600; color:var(--muted);
  text-transform:uppercase; letter-spacing:.5px; margin-bottom:.5rem; }
.form-control { width:100%; background:var(--surface2); border:1px solid var(--border);
  color:var(--text); border-radius:7px; padding:.65rem .85rem; font-family:inherit;
  font-size:.9rem; transition:.15s; }
.form-control:focus { outline:none; border-color:var(--orange); box-shadow:0 0 0 3px rgba(232,99,43,.15); }
.form-control option { background:var(--surface2); }
.form-row { display:grid; grid-template-columns:1fr 1fr; gap:1rem; }
.form-row-3 { display:grid; grid-template-columns:1fr 1fr 1fr; gap:1rem; }

.rating-group { display:flex; flex-direction:column; gap:.35rem; }
.rating-label { font-size:.82rem; color:var(--muted); font-weight:500; }
.stars { display:flex; gap:.25rem; }
.star { width:28px; height:28px; cursor:pointer; border-radius:5px; background:var(--surface2);
  border:1px solid var(--border); display:flex; align-items:center; justify-content:center;
  font-size:.9rem; transition:.12s; }
.star:hover, .star.active { background:var(--amber); border-color:var(--amber); }

.score-bar { display:flex; align-items:center; gap:.75rem; }
.score-bar-track { flex:1; height:6px; background:var(--surface2); border-radius:3px; overflow:hidden; }
.score-bar-fill  { height:100%; border-radius:3px; background:var(--orange); transition:.4s; }
.score-num { font-family:'DM Mono',monospace; font-size:.8rem; color:var(--muted); width:28px; text-align:right; }

.email-preview { background:var(--surface2); border:1px solid var(--border);
  border-radius:8px; padding:1.25rem; font-size:.85rem; line-height:1.7; }
.email-preview .email-field { display:flex; gap:.75rem; margin-bottom:.5rem; }
.email-preview .field-key { color:var(--muted); width:50px; flex-shrink:0; font-weight:600; font-size:.78rem; }
.email-preview .email-body { margin-top:1rem; padding-top:1rem; border-top:1px solid var(--border); }

.empty { text-align:center; padding:3rem; color:var(--muted); }
.empty .icon { font-size:2.5rem; margin-bottom:.75rem; }
.empty p { font-size:.9rem; }

.notif { position:fixed; top:1rem; right:1rem; z-index:500; display:flex; flex-direction:column; gap:.5rem; }
.notif-item { background:var(--surface); border:1px solid var(--border); border-radius:9px;
  padding:.85rem 1.1rem; font-size:.88rem; display:flex; align-items:center; gap:.6rem;
  box-shadow:var(--shadow); animation:slideIn .2s ease; min-width:280px; }
.notif-item.success { border-color:var(--green); }
.notif-item.error   { border-color:var(--red); }
@keyframes slideIn { from { opacity:0; transform:translateX(20px); } to { opacity:1; transform:translateX(0); } }

.cand-strip { display:flex; align-items:center; gap:.85rem; background:var(--surface2);
  border:1px solid var(--border); border-radius:9px; padding:.85rem 1.1rem; margin-bottom:1.5rem; }
.cand-avatar { width:40px; height:40px; border-radius:50%; background:var(--orange);
  display:flex; align-items:center; justify-content:center; font-weight:700; font-size:1rem; flex-shrink:0; }
.cand-info .name { font-weight:600; font-size:.95rem; }
.cand-info .pos  { font-size:.8rem; color:var(--muted); }
.cand-score { margin-left:auto; font-family:'DM Mono',monospace; font-size:1.1rem;
  font-weight:700; color:var(--green); }

.reco-group { display:flex; gap:.75rem; flex-wrap:wrap; }
.reco-btn { padding:.55rem 1.1rem; border-radius:7px; font-size:.84rem; font-weight:600;
  cursor:pointer; border:2px solid var(--border); background:var(--surface2); color:var(--muted);
  transition:.15s; font-family:inherit; }
.reco-btn:hover { border-color:currentColor; }
.reco-btn.selected { border-color:currentColor; }
.reco-btn.pass     { color:var(--green); }
.reco-btn.pass.selected    { background:rgba(39,194,107,.15); }
.reco-btn.hold     { color:var(--amber); }
.reco-btn.hold.selected    { background:rgba(254,195,19,.12); }
.reco-btn.reject   { color:var(--red); }
.reco-btn.reject.selected  { background:rgba(232,66,90,.12); }
.reco-btn.fail             { color:var(--red); }
.reco-btn.fail.selected    { background:rgba(232,66,90,.12); }
.reco-btn.keep_in_view             { color:var(--amber); }
.reco-btn.keep_in_view.selected    { background:rgba(254,195,19,.12); }

.icard { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius);
  padding:1.1rem 1.3rem; display:flex; align-items:center; gap:1rem; margin-bottom:.75rem; }
.icard .date-block { text-align:center; background:var(--surface2); border-radius:8px;
  padding:.5rem .75rem; min-width:56px; flex-shrink:0; }
.icard .date-block .day  { font-size:1.4rem; font-weight:700; line-height:1; }
.icard .date-block .mon  { font-size:.7rem; color:var(--muted); text-transform:uppercase; }
.icard .icard-main { flex:1; }
.icard .icard-name { font-weight:600; font-size:.95rem; }
.icard .icard-meta { font-size:.8rem; color:var(--muted); margin-top:.2rem; }
.icard .icard-actions { display:flex; gap:.5rem; flex-shrink:0; }

/* Module index cards on landing */
.module-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:1rem; }
.mod-card { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius);
  padding:1.5rem; box-shadow:var(--shadow); text-decoration:none; color:inherit; display:block;
  transition:.18s; }
.mod-card.live { border-color:var(--orange); }
.mod-card.live:hover { transform:translateY(-3px); box-shadow:0 8px 28px rgba(232,99,43,.18); }
.mod-card.coming { opacity:.55; cursor:not-allowed; }
.mod-card .mod-ico { font-size:2rem; margin-bottom:.6rem; }
.mod-card h2 { font-size:1rem; font-weight:700; margin-bottom:.4rem; letter-spacing:-.2px; }
.mod-card p { color:var(--muted); font-size:.83rem; line-height:1.55; }
.mod-card .status-line { margin-top:.85rem; font-size:.75rem; font-weight:600;
  text-transform:uppercase; letter-spacing:.4px; }
.mod-card.live .status-line { color:var(--green); }
.mod-card.coming .status-line { color:var(--muted); }
</style>
"""

BASE_JS = """
<script>
function showNotif(msg, type='success') {
  const c = document.getElementById('notif-container') || (() => {
    const el = document.createElement('div');
    el.id = 'notif-container';
    el.className = 'notif';
    document.body.appendChild(el);
    return el;
  })();
  const n = document.createElement('div');
  n.className = `notif-item ${type}`;
  n.innerHTML = `<span>${type === 'success' ? '✅' : '❌'}</span> ${msg}`;
  c.appendChild(n);
  setTimeout(() => n.remove(), 3500);
}

function setRating(field, val) {
  document.getElementById('input_'+field).value = val;
  document.querySelectorAll(`[data-field="${field}"] .star`).forEach((s,i) => {
    s.classList.toggle('active', i < val);
  });
  updateOverallRating();
}

function updateOverallRating() {
  const fields = ['technical','communication','culture_fit','problem_solving'];
  const vals = fields.map(f => parseInt(document.getElementById('input_'+f)?.value || 0));
  const filled = vals.filter(v => v > 0);
  if (filled.length === 0) return;
  const avg = Math.round(filled.reduce((a,b) => a+b, 0) / filled.length);
  document.getElementById('input_overall_rating').value = avg;
  document.querySelectorAll(`[data-field="overall_rating"] .star`).forEach((s,i) => {
    s.classList.toggle('active', i < avg);
  });
}

function setReco(val) {
  document.getElementById('input_recommendation').value = val;
  document.querySelectorAll('.reco-btn').forEach(b => {
    b.classList.toggle('selected', b.dataset.val === val);
  });
}
</script>
"""


def avatar_letter(name):
    parts = name.strip().split()
    if len(parts) >= 2:
        return parts[0][0].upper() + parts[-1][0].upper()
    return name[0].upper()


def status_badge(status):
    classes = {
        "qualified": "badge-qualified", "scheduled": "badge-scheduled",
        "completed": "badge-completed", "cancelled": "badge-cancelled",
        "pending": "badge-pending",
    }
    return f'<span class="badge {classes.get(status, "badge-pending")}">{status.capitalize()}</span>'


def scheduling_nav(active=""):
    """Top-nav for pages inside the Scheduling module."""
    def cls(k):
        return "class='active'" if active == k else ''
    return f"""
    <nav class="topnav">
      <div class="brand">
        <a href="/"><span class="accent">VNGG</span>ATS</a>
        <span class="crumb-sep">/</span>
        <span class="crumb">Scheduling</span>
      </div>
      <div class="nav-links">
        <a href="/scheduling/" {cls('home')}>Dashboard</a>
        <a href="/scheduling/candidates" {cls('candidates')}>Candidates</a>
        <a href="/scheduling/schedule" {cls('schedule')}>Schedule</a>
        <a href="/scheduling/interviews" {cls('interviews')}>Interviews</a>
        <a href="/scheduling/notes" {cls('notes')}>Notes</a>
      </div>
    </nav>
    """


def scheduling_page(content, active="", title="Scheduling"):
    """Wrap content in scheduling-module HTML shell (nav + style + js)."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{title} — VNGG ATS</title>
  {BASE_STYLE}
</head>
<body>
  {scheduling_nav(active)}
  {content}
  <div id="notif-container" class="notif"></div>
  {BASE_JS}
</body>
</html>"""
