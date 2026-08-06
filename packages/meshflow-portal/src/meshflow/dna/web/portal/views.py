"""Protected client portal reporting views."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable

from werkzeug.wrappers import Request, Response

from meshflow.dna.settings import DnaSettings
from meshflow.dna.store import load_pack_from_settings, read_json_artifact, read_production_output
from meshflow.dna.web.portal.config import ClientPortalConfig
from meshflow.dna.web.charts import charts_page_assets
from meshflow.dna.web.charts.catalog import CHART_TYPE_CATALOG
from meshflow.dna.web.charts.demo import chart_demo_has_charts, chart_demo_section_html
from meshflow.dna.web.charts.gold import (
    REVENUE_OUTPUT_ID,
    aggregate_revenue_by_month,
)
from meshflow.dna.web.theme import (
    TAGLINE,
    badge_row,
    empty_state,
    escape,
    page_header,
    render_portal_page,
)
from meshflow.dna.web.portal.catalog import catalog_section_nav
from meshflow.dna.web.portal.reporting_layout import (
    is_chart_catalog_page,
    reporting_data_menu,
    reporting_quick_links,
)
from meshflow.dna.web.portal.reporting_render import (
    DEFAULT_CHART_MONTHS,
    DEFAULT_TABLE_LIMIT,
    generic_table_html,
    page_eyebrow,
    page_has_content,
    render_page_body,
)
from meshflow.dna.workflow import load_workflow_state

REVENUE_OUTPUT_ID = REVENUE_OUTPUT_ID
REVENUE_TABLE_LIMIT = DEFAULT_TABLE_LIMIT
REVENUE_TREND_MONTHS = DEFAULT_CHART_MONTHS

PORTAL_NAV = (
    ("/portal/catalog", "Catalog"),
    ("/portal/governance", "Governance"),
)

# In-page sub-nav under Governance (always visible; pages enforce admin auth).
GOVERNANCE_SECTION_NAV = (
    ("/portal/governance", "Pack Registry"),
    ("/portal/governance/users", "Users"),
)

CONFIG_ASSISTANT_ACTIONS = frozenset(
    {
        "chat",
        "cancel_running",
        "preview",
        "approve_dna",
        "approve_reporting",
        "deny",
        "deny_dna",
        "deny_reporting",
    }
)

MANUAL_GOVERNANCE_ACTIONS = frozenset(
    {
        "manual_draft_dna",
        "manual_approve_dna",
        "manual_draft_reporting",
        "manual_approve_reporting",
    }
)

# Legacy fallbacks when reporting config cannot be loaded (tests / empty seed).
PORTAL_DATA_MENU = (
    ("/portal", "Summary"),
    ("/portal/executive", "Executive"),
    (
        "/portal/sales",
        "Sales",
        (
            ("/portal/revenue", "Order-to-cash detail"),
            ("/portal/revenue-trend", "Revenue trend"),
        ),
    ),
    ("/portal/operations", "Operations"),
    ("/portal/finance", "Finance"),
    ("/portal/inventory", "Inventory"),
)

PORTAL_REPORT_PAGES = (
    ("/portal/executive", "Executive KPIs", "Full metric cards with definitions and pack provenance"),
    ("/portal/revenue", "Order-to-cash detail", "Posted invoice lines from certified gold output"),
    ("/portal/revenue-trend", "Revenue trend", "Monthly posted revenue from certified invoice lines"),
)

def _format_published_date(published_at: Any) -> str:
    text = str(published_at).strip()
    if not text:
        return text
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%b %d, %Y")
    except ValueError:
        return text[:10] if len(text) >= 10 else text


def render_assistant_diff_html(
    before: str,
    after: str,
    *,
    empty_label: str = "(no changes)",
) -> str:
    """Render a full-file YAML diff with highlighted adds/removes and change paging."""
    from meshflow.dna.web.portal.config_assistant.proposals import (
        build_yaml_diff_lines,
        yaml_content_changed,
    )

    if not yaml_content_changed(before, after):
        return (
            f'<div class="assistant-diff assistant-diff-empty">'
            f"{escape(empty_label)}</div>"
        )

    diff_lines = build_yaml_diff_lines(before, after)
    line_html: list[str] = []
    for entry in diff_lines:
        kind = str(entry.get("kind") or "context")
        hunk = int(entry.get("hunk") or 0)
        classes = ["assistant-diff-line", kind]
        if hunk:
            classes.append("change")
        line_html.append(
            f'<div class="{" ".join(classes)}" data-hunk="{hunk}" data-line-index="{len(line_html)}">'
            f"{escape(str(entry.get('text') or ''))}</div>"
        )

    return (
        f'<div class="assistant-diff-shell" data-assistant-diff data-diff-context="3" data-diff-context-after="2">'
        f'<div class="assistant-diff-nav">'
        f'<button type="button" class="btn assistant-diff-nav-btn" data-diff-prev '
        f'aria-label="Previous change" disabled>Previous</button>'
        f'<span class="assistant-diff-nav-label" data-diff-label></span>'
        f'<button type="button" class="btn assistant-diff-nav-btn" data-diff-next '
        f'aria-label="Next change" disabled>Next</button>'
        f"</div>"
        f'<div class="assistant-diff">{"".join(line_html)}</div>'
        f"</div>"
    )


def _assistant_diff_nav_script() -> str:
    return """<script>
(function () {
  function computeHunkWindow(allLines, hunkId, contextBefore, contextAfter) {
    var firstChangeIdx = -1;
    var lastChangeIdx = -1;
    for (var i = 0; i < allLines.length; i += 1) {
      if (parseInt(allLines[i].getAttribute("data-hunk") || "0", 10) === hunkId) {
        if (firstChangeIdx < 0) firstChangeIdx = i;
        lastChangeIdx = i;
      }
    }
    if (firstChangeIdx < 0) return null;

    var anchorIdx = firstChangeIdx;
    var beforeCount = 0;
    while (anchorIdx > 0 && beforeCount < contextBefore) {
      var prev = allLines[anchorIdx - 1];
      if (parseInt(prev.getAttribute("data-hunk") || "0", 10) !== 0) break;
      if (!prev.classList.contains("context")) break;
      anchorIdx -= 1;
      beforeCount += 1;
    }

    var endIdx = lastChangeIdx;
    var afterCount = 0;
    while (endIdx < allLines.length - 1 && afterCount < contextAfter) {
      var next = allLines[endIdx + 1];
      if (parseInt(next.getAttribute("data-hunk") || "0", 10) !== 0) break;
      if (!next.classList.contains("context")) break;
      endIdx += 1;
      afterCount += 1;
    }

    return { anchorIdx: anchorIdx, endIdx: endIdx };
  }

  function applyHunkWindow(shell, hunkId) {
    var body = shell.querySelector(".assistant-diff");
    if (!body) return false;

    var contextBefore = parseInt(shell.getAttribute("data-diff-context") || "3", 10);
    var contextAfter = parseInt(shell.getAttribute("data-diff-context-after") || "2", 10);
    if (!Number.isFinite(contextBefore) || contextBefore < 0) contextBefore = 3;
    if (!Number.isFinite(contextAfter) || contextAfter < 0) contextAfter = 2;

    var allLines = body.querySelectorAll(".assistant-diff-line");
    var windowRange = computeHunkWindow(allLines, hunkId, contextBefore, contextAfter);
    if (!windowRange) return false;

    for (var i = 0; i < allLines.length; i += 1) {
      var outOfPage = i < windowRange.anchorIdx || i > windowRange.endIdx;
      allLines[i].classList.toggle("is-out-of-page", outOfPage);
    }
    body.scrollTop = 0;
    return true;
  }

  function showDiffHunk(shell, index) {
    var body = shell.querySelector(".assistant-diff");
    var label = shell.querySelector("[data-diff-label]");
    var prevBtn = shell.querySelector("[data-diff-prev]");
    var nextBtn = shell.querySelector("[data-diff-next]");
    if (!body || !label || !prevBtn || !nextBtn) return;

    var hunkIds = (shell.getAttribute("data-diff-hunks") || "")
      .split(",")
      .filter(Boolean)
      .map(function (value) { return parseInt(value, 10); });
    if (!hunkIds.length) return;

    index = Math.max(0, Math.min(hunkIds.length - 1, index));
    shell.setAttribute("data-diff-index", String(index));

    var hunkId = hunkIds[index];
    body.querySelectorAll(".assistant-diff-line.current-change").forEach(function (el) {
      el.classList.remove("current-change");
    });
    var lines = body.querySelectorAll('[data-hunk="' + hunkId + '"]');
    lines.forEach(function (el) {
      el.classList.add("current-change");
    });
    applyHunkWindow(shell, hunkId);

    label.textContent = "Change " + (index + 1) + " of " + hunkIds.length;
    prevBtn.disabled = index === 0;
    nextBtn.disabled = index === hunkIds.length - 1;
  }

  function initAssistantDiffShells(root) {
    var scope = root || document;
    scope.querySelectorAll("[data-assistant-diff]").forEach(function (shell) {
      if (shell.getAttribute("data-diff-ready") === "1") return;

      var body = shell.querySelector(".assistant-diff");
      var label = shell.querySelector("[data-diff-label]");
      var prevBtn = shell.querySelector("[data-diff-prev]");
      var nextBtn = shell.querySelector("[data-diff-next]");
      if (!body || !label || !prevBtn || !nextBtn) return;

      var hunkIds = [];
      body.querySelectorAll("[data-hunk]").forEach(function (line) {
        var id = parseInt(line.getAttribute("data-hunk") || "0", 10);
        if (id > 0 && hunkIds.indexOf(id) === -1) hunkIds.push(id);
      });

      shell.setAttribute("data-diff-ready", "1");
      if (!hunkIds.length) {
        label.textContent = "No highlighted changes";
        prevBtn.disabled = true;
        nextBtn.disabled = true;
        return;
      }

      shell.setAttribute("data-diff-hunks", hunkIds.join(","));
      shell.setAttribute("data-diff-index", "0");
      showDiffHunk(shell, 0);
    });
  }

  document.addEventListener("click", function (event) {
    var target = event.target;
    if (!target || typeof target.closest !== "function") return;

    var nextBtn = target.closest("[data-diff-next]");
    var prevBtn = target.closest("[data-diff-prev]");
    if (!nextBtn && !prevBtn) return;

    event.preventDefault();
    var shell = (nextBtn || prevBtn).closest("[data-assistant-diff]");
    if (!shell || shell.getAttribute("data-diff-ready") !== "1") return;

    var hunkIds = (shell.getAttribute("data-diff-hunks") || "").split(",").filter(Boolean);
    var index = parseInt(shell.getAttribute("data-diff-index") || "0", 10);
    if (nextBtn && index < hunkIds.length - 1) {
      showDiffHunk(shell, index + 1);
    } else if (prevBtn && index > 0) {
      showDiffHunk(shell, index - 1);
    }
  });

  document.addEventListener("meshflow:assistant-live-updated", function (event) {
    var root = event.target && event.target.id === "config-assist-live"
      ? event.target
      : document;
    initAssistantDiffShells(root);
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      initAssistantDiffShells(document);
    });
  } else {
    initAssistantDiffShells(document);
  }
})();
</script>"""


def _history_entry_target(entry: dict[str, Any]) -> str:
    target = str(entry.get("target") or "").strip().lower()
    if target:
        return target
    notes = str(entry.get("notes") or "")
    if "Updated via client portal" in notes:
        return "all"
    return "dna"


def _filter_pack_history(history: list[Any], pack_kind: str) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for entry in history:
        if not isinstance(entry, dict):
            continue
        target = _history_entry_target(entry)
        if pack_kind == "dna" and target in {"dna", "all"}:
            filtered.append(entry)
        elif pack_kind == "reporting" and target in {"reporting", "all"}:
            filtered.append(entry)
    return filtered


def _history_table_rows(
    history: list[dict[str, Any]],
    *,
    pack_kind: str = "dna",
    active_version: str = "",
    is_admin: bool = False,
    form_action: str = "",
    settings: DnaSettings | None = None,
) -> str:
    from meshflow.dna.web.portal.governance_restore import (
        RestoreTarget,
        governance_target_snapshot_exists,
    )

    target: RestoreTarget = "dna" if pack_kind == "dna" else "reporting"
    restore_action = "restore_dna" if target == "dna" else "restore_reporting"
    label = "DNA" if target == "dna" else "reporting"
    col_count = 6 if is_admin else 5
    rows = ""
    for entry in reversed(history):
        version = str(entry.get("version") or "").strip()
        version_label = escape(version or "—")
        action_cell = ""
        if is_admin:
            if version and version == str(active_version or "").strip():
                action_cell = '<td><span class="muted">Current</span></td>'
            elif (
                version
                and form_action
                and settings is not None
                and governance_target_snapshot_exists(
                    settings, target=target, version=version
                )
            ):
                confirm = (
                    f"Restore {label} from v{version}? "
                    "This creates a new patch version and pins it as production. "
                    "Gold outputs are not republished automatically."
                )
                action_cell = (
                    f'<td><form method="post" action="{escape(form_action)}" '
                    f'class="history-restore-form" '
                    f"onsubmit=\"return window.confirm({escape(repr(confirm))});\">"
                    f'<input type="hidden" name="action" value="{escape(restore_action)}">'
                    f'<input type="hidden" name="source_version" value="{escape(version)}">'
                    f'<button type="submit" class="btn">Revert</button>'
                    f"</form></td>"
                )
            else:
                action_cell = "<td>—</td>"
        rows += (
            f"<tr><td>v{version_label}</td>"
            f"<td>{escape(str(entry.get('status', '—')))}</td>"
            f"<td>{escape(entry.get('approver') or '—')}</td>"
            f"<td>{escape(_format_published_date(entry.get('at')) if entry.get('at') else '—')}</td>"
            f"<td>{escape(entry.get('notes') or '—')}</td>"
            f"{action_cell}</tr>"
        )
    if rows:
        return rows
    return f"<tr><td colspan='{col_count}'>No promotion history recorded yet</td></tr>"


def _portal_nav_links(*, is_admin: bool = False) -> tuple[tuple[str, str], ...]:
    del is_admin  # top nav is the same; admin tools live under Governance sub-nav
    return PORTAL_NAV


def _portal_nav_active_path(active_path: str) -> str:
    if active_path == "/portal/semantics":
        return "/portal/governance"
    if active_path.startswith("/portal/governance") or active_path.startswith(
        "/portal/admin/"
    ):
        return "/portal/governance"
    if active_path.startswith("/portal/catalog"):
        return "/portal/catalog"
    return active_path


def _preview_banner_html(
    url: Callable[[str], str],
    *,
    next_version: str,
    proposal_id: str,
) -> str:
    return f"""
    <div class="form-success" style="margin-bottom:1rem">
      Previewing proposed config <strong>v{escape(next_version)}</strong>
      (proposal <code>{escape(proposal_id)}</code>) — not live.
      <a href="{escape(url('/portal/governance?update=assist'))}">Back to Pack Registry</a>
      ·
      <a href="{escape(url('/portal/governance/config/preview/exit'))}">Exit preview</a>
    </div>
    """


def _report_page_links_html(
    url: Callable[[str], str],
    *,
    settings: DnaSettings | None = None,
    reporting_override: dict[str, Any] | None = None,
) -> str:
    if settings is not None:
        pages = reporting_quick_links(settings, override=reporting_override)
    else:
        pages = PORTAL_REPORT_PAGES
    links = []
    for path, title, subtitle in pages:
        links.append(
            f"""
          <a class="quick-link" href="{escape(url(path))}">
            <div><strong>{escape(title)}</strong><br><span>{escape(subtitle)}</span></div>
            <span class="arrow">→</span>
          </a>"""
        )
    return f'<div class="quick-links">{"".join(links)}</div>'


_PILLAR_LABELS = {
    "executive": "Executive",
    "sales": "Sales",
    "operations": "Operations",
    "finance": "Finance",
    "inventory": "Inventory",
    "developer": "Developer",
}


def _pillar_grouped_links_html(
    url: Callable[[str], str],
    *,
    settings: DnaSettings | None = None,
    reporting_override: dict[str, Any] | None = None,
) -> str:
    from meshflow.dna.web.portal.reporting_layout import list_reporting_pages

    if settings is None:
        return _report_page_links_html(url, settings=settings, reporting_override=reporting_override)

    by_pillar: dict[str, list[dict[str, Any]]] = {}
    for page in list_reporting_pages(settings, override=reporting_override):
        path = page.get("path") or ""
        if path in {"/portal", "/portal/"}:
            continue
        pillar = str(page.get("pillar") or "sales")
        by_pillar.setdefault(pillar, []).append(page)

    order = ("executive", "sales", "operations", "finance", "inventory", "developer")
    sections: list[str] = []
    for pillar in order:
        pages = by_pillar.get(pillar) or []
        if not pages:
            continue
        content_pages = [
            page
            for page in pages
            if page_has_content(page) or page.get("chart_catalog")
        ]
        # When a pillar has detail pages, omit the empty hub landing from quick links.
        pages = content_pages or pages
        label = _PILLAR_LABELS.get(pillar, pillar.title())
        links = []
        for page in pages:
            links.append(
                f"""
          <a class="quick-link" href="{escape(url(page['path']))}">
            <div><strong>{escape(page['title'])}</strong><br><span>{escape(page.get('description') or '')}</span></div>
            <span class="arrow">→</span>
          </a>"""
            )
        sections.append(
            f'<div class="section-title">{escape(label)}</div>'
            f'<div class="quick-links">{"".join(links)}</div>'
        )
    if not sections:
        return _report_page_links_html(url, settings=settings, reporting_override=reporting_override)
    return "".join(sections)


def _pillar_hub_links(page: dict[str, Any], url: Callable[[str], str], *, settings: DnaSettings) -> str:
    from meshflow.dna.web.portal.reporting_layout import list_reporting_pages

    pillar = str(page.get("pillar") or "")
    related = [
        item
        for item in list_reporting_pages(settings)
        if str(item.get("pillar") or "") == pillar
        and item.get("path") not in {"/portal", page.get("path")}
        and (item.get("tables") or item.get("charts") or item.get("sections"))
    ]
    if not related:
        return empty_state(
            "Reports coming soon",
            "Additional pages for this pillar will appear here as they are configured.",
        )
    links = []
    for item in related:
        links.append(
            f"""
          <a class="quick-link" href="{escape(url(item['path']))}">
            <div><strong>{escape(item['title'])}</strong><br><span>{escape(item.get('description') or '')}</span></div>
            <span class="arrow">→</span>
          </a>"""
        )
    return f'<div class="quick-links">{"".join(links)}</div>'


def _portal_side_nav(
    active_path: str,
    data_menu: tuple[Any, ...],
    catalog_menu: tuple[Any, ...] | None = None,
) -> tuple[str | None, tuple[Any, ...] | None, str | None]:
    if active_path.startswith("/portal/governance") or active_path == "/portal/semantics":
        return "Governance", GOVERNANCE_SECTION_NAV, "governance"
    if active_path.startswith("/portal/catalog"):
        return "Catalog", catalog_menu or (("/portal/catalog", "No tables yet"),), "catalog"
    if active_path.startswith("/portal"):
        return "Reporting", data_menu, "reporting"
    return None, None, None


def _html_response(
    request: Request,
    *,
    client: ClientPortalConfig,
    title: str,
    active_path: str,
    body: str,
    page_title: str | None = None,
    use_charts: bool = False,
    is_admin: bool = False,
    settings: DnaSettings | None = None,
    reporting_override: dict[str, Any] | None = None,
    preview_meta: dict[str, Any] | None = None,
) -> Response:
    url = lambda path: f"{request.script_root}{path if path.startswith('/') else f'/{path}'}"
    charts_assets = charts_page_assets(url) if use_charts else ""
    data_menu = (
        reporting_data_menu(settings, override=reporting_override)
        if settings is not None
        else PORTAL_DATA_MENU
    )
    if not data_menu:
        data_menu = PORTAL_DATA_MENU
    catalog_menu = catalog_section_nav(settings)
    if preview_meta:
        body = (
            _preview_banner_html(
                url,
                next_version=str(preview_meta.get("next_version") or ""),
                proposal_id=str(preview_meta.get("proposal_id") or ""),
            )
            + body
        )
    sidebar_active_path = active_path
    nav_active_path = _portal_nav_active_path(active_path)
    side_nav_title, side_nav_items, side_nav_id = _portal_side_nav(
        active_path, data_menu, catalog_menu
    )
    return Response(
        render_portal_page(
            title=title,
            active_path=nav_active_path,
            sidebar_active_path=sidebar_active_path,
            body=body,
            page_title=page_title,
            client=client,
            nav_links=_portal_nav_links(is_admin=is_admin),
            data_menu=data_menu,
            side_nav_title=side_nav_title,
            side_nav_items=side_nav_items,
            side_nav_id=side_nav_id,
            url=url,
            charts_assets=charts_assets,
        ),
        mimetype="text/html",
    )


def render_overview(
    request: Request,
    *,
    settings: DnaSettings,
    client: ClientPortalConfig,
    is_admin: bool = False,
    page: dict[str, Any] | None = None,
    reporting_override: dict[str, Any] | None = None,
    preview_meta: dict[str, Any] | None = None,
) -> Response:
    page = page or {}
    workflow = load_workflow_state(settings, settings.dna_config_id)
    manifest = read_json_artifact(settings, f"{settings.gold_dna_prefix}/manifest.json") or {}
    url: Callable[[str], str] = lambda path: f"{request.script_root}{path if path.startswith('/') else f'/{path}'}"
    active_path = str(page.get("path") or "/portal")
    title = str(page.get("title") or "Reporting")

    badges: list[tuple[str, bool]] = []
    active = workflow.get("active_version")
    if active:
        badges.append((f"v{active} production", True))
    if manifest.get("published_at"):
        badges.append((f"Updated {_format_published_date(manifest.get('published_at'))}", True))

    body = page_header(client.welcome_title, client.welcome_message, eyebrow=TAGLINE)
    if badges:
        body += badge_row(*badges)
    if page_has_content(page):
        sections_html, _use_charts = render_page_body(page, settings=settings)
        body += sections_html
    body += f"""
    <section class="section">
      <div class="section-title">Reports by pillar</div>
      <div class="card">
        {_pillar_grouped_links_html(url, settings=settings, reporting_override=reporting_override)}
      </div>
    </section>
    """
    return _html_response(
        request,
        client=client,
        title=title,
        active_path=active_path,
        body=body,
        is_admin=is_admin,
        settings=settings,
        reporting_override=reporting_override,
        preview_meta=preview_meta,
    )


def render_generic_page(
    request: Request,
    *,
    settings: DnaSettings,
    client: ClientPortalConfig,
    is_admin: bool = False,
    page: dict[str, Any] | None = None,
    reporting_override: dict[str, Any] | None = None,
    preview_meta: dict[str, Any] | None = None,
) -> Response:
    page = page or {}
    title = str(page.get("title") or "Report")
    description = str(page.get("description") or "Configured in the company reporting pack.")
    active_path = str(page.get("path") or "/portal")
    body = page_header(title, description, eyebrow=page_eyebrow(page))
    page_html, use_charts = render_page_body(page, settings=settings)
    body += page_html
    return _html_response(
        request,
        client=client,
        title=title,
        active_path=active_path,
        body=body,
        use_charts=use_charts,
        is_admin=is_admin,
        settings=settings,
        reporting_override=reporting_override,
        preview_meta=preview_meta,
    )


def render_pillar_hub(
    request: Request,
    *,
    settings: DnaSettings,
    client: ClientPortalConfig,
    is_admin: bool = False,
    page: dict[str, Any] | None = None,
    reporting_override: dict[str, Any] | None = None,
    preview_meta: dict[str, Any] | None = None,
) -> Response:
    page = page or {}
    title = str(page.get("title") or "Reports")
    description = str(page.get("description") or "Configured reports for this business pillar.")
    active_path = str(page.get("path") or "/portal")
    pillar = str(page.get("pillar") or "sales").title()
    url: Callable[[str], str] = lambda path: f"{request.script_root}{path if path.startswith('/') else f'/{path}'}"
    body = page_header(title, description, eyebrow=pillar)
    body += f'<section class="section"><div class="card">{_pillar_hub_links(page, url, settings=settings)}</div></section>'
    return _html_response(
        request,
        client=client,
        title=title,
        active_path=active_path,
        body=body,
        is_admin=is_admin,
        settings=settings,
        reporting_override=reporting_override,
        preview_meta=preview_meta,
    )


def render_chart_demo(
    request: Request,
    *,
    settings: DnaSettings,
    client: ClientPortalConfig,
    is_admin: bool = False,
    page: dict[str, Any] | None = None,
    reporting_override: dict[str, Any] | None = None,
    preview_meta: dict[str, Any] | None = None,
) -> Response:
    title = str((page or {}).get("title") or "Chart catalog")
    description = str(
        (page or {}).get("description")
        or f"Interactive gallery of reporting chart types sourced from certified gold outputs ({REVENUE_OUTPUT_ID}, out_dim_items)."
    )
    active_path = str((page or {}).get("path") or "/portal/chart-demo")
    body = page_header(title, description, eyebrow="ECharts")
    body += badge_row((f"{len(CHART_TYPE_CATALOG)} chart types", True), ("Gold-backed demo", False))
    body += f"""
    <section class="section">
      <div class="section-title">Catalog</div>
      {chart_demo_section_html(settings)}
    </section>
    """
    return _html_response(
        request,
        client=client,
        title=title,
        active_path=active_path,
        body=body,
        use_charts=chart_demo_has_charts(settings),
        is_admin=is_admin,
        settings=settings,
        reporting_override=reporting_override,
        preview_meta=preview_meta,
    )


def render_catalog(
    request: Request,
    *,
    settings: DnaSettings,
    client: ClientPortalConfig,
    is_admin: bool = False,
) -> Response:
    """Catalog landing — open the first gold table, or an empty state."""
    from meshflow.dna.web.portal.catalog import CATALOG_ROOT, list_catalog_tables

    tables = list_catalog_tables(settings)
    if tables:
        target = f"{CATALOG_ROOT}/{tables[0].id}"
        return Response(
            status=302,
            headers={
                "Location": f"{request.script_root}{target}",
            },
        )
    body = page_header(
        "Catalog",
        "Certified gold tables appear here after DNA publish completes.",
        eyebrow="Gold layer",
    )
    body += empty_state(
        "No gold tables yet",
        "Publish a DNA pack with table outputs to browse them here.",
    )
    return _html_response(
        request,
        client=client,
        title="Catalog",
        active_path=CATALOG_ROOT,
        body=body,
        is_admin=is_admin,
        settings=settings,
    )


def render_catalog_table(
    request: Request,
    *,
    settings: DnaSettings,
    client: ClientPortalConfig,
    output_id: str,
    is_admin: bool = False,
) -> Response:
    """Preview a single gold table (all columns, limited rows)."""
    from meshflow.dna.web.portal.catalog import (
        CATALOG_PREVIEW_LIMIT,
        CATALOG_ROOT,
        catalog_table_config,
        catalog_table_label,
        find_catalog_table,
    )

    output = find_catalog_table(settings, output_id)
    if output is None:
        return Response("Not found", status=404, mimetype="text/plain")

    title = catalog_table_label(output)
    active_path = f"{CATALOG_ROOT}/{output.id}"
    body = page_header(
        title,
        f"Gold preview · first {CATALOG_PREVIEW_LIMIT} rows · all columns",
        eyebrow="Catalog",
    )
    body += f"""
    <section class="section">
      {generic_table_html(
          settings,
          catalog_table_config(output),
          empty_title="No rows yet",
          empty_detail="This gold table has not been published yet.",
      )}
    </section>
    """
    return _html_response(
        request,
        client=client,
        title=title,
        active_path=active_path,
        body=body,
        is_admin=is_admin,
        settings=settings,
    )


def render_configured_page(
    request: Request,
    *,
    settings: DnaSettings,
    client: ClientPortalConfig,
    page: dict[str, Any],
    is_admin: bool = False,
    reporting_override: dict[str, Any] | None = None,
    preview_meta: dict[str, Any] | None = None,
) -> Response:
    """Dispatch a reporting-config page to the matching renderer."""
    page_id = str(page.get("id") or "")
    path = str(page.get("path") or "")
    common = dict(
        settings=settings,
        client=client,
        is_admin=is_admin,
        page=page,
        reporting_override=reporting_override,
        preview_meta=preview_meta,
    )

    if page_id == "page_summary" or path in {"/portal", "/portal/"}:
        return render_overview(request, **common)
    if is_chart_catalog_page(page):
        return render_chart_demo(request, **common)
    if page_id in {"page_sales", "page_operations", "page_finance", "page_inventory"} and not page_has_content(
        page
    ):
        return render_pillar_hub(request, **common)
    if page_has_content(page):
        return render_generic_page(request, **common)
    # Unknown page shape — still show title/description from config.
    title = str(page.get("title") or "Report")
    description = str(page.get("description") or "Configured in the company reporting pack.")
    body = page_header(title, description, eyebrow="Report")
    body += empty_state(
        "No charts or tables configured",
        "Add charts or tables with source_output bindings in the reporting config.",
    )
    return _html_response(
        request,
        client=client,
        title=title,
        active_path=path or "/portal",
        body=body,
        is_admin=is_admin,
        settings=settings,
        reporting_override=reporting_override,
        preview_meta=preview_meta,
    )


def _pack_to_yaml(payload: dict[str, Any]) -> str:
    import yaml

    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


def is_config_assistant_action(action: str) -> bool:
    return action in CONFIG_ASSISTANT_ACTIONS


def is_manual_governance_action(action: str) -> bool:
    return action in MANUAL_GOVERNANCE_ACTIONS


def _governance_update_tab_script() -> str:
    return """<script>
(function () {
  var section = document.getElementById("governance-update");
  if (!section) return;
  var tabs = section.querySelectorAll("[data-governance-tab]");
  var panels = section.querySelectorAll("[data-governance-panel]");
  function activate(name) {
    tabs.forEach(function (tab) {
      var active = tab.getAttribute("data-governance-tab") === name;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    panels.forEach(function (panel) {
      panel.hidden = panel.getAttribute("data-governance-panel") !== name;
    });
  }
  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      activate(tab.getAttribute("data-governance-tab"));
    });
  });
  var initial = section.getAttribute("data-initial-tab") || "assist";
  var params = new URLSearchParams(window.location.search);
  if (params.get("update") === "manual") initial = "manual";
  else if (params.get("update") === "assist") initial = "assist";
  activate(initial);
  // After Config Assist / Manual Edit form POSTs, stay on this section.
  if (
    window.location.hash === "#governance-update"
    || params.has("msg")
    || params.has("err")
  ) {
    section.scrollIntoView({ block: "start" });
  }
})();
</script>"""


def _version_bump_field_html(
    *,
    input_id: str,
    input_name: str,
    label: str,
    value: str,
    base_version: str,
    next_patch: str,
    next_minor: str,
    next_major: str,
    field_class: str = "form-field",
) -> str:
    """Read-only next-patch version input with minor/major bump buttons."""
    return f"""
            <div class="{escape(field_class)}" data-version-bump
              data-base-version="{escape(base_version)}"
              data-next-patch="{escape(next_patch)}"
              data-next-minor="{escape(next_minor)}"
              data-next-major="{escape(next_major)}">
              <label for="{escape(input_id)}">{escape(label)}</label>
              <div class="version-bump-row">
                <input id="{escape(input_id)}" name="{escape(input_name)}"
                  value="{escape(value)}" required readonly
                  pattern="\\d+\\.\\d+\\.\\d+" title="Semver major.minor.patch"
                  data-version-input />
                <div class="version-bump-buttons">
                  <button type="button" class="btn version-bump-btn" data-bump="minor"
                    title="Bump to v{escape(next_minor)}">Minor</button>
                  <button type="button" class="btn version-bump-btn" data-bump="major"
                    title="Bump to v{escape(next_major)}">Major</button>
                </div>
              </div>
              <p class="form-hint">
                Defaults to the next patch (<code>v{escape(next_patch)}</code>).
                Use Minor (<code>v{escape(next_minor)}</code>) or Major
                (<code>v{escape(next_major)}</code>) to bump; patch/minor reset accordingly.
              </p>
              <p class="form-warning" data-version-warning hidden></p>
            </div>
    """


def _version_bump_script() -> str:
    return """
<script>
(function () {
  function classify(root, proposed) {
    var base = (root.getAttribute("data-base-version") || "").trim();
    var nextPatch = (root.getAttribute("data-next-patch") || "").trim();
    var nextMinor = (root.getAttribute("data-next-minor") || "").trim();
    var nextMajor = (root.getAttribute("data-next-major") || "").trim();
    proposed = (proposed || "").trim();
    if (!proposed) return { kind: "invalid", text: "" };
    if (proposed === nextPatch) return { kind: "patch", text: "" };
    if (proposed === nextMinor) {
      var minorLine = proposed.split(".").slice(0, 2).join(".");
      return {
        kind: "minor",
        text: "Minor bump from v" + base + " to v" + proposed +
          ": patch resets to 0, and all further versions will continue from v" +
          minorLine + ".x."
      };
    }
    if (proposed === nextMajor) {
      var majorLine = proposed.split(".")[0];
      return {
        kind: "major",
        text: "Major bump from v" + base + " to v" + proposed +
          ": minor and patch reset to 0, and all further versions will continue from v" +
          majorLine + ".x.x."
      };
    }
    return {
      kind: "invalid",
      text: "Use the next patch (" + nextPatch + "), next minor (" + nextMinor +
        "), or next major (" + nextMajor + ")."
    };
  }

  function refresh(root) {
    var input = root.querySelector("[data-version-input]");
    var warning = root.querySelector("[data-version-warning]");
    if (!input || !warning) return;
    var result = classify(root, input.value);
    warning.hidden = !result.text;
    warning.textContent = result.text;
    warning.classList.toggle("form-warning", result.kind === "minor" || result.kind === "major");
    warning.classList.toggle("form-error", result.kind === "invalid");
    root.querySelectorAll("[data-bump]").forEach(function (btn) {
      btn.classList.toggle("is-active", btn.getAttribute("data-bump") === result.kind);
    });
  }

  function bind(root) {
    if (root.getAttribute("data-version-bump-bound") === "1") return;
    root.setAttribute("data-version-bump-bound", "1");
    var input = root.querySelector("[data-version-input]");
    if (!input) return;
    var nextPatch = (root.getAttribute("data-next-patch") || "").trim();
    var nextMinor = (root.getAttribute("data-next-minor") || "").trim();
    var nextMajor = (root.getAttribute("data-next-major") || "").trim();
    root.querySelectorAll("[data-bump]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var kind = btn.getAttribute("data-bump");
        var target = kind === "minor" ? nextMinor : nextMajor;
        if ((input.value || "").trim() === target) {
          input.value = nextPatch;
        } else {
          input.value = target;
        }
        refresh(root);
      });
    });
    var form = root.closest("form");
    if (form && form.getAttribute("data-version-bump-submit") !== "1") {
      form.setAttribute("data-version-bump-submit", "1");
      form.addEventListener("submit", function (event) {
        var submitter = event.submitter;
        var action = submitter ? (submitter.getAttribute("value") || "") : "";
        if (action.indexOf("deny") === 0) return;
        var fields = form.querySelectorAll("[data-version-bump]");
        for (var i = 0; i < fields.length; i++) {
          var field = fields[i];
          var fieldInput = field.querySelector("[data-version-input]");
          if (!fieldInput) continue;
          var result = classify(field, fieldInput.value);
          if (result.kind === "invalid") {
            event.preventDefault();
            refresh(field);
            fieldInput.focus();
            return;
          }
          if ((result.kind === "minor" || result.kind === "major") &&
              !window.confirm(result.text + "\\n\\nContinue with this version?")) {
            event.preventDefault();
            return;
          }
        }
      });
    }
    refresh(root);
  }

  function bindAll(scope) {
    (scope || document).querySelectorAll("[data-version-bump]").forEach(bind);
  }

  bindAll(document);
  document.addEventListener("meshflow:assistant-live-updated", function (event) {
    bindAll((event && event.target) || document);
  });
})();
</script>
"""


def _governance_manual_edit_panel_html(
    *,
    request_url: str,
    dna_yaml: str,
    reporting_yaml: str,
    dna_version: str,
    dna_base_version: str,
    dna_next_patch: str,
    dna_next_minor: str,
    dna_next_major: str,
    reporting_version: str,
    reporting_base_version: str,
    reporting_next_patch: str,
    reporting_next_minor: str,
    reporting_next_major: str,
    hidden: bool = False,
) -> str:
    hidden_attr = " hidden" if hidden else ""
    return f"""
        <div class="governance-update-panel" data-governance-panel="manual"{hidden_attr}>
          <p class="pack-card-lead">Edit DNA and reporting YAML directly. Approve each pack independently; each gets its own version under <code>governance/</code>.</p>
          <div class="governance-manual-packs">
            <div class="assistant-pack-block">
              <div class="section-title">DNA</div>
              <form method="post" action="{escape(request_url)}" class="governance-edit-form">
                {_version_bump_field_html(
                    input_id="dna_version",
                    input_name="dna_version",
                    label="DNA version",
                    value=dna_version,
                    base_version=dna_base_version,
                    next_patch=dna_next_patch,
                    next_minor=dna_next_minor,
                    next_major=dna_next_major,
                    field_class="form-field version-bump-field",
                )}
                <div class="form-field">
                  <label for="dna_yaml">DNA pack (YAML)</label>
                  <textarea id="dna_yaml" name="dna_yaml" rows="18" class="yaml-editor">{escape(dna_yaml)}</textarea>
                </div>
                <div class="governance-edit-form-actions">
                  <button type="submit" name="action" value="manual_draft_dna" class="btn">Save draft</button>
                  <button type="submit" name="action" value="manual_approve_dna" class="btn btn-primary">Approve DNA</button>
                </div>
              </form>
            </div>
            <div class="assistant-pack-block">
              <div class="section-title">Reporting</div>
              <form method="post" action="{escape(request_url)}" class="governance-edit-form">
                {_version_bump_field_html(
                    input_id="reporting_version",
                    input_name="reporting_version",
                    label="Reporting version",
                    value=reporting_version,
                    base_version=reporting_base_version,
                    next_patch=reporting_next_patch,
                    next_minor=reporting_next_minor,
                    next_major=reporting_next_major,
                    field_class="form-field version-bump-field",
                )}
                <div class="form-field">
                  <label for="reporting_yaml">Reporting pack (YAML)</label>
                  <textarea id="reporting_yaml" name="reporting_yaml" rows="14" class="yaml-editor">{escape(reporting_yaml)}</textarea>
                </div>
                <div class="governance-edit-form-actions">
                  <button type="submit" name="action" value="manual_draft_reporting" class="btn">Save draft</button>
                  <button type="submit" name="action" value="manual_approve_reporting" class="btn btn-primary">Approve reporting</button>
                </div>
              </form>
            </div>
          </div>
        </div>
    """


def _config_assistant_messages_html(
    proposal_view_data: dict[str, Any] | None,
    *,
    running: bool,
) -> str:
    messages: list[dict[str, Any]] = []
    if proposal_view_data:
        conversation = proposal_view_data.get("conversation") or {}
        raw_messages = conversation.get("messages") or []
        if isinstance(raw_messages, list):
            messages = [m for m in raw_messages if isinstance(m, dict)]

    if not messages:
        return '<p class="pack-card-lead">Describe the reporting or DNA config change you want.</p>'

    html = ""
    for entry in messages:
        role = str(entry.get("role") or "")
        content = str(entry.get("content") or "")
        bubble_class = "assistant-bubble user" if role == "user" else "assistant-bubble"
        label = "You" if role == "user" else "Assistant"
        html += (
            f'<div class="{bubble_class}">'
            f'<div class="assistant-bubble-label">{escape(label)}</div>'
            f'<div class="assistant-bubble-text">{escape(content)}</div>'
            f"</div>"
        )
    if running:
        html += (
            '<div class="assistant-bubble thinking" aria-live="polite">'
            '<div class="assistant-bubble-label">Assistant</div>'
            '<div class="assistant-bubble-text">'
            'Thinking<span class="assistant-thinking-dots" aria-hidden="true">'
            "<span>.</span><span>.</span><span>.</span>"
            "</span></div></div>"
        )
    return html


def _config_assistant_live_body_html(
    url: Callable[[str], str],
    *,
    governance_path: str,
    proposal_view_data: dict[str, Any] | None,
    usage_at_limit: bool = False,
) -> str:
    """Inner Config Assist markup that can be polled and replaced in place."""
    running = bool(
        proposal_view_data and proposal_view_data.get("meta", {}).get("status") == "running"
    )
    meta = (proposal_view_data or {}).get("meta") or {}
    form_action = escape(url(governance_path))

    html = ""
    if running:
        html += (
            '<div class="form-success">Assistant is working on your request…</div>'
        )

    html += '<div class="assistant-chat-shell"><div class="assistant-chat">'
    html += _config_assistant_messages_html(proposal_view_data, running=running)
    html += "</div>"

    if running:
        proposal_id = escape(str(proposal_view_data.get("proposal_id") or ""))
        html += '<p class="pack-card-lead">Send is disabled while the assistant is working.</p>'
        html += f"""
          <form method="post" action="{form_action}" class="assistant-cancel-form">
            <input type="hidden" name="action" value="cancel_running" />
            <input type="hidden" name="proposal_id" value="{proposal_id}" />
            <button type="submit" class="btn">Cancel and unlock</button>
          </form>
        """
    else:
        if usage_at_limit:
            html += (
                '<p class="pack-card-lead governance-usage-limit">'
                "Monthly Config Assist allowance reached. "
                "Manual edits are still available on the Manual Edit tab.</p>"
            )
        else:
            html += f"""
          <form method="post" action="{form_action}" class="assistant-compose">
            <input type="hidden" name="action" value="chat" />
            <div class="form-field assistant-compose-field">
              <label for="message">Message</label>
              <textarea id="message" name="message" rows="2" required
                class="assistant-compose-input"
                placeholder="e.g. Rename Order-to-cash detail to Invoice lines and hide the chart catalog"></textarea>
            </div>
            <button type="submit" class="btn btn-primary portal-submit-btn">Send</button>
          </form>
        """
    html += "</div>"

    if proposal_view_data and proposal_view_data.get("meta", {}).get("status") == "open":
        from meshflow.dna.web.portal.config_assistant.proposals import (
            bump_major_version,
            bump_minor_version,
            bump_patch_version,
        )

        proposal_id = escape(str(proposal_view_data.get("proposal_id") or ""))
        summary = escape(str(meta.get("summary") or ""))
        base_dna_yaml = str(proposal_view_data.get("base_dna_yaml") or "")
        base_reporting_yaml = str(proposal_view_data.get("base_reporting_yaml") or "")
        proposed_dna_yaml = str(proposal_view_data.get("dna_yaml") or "")
        proposed_reporting_yaml = str(proposal_view_data.get("reporting_yaml") or "")
        dna_pending = bool(proposal_view_data.get("dna_pending"))
        reporting_pending = bool(proposal_view_data.get("reporting_pending"))
        dna_status = escape(str(meta.get("dna_status") or "skipped"))
        reporting_status = escape(str(meta.get("reporting_status") or "skipped"))
        dna_base = str(meta.get("dna_base_version") or "")
        reporting_base = str(meta.get("reporting_base_version") or "")
        dna_next_patch = bump_patch_version(dna_base)
        dna_next_minor = bump_minor_version(dna_base)
        dna_next_major = bump_major_version(dna_base)
        reporting_next_patch = bump_patch_version(reporting_base)
        reporting_next_minor = bump_minor_version(reporting_base)
        reporting_next_major = bump_major_version(reporting_base)

        html += f"""
          <div class="card pack-card governance-proposal-card">
            <div class="section-title">Open proposal</div>
            <p class="pack-card-lead">{summary or "Open proposal ready for review."}</p>
            <form method="post" action="{form_action}" class="assistant-actions">
              <input type="hidden" name="proposal_id" value="{proposal_id}" />
              <button type="submit" name="action" value="preview" class="btn">Preview portal</button>
              <button type="submit" name="action" value="deny" class="btn">Deny all</button>
            </form>
            <div class="assistant-pack-block">
              <div class="section-title">DNA <span class="assistant-status-pill">{dna_status}</span></div>
              {render_assistant_diff_html(base_dna_yaml, proposed_dna_yaml, empty_label="(no DNA changes)")}
        """
        if dna_pending:
            html += f"""
              <form method="post" action="{form_action}" class="assistant-approve-form">
                <input type="hidden" name="proposal_id" value="{proposal_id}" />
                {_version_bump_field_html(
                    input_id="next_dna_version",
                    input_name="next_dna_version",
                    label="DNA version to pin",
                    value=dna_next_patch,
                    base_version=dna_base,
                    next_patch=dna_next_patch,
                    next_minor=dna_next_minor,
                    next_major=dna_next_major,
                    field_class="form-field version-bump-field",
                )}
                <div class="assistant-approve-actions">
                  <button type="submit" name="action" value="approve_dna" class="btn btn-primary">Approve DNA</button>
                  <button type="submit" name="action" value="deny_dna" class="btn" formnovalidate>Deny DNA</button>
                </div>
              </form>
            """
        html += f"""
            </div>
            <div class="assistant-pack-block">
              <div class="section-title">Reporting <span class="assistant-status-pill">{reporting_status}</span></div>
              {render_assistant_diff_html(base_reporting_yaml, proposed_reporting_yaml, empty_label="(no reporting changes)")}
        """
        if reporting_pending:
            html += f"""
              <form method="post" action="{form_action}" class="assistant-approve-form">
                <input type="hidden" name="proposal_id" value="{proposal_id}" />
                {_version_bump_field_html(
                    input_id="next_reporting_version",
                    input_name="next_reporting_version",
                    label="Reporting version to pin",
                    value=reporting_next_patch,
                    base_version=reporting_base,
                    next_patch=reporting_next_patch,
                    next_minor=reporting_next_minor,
                    next_major=reporting_next_major,
                    field_class="form-field version-bump-field",
                )}
                <div class="assistant-approve-actions">
                  <button type="submit" name="action" value="approve_reporting" class="btn btn-primary">Approve reporting</button>
                  <button type="submit" name="action" value="deny_reporting" class="btn" formnovalidate>Deny reporting</button>
                </div>
              </form>
            """
        html += "</div></div>"

    return html


def config_assistant_poll_payload(
    url: Callable[[str], str],
    *,
    governance_path: str,
    proposal_view_data: dict[str, Any] | None,
    usage_at_limit: bool = False,
) -> dict[str, Any]:
    """JSON body for Config Assist live polling."""
    running = bool(
        proposal_view_data and proposal_view_data.get("meta", {}).get("status") == "running"
    )
    status = ""
    if proposal_view_data:
        status = str((proposal_view_data.get("meta") or {}).get("status") or "")
    return {
        "running": running,
        "status": status,
        "html": _config_assistant_live_body_html(
            url,
            governance_path=governance_path,
            proposal_view_data=proposal_view_data,
            usage_at_limit=usage_at_limit,
        ),
    }


def _config_assistant_panel_html(
    url: Callable[[str], str],
    *,
    governance_path: str,
    proposal_view_data: dict[str, Any] | None,
    base_version: str,
    hidden: bool = True,
    usage_at_limit: bool = False,
) -> str:
    running = bool(
        proposal_view_data and proposal_view_data.get("meta", {}).get("status") == "running"
    )
    poll_url = escape(url("/api/config-assistant"))
    hidden_attr = " hidden" if hidden else ""
    live_body = _config_assistant_live_body_html(
        url,
        governance_path=governance_path,
        proposal_view_data=proposal_view_data,
        usage_at_limit=usage_at_limit,
    )
    return f"""
        <div class="governance-update-panel" data-governance-panel="assist"{hidden_attr}>
          <div id="config-assist-live"
            data-poll-url="{poll_url}"
            data-running="{"1" if running else "0"}">
            {live_body}
          </div>
          <script>
          (function () {{
            var panel = document.querySelector('[data-governance-panel="assist"]');
            if (!panel) return;
            var live = document.getElementById("config-assist-live");
            if (!live) return;
            var pollUrl = live.getAttribute("data-poll-url") || "";
            var timer = null;
            var inFlight = false;

            function bindCompose() {{
              var form = panel.querySelector("form.assistant-compose");
              var box = document.getElementById("message");
              if (!form || !box || box.dataset.enterBound === "1") return;
              box.dataset.enterBound = "1";
              box.addEventListener("keydown", function (event) {{
                if (event.key === "Enter" && !event.shiftKey) {{
                  event.preventDefault();
                  if (typeof form.requestSubmit === "function") form.requestSubmit();
                  else form.submit();
                }}
              }});
            }}

            function scrollChat() {{
              var chat = live.querySelector(".assistant-chat");
              if (chat) chat.scrollTop = chat.scrollHeight;
            }}

            function schedule() {{
              if (timer) clearTimeout(timer);
              if (live.getAttribute("data-running") !== "1" || !pollUrl) return;
              timer = setTimeout(poll, 2500);
            }}

            function poll() {{
              if (inFlight || live.getAttribute("data-running") !== "1") return;
              inFlight = true;
              fetch(pollUrl, {{
                credentials: "same-origin",
                headers: {{ "Accept": "application/json" }}
              }})
                .then(function (response) {{
                  if (!response.ok) throw new Error("poll failed");
                  return response.json();
                }})
                .then(function (data) {{
                  if (!data || typeof data.html !== "string") return;
                  live.innerHTML = data.html;
                  live.setAttribute("data-running", data.running ? "1" : "0");
                  bindCompose();
                  scrollChat();
                  live.dispatchEvent(new CustomEvent("meshflow:assistant-live-updated", {{ bubbles: true }}));
                  if (data.running) schedule();
                }})
                .catch(function () {{ schedule(); }})
                .finally(function () {{ inFlight = false; }});
            }}

            bindCompose();
            scrollChat();
            schedule();
          }})();
          </script>
        </div>
    """


def _bedrock_usage_meter_html(usage: dict[str, Any]) -> str:
    percent = float(usage.get("usage_percent") or 0.0)
    percent = max(0.0, min(100.0, percent))
    cost = float(usage.get("estimated_cost_usd") or 0.0)
    budget = float(usage.get("monthly_budget_usd") or 0.0)
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    month = escape(str(usage.get("month") or ""))
    at_limit = bool(usage.get("at_limit"))
    bar_class = "governance-usage-fill"
    if percent >= 90:
        bar_class += " critical"
    elif percent >= 75:
        bar_class += " warn"
    limit_note = (
        '<p class="governance-usage-limit">Monthly Config Assist allowance reached. '
        "New assistant messages are disabled until next month.</p>"
        if at_limit
        else ""
    )
    return f"""
      <div class="governance-usage-meter" aria-label="Config Assist monthly usage">
        <div class="governance-usage-head">
          <span class="governance-usage-label">Config Assist usage ({month})</span>
          <span class="governance-usage-value">{percent:.0f}%</span>
        </div>
        <div class="governance-usage-track" role="progressbar"
          aria-valuemin="0" aria-valuemax="100" aria-valuenow="{percent:.0f}"
          aria-label="Config Assist monthly usage">
          <div class="{bar_class}" style="width:{percent:.1f}%"></div>
        </div>
        <p class="governance-usage-meta">
          ${cost:.2f} of ${budget:.2f} estimated ·
          {input_tokens:,} input / {output_tokens:,} output tokens
        </p>
        {limit_note}
      </div>
    """


def _governance_update_section_html(
    url: Callable[[str], str],
    *,
    request_url: str,
    dna_yaml: str,
    reporting_yaml: str,
    dna_version: str,
    dna_base_version: str,
    dna_next_patch: str,
    dna_next_minor: str,
    dna_next_major: str,
    reporting_version: str,
    reporting_base_version: str,
    reporting_next_patch: str,
    reporting_next_minor: str,
    reporting_next_major: str,
    proposal_view_data: dict[str, Any] | None,
    base_version: str,
    pinned_dna_version: str,
    pinned_reporting_version: str,
    update_tab: str,
    governance_path: str = "/portal/governance",
    usage_summary: dict[str, Any] | None = None,
) -> str:
    manual_active = update_tab != "assist"
    assist_active = update_tab == "assist"
    dna_pin = escape(pinned_dna_version or "—")
    reporting_pin = escape(pinned_reporting_version or "—")
    usage_html = _bedrock_usage_meter_html(usage_summary or {})
    return f"""
    <section class="section" id="governance-update" data-initial-tab="{escape(update_tab)}">
      <div class="section-title">Update governance packs</div>
      <div class="card pack-card governance-update-card">
        {usage_html}
        <div class="governance-update-header">
          <div class="governance-update-tabs" role="tablist" aria-label="Update method">
            <button type="button" class="governance-update-tab{" active" if assist_active else ""}"
              role="tab" data-governance-tab="assist" aria-selected="{"true" if assist_active else "false"}">
              Config Assist
            </button>
            <button type="button" class="governance-update-tab{" active" if manual_active else ""}"
              role="tab" data-governance-tab="manual" aria-selected="{"true" if manual_active else "false"}">
              Manual Edit
            </button>
          </div>
          <p class="governance-update-pins">
            DNA <code>v{dna_pin}</code> · reporting <code>v{reporting_pin}</code>
          </p>
        </div>
        {_governance_manual_edit_panel_html(
            request_url=request_url,
            dna_yaml=dna_yaml,
            reporting_yaml=reporting_yaml,
            dna_version=dna_version,
            dna_base_version=dna_base_version,
            dna_next_patch=dna_next_patch,
            dna_next_minor=dna_next_minor,
            dna_next_major=dna_next_major,
            reporting_version=reporting_version,
            reporting_base_version=reporting_base_version,
            reporting_next_patch=reporting_next_patch,
            reporting_next_minor=reporting_next_minor,
            reporting_next_major=reporting_next_major,
            hidden=assist_active,
        )}
        {_config_assistant_panel_html(
            url,
            governance_path=governance_path,
            proposal_view_data=proposal_view_data,
            base_version=base_version,
            hidden=not assist_active,
            usage_at_limit=bool((usage_summary or {}).get("at_limit")),
        )}
      </div>
    </section>
    {_governance_update_tab_script()}
    {_version_bump_script()}
    {_assistant_diff_nav_script()}
    """


def _governance_update_restricted_html() -> str:
    return """
    <section class="section" id="governance-update">
      <div class="section-title">Update governance packs</div>
      <div class="card pack-card governance-update-card">
        <p class="governance-update-restricted-note">
          Admin access is required to view and edit DNA and reporting config files.
          Contact your portal administrator if you need changes.
        </p>
      </div>
    </section>
    """


def _append_portal_governance_history(
    state: dict[str, Any],
    *,
    version: str,
    status: str,
    approver: str,
    target: str,
    notes: str,
) -> None:
    history = state.get("history", [])
    if not isinstance(history, list):
        history = []
    history.append(
        {
            "version": version,
            "status": status,
            "approver": approver or "Portal admin",
            "at": datetime.now(UTC).isoformat(),
            "notes": notes,
            "target": target,
        }
    )
    state["history"] = history


def save_governance_dna_from_portal(
    settings: DnaSettings,
    *,
    dna_yaml: str,
    dna_version: str,
    pin_production: bool,
    approver: str,
) -> dict[str, Any]:
    """Parse portal DNA YAML and persist a governance version."""
    from meshflow.dna.governance import save_governance_version
    from meshflow.dna.schema import load_definition_pack_yaml
    from meshflow.dna.web.portal.config_assistant.proposals import (
        bump_major_version,
        bump_minor_version,
        bump_patch_version,
        classify_manual_version_bump,
    )
    from meshflow.dna.workflow import load_workflow_state, save_workflow_state

    dna_version = dna_version.strip()
    if not dna_version:
        raise ValueError("DNA version is required")

    state = load_workflow_state(settings, settings.dna_config_id)
    pack = load_definition_pack_yaml(dna_yaml)
    pack.pack_id = settings.dna_config_id
    dna_base = str(state.get("active_version") or pack.version or "")

    dna_bump = classify_manual_version_bump(dna_base, dna_version)
    if dna_bump["kind"] == "invalid":
        raise ValueError(f"DNA: {dna_bump['error']}")

    pack.version = dna_version
    if pin_production:
        pack.status = "production"
        pack.approval.status = "production"
        pack.approval.approver = approver or pack.approval.approver or "Portal admin"
        pack.approval.approved_at = datetime.now(UTC).date().isoformat()
    else:
        pack.status = "draft"
        pack.approval.status = "draft"

    notes = "Updated DNA via client portal manual edit"
    if dna_bump["kind"] in {"minor", "major"} and dna_bump.get("warning"):
        notes = f"{notes}. {dna_bump['warning']}"

    saved = save_governance_version(settings, pack=pack, reporting=None)
    state["pack_id"] = settings.dna_config_id
    _append_portal_governance_history(
        state,
        version=dna_version,
        status=pack.approval.status,
        approver=approver,
        target="dna",
        notes=notes,
    )
    if pin_production:
        prior_dna_pin = str(state.get("active_version") or dna_base)
        if not state.get("active_reporting_version"):
            state["active_reporting_version"] = prior_dna_pin
        state["active_version"] = dna_version
    save_workflow_state(settings, state)
    return {
        "status": "saved",
        "target": "dna",
        "dna_version": dna_version,
        "version": dna_version,
        "approval_status": pack.approval.status,
        "bump_kind": dna_bump["kind"],
        "warning": dna_bump.get("warning") or "",
        "dna_base_version": dna_base,
        "dna_next_patch": bump_patch_version(dna_base),
        "dna_next_minor": bump_minor_version(dna_base),
        "dna_next_major": bump_major_version(dna_base),
        **{k: saved[k] for k in ("dna_path", "manifest_path") if k in saved},
    }


def save_governance_reporting_from_portal(
    settings: DnaSettings,
    *,
    reporting_yaml: str,
    reporting_version: str,
    pin_production: bool,
    approver: str,
) -> dict[str, Any]:
    """Parse portal reporting YAML and persist a governance version."""
    from meshflow.dna.web.portal.config_assistant.proposals import (
        bump_major_version,
        bump_minor_version,
        bump_patch_version,
        classify_manual_version_bump,
    )
    from meshflow.dna.reporting import (
        load_reporting_pack_yaml,
        normalize_reporting_identity,
        save_reporting_pack,
    )
    from meshflow.dna.workflow import load_workflow_state, save_workflow_state

    reporting_version = reporting_version.strip()
    if not reporting_version:
        raise ValueError("Reporting version is required")

    state = load_workflow_state(settings, settings.dna_config_id)
    reporting_base = str(
        state.get("active_reporting_version") or state.get("active_version") or ""
    )

    reporting_bump = classify_manual_version_bump(reporting_base, reporting_version)
    if reporting_bump["kind"] == "invalid":
        raise ValueError(f"Reporting: {reporting_bump['error']}")

    reporting_status = "production" if pin_production else "draft"
    reporting = load_reporting_pack_yaml(reporting_yaml)
    reporting = normalize_reporting_identity(
        settings,
        reporting,
        version=reporting_version,
        status=reporting_status,
    )

    notes = "Updated reporting via client portal manual edit"
    if reporting_bump["kind"] in {"minor", "major"} and reporting_bump.get("warning"):
        notes = f"{notes}. {reporting_bump['warning']}"

    saved = save_reporting_pack(
        settings,
        pack_id=settings.dna_config_id,
        version=reporting_version,
        reporting=reporting,
        status=reporting_status,
    )
    state["pack_id"] = settings.dna_config_id
    _append_portal_governance_history(
        state,
        version=reporting_version,
        status=reporting_status,
        approver=approver,
        target="reporting",
        notes=notes,
    )
    if pin_production:
        state["active_reporting_version"] = reporting_version
        if not state.get("active_version"):
            state["active_version"] = reporting_base
    save_workflow_state(settings, state)
    return {
        "status": "saved",
        "target": "reporting",
        "reporting_version": reporting_version,
        "version": reporting_version,
        "approval_status": reporting_status,
        "bump_kind": reporting_bump["kind"],
        "warning": reporting_bump.get("warning") or "",
        "reporting_base_version": reporting_base,
        "reporting_next_patch": bump_patch_version(reporting_base),
        "reporting_next_minor": bump_minor_version(reporting_base),
        "reporting_next_major": bump_major_version(reporting_base),
        "reporting_path": saved.get("path"),
    }


def save_governance_packs_from_portal(
    settings: DnaSettings,
    *,
    dna_yaml: str,
    reporting_yaml: str,
    dna_version: str,
    reporting_version: str,
    pin_production: bool,
    approver: str,
) -> dict[str, Any]:
    """Persist DNA and reporting from portal editors (combined save helper)."""
    from meshflow.dna.governance import save_governance_version
    from meshflow.dna.schema import load_definition_pack_yaml
    from meshflow.dna.web.portal.config_assistant.proposals import (
        bump_major_version,
        bump_minor_version,
        bump_patch_version,
        classify_manual_version_bump,
    )
    from meshflow.dna.reporting import (
        load_reporting_pack_yaml,
        normalize_reporting_identity,
    )
    from meshflow.dna.workflow import load_workflow_state, save_workflow_state

    dna_version = dna_version.strip()
    reporting_version = reporting_version.strip()
    if dna_version != reporting_version:
        dna_result = save_governance_dna_from_portal(
            settings,
            dna_yaml=dna_yaml,
            dna_version=dna_version,
            pin_production=pin_production,
            approver=approver,
        )
        reporting_result = save_governance_reporting_from_portal(
            settings,
            reporting_yaml=reporting_yaml,
            reporting_version=reporting_version,
            pin_production=pin_production,
            approver=approver,
        )
        warnings = " ".join(
            part
            for part in (dna_result.get("warning") or "", reporting_result.get("warning") or "")
            if part
        ).strip()
        return {
            "status": "saved",
            "dna_version": dna_result["dna_version"],
            "reporting_version": reporting_result["reporting_version"],
            "version": dna_result["dna_version"],
            "approval_status": dna_result["approval_status"],
            "bump_kind": dna_result["bump_kind"],
            "warning": warnings,
            "dna_base_version": dna_result["dna_base_version"],
            "reporting_base_version": reporting_result["reporting_base_version"],
            "dna_next_patch": dna_result["dna_next_patch"],
            "dna_next_minor": dna_result["dna_next_minor"],
            "dna_next_major": dna_result["dna_next_major"],
            "reporting_next_patch": reporting_result["reporting_next_patch"],
            "reporting_next_minor": reporting_result["reporting_next_minor"],
            "reporting_next_major": reporting_result["reporting_next_major"],
            "dna_path": dna_result.get("dna_path"),
            "reporting_path": reporting_result.get("reporting_path"),
            "manifest_path": dna_result.get("manifest_path"),
        }

    state = load_workflow_state(settings, settings.dna_config_id)
    pack = load_definition_pack_yaml(dna_yaml)
    pack.pack_id = settings.dna_config_id
    dna_base = str(state.get("active_version") or pack.version or "")
    reporting_base = str(
        state.get("active_reporting_version") or state.get("active_version") or ""
    )

    dna_bump = classify_manual_version_bump(dna_base, dna_version)
    if dna_bump["kind"] == "invalid":
        raise ValueError(f"DNA: {dna_bump['error']}")
    reporting_bump = classify_manual_version_bump(reporting_base, dna_version)
    if reporting_bump["kind"] == "invalid":
        raise ValueError(f"Reporting: {reporting_bump['error']}")

    pack.version = dna_version
    reporting = load_reporting_pack_yaml(reporting_yaml)
    if pin_production:
        pack.status = "production"
        pack.approval.status = "production"
        pack.approval.approver = approver or pack.approval.approver or "Portal admin"
        pack.approval.approved_at = datetime.now(UTC).date().isoformat()
        reporting_status = "production"
    else:
        pack.status = "draft"
        pack.approval.status = "draft"
        reporting_status = "draft"

    reporting = normalize_reporting_identity(
        settings,
        reporting,
        version=dna_version,
        status=reporting_status,
    )

    warnings: list[str] = []
    for bump in (dna_bump, reporting_bump):
        if bump["kind"] in {"minor", "major"} and bump.get("warning"):
            warnings.append(str(bump["warning"]))

    saved = save_governance_version(settings, pack=pack, reporting=reporting)
    state["pack_id"] = settings.dna_config_id
    notes = "Updated via client portal"
    if warnings:
        notes = f"{notes}. {' '.join(warnings)}"
    _append_portal_governance_history(
        state,
        version=dna_version,
        status=pack.approval.status,
        approver=approver,
        target="all",
        notes=notes,
    )
    if pin_production:
        state["active_version"] = dna_version
        state["active_reporting_version"] = dna_version
    save_workflow_state(settings, state)
    return {
        "status": "saved",
        "dna_version": dna_version,
        "reporting_version": dna_version,
        "version": dna_version,
        "approval_status": pack.approval.status,
        "bump_kind": dna_bump["kind"],
        "warning": " ".join(warnings),
        "dna_base_version": dna_base,
        "reporting_base_version": reporting_base,
        "dna_next_patch": bump_patch_version(dna_base),
        "dna_next_minor": bump_minor_version(dna_base),
        "dna_next_major": bump_major_version(dna_base),
        "reporting_next_patch": bump_patch_version(reporting_base),
        "reporting_next_minor": bump_minor_version(reporting_base),
        "reporting_next_major": bump_major_version(reporting_base),
        **{k: saved[k] for k in ("dna_path", "reporting_path", "manifest_path") if k in saved},
    }


def render_governance(
    request: Request,
    *,
    settings: DnaSettings,
    client: ClientPortalConfig,
    is_admin: bool = False,
    message: str = "",
    error: str = "",
    dna_yaml_override: str | None = None,
    reporting_yaml_override: str | None = None,
    dna_version_override: str | None = None,
    reporting_version_override: str | None = None,
    proposal_view_data: dict[str, Any] | None = None,
    base_version: str = "",
    update_tab: str = "assist",
) -> Response:
    from meshflow.dna.reporting import (
        default_reporting_pack,
        load_production_reporting,
    )
    from meshflow.dna.workflow import load_production_pack

    try:
        pack = load_production_pack(settings)
    except Exception:  # noqa: BLE001
        pack = load_pack_from_settings(settings)

    workflow = load_workflow_state(settings, settings.dna_config_id)
    manifest = read_json_artifact(settings, f"{settings.gold_dna_prefix}/manifest.json") or {}
    active_version = workflow.get("active_version") or pack.version
    history = workflow.get("history", [])
    if not isinstance(history, list):
        history = []

    try:
        reporting = load_production_reporting(settings)
    except FileNotFoundError:
        reporting = default_reporting_pack(
            pack_id=settings.reporting_config_id,
            version=str(active_version),
            status="draft",
            description="Reporting config not seeded yet.",
        )
    active_reporting_version = (
        workflow.get("active_reporting_version") or reporting.get("version") or active_version
    )

    url: Callable[[str], str] = lambda path: f"{request.script_root}{path if path.startswith('/') else f'/{path}'}"
    dna_history = _filter_pack_history(history, "dna")
    reporting_history = _filter_pack_history(history, "reporting")
    governance_form_action = url("/portal/governance")
    dna_history_rows = _history_table_rows(
        dna_history,
        pack_kind="dna",
        active_version=str(active_version or ""),
        is_admin=is_admin,
        form_action=governance_form_action,
        settings=settings,
    )
    reporting_history_rows = _history_table_rows(
        reporting_history,
        pack_kind="reporting",
        active_version=str(active_reporting_version or ""),
        is_admin=is_admin,
        form_action=governance_form_action,
        settings=settings,
    )
    history_actions_header = "<th>Actions</th>" if is_admin else ""
    reporting_pages = "".join(
        f"<li>{escape(str(page.get('title') or page.get('id') or page))}</li>"
        for page in reporting.get("pages", [])
        if isinstance(page, dict) or isinstance(page, str)
    )
    manifest_outputs = manifest.get("outputs", [])
    output_count = len(manifest_outputs) if isinstance(manifest_outputs, list) else 0
    published_at = _format_published_date(manifest.get("published_at")) if manifest.get("published_at") else "—"

    dna_yaml = dna_yaml_override if dna_yaml_override is not None else _pack_to_yaml(pack.to_dict())
    reporting_yaml = (
        reporting_yaml_override
        if reporting_yaml_override is not None
        else _pack_to_yaml(reporting)
    )
    body = page_header(
        "Pack Registry",
        "Version-controlled DNA and reporting packs — view and update the contracts that power this portal.",
        eyebrow="Governance",
    )
    if message:
        body += f'<div class="form-success">{escape(message)}</div>'
    if error:
        body += f'<div class="form-error">{escape(error)}</div>'
    body += f"""
    <section class="section">
      <div class="section-title">DNA definition pack</div>
      <div class="card pack-card">
        <p class="pack-card-lead">{escape(pack.description)}</p>
        <dl class="pack-meta">
          <div><dt>Pack</dt><dd><code>{escape(pack.pack_id)}</code></dd></div>
          <div><dt>Version</dt><dd><span class="pack-version">v{escape(pack.version)}</span></dd></div>
          <div><dt>Status</dt><dd>{escape(pack.approval.status)}</dd></div>
          <div><dt>Production pin</dt><dd>v{escape(str(active_version))}</dd></div>
          <div><dt>Approver</dt><dd>{escape(pack.approval.approver or "—")}</dd></div>
          <div><dt>Approved</dt><dd>{escape(pack.approval.approved_at or "—")}</dd></div>
          <div><dt>Gold refresh</dt><dd>{escape(published_at)}</dd></div>
          <div><dt>Published outputs</dt><dd>{output_count}</dd></div>
        </dl>
      </div>
    </section>
    <section class="section">
      <div class="section-title">Reporting layout pack</div>
      <div class="card pack-card">
        <p class="pack-card-lead">{escape(str(reporting.get("description") or ""))}</p>
        <dl class="pack-meta">
          <div><dt>Pack</dt><dd><code>{escape(str(reporting.get("pack_id") or settings.reporting_config_id))}</code></dd></div>
          <div><dt>Version</dt><dd><span class="pack-version">v{escape(str(reporting.get("version") or "—"))}</span></dd></div>
          <div><dt>Status</dt><dd>{escape(str(reporting.get("status") or "—"))}</dd></div>
          <div><dt>Production pin</dt><dd>v{escape(str(active_reporting_version))}</dd></div>
        </dl>
        <div class="section-title" style="margin-top:1rem;margin-bottom:0.5rem">Included pages</div>
        <ul class="plain">{reporting_pages or "<li>No pages defined</li>"}</ul>
      </div>
    </section>
    """
    if is_admin:
        from meshflow.dna.web.portal.config_assistant.bedrock_usage import usage_summary as bedrock_usage_summary
        from meshflow.dna.web.portal.config_assistant.proposals import (
            bump_major_version,
            bump_minor_version,
            bump_patch_version,
        )

        assist_meta = (proposal_view_data or {}).get("meta") or {}
        pinned_dna = str(assist_meta.get("dna_base_version") or active_version or "—")
        pinned_reporting = str(
            assist_meta.get("reporting_base_version") or active_reporting_version or "—"
        )
        dna_base = str(active_version or pack.version or "")
        reporting_base = str(active_reporting_version or reporting.get("version") or dna_base)
        dna_next_patch = bump_patch_version(dna_base)
        dna_next_minor = bump_minor_version(dna_base)
        dna_next_major = bump_major_version(dna_base)
        reporting_next_patch = bump_patch_version(reporting_base)
        reporting_next_minor = bump_minor_version(reporting_base)
        reporting_next_major = bump_major_version(reporting_base)
        manual_dna_version = (
            str(dna_version_override).strip()
            if dna_version_override
            else dna_next_patch
        )
        manual_reporting_version = (
            str(reporting_version_override).strip()
            if reporting_version_override
            else reporting_next_patch
        )
        assistant_usage = bedrock_usage_summary(
            settings,
            client_id=client.client_id,
            monthly_budget_usd=client.config_assistant_monthly_budget_usd,
        ).to_dict()
        body += _governance_update_section_html(
            url,
            request_url=request.url,
            dna_yaml=dna_yaml,
            reporting_yaml=reporting_yaml,
            dna_version=manual_dna_version,
            dna_base_version=dna_base,
            dna_next_patch=dna_next_patch,
            dna_next_minor=dna_next_minor,
            dna_next_major=dna_next_major,
            reporting_version=manual_reporting_version,
            reporting_base_version=reporting_base,
            reporting_next_patch=reporting_next_patch,
            reporting_next_minor=reporting_next_minor,
            reporting_next_major=reporting_next_major,
            proposal_view_data=proposal_view_data,
            base_version=base_version,
            pinned_dna_version=pinned_dna,
            pinned_reporting_version=pinned_reporting,
            update_tab=update_tab,
            usage_summary=assistant_usage,
        )
    else:
        body += _governance_update_restricted_html()
    body += f"""
    <section class="section">
      <div class="section-title">Version history</div>
      <div class="pack-history-subtitle">DNA</div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Version</th><th>Status</th><th>Approver</th><th>Date</th><th>Notes</th>{history_actions_header}</tr></thead>
          <tbody>{dna_history_rows}</tbody>
        </table>
      </div>
      <div class="pack-history-subtitle">Reporting</div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Version</th><th>Status</th><th>Approver</th><th>Date</th><th>Notes</th>{history_actions_header}</tr></thead>
          <tbody>{reporting_history_rows}</tbody>
        </table>
      </div>
    </section>
    """
    return _html_response(
        request,
        client=client,
        title="Pack Registry",
        active_path="/portal/governance",
        body=body,
        is_admin=is_admin,
        settings=settings,
    )


def render_config_assistant(
    request: Request,
    *,
    settings: DnaSettings,
    client: ClientPortalConfig,
    proposal_view_data: dict[str, Any] | None = None,
    base_version: str = "",
    message: str = "",
    error: str = "",
) -> Response:
    """Legacy entry point — Config Assist now lives on Pack Registry."""
    return render_governance(
        request,
        settings=settings,
        client=client,
        is_admin=True,
        message=message,
        error=error,
        proposal_view_data=proposal_view_data,
        base_version=base_version,
        update_tab="assist",
    )


def _user_status_label(status: str) -> str:
    labels = {
        "CONFIRMED": "Active",
        "FORCE_CHANGE_PASSWORD": "Invite pending",
        "RESET_REQUIRED": "Password reset",
        "UNCONFIRMED": "Unconfirmed",
    }
    return labels.get(status, status.replace("_", " ").title())


def _legacy_portal_users(client_id: str, *, company: str, environment: str) -> list[Any]:
    from meshflow.dna.web.portal.auth import load_portal_users
    from meshflow.dna.web.portal.cognito import PORTAL_ROLE_ADMIN, PortalUserRecord

    normalized = client_id.strip().lower()
    records: list[PortalUserRecord] = []
    for user in load_portal_users(company=company, environment=environment).values():
        if user.client_id != normalized:
            continue
        records.append(
            PortalUserRecord(
                username=user.username,
                email="",
                client_id=user.client_id,
                role=PORTAL_ROLE_ADMIN,
                status="CONFIRMED",
                enabled=True,
            )
        )
    records.sort(key=lambda item: item.username)
    return records


def render_admin_users(
    request: Request,
    *,
    client: ClientPortalConfig,
    users: list[Any],
    current_username: str,
    message: str = "",
    error: str = "",
    invites_enabled: bool = True,
    is_admin: bool = True,
    settings: DnaSettings | None = None,
) -> Response:
    from meshflow.dna.web.portal.cognito import PORTAL_ROLE_ADMIN, PORTAL_ROLE_MEMBER

    url: Callable[[str], str] = lambda path: f"{request.script_root}{path if path.startswith('/') else f'/{path}'}"
    seat_count = len(users)
    at_capacity = seat_count >= client.max_users
    users_path = "/portal/governance/users"

    message_html = f'<div class="form-success">{escape(message)}</div>' if message else ""
    error_html = f'<div class="form-error">{escape(error)}</div>' if error else ""

    user_rows = ""
    for user in users:
        you = user.username.casefold() == current_username.strip().casefold()
        you_marker = " (you)" if you else ""
        enabled_label = "Active" if user.enabled else "Disabled"
        if user.status == "FORCE_CHANGE_PASSWORD":
            enabled_label = "Invite pending"
        current_role = str(getattr(user, "role", PORTAL_ROLE_MEMBER) or PORTAL_ROLE_MEMBER).lower()
        if is_admin and not you:
            role_cell = f"""
            <form method="post" action="{escape(url(users_path))}" class="governance-role-form">
              <input type="hidden" name="action" value="set_role" />
              <input type="hidden" name="username" value="{escape(user.username)}" />
              <select name="role" class="governance-role-select" aria-label="Role for {escape(user.username)}">
                <option value="{PORTAL_ROLE_MEMBER}" {"selected" if current_role == PORTAL_ROLE_MEMBER else ""}>Member</option>
                <option value="{PORTAL_ROLE_ADMIN}" {"selected" if current_role == PORTAL_ROLE_ADMIN else ""}>Admin</option>
              </select>
              <button type="submit" class="btn portal-submit-btn">Update</button>
            </form>
            """
        else:
            role_cell = escape(current_role.title())
        user_rows += (
            f"<tr>"
            f"<td>{escape(user.username)}{escape(you_marker)}</td>"
            f"<td>{escape(user.email or '—')}</td>"
            f"<td>{role_cell}</td>"
            f"<td>{escape(_user_status_label(user.status))}</td>"
            f"<td>{escape(enabled_label)}</td>"
            f"</tr>"
        )

    invite_disabled = at_capacity or not invites_enabled or not is_admin
    invite_note = ""
    if not is_admin:
        invite_note = (
            '<p class="governance-invite-note">Only admins can invite users or change roles.</p>'
        )
    elif not invites_enabled:
        invite_note = (
            '<p class="governance-invite-note">User invites require Cognito in deployed environments.</p>'
        )
    elif at_capacity:
        invite_note = (
            f'<p class="governance-invite-note">All {client.max_users} seats are in use. '
            "Remove a user or contact HiveFlowAI to increase your limit.</p>"
        )

    if invite_disabled:
        invite_fields = (
            '<div class="form-field"><label>Username</label><input disabled /></div>'
            '<div class="form-field"><label>Email</label><input disabled /></div>'
            '<div class="form-field"><label>Role</label><select disabled><option>Member</option></select></div>'
            '<div class="form-field governance-invite-action">'
            '<button class="btn btn-primary portal-submit-btn" type="submit" disabled>Send invite</button>'
            '</div>'
        )
    else:
        invite_fields = f"""
          <div class="form-field">
            <label for="invite_username">Username</label>
            <input id="invite_username" name="username" autocomplete="off" required />
          </div>
          <div class="form-field">
            <label for="invite_email">Email</label>
            <input id="invite_email" name="email" type="email" autocomplete="off" required />
          </div>
          <div class="form-field">
            <label for="invite_role">Role</label>
            <select id="invite_role" name="role">
              <option value="{PORTAL_ROLE_MEMBER}" selected>Member</option>
              <option value="{PORTAL_ROLE_ADMIN}">Admin</option>
            </select>
          </div>
          <div class="form-field governance-invite-action">
            <button class="btn btn-primary portal-submit-btn" type="submit">Send invite</button>
          </div>
        """

    body = page_header(
        "Users",
        "Portal users for this client — invite colleagues and manage admin vs member roles.",
        eyebrow="Governance",
    )
    body += badge_row((f"{seat_count} of {client.max_users} seats used", False))
    body += message_html
    body += error_html
    body += f"""
    <section class="section">
      <div class="section-title">Current users</div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr><th>Username</th><th>Email</th><th>Role</th><th>Status</th><th>Access</th></tr>
          </thead>
          <tbody>{user_rows or "<tr><td colspan='5'>No users found for this client.</td></tr>"}</tbody>
        </table>
      </div>
    </section>
    <section class="section governance-invite-section">
      <div class="section-title">Invite user</div>
      <div class="card pack-card governance-invite-card">
        {invite_note}
        <form method="post" action="{escape(url(users_path))}" class="governance-invite-form">
          <input type="hidden" name="action" value="invite" />
          {invite_fields}
        </form>
      </div>
    </section>
    """
    return _html_response(
        request,
        client=client,
        title="Users",
        active_path=users_path,
        body=body,
        is_admin=is_admin,
        settings=settings,
    )


# Legacy alias until callers migrate
render_semantics = render_governance
