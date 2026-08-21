"""Shared Jinja2 environment for the web presentation layer."""

from __future__ import annotations

from jinja2 import Environment, PackageLoader, select_autoescape

_env = Environment(
    loader=PackageLoader("meshflow.dna.web", "templates"),
    autoescape=select_autoescape(["html", "jinja", "jinja2"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_template(template_name: str, **context: object) -> str:
    return _env.get_template(template_name).render(**context)
