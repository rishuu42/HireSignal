"""
app.py
------
Flask API exposing job intelligence data with a built-in dashboard.

Endpoints:
  GET /           → Dashboard UI
  GET /api/jobs   → JSON list of jobs (supports ?remote=true, ?tech=Python, ?role=Engineer, ?limit=50)
  GET /api/stats  → Aggregate stats (top techs, top locations, remote %)
  POST /api/refresh → Manually trigger a pipeline run
"""

import json
import sqlite3
import os
import threading
from flask import Flask, jsonify, request, render_template_string
from cleaner import run_cleaning_pipeline

app = Flask(__name__)
DB_PATH = os.path.join("data", "jobs.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row):
    d = dict(row)
    for field in ["roles", "tech_stack", "locations"]:
        try:
            d[field] = json.loads(d[field]) if d[field] else []
        except Exception:
            d[field] = []
    d["is_remote"] = bool(d.get("is_remote"))
    return d


# ── API Routes ─────────────────────────────────────────────────────────────────

@app.route("/api/jobs")
def get_jobs():
    conn = get_db()
    query = "SELECT * FROM jobs WHERE 1=1"
    params = []

    if request.args.get("remote") == "true":
        query += " AND is_remote = 1"
    if request.args.get("tech"):
        query += " AND tech_stack LIKE ?"
        params.append(f'%{request.args["tech"]}%')
    if request.args.get("role"):
        query += " AND roles LIKE ?"
        params.append(f'%{request.args["role"]}%')
    if request.args.get("q"):
        query += " AND (full_text LIKE ? OR company LIKE ?)"
        q = f'%{request.args["q"]}%'
        params.extend([q, q])

    limit = min(int(request.args.get("limit", 50)), 200)
    query += f" ORDER BY id DESC LIMIT {limit}"

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([row_to_dict(r) for r in rows])


@app.route("/api/stats")
def get_stats():
    conn = get_db()
    rows = conn.execute("SELECT tech_stack, locations, is_remote FROM jobs").fetchall()
    conn.close()

    tech_count = {}
    loc_count = {}
    remote_count = 0
    total = len(rows)

    for row in rows:
        for tech in json.loads(row["tech_stack"] or "[]"):
            tech_count[tech] = tech_count.get(tech, 0) + 1
        for loc in json.loads(row["locations"] or "[]"):
            loc_count[loc] = loc_count.get(loc, 0) + 1
        if row["is_remote"]:
            remote_count += 1

    top_tech = sorted(tech_count.items(), key=lambda x: -x[1])[:15]
    top_loc = sorted(loc_count.items(), key=lambda x: -x[1])[:10]

    return jsonify({
        "total_jobs": total,
        "remote_count": remote_count,
        "remote_pct": round(remote_count / total * 100, 1) if total else 0,
        "top_technologies": [{"name": k, "count": v} for k, v in top_tech],
        "top_locations": [{"name": k, "count": v} for k, v in top_loc],
    })


@app.route("/api/refresh", methods=["POST"])
def refresh():
    """Trigger a pipeline run in background."""
    def run():
        try:
            run_cleaning_pipeline()
        except Exception as e:
            print(f"Refresh failed: {e}")
    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status": "Pipeline started in background"})


# ── Dashboard UI ───────────────────────────────────────────────────────────────

DASHBOARD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>HireSignal — B2B Job Intelligence</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Mono:wght@300;400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #0a0a0f;
    --surface: #12121a;
    --surface2: #1a1a26;
    --border: #2a2a3d;
    --accent: #7c6af7;
    --accent2: #f7a26a;
    --green: #4dffb4;
    --text: #e8e8f0;
    --muted: #7878a0;
    --card-hover: #1e1e2e;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: 'DM Mono', monospace; min-height: 100vh; }

  /* noise texture overlay */
  body::before {
    content: ''; position: fixed; inset: 0;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.04'/%3E%3C/svg%3E");
    pointer-events: none; z-index: 0; opacity: 0.4;
  }

  header {
    border-bottom: 1px solid var(--border);
    padding: 20px 40px;
    display: flex; align-items: center; justify-content: space-between;
    position: sticky; top: 0; background: rgba(10,10,15,0.92);
    backdrop-filter: blur(12px); z-index: 100;
  }
  .logo { font-family: 'Syne', sans-serif; font-weight: 800; font-size: 1.3rem; letter-spacing: -0.5px; }
  .logo span { color: var(--accent); }
  .badge { background: var(--accent); color: white; font-size: 0.65rem; padding: 2px 8px; border-radius: 20px; margin-left: 8px; vertical-align: middle; font-family: 'DM Mono'; }

  main { max-width: 1200px; margin: 0 auto; padding: 40px; position: relative; z-index: 1; }

  .hero { margin-bottom: 40px; }
  .hero h1 { font-family: 'Syne', sans-serif; font-size: 2.2rem; font-weight: 800; line-height: 1.15; }
  .hero h1 em { color: var(--accent); font-style: normal; }
  .hero p { color: var(--muted); margin-top: 8px; font-size: 0.85rem; }

  /* Stats bar */
  .stats-bar {
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 36px;
  }
  .stat-card {
    background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
    padding: 20px; transition: border-color 0.2s;
  }
  .stat-card:hover { border-color: var(--accent); }
  .stat-num { font-family: 'Syne', sans-serif; font-size: 2rem; font-weight: 700; color: var(--accent); }
  .stat-label { font-size: 0.72rem; color: var(--muted); margin-top: 4px; text-transform: uppercase; letter-spacing: 1px; }

  /* Filters */
  .filters {
    display: flex; gap: 10px; margin-bottom: 24px; flex-wrap: wrap; align-items: center;
  }
  input[type=text], select {
    background: var(--surface); border: 1px solid var(--border); color: var(--text);
    padding: 10px 14px; border-radius: 8px; font-family: 'DM Mono'; font-size: 0.82rem;
    outline: none; transition: border-color 0.2s;
  }
  input[type=text]:focus, select:focus { border-color: var(--accent); }
  input[type=text] { flex: 1; min-width: 200px; }
  .btn {
    background: var(--accent); color: white; border: none; padding: 10px 20px;
    border-radius: 8px; cursor: pointer; font-family: 'Syne'; font-size: 0.82rem;
    font-weight: 600; transition: opacity 0.2s, transform 0.1s;
  }
  .btn:hover { opacity: 0.85; transform: translateY(-1px); }
  .btn-ghost {
    background: transparent; border: 1px solid var(--border); color: var(--muted);
  }
  .btn-ghost:hover { border-color: var(--accent2); color: var(--accent2); }

  /* Tag toggles */
  .tag-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 24px; }
  .tag {
    padding: 4px 12px; border-radius: 20px; border: 1px solid var(--border);
    font-size: 0.72rem; cursor: pointer; transition: all 0.15s; color: var(--muted);
  }
  .tag:hover, .tag.active { border-color: var(--accent); color: var(--accent); background: rgba(124,106,247,0.08); }

  /* Job cards */
  #jobs-container { display: flex; flex-direction: column; gap: 14px; }
  .job-card {
    background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
    padding: 20px 24px; transition: all 0.2s; cursor: pointer;
  }
  .job-card:hover { border-color: var(--accent); background: var(--card-hover); transform: translateX(3px); }
  .job-top { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px; }
  .company { font-family: 'Syne'; font-size: 1rem; font-weight: 700; }
  .job-meta { display: flex; gap: 8px; flex-wrap: wrap; }
  .pill {
    padding: 3px 10px; border-radius: 20px; font-size: 0.68rem;
    border: 1px solid var(--border); color: var(--muted);
  }
  .pill.remote { border-color: var(--green); color: var(--green); }
  .pill.salary { border-color: var(--accent2); color: var(--accent2); }
  .tech-tags { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; }
  .tech-pill {
    padding: 2px 8px; background: rgba(124,106,247,0.1); color: var(--accent);
    border-radius: 4px; font-size: 0.66rem;
  }
  .snippet { font-size: 0.78rem; color: var(--muted); margin-top: 8px; line-height: 1.5; }

  /* Expanded view */
  .job-card.expanded .full-text { display: block !important; }
  .full-text {
    display: none; margin-top: 14px; padding-top: 14px;
    border-top: 1px solid var(--border); font-size: 0.78rem; color: var(--muted);
    line-height: 1.7; white-space: pre-wrap; max-height: 300px; overflow-y: auto;
  }
  .view-link { font-size: 0.72rem; color: var(--accent); text-decoration: none; }
  .view-link:hover { text-decoration: underline; }

  /* Top tech chart */
  .section-title { font-family: 'Syne'; font-size: 0.85rem; font-weight: 700; text-transform: uppercase; letter-spacing: 2px; color: var(--muted); margin-bottom: 16px; }
  .tech-chart { display: flex; flex-direction: column; gap: 8px; }
  .tech-bar-row { display: flex; align-items: center; gap: 10px; font-size: 0.75rem; }
  .tech-name { width: 100px; color: var(--text); }
  .tech-bar-bg { flex: 1; background: var(--surface2); border-radius: 4px; height: 8px; }
  .tech-bar-fill { height: 8px; border-radius: 4px; background: var(--accent); transition: width 0.6s ease; }
  .tech-count { color: var(--muted); width: 30px; text-align: right; }

  .two-col { display: grid; grid-template-columns: 1fr 320px; gap: 32px; align-items: start; }
  .sidebar { position: sticky; top: 90px; }
  .sidebar-card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 20px; margin-bottom: 16px; }

  .loading { text-align: center; color: var(--muted); padding: 60px; font-size: 0.85rem; }
  .empty { text-align: center; color: var(--muted); padding: 40px; }

  @media (max-width: 768px) {
    main { padding: 20px; }
    .stats-bar { grid-template-columns: repeat(2, 1fr); }
    .two-col { grid-template-columns: 1fr; }
    .sidebar { position: static; }
  }
</style>
</head>
<body>
<header>
  <div class="logo">Hire<span>Signal</span> <span class="badge">LIVE</span></div>
  <div style="font-size:0.72rem; color:var(--muted)">HN Hiring Intelligence</div>
</header>

<main>
  <div class="hero">
    <h1>B2B Talent <em>Intelligence</em><br>from HackerNews</h1>
    <p>Real-time job signal from the tech community's most trusted hiring thread.</p>
  </div>

  <div class="stats-bar" id="stats-bar">
    <div class="stat-card"><div class="stat-num" id="s-total">—</div><div class="stat-label">Total Postings</div></div>
    <div class="stat-card"><div class="stat-num" id="s-remote">—</div><div class="stat-label">Remote Roles</div></div>
    <div class="stat-card"><div class="stat-num" id="s-pct">—</div><div class="stat-label">Remote %</div></div>
    <div class="stat-card"><div class="stat-num" id="s-tech">—</div><div class="stat-label">Distinct Tech Tags</div></div>
  </div>

  <div class="two-col">
    <div>
      <div class="filters">
        <input type="text" id="q-input" placeholder="Search company, keyword..." />
        <select id="tech-select">
          <option value="">All Tech</option>
          <option>Python</option><option>JavaScript</option><option>TypeScript</option>
          <option>Rust</option><option>Go</option><option>React</option>
          <option>AWS</option><option>Kubernetes</option><option>PostgreSQL</option>
        </select>
        <button class="btn" onclick="loadJobs()">Search</button>
        <button class="btn btn-ghost" id="remote-toggle" onclick="toggleRemote()">Remote Only</button>
      </div>

      <div id="jobs-container"><div class="loading">Loading job intelligence...</div></div>
    </div>

    <div class="sidebar">
      <div class="sidebar-card">
        <div class="section-title">Top Technologies</div>
        <div class="tech-chart" id="tech-chart"><div style="color:var(--muted);font-size:0.75rem">Loading...</div></div>
      </div>
      <div class="sidebar-card">
        <div class="section-title">Top Locations</div>
        <div id="loc-list" style="font-size:0.78rem; color:var(--muted); display:flex; flex-direction:column; gap:6px;"></div>
      </div>
      <button class="btn btn-ghost" style="width:100%;font-size:0.75rem" onclick="triggerRefresh()">↻ Refresh Pipeline</button>
    </div>
  </div>
</main>

<script>
let remoteOnly = false;

async function loadStats() {
  try {
    const res = await fetch('/api/stats');
    const data = await res.json();
    document.getElementById('s-total').textContent = data.total_jobs;
    document.getElementById('s-remote').textContent = data.remote_count;
    document.getElementById('s-pct').textContent = data.remote_pct + '%';

    // Render tech chart
    const maxCount = data.top_technologies[0]?.count || 1;
    const chart = document.getElementById('tech-chart');
    chart.innerHTML = data.top_technologies.map(t => `
      <div class="tech-bar-row">
        <div class="tech-name">${t.name}</div>
        <div class="tech-bar-bg"><div class="tech-bar-fill" style="width:${Math.round(t.count/maxCount*100)}%"></div></div>
        <div class="tech-count">${t.count}</div>
      </div>`).join('');

    // Distinct tech count
    document.getElementById('s-tech').textContent = data.top_technologies.length + '+';

    // Locations
    const locList = document.getElementById('loc-list');
    locList.innerHTML = data.top_locations.map(l => `
      <div style="display:flex;justify-content:space-between">
        <span>${l.name}</span><span style="color:var(--accent)">${l.count}</span>
      </div>`).join('');
  } catch(e) { console.error(e); }
}

async function loadJobs() {
  const container = document.getElementById('jobs-container');
  container.innerHTML = '<div class="loading">Fetching signals...</div>';

  const q = document.getElementById('q-input').value;
  const tech = document.getElementById('tech-select').value;

  let url = `/api/jobs?limit=60`;
  if (q) url += `&q=${encodeURIComponent(q)}`;
  if (tech) url += `&tech=${encodeURIComponent(tech)}`;
  if (remoteOnly) url += `&remote=true`;

  try {
    const res = await fetch(url);
    const jobs = await res.json();

    if (!jobs.length) {
      container.innerHTML = '<div class="empty">No jobs match your filters.</div>';
      return;
    }

    container.innerHTML = jobs.map(j => `
      <div class="job-card" onclick="this.classList.toggle('expanded')">
        <div class="job-top">
          <div class="company">${escHtml(j.company)}</div>
          <div class="job-meta">
            ${j.is_remote ? '<span class="pill remote">Remote</span>' : ''}
            ${j.salary ? `<span class="pill salary">${escHtml(j.salary)}</span>` : ''}
            ${j.posted_at ? `<span class="pill">${j.posted_at}</span>` : ''}
          </div>
        </div>
        ${j.roles.length ? `<div style="font-size:0.78rem;color:var(--muted)">${j.roles.slice(0,3).join(' · ')}</div>` : ''}
        <div class="tech-tags">${j.tech_stack.slice(0,8).map(t => `<span class="tech-pill">${escHtml(t)}</span>`).join('')}</div>
        <div class="snippet">${escHtml((j.full_text||'').slice(0,160))}…</div>
        <div class="full-text">${escHtml(j.full_text || '')}
          <br><a class="view-link" href="${j.url}" target="_blank" onclick="event.stopPropagation()">View on HN ↗</a>
        </div>
      </div>`).join('');
  } catch(e) {
    container.innerHTML = '<div class="empty">Error loading jobs. Is the DB populated? Run the pipeline first.</div>';
  }
}

function toggleRemote() {
  remoteOnly = !remoteOnly;
  const btn = document.getElementById('remote-toggle');
  btn.style.borderColor = remoteOnly ? 'var(--green)' : '';
  btn.style.color = remoteOnly ? 'var(--green)' : '';
  loadJobs();
}

async function triggerRefresh() {
  await fetch('/api/refresh', { method: 'POST' });
  alert('Pipeline started! Refresh in ~2 minutes.');
}

function escHtml(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

document.getElementById('q-input').addEventListener('keydown', e => { if(e.key==='Enter') loadJobs(); });

loadStats();
loadJobs();
</script>
</body>
</html>"""


@app.route("/")
def dashboard():
    return render_template_string(DASHBOARD)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
