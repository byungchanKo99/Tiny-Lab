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
    <h2>Lever Comparison</h2>
    <canvas id="leverChart"></canvas>
  </div>
  <div class="card">
    <h2>Best Result</h2>
    <div class="stat">{best_metric}</div>
    <div class="stat-label">{best_desc}</div>
  </div>
</div>

<div class="card">
  <h2>Experiment Log</h2>
  <table>
    <thead><tr><th>ID</th><th>Verdict</th><th>{metric_name}</th><th>Delta%</th><th>Lever</th><th>Value</th><th>Description</th></tr></thead>
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

// Metric trend line
const experiments = DATA.ledger.filter(r => r.class !== 'BASELINE');
const metricVals = experiments.map(r => (r.primary_metric || {{}})[DATA.metric_name]);
new Chart(document.getElementById('trendChart'), {{
  type: 'line',
  data: {{
    labels: experiments.map(r => r.id),
    datasets: [{{
      label: DATA.metric_name,
      data: metricVals,
      borderColor: '#58a6ff', backgroundColor: 'rgba(88,166,255,0.1)', fill: true, tension: 0.3,
    }}, {{
      label: 'Baseline',
      data: experiments.map(() => DATA.baseline),
      borderColor: '#f85149', borderDash: [5,5], pointRadius: 0,
    }}]
  }},
  options: {{ scales: {{ x: {{ ticks: {{ color: '#8b949e' }} }}, y: {{ ticks: {{ color: '#8b949e' }} }} }},
             plugins: {{ legend: {{ labels: {{ color: '#c9d1d9' }} }} }} }}
}});

// Lever win/loss bar chart
const levers = {{}};
experiments.forEach(r => {{
  const lv = r.changed_variable || '?';
  if (!levers[lv]) levers[lv] = {{ WIN: 0, LOSS: 0, INVALID: 0 }};
  if (levers[lv][r.class] !== undefined) levers[lv][r.class]++;
}});
const leverNames = Object.keys(levers);
new Chart(document.getElementById('leverChart'), {{
  type: 'bar',
  data: {{
    labels: leverNames,
    datasets: [
      {{ label: 'WIN', data: leverNames.map(l => levers[l].WIN), backgroundColor: '#3fb950' }},
      {{ label: 'LOSS', data: leverNames.map(l => levers[l].LOSS), backgroundColor: '#f85149' }},
      {{ label: 'INVALID', data: leverNames.map(l => levers[l].INVALID), backgroundColor: '#d29922' }},
    ]
  }},
  options: {{ scales: {{ x: {{ stacked: true, ticks: {{ color: '#8b949e' }} }}, y: {{ stacked: true, ticks: {{ color: '#8b949e' }} }} }},
             plugins: {{ legend: {{ labels: {{ color: '#c9d1d9' }} }} }} }}
}});

// Populate log table
const tbody = document.getElementById('logBody');
DATA.ledger.slice().reverse().forEach(r => {{
  const pm = r.primary_metric || {{}};
  const cls = (r.class || '').toLowerCase();
  const val = typeof r.value === 'object' ? Object.entries(r.value).map(([k,v]) => k+'='+v).join(', ') : (r.value || '');
  tbody.innerHTML += `<tr>
    <td>${{r.id}}</td><td class="${{cls}}">${{r.class}}</td>
    <td>${{pm[DATA.metric_name] ?? 'N/A'}}</td><td>${{pm.delta_pct ?? 'N/A'}}</td>
    <td>${{r.changed_variable || ''}}</td><td>${{val}}</td>
    <td>${{(r.question || '').slice(0, 60)}}</td></tr>`;
}});
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
        best_desc = f"{best_row['id']} — {best_row.get('changed_variable')}={best_row.get('value')} (delta={bpm.get('delta_pct')}%)"
    else:
        best_metric = "N/A"
        best_desc = "No experiments yet"

    # Prepare JSON data for embedding
    data_json = json.dumps({
        "metric_name": metric_name,
        "baseline": data["baseline"],
        "counts": data["counts"],
        "ledger": data["ledger"],
    }, ensure_ascii=False)

    html = _HTML_TEMPLATE.format(
        title=data["project"]["name"],
        metric_name=metric_name,
        direction=data["direction"],
        baseline=data["baseline"],
        total=len(data["ledger"]),
        best_metric=best_metric,
        best_desc=best_desc,
        data_json=data_json,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html)
