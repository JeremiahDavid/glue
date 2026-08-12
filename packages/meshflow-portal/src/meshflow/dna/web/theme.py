"""HiveFlowAI presentation layer — dark dashboard theme and layout helpers."""

from __future__ import annotations

import html
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

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

# Content types that must be base64-encoded for API Gateway REST + awsgi.
BINARY_STATIC_CONTENT_TYPES = frozenset(
    mime for mime in MIME_TYPES.values() if mime.startswith("image/")
)


def brand_home_href(url: Callable[[str], str]) -> str:
    """Marketing site root — use primary hostname on reporting subdomains."""
    primary = os.getenv("HIVEFLOW_PRIMARY_SITE_URL", "").strip().rstrip("/")
    if primary:
        return f"{primary}/"
    return url("/")


def escape(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _side_nav_link_active(href: str, active_path: str) -> bool:
    href_norm = href.rstrip("/") or "/"
    path_norm = active_path.split("?")[0].rstrip("/") or "/"
    return href_norm == path_norm


def _nav_abbrev(label: str) -> str:
    words = [part for part in str(label).split() if part]
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    cleaned = str(label).strip()
    return cleaned[:2].upper() if cleaned else "•"


def _side_nav_link(
    href: str,
    label: str,
    active_path: str,
    url: Callable[[str], str],
    *,
    child: bool = False,
    ancestor: bool = False,
    has_children: bool = False,
) -> str:
    is_active = _side_nav_link_active(href, active_path)
    item_active = ' aria-current="page"' if is_active else ""
    classes = ["portal-side-nav-link"]
    if child:
        classes.append("is-child")
    if has_children:
        classes.append("has-children")
    if is_active:
        classes.append("active")
    if ancestor and not is_active:
        classes.append("is-ancestor")
    abbrev = _nav_abbrev(label)
    return (
        f'<a class="{" ".join(classes)}" href="{escape(url(href))}" title="{escape(label)}"{item_active}>'
        f'<span class="portal-side-nav-icon" aria-hidden="true">{escape(abbrev)}</span>'
        f'<span class="portal-side-nav-link-text">{escape(label)}</span>'
        f"</a>"
    )


def _nav_item_has_active_descendant(item: Any, active_path: str) -> bool:
    if _side_nav_link_active(item[0], active_path):
        return True
    if len(item) > 2:
        return any(_nav_item_has_active_descendant(child, active_path) for child in item[2])
    return False


def _render_side_nav_item(
    item: Any,
    active_path: str,
    url: Callable[[str], str],
    *,
    depth: int = 0,
) -> str:
    href = item[0]
    label = item[1]
    children: tuple[Any, ...] = item[2] if len(item) > 2 else ()
    is_child = depth > 0
    if not children:
        return _side_nav_link(href, label, active_path, url, child=is_child)

    descendant_active = any(_nav_item_has_active_descendant(child, active_path) for child in children)
    parent_active = _side_nav_link_active(href, active_path)
    is_open = descendant_active or parent_active
    open_class = " is-open" if is_open else ""
    expanded = "true" if is_open else "false"
    parent_link = _side_nav_link(
        href,
        label,
        active_path,
        url,
        child=is_child,
        ancestor=descendant_active,
        has_children=True,
    )
    child_links = "".join(
        _render_side_nav_item(child, active_path, url, depth=depth + 1) for child in children
    )
    return (
        f'<div class="portal-side-nav-group{open_class}" data-nav-group>'
        f'<div class="portal-side-nav-row">'
        f'<button type="button" class="portal-side-nav-disclosure" '
        f'aria-expanded="{expanded}" aria-label="Toggle {escape(label)} pages">'
        f'<span class="portal-side-nav-disclosure-icon" aria-hidden="true"></span>'
        f"</button>"
        f"{parent_link}"
        f"</div>"
        f'<div class="portal-side-nav-children" role="group" '
        f'aria-label="{escape(label)} pages">{child_links}</div>'
        f"</div>"
    )


def _side_nav_html(
    active_path: str,
    url: Callable[[str], str],
    items: tuple[tuple[str, str], ...] | tuple[Any, ...],
    *,
    title: str,
    nav_id: str,
) -> str:
    links = [_render_side_nav_item(item, active_path, url) for item in items]
    return f"""
    <aside class="portal-side-nav" data-nav-id="{escape(nav_id)}" aria-label="{escape(title)} navigation">
      <div class="portal-side-nav-header">
        <span class="portal-side-nav-title">{escape(title)}</span>
        <button type="button" class="portal-side-nav-toggle" aria-label="Collapse {escape(title)} navigation" aria-expanded="true">
          <span class="portal-side-nav-toggle-icon" aria-hidden="true">⟨</span>
        </button>
      </div>
      <nav class="portal-side-nav-links">{"".join(links)}</nav>
    </aside>
    """


def _side_nav_script() -> str:
    return """<script>
(function () {
  var storagePrefix = "meshflow-portal-side-nav-";

  function applyCollapsed(nav, collapsed) {
    nav.classList.toggle("is-collapsed", collapsed);
    document.body.classList.toggle("portal-sidebar-collapsed", collapsed);
    var toggle = nav.querySelector(".portal-side-nav-toggle");
    if (!toggle) return;
    toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
    toggle.setAttribute(
      "aria-label",
      collapsed ? "Expand navigation" : "Collapse navigation"
    );
    var icon = toggle.querySelector(".portal-side-nav-toggle-icon");
    if (icon) icon.textContent = collapsed ? "⟩" : "⟨";
  }

  document.querySelectorAll(".portal-side-nav").forEach(function (nav) {
    var navId = nav.getAttribute("data-nav-id") || "default";
    var storageKey = storagePrefix + navId;
    var stored = null;
    try {
      stored = window.localStorage.getItem(storageKey);
    } catch (err) {
      stored = null;
    }
    if (stored === "collapsed") applyCollapsed(nav, true);
    else if (stored === "expanded") applyCollapsed(nav, false);

    var toggle = nav.querySelector(".portal-side-nav-toggle");
    if (!toggle) return;
    toggle.addEventListener("click", function () {
      var collapsed = !nav.classList.contains("is-collapsed");
      applyCollapsed(nav, collapsed);
      try {
        window.localStorage.setItem(storageKey, collapsed ? "collapsed" : "expanded");
      } catch (err) {
        /* ignore */
      }
    });
  });

  function setNavGroupOpen(group, open) {
    group.classList.toggle("is-open", open);
    var disclosure = group.querySelector(".portal-side-nav-disclosure");
    if (disclosure) disclosure.setAttribute("aria-expanded", open ? "true" : "false");
  }

  document.querySelectorAll("[data-nav-group]").forEach(function (group) {
    var disclosure = group.querySelector(".portal-side-nav-disclosure");
    var parentLink = group.querySelector(".portal-side-nav-link.has-children");
    if (!disclosure || !parentLink) return;

    disclosure.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      setNavGroupOpen(group, !group.classList.contains("is-open"));
    });

    parentLink.addEventListener("click", function (event) {
      if (parentLink.classList.contains("active")) {
        event.preventDefault();
        setNavGroupOpen(group, !group.classList.contains("is-open"));
      }
    });
  });
})();
</script>"""


def _flatten_nav_paths(data_menu: tuple[Any, ...]) -> set[str]:
    paths: set[str] = set()

    def _walk(item: Any) -> None:
        paths.add(item[0])
        if len(item) > 2:
            for child in item[2]:
                _walk(child)

    for entry in data_menu:
        _walk(entry)
    return paths


def _nav_html(
    active_path: str,
    url: Callable[[str], str],
    nav_links: tuple[tuple[str, str], ...],
    *,
    data_menu: tuple[Any, ...] | None = None,
) -> str:
    items = []
    if data_menu:
        data_paths = _flatten_nav_paths(data_menu)
        data_root = data_menu[0][0]
        data_active = active_path in data_paths
        cls = "nav-link active" if data_active else "nav-link"
        aria = ' aria-current="page"' if data_active else ""
        items.append(
            f'<a class="{cls}" href="{escape(url(data_root))}"{aria}>Reporting</a>'
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
      --shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
      --radius: 8px;
      --radius-sm: 6px;
      --portal-sidebar-width: 15rem;
      --portal-sidebar-collapsed-width: 3.5rem;
      --portal-topbar-height: 4.25rem;
      --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, Helvetica, Arial, sans-serif;
      --font-mono: ui-monospace, "SF Mono", SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      --scrollbar-size: 10px;
      --scrollbar-track: transparent;
      --scrollbar-thumb: rgba(139, 151, 173, 0.28);
      --scrollbar-thumb-hover: rgba(56, 189, 248, 0.42);
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    * {
      scrollbar-width: thin;
      scrollbar-color: var(--scrollbar-thumb) var(--scrollbar-track);
    }

    *::-webkit-scrollbar {
      width: var(--scrollbar-size);
      height: var(--scrollbar-size);
    }

    *::-webkit-scrollbar-track {
      background: var(--scrollbar-track);
    }

    *::-webkit-scrollbar-thumb {
      background-color: var(--scrollbar-thumb);
      border: 2px solid transparent;
      border-radius: 999px;
      background-clip: content-box;
    }

    *::-webkit-scrollbar-thumb:hover {
      background-color: var(--scrollbar-thumb-hover);
    }

    *::-webkit-scrollbar-corner {
      background: var(--scrollbar-track);
    }

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
        radial-gradient(ellipse 80% 50% at 15% -10%, rgba(245, 158, 11, 0.05), transparent 55%),
        radial-gradient(ellipse 70% 45% at 85% 0%, rgba(56, 189, 248, 0.04), transparent 50%);
      pointer-events: none;
      z-index: 0;
    }

    .shell { position: relative; z-index: 1; min-height: 100vh; display: flex; flex-direction: column; }

    .shell-with-sidebar {
      height: 100vh;
      max-height: 100vh;
      overflow: hidden;
    }

    .shell-with-sidebar .topbar {
      flex-shrink: 0;
    }

    .shell-with-sidebar .topbar-inner {
      max-width: none;
    }

    .portal-workspace {
      display: flex;
      flex: 1;
      min-height: 0;
      width: 100%;
      align-items: stretch;
    }

    .shell-with-sidebar .portal-workspace {
      overflow: hidden;
    }

    .portal-main {
      flex: 1;
      min-width: 0;
      min-height: 0;
      display: flex;
      flex-direction: column;
      background: var(--bg-base);
    }

    .shell-with-sidebar .portal-main {
      overflow-y: auto;
    }

    .portal-content {
      flex: 1;
      width: 100%;
      max-width: 1200px;
      margin: 0 auto;
      padding: 1.5rem 1.75rem 2rem;
    }

    .portal-footer {
      max-width: none;
      margin: 0;
      padding: 1.25rem 2rem 1.75rem;
      border-top: 1px solid var(--border);
    }

    .portal-side-nav {
      width: var(--portal-sidebar-width);
      flex-shrink: 0;
      display: flex;
      flex-direction: column;
      align-self: stretch;
      min-height: 0;
      height: auto;
      border-right: 1px solid var(--border);
      background: var(--bg-elevated);
      transition: width 0.18s ease;
      overflow: hidden;
    }

    .portal-side-nav.is-collapsed {
      width: var(--portal-sidebar-collapsed-width);
    }

    .portal-side-nav-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.5rem;
      padding: 0.6rem 0.65rem;
      border-bottom: 1px solid var(--border);
      min-height: 2.5rem;
      flex-shrink: 0;
    }

    .portal-side-nav-title {
      font-size: 0.7rem;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--text-dim);
      font-weight: 600;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .portal-side-nav.is-collapsed .portal-side-nav-header {
      justify-content: center;
      padding-left: 0.4rem;
      padding-right: 0.4rem;
    }

    .portal-side-nav.is-collapsed .portal-side-nav-title {
      display: none;
    }

    .portal-side-nav-toggle {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 1.5rem;
      height: 1.5rem;
      padding: 0;
      border: none;
      border-radius: 0;
      background: transparent;
      color: var(--text-dim);
      cursor: pointer;
      font: inherit;
      flex-shrink: 0;
      transition: color 0.12s;
    }

    .portal-side-nav-toggle:hover {
      color: var(--text);
    }

    .portal-side-nav-toggle-icon {
      font-size: 1rem;
      line-height: 1;
    }

    .portal-side-nav-links {
      display: flex;
      flex-direction: column;
      gap: 0;
      flex: 1;
      overflow-y: auto;
      padding: 0.35rem 0;
    }

    .portal-side-nav-link {
      display: flex;
      align-items: center;
      gap: 0;
      padding: 0.48rem 0.85rem;
      border-left: 2px solid transparent;
      border-radius: 0;
      text-decoration: none;
      color: var(--text-muted);
      font-size: 0.8125rem;
      font-weight: 500;
      line-height: 1.35;
      transition: color 0.12s, background 0.12s, border-color 0.12s;
      min-height: 2.1rem;
    }

    .portal-side-nav-link:hover {
      color: var(--text);
      background: rgba(255, 255, 255, 0.03);
    }

    .portal-side-nav-link.active {
      color: var(--text);
      background: rgba(255, 255, 255, 0.04);
      border-left-color: var(--accent-mid);
      font-weight: 600;
    }

    .portal-side-nav-link.is-ancestor {
      color: var(--text);
    }

    .portal-side-nav-group {
      display: flex;
      flex-direction: column;
    }

    .portal-side-nav-row {
      display: flex;
      align-items: stretch;
      min-height: 2.1rem;
    }

    .portal-side-nav-disclosure {
      flex-shrink: 0;
      width: 1.45rem;
      margin-left: 0.35rem;
      border: none;
      background: transparent;
      color: var(--text-dim);
      cursor: pointer;
      padding: 0;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      transition: color 0.12s;
    }

    .portal-side-nav-disclosure:hover {
      color: var(--text);
    }

    .portal-side-nav-disclosure-icon {
      display: block;
      width: 0.42rem;
      height: 0.42rem;
      border-right: 1.5px solid currentColor;
      border-bottom: 1.5px solid currentColor;
      transform: rotate(-45deg);
      transition: transform 0.15s ease;
    }

    .portal-side-nav-group.is-open > .portal-side-nav-row .portal-side-nav-disclosure-icon {
      transform: rotate(45deg);
    }

    .portal-side-nav-row .portal-side-nav-link {
      flex: 1;
      min-width: 0;
      padding-left: 0.35rem;
    }

    .portal-side-nav-children {
      display: none;
      flex-direction: column;
      margin-left: 1.15rem;
      padding-left: 0.55rem;
      border-left: 1px solid rgba(255, 255, 255, 0.08);
    }

    .portal-side-nav-group.is-open > .portal-side-nav-children {
      display: flex;
    }

    .portal-side-nav-link.is-child {
      padding-left: 0.65rem;
      font-size: 0.78rem;
      font-weight: 450;
      min-height: 1.9rem;
      color: var(--text-dim);
    }

    .portal-side-nav-link.is-child:hover,
    .portal-side-nav-link.is-child.active {
      color: var(--text);
    }

    .portal-side-nav-icon {
      display: none;
    }

    .portal-side-nav-link-text {
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .portal-side-nav.is-collapsed .portal-side-nav-link {
      justify-content: center;
      padding-left: 0;
      padding-right: 0;
    }

    .portal-side-nav.is-collapsed .portal-side-nav-link-text {
      display: none;
    }

    .portal-side-nav.is-collapsed .portal-side-nav-children {
      display: none;
    }

    .portal-side-nav.is-collapsed .portal-side-nav-disclosure {
      display: none;
    }

    .portal-side-nav.is-collapsed .portal-side-nav-row .portal-side-nav-link {
      padding-left: 0;
    }

    .portal-side-nav.is-collapsed .portal-side-nav-icon {
      display: inline;
      font-size: 0.65rem;
      font-weight: 700;
      letter-spacing: 0.03em;
      color: var(--text-muted);
    }

    .portal-side-nav.is-collapsed .portal-side-nav-link.active .portal-side-nav-icon,
    .portal-side-nav.is-collapsed .portal-side-nav-link.is-ancestor .portal-side-nav-icon {
      color: var(--text);
    }

    .portal-side-nav.is-collapsed .portal-side-nav-link.active {
      background: rgba(255, 255, 255, 0.05);
      border-left-color: var(--accent-mid);
    }

    .topbar {
      position: sticky;
      top: 0;
      z-index: 100;
      background: rgba(6, 9, 18, 0.94);
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
      padding: 0.45rem 0.75rem;
      border-radius: var(--radius-sm);
      transition: color 0.12s, background 0.12s;
    }

    .nav-link:hover { color: var(--text); background: rgba(255,255,255,0.04); }
    .nav-link.active {
      color: var(--text);
      background: rgba(255,255,255,0.05);
    }

    main {
      max-width: 1200px;
      margin: 0 auto;
      padding: 2rem 1.5rem 3rem;
      width: 100%;
      flex: 1;
    }

    .page-header { margin-bottom: 1.35rem; }

    .eyebrow {
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.16em;
      color: var(--accent-electric-gold);
      font-weight: 600;
      margin-bottom: 0.5rem;
    }

    .page-header h1 {
      font-size: clamp(1.6rem, 3.5vw, 2.1rem);
      font-weight: 650;
      letter-spacing: -0.03em;
      line-height: 1.15;
      margin-bottom: 0.4rem;
    }

    .page-header .subtitle { color: var(--text-muted); max-width: 52ch; font-size: 0.95rem; }

    .badge-row {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin-top: 0.75rem;
      margin-bottom: 1.5rem;
    }

    .page-header + .badge-row { margin-top: 0; }

    .badge {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      font-size: 0.75rem;
      font-weight: 500;
      padding: 0.22rem 0.55rem;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border);
      background: rgba(255,255,255,0.02);
      color: var(--text-muted);
    }

    .badge.accent {
      border-color: rgba(20, 184, 166, 0.28);
      color: #99f6e4;
      background: rgba(20, 184, 166, 0.06);
    }

    .section { margin-bottom: 1.75rem; }

    .section-title {
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--text-dim);
      font-weight: 600;
      margin-bottom: 0.75rem;
    }

    .card {
      background: var(--bg-elevated);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 1rem 1.15rem;
      box-shadow: none;
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
      padding: 1rem 1.1rem;
      border-left: 2px solid var(--accent-mid);
    }

    .kpi-card::before {
      display: none;
    }

    .kpi-label {
      font-size: 0.82rem;
      color: var(--text-muted);
      font-weight: 500;
      margin-bottom: 0.65rem;
    }

    .kpi-value {
      font-size: clamp(1.45rem, 2.8vw, 1.85rem);
      font-weight: 650;
      letter-spacing: -0.03em;
      font-variant-numeric: tabular-nums;
      margin-bottom: 0.4rem;
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

    .kpi-compare-card .kpi-compare-meta {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.75rem;
      margin-top: 0.45rem;
      font-size: 0.8rem;
    }

    .kpi-compare-card .kpi-prior {
      color: var(--text-muted);
    }

    .kpi-delta {
      font-weight: 600;
      font-variant-numeric: tabular-nums;
    }

    .kpi-delta.positive { color: #6ee7b7; }
    .kpi-delta.negative { color: #fca5a5; }
    .kpi-delta.neutral { color: var(--text-dim); }

    .quick-links { display: grid; gap: 0.65rem; }

    .quick-link {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
      padding: 0.75rem 0.9rem;
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
      font-size: 0.88rem;
      line-height: 1.45;
      margin-bottom: 0.75rem;
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

    .pack-version {
      display: inline-flex;
      align-items: center;
      font-size: 0.8rem;
      font-weight: 600;
      padding: 0.12rem 0.45rem;
      border-radius: var(--radius-sm);
      border: 1px solid rgba(20, 184, 166, 0.28);
      color: #99f6e4;
      background: rgba(20, 184, 166, 0.06);
    }

    .pack-history-subtitle {
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--text-dim);
      font-weight: 600;
      margin: 1.25rem 0 0.65rem;
    }

    .pack-history-subtitle:first-of-type {
      margin-top: 0;
    }

    tbody tr.history-empty-row td {
      padding: 0.35rem 1rem;
      font-size: 0.8rem;
      color: var(--text-dim);
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

    .chart-demo-source {
      font-size: 0.72rem;
      color: var(--text-dim);
      margin-top: 0.35rem;
      font-family: var(--font-mono);
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
      .shell-with-sidebar {
        height: auto;
        max-height: none;
        overflow: visible;
      }

      .shell-with-sidebar .portal-workspace {
        overflow: visible;
      }

      .shell-with-sidebar .portal-main {
        overflow-y: visible;
      }

      .topbar-inner { grid-template-columns: 1fr; }
      .brand { grid-column: 1; }
      .topbar-main { grid-column: 1; }
      .nav { margin-left: 0; width: 100%; flex-wrap: wrap; }
      .portal-workspace {
        flex-direction: column;
      }
      .portal-side-nav {
        width: 100%;
        min-height: auto;
        border-right: none;
        border-bottom: 1px solid var(--border);
      }
      .portal-side-nav.is-collapsed {
        width: 100%;
      }
      .portal-side-nav-links {
        flex-direction: row;
        flex-wrap: nowrap;
        overflow-x: auto;
        padding: 0.5rem;
      }
      .portal-side-nav-link {
        flex-shrink: 0;
        border-left: none;
        border-bottom: 2px solid transparent;
        padding: 0.55rem 0.85rem;
      }
      .portal-side-nav-link.active {
        border-left: none;
        border-bottom-color: var(--accent-mid);
      }
      .portal-side-nav-link.is-child {
        padding-left: 0.65rem;
      }
      .portal-side-nav-children {
        flex-direction: column;
        display: none;
        margin-left: 0;
        padding-left: 0;
        border-left: none;
      }
      .portal-side-nav-group.is-open > .portal-side-nav-children {
        display: flex;
      }
      .portal-side-nav-disclosure {
        display: none;
      }
      .portal-content {
        padding: 1.25rem 1rem 2rem;
      }
      .portal-footer {
        padding: 1rem 1rem 1.5rem;
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
      padding: 0.55rem 1rem;
      border-radius: var(--radius-sm);
      font-size: 0.875rem;
      font-weight: 600;
      text-decoration: none;
      border: 1px solid transparent;
      cursor: pointer;
      font: inherit;
      transition: opacity 0.12s, background 0.12s, border-color 0.12s;
    }

    .button:hover { opacity: 0.92; }
    .button:disabled,
    .btn:disabled {
      opacity: 0.55;
      cursor: not-allowed;
      transform: none;
    }
    .button.primary { background: var(--accent-light-blue); color: #ffffff; }
    .button.secondary {
      border-color: var(--border-strong);
      color: var(--text);
      background: rgba(255,255,255,0.04);
    }

    /* Portal forms historically used .btn; keep them aligned with the streamlined theme. */
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 0.55rem 1rem;
      border-radius: var(--radius-sm);
      font-size: 0.875rem;
      font-weight: 600;
      text-decoration: none;
      border: 1px solid var(--border-strong);
      color: var(--text);
      background: rgba(255,255,255,0.03);
      cursor: pointer;
      font: inherit;
      transition: opacity 0.12s, background 0.12s, border-color 0.12s;
    }
    .btn:hover { background: rgba(255,255,255,0.05); }
    .btn-primary {
      border-color: rgba(20, 184, 166, 0.35);
      background: var(--accent-mid);
      color: #ffffff;
      box-shadow: none;
    }
    .btn-primary:hover {
      background: #0d9488;
    }

    .feature-list { list-style: none; display: grid; gap: 0.85rem; }
    .feature-list li { display: grid; gap: 0.2rem; }
    .feature-list strong { color: var(--text); font-size: 0.95rem; }
    .feature-list span { color: var(--text-muted); font-size: 0.88rem; }

    .pricing-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 1rem;
      align-items: stretch;
    }

    .pricing-grid > .card + .card { margin-top: 0; }

    .pricing-card {
      display: flex;
      flex-direction: column;
      height: 100%;
    }

    .pricing-card .pricing-offer {
      min-height: 1.65rem;
      margin-bottom: 0.75rem;
    }

    .pricing-card .price {
      font-size: 1.8rem;
      font-weight: 700;
      letter-spacing: -0.03em;
      margin: 0.35rem 0;
    }

    .pricing-card .price span { font-size: 0.95rem; color: var(--text-muted); font-weight: 500; }
    .pricing-card .price-sub { color: var(--accent-mid); font-weight: 600; margin-bottom: 0.85rem; }
    .pricing-card.featured { box-shadow: inset 0 0 0 1px rgba(20,184,166,0.22); }

    .card h3 { font-size: 1.05rem; margin-bottom: 0.45rem; }
    .card p { color: var(--text-muted); font-size: 0.92rem; }

    .portal-badge {
      margin-left: auto;
      font-size: 0.78rem;
      color: var(--text-muted);
      padding: 0.28rem 0.55rem;
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      background: rgba(255,255,255,0.02);
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
      padding: 0.6rem 0.75rem;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border);
      background: rgba(255,255,255,0.03);
      color: var(--text);
      font: inherit;
    }

    .form-field select,
    .governance-role-select {
      padding: 0.6rem 0.75rem;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border);
      background: rgba(255,255,255,0.04);
      color: var(--text);
      font: inherit;
      font-size: inherit;
    }

    .form-field select {
      width: 100%;
    }

    .governance-role-select {
      min-width: 7rem;
    }

    .form-field input:focus,
    .form-field select:focus,
    .governance-role-select:focus {
      outline: none;
      border-color: rgba(56, 189, 248, 0.45);
      box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.12);
    }

    .btn.portal-submit-btn {
      padding: 0.4rem 0.85rem;
      font-size: 0.8rem;
      min-height: auto;
      border-radius: var(--radius-sm);
      box-shadow: none;
    }

    .btn.portal-submit-btn.btn-primary {
      background: var(--accent-mid);
      border: 1px solid rgba(20, 184, 166, 0.35);
    }

    .form-error {
      color: #fca5a5;
      font-size: 0.85rem;
      margin: 0 0 1.25rem;
    }

    .form-warning {
      color: #fbbf24;
      font-size: 0.85rem;
      margin: -0.15rem 0 1rem;
      line-height: 1.4;
    }

    .form-success {
      color: #6ee7b7;
      font-size: 0.85rem;
      margin: 0 0 1.25rem;
    }

    .login-actions { display: flex; justify-content: space-between; align-items: center; gap: 1rem; margin-top: 0.5rem; }

    .login-help {
      display: flex;
      justify-content: flex-end;
      margin: -0.35rem 0 1rem;
    }

    .login-help a {
      color: var(--text-muted);
      font-size: 0.82rem;
      text-decoration: none;
    }

    .login-help a:hover { color: var(--accent-end); }

    .form-hint {
      color: var(--text-dim);
      font-size: 0.78rem;
      margin: -0.35rem 0 1rem;
      line-height: 1.4;
    }

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
      border-radius: var(--radius-sm);
      border: 1px solid var(--border);
      background: rgba(10, 16, 28, 0.85);
      text-decoration: none;
      color: inherit;
      transition: border-color 0.12s, background 0.12s;
    }

    .flow-card:hover {
      border-color: var(--border-strong);
      background: rgba(255, 255, 255, 0.03);
    }

    .flow-card-icon {
      width: 44px;
      height: 44px;
      border-radius: var(--radius-sm);
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
      border-radius: var(--radius-sm);
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
      border-radius: var(--radius-sm);
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
      transition: background 0.12s;
    }

    a.platform-node:hover {
      background: rgba(255, 255, 255, 0.04);
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
      border-radius: var(--radius-sm);
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
      border-radius: var(--radius-sm);
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
      padding: 1.15rem;
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: var(--bg-elevated);
      box-shadow: none;
      position: relative;
      scroll-margin-top: 5.5rem;
    }

    .platform-layer:target {
      border-color: rgba(56, 189, 248, 0.35);
      box-shadow: inset 0 0 0 1px rgba(56, 189, 248, 0.12);
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
      border-radius: var(--radius);
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
      border-radius: var(--radius-sm);
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
      padding: 0.22rem 0.5rem;
      border-radius: var(--radius-sm);
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

    .assistant-chat-card {
      background: var(--bg-elevated);
    }

    .assistant-chat {
      display: flex;
      flex-direction: column;
      gap: 0.65rem;
      margin: 0.85rem 0 1rem;
      max-height: 420px;
      overflow: auto;
      padding: 0.15rem 0;
    }

    .assistant-bubble {
      align-self: flex-start;
      max-width: min(92%, 560px);
      padding: 0.7rem 0.9rem;
      border-radius: var(--radius-sm);
      border: 1px solid rgba(56, 189, 248, 0.15);
      background: rgba(20, 184, 166, 0.06);
      box-shadow: none;
    }

    .assistant-bubble.user {
      align-self: flex-end;
      border-color: rgba(245, 158, 11, 0.22);
      background: rgba(245, 158, 11, 0.06);
    }

    .assistant-bubble.thinking {
      opacity: 0.85;
      border-style: dashed;
    }

    .assistant-thinking-dots {
      display: inline-block;
      margin-left: 0.05em;
      letter-spacing: 0.02em;
    }

    .assistant-thinking-dots span {
      display: inline-block;
      opacity: 0.2;
      animation: assistant-dot-flow 1.2s ease-in-out infinite;
    }

    .assistant-thinking-dots span:nth-child(1) { animation-delay: 0s; }
    .assistant-thinking-dots span:nth-child(2) { animation-delay: 0.2s; }
    .assistant-thinking-dots span:nth-child(3) { animation-delay: 0.4s; }

    @keyframes assistant-dot-flow {
      0%, 80%, 100% { opacity: 0.15; transform: translateY(0); }
      40% { opacity: 1; transform: translateY(-0.12em); }
    }

    .assistant-bubble-label {
      font-size: 0.72rem;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--text-muted);
      font-weight: 600;
      margin-bottom: 0.35rem;
    }

    .assistant-bubble-text {
      white-space: pre-wrap;
      font-size: 0.92rem;
      line-height: 1.45;
      color: var(--text);
    }

    .assistant-compose {
      display: grid;
      gap: 0.85rem;
    }

    .assistant-compose-field { margin-bottom: 0; }

    .assistant-compose-input {
      width: 100%;
      min-height: 5rem;
      resize: vertical;
      padding: 0.65rem 0.85rem;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.03);
      color: var(--text);
      font: inherit;
      line-height: 1.45;
      box-shadow: none;
    }

    .governance-role-form {
      display: flex;
      gap: 0.5rem;
      align-items: center;
      margin: 0;
    }

    .governance-invite-section {
      margin-bottom: 1.5rem;
    }

    .governance-invite-section .section-title {
      margin-bottom: 0.65rem;
    }

    .governance-invite-card {
      padding: 0.85rem 1rem;
    }

    .governance-invite-note {
      color: var(--text-muted);
      font-size: 0.8rem;
      line-height: 1.4;
      margin: 0 0 0.65rem;
    }

    .governance-invite-form {
      display: grid;
      grid-template-columns: minmax(7rem, 1fr) minmax(9rem, 1.35fr) minmax(6.5rem, 0.7fr) auto;
      gap: 0.55rem 0.65rem;
      align-items: end;
    }

    .governance-invite-form .form-field {
      margin-bottom: 0;
      gap: 0.2rem;
    }

    .governance-invite-form .form-field label {
      font-size: 0.72rem;
    }

    .governance-invite-form .form-field input,
    .governance-invite-form .form-field select {
      padding: 0.42rem 0.62rem;
      border-radius: 8px;
      font-size: 0.84rem;
    }

    .governance-invite-form .governance-invite-action {
      align-self: end;
    }

    .governance-edit-form .yaml-editor {
      width: 100%;
      min-height: 10rem;
      resize: vertical;
      padding: 0.85rem 1rem;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border);
      background: rgba(0, 0, 0, 0.22);
      color: var(--text);
      font-family: var(--font-mono);
      font-size: 0.82rem;
      line-height: 1.55;
      tab-size: 2;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
    }

    .governance-edit-form .yaml-editor:focus {
      outline: none;
      border-color: rgba(56, 189, 248, 0.45);
      box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.12);
    }

    .governance-edit-form-actions {
      display: flex;
      gap: 0.75rem;
      flex-wrap: wrap;
      margin-top: 0.25rem;
    }

    .governance-manual-packs .assistant-pack-block:first-child {
      margin-top: 0;
      padding-top: 0;
      border-top: none;
    }

    .version-bump-row {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      flex-wrap: wrap;
    }

    .version-bump-row input[readonly] {
      flex: 0 1 7.5rem;
      min-width: 6.5rem;
      cursor: default;
      color: var(--text);
      background: rgba(0, 0, 0, 0.28);
    }

    .version-bump-buttons {
      display: flex;
      gap: 0.35rem;
      flex-wrap: wrap;
    }

    .btn.version-bump-btn {
      padding: 0.35rem 0.6rem;
      font-size: 0.72rem;
      font-weight: 600;
      letter-spacing: 0.02em;
      line-height: 1.2;
      min-height: 0;
    }

    .btn.version-bump-btn.is-active {
      border-color: rgba(56, 189, 248, 0.55);
      background: rgba(56, 189, 248, 0.14);
      color: #bae6fd;
    }

    #governance-update {
      scroll-margin-top: 5.5rem;
    }

    .governance-update-card {
      padding-top: 0;
    }

    .governance-usage-meter {
      margin: 0 -1.15rem;
      padding: 0.85rem 1.15rem 0.75rem;
      border-bottom: 1px solid var(--border);
      background: color-mix(in srgb, var(--surface-2) 70%, transparent);
    }

    .governance-usage-head {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 0.75rem;
      margin-bottom: 0.45rem;
    }

    .governance-usage-label {
      font-size: 0.82rem;
      font-weight: 600;
      color: var(--text);
    }

    .governance-usage-value {
      font-size: 0.82rem;
      font-weight: 700;
      color: var(--accent);
      font-variant-numeric: tabular-nums;
    }

    .governance-usage-track {
      height: 0.45rem;
      border-radius: 999px;
      background: color-mix(in srgb, var(--border) 80%, transparent);
      overflow: hidden;
    }

    .governance-usage-fill {
      height: 100%;
      border-radius: inherit;
      background: linear-gradient(90deg, var(--accent), color-mix(in srgb, var(--accent) 70%, #fff));
      transition: width 0.25s ease;
    }

    .governance-usage-fill.warn {
      background: linear-gradient(90deg, #d97706, #f59e0b);
    }

    .governance-usage-fill.critical {
      background: linear-gradient(90deg, #dc2626, #ef4444);
    }

    .governance-usage-meta {
      margin: 0.45rem 0 0;
      font-size: 0.74rem;
      color: var(--text-dim);
      font-variant-numeric: tabular-nums;
    }

    .governance-usage-limit {
      margin: 0.55rem 0 0;
      font-size: 0.78rem;
      color: #b45309;
    }

    .dna-refresh-status {
      margin: 0 -1.15rem;
      padding: 0.95rem 1.15rem 0.85rem;
      border-bottom: 1px solid var(--border);
      background: color-mix(in srgb, var(--surface-2) 55%, transparent);
    }

    .dna-refresh-status-head {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 1rem;
      flex-wrap: wrap;
    }

    .dna-refresh-state {
      display: inline-flex;
      align-items: center;
      padding: 0.2rem 0.55rem;
      border-radius: 999px;
      font-size: 0.74rem;
      font-weight: 700;
      letter-spacing: 0.02em;
      text-transform: uppercase;
    }

    .dna-refresh-state.current {
      color: #047857;
      background: color-mix(in srgb, #10b981 18%, transparent);
    }

    .dna-refresh-state.stale {
      color: #b45309;
      background: color-mix(in srgb, #f59e0b 20%, transparent);
    }

    .dna-refresh-state.in-progress {
      color: #1d4ed8;
      background: color-mix(in srgb, #3b82f6 18%, transparent);
    }

    .dna-refresh-status-detail {
      margin: 0.45rem 0 0;
      font-size: 0.82rem;
      color: var(--text-dim);
      max-width: 42rem;
      line-height: 1.45;
    }

    .dna-refresh-form {
      margin: 0;
      flex: 0 0 auto;
    }

    .dna-refresh-quota-meta {
      margin: 0.65rem 0 0;
      font-size: 0.76rem;
      color: var(--text-dim);
      font-variant-numeric: tabular-nums;
    }

    .dna-refresh-limit {
      margin: 0.45rem 0 0;
      font-size: 0.78rem;
      color: #b45309;
    }

    .governance-update-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
      border-bottom: 1px solid var(--border);
      margin: 0 -1.15rem 0.65rem;
      padding: 0 1.15rem;
      flex-wrap: wrap;
    }

    .governance-update-tabs {
      display: flex;
      gap: 0;
      border-bottom: none;
      margin: 0;
      padding: 0;
      flex: 1;
      min-width: 0;
    }

    .governance-update-pins {
      margin: 0;
      padding: 0.45rem 0;
      font-size: 0.78rem;
      color: var(--text-dim);
      white-space: nowrap;
      flex-shrink: 0;
    }

    .governance-update-pins code {
      font-size: 0.76rem;
      color: var(--text-muted);
    }

    .governance-update-tab {
      padding: 0.65rem 1rem;
      border: none;
      border-bottom: 2px solid transparent;
      margin-bottom: -1px;
      background: transparent;
      color: var(--text-muted);
      cursor: pointer;
      font: inherit;
      font-size: 0.84rem;
      font-weight: 500;
      transition: color 0.12s, border-color 0.12s;
    }

    .governance-update-tab:hover {
      color: var(--text);
    }

    .governance-update-tab.active {
      color: var(--text);
      border-bottom-color: var(--accent-mid);
    }

    .governance-update-panel[hidden] {
      display: none;
    }

    .governance-update-panel .assistant-chat-shell {
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      background: rgba(255, 255, 255, 0.02);
      padding: 0.65rem 0.75rem 0.7rem;
    }

    .governance-update-panel .assistant-chat {
      margin: 0 0 0.55rem;
      gap: 0.55rem;
      max-height: 240px;
      padding: 0;
    }

    .governance-update-panel .assistant-chat:empty,
    .governance-update-panel .assistant-chat .pack-card-lead {
      margin: 0;
      font-size: 0.86rem;
      line-height: 1.35;
    }

    .governance-update-panel .assistant-compose {
      gap: 0.5rem;
    }

    .governance-update-panel .assistant-compose-input {
      min-height: 3.25rem;
      padding: 0.55rem 0.75rem;
      border-radius: var(--radius-sm);
    }

    .governance-update-panel .assistant-bubble {
      padding: 0.55rem 0.75rem;
      border-radius: var(--radius-sm);
    }

    .governance-update-panel .assistant-bubble.user {
      border-radius: var(--radius-sm);
    }

    .governance-update-restricted-note {
      color: var(--text-muted);
      font-size: 0.9rem;
      line-height: 1.55;
      margin: 0;
    }

    .governance-proposal-card {
      margin-top: 1rem;
    }

    .assistant-cancel-form {
      margin-top: 0.75rem;
    }

    @media (max-width: 820px) {
      .governance-invite-form {
        grid-template-columns: 1fr 1fr;
      }

      .governance-invite-form .governance-invite-action {
        grid-column: 1 / -1;
      }
    }

    @media (max-width: 520px) {
      .governance-invite-form {
        grid-template-columns: 1fr;
      }
    }

    .assistant-compose-input:focus {
      outline: none;
      border-color: rgba(56, 189, 248, 0.45);
      box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.12);
    }

    .assistant-compose .btn,
    .assistant-chat-card .btn,
    .assistant-pack-block .btn,
    .assistant-approve-form .btn {
      border-radius: var(--radius-sm);
      padding: 0.55rem 1rem;
    }

    .assistant-compose .assistant-send-btn,
    .assistant-compose .portal-submit-btn {
      justify-self: start;
      padding: 0.38rem 0.85rem;
      font-size: 0.8rem;
      min-height: auto;
      box-shadow: none;
    }

    .assistant-compose .btn-primary,
    .assistant-approve-form .btn-primary {
      background: var(--accent-mid);
      border: 1px solid rgba(20, 184, 166, 0.35);
      box-shadow: none;
    }

    .assistant-compose .assistant-send-btn.btn-primary,
    .assistant-compose .portal-submit-btn.btn-primary {
      box-shadow: none;
    }

    .assistant-chat-card .btn:not(.btn-primary) {
      border-radius: var(--radius-sm);
      border-color: var(--border-strong);
      background: rgba(255, 255, 255, 0.03);
      box-shadow: none;
    }

    .assistant-actions {
      margin-top: 0.75rem;
      display: flex;
      gap: 0.75rem;
      flex-wrap: wrap;
    }

    .assistant-pack-block {
      margin-top: 1.25rem;
      padding-top: 1rem;
      border-top: 1px solid var(--border);
    }

    #kpi-generator-validation-filters .kpi-validation-shell {
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      background: rgba(255, 255, 255, 0.02);
      padding: 0.85rem 0.9rem;
    }

    #kpi-generator-validation-filters .kpi-filter-header,
    #kpi-generator-validation-filters .kpi-filter-row {
      display: grid;
      grid-template-columns: minmax(0, 1.2fr) minmax(0, 1.2fr) minmax(0, 1fr) auto;
      gap: 0.55rem;
      align-items: center;
    }

    #kpi-generator-validation-filters .kpi-filter-header {
      margin-bottom: 0.55rem;
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--text-dim);
      font-weight: 600;
    }

    #kpi-generator-validation-filters .kpi-filter-row {
      margin-bottom: 0.55rem;
    }

    #kpi-generator-validation-filters .kpi-filter-control {
      width: 100%;
      padding: 0.5rem 0.65rem;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border);
      background: rgba(0, 0, 0, 0.42);
      color: var(--text);
      font: inherit;
      font-size: 0.88rem;
      min-height: 2.35rem;
    }

    #kpi-generator-validation-filters select.kpi-filter-control {
      background-color: #0a101c;
      color-scheme: dark;
    }

    #kpi-generator-validation-filters .kpi-filter-control::placeholder {
      color: var(--text-dim);
    }

    #kpi-generator-validation-filters .kpi-filter-control:focus {
      outline: none;
      border-color: rgba(56, 189, 248, 0.45);
      box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.12);
    }

    #kpi-generator-validation-filters .kpi-filter-actions {
      margin-top: 0.65rem;
    }

    #kpi-generator-results .kpi-chip-list {
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem;
      margin: 0;
      padding: 0;
      list-style: none;
    }

    #kpi-generator-results .kpi-chip {
      display: inline-flex;
      align-items: center;
      padding: 0.18rem 0.55rem;
      border-radius: 999px;
      border: 1px solid rgba(56, 189, 248, 0.22);
      background: rgba(56, 189, 248, 0.08);
      color: #bae6fd;
      font-size: 0.78rem;
      line-height: 1.35;
    }

    #kpi-generator-results .kpi-calculation {
      margin: 0;
      font-size: 0.92rem;
      line-height: 1.5;
      color: var(--text);
      white-space: pre-wrap;
    }

    #kpi-generator-results .kpi-section-heading {
      font-size: 0.92rem;
      font-weight: 600;
      letter-spacing: 0.01em;
      text-transform: none;
      color: #e8eef8;
      margin: 0 0 0.75rem;
      padding: 0.4rem 0.75rem;
      border-left: 3px solid rgba(20, 184, 166, 0.65);
      background: linear-gradient(90deg, rgba(20, 184, 166, 0.1), transparent 70%);
      border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
    }

    #kpi-generator-results .kpi-sql-details summary {
      cursor: pointer;
      color: var(--text-muted);
      font-size: 0.86rem;
      user-select: none;
    }

    #kpi-generator-results .kpi-sql-details summary:hover {
      color: var(--text);
    }

    #kpi-generator-results .kpi-sql-block {
      margin: 0.65rem 0 0;
      padding: 0.85rem 1rem;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border);
      background: rgba(0, 0, 0, 0.32);
      color: #dbeafe;
      font-family: var(--font-mono);
      font-size: 0.82rem;
      line-height: 1.55;
      white-space: pre;
      overflow-x: auto;
      tab-size: 2;
    }

    #kpi-generator-results .assistant-pack-block:first-of-type {
      margin-top: 0.85rem;
      padding-top: 0;
      border-top: none;
    }

    @media (max-width: 820px) {
      #kpi-generator-validation-filters .kpi-filter-header {
        display: none;
      }

      #kpi-generator-validation-filters .kpi-filter-row {
        grid-template-columns: 1fr;
      }
    }

    .assistant-diff-shell {
      margin-top: 0.65rem;
    }

    .assistant-diff-nav {
      display: flex;
      align-items: center;
      gap: 0.65rem;
      flex-wrap: wrap;
      margin-bottom: 0.45rem;
    }

    .assistant-diff-nav-label {
      color: var(--text-muted);
      font-size: 0.82rem;
    }

    .assistant-diff-nav-btn {
      padding: 0.35rem 0.65rem;
      font-size: 0.82rem;
    }

    .assistant-diff {
      overflow: auto;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 0.8rem;
      line-height: 1.45;
      max-height: 280px;
      padding: 0.35rem 0;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border);
      background: rgba(0, 0, 0, 0.22);
    }

    .assistant-diff-empty {
      padding: 0.75rem 0.85rem;
      color: var(--text-muted);
    }

    .assistant-diff-line {
      white-space: pre-wrap;
      word-break: break-word;
      padding: 0.1rem 0.85rem;
    }

    .assistant-diff-line.context {
      color: var(--text-muted);
    }

    .assistant-diff-line.is-out-of-page {
      display: none;
    }

    .assistant-diff-line.del {
      color: #fecaca;
      background: rgba(239, 68, 68, 0.18);
    }

    .assistant-diff-line.add {
      color: #bbf7d0;
      background: rgba(34, 197, 94, 0.16);
    }

    .assistant-diff-line.current-change.del {
      background: rgba(239, 68, 68, 0.32);
    }

    .assistant-diff-line.current-change.add {
      background: rgba(34, 197, 94, 0.28);
    }

    .assistant-approve-form {
      margin-top: 0.85rem;
      display: flex;
      gap: 0.75rem;
      flex-wrap: wrap;
      align-items: end;
    }

    .assistant-approve-form .version-bump-field {
      flex: 1 1 100%;
      margin: 0;
    }

    .assistant-approve-form .form-field input {
      border-radius: var(--radius-sm);
      padding: 0.55rem 0.75rem;
      min-width: 8.5rem;
    }

    .assistant-approve-actions {
      display: flex;
      gap: 0.75rem;
      flex-wrap: wrap;
      align-items: center;
    }

    .assistant-status-pill {
      display: inline-flex;
      align-items: center;
      margin-left: 0.45rem;
      padding: 0.12rem 0.45rem;
      border-radius: var(--radius-sm);
      font-size: 0.68rem;
      font-weight: 600;
      letter-spacing: 0.03em;
      text-transform: uppercase;
      color: #99f6e4;
      background: rgba(20, 184, 166, 0.12);
      border: 1px solid rgba(20, 184, 166, 0.28);
      vertical-align: middle;
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
    data_menu: tuple[Any, ...] | None = None,
    side_nav_title: str | None = None,
    side_nav_items: tuple[Any, ...] | None = None,
    side_nav_id: str | None = None,
    sidebar_active_path: str | None = None,
    charts_assets: str = "",
    brand_href: str | None = None,
) -> str:
    window_title = escape(page_title or title)
    accent_style = ""
    if client_accent:
        accent_style = f"<style>:root {{ --accent-mid: {escape(client_accent)}; }}</style>"
    footer_text = footer_left or f"{BRAND_NAME} · {PRODUCT_SUBTITLE}"
    side_nav_html = ""
    if side_nav_title and side_nav_items and side_nav_id:
        side_nav_html = _side_nav_html(
            sidebar_active_path or active_path,
            url,
            side_nav_items,
            title=side_nav_title,
            nav_id=side_nav_id,
        )
    side_nav_script = _side_nav_script() if side_nav_html else ""
    home_href = brand_href if brand_href is not None else brand_home_href(url)
    if side_nav_html:
        content_block = f"""
    <div class="portal-workspace">
      {side_nav_html}
      <div class="portal-main">
        <div class="portal-content">{body}</div>
        <footer class="footer portal-footer">
          <span>{escape(footer_text)}</span>
          <span>Powered by Meshflow DNA</span>
        </footer>
      </div>
    </div>"""
        shell_class = "shell shell-with-sidebar"
        outer_footer = ""
    else:
        content_block = f"<main>{body}</main>"
        shell_class = "shell"
        outer_footer = f"""
    <footer class="footer">
      <span>{escape(footer_text)}</span>
      <span>Powered by Meshflow DNA</span>
    </footer>"""
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
  <div class="{shell_class}">
    <header class="topbar">
      <div class="topbar-inner">
        <a class="brand" href="{escape(home_href)}">
          <img src="{escape(url("/static/hiveflowai-symbol.png"))}" alt="{escape(BRAND_NAME)} symbol" width="36" height="36" />
          <div class="brand-text">
            <div class="brand-name">Hive Flow <span>AI</span></div>
            <div class="brand-tagline">{escape(TAGLINE)}</div>
          </div>
        </a>
        <div class="topbar-main">
          <div class="nav-actions">
            <nav class="nav" aria-label="Primary">{_nav_html(active_path, url, nav_links, data_menu=data_menu)}</nav>
            {topbar_extra}
          </div>
        </div>
      </div>
    </header>
    {content_block}{outer_footer}
  </div>
  {side_nav_script}
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
    data_menu: tuple[Any, ...] | None = None,
    side_nav_title: str | None = None,
    side_nav_items: tuple[Any, ...] | None = None,
    side_nav_id: str | None = None,
    sidebar_active_path: str | None = None,
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
        side_nav_title=side_nav_title,
        side_nav_items=side_nav_items,
        side_nav_id=side_nav_id,
        sidebar_active_path=sidebar_active_path,
        charts_assets=charts_assets,
        brand_href=link("/portal"),
    )


def render_login_page(
    *,
    url: Callable[[str], str],
    error: str = "",
    success: str = "",
    next_path: str = "/portal",
    mode: str = "sign_in",
    username: str = "",
    session: str = "",
) -> str:
    error_html = f'<div class="form-error">{escape(error)}</div>' if error else ""
    success_html = f'<div class="form-success">{escape(success)}</div>' if success else ""
    password_hint = (
        '<p class="form-hint">Use at least 12 characters with uppercase, lowercase, and a number.</p>'
    )
    forgot_href = escape(
        url(f"/portal/login?{urlencode({'mode': 'forgot_password', 'next': next_path})}")
    )
    sign_in_href = escape(url(f"/portal/login?{urlencode({'next': next_path})}"))

    if mode == "set_password":
        body = f"""
    <div class="login-shell">
      <div class="card login-card">
        <div class="eyebrow">Client portal</div>
        <h1 style="font-size:1.6rem;margin:0.35rem 0 0.5rem">Set your password</h1>
        <p class="hero-subtitle" style="margin-bottom:1.25rem">Choose a permanent password to finish activating your HiveFlowAI portal account.</p>
        {error_html}
        <form method="post" action="{escape(url("/portal/login"))}">
          <input type="hidden" name="action" value="set_password" />
          <input type="hidden" name="next" value="{escape(next_path)}" />
          <input type="hidden" name="username" value="{escape(username)}" />
          <input type="hidden" name="session" value="{escape(session)}" />
          <div class="form-field">
            <label for="username_display">Username</label>
            <input id="username_display" value="{escape(username)}" readonly />
          </div>
          <div class="form-field">
            <label for="new_password">New password</label>
            <input id="new_password" name="new_password" type="password" autocomplete="new-password" required />
          </div>
          {password_hint}
          <div class="form-field">
            <label for="confirm_password">Confirm password</label>
            <input id="confirm_password" name="confirm_password" type="password" autocomplete="new-password" required />
          </div>
          <div class="login-actions">
            <a class="button secondary" href="{sign_in_href}">Back to sign in</a>
            <button class="button primary" type="submit">Save password</button>
          </div>
        </form>
      </div>
    </div>
    """
        page_title = "Set password"
    elif mode == "forgot_password":
        body = f"""
    <div class="login-shell">
      <div class="card login-card">
        <div class="eyebrow">Client portal</div>
        <h1 style="font-size:1.6rem;margin:0.35rem 0 0.5rem">Forgot password</h1>
        <p class="hero-subtitle" style="margin-bottom:1.25rem">Enter your username or email and we will send a reset code if an account exists.</p>
        {error_html}{success_html}
        <form method="post" action="{escape(url("/portal/login"))}">
          <input type="hidden" name="action" value="forgot_password" />
          <input type="hidden" name="next" value="{escape(next_path)}" />
          <div class="form-field">
            <label for="username">Username or email</label>
            <input id="username" name="username" value="{escape(username)}" autocomplete="username" required autofocus />
          </div>
          <div class="login-actions">
            <a class="button secondary" href="{sign_in_href}">Back to sign in</a>
            <button class="button primary" type="submit">Send reset code</button>
          </div>
        </form>
      </div>
    </div>
    """
        page_title = "Forgot password"
    elif mode == "reset_password":
        body = f"""
    <div class="login-shell">
      <div class="card login-card">
        <div class="eyebrow">Client portal</div>
        <h1 style="font-size:1.6rem;margin:0.35rem 0 0.5rem">Reset your password</h1>
        <p class="hero-subtitle" style="margin-bottom:1.25rem">Enter the code from your email and choose a new password.</p>
        {error_html}{success_html}
        <form method="post" action="{escape(url("/portal/login"))}">
          <input type="hidden" name="action" value="confirm_forgot_password" />
          <input type="hidden" name="next" value="{escape(next_path)}" />
          <div class="form-field">
            <label for="username">Username or email</label>
            <input id="username" name="username" value="{escape(username)}" autocomplete="username" required />
          </div>
          <div class="form-field">
            <label for="confirmation_code">Reset code</label>
            <input id="confirmation_code" name="confirmation_code" inputmode="numeric" autocomplete="one-time-code" required autofocus />
          </div>
          <div class="form-field">
            <label for="new_password">New password</label>
            <input id="new_password" name="new_password" type="password" autocomplete="new-password" required />
          </div>
          {password_hint}
          <div class="form-field">
            <label for="confirm_password">Confirm password</label>
            <input id="confirm_password" name="confirm_password" type="password" autocomplete="new-password" required />
          </div>
          <div class="login-actions">
            <a class="button secondary" href="{forgot_href}">Request a new code</a>
            <button class="button primary" type="submit">Update password</button>
          </div>
        </form>
      </div>
    </div>
    """
        page_title = "Reset password"
    else:
        body = f"""
    <div class="login-shell">
      <div class="card login-card">
        <div class="eyebrow">Client portal</div>
        <h1 style="font-size:1.6rem;margin:0.35rem 0 0.5rem">Sign in to HiveFlowAI</h1>
        <p class="hero-subtitle" style="margin-bottom:1.25rem">Access your governed reporting portal with your client credentials.</p>
        {error_html}{success_html}
        <form method="post" action="{escape(url("/portal/login"))}">
          <input type="hidden" name="action" value="sign_in" />
          <input type="hidden" name="next" value="{escape(next_path)}" />
          <div class="form-field">
            <label for="username">Username</label>
            <input id="username" name="username" autocomplete="username" required />
          </div>
          <div class="form-field">
            <label for="password">Password</label>
            <input id="password" name="password" type="password" autocomplete="current-password" required />
          </div>
          <div class="login-help">
            <a href="{forgot_href}">Forgot password?</a>
          </div>
          <div class="login-actions">
            <a class="button secondary" href="{escape(brand_home_href(url))}">Back to site</a>
            <button class="button primary" type="submit">Sign in</button>
          </div>
        </form>
      </div>
    </div>
    """
        page_title = "Client login"
    return _layout_shell(
        title="Client login",
        body=body,
        active_path="/portal/login",
        nav_links=(("/", "Home"), ("/pricing", "Pricing"), ("/portal/login", "Client login")),
        url=url,
        page_title=page_title,
    )
