"""Self-contained HTML report generation for experiment dashboard."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Tiny-Lab Report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
         background: #0d1117; color: #c9d1d9; padding: 2rem; }}
  h1 {{ color: #58a6ff; margin-bottom: 0.5rem; }}
  .meta {{ color: #8b949e; margin-bottom: 2rem; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1.5rem; margin-bottom: 2rem; }}
  .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1.5rem; }}
  .card h2 {{ color: #58a6ff; font-size: 1rem; margin-bottom: 1rem; }}
  .stat {{ font-size: 2rem; font-weight: bold; color: #f0f6fc; }}
  .stat-label {{ color: #8b949e; font-size: 0.85rem; }}
  .stat-detail {{ color: #8b949e; font-size: 0.75rem; margin-top: 0.25rem; }}
  canvas {{ max-height: 300px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
  th, td {{ padding: 0.5rem 0.75rem; text-align: left; border-bottom: 1px solid #21262d; font-size: 0.85rem; }}
  th {{ color: #8b949e; font-weight: 600; }}
  .win {{ color: #3fb950; }} .loss {{ color: #f85149; }}
  .invalid {{ color: #d29922; }} .baseline {{ color: #8b949e; }}
  .inconclusive {{ color: #8b949e; }}
</style>
</head>
<body>
<h1>{title}</h1>
<p class="meta">Metric: {metric_name} ({direction}) &middot; Baseline: {baseline} &middot; Experiments: {total}</p>

<div class="grid">
  <div class="card">
    <h2>Results</h2>
    <canvas id="classChart"></canvas>
  </div>
  <div class="card">
    <h2>Metric Trend</h2>
    <canvas id="trendChart"></canvas>
  </div>
  <div class="card">
    <h2>Approach Comparison</h2>
    <canvas id="approachChart"></canvas>
  </div>
  <div class="card">
    <h2>Best Result</h2>
    <div class="stat">{best_metric}</div>
    <div class="stat-label">{best_desc}</div>
    <div class="stat-detail">{best_detail}</div>
  </div>
  <div class="card">
    <h2>Baseline</h2>
    <div class="stat">{baseline}</div>
    <div class="stat-label">{baseline_command}</div>
  </div>
</div>

<div class="card">
  <h2>Experiment Log</h2>
  <table>
    <thead><tr><th>ID</th><th>Verdict</th><th>{metric_name}</th><th>Delta%</th><th>Approach/Config</th><th>Best Params</th><th>Reasoning</th></tr></thead>
    <tbody id="logBody"></tbody>
  </table>
</div>

<script>
const DATA = {data_json};

// Class distribution pie
new Chart(document.getElementById('classChart'), {{
  type: 'doughnut',
  data: {{
    labels: Object.keys(DATA.counts),
    datasets: [{{ data: Object.values(DATA.counts),
      backgroundColor: Object.keys(DATA.counts).map(c =>
        c === 'WIN' ? '#3fb950' : c === 'LOSS' ? '#f85149' : c === 'BASELINE' ? '#8b949e' : '#d29922') }}]
  }},
  options: {{ plugins: {{ legend: {{ labels: {{ color: '#c9d1d9' }} }} }} }}
}});

// Metric trend line — color by approach
const experiments = DATA.ledger.filter(r => r.class !== 'BASELINE');
const approaches = [...new Set(experiments.map(r => r.approach || r.changed_variable || '?'))];
const colors = ['#58a6ff', '#3fb950', '#f0883e', '#bc8cff', '#f85149', '#39d353', '#db61a2', '#79c0ff'];
const metricVals = experiments.map(r => (r.primary_metric || {{}})[DATA.metric_name]);
const bgColors = experiments.map(r => {{
  const a = r.approach || r.changed_variable || '?';
  return colors[approaches.indexOf(a) % colors.length];
}});

new Chart(document.getElementById('trendChart'), {{
  type: 'line',
  data: {{
    labels: experiments.map(r => r.id),
    datasets: [{{
      label: DATA.metric_name,
      data: metricVals,
      borderColor: '#58a6ff', backgroundColor: 'rgba(88,166,255,0.1)', fill: true, tension: 0.3,
      pointBackgroundColor: bgColors, pointRadius: 4,
    }}, {{
      label: 'Baseline',
      data: experiments.map(() => DATA.baseline),
      borderColor: '#f85149', borderDash: [5,5], pointRadius: 0,
    }}]
  }},
  options: {{
    scales: {{ x: {{ ticks: {{ color: '#8b949e' }} }}, y: {{ ticks: {{ color: '#8b949e' }} }} }},
    plugins: {{
      legend: {{ labels: {{ color: '#c9d1d9' }} }},
      tooltip: {{
        callbacks: {{
          afterLabel: function(ctx) {{
            const r = experiments[ctx.dataIndex];
            if (!r) return '';
            const lines = [];
            if (r.approach) lines.push('Approach: ' + r.approach);
            const opt = r.optimize_result;
            if (opt && opt.best_params) {{
              lines.push('Params: ' + Object.entries(opt.best_params).map(([k,v]) => k+'='+v).join(', '));
              lines.push('Trials: ' + opt.n_trials + ' (' + opt.total_seconds + 's)');
            }}
            return lines.join('\\n');
          }}
        }}
      }}
    }}
  }}
}});

// Approach comparison bar chart (best value per approach)
const approachData = DATA.approach_summary || {{}};
const approachNames = Object.keys(approachData);
new Chart(document.getElementById('approachChart'), {{
  type: 'bar',
  data: {{
    labels: approachNames,
    datasets: [{{
      label: 'Best ' + DATA.metric_name,
      data: approachNames.map(a => approachData[a].best_value),
      backgroundColor: approachNames.map((a, i) => colors[i % colors.length]),
    }}]
  }},
  options: {{
    indexAxis: approachNames.length > 6 ? 'y' : 'x',
    scales: {{
      x: {{ ticks: {{ color: '#8b949e' }} }},
      y: {{ ticks: {{ color: '#8b949e' }} }}
    }},
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        callbacks: {{
          afterLabel: function(ctx) {{
            const a = approachNames[ctx.dataIndex];
            const info = approachData[a];
            const lines = ['W:' + info.wins + ' L:' + info.losses];
            if (info.best_params && Object.keys(info.best_params).length) {{
              lines.push(Object.entries(info.best_params).map(([k,v]) => k+'='+v).join(', '));
            }}
            return lines.join('\\n');
          }}
        }}
      }}
    }}
  }}
}});

// Populate log table with approach + best_params columns
const tbody = document.getElementById('logBody');
DATA.ledger.slice().reverse().forEach(r => {{
  const pm = r.primary_metric || {{}};
  const cls = (r.class || '').toLowerCase();
  const approach = r.approach || r.changed_variable || '';
  const opt = r.optimize_result || {{}};
  const params = opt.best_params
    ? Object.entries(opt.best_params).map(([k,v]) => k+'='+v).join(', ')
    : (r.config && !r.config.baseline_command ? Object.entries(r.config).map(([k,v]) => k+'='+v).join(', ') : '');
  const reasoning = (r.reasoning || r.question || '').slice(0, 60);
  tbody.innerHTML += `<tr>
    <td>${{r.id}}</td><td class="${{cls}}">${{r.class}}</td>
    <td>${{pm[DATA.metric_name] ?? 'N/A'}}</td><td>${{pm.delta_pct ?? 'N/A'}}</td>
    <td>${{approach}}</td><td>${{params}}</td>
    <td>${{reasoning}}</td></tr>`;
}});

// Optimization Summary
const optExps = DATA.ledger.filter(r => r.optimize_result && r.optimize_result.n_trials > 1);
if (optExps.length > 0) {{
  const optDiv = document.createElement('div');
  optDiv.className = 'card';
  optDiv.style.marginTop = '1.5rem';
  optDiv.innerHTML = '<h2>Optimization Summary</h2><table><thead><tr><th>Experiment</th><th>Approach</th><th>Trials</th><th>Time (s)</th><th>Best Value</th><th>Delta%</th><th>Best Params</th></tr></thead><tbody id="optBody"></tbody></table>';
  document.body.appendChild(optDiv);
  const optBody = document.getElementById('optBody');
  optExps.forEach(r => {{
    const opt = r.optimize_result;
    const pm = r.primary_metric || {{}};
    const params = opt.best_params ? Object.entries(opt.best_params).map(([k,v]) => k+'='+v).join(', ') : '';
    optBody.innerHTML += `<tr><td>${{r.id}}</td><td>${{r.approach || r.changed_variable || '?'}}</td><td>${{opt.n_trials}}</td><td>${{opt.total_seconds}}</td><td>${{opt.best_value ?? 'N/A'}}</td><td>${{pm.delta_pct ?? 'N/A'}}%</td><td>${{params}}</td></tr>`;
  }});
}}

// Generation History
if (DATA.gen_history && DATA.gen_history.length > 0) {{
  const ghDiv = document.createElement('div');
  ghDiv.className = 'card';
  ghDiv.style.marginTop = '1.5rem';
  ghDiv.innerHTML = '<h2>Generation History</h2><table><thead><tr><th>Timestamp</th><th>State</th><th>Added</th><th>Reasoning</th><th>Changes</th><th>References</th></tr></thead><tbody id="ghBody"></tbody></table>';
  document.body.appendChild(ghDiv);
  const ghBody = document.getElementById('ghBody');
  DATA.gen_history.slice().reverse().forEach(e => {{
    const ts = (e.timestamp || '').slice(0, 19);
    const refs = (e.references || []).join(', ');
    const changes = (e.changes_made || []).join('; ');
    ghBody.innerHTML += `<tr><td>${{ts}}</td><td>${{e.state || '?'}}</td><td>${{e.hypotheses_added_count || 0}}</td><td>${{(e.reasoning || '').slice(0, 80)}}</td><td>${{changes}}</td><td>${{refs}}</td></tr>`;
  }});
}}
</script>
</body>
</html>"""


def generate_html_report(data: dict[str, Any], output_path: Path) -> None:
    """Generate a self-contained HTML report from board data."""
    metric_name = data["metric_name"]
    best_row = data["best_row"]

    if best_row:
        bpm = best_row.get("primary_metric", {})
        best_metric = f"{bpm.get(metric_name, 'N/A')}"
        # v2: show approach + best_params
        if best_row.get("approach"):
            best_desc = f"{best_row['id']} — {best_row['approach']} (delta={bpm.get('delta_pct')}%)"
            opt = best_row.get("optimize_result", {})
            bp = opt.get("best_params", {})
            best_detail = ", ".join(f"{k}={v}" for k, v in bp.items()) if bp else ""
            if opt.get("n_trials"):
                best_detail += f" ({opt['n_trials']} trials, {opt.get('total_seconds', '?')}s)"
        else:
            best_desc = f"{best_row['id']} — {best_row.get('changed_variable')}={best_row.get('value')} (delta={bpm.get('delta_pct')}%)"
            best_detail = ""
    else:
        best_metric = "N/A"
        best_desc = "No experiments yet"
        best_detail = ""

    # Prepare JSON data for embedding
    data_json = json.dumps({
        "metric_name": metric_name,
        "baseline": data["baseline"],
        "counts": data["counts"],
        "ledger": data["ledger"],
        "approach_summary": data.get("approach_summary", {}),
        "gen_history": data.get("gen_history", []),
    }, ensure_ascii=False)

    baseline_command = data.get("baseline_command", "")

    html = _HTML_TEMPLATE.format(
        title=data["project"]["name"],
        metric_name=metric_name,
        direction=data["direction"],
        baseline=data["baseline"],
        baseline_command=baseline_command or "N/A",
        total=len(data["ledger"]),
        best_metric=best_metric,
        best_desc=best_desc,
        best_detail=best_detail,
        data_json=data_json,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html)
