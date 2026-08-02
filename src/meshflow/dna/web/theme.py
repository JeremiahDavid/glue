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
    ("/portal", "Overview"),
    ("/portal/executive", "Executive"),
    ("/portal/revenue", "Revenue"),
    ("/portal/semantics", "Semantics"),
)

MIME_TYPES = {
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".css": "text/css",
    ".ico": "image/x-icon",
}


def escape(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _nav_html(active_path: str, url: Callable[[str], str], nav_links: tuple[tuple[str, str], ...]) -> str:
    items = []
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
      padding: 0.85rem 1.5rem;
      display: flex;
      align-items: center;
      gap: 1.5rem;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      text-decoration: none;
      color: inherit;
      flex-shrink: 0;
    }

    .brand img { height: 36px; width: auto; display: block; }

    .brand-text { display: flex; flex-direction: column; line-height: 1.15; }

    .brand-name {
      font-size: 1.05rem;
      font-weight: 650;
      letter-spacing: -0.02em;
    }

    .brand-name span {
      background: var(--gradient);
      -webkit-background-clip: text;
      background-clip: text;
      color: transparent;
    }

    .brand-tagline {
      font-size: 0.68rem;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      color: var(--text-dim);
      margin-top: 0.15rem;
    }

    .nav { display: flex; gap: 0.25rem; flex-wrap: wrap; margin-left: auto; }

    .nav-link {
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
      color: var(--accent-mid);
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
      .topbar-inner { flex-wrap: wrap; }
      .nav { margin-left: 0; width: 100%; }
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
      background: var(--gradient);
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
    .button.primary { background: var(--gradient); color: #041018; }
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

    .nav-actions { display: flex; align-items: center; gap: 0.75rem; margin-left: auto; }

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
) -> str:
    window_title = escape(page_title or title)
    accent_style = ""
    if client_accent:
        accent_style = f"<style>:root {{ --accent-mid: {escape(client_accent)}; }}</style>"
    footer_text = footer_left or f"{BRAND_NAME} · {PRODUCT_SUBTITLE}"
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
        <div class="nav-actions">
          <nav class="nav" aria-label="Primary">{_nav_html(active_path, url, nav_links)}</nav>
          {topbar_extra}
        </div>
      </div>
    </header>
    <main>{body}</main>
    <footer class="footer">
      <span>{escape(footer_text)}</span>
      <span>Powered by Meshflow DNA</span>
    </footer>
  </div>
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
