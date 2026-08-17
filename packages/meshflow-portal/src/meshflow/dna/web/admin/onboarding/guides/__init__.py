"""Load connector credential setup guides from ``onboarding/`` markdown files."""

from __future__ import annotations

import importlib.resources
import re
from functools import lru_cache
from html import escape
from pathlib import Path

# Source key → markdown filename under ``onboarding/`` (repo root) and packaged guides/.
CONNECTOR_GUIDE_FILES: dict[str, str] = {
    "dbc": "business-central.md",
    "qbo": "quickbooks-online.md",
    "qbd": "quickbooks-desktop.md",
}


def connector_guide_filename(source: str) -> str | None:
    key = source.strip().lower()
    if not key:
        return None
    if key in CONNECTOR_GUIDE_FILES:
        return CONNECTOR_GUIDE_FILES[key]
    return f"{key}.md"


def _repo_onboarding_dir() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "onboarding"
        if (candidate / "README.md").is_file():
            return candidate
    return None


def load_connector_guide_markdown(source: str) -> str | None:
    filename = connector_guide_filename(source)
    if not filename:
        return None

    onboarding_dir = _repo_onboarding_dir()
    if onboarding_dir is not None:
        path = onboarding_dir / filename
        if path.is_file():
            return path.read_text(encoding="utf-8")

    try:
        ref = importlib.resources.files(__package__).joinpath(filename)
        if ref.is_file():
            return ref.read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, TypeError, ValueError):
        pass
    return None


def _credentials_section_markdown(markdown: str) -> str:
    """Prefer the credential-setup portion of a full onboarding guide."""
    lines = markdown.splitlines()
    start = 0
    for index, line in enumerate(lines):
        if line.startswith("## What the client needs"):
            start = index
            break

    end = len(lines)
    deploy_heading = re.compile(r"^## Step \d+ — Deploy AWS infrastructure\b")
    for index in range(start + 1, len(lines)):
        if deploy_heading.match(lines[index]):
            end = index
            break

    section = "\n".join(lines[start:end]).strip()
    return section or markdown.strip()


def _render_inline(text: str) -> str:
    escaped = escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda match: (
            f'<a href="{escape(match.group(2), quote=True)}" target="_blank" '
            f'rel="noopener noreferrer">{escape(match.group(1))}</a>'
        ),
        escaped,
    )
    return escaped


def _render_markdown(markdown: str) -> str:
    lines = markdown.splitlines()
    html_parts: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    in_list = False
    in_code = False
    code_lines: list[str] = []
    table_rows: list[list[str]] = []
    in_table = False

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            html_parts.append(f"<p>{_render_inline(' '.join(paragraph))}</p>")
            paragraph = []

    def flush_list() -> None:
        nonlocal list_items, in_list
        if list_items:
            html_parts.append("<ul>" + "".join(f"<li>{_render_inline(item)}</li>" for item in list_items) + "</ul>")
            list_items = []
        in_list = False

    def flush_table() -> None:
        nonlocal table_rows, in_table
        if not table_rows:
            in_table = False
            return
        head, *body = table_rows
        rows_html = [
            "<thead><tr>"
            + "".join(f"<th>{_render_inline(cell)}</th>" for cell in head)
            + "</tr></thead>"
        ]
        if body:
            rows_html.append(
                "<tbody>"
                + "".join(
                    "<tr>" + "".join(f"<td>{_render_inline(cell)}</td>" for cell in row) + "</tr>"
                    for row in body
                )
                + "</tbody>"
            )
        html_parts.append('<div class="table-wrap"><table>' + "".join(rows_html) + "</table></div>")
        table_rows = []
        in_table = False

    for line in lines:
        if in_code:
            if line.strip().startswith("```"):
                html_parts.append(
                    "<pre><code>"
                    + escape("\n".join(code_lines))
                    + "</code></pre>"
                )
                code_lines = []
                in_code = False
            else:
                code_lines.append(line)
            continue

        if line.strip().startswith("```"):
            flush_paragraph()
            flush_list()
            flush_table()
            in_code = True
            code_lines = []
            continue

        if line.strip().startswith("|"):
            flush_paragraph()
            flush_list()
            in_table = True
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if all(set(cell) <= {"-", ":", " "} for cell in cells):
                continue
            table_rows.append(cells)
            continue
        if in_table:
            flush_table()

        if line.startswith("# "):
            flush_paragraph()
            flush_list()
            html_parts.append(f"<h1>{_render_inline(line[2:].strip())}</h1>")
            continue
        if line.startswith("## "):
            flush_paragraph()
            flush_list()
            html_parts.append(f"<h2>{_render_inline(line[3:].strip())}</h2>")
            continue
        if line.startswith("### "):
            flush_paragraph()
            flush_list()
            html_parts.append(f"<h3>{_render_inline(line[4:].strip())}</h3>")
            continue
        if line.strip() == "---":
            flush_paragraph()
            flush_list()
            html_parts.append("<hr />")
            continue
        if line.startswith("> "):
            flush_paragraph()
            flush_list()
            html_parts.append(f"<blockquote><p>{_render_inline(line[2:].strip())}</p></blockquote>")
            continue
        if re.match(r"^\d+\.\s+", line):
            flush_paragraph()
            if not in_list:
                in_list = True
            list_items.append(re.sub(r"^\d+\.\s+", "", line).strip())
            continue
        if line.startswith("- "):
            flush_paragraph()
            if not in_list:
                in_list = True
            list_items.append(line[2:].strip())
            continue

        if in_list and not line.strip():
            flush_list()
            continue
        if in_list:
            flush_list()

        if not line.strip():
            flush_paragraph()
            continue
        paragraph.append(line.strip())

    flush_paragraph()
    flush_list()
    flush_table()
    if in_code and code_lines:
        html_parts.append("<pre><code>" + escape("\n".join(code_lines)) + "</code></pre>")
    return "\n".join(html_parts)


@lru_cache(maxsize=16)
def render_connector_guide_html(source: str, *, credentials_only: bool = True) -> str:
    markdown = load_connector_guide_markdown(source)
    if not markdown:
        return '<p class="pack-card-lead">No setup guide is available for this connector yet.</p>'
    content = _credentials_section_markdown(markdown) if credentials_only else markdown.strip()
    return f'<div class="admin-connector-guide-content">{_render_markdown(content)}</div>'
