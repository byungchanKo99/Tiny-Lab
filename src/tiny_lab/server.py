"""Live dashboard HTTP server — serves auto-refreshing HTML report."""
from __future__ import annotations

import threading
from functools import partial
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any


def _render_live_html(project_dir: Path, refresh_interval: int) -> str:
    """Generate HTML report with auto-refresh meta tag."""
    from .dashboard import build_board_data
    from .report import generate_html_report

    data = build_board_data(project_dir)
    if data is None:
        return "<html><body><h1>No project.yaml found. Run 'tiny-lab init' first.</h1></body></html>"

    # Generate HTML into a string by writing to a temp path
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
        tmp = Path(f.name)
    generate_html_report(data, tmp)
    html = tmp.read_text()
    tmp.unlink()

    # Check loop status for live badge
    from .dashboard import build_status_data
    status = build_status_data(project_dir)
    loop_running = status.get("loop") == "RUNNING"
    badge_color = "#238636" if loop_running else "#6e7681"
    badge_text = "RUNNING" if loop_running else "STOPPED"

    # Inject auto-refresh, live badge, filtering, and auto-scroll
    refresh_meta = f'<meta http-equiv="refresh" content="{refresh_interval}">'
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
</style>
<script>
function filterTable() {{
  const checks = document.querySelectorAll('.filter-check');
  const active = [...checks].filter(c => c.checked).map(c => c.value);
  document.querySelectorAll('#logBody tr').forEach(tr => {{
    const verdict = tr.children[1]?.textContent?.trim();
    tr.style.display = active.includes(verdict) ? '' : 'none';
  }});
}}
window.addEventListener('load', () => {{
  const logDiv = document.querySelector('.log-scroll');
  if (logDiv) logDiv.scrollTop = logDiv.scrollHeight;
}});
</script>"""

    live_badge = (
        f'<div class="live-badge">{badge_text} &mdash; refreshing every {refresh_interval}s</div>'
    )

    # Inject filter controls before the experiment log table
    filter_html = (
        '<div class="filters">'
        '<label><input type="checkbox" class="filter-check" value="WIN" checked onchange="filterTable()"> WIN</label>'
        '<label><input type="checkbox" class="filter-check" value="LOSS" checked onchange="filterTable()"> LOSS</label>'
        '<label><input type="checkbox" class="filter-check" value="INVALID" checked onchange="filterTable()"> INVALID</label>'
        '<label><input type="checkbox" class="filter-check" value="BASELINE" checked onchange="filterTable()"> BASELINE</label>'
        '</div>'
    )

    html = html.replace("<head>", f"<head>\n{refresh_meta}", 1)
    html = html.replace("</head>", f"{live_extras}\n</head>", 1)
    html = html.replace("<body>", f"<body>\n{live_badge}", 1)
    # Add filter controls and scrollable container to log table
    html = html.replace('<h2>Experiment Log</h2>', f'<h2>Experiment Log</h2>\n{filter_html}\n<div class="log-scroll">')
    html = html.replace('</tbody>\n  </table>\n</div>', '</tbody>\n  </table>\n</div>\n</div>', 1)

    return html


class _DashboardHandler(BaseHTTPRequestHandler):
    """HTTP handler that regenerates dashboard HTML on each request."""

    project_dir: Path
    refresh_interval: int

    def do_GET(self) -> None:
        if self.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
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
        # Suppress default stderr logging
        pass


def serve_dashboard(
    project_dir: Path,
    *,
    port: int = 8505,
    refresh: int = 5,
    open_browser: bool = True,
) -> None:
    """Start a live dashboard HTTP server.

    Args:
        project_dir: Project root directory.
        port: Port to bind (default 8505).
        refresh: Auto-refresh interval in seconds (default 5).
        open_browser: Open browser automatically on start.
    """
    handler = type("Handler", (_DashboardHandler,), {
        "project_dir": project_dir.resolve(),
        "refresh_interval": refresh,
    })

    server = HTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}"

    print(f"Live dashboard: {url}")
    print(f"Auto-refresh: every {refresh}s")
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
