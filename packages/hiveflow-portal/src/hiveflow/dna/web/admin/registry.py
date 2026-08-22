"""Platform admin job registry — source-agnostic invoke + monitor catalog.

v1 registers Business Central (dbc) source-docs jobs. Add future connectors by
appending AdminJob entries and granting the admin Lambda IAM/env for those functions.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AdminJob:
    """One runnable / monitorable platform job."""

    id: str
    source: str
    group: str
    title: str
    description: str
    function_env: str
    default_payload: dict[str, Any] = field(default_factory=dict)
    follow_ons: tuple[str, ...] = ()

    def function_name(self) -> str:
        return os.getenv(self.function_env, "").strip()


def registered_admin_jobs() -> list[AdminJob]:
    """Return all platform admin jobs (extend this list for new data sources)."""
    return [
        AdminJob(
            id="dbc.source_docs.scrape",
            source="dbc",
            group="Source documentation",
            title="Scrape MS Learn properties",
            description=(
                "Scrape Microsoft Learn APV2 Properties tables into "
                "entity_properties.yaml. On success, async-invokes relationships and tags."
            ),
            function_env="HIVEFLOW_SOURCE_DOCS_SCRAPE_FUNCTION",
            default_payload={"source": "dbc", "delay_seconds": 0.35},
            follow_ons=("dbc.source_docs.relationships", "dbc.source_docs.tags"),
        ),
        AdminJob(
            id="dbc.source_docs.relationships",
            source="dbc",
            group="Source documentation",
            title="Derive PK/FK relationships",
            description="Rebuild entity_relationships.yaml from the published properties catalog.",
            function_env="HIVEFLOW_SOURCE_DOCS_RELATIONSHIPS_FUNCTION",
            default_payload={"source": "dbc"},
        ),
        AdminJob(
            id="dbc.source_docs.tags",
            source="dbc",
            group="Source documentation",
            title="Generate property tags",
            description=(
                "Rebuild entity_property_tags.yaml (field-specific + foreign-key tags) "
                "from the published properties catalog."
            ),
            function_env="HIVEFLOW_SOURCE_DOCS_TAGS_FUNCTION",
            default_payload={"source": "dbc"},
        ),
        # Future sources (qbo / qbd / …): register AdminJob entries here.
    ]


def get_admin_job(job_id: str) -> AdminJob | None:
    needle = str(job_id or "").strip()
    if not needle:
        return None
    for job in registered_admin_jobs():
        if job.id == needle:
            return job
    return None


def jobs_grouped_by_source() -> list[tuple[str, list[tuple[str, list[AdminJob]]]]]:
    """[(source, [(group, [jobs…]), …]), …] preserving registry order."""
    by_source: dict[str, dict[str, list[AdminJob]]] = {}
    source_order: list[str] = []
    group_order: dict[str, list[str]] = {}
    for job in registered_admin_jobs():
        if job.source not in by_source:
            by_source[job.source] = {}
            source_order.append(job.source)
            group_order[job.source] = []
        groups = by_source[job.source]
        if job.group not in groups:
            groups[job.group] = []
            group_order[job.source].append(job.group)
        groups[job.group].append(job)
    return [
        (source, [(group, by_source[source][group]) for group in group_order[source]])
        for source in source_order
    ]


def source_display_name(source: str) -> str:
    labels = {
        "dbc": "Business Central (DBC)",
        "qbo": "QuickBooks Online",
        "qbd": "QuickBooks Desktop",
    }
    key = str(source or "").strip().lower()
    return labels.get(key, key.upper() if key else "Unknown")
