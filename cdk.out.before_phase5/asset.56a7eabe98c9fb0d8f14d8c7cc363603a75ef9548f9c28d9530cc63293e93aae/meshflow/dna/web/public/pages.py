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


def _platform_emblem(*, icon: str, label: str, variant: str, ai: bool = False) -> str:
    ai_html = '<span class="platform-emblem-ai">AI</span>' if ai else ""
    return f"""
    <div class="platform-layer-emblem {variant}">
      <div class="platform-emblem-icon">{ai_html}{icon}</div>
      <span class="platform-emblem-name">{label}</span>
    </div>"""


def _engine_icon(*, stroke: str, fill: str, overlay: str = "") -> str:
    return f"""
      <svg class="platform-engine" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M5 17 8.5 6 11.5 8 10 17Z" fill="{fill}" stroke="{stroke}" stroke-width="1.5" stroke-linejoin="round"/>
        <path d="M19 17 15.5 6 12.5 8 14 17Z" fill="{fill}" stroke="{stroke}" stroke-width="1.5" stroke-linejoin="round"/>
        <path d="M5 17c2.2 3 4.5 4.5 7 4.5s4.8-1.5 7-4.5" stroke="{stroke}" stroke-width="1.5" stroke-linecap="round"/>
        <circle cx="12" cy="15.5" r="1.8" fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>
        {overlay}
      </svg>"""


def _flow_card(*, href: str, title: str, subtitle: str = "", icon: str = "", variant: str = "", extra: str = "", ai: bool = False) -> str:
    ai_badge = '<span class="flow-card-ai">AI</span>' if ai else ""
    sub_html = f'<span class="flow-card-sub">{subtitle}</span>' if subtitle else ""
    return f"""
    <a class="flow-card {variant}" href="{href}">
      <span class="flow-card-icon">{ai_badge}{icon}</span>
      <span class="flow-card-title">{title}</span>
      {sub_html}
      {extra}
    </a>"""


def render_platform(request: Request) -> Response:
    arrow_right = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>'
    arrow_down = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 5v14M6 13l6 6 6-6"/></svg>'

    icon_sources = """
      <svg viewBox="0 0 24 24" fill="none" stroke="#7dd3fc" stroke-width="1.6" aria-hidden="true">
        <rect x="3" y="4" width="7" height="7" rx="1.5"/><rect x="14" y="4" width="7" height="7" rx="1.5"/>
        <rect x="3" y="13" width="7" height="7" rx="1.5"/><rect x="14" y="13" width="7" height="7" rx="1.5"/>
      </svg>"""
    icon_lake = """
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M3 12 L8 7 L12 10 L16 6 L21 11" stroke="#64748b" stroke-width="1.4" stroke-linejoin="round"/>
        <ellipse cx="12" cy="16" rx="9.5" ry="3.2" fill="rgba(7,155,232,0.18)" stroke="#079be8" stroke-width="1.4"/>
        <path d="M5 16.2 Q9 14.8 12 16.2 T19 16.2" stroke="#38bdf8" stroke-width="1.2" fill="none" opacity="0.8"/>
        <path d="M6.5 17.4 Q10 16.2 12 17.4 T17.5 17.4" stroke="#7dd3fc" stroke-width="1" fill="none" opacity="0.55"/>
      </svg>"""
    icon_portal = """
      <svg viewBox="0 0 24 24" fill="none" stroke="#ffb800" stroke-width="1.6" aria-hidden="true">
        <rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M8 4v5"/>
      </svg>"""
    icon_change = """
      <svg viewBox="0 0 24 24" fill="none" stroke="#99f6e4" stroke-width="1.6" aria-hidden="true">
        <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5z"/>
        <path d="M14 3v5h5M9 13h6M9 17h4"/>
      </svg>"""
    icon_engine_dna = _engine_icon(
        stroke="#5eead4",
        fill="rgba(20,184,166,0.15)",
    )
    icon_engine_reporting = _engine_icon(
        stroke="#fcd34d",
        fill="rgba(245,158,11,0.15)",
    )

    emblem_sources = _platform_emblem(icon=icon_sources, label="Source systems", variant="sources")
    emblem_lake = _platform_emblem(icon=icon_lake, label="Data lake", variant="lake")
    emblem_dna = _platform_emblem(icon=icon_engine_dna, label="DNA Engine", variant="dna", ai=True)
    emblem_reporting = _platform_emblem(icon=icon_engine_reporting, label="Reporting Engine", variant="reporting", ai=True)
    emblem_portal = _platform_emblem(icon=icon_portal, label="Client portal", variant="portal")

    lake_tiers = """
      <span class="flow-tier-pills">
        <span class="bronze">Bronze</span>
        <span class="silver">Silver</span>
        <span class="gold">Gold</span>
      </span>"""

    body = page_header(
        "Platform",
        "Four governed layers — from raw source data to client-ready reporting — with clear separation between data refresh and semantic change.",
        eyebrow="How it works",
    )
    body += f"""
    <section class="platform-overview">
      <div class="platform-flow">
        <div class="platform-flow-title">How data moves through HiveFlowAI</div>
        <div class="platform-flow-visual">
          <div class="flow-band refresh">
            <p class="flow-band-label">Scheduled refresh</p>
            <div class="flow-band-track">
              {_flow_card(href="#platform-sources", title="Source systems", subtitle="BC · QBO · Excel", icon=icon_sources, variant="sources")}
              <span class="flow-arrow" aria-hidden="true">→</span>
              {_flow_card(href="#platform-lake", title="Data lake", icon=icon_lake, variant="lake", extra=lake_tiers)}
              <span class="flow-bridge-pill">Nightly data</span>
              {_flow_card(href="#platform-portal", title="Client portal", subtitle="Live metrics", icon=icon_portal, variant="portal")}
            </div>
          </div>

          <svg class="flow-bridge-svg" viewBox="0 0 720 36" aria-hidden="true">
            <path d="M 268 34 C 268 18 292 6 318 6" stroke="#5eead4" stroke-width="1.5" stroke-dasharray="5 4" fill="none" opacity="0.55"/>
            <path d="M 452 34 C 452 18 478 6 598 6" stroke="#fcd34d" stroke-width="1.5" stroke-dasharray="5 4" fill="none" opacity="0.55"/>
            <text x="248" y="32" fill="#5eead4" font-size="10" font-family="system-ui,sans-serif" opacity="0.85">writes gold</text>
            <text x="468" y="32" fill="#fcd34d" font-size="10" font-family="system-ui,sans-serif" opacity="0.85">writes layout</text>
          </svg>

          <div class="flow-band change">
            <p class="flow-band-label">Change request updates</p>
            <div class="flow-band-track">
              {_flow_card(href="#platform-governance", title="Change request", subtitle="Doc update · review", icon=icon_change, variant="change")}
              <span class="flow-arrow" aria-hidden="true">→</span>
              <div class="flow-engines">
                {_flow_card(href="#platform-dna", title="DNA Engine", subtitle="Semantic logic", icon=icon_engine_dna, variant="dna", ai=True)}
                <span class="flow-parallel-pill">parallel</span>
                {_flow_card(href="#platform-reporting", title="Reporting Engine", subtitle="Portal layout", icon=icon_engine_reporting, variant="reporting", ai=True)}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="platform-layers">
      <article class="platform-layer" id="platform-sources" data-layer="1">
        <div class="platform-layer-visual">
          {emblem_sources}
          <div class="mini-lake-sources" style="margin-bottom:0">
            <div class="mini-source">BC</div>
            <div class="mini-source">QB</div>
            <div class="mini-source">XL</div>
            <div class="mini-source">OPS</div>
          </div>
        </div>
        <div class="platform-layer-body">
          <div class="platform-layer-badge"><span>1</span> Source systems</div>
          <h3>Connect ERP, accounting, and ops</h3>
          <p>Business Central, QuickBooks, Excel, and operational systems connect into HiveFlowAI on a governed ingest schedule. Each source lands in tenant-scoped bronze storage with full lineage.</p>
          <div class="platform-layer-tags">
            <span class="platform-tag">Multi-source</span>
            <span class="platform-tag">Scheduled sync</span>
            <span class="platform-tag">Immutable extracts</span>
          </div>
        </div>
      </article>

      <div class="platform-layer-connector">{arrow_down}</div>

      <article class="platform-layer" id="platform-lake" data-layer="2">
        <div class="platform-layer-visual">
          {emblem_lake}
          <div class="mini-lake-stack">
            <div class="mini-lake-tier bronze"><span>Bronze</span><div class="bar"><i></i></div></div>
            <div class="mini-lake-tier silver"><span>Silver</span><div class="bar"><i></i></div></div>
            <div class="mini-lake-tier gold"><span>Gold</span><div class="bar"><i></i></div></div>
          </div>
        </div>
        <div class="platform-layer-body">
          <div class="platform-layer-badge"><span>2</span> Data lake</div>
          <h3>Three layers — one governed store</h3>
          <p>Tenant-scoped storage from raw ingest through certified KPI tables. Scheduled refresh updates bronze and silver; gold updates on governed change requests.</p>
          <div class="platform-lake-sections">
            <section class="lake-section bronze" id="platform-bronze">
              <h4>Bronze</h4>
              <p>Immutable raw extracts from every connected source — full lineage, append-only landing zone.</p>
            </section>
            <section class="lake-section silver" id="platform-silver">
              <h4>Silver</h4>
              <p>Consolidated, catalogued tables — cleaned, typed, and SQL-ready for downstream engines.</p>
            </section>
            <section class="lake-section gold" id="platform-gold">
              <h4>Gold</h4>
              <p>Certified KPI tables written by the DNA Engine on change requests — the semantic source of truth for reporting.</p>
            </section>
          </div>
          <div class="platform-layer-tags">
            <span class="platform-tag">Tenant-isolated</span>
            <span class="platform-tag">Catalog + SQL</span>
            <span class="platform-tag">Nightly refresh</span>
          </div>
        </div>
      </article>

      <div class="platform-layer-connector">{arrow_down}</div>

      <article class="platform-layer" id="platform-dna" data-layer="3">
        <div class="platform-layer-visual">
          {emblem_dna}
          <div class="mini-pipeline">
            <div class="mini-pipe-node">Customer<br>docs</div>
            <span class="mini-pipe-arrow">→</span>
            <div class="mini-pipe-node highlight">DNA<br>file</div>
            <span class="mini-pipe-arrow">→</span>
            <div class="mini-pipe-node">Compile</div>
          </div>
          <div class="mini-gold-table">
            <header>Gold · certified KPIs</header>
            <div class="rows"><div class="row"></div><div class="row"></div><div class="row"></div></div>
          </div>
        </div>
        <div class="platform-layer-body">
          <div class="platform-layer-badge"><span>3</span> DNA Engine · AI</div>
          <h3>Governed semantics from documentation</h3>
          <p>Customer documentation becomes a version-controlled DNA file. AI generates semantic SQL/Python; compile and publish <strong>writes certified gold tables</strong> to the data lake. Runs on requirement updates — not on every data refresh.</p>
          <div class="platform-layer-tags">
            <span class="platform-tag">Version-controlled</span>
            <span class="platform-tag">Human-approved</span>
            <span class="platform-tag">Gold outputs</span>
          </div>
        </div>
      </article>

      <div class="platform-parallel">
        <div class="platform-parallel-card dna">
          <div class="platform-parallel-emblem">{icon_engine_dna}</div>
          <strong>DNA Engine</strong>
          <span>Calculations &amp; KPI definitions</span>
        </div>
        <div class="platform-parallel-label">Parallel tracks</div>
        <div class="platform-parallel-card reporting">
          <div class="platform-parallel-emblem">{icon_engine_reporting}</div>
          <strong>Reporting Engine</strong>
          <span>Layout &amp; presentation</span>
        </div>
      </div>

      <article class="platform-layer" id="platform-reporting" data-layer="4">
        <div class="platform-layer-visual">
          {emblem_reporting}
          <div class="mini-pipeline">
            <div class="mini-pipe-node">Reporting<br>docs</div>
            <span class="mini-pipe-arrow">→</span>
            <div class="mini-pipe-node highlight">Layout<br>file</div>
            <span class="mini-pipe-arrow">→</span>
            <div class="mini-pipe-node">Portal<br>pages</div>
          </div>
          <div class="mini-portal-grid" style="margin-top:0.55rem">
            <div class="mini-portal-kpi"><div class="label">Revenue</div><div class="val gold">$2.4M</div></div>
            <div class="mini-portal-kpi"><div class="label">Margin</div><div class="val teal">18.2%</div></div>
            <div class="mini-portal-chart"><span></span><span></span><span></span><span></span><span></span></div>
          </div>
        </div>
        <div class="platform-layer-body">
          <div class="platform-layer-badge"><span>4</span> Reporting Engine · AI</div>
          <h3>Presentation without touching calculations</h3>
          <p>Reporting documentation becomes a version-controlled layout file. AI generates portal HTML/Python bound to gold outputs and <strong>writes updates directly to the client portal</strong> — chart and page changes without redefining KPIs.</p>
          <div class="platform-layer-tags">
            <span class="platform-tag">Bound to gold</span>
            <span class="platform-tag">Independent layout</span>
            <span class="platform-tag">Branded views</span>
          </div>
        </div>
      </article>

      <div class="platform-layer-connector">{arrow_down}</div>

      <article class="platform-layer" id="platform-portal" data-layer="5">
        <div class="platform-layer-visual">
          {emblem_portal}
          <div class="mini-delivery">
            <div class="mini-delivery-row"><span class="dot live"></span> Scheduled refresh updates live data</div>
            <div class="mini-delivery-row"><span class="dot pinned"></span> Logic &amp; layout pinned until promoted</div>
            <div class="mini-delivery-row"><span class="dot live"></span> Read-only client portal per tenant</div>
          </div>
        </div>
        <div class="platform-layer-body">
          <div class="platform-layer-badge"><span>5</span> Client portal</div>
          <h3>Secure delivery to every stakeholder</h3>
          <p>HiveFlowAI serves read-only views from the semantic layer. Scheduled refresh updates data; pinned logic and layout until the customer promotes a doc change.</p>
          <div class="platform-layer-tags">
            <span class="platform-tag">Per-client branding</span>
            <span class="platform-tag">Read-only</span>
            <span class="platform-tag">Governed updates</span>
          </div>
        </div>
      </article>
    </section>

    <section class="section" id="platform-governance">
      <div class="section-title">Governance model</div>
      <div class="platform-governance-grid">
        <article class="platform-gov-card">
          <h3>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#99f6e4" stroke-width="1.8" aria-hidden="true">
              <circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>
            </svg>
            Scheduled data refresh
          </h3>
          <div class="platform-gov-visual">
            <div class="platform-gov-step">Sources sync</div>
            <span class="platform-gov-arrow">→</span>
            <div class="platform-gov-step active">Lake updates</div>
            <span class="platform-gov-arrow">→</span>
            <div class="platform-gov-step active">Portal data refreshes</div>
          </div>
          <p>Overnight ingest refreshes bronze and silver layers. Gold tables and portal views pick up new data automatically — semantic logic and layout stay pinned.</p>
        </article>
        <article class="platform-gov-card">
          <h3>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fcd34d" stroke-width="1.8" aria-hidden="true">
              <path d="M12 3l7 4v5c0 4.5-3 8-7 9-4-1-7-4.5-7-9V7l7-4z"/><path d="M9 12l2 2 4-4"/>
            </svg>
            Governed change requests
          </h3>
          <div class="platform-gov-visual">
            <div class="platform-gov-step">Doc update</div>
            <span class="platform-gov-arrow">→</span>
            <div class="platform-gov-step active">Human review</div>
            <span class="platform-gov-arrow">→</span>
            <div class="platform-gov-step active">Promote to prod</div>
          </div>
          <p>DNA and Reporting files are version-controlled. AI agents draft from customer docs; humans approve before codegen runs. No silent AI drift.</p>
        </article>
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
          <div class="pricing-offer"><span class="badge accent">Current offer</span></div>
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
          <div class="pricing-offer" aria-hidden="true"></div>
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
          <div class="pricing-offer" aria-hidden="true"></div>
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
