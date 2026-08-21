from __future__ import annotations

import os

from werkzeug.serving import run_simple

from meshflow.config import load_qbd_settings
from meshflow.qbd.qbwc.soap_app import QBWCSoapApp
from meshflow.qbd.sync.engine import SyncEngine


def create_wsgi_app(engine_instance: SyncEngine | None = None) -> QBWCSoapApp:
    return QBWCSoapApp(engine_instance or SyncEngine())


def main() -> None:
    settings = load_qbd_settings()
    host = os.getenv("QBWC_SOAP_HOST", "0.0.0.0")
    port = int(os.getenv("QBWC_SOAP_PORT", "8080"))
    app = create_wsgi_app(SyncEngine(settings))
    print(f"Meshflow QBD SOAP listening on http://{host}:{port}/")
    run_simple(host, port, app, use_reloader=False, use_debugger=False)


if __name__ == "__main__":
    main()
