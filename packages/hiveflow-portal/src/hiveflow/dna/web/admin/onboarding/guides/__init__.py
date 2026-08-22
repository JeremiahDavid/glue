"""Load connector credential setup guides from ``onboarding/`` markdown files."""

from __future__ import annotations

import importlib.resources
import re
from dataclasses import dataclass
from functools import lru_cache
from html import escape
from pathlib import Path

from hiveflow.dna.web.templating import render_template

# Source key → markdown filename under ``onboarding/`` (repo root) and packaged guides/.
CONNECTOR_GUIDE_FILES: dict[str, str] = {
    "dbc": "business-central.md",
    "qbo": "quickbooks-online.md",
    "qbd": "quickbooks-desktop.md",
}


@dataclass(frozen=True)
class ConnectorCredentialField:
    key: str
    label: str
    hint: str
    where_to_find: str
    input_type: str = "text"
    company_picker: bool = False


DBC_COMPANY_LOOKUP_FIELDS = (
    "BC_CLIENT_ID",
    "BC_CLIENT_SECRET",
    "BC_TENANT_ID",
    "BC_ENVIRONMENT_NAME",
)
DBC_LOAD_COMPANIES_DISABLED_TITLE = (
    "Fill in the four fields above (Entra client id, client secret, tenant id, and BC environment name) "
    "to load companies."
)
DBC_LOAD_COMPANIES_ENABLED_TITLE = "Load companies from this BC environment"

DBC_REQUIRED_PERMISSION_SETS = (
    "ADD RELATED FIELDS",
    "D365 AUTOMATION",
    "D365 BUS FULL ACCESS",
)


def dbc_permission_sets_requirement_html() -> str:
    return render_template(
        "admin/_dbc_permission_sets.html", names=DBC_REQUIRED_PERMISSION_SETS
    )


CONNECTOR_CREDENTIAL_FIELDS: dict[str, tuple[ConnectorCredentialField, ...]] = {
    "dbc": (
        ConnectorCredentialField(
            "BC_CLIENT_ID",
            "Entra client id",
            "Microsoft Entra application (client) id authorized for Business Central API access.",
            "Entra ID → **App registrations** → your app → **Application (client) ID**",
        ),
        ConnectorCredentialField(
            "BC_CLIENT_SECRET",
            "Entra client secret",
            "Client secret for the Entra app.",
            "Entra ID → **App registrations** → **Certificates & secrets** → new secret → copy the **Value** (not Secret ID)",
            "password",
        ),
        ConnectorCredentialField(
            "BC_TENANT_ID",
            "Entra tenant id",
            "Microsoft Entra directory id that owns the Business Central environment.",
            "Entra ID → **App registrations** → **Directory (tenant) ID**",
        ),
        ConnectorCredentialField(
            "BC_ENVIRONMENT_NAME",
            "BC environment name",
            "Business Central environment name, such as Production or a named sandbox.",
            "BC Admin Center → **Environments** — use the exact name shown (e.g. `Production`, `Sandbox`)",
        ),
        ConnectorCredentialField(
            "BC_COMPANY_ID",
            "BC company",
            "GUID of the Business Central company to sync into the lake.",
            "Load companies after the four Entra fields above are filled, then select the target company.",
            company_picker=True,
        ),
    ),
    "qbo": (
        ConnectorCredentialField(
            "QBO_CLIENT_ID",
            "QBO client id",
            "Intuit developer application client id used for OAuth and API access.",
            "Intuit Developer → your app → **Keys & credentials** → **Client ID** (Development or Production tier)",
        ),
        ConnectorCredentialField(
            "QBO_CLIENT_SECRET",
            "QBO client secret",
            "Intuit app client secret from the Developer portal.",
            "Intuit Developer → **Keys & credentials** → **Client Secret** for the same tier as the Client ID",
            "password",
        ),
        ConnectorCredentialField(
            "QBO_ENVIRONMENT",
            "QBO environment",
            "Intuit API tier: sandbox for testing or production for live company data.",
            "Set to `sandbox` when using Development keys, or `production` when using Production keys — must match the Intuit app tier",
        ),
        ConnectorCredentialField(
            "QBO_REDIRECT_URI",
            "QBO redirect URI",
            "OAuth redirect URL registered in the Intuit developer portal for this app.",
            "Intuit Developer → app → **Redirect URIs** — use the same URI registered there (typically `http://localhost:8080/callback`)",
        ),
    ),
    "qbd": (
        ConnectorCredentialField(
            "QBD_QBWC_USERNAME",
            "QBWC username",
            "Username QuickBooks Web Connector uses to authenticate to the ingest SOAP endpoint.",
            "Choose a username — it must match the login entered in QuickBooks Web Connector when installing the `.qwc` file",
        ),
        ConnectorCredentialField(
            "QBD_QBWC_PASSWORD",
            "QBWC password",
            "Password paired with the QBWC username for SOAP authentication.",
            "Choose a strong password — it must match the password entered in QuickBooks Web Connector",
            "password",
        ),
        ConnectorCredentialField(
            "QBWC_SOAP_URL",
            "SOAP URL (after ingest deploy)",
            "SOAP endpoint URL shown after stack deploy on this onboarding page.",
            "After **Deploy stacks** on this page, copy the SOAP endpoint URL from the ingest stack output (`QbdSoapUrl`)",
        ),
        ConnectorCredentialField(
            "QBD_COMPANY_NAME",
            "Company name",
            "QuickBooks company file name as shown in Web Connector.",
            "QuickBooks Desktop — the company file name as shown in Web Connector (must match the authorized company)",
        ),
    ),
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
    """Extract the operator-facing credential guide (excludes backend/deploy content)."""
    start_marker = "<!-- credentials-guide-start -->"
    end_marker = "<!-- credentials-guide-end -->"
    start = markdown.find(start_marker)
    end = markdown.find(end_marker)
    if start != -1 and end != -1 and end > start:
        return markdown[start + len(start_marker) : end].strip()
    return ""


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


_CREDENTIAL_FIELD_MARKER = re.compile(r"<!--\s*credential-field:([A-Z0-9_]+)\s*-->")


def render_credential_inline_input(field: ConnectorCredentialField, *, form_id: str) -> str:
    field_id = f"{form_id}-guide-{field.key.lower()}"
    return render_template("admin/_credential_inline_input.html", field_id=field_id, field=field)


def _expand_credential_field_markers(
    text: str,
    fields_by_key: dict[str, ConnectorCredentialField],
    form_id: str,
) -> str:
    parts: list[str] = []
    last = 0
    for match in _CREDENTIAL_FIELD_MARKER.finditer(text):
        if match.start() > last:
            parts.append(_render_inline(text[last : match.start()]))
        field = fields_by_key.get(match.group(1))
        if field is not None and not field.company_picker:
            parts.append(render_credential_inline_input(field, form_id=form_id))
        last = match.end()
    if last < len(text):
        parts.append(_render_inline(text[last:]))
    return "".join(parts) if parts else _render_inline(text)


def render_credential_summary_fields(
    source: str,
    *,
    form_id: str,
    values: dict[str, str] | None = None,
) -> str:
    fields = CONNECTOR_CREDENTIAL_FIELDS.get(source.strip().lower(), ())
    if not fields:
        return ""
    saved_values = values or {}
    lookup_ready = all(str(saved_values.get(key, "")).strip() for key in DBC_COMPANY_LOOKUP_FIELDS)
    load_title = DBC_LOAD_COMPANIES_ENABLED_TITLE if lookup_ready else DBC_LOAD_COMPANIES_DISABLED_TITLE
    items = []
    for field in fields:
        field_id = f"{form_id}-main-{field.key.lower()}"
        saved_value = str(saved_values.get(field.key, "")).strip()
        items.append(
            {
                "field": field,
                "field_id": field_id,
                "saved_value": saved_value,
                "lookup_ready": lookup_ready,
                "load_title": load_title,
            }
        )
    return render_template("admin/_credential_summary_fields.html", items=items)


def _credential_fields_by_key(source: str) -> dict[str, ConnectorCredentialField]:
    return {field.key: field for field in CONNECTOR_CREDENTIAL_FIELDS.get(source.strip().lower(), ())}


def _render_markdown(markdown: str, *, source: str = "", form_id: str = "") -> str:
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
            html_parts.append(f"<p>{render_text(' '.join(paragraph))}</p>")
            paragraph = []

    def flush_list() -> None:
        nonlocal list_items, in_list
        if list_items:
            html_parts.append(
                "<ul>"
                + "".join(f"<li>{render_text(item)}</li>" for item in list_items)
                + "</ul>"
            )
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

    fields_by_key = _credential_fields_by_key(source) if source and form_id else {}

    def render_text(text: str) -> str:
        if fields_by_key and form_id and _CREDENTIAL_FIELD_MARKER.search(text):
            return _expand_credential_field_markers(text, fields_by_key, form_id)
        return _render_inline(text)

    for line in lines:
        if _CREDENTIAL_FIELD_MARKER.fullmatch(line.strip()):
            continue

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
            html_parts.append(f"<blockquote><p>{render_text(line[2:].strip())}</p></blockquote>")
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


def _credential_field_lookup_markdown(source: str) -> str:
    fields = CONNECTOR_CREDENTIAL_FIELDS.get(source.strip().lower(), ())
    if not fields:
        return ""
    rows = "\n".join(
        f"| **{field.label}** | {field.where_to_find} |"
        for field in fields
    )
    return (
        "## Where to find each input\n\n"
        "| Form field | Where to find it |\n"
        "|---|---|\n"
        f"{rows}"
    )


@lru_cache(maxsize=16)
def render_connector_guide_html(source: str, *, credentials_only: bool = True) -> str:
    markdown = load_connector_guide_markdown(source)
    if not markdown:
        return '<p class="pack-card-lead">No setup guide is available for this connector yet.</p>'
    content = _credentials_section_markdown(markdown) if credentials_only else markdown.strip()
    lookup = _credential_field_lookup_markdown(source)
    if lookup:
        content = f"{content}\n\n{lookup}".strip()
    form_id = f"connector-secrets-{source.strip().lower()}"
    return (
        f'<div class="admin-connector-guide-content">'
        f"{_render_markdown(content, source=source, form_id=form_id)}"
        f"</div>"
    )
