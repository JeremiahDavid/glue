"""DNA — Semantic Engine: versioned definition packs → certified gold tables."""

from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)

# Import submodules directly (e.g. meshflow.dna.compile) — avoid eager imports here
# so lightweight imports like meshflow.dna.web.domain_names do not load the full engine.
