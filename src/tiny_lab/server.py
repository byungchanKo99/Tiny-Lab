"""Live dashboard HTTP server — serves HTML with JS-based data polling."""
from __future__ import annotations

import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any


def _build_api_data(project_dir: Path) -> dict[str, Any]:
    """Build JSON data for the live dashboard API endpoint."""
    from .dashboard import build_board_data, build_status_data

    data = build_board_data(project_dir)
    if data is None:
        return {"error": "No project.yaml found"}

    status = build_status_data(project_dir)

    # Extract lever baselines for optimization detail cards
    lever_baselines = {}
    for name, lever in data["project"].get("levers", {}).items():
        lever_baselines[name] = {"baseline": lever.get("baseline")}

    return {
        "metric_name": data["metric_name"],
        "direction": data["direction"],
        "baseline": data["baseline"],
        "baseline_command": data.get("baseline_command", ""),
        "project_name": data["project"]["name"],
        "counts": data["counts"],
        "ledger": data["ledger"],
        "approach_summary": data.get("approach_summary", {}),
        "lever_baselines": lever_baselines,
        "gen_history": data.get("gen_history", []),
        "best_row": data["best_row"],
        "queue_counts": data.get("queue_counts", {}),
        "pending_queue": data.get("pending_queue", []),
        "insights": data.get("insights", {}),
        "loop_status": status.get("loop", "STOPPED"),
    }


def _render_live_html(project_dir: Path, refresh_interval: int) -> str:
    """Generate HTML with JS fetch-based polling (no full page refresh)."""
    from .dashboard import build_board_data, build_status_data
    from .report import generate_html_report

    data = build_board_data(project_dir)
    if data is None:
        return "<html><body><h1>No project.yaml found. Run 'tiny-lab init' first.</h1></body></html>"

    # Generate base HTML
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
        tmp = Path(f.name)
    generate_html_report(data, tmp)
    html = tmp.read_text()
    tmp.unlink()

    # Check loop status
    status = build_status_data(project_dir)
    loop_running = status.get("loop") == "RUNNING"
    badge_color = "#238636" if loop_running else "#6e7681"
    badge_text = "RUNNING" if loop_running else "STOPPED"

    # NO meta refresh — use JS polling instead
    live_extras = f"""<style>
.live-badge {{ position: fixed; top: 1rem; right: 1rem;
  background: {badge_color}; color: #fff; padding: 0.3rem 0.8rem;
  border-radius: 12px; font-size: 0.75rem; font-weight: 600;
  animation: pulse 2s infinite; z-index: 999; }}
@keyframes pulse {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: 0.6; }} }}
.filters {{ margin: 1rem 0; display: flex; gap: 0.5rem; align-items: center; }}
.filters label {{ color: #8b949e; font-size: 0.8rem; cursor: pointer; }}
.filters input[type=checkbox] {{ margin-right: 0.2rem; }}
.log-scroll {{ max-height: 500px; overflow-y: auto; }}
.update-flash {{ animation: flash 0.5s; }}
@keyframes flash {{ 0% {{ background: #1f6feb33; }} 100% {{ background: transparent; }} }}
</style>
<script>
// Polling-based live update — preserves scroll position
let _prevCount = 0;

async function pollData() {{
  try {{
    const resp = await fetch('/api/data');
    const data = await resp.json();
    if (data.error) return;

    // Update badge
    const badge = document.querySelector('.live-badge');
    if (badge) {{
      const running = data.loop_status === 'RUNNING';
      badge.style.background = running ? '#238636' : '#6e7681';
      badge.textContent = (running ? 'RUNNING' : 'STOPPED') + ' — polling every {refresh_interval}s';
    }}

    // Update experiment log (preserve scroll)
    const tbody = document.getElementById('logBody');
    if (tbody && data.ledger) {{
      const logDiv = document.querySelector('.log-scroll');
      const wasAtBottom = logDiv && (logDiv.scrollHeight - logDiv.scrollTop - logDiv.clientHeight < 50);

      tbody.innerHTML = '';
      data.ledger.slice().reverse().forEach(r => {{
        const pm = r.primary_metric || {{}};
        const cls = (r.class || '').toLowerCase();
        const approach = r.approach || r.changed_variable || '';
        const opt = r.optimize_result;
        const trialInfo = opt ? ` (${{opt.n_trials}}T, ${{opt.total_seconds}}s)` : '';
        const reasoning = (r.reasoning || r.question || '').slice(0, 80);
        tbody.innerHTML += `<tr>
          <td>${{r.id}}</td><td class="${{cls}}">${{r.class}}</td>
          <td>${{pm[data.metric_name] ?? 'N/A'}}</td><td>${{pm.delta_pct ?? 'N/A'}}</td>
          <td>${{approach}}${{trialInfo}}</td><td>${{reasoning}}</td></tr>`;
      }});

      // Auto-scroll only if was at bottom (new experiment added)
      if (wasAtBottom && data.ledger.length > _prevCount && logDiv) {{
        logDiv.scrollTop = logDiv.scrollHeight;
      }}
      _prevCount = data.ledger.length;

      // Re-apply filters
      filterTable();
    }}

    // Update meta text
    const meta = document.querySelector('.meta');
    if (meta) {{
      meta.textContent = `Metric: ${{data.metric_name}} (${{data.direction}}) · Baseline: ${{data.baseline}} · Experiments: ${{data.ledger.length}}`;
    }}

  }} catch (e) {{
    console.error('Poll failed:', e);
  }}
}}

function filterTable() {{
  const checks = document.querySelectorAll('.filter-check');
  const active = [...checks].filter(c => c.checked).map(c => c.value);
  document.querySelectorAll('#logBody tr').forEach(tr => {{
    const verdict = tr.children[1]?.textContent?.trim();
    tr.style.display = active.includes(verdict) ? '' : 'none';
  }});
}}

// Start polling
setInterval(pollData, {refresh_interval} * 1000);

// Initial scroll to bottom
window.addEventListener('load', () => {{
  const logDiv = document.querySelector('.log-scroll');
  if (logDiv) logDiv.scrollTop = logDiv.scrollHeight;
  _prevCount = (document.querySelectorAll('#logBody tr') || []).length;
}});
</script>"""

    live_badge = (
        f'<div class="live-badge">{badge_text} &mdash; polling every {refresh_interval}s</div>'
    )

    filter_html = (
        '<div class="filters">'
        '<label><input type="checkbox" class="filter-check" value="WIN" checked onchange="filterTable()"> WIN</label>'
        '<label><input type="checkbox" class="filter-check" value="LOSS" checked onchange="filterTable()"> LOSS</label>'
        '<label><input type="checkbox" class="filter-check" value="INVALID" checked onchange="filterTable()"> INVALID</label>'
        '<label><input type="checkbox" class="filter-check" value="BASELINE" checked onchange="filterTable()"> BASELINE</label>'
        '</div>'
    )

    # Inject — NO meta refresh tag
    html = html.replace("</head>", f"{live_extras}\n</head>", 1)
    html = html.replace("<body>", f"<body>\n{live_badge}", 1)
    html = html.replace('<h2>Experiment Log</h2>', f'<h2>Experiment Log</h2>\n{filter_html}\n<div class="log-scroll">')
    html = html.replace('</tbody>\n  </table>\n</div>', '</tbody>\n  </table>\n</div>\n</div>', 1)

    return html


class _DashboardHandler(BaseHTTPRequestHandler):
    """HTTP handler with HTML page + JSON API endpoint."""

    project_dir: Path
    refresh_interval: int

    def do_GET(self) -> None:
        if self.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        if self.path == "/api/data":
            data = _build_api_data(self.project_dir)
            payload = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(payload)
            return

        html = _render_live_html(self.project_dir, self.refresh_interval)
        payload = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: Any) -> None:
        pass


def serve_dashboard(
    project_dir: Path,
    *,
    port: int = 8505,
    refresh: int = 5,
    open_browser: bool = True,
) -> None:
    """Start a live dashboard HTTP server.

    Uses JS fetch polling instead of meta refresh to preserve scroll
    position and filter state between updates.
    """
    handler = type("Handler", (_DashboardHandler,), {
        "project_dir": project_dir.resolve(),
        "refresh_interval": refresh,
    })

    server = HTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}"

    print(f"Live dashboard: {url}")
    print(f"Auto-refresh: every {refresh}s (JS polling, no page reload)")
    print("Press Ctrl+C to stop.\n")

    if open_browser:
        import webbrowser
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()
