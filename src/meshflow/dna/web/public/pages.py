"""Public marketing pages for HiveFlowAI."""

from __future__ import annotations

from werkzeug.wrappers import Request, Response

from meshflow.dna.web.theme import escape, page_header, render_public_page

PUBLIC_NAV = (
    ("/", "Home"),
    ("/platform", "Platform"),
    ("/pricing", "Pricing"),
    ("/portal/login", "Client login"),
)


def _public_response(request: Request, *, title: str, active_path: str, body: str) -> Response:
    url = lambda path: f"{request.script_root}{path if path.startswith('/') else f'/{path}'}"
    return Response(
        render_public_page(title=title, active_path=active_path, body=body, nav_links=PUBLIC_NAV, url=url),
        mimetype="text/html",
    )


def render_landing(request: Request) -> Response:
    url = lambda path: f"{request.script_root}{path if path.startswith('/') else f'/{path}'}"
    body = f"""
    <section class="hero">
      <div class="hero-copy">
        <div class="eyebrow">Operational intelligence</div>
        <h1>Connect your systems.<br>Unify your data.<br><span class="gradient-text">Reveal what matters.</span></h1>
        <p class="hero-subtitle">
          HiveFlowAI turns ERP, accounting, and operational data into governed metrics and
          client-ready reporting — with version-controlled semantics you can trust.
        </p>
        <div class="hero-actions">
          <a class="button primary" href="{escape(url("/pricing"))}">View pricing</a>
          <a class="button secondary" href="{escape(url("/portal/login"))}">Client login</a>
        </div>
      </div>
      <div class="hero-panel card">
        <div class="section-title">What you get</div>
        <ul class="feature-list">
          <li><strong>Data lake</strong><span>All your source data consolidated in one tenant environment</span></li>
          <li><strong>Semantic engine</strong><span>Human-validated KPI definitions with versioned logic</span></li>
          <li><strong>Reporting portal</strong><span>Branded client views that update on governed change requests</span></li>
        </ul>
      </div>
    </section>

    <section class="section">
      <div class="section-title">Built for operators and controllers</div>
      <div class="grid">
        <article class="card">
          <h3>No shadow spreadsheets</h3>
          <p>Every KPI links to an approved definition pack — not ad-hoc SQL or forked BI logic.</p>
        </article>
        <article class="card">
          <h3>Two-layer delivery</h3>
          <p>Public product information for prospects, plus a secure portal for each client's reporting.</p>
        </article>
        <article class="card">
          <h3>Update without drift</h3>
          <p>Reporting layout and semantics change only through governed update requests — not silent AI drift.</p>
        </article>
      </div>
    </section>
    """
    return _public_response(request, title="Home", active_path="/", body=body)


def render_platform(request: Request) -> Response:
    body = page_header(
        "Platform",
        "HiveFlowAI combines ingestion, governed semantics, and a client reporting portal on one stack.",
        eyebrow="How it works",
    )
    body += """
    <section class="section">
      <div class="grid">
        <article class="card">
          <div class="section-title">Layer 1 · Data lake</div>
          <p>Bronze ingest and silver consolidation from Business Central and adjunct systems into tenant-scoped storage and catalog tables.</p>
        </article>
        <article class="card">
          <div class="section-title">Layer 2 · DNA Engine</div>
          <p>Customer documentation becomes a version-controlled DNA file. AI generates semantic SQL/Python; compile and publish materializes certified gold tables. Runs on requirement updates — not on every data refresh.</p>
        </article>
        <article class="card">
          <div class="section-title">Layer 3 · Reporting Engine</div>
          <p>Reporting documentation becomes a version-controlled layout file. AI generates portal HTML/Python bound to gold outputs. Parallel to DNA — chart and page changes without touching calculations.</p>
        </article>
        <article class="card">
          <div class="section-title">Layer 4 · Client portal</div>
          <p>HiveFlowAI serves read-only views from the semantic layer. Scheduled refresh updates data; pinned logic and layout until the customer promotes a doc change.</p>
        </article>
      </div>
    </section>
    <section class="section">
      <div class="card">
        <div class="section-title">Governance model</div>
        <ul class="plain">
          <li>DNA and Reporting files are version-controlled — changes require explicit promotion to production.</li>
          <li>AI agents draft from customer docs; humans approve before codegen runs.</li>
          <li>Scheduled refresh updates data only; pinned semantic logic and portal layout until promoted.</li>
        </ul>
      </div>
    </section>
    """
    return _public_response(request, title="Platform", active_path="/platform", body=body)


def render_pricing(request: Request) -> Response:
    body = page_header(
        "Pricing",
        "DNA is in beta — early customers help shape the product. GA pricing is the target once the platform is production-ready.",
        eyebrow="Plans",
    )
    body += """
    <section class="section">
      <div class="pricing-grid">
        <article class="card pricing-card featured">
          <div class="section-title">HiveFlowAI · DNA Beta</div>
          <div class="badge accent" style="display:inline-block;margin-bottom:0.75rem">Current offer</div>
          <div class="price">$0 <span>implementation</span></div>
          <div class="price-sub">$100 / month</div>
          <ul class="plain">
            <li>Starter KPI library on your Business Central data</li>
            <li>Governed definition pack and client reporting portal</li>
            <li>Direct product feedback channel — limited beta slots</li>
          </ul>
        </article>
        <article class="card pricing-card">
          <div class="section-title">HiveFlowAI · DNA (GA target)</div>
          <div class="price">$5,000 <span>implementation</span></div>
          <div class="price-sub">$1,000 / month</div>
          <ul class="plain">
            <li>Self-service KPIs and reports via documented requirements</li>
            <li>Version-controlled DNA + Reporting engines</li>
            <li>Target pricing — subject to delivery cost at scale</li>
          </ul>
        </article>
        <article class="card pricing-card">
          <div class="section-title">Meshflow Signals</div>
          <div class="price">$4,000 <span>activation</span></div>
          <div class="price-sub">$600 / month</div>
          <ul class="plain">
            <li>Ranked exception queues and operational briefings</li>
            <li>Up to 3 systems and 5 named users</li>
            <li>Best for HVAC, thin-stack, and to-do-first workflows</li>
          </ul>
        </article>
      </div>
    </section>
    <section class="section">
      <div class="card">
        <div class="section-title">Phased rollout</div>
        <p style="color:var(--text-muted)">
          We start at <strong>$100/month</strong> during beta to learn with real customers.
          Target general-availability pricing is <strong>$5,000 implementation + $1,000/month</strong>
          once validation workflow, portal, and starter packs are production-ready.
          Beta customers receive notice before any price change.
        </p>
      </div>
    </section>
    <section class="section">
      <div class="card">
        <div class="section-title">Trial</div>
        <p style="color:var(--text-muted)">Standard Meshflow trial: free implementation plus a 2-week evaluation before conversion. DNA may enroll directly at beta pricing or run a starter-KPI evaluation first.</p>
      </div>
    </section>
    """
    return _public_response(request, title="Pricing", active_path="/pricing", body=body)
