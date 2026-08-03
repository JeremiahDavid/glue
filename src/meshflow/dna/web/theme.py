"""HiveFlowAI presentation layer — dark dashboard theme and layout helpers."""

from __future__ import annotations

import html
from collections.abc import Callable
from pathlib import Path
from typing import Any

BRAND_NAME = "HiveFlowAI"
TAGLINE = "Connect. Unify. Reveal."
PRODUCT_SUBTITLE = "Operational intelligence · governed metrics"

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Legacy alias kept for tests importing NAV_LINKS
NAV_LINKS = (
    ("/portal/governance", "Governance"),
)

MIME_TYPES = {
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".css": "text/css",
    ".js": "application/javascript",
    ".ico": "image/x-icon",
}


def escape(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _data_nav_bar_html(
    active_path: str,
    url: Callable[[str], str],
    data_menu: tuple[tuple[str, str], ...],
) -> str:
    menu_items = []
    for href, label in data_menu:
        item_active = ' aria-current="page"' if href == active_path else ""
        item_cls = "nav-dropdown-item" + (" active" if href == active_path else "")
        menu_items.append(
            f'<a class="{item_cls}" href="{escape(url(href))}" role="menuitem"{item_active}>'
            f"{escape(label)}"
            f"</a>"
        )
    return f'<div class="nav-data-bar"><div class="nav-dropdown-panel" role="menu">{"".join(menu_items)}</div></div>'


def _data_nav_script() -> str:
    return """<script>
(function () {
  document.querySelectorAll(".nav-data-menu").forEach(function (menu) {
    var dropdown = menu.querySelector(".nav-dropdown");
    if (!dropdown) return;

    var closeTimer = null;
    var closeDelayMs = 350;

    function openMenu() {
      if (closeTimer) {
        clearTimeout(closeTimer);
        closeTimer = null;
      }
      menu.classList.add("is-open");
    }

    function scheduleClose() {
      if (closeTimer) clearTimeout(closeTimer);
      closeTimer = setTimeout(function () {
        menu.classList.remove("is-open");
        closeTimer = null;
      }, closeDelayMs);
    }

    dropdown.addEventListener("mouseenter", openMenu);
    dropdown.addEventListener("focusin", openMenu);
    menu.addEventListener("mouseenter", function () {
      if (closeTimer) {
        clearTimeout(closeTimer);
        closeTimer = null;
      }
    });
    menu.addEventListener("mouseleave", scheduleClose);
    menu.addEventListener("focusout", function (event) {
      if (!menu.contains(event.relatedTarget)) scheduleClose();
    });
  });
})();
</script>"""


def _nav_html(
    active_path: str,
    url: Callable[[str], str],
    nav_links: tuple[tuple[str, str], ...],
    *,
    data_menu: tuple[tuple[str, str], ...] | None = None,
) -> str:
    items = []
    if data_menu:
        data_paths = {entry[0] for entry in data_menu}
        data_root = data_menu[0][0]
        data_active = active_path in data_paths
        trigger_cls = "nav-link nav-dropdown-trigger" + (" active" if data_active else "")
        items.append(
            f'<div class="nav-dropdown">'
            f'<a class="{trigger_cls}" href="{escape(url(data_root))}" aria-haspopup="true">Data</a>'
            f"</div>"
        )

    for href, label in nav_links:
        active = ' aria-current="page"' if href == active_path else ""
        cls = "nav-link active" if href == active_path else "nav-link"
        items.append(f'<a class="{cls}" href="{escape(url(href))}"{active}>{escape(label)}</a>')
    return "\n".join(items)


def styles() -> str:
    return """
    :root {
      --bg-base: #060912;
      --bg-elevated: #0c1220;
      --bg-card: rgba(14, 22, 38, 0.72);
      --border: rgba(255, 255, 255, 0.08);
      --border-strong: rgba(255, 255, 255, 0.14);
      --text: #eef2f8;
      --text-muted: #8b97ad;
      --text-dim: #5c677d;
      --accent-start: #f59e0b;
      --accent-mid: #14b8a6;
      --accent-end: #38bdf8;
      --accent-electric-blue: #0066ff;
      --accent-electric-gold: #ffb800;
      --accent-light-blue: #079be8;
      --gradient-gold-text: linear-gradient(90deg, #1a1509 0%, #3d2e00 40%, #806000 72%, #c99000 88%, var(--accent-electric-gold) 100%);
      --gradient: linear-gradient(120deg, var(--accent-start), var(--accent-mid), var(--accent-end));
      --shadow: 0 24px 64px rgba(0, 0, 0, 0.45);
      --radius: 14px;
      --radius-sm: 10px;
      --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, Helvetica, Arial, sans-serif;
      --font-mono: ui-monospace, "SF Mono", SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    html { scroll-behavior: smooth; }

    body {
      font-family: var(--font);
      background: var(--bg-base);
      color: var(--text);
      line-height: 1.55;
      min-height: 100vh;
      -webkit-font-smoothing: antialiased;
    }

    body::before {
      content: "";
      position: fixed;
      inset: 0;
      background:
        radial-gradient(ellipse 80% 50% at 15% -10%, rgba(245, 158, 11, 0.12), transparent 55%),
        radial-gradient(ellipse 70% 45% at 85% 0%, rgba(56, 189, 248, 0.10), transparent 50%),
        radial-gradient(circle at 50% 100%, rgba(20, 184, 166, 0.06), transparent 40%);
      pointer-events: none;
      z-index: 0;
    }

    .shell { position: relative; z-index: 1; min-height: 100vh; display: flex; flex-direction: column; }

    .topbar {
      position: sticky;
      top: 0;
      z-index: 100;
      backdrop-filter: blur(18px) saturate(160%);
      background: rgba(6, 9, 18, 0.82);
      border-bottom: 1px solid var(--border);
    }

    .topbar-inner {
      max-width: 1200px;
      margin: 0 auto;
      padding: 0.85rem 1.5rem 0.75rem;
      display: grid;
      grid-template-columns: auto 1fr;
      column-gap: 1.5rem;
      row-gap: 0;
      align-items: center;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      text-decoration: none;
      color: inherit;
      flex-shrink: 0;
      grid-column: 1;
      grid-row: 1;
      align-self: center;
    }

    .topbar-main {
      grid-column: 2;
      grid-row: 1;
      min-width: 0;
      justify-self: stretch;
    }

    .brand img { height: 36px; width: auto; display: block; }

    .brand-text { display: flex; flex-direction: column; line-height: 1.15; }

    .brand-name {
      font-size: 1.05rem;
      font-weight: 650;
      letter-spacing: -0.02em;
    }

    .brand-name span {
      color: var(--accent-electric-gold);
    }

    .brand-tagline {
      font-size: 0.68rem;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      color: var(--text-dim);
      margin-top: 0.15rem;
    }

    .nav {
      display: flex;
      align-items: center;
      gap: 0.25rem;
      flex-wrap: nowrap;
      margin-left: auto;
    }

    .nav-link {
      display: inline-flex;
      align-items: center;
      color: var(--text-muted);
      text-decoration: none;
      font-size: 0.875rem;
      font-weight: 500;
      padding: 0.45rem 0.85rem;
      border-radius: 999px;
      transition: color 0.15s, background 0.15s;
    }

    .nav-link:hover { color: var(--text); background: rgba(255,255,255,0.05); }
    .nav-link.active {
      color: var(--text);
      background: rgba(255,255,255,0.07);
      box-shadow: inset 0 0 0 1px var(--border);
    }

    .topbar:has(.nav-data-bar) .topbar-inner {
      padding-bottom: 0.75rem;
    }

    .nav-data-menu {
      position: relative;
      width: 100%;
    }

    .nav-data-bar {
      width: 100%;
      border-top: 1px solid transparent;
      padding-top: 0;
      max-height: 0;
      overflow: hidden;
      pointer-events: none;
      transition:
        max-height 0.2s ease 0.35s,
        padding-top 0.15s ease 0.35s,
        border-color 0.15s ease 0.35s;
    }

    .nav-data-menu.is-open .nav-data-bar {
      max-height: 4.5rem;
      padding-top: 0.45rem;
      border-top-color: var(--border);
      pointer-events: auto;
      transition-delay: 0s;
    }

    .nav-dropdown {
      position: relative;
      display: inline-flex;
      align-items: center;
    }

    .nav-dropdown-trigger::after {
      content: "▾";
      margin-left: 0.35rem;
      font-size: 0.68rem;
      opacity: 0.75;
    }

    .nav-dropdown-panel {
      position: relative;
      z-index: 6;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.35rem 1.75rem;
      opacity: 0;
      visibility: hidden;
      pointer-events: none;
      transition:
        opacity 0.12s ease 0.35s,
        visibility 0s linear 0.47s;
    }

    .nav-data-menu.is-open .nav-dropdown-panel {
      opacity: 1;
      visibility: visible;
      pointer-events: auto;
      transition-delay: 0s;
    }

    .nav-dropdown-item {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 0.35rem 0.5rem;
      border: none;
      background: none;
      box-shadow: none;
      text-decoration: none;
      color: var(--text-muted);
      font-size: 0.875rem;
      font-weight: 500;
      line-height: 1.3;
      text-align: center;
      transition: color 0.15s;
    }

    .nav-dropdown-item:hover {
      color: var(--text);
      background: none;
    }

    .nav-dropdown-item.active {
      color: var(--text);
      font-weight: 600;
      background: none;
      border: none;
      box-shadow: none;
    }

    main {
      max-width: 1200px;
      margin: 0 auto;
      padding: 2rem 1.5rem 3rem;
      width: 100%;
      flex: 1;
    }

    .page-header { margin-bottom: 1.75rem; }

    .eyebrow {
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.16em;
      color: var(--accent-electric-gold);
      font-weight: 600;
      margin-bottom: 0.5rem;
    }

    .page-header h1 {
      font-size: clamp(1.75rem, 4vw, 2.35rem);
      font-weight: 650;
      letter-spacing: -0.03em;
      line-height: 1.15;
      margin-bottom: 0.5rem;
    }

    .page-header .subtitle { color: var(--text-muted); max-width: 52ch; font-size: 1rem; }

    .badge-row { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 1rem; }

    .badge {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      font-size: 0.75rem;
      font-weight: 500;
      padding: 0.3rem 0.65rem;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: rgba(255,255,255,0.03);
      color: var(--text-muted);
    }

    .badge.accent {
      border-color: rgba(20, 184, 166, 0.35);
      color: #99f6e4;
      background: rgba(20, 184, 166, 0.08);
    }

    .section { margin-bottom: 1.5rem; }

    .section-title {
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: var(--text-dim);
      font-weight: 600;
      margin-bottom: 0.85rem;
    }

    .card {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 1.25rem 1.35rem;
      backdrop-filter: blur(12px);
      box-shadow: var(--shadow);
    }

    .card + .card { margin-top: 1rem; }

    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 1rem;
      align-items: stretch;
    }

    .grid > .card + .card { margin-top: 0; }

    .grid > .card {
      display: flex;
      flex-direction: column;
      height: 100%;
    }

    .kpi-card {
      position: relative;
      overflow: hidden;
      padding: 1.35rem;
    }

    .kpi-card::before {
      content: "";
      position: absolute;
      top: 0; left: 0; right: 0;
      height: 2px;
      background: var(--gradient);
      opacity: 0.85;
    }

    .kpi-label {
      font-size: 0.82rem;
      color: var(--text-muted);
      font-weight: 500;
      margin-bottom: 0.65rem;
    }

    .kpi-value {
      font-size: clamp(1.6rem, 3vw, 2rem);
      font-weight: 650;
      letter-spacing: -0.03em;
      font-variant-numeric: tabular-nums;
      margin-bottom: 0.5rem;
    }

    .kpi-value .unit {
      font-size: 0.55em;
      font-weight: 500;
      color: var(--text-muted);
      margin-left: 0.2rem;
    }

    .kpi-meta {
      font-size: 0.78rem;
      color: var(--text-dim);
      line-height: 1.45;
    }

    .kpi-id {
      font-family: var(--font-mono);
      font-size: 0.72rem;
      color: var(--text-dim);
      margin-top: 0.65rem;
    }

    .quick-links { display: grid; gap: 0.65rem; }

    .quick-link {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
      padding: 0.9rem 1rem;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border);
      background: rgba(255,255,255,0.02);
      text-decoration: none;
      color: inherit;
      transition: border-color 0.15s, background 0.15s;
    }

    .quick-link:hover {
      border-color: var(--border-strong);
      background: rgba(255,255,255,0.04);
    }

    .quick-link strong { font-weight: 600; font-size: 0.95rem; }
    .quick-link span { color: var(--text-muted); font-size: 0.85rem; }
    .quick-link .arrow { color: var(--accent-end); font-size: 1.1rem; }

    .subpage-back {
      margin: 0 0 1rem;
      font-size: 0.88rem;
    }

    .subpage-back a {
      color: var(--text-muted);
      text-decoration: none;
    }

    .subpage-back a:hover { color: var(--accent-end); }

    .pack-card-lead {
      color: var(--text-muted);
      font-size: 0.92rem;
      line-height: 1.55;
      margin-bottom: 1rem;
    }

    .pack-meta {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 0.85rem 1.25rem;
      margin: 0;
    }

    .pack-meta div { min-width: 0; }

    .pack-meta dt {
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--text-dim);
      margin-bottom: 0.2rem;
    }

    .pack-meta dd {
      margin: 0;
      font-size: 0.92rem;
      color: var(--text-muted);
    }

    .revenue-trend-summary {
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    }

    .revenue-trend-stat .kpi-value {
      font-size: clamp(1.35rem, 2.5vw, 1.75rem);
    }

    .hive-chart {
      padding: 1rem 1rem 0.75rem;
      overflow: hidden;
      min-height: 240px;
    }

    .hive-chart canvas {
      display: block;
    }

    .chart-demo-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(min(100%, 520px), 1fr));
      gap: 1.25rem;
      align-items: stretch;
    }

    .chart-demo-item {
      display: flex;
      flex-direction: column;
      padding: 1rem 1.1rem 0.85rem;
    }

    .chart-demo-meta {
      margin-bottom: 0.65rem;
    }

    .chart-demo-type {
      font-size: 0.68rem;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: var(--accent-electric-gold);
      font-weight: 600;
      margin-bottom: 0.25rem;
    }

    .chart-demo-label {
      font-size: 1rem;
      font-weight: 600;
      letter-spacing: -0.01em;
      margin-bottom: 0.25rem;
    }

    .chart-demo-desc {
      font-size: 0.84rem;
      color: var(--text-muted);
      line-height: 1.45;
    }

    .chart-demo-mount {
      flex: 1;
      min-height: 240px;
      padding: 0.35rem 0 0;
      margin-top: 0.35rem;
      border-top: 1px solid var(--border);
    }

    .revenue-trend-chart {
      padding: 1rem 1rem 0.5rem;
      overflow: hidden;
    }

    .table-wrap {
      overflow-x: auto;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border);
    }

    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.84rem;
    }

    thead th {
      position: sticky;
      top: 0;
      background: rgba(10, 16, 28, 0.95);
      text-align: left;
      padding: 0.75rem 1rem;
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--text-dim);
      font-weight: 600;
      border-bottom: 1px solid var(--border);
      white-space: nowrap;
    }

    tbody td {
      padding: 0.7rem 1rem;
      border-bottom: 1px solid rgba(255,255,255,0.04);
      color: var(--text-muted);
      font-variant-numeric: tabular-nums;
    }

    tbody tr:hover td { background: rgba(255,255,255,0.02); color: var(--text); }
    tbody tr:last-child td { border-bottom: none; }

    td.num, th.num { text-align: right; font-family: var(--font-mono); }

    code {
      font-family: var(--font-mono);
      font-size: 0.82em;
      padding: 0.15rem 0.4rem;
      border-radius: 6px;
      background: rgba(255,255,255,0.06);
      color: #7dd3fc;
    }

    .empty {
      padding: 2.5rem 1.5rem;
      text-align: center;
      color: var(--text-muted);
      border: 1px dashed var(--border);
      border-radius: var(--radius);
      background: rgba(255,255,255,0.02);
    }

    .empty strong { display: block; color: var(--text); margin-bottom: 0.35rem; }

    ul.plain { list-style: none; }
    ul.plain li {
      padding: 0.55rem 0;
      border-bottom: 1px solid rgba(255,255,255,0.04);
      color: var(--text-muted);
      font-size: 0.9rem;
    }
    ul.plain li:last-child { border-bottom: none; }

    .footer {
      max-width: 1200px;
      margin: 0 auto;
      padding: 1.25rem 1.5rem 2rem;
      border-top: 1px solid var(--border);
      color: var(--text-dim);
      font-size: 0.78rem;
      display: flex;
      justify-content: space-between;
      gap: 1rem;
      flex-wrap: wrap;
    }

    @media (max-width: 720px) {
      .topbar-inner { grid-template-columns: 1fr; }
      .brand { grid-column: 1; }
      .topbar-main { grid-column: 1; }
      .nav { margin-left: 0; width: 100%; flex-wrap: wrap; }
      .nav-dropdown-panel {
        gap: 0.35rem 1.25rem;
      }
      .brand-tagline { display: none; }
      .hero { grid-template-columns: 1fr; }
    }

    .hero {
      display: grid;
      grid-template-columns: 1.2fr 0.8fr;
      gap: 1.5rem;
      align-items: stretch;
      margin-bottom: 2rem;
    }

    .hero-copy h1 {
      font-size: clamp(2rem, 5vw, 3.2rem);
      line-height: 1.08;
      letter-spacing: -0.04em;
      margin: 0.75rem 0 1rem;
      font-weight: 700;
    }

    .gradient-text {
      background: var(--gradient-gold-text);
      -webkit-background-clip: text;
      background-clip: text;
      color: transparent;
    }

    .hero-subtitle { color: var(--text-muted); font-size: 1.05rem; max-width: 52ch; }

    .hero-actions { display: flex; gap: 0.75rem; flex-wrap: wrap; margin-top: 1.5rem; }

    .button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 0.7rem 1.15rem;
      border-radius: 999px;
      font-size: 0.92rem;
      font-weight: 600;
      text-decoration: none;
      border: 1px solid transparent;
      transition: transform 0.15s, opacity 0.15s;
    }

    .button:hover { transform: translateY(-1px); }
    .button.primary { background: var(--accent-light-blue); color: #ffffff; }
    .button.secondary {
      border-color: var(--border-strong);
      color: var(--text);
      background: rgba(255,255,255,0.04);
    }

    .feature-list { list-style: none; display: grid; gap: 0.85rem; }
    .feature-list li { display: grid; gap: 0.2rem; }
    .feature-list strong { color: var(--text); font-size: 0.95rem; }
    .feature-list span { color: var(--text-muted); font-size: 0.88rem; }

    .pricing-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 1rem;
    }

    .pricing-card .price {
      font-size: 1.8rem;
      font-weight: 700;
      letter-spacing: -0.03em;
      margin: 0.35rem 0;
    }

    .pricing-card .price span { font-size: 0.95rem; color: var(--text-muted); font-weight: 500; }
    .pricing-card .price-sub { color: var(--accent-mid); font-weight: 600; margin-bottom: 0.85rem; }
    .pricing-card.featured { box-shadow: 0 0 0 1px rgba(20,184,166,0.25), var(--shadow); }

    .card h3 { font-size: 1.05rem; margin-bottom: 0.45rem; }
    .card p { color: var(--text-muted); font-size: 0.92rem; }

    .portal-badge {
      margin-left: auto;
      font-size: 0.78rem;
      color: var(--text-muted);
      padding: 0.35rem 0.7rem;
      border: 1px solid var(--border);
      border-radius: 999px;
      background: rgba(255,255,255,0.03);
      white-space: nowrap;
    }

    .nav-actions { display: flex; align-items: center; justify-content: flex-end; gap: 0.75rem; flex-shrink: 0; width: 100%; padding-bottom: 0.15rem; }

    .login-shell {
      min-height: calc(100vh - 120px);
      display: grid;
      place-items: center;
      padding: 2rem 0;
    }

    .login-card {
      width: min(420px, 100%);
      padding: 1.75rem;
    }

    .form-field { display: grid; gap: 0.35rem; margin-bottom: 1rem; }
    .form-field label { font-size: 0.82rem; color: var(--text-muted); font-weight: 500; }
    .form-field input {
      width: 100%;
      padding: 0.75rem 0.85rem;
      border-radius: 10px;
      border: 1px solid var(--border);
      background: rgba(255,255,255,0.04);
      color: var(--text);
      font: inherit;
    }

    .form-field input:focus {
      outline: none;
      border-color: rgba(56, 189, 248, 0.45);
      box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.12);
    }

    .form-error {
      color: #fca5a5;
      font-size: 0.85rem;
      margin-bottom: 0.75rem;
    }

    .login-actions { display: flex; justify-content: space-between; align-items: center; gap: 1rem; margin-top: 0.5rem; }

    /* ── Platform page ── */

    .platform-overview {
      margin-bottom: 2.25rem;
    }

    .platform-flow {
      position: relative;
      padding: 1rem 1.1rem 1.15rem;
      border-radius: var(--radius);
      border: 1px solid var(--border);
      background:
        radial-gradient(ellipse 70% 80% at 0% 50%, rgba(7, 155, 232, 0.08), transparent 55%),
        radial-gradient(ellipse 60% 70% at 100% 40%, rgba(245, 158, 11, 0.07), transparent 50%),
        rgba(14, 22, 38, 0.55);
      overflow: hidden;
    }

    .platform-flow-title {
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      color: var(--text-dim);
      font-weight: 600;
      margin-bottom: 0.75rem;
      text-align: center;
    }

    .platform-flow-visual {
      display: flex;
      flex-direction: column;
      gap: 0.15rem;
    }

    .flow-band {
      padding: 1rem 1.1rem;
      border-radius: var(--radius-sm);
    }

    .flow-band.refresh {
      background: rgba(56, 189, 248, 0.05);
      border: 1px solid rgba(56, 189, 248, 0.14);
    }

    .flow-band.change {
      background: rgba(20, 184, 166, 0.05);
      border: 1px solid rgba(20, 184, 166, 0.14);
    }

    .flow-band-label {
      font-size: 0.68rem;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      font-weight: 600;
      margin-bottom: 0.75rem;
    }

    .flow-band.refresh .flow-band-label { color: #7dd3fc; }
    .flow-band.change .flow-band-label { color: #99f6e4; }

    .flow-band-track {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.55rem;
      flex-wrap: wrap;
    }

    .flow-card {
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
      gap: 0.35rem;
      padding: 0.8rem 0.95rem;
      min-width: 108px;
      max-width: 148px;
      border-radius: 14px;
      border: 1px solid var(--border);
      background: rgba(10, 16, 28, 0.85);
      text-decoration: none;
      color: inherit;
      transition: transform 0.15s, border-color 0.15s, box-shadow 0.15s;
    }

    .flow-card:hover {
      transform: translateY(-2px);
      border-color: var(--border-strong);
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
    }

    .flow-card-icon {
      width: 44px;
      height: 44px;
      border-radius: 12px;
      display: grid;
      place-items: center;
      border: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.04);
      position: relative;
    }

    .flow-card-icon svg,
    .flow-card-icon .platform-engine {
      width: 24px;
      height: 24px;
      display: block;
    }

    .flow-card-ai {
      position: absolute;
      top: -5px;
      right: -5px;
      font-size: 0.5rem;
      font-weight: 800;
      letter-spacing: 0.04em;
      padding: 0.1rem 0.28rem;
      border-radius: 999px;
      line-height: 1;
      border: 1px solid rgba(255, 255, 255, 0.15);
      background: rgba(6, 9, 18, 0.92);
    }

    .flow-card.dna .flow-card-ai { color: #99f6e4; border-color: rgba(20, 184, 166, 0.4); }
    .flow-card.reporting .flow-card-ai { color: #fcd34d; border-color: rgba(245, 158, 11, 0.4); }

    .flow-card-title {
      font-size: 0.82rem;
      font-weight: 650;
      color: var(--text);
      line-height: 1.25;
    }

    .flow-card-sub {
      font-size: 0.68rem;
      color: var(--text-dim);
      line-height: 1.3;
    }

    .flow-card.sources .flow-card-icon { border-color: rgba(56, 189, 248, 0.25); background: rgba(56, 189, 248, 0.08); }
    .flow-card.lake .flow-card-icon { border-color: rgba(7, 155, 232, 0.3); background: rgba(7, 155, 232, 0.1); }
    .flow-card.portal .flow-card-icon { border-color: rgba(255, 184, 0, 0.35); background: rgba(255, 184, 0, 0.08); }
    .flow-card.change .flow-card-icon { border-color: rgba(20, 184, 166, 0.3); background: rgba(20, 184, 166, 0.1); }
    .flow-card.dna .flow-card-icon { border-color: rgba(20, 184, 166, 0.3); background: rgba(20, 184, 166, 0.1); }
    .flow-card.reporting .flow-card-icon { border-color: rgba(245, 158, 11, 0.3); background: rgba(245, 158, 11, 0.1); }

    .flow-tier-pills {
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: 0.25rem;
      margin-top: 0.15rem;
    }

    .flow-tier-pills span {
      font-size: 0.52rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      padding: 0.12rem 0.35rem;
      border-radius: 4px;
    }

    .flow-tier-pills .bronze { background: rgba(180, 120, 60, 0.15); color: #d4a574; }
    .flow-tier-pills .silver { background: rgba(148, 163, 184, 0.12); color: #cbd5e1; }
    .flow-tier-pills .gold { background: rgba(255, 184, 0, 0.12); color: var(--accent-electric-gold); }

    .flow-arrow {
      color: var(--text-dim);
      font-size: 1.15rem;
      line-height: 1;
      flex-shrink: 0;
      opacity: 0.65;
    }

    .flow-bridge-pill {
      font-size: 0.58rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: rgba(125, 211, 252, 0.8);
      padding: 0.2rem 0.5rem;
      border-radius: 999px;
      border: 1px dashed rgba(56, 189, 248, 0.3);
      white-space: nowrap;
    }

    .flow-bridge-svg {
      width: min(100%, 680px);
      height: 28px;
      margin: 0 auto;
      display: block;
    }

    .flow-engines {
      display: flex;
      align-items: center;
      gap: 0.45rem;
      flex-wrap: wrap;
      justify-content: center;
    }

    .flow-parallel-pill {
      font-size: 0.58rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--text-dim);
    }

    .platform-lake-sections {
      display: grid;
      gap: 0.55rem;
      margin: 0.75rem 0;
    }

    .lake-section {
      padding: 0.65rem 0.75rem;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.02);
    }

    .lake-section h4 {
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      font-weight: 700;
      margin-bottom: 0.3rem;
    }

    .lake-section p {
      font-size: 0.84rem;
      color: var(--text-muted);
      margin: 0;
      line-height: 1.45;
    }

    .lake-section.bronze { border-color: rgba(180, 120, 60, 0.22); }
    .lake-section.bronze h4 { color: #d4a574; }
    .lake-section.silver { border-color: rgba(148, 163, 184, 0.2); }
    .lake-section.silver h4 { color: #cbd5e1; }
    .lake-section.gold { border-color: rgba(255, 184, 0, 0.28); }
    .lake-section.gold h4 { color: var(--accent-electric-gold); }

    .lake-section:target {
      box-shadow: 0 0 0 1px rgba(56, 189, 248, 0.2);
    }

    .platform-node.change .platform-node-icon {
      border-color: rgba(20, 184, 166, 0.3);
      background: rgba(20, 184, 166, 0.1);
    }

    .platform-node.gold .platform-node-icon {
      border-color: rgba(255, 184, 0, 0.35);
      background: rgba(255, 184, 0, 0.1);
    }

    #platform-governance {
      scroll-margin-top: 5.5rem;
    }

    #platform-governance:target {
      outline: none;
    }

    #platform-governance:target .section-title {
      color: #99f6e4;
    }

    .platform-flow-track {
      display: flex;
      align-items: stretch;
      justify-content: space-between;
      gap: 0;
      flex-wrap: nowrap;
      overflow-x: auto;
      padding-bottom: 0.25rem;
      scrollbar-width: thin;
    }

    a.platform-node {
      flex: 1 1 0;
      min-width: 108px;
      max-width: none;
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
      gap: 0.55rem;
      padding: 0.5rem 0.4rem;
      text-decoration: none;
      color: inherit;
      border-radius: var(--radius-sm);
      transition: background 0.15s, transform 0.15s;
    }

    a.platform-node:hover {
      background: rgba(255, 255, 255, 0.04);
      transform: translateY(-2px);
    }

    a.platform-node:focus-visible {
      outline: 2px solid rgba(56, 189, 248, 0.45);
      outline-offset: 3px;
    }

    a.platform-node:hover .platform-node-icon {
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08), 0 0 0 1px rgba(255, 255, 255, 0.06);
    }

    .platform-node {
      flex: 1 1 0;
      min-width: 108px;
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
      gap: 0.55rem;
      padding: 0.35rem 0.5rem;
    }

    .platform-node-icon {
      width: 52px;
      height: 52px;
      border-radius: 14px;
      display: grid;
      place-items: center;
      border: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.04);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06);
      position: relative;
      transition: box-shadow 0.15s;
    }

    .platform-node-icon svg {
      width: 28px;
      height: 28px;
      display: block;
    }

    .platform-node-ai {
      position: absolute;
      top: -5px;
      right: -5px;
      font-size: 0.52rem;
      font-weight: 800;
      letter-spacing: 0.04em;
      padding: 0.12rem 0.3rem;
      border-radius: 999px;
      line-height: 1;
      border: 1px solid rgba(255, 255, 255, 0.15);
      background: rgba(6, 9, 18, 0.92);
      color: var(--text);
    }

    .platform-node.dna .platform-node-ai {
      border-color: rgba(20, 184, 166, 0.45);
      color: #99f6e4;
      background: rgba(20, 184, 166, 0.15);
    }

    .platform-node.reporting .platform-node-ai {
      border-color: rgba(245, 158, 11, 0.45);
      color: #fcd34d;
      background: rgba(245, 158, 11, 0.15);
    }

    .platform-node-label {
      font-size: 0.78rem;
      font-weight: 600;
      color: var(--text);
      line-height: 1.25;
    }

    .platform-node-sub {
      font-size: 0.68rem;
      color: var(--text-dim);
      line-height: 1.3;
    }

    .platform-connector {
      flex: 0 0 auto;
      display: flex;
      align-items: center;
      justify-content: center;
      width: 2rem;
      color: var(--text-dim);
      opacity: 0.7;
      padding-top: 0.5rem;
    }

    .platform-connector svg { width: 1.25rem; height: 1.25rem; }

    .platform-node.sources .platform-node-icon { border-color: rgba(56, 189, 248, 0.25); background: rgba(56, 189, 248, 0.08); }
    .platform-node.lake .platform-node-icon { border-color: rgba(7, 155, 232, 0.3); background: rgba(7, 155, 232, 0.1); }
    .platform-node.dna .platform-node-icon { border-color: rgba(20, 184, 166, 0.3); background: rgba(20, 184, 166, 0.1); }
    .platform-node.reporting .platform-node-icon { border-color: rgba(245, 158, 11, 0.3); background: rgba(245, 158, 11, 0.1); }
    .platform-node.portal .platform-node-icon { border-color: rgba(255, 184, 0, 0.35); background: rgba(255, 184, 0, 0.08); }

    .platform-layers {
      display: grid;
      gap: 0;
      margin-bottom: 2rem;
    }

    .platform-layer {
      display: grid;
      grid-template-columns: minmax(0, 280px) minmax(0, 1fr);
      gap: 1.25rem;
      align-items: stretch;
      padding: 1.35rem;
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: var(--bg-card);
      box-shadow: var(--shadow);
      position: relative;
      scroll-margin-top: 5.5rem;
    }

    .platform-layer:target {
      border-color: rgba(56, 189, 248, 0.35);
      box-shadow: 0 0 0 1px rgba(56, 189, 248, 0.12), var(--shadow);
    }

    .platform-layer + .platform-layer { margin-top: 0; }

    .platform-layer-connector {
      display: flex;
      justify-content: center;
      padding: 0.35rem 0;
      color: var(--text-dim);
    }

    .platform-layer-connector svg { width: 1.1rem; height: 1.1rem; opacity: 0.65; }

    .platform-layer-badge {
      display: inline-flex;
      align-items: center;
      gap: 0.45rem;
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      font-weight: 700;
      margin-bottom: 0.65rem;
    }

    .platform-layer-badge span {
      width: 1.5rem;
      height: 1.5rem;
      border-radius: 6px;
      display: grid;
      place-items: center;
      font-size: 0.72rem;
      font-weight: 700;
      color: var(--text);
    }

    .platform-layer[data-layer="1"] .platform-layer-badge span { background: rgba(56, 189, 248, 0.18); color: #7dd3fc; }
    .platform-layer[data-layer="2"] .platform-layer-badge span { background: rgba(7, 155, 232, 0.2); color: #7dd3fc; }
    .platform-layer[data-layer="3"] .platform-layer-badge span { background: rgba(20, 184, 166, 0.2); color: #99f6e4; }
    .platform-layer[data-layer="4"] .platform-layer-badge span { background: rgba(245, 158, 11, 0.2); color: #fcd34d; }
    .platform-layer[data-layer="5"] .platform-layer-badge span { background: rgba(255, 184, 0, 0.18); color: var(--accent-electric-gold); }

    .platform-layer-visual {
      border-radius: var(--radius-sm);
      border: 1px solid var(--border);
      background: rgba(0, 0, 0, 0.22);
      padding: 1rem;
      min-height: 148px;
      display: flex;
      flex-direction: column;
      justify-content: flex-start;
    }

    .platform-layer-emblem {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 0.45rem;
      padding-bottom: 0.85rem;
      margin-bottom: 0.85rem;
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    }

    .platform-emblem-icon {
      width: 68px;
      height: 68px;
      border-radius: 16px;
      display: grid;
      place-items: center;
      border: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.04);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06);
      position: relative;
    }

    .platform-emblem-icon svg,
    .platform-emblem-icon .platform-engine {
      width: 40px;
      height: 40px;
      display: block;
    }

    .platform-node-icon .platform-engine {
      width: 28px;
      height: 28px;
      display: block;
    }

    .platform-parallel-emblem .platform-engine {
      width: 28px;
      height: 28px;
      display: block;
    }

    .platform-emblem-ai {
      position: absolute;
      top: -6px;
      right: -6px;
      font-size: 0.56rem;
      font-weight: 800;
      letter-spacing: 0.04em;
      padding: 0.14rem 0.34rem;
      border-radius: 999px;
      line-height: 1;
      border: 1px solid rgba(255, 255, 255, 0.15);
      background: rgba(6, 9, 18, 0.92);
    }

    .platform-emblem-name {
      font-size: 0.72rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--text-muted);
    }

    .platform-layer-emblem.sources .platform-emblem-icon { border-color: rgba(56, 189, 248, 0.25); background: rgba(56, 189, 248, 0.08); }
    .platform-layer-emblem.lake .platform-emblem-icon { border-color: rgba(7, 155, 232, 0.3); background: rgba(7, 155, 232, 0.1); }
    .platform-layer-emblem.dna .platform-emblem-icon { border-color: rgba(20, 184, 166, 0.3); background: rgba(20, 184, 166, 0.1); }
    .platform-layer-emblem.dna .platform-emblem-ai { border-color: rgba(20, 184, 166, 0.45); color: #99f6e4; background: rgba(20, 184, 166, 0.15); }
    .platform-layer-emblem.reporting .platform-emblem-icon { border-color: rgba(245, 158, 11, 0.3); background: rgba(245, 158, 11, 0.1); }
    .platform-layer-emblem.reporting .platform-emblem-ai { border-color: rgba(245, 158, 11, 0.45); color: #fcd34d; background: rgba(245, 158, 11, 0.15); }
    .platform-layer-emblem.portal .platform-emblem-icon { border-color: rgba(255, 184, 0, 0.35); background: rgba(255, 184, 0, 0.08); }

    .platform-parallel-emblem {
      width: 44px;
      height: 44px;
      margin: 0 auto 0.45rem;
      display: grid;
      place-items: center;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.03);
    }

    .platform-parallel-emblem svg,
    .platform-parallel-emblem .platform-engine { width: 28px; height: 28px; display: block; }

    .platform-parallel-card.dna .platform-parallel-emblem {
      border-color: rgba(20, 184, 166, 0.25);
      background: rgba(20, 184, 166, 0.08);
    }

    .platform-parallel-card.reporting .platform-parallel-emblem {
      border-color: rgba(245, 158, 11, 0.25);
      background: rgba(245, 158, 11, 0.08);
    }

    .platform-layer-body h3 {
      font-size: 1.1rem;
      font-weight: 650;
      margin-bottom: 0.5rem;
      letter-spacing: -0.02em;
    }

    .platform-layer-body p {
      color: var(--text-muted);
      font-size: 0.92rem;
      margin-bottom: 0.75rem;
    }

    .platform-layer-tags {
      display: flex;
      flex-wrap: wrap;
      gap: 0.4rem;
    }

    .platform-tag {
      font-size: 0.68rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      padding: 0.25rem 0.55rem;
      border-radius: 999px;
      border: 1px solid var(--border);
      color: var(--text-dim);
      background: rgba(255, 255, 255, 0.03);
    }

    /* Mini diagram: data lake */
    .mini-lake-sources {
      display: flex;
      justify-content: center;
      gap: 0.45rem;
      margin-bottom: 0.65rem;
    }

    .mini-source {
      width: 2rem;
      height: 2rem;
      border-radius: 8px;
      border: 1px solid rgba(56, 189, 248, 0.25);
      background: rgba(56, 189, 248, 0.08);
      display: grid;
      place-items: center;
      font-size: 0.55rem;
      font-weight: 700;
      color: #7dd3fc;
      letter-spacing: 0.02em;
    }

    .mini-lake-stack {
      display: grid;
      gap: 0.35rem;
    }

    .mini-lake-tier {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.4rem 0.55rem;
      border-radius: 8px;
      font-size: 0.68rem;
      font-weight: 600;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }

    .mini-lake-tier.bronze {
      background: rgba(180, 120, 60, 0.15);
      border: 1px solid rgba(180, 120, 60, 0.25);
      color: #d4a574;
    }

    .mini-lake-tier.silver {
      background: rgba(148, 163, 184, 0.12);
      border: 1px solid rgba(148, 163, 184, 0.22);
      color: #cbd5e1;
    }

    .mini-lake-tier.gold {
      background: rgba(255, 184, 0, 0.12);
      border: 1px solid rgba(255, 184, 0, 0.28);
      color: var(--accent-electric-gold);
    }

    .mini-lake-tier .bar {
      flex: 1;
      height: 4px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.12);
      overflow: hidden;
    }

    .mini-lake-tier .bar i {
      display: block;
      height: 100%;
      border-radius: inherit;
      background: currentColor;
      opacity: 0.55;
    }

    .mini-lake-tier.bronze .bar i { width: 88%; }
    .mini-lake-tier.silver .bar i { width: 62%; }
    .mini-lake-tier.gold .bar i { width: 48%; }

    /* Mini diagram: DNA pipeline */
    .mini-pipeline {
      display: flex;
      align-items: center;
      gap: 0.35rem;
    }

    .mini-pipe-node {
      flex: 1;
      min-width: 0;
      padding: 0.45rem 0.35rem;
      border-radius: 8px;
      border: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.03);
      text-align: center;
      font-size: 0.62rem;
      font-weight: 600;
      color: var(--text-muted);
      line-height: 1.25;
    }

    .mini-pipe-node.highlight {
      border-color: rgba(20, 184, 166, 0.35);
      background: rgba(20, 184, 166, 0.1);
      color: #99f6e4;
    }

    .mini-pipe-arrow {
      flex-shrink: 0;
      color: var(--text-dim);
      font-size: 0.75rem;
    }

    .mini-gold-table {
      margin-top: 0.55rem;
      border-radius: 8px;
      border: 1px solid rgba(255, 184, 0, 0.25);
      background: rgba(255, 184, 0, 0.06);
      overflow: hidden;
    }

    .mini-gold-table header {
      padding: 0.3rem 0.5rem;
      font-size: 0.6rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--accent-electric-gold);
      border-bottom: 1px solid rgba(255, 184, 0, 0.15);
    }

    .mini-gold-table .rows {
      padding: 0.35rem 0.5rem;
      display: grid;
      gap: 0.25rem;
    }

    .mini-gold-table .row {
      height: 4px;
      border-radius: 999px;
      background: rgba(255, 184, 0, 0.2);
    }

    .mini-gold-table .row:nth-child(1) { width: 92%; }
    .mini-gold-table .row:nth-child(2) { width: 78%; }
    .mini-gold-table .row:nth-child(3) { width: 85%; }

    /* Mini diagram: reporting */
    .mini-portal-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0.4rem;
    }

    .mini-portal-kpi {
      padding: 0.45rem 0.5rem;
      border-radius: 8px;
      border: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.03);
    }

    .mini-portal-kpi .label {
      font-size: 0.55rem;
      color: var(--text-dim);
      text-transform: uppercase;
      letter-spacing: 0.06em;
      margin-bottom: 0.2rem;
    }

    .mini-portal-kpi .val {
      font-size: 0.85rem;
      font-weight: 700;
      color: var(--text);
      font-variant-numeric: tabular-nums;
    }

    .mini-portal-kpi .val.gold { color: var(--accent-electric-gold); }
    .mini-portal-kpi .val.teal { color: #5eead4; }

    .mini-portal-chart {
      grid-column: 1 / -1;
      height: 2.5rem;
      border-radius: 8px;
      border: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.02);
      display: flex;
      align-items: flex-end;
      gap: 0.25rem;
      padding: 0.35rem 0.45rem;
    }

    .mini-portal-chart span {
      flex: 1;
      border-radius: 3px 3px 0 0;
      background: linear-gradient(180deg, rgba(245, 158, 11, 0.55), rgba(245, 158, 11, 0.15));
    }

    .mini-portal-chart span:nth-child(1) { height: 45%; }
    .mini-portal-chart span:nth-child(2) { height: 72%; }
    .mini-portal-chart span:nth-child(3) { height: 58%; }
    .mini-portal-chart span:nth-child(4) { height: 88%; }
    .mini-portal-chart span:nth-child(5) { height: 65%; }

    /* Mini diagram: client portal delivery */
    .mini-delivery {
      display: grid;
      gap: 0.45rem;
    }

    .mini-delivery-row {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.4rem 0.55rem;
      border-radius: 8px;
      border: 1px solid var(--border);
      font-size: 0.68rem;
      color: var(--text-muted);
    }

    .mini-delivery-row .dot {
      width: 0.45rem;
      height: 0.45rem;
      border-radius: 50%;
      flex-shrink: 0;
    }

    .mini-delivery-row .dot.live { background: #34d399; box-shadow: 0 0 6px rgba(52, 211, 153, 0.5); }
    .mini-delivery-row .dot.pinned { background: var(--accent-electric-gold); box-shadow: 0 0 6px rgba(255, 184, 0, 0.35); }

    .platform-parallel {
      display: grid;
      grid-template-columns: 1fr auto 1fr;
      gap: 0.75rem;
      align-items: center;
      margin: 1.5rem 0 2rem;
      padding: 1rem 1.25rem;
      border-radius: var(--radius-sm);
      border: 1px dashed rgba(255, 255, 255, 0.1);
      background: rgba(255, 255, 255, 0.02);
    }

    .platform-parallel-label {
      font-size: 0.68rem;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--text-dim);
      font-weight: 600;
      text-align: center;
      writing-mode: vertical-rl;
      transform: rotate(180deg);
    }

    .platform-parallel-card {
      padding: 0.85rem 1rem;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.03);
      text-align: center;
    }

    .platform-parallel-card strong {
      display: block;
      font-size: 0.82rem;
      margin-bottom: 0.25rem;
    }

    .platform-parallel-card span {
      font-size: 0.75rem;
      color: var(--text-dim);
    }

    .platform-parallel-card.dna { border-color: rgba(20, 184, 166, 0.25); }
    .platform-parallel-card.reporting { border-color: rgba(245, 158, 11, 0.25); }

    .platform-governance-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 1rem;
    }

    .platform-gov-card {
      padding: 1.25rem;
      border-radius: var(--radius);
      border: 1px solid var(--border);
      background: var(--bg-card);
    }

    .platform-gov-card h3 {
      font-size: 0.95rem;
      margin-bottom: 0.75rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .platform-gov-visual {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.5rem;
      padding: 1rem 0.5rem;
      margin-bottom: 0.75rem;
    }

    .platform-gov-step {
      flex: 1;
      min-width: 0;
      text-align: center;
      padding: 0.55rem 0.35rem;
      border-radius: 10px;
      border: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.03);
      font-size: 0.68rem;
      font-weight: 600;
      color: var(--text-muted);
      line-height: 1.3;
    }

    .platform-gov-step.active {
      border-color: rgba(20, 184, 166, 0.35);
      color: #99f6e4;
      background: rgba(20, 184, 166, 0.08);
    }

    .platform-gov-arrow { color: var(--text-dim); font-size: 0.8rem; flex-shrink: 0; }

    .platform-gov-card p {
      font-size: 0.88rem;
      color: var(--text-muted);
      line-height: 1.5;
    }

    @media (max-width: 820px) {
      .platform-layer { grid-template-columns: 1fr; }
      .platform-parallel {
        grid-template-columns: 1fr;
        text-align: center;
      }
      .platform-parallel-label {
        writing-mode: horizontal-tb;
        transform: none;
      }
    }
    """


def page_header(title: str, subtitle: str = "", *, eyebrow: str = "") -> str:
    eyebrow_html = f'<div class="eyebrow">{escape(eyebrow)}</div>' if eyebrow else ""
    subtitle_html = f'<p class="subtitle">{escape(subtitle)}</p>' if subtitle else ""
    return f"""
    <header class="page-header">
      {eyebrow_html}
      <h1>{escape(title)}</h1>
      {subtitle_html}
    </header>
    """


def badge_row(*badges: tuple[str, bool]) -> str:
    items = []
    for label, accent in badges:
        cls = "badge accent" if accent else "badge"
        items.append(f'<span class="{cls}">{escape(label)}</span>')
    return f'<div class="badge-row">{"".join(items)}</div>'


def empty_state(title: str, message: str) -> str:
    return f"""
    <div class="empty">
      <strong>{escape(title)}</strong>
      <span>{escape(message)}</span>
    </div>
    """


def render_page(
    *,
    title: str,
    active_path: str,
    body: str,
    page_title: str | None = None,
    url: Callable[[str], str] | None = None,
    nav_links: tuple[tuple[str, str], ...] | None = None,
) -> str:
    return render_public_page(
        title=title,
        active_path=active_path,
        body=body,
        page_title=page_title,
        url=url,
        nav_links=nav_links or NAV_LINKS,
    )


def _layout_shell(
    *,
    title: str,
    body: str,
    active_path: str,
    nav_links: tuple[tuple[str, str], ...],
    url: Callable[[str], str],
    page_title: str | None = None,
    topbar_extra: str = "",
    footer_left: str | None = None,
    client_accent: str | None = None,
    data_menu: tuple[tuple[str, str], ...] | None = None,
    charts_assets: str = "",
) -> str:
    window_title = escape(page_title or title)
    accent_style = ""
    if client_accent:
        accent_style = f"<style>:root {{ --accent-mid: {escape(client_accent)}; }}</style>"
    footer_text = footer_left or f"{BRAND_NAME} · {PRODUCT_SUBTITLE}"
    data_nav_bar = (
        _data_nav_bar_html(active_path, url, data_menu) if data_menu else ""
    )
    data_nav_script = _data_nav_script() if data_menu else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="theme-color" content="#060912" />
  <title>{window_title} · {escape(BRAND_NAME)}</title>
  <link rel="icon" href="{escape(url("/static/hiveflowai-symbol.png"))}" type="image/png" />
  <style>{styles()}</style>
  {accent_style}
</head>
<body>
  <div class="shell">
    <header class="topbar">
      <div class="topbar-inner">
        <a class="brand" href="{escape(url("/"))}">
          <img src="{escape(url("/static/hiveflowai-symbol.png"))}" alt="{escape(BRAND_NAME)} symbol" width="36" height="36" />
          <div class="brand-text">
            <div class="brand-name">Hive Flow <span>AI</span></div>
            <div class="brand-tagline">{escape(TAGLINE)}</div>
          </div>
        </a>
        <div class="topbar-main">
          <div class="nav-data-menu">
            <div class="nav-actions">
              <nav class="nav" aria-label="Primary">{_nav_html(active_path, url, nav_links, data_menu=data_menu)}</nav>
              {topbar_extra}
            </div>
            {data_nav_bar}
          </div>
        </div>
      </div>
    </header>
    <main>{body}</main>
    <footer class="footer">
      <span>{escape(footer_text)}</span>
      <span>Powered by Meshflow DNA</span>
    </footer>
  </div>
  {data_nav_script}
  {charts_assets}
</body>
</html>"""


def render_public_page(
    *,
    title: str,
    active_path: str,
    body: str,
    nav_links: tuple[tuple[str, str], ...],
    page_title: str | None = None,
    url: Callable[[str], str] | None = None,
) -> str:
    link = url or (lambda path: path)
    return _layout_shell(
        title=title,
        body=body,
        active_path=active_path,
        nav_links=nav_links,
        url=link,
        page_title=page_title,
    )


def render_portal_page(
    *,
    title: str,
    active_path: str,
    body: str,
    nav_links: tuple[tuple[str, str], ...],
    client: Any,
    page_title: str | None = None,
    url: Callable[[str], str] | None = None,
    data_menu: tuple[tuple[str, str], ...] | None = None,
    charts_assets: str = "",
) -> str:
    link = url or (lambda path: path)
    topbar_extra = f'<span class="portal-badge">{escape(client.display_name)}</span>'
    topbar_extra += f'<a class="nav-link" href="{escape(link("/portal/logout"))}">Sign out</a>'
    return _layout_shell(
        title=title,
        body=body,
        active_path=active_path,
        nav_links=nav_links,
        url=link,
        page_title=page_title,
        topbar_extra=topbar_extra,
        footer_left=f"{client.display_name} · Client portal",
        client_accent=getattr(client, "accent_color", None),
        data_menu=data_menu,
        charts_assets=charts_assets,
    )


def render_login_page(
    *,
    url: Callable[[str], str],
    error: str = "",
    next_path: str = "/portal",
) -> str:
    error_html = f'<div class="form-error">{escape(error)}</div>' if error else ""
    body = f"""
    <div class="login-shell">
      <div class="card login-card">
        <div class="eyebrow">Client portal</div>
        <h1 style="font-size:1.6rem;margin:0.35rem 0 0.5rem">Sign in to HiveFlowAI</h1>
        <p class="hero-subtitle" style="margin-bottom:1.25rem">Access your governed reporting portal with your client credentials.</p>
        {error_html}
        <form method="post" action="{escape(url("/portal/login"))}">
          <input type="hidden" name="next" value="{escape(next_path)}" />
          <div class="form-field">
            <label for="username">Username</label>
            <input id="username" name="username" autocomplete="username" required />
          </div>
          <div class="form-field">
            <label for="password">Password</label>
            <input id="password" name="password" type="password" autocomplete="current-password" required />
          </div>
          <div class="login-actions">
            <a class="button secondary" href="{escape(url("/"))}">Back to site</a>
            <button class="button primary" type="submit">Sign in</button>
          </div>
        </form>
      </div>
    </div>
    """
    return _layout_shell(
        title="Client login",
        body=body,
        active_path="/portal/login",
        nav_links=(("/", "Home"), ("/pricing", "Pricing"), ("/portal/login", "Client login")),
        url=url,
        page_title="Client login",
    )
