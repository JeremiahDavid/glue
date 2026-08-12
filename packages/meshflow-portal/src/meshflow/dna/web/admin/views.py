"""HTML for the platform admin job shell."""

from __future__ import annotations

from html import escape
from typing import Any, Callable

from meshflow.dna.web.admin.diagrams import INFRASTRUCTURE_MERMAID, PIPELINE_MERMAID
from meshflow.dna.web.admin.registry import (
    AdminJob,
    jobs_grouped_by_source,
    source_display_name,
)
from meshflow.dna.web.theme import render_page


UrlFn = Callable[[str], str]

_ADMIN_NAV = (
    ("/admin", "Jobs"),
    ("/admin/architecture", "Architecture"),
)

_ADMIN_SHELL_CSS = """
      .admin-shell { max-width: 960px; margin: 0 auto; padding: 1.5rem 1rem 3rem; }
      .admin-shell-header {
        display: flex; justify-content: space-between; gap: 1rem; align-items: flex-start;
        margin-bottom: 1.75rem;
      }
      .admin-eyebrow {
        text-transform: uppercase; letter-spacing: 0.16em; font-size: 0.72rem;
        color: var(--accent-electric-gold); font-weight: 600; margin: 0 0 0.35rem;
      }
"""


def _run_state_css(state: str) -> str:
    key = state.strip().lower()
    if key in {"completed", "ok", "local"}:
        return "is-ok"
    if key in {"running", "queued"}:
        return "is-running"
    if key in {"failed", "error", "inactive"}:
        return "is-error"
    return "is-unknown"


def _status_badge(status: dict[str, Any] | None) -> str:
    if not status:
        return '<span class="admin-job-state is-unknown" data-run-state="unknown">Unknown</span>'
    state = str(status.get("run_state") or status.get("state") or "unknown").strip() or "unknown"
    label = escape(state.replace("_", " ").title())
    return (
        f'<span class="admin-job-state {_run_state_css(state)}" data-run-state="{escape(state)}">'
        f"{label}</span>"
    )


def _job_card_html(
    job: AdminJob,
    *,
    url: UrlFn,
    status: dict[str, Any] | None = None,
    flash: str = "",
    optimistic_state: str = "",
) -> str:
    follow = ""
    if job.follow_ons:
        follow = (
            '<p class="admin-job-follow">Follow-ons: '
            + ", ".join(f"<code>{escape(item)}</code>" for item in job.follow_ons)
            + "</p>"
        )
    display_status = dict(status or {})
    current_state = str(display_status.get("run_state") or display_status.get("state") or "").lower()
    if optimistic_state == "queued" and current_state != "running":
        # Prior completed/failed is stale until the new invocation appears in logs.
        display_status["run_state"] = "queued"
        display_status["summary"] = flash or "Invoked — waiting for Lambda logs…"

    summary = ""
    summary_text = str(display_status.get("summary") or "").strip()
    if summary_text and not summary_text.startswith("{"):
        summary = (
            f'<p class="admin-job-summary" data-role="summary">'
            f"{escape(summary_text)}</p>"
        )
    flash_html = ""
    if flash:
        flash_html = f'<p class="admin-job-flash">{escape(flash)}</p>'

    function_name = str((status or {}).get("function_name") or job.function_name() or "").strip()
    console_url = str((status or {}).get("console_url") or "").strip()
    if not console_url and function_name:
        from meshflow.dna.web.admin.jobs import lambda_console_url

        console_url = lambda_console_url(function_name)

    lambda_link = ""
    if console_url:
        lambda_link = (
            f'<a class="btn secondary" href="{escape(console_url)}" target="_blank" '
            f'rel="noopener noreferrer">Open Lambda</a>'
        )
    status_url = escape(url(f"/admin/jobs/{job.id}/status"))
    return f"""
    <article class="admin-job-card" data-job-id="{escape(job.id)}"
             data-status-url="{status_url}">
      <div class="admin-job-card-head">
        <h3>{escape(job.title)}</h3>
        {_status_badge(display_status)}
      </div>
      <p class="admin-job-desc">{escape(job.description)}</p>
      <p class="admin-job-id"><code>{escape(job.id)}</code></p>
      {follow}
      {summary}
      {flash_html}
      <div class="admin-job-actions">
        <form method="post" action="{escape(url(f'/admin/jobs/{job.id}/run'))}">
          <button type="submit" class="btn">Run</button>
        </form>
        {lambda_link}
      </div>
    </article>
    """

def render_admin_login_page(
    *,
    url: UrlFn,
    error: str = "",
    next_path: str = "/admin",
    mode: str = "login",
    username: str = "",
    session: str = "",
) -> str:
    error_html = f'<p class="form-error">{escape(error)}</p>' if error else ""
    if mode == "set_password":
        form = f"""
        <form method="post" action="{escape(url("/admin/login"))}" class="admin-login-form">
          <input type="hidden" name="mode" value="set_password" />
          <input type="hidden" name="username" value="{escape(username)}" />
          <input type="hidden" name="session" value="{escape(session)}" />
          <input type="hidden" name="next" value="{escape(next_path)}" />
          <label>New password
            <input type="password" name="new_password" required autocomplete="new-password" />
          </label>
          <button type="submit" class="btn">Set password</button>
        </form>
        """
    else:
        form = f"""
        <form method="post" action="{escape(url("/admin/login"))}" class="admin-login-form">
          <input type="hidden" name="next" value="{escape(next_path)}" />
          <label>Username
            <input type="text" name="username" required autocomplete="username"
                   value="{escape(username)}" />
          </label>
          <label>Password
            <input type="password" name="password" required autocomplete="current-password" />
          </label>
          <button type="submit" class="btn">Sign in</button>
        </form>
        """
    body = f"""
    <section class="admin-login">
      <h1>Platform admin</h1>
      <p class="pack-card-lead">HiveFlowAI operational jobs. GlobalAdmin only.</p>
      {error_html}
      {form}
    </section>
    <style>
      .admin-login {{ max-width: 28rem; margin: 3rem auto; padding: 0 1rem; }}
      .admin-login h1 {{ font-size: 1.75rem; margin-bottom: 0.35rem; }}
      .admin-login-form {{ display: grid; gap: 0.85rem; margin-top: 1.25rem; }}
      .admin-login-form label {{
        display: grid; gap: 0.35rem; font-size: 0.9rem; color: var(--text-muted);
      }}
      .admin-login-form input {{
        padding: 0.55rem 0.7rem; border: 1px solid var(--border); border-radius: var(--radius-sm);
        background: rgba(255, 255, 255, 0.03); color: var(--text); font: inherit;
      }}
      .admin-login-form input:focus {{
        outline: none; border-color: rgba(56, 189, 248, 0.45);
        box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.12);
      }}
      .form-error {{ color: #fca5a5; margin-top: 0.75rem; }}
    </style>
    """
    return render_page(
        title="Platform admin login",
        body=body,
        url=url,
        active_path="/admin/login",
        nav_links=_ADMIN_NAV,
    )


def render_admin_dashboard(
    *,
    url: UrlFn,
    username: str,
    statuses: dict[str, dict[str, Any]] | None = None,
    flash_by_job: dict[str, str] | None = None,
    optimistic_by_job: dict[str, str] | None = None,
) -> str:
    statuses = statuses or {}
    flash_by_job = flash_by_job or {}
    optimistic_by_job = optimistic_by_job or {}
    sections: list[str] = []
    for source, groups in jobs_grouped_by_source():
        group_html: list[str] = []
        for group_name, jobs in groups:
            cards = "".join(
                _job_card_html(
                    job,
                    url=url,
                    status=statuses.get(job.id),
                    flash=flash_by_job.get(job.id, ""),
                    optimistic_state=optimistic_by_job.get(job.id, ""),
                )
                for job in jobs
            )
            group_html.append(
                f'<section class="admin-job-group">'
                f"<h2>{escape(group_name)}</h2>"
                f'<div class="admin-job-grid">{cards}</div>'
                f"</section>"
            )
        sections.append(
            f'<section class="admin-source-section" data-source="{escape(source)}">'
            f"<h1>{escape(source_display_name(source))}</h1>"
            f'{"".join(group_html)}'
            f"</section>"
        )

    if not sections:
        sections.append(
            '<p class="pack-card-lead">No jobs registered yet. '
            "Add entries in <code>admin.registry.registered_admin_jobs</code>.</p>"
        )

    body = f"""
    <div class="admin-shell">
      <header class="admin-shell-header">
        <div>
          <p class="admin-eyebrow">Platform admin</p>
          <h1>Operational jobs</h1>
          <p class="pack-card-lead">
            Invoke and monitor connector documentation and future data-source jobs.
            Signed in as <strong>{escape(username)}</strong>.
          </p>
        </div>
        <form method="post" action="{escape(url("/admin/logout"))}">
          <button type="submit" class="btn secondary">Sign out</button>
        </form>
      </header>
      {"".join(sections)}
      <p class="admin-extensibility-note">
        Additional data sources (QBO, QBD, …) register here via the admin job catalog —
        same Run / Open Lambda pattern. Badges refresh while a job is queued or running.
      </p>
    </div>
    <style>
      {_ADMIN_SHELL_CSS}
      .admin-source-section {{ margin-bottom: 2rem; }}
      .admin-source-section > h1 {{ font-size: 1.35rem; margin-bottom: 0.75rem; }}
      .admin-job-group h2 {{
        font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.1em;
        font-weight: 600; margin: 0 0 0.75rem; color: var(--text-dim);
      }}
      .admin-job-grid {{ display: grid; gap: 1rem; }}
      .admin-job-card {{
        border: 1px solid var(--border); border-radius: var(--radius);
        padding: 1rem 1.15rem; background: var(--bg-elevated);
      }}
      .admin-job-card-head {{
        display: flex; justify-content: space-between; gap: 0.75rem; align-items: center;
      }}
      .admin-job-card-head h3 {{ margin: 0; font-size: 1.05rem; color: var(--text); }}
      .admin-job-desc {{ color: var(--text-muted); margin: 0.55rem 0; font-size: 0.92rem; }}
      .admin-job-id, .admin-job-follow, .admin-job-summary {{
        font-size: 0.85rem; color: var(--text-dim); margin: 0.25rem 0;
      }}
      .admin-job-flash {{ color: #99f6e4; font-size: 0.9rem; }}
      .admin-job-actions {{ display: flex; gap: 0.6rem; margin-top: 0.85rem; align-items: center; }}
      .admin-job-state {{
        font-size: 0.75rem; font-weight: 600; padding: 0.2rem 0.5rem;
        border-radius: var(--radius-sm); border: 1px solid var(--border);
        background: rgba(255, 255, 255, 0.02); color: var(--text-muted);
        text-transform: capitalize;
      }}
      .admin-job-state.is-ok {{
        border-color: rgba(20, 184, 166, 0.28); background: rgba(20, 184, 166, 0.06);
        color: #99f6e4;
      }}
      .admin-job-state.is-running {{
        border-color: rgba(56, 189, 248, 0.35); background: rgba(56, 189, 248, 0.08);
        color: #7dd3fc;
      }}
      .admin-job-state.is-error {{
        border-color: rgba(239, 68, 68, 0.28); background: rgba(239, 68, 68, 0.1);
        color: #fca5a5;
      }}
      .admin-extensibility-note {{
        margin-top: 2rem; font-size: 0.9rem; color: var(--text-dim);
        border-top: 1px solid var(--border); padding-top: 1rem;
      }}
    </style>
    <script>
      (function () {{
        const POLL_MS = 5000;
        const ACTIVE = new Set(["queued", "running"]);

        function cssFor(state) {{
          const key = String(state || "unknown").toLowerCase();
          if (key === "completed" || key === "ok" || key === "local") return "is-ok";
          if (key === "running" || key === "queued") return "is-running";
          if (key === "failed" || key === "error" || key === "inactive") return "is-error";
          return "is-unknown";
        }}

        function labelFor(state) {{
          return String(state || "unknown").replace(/_/g, " ");
        }}

        function applyStatus(card, payload) {{
          const state = String(payload.run_state || payload.state || "unknown");
          const badge = card.querySelector(".admin-job-state");
          if (badge) {{
            badge.className = "admin-job-state " + cssFor(state);
            badge.dataset.runState = state;
            badge.textContent = labelFor(state);
          }}
          let summary = card.querySelector('[data-role="summary"]');
          const text = String(payload.summary || "").trim();
          if (text && !text.startsWith("{{")) {{
            if (!summary) {{
              summary = document.createElement("p");
              summary.className = "admin-job-summary";
              summary.dataset.role = "summary";
              const actions = card.querySelector(".admin-job-actions");
              card.insertBefore(summary, actions);
            }}
            summary.textContent = text;
          }}
          card.dataset.runState = state;
        }}

        async function refreshCard(card) {{
          const statusUrl = card.getAttribute("data-status-url");
          if (!statusUrl) return;
          try {{
            const response = await fetch(statusUrl, {{
              headers: {{ "Accept": "application/json" }},
              credentials: "same-origin",
            }});
            if (!response.ok) return;
            const payload = await response.json();
            applyStatus(card, payload);
          }} catch (_err) {{
            /* keep last known badge */
          }}
        }}

        async function tick() {{
          const cards = Array.from(document.querySelectorAll(".admin-job-card[data-status-url]"));
          const active = cards.filter((card) => {{
            const state = (
              card.dataset.runState
              || card.querySelector(".admin-job-state")?.dataset?.runState
              || ""
            ).toLowerCase();
            return ACTIVE.has(state);
          }});
          const targets = active.length ? active : cards;
          await Promise.all(targets.map(refreshCard));
          const stillActive = cards.some((card) =>
            ACTIVE.has(String(card.dataset.runState || "").toLowerCase())
          );
          window.setTimeout(tick, stillActive ? POLL_MS : POLL_MS * 3);
        }}

        document.querySelectorAll(".admin-job-card").forEach((card) => {{
          const state = card.querySelector(".admin-job-state")?.dataset?.runState || "";
          card.dataset.runState = state;
        }});
        window.setTimeout(tick, 1500);
      }})();
    </script>
    """
    return render_page(
        title="Platform admin",
        body=body,
        url=url,
        active_path="/admin",
        nav_links=_ADMIN_NAV,
    )

def render_admin_architecture(*, url: UrlFn, username: str) -> str:
    body = f"""
    <div class="admin-shell admin-architecture">
      <header class="admin-shell-header">
        <div>
          <p class="admin-eyebrow">Platform admin</p>
          <h1>Architecture</h1>
          <p class="pack-card-lead">
            Current-state AWS stacks and the ingest → DNA → reporting data path.
            Signed in as <strong>{escape(username)}</strong>.
          </p>
        </div>
        <form method="post" action="{escape(url("/admin/logout"))}">
          <button type="submit" class="btn secondary">Sign out</button>
        </form>
      </header>

      <section class="admin-diagram-section" id="infrastructure">
        <h2>Infrastructure</h2>
        <p class="pack-card-lead">
          DNS edge, Global UI, Reporting, Platform Admin, Source Docs, and company
          Ingest / DNA stacks.
        </p>
        <div class="admin-diagram-panel">
          <pre class="mermaid">{escape(INFRASTRUCTURE_MERMAID)}</pre>
        </div>
      </section>

      <section class="admin-diagram-section" id="pipeline">
        <h2>Ingest / DNA / Reporting</h2>
        <p class="pack-card-lead">
          Scheduled bronze → silver → gold refresh versus on-demand DNA and Reporting
          pack updates that pin compile and portal layout.
        </p>
        <div class="admin-diagram-panel">
          <pre class="mermaid">{escape(PIPELINE_MERMAID)}</pre>
        </div>
      </section>
    </div>
    <style>
      {_ADMIN_SHELL_CSS}
      .admin-architecture {{ max-width: 1100px; }}
      .admin-diagram-section {{ margin-bottom: 2.25rem; }}
      .admin-diagram-section h2 {{
        font-size: 1.2rem; margin: 0 0 0.4rem; color: var(--text);
      }}
      .admin-diagram-panel {{
        margin-top: 1rem;
        border: 1px solid var(--border);
        border-radius: var(--radius);
        background: var(--bg-elevated);
        padding: 1rem 1.1rem;
        overflow-x: auto;
      }}
      .admin-diagram-panel .mermaid {{
        margin: 0;
        background: transparent;
        font-family: inherit;
        text-align: center;
      }}
    </style>
    <script type="module">
      import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
      mermaid.initialize({{
        startOnLoad: true,
        theme: "dark",
        securityLevel: "strict",
        flowchart: {{ htmlLabels: false, curve: "basis" }},
      }});
    </script>
    """
    return render_page(
        title="Architecture",
        body=body,
        url=url,
        active_path="/admin/architecture",
        nav_links=_ADMIN_NAV,
    )
