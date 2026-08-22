"""Marketing site route registration — extracted from app.py (Phase 1 split).

Genuinely marketing-only: no portal or admin imports, no closure state. These
routes render for both HIVEFLOW_UI_MODE=global (the shared marketing + login
hub) and HIVEFLOW_UI_MODE=full (local dev).
"""

from __future__ import annotations

from werkzeug.routing import Rule
from werkzeug.wrappers import Request, Response

from hiveflow.dna.web.public.pages import render_landing, render_platform, render_pricing

def build_public_rules() -> list[Rule]:
    # Werkzeug Rule instances bind to a single Map, so create_app() needs a
    # fresh list every call — a module-level list of pre-built Rules would
    # raise "already bound to map" the second time create_app() runs in the
    # same process (e.g. across tests).
    return [
        Rule("/", endpoint="landing"),
        Rule("/platform", endpoint="platform"),
        Rule("/pricing", endpoint="pricing"),
    ]


def on_landing(request: Request) -> Response:
    return render_landing(request)


def on_platform(request: Request) -> Response:
    return render_platform(request)


def on_pricing(request: Request) -> Response:
    return render_pricing(request)


PUBLIC_ENDPOINTS = {
    "landing": on_landing,
    "platform": on_platform,
    "pricing": on_pricing,
}
