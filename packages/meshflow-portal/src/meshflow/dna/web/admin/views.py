"""HTML for the platform admin job shell."""

from __future__ import annotations

from html import escape
from typing import Any, Callable

from meshflow.dna.web.admin.registry import (
    AdminJob,
    jobs_grouped_by_source,
    source_display_name,
)
from meshflow.dna.web.theme import render_page


UrlFn = Callable[[str], str]


def _status_badge(status: dict[str, Any] | None) -> str:
    if not status:
        return '<span class="admin-job-state is-unknown">Unknown</span>'
    state = str(status.get("state") or "unknown").strip() or "unknown"
    css = "is-ok" if state.lower() in {"active", "queued", "local"} else "is-unknown"
    if state.lower() in {"failed", "inactive", "error"}:
        css = "is-error"
    label = escape(state)
    return f'<span class="admin-job-state {css}">{label}</span>'


def _job_card_html(
    job: AdminJob,
    *,
    url: UrlFn,
    status: dict[str, Any] | None = None,
    flash: str = "",
) -> str:
    follow = ""
    if job.follow_ons:
        follow = (
            '<p class="admin-job-follow">Follow-ons: '
            + ", ".join(f"<code>{escape(item)}</code>" for item in job.follow_ons)
            + "</p>"
        )
    message = ""
    if status and status.get("message"):
        message = f'<p class="admin-job-message">{escape(str(status.get("message")))}</p>'
    flash_html = ""
    if flash:
        flash_html = f'<p class="admin-job-flash">{escape(flash)}</p>'
    last_mod = ""
    if status and status.get("last_modified"):
        last_mod = (
            f'<p class="admin-job-meta">Last modified: '
            f'{escape(str(status.get("last_modified")))}</p>'
        )
    return f"""
    <article class="admin-job-card" data-job-id="{escape(job.id)}">
      <div class="admin-job-card-head">
        <h3>{escape(job.title)}</h3>
        {_status_badge(status)}
      </div>
      <p class="admin-job-desc">{escape(job.description)}</p>
      <p class="admin-job-id"><code>{escape(job.id)}</code></p>
      {follow}
      {last_mod}
      {message}
      {flash_html}
      <div class="admin-job-actions">
        <form method="post" action="{escape(url(f'/admin/jobs/{job.id}/run'))}">
          <button type="submit" class="btn">Run</button>
        </form>
        <a class="btn secondary" href="{escape(url(f'/admin/jobs/{job.id}/status'))}">Status JSON</a>
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
        nav_links=(("/admin", "Jobs"),),
    )


def render_admin_dashboard(
    *,
    url: UrlFn,
    username: str,
    statuses: dict[str, dict[str, Any]] | None = None,
    flash_by_job: dict[str, str] | None = None,
) -> str:
    statuses = statuses or {}
    flash_by_job = flash_by_job or {}
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
        same Run / Status pattern.
      </p>
    </div>
    <style>
      .admin-shell {{ max-width: 960px; margin: 0 auto; padding: 1.5rem 1rem 3rem; }}
      .admin-shell-header {{
        display: flex; justify-content: space-between; gap: 1rem; align-items: flex-start;
        margin-bottom: 1.75rem;
      }}
      .admin-eyebrow {{
        text-transform: uppercase; letter-spacing: 0.16em; font-size: 0.72rem;
        color: var(--accent-electric-gold); font-weight: 600; margin: 0 0 0.35rem;
      }}
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
      .admin-job-id, .admin-job-follow, .admin-job-meta, .admin-job-message {{
        font-size: 0.85rem; color: var(--text-dim); margin: 0.25rem 0;
      }}
      .admin-job-flash {{ color: #99f6e4; font-size: 0.9rem; }}
      .admin-job-actions {{ display: flex; gap: 0.6rem; margin-top: 0.85rem; align-items: center; }}
      .admin-job-state {{
        font-size: 0.75rem; font-weight: 600; padding: 0.2rem 0.5rem;
        border-radius: var(--radius-sm); border: 1px solid var(--border);
        background: rgba(255, 255, 255, 0.02); color: var(--text-muted);
      }}
      .admin-job-state.is-ok {{
        border-color: rgba(20, 184, 166, 0.28); background: rgba(20, 184, 166, 0.06);
        color: #99f6e4;
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
    """
    return render_page(
        title="Platform admin",
        body=body,
        url=url,
        active_path="/admin",
        nav_links=(("/admin", "Jobs"),),
    )
