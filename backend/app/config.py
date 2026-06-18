"""Runtime configuration, read from the environment.

APoc keeps configuration tiny on purpose — it should run with nothing but an
``ANTHROPIC_API_KEY`` set.
"""

from __future__ import annotations

import os
from pathlib import Path

# Load the nearest .env (walking up from this file) so keys placed in the repo
# root .env are picked up without exporting them. Existing env vars win.
try:
    from dotenv import load_dotenv

    for _parent in Path(__file__).resolve().parents:
        _env = _parent / ".env"
        if _env.exists():
            load_dotenv(_env, override=False)
            break
except Exception:  # dotenv optional
    pass

# Where the SQLite file lives. Defaults next to the backend package.
DB_PATH = Path(os.environ.get("APOC_DB_PATH", Path(__file__).resolve().parent.parent / "apoc.db"))

# Provider selection. Explicit APOC_PROVIDER wins; otherwise prefer DeepSeek when
# a DeepSeek key is present (the user's current setup), else Anthropic.
PROVIDER = os.environ.get("APOC_PROVIDER") or (
    "deepseek" if os.environ.get("DEEPSEEK_API_KEY") else "anthropic"
)

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_BASE = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com").rstrip("/")
DEEPSEEK_MODEL = os.environ.get("APOC_DEEPSEEK_MODEL", "deepseek-v4-pro")
DEEPSEEK_THINKING = os.environ.get("APOC_DEEPSEEK_THINKING", "enabled")
DEEPSEEK_REASONING_EFFORT = os.environ.get("APOC_DEEPSEEK_REASONING_EFFORT", "max")
EXTRACTION_MODEL = os.environ.get("APOC_EXTRACTION_MODEL", DEEPSEEK_MODEL)
EXTRACTION_DEEPSEEK_THINKING = os.environ.get("APOC_EXTRACTION_DEEPSEEK_THINKING", "disabled")
EXTRACTION_REASONING_EFFORT = os.environ.get("APOC_EXTRACTION_REASONING_EFFORT", "max")

# Both AI panel features (edit + chat) are pinned to one model, independent of the
# generation pipeline's per-stage assignment.
AI_EDIT_MODEL = os.environ.get("APOC_AI_EDIT_MODEL", "deepseek-v4-pro")

if PROVIDER == "deepseek":
    MODEL = os.environ.get("APOC_MODEL", DEEPSEEK_MODEL)
    RESEARCH_MODEL = os.environ.get("APOC_RESEARCH_MODEL", MODEL)
else:
    MODEL = os.environ.get("APOC_MODEL", "claude-opus-4-8")
    RESEARCH_MODEL = os.environ.get("APOC_RESEARCH_MODEL", MODEL)

# Effort for the heavier reasoning steps (Anthropic only). low|medium|high|xhigh|max.
EFFORT = os.environ.get("APOC_EFFORT", "high")

# Demo mode: every caller may act as any stakeholder and may edit. Roles still
# exist so the architect-only edit gate and approval roll-up are demonstrable.
DEMO_ALL_ADMIN = os.environ.get("APOC_DEMO_ALL_ADMIN", "1") not in ("0", "false", "False")

# CORS origin for the Vite dev server.
FRONTEND_ORIGIN = os.environ.get("APOC_FRONTEND_ORIGIN", "http://localhost:5174")

# Provider-neutral research grounding. By default APoc discovers sources through
# SearXNG and crawls page bodies with Crawl4AI. Anthropic's native web_search is
# still available for teams that explicitly want the provider-hosted path.
SEARXNG_URL = os.environ.get("APOC_SEARXNG_URL", "http://localhost:8080").rstrip("/")
SEARCH_TOPK = int(os.environ.get("APOC_SEARCH_TOPK", "4"))
CRAWL_CONCURRENCY = int(os.environ.get("APOC_CRAWL_CONCURRENCY", "4"))
CRAWL_TIMEOUT = float(os.environ.get("APOC_CRAWL_TIMEOUT", "30"))
GROUNDING = os.environ.get("APOC_GROUNDING", "searxng").strip().lower()
ANTHROPIC_NATIVE_SEARCH = (
    GROUNDING == "anthropic_native"
    or os.environ.get("APOC_ANTHROPIC_NATIVE_SEARCH", "").strip().lower() in {"1", "true", "yes", "on"}
)

# Stakeholder roles understood by the platform. Each maps to a review lens.
ROLES = [
    "architect",
    "compliance",
    "security",
    "finops",
    "legal",
    "cto",
    "client_sponsor",
    "consultant",
]

# Roles that produce an AI review report + annotations during generation.
REVIEW_ROLES = ["compliance", "security", "finops", "cto"]

# Only this role may edit the POC deck.
EDITOR_ROLE = "architect"

# Roles whose approval counts toward the "ready to align" roll-up.
APPROVER_ROLES = ["architect", "compliance", "security", "finops", "cto"]

# Semantic categories for architecture-diagram nodes. Drives node color/icon in
# the UI. The LLM assigns each component one of these; anything else falls back
# to "backend". Nodes remain 1:1 with the POC document's components.
NODE_TYPES = (
    "frontend",
    "backend",
    "database",
    "cloud",
    "security",
    "messagebus",
    "external",
    "gateway",
)
NODE_TYPE_FALLBACK = "backend"

# --- Fusion generation (LangGraph) -----------------------------------------
# Generation backend: "graph" (new fusion flow) or "legacy" (the old monolithic
# generation.run_generation). Lets the new path roll out without deleting the old.
GENERATION_MODE = os.environ.get("APOC_GENERATION", "graph").strip().lower()

# Where per-run artifacts (candidate designs, canonical design, manifest) live.
RUNS_DIR = Path(os.environ.get("APOC_RUNS_DIR", Path(__file__).resolve().parent.parent / "runs"))

# Per-stage model assignment. Each may be overridden via env. Defaults encode the
# settled plan: DeepSeek V4 Pro for breadth, Opus only where discrimination matters.
RESEARCH_MODEL_FUSION = os.environ.get("APOC_FUSION_RESEARCH_MODEL", DEEPSEEK_MODEL)
CANDIDATE_MODELS = [
    os.environ.get("APOC_FUSION_CANDIDATE_A", DEEPSEEK_MODEL),
    os.environ.get("APOC_FUSION_CANDIDATE_B", "claude-haiku-4-5"),
]
JUDGE_MODEL = os.environ.get("APOC_FUSION_JUDGE_MODEL", "claude-opus-4-8")
DOCUMENT_MODEL = os.environ.get("APOC_FUSION_DOCUMENT_MODEL", DEEPSEEK_MODEL)
DECK_MODEL = os.environ.get("APOC_FUSION_DECK_MODEL", DEEPSEEK_MODEL)
REVIEW_MODEL_FUSION = os.environ.get("APOC_FUSION_REVIEW_MODEL", DEEPSEEK_MODEL)

# --- Evaluation (fusion ablation) ------------------------------------------
OPUS_SOLO_MODEL = os.environ.get("APOC_EVAL_OPUS_SOLO_MODEL", "claude-opus-4-8")
EVAL_JUDGE_MODEL = os.environ.get("APOC_EVAL_JUDGE_MODEL", "")  # held-out; different family

# --- Langfuse (tracing + eval hosting) -------------------------------------
# Accept both naming conventions:
#   APOC_LANGFUSE_ENABLED  (code-level override)  or  LANGFUSE_ENABLED  (.env convention)
#   LANGFUSE_HOST          (explicit)              or  LANGFUSE_BASE_URL (.env convention)
#   LANGFUSE_PUBLIC_KEY    (explicit)              or  LANGFUSE_INIT_PROJECT_PUBLIC_KEY
#   LANGFUSE_SECRET_KEY    (explicit)              or  LANGFUSE_INIT_PROJECT_SECRET_KEY
def _truthy(v: str) -> bool:
    return v.lower() not in ("0", "false", "")

_lf_enabled_raw = os.environ.get("APOC_LANGFUSE_ENABLED") or os.environ.get("LANGFUSE_ENABLED", "0")
LANGFUSE_ENABLED = _truthy(_lf_enabled_raw)
LANGFUSE_PUBLIC_KEY = (
    os.environ.get("LANGFUSE_PUBLIC_KEY")
    or os.environ.get("LANGFUSE_INIT_PROJECT_PUBLIC_KEY", "")
)
LANGFUSE_SECRET_KEY = (
    os.environ.get("LANGFUSE_SECRET_KEY")
    or os.environ.get("LANGFUSE_INIT_PROJECT_SECRET_KEY", "")
)
LANGFUSE_HOST = (
    os.environ.get("LANGFUSE_HOST")
    or os.environ.get("LANGFUSE_BASE_URL", "http://localhost:3000")
)

# The fixed POC document sections, in order. (key, H2 heading). Reviews and the
# document writer both anchor to these headings — keep them in sync with prompts.
# Consolidated from 10 to 7: requirements_mapping+nfrs and decisions+risks+
# open_questions were merged because, generated as independent calls, each section
# re-stated the same NFR table / risk list (the writer can't see its siblings'
# output). Merging removes the cross-section duplication AND cuts sequential calls.
DOC_SECTIONS = [
    ("executive_summary", "Executive summary"),
    ("context_goals", "Context & goals"),
    ("requirements_nfrs", "Requirements & non-functional requirements"),
    ("proposed_architecture", "Proposed architecture"),
    ("technology_choices", "Technology choices"),
    ("decisions_risks", "Key decisions, risks & open questions"),
    ("cost_outlook", "Cost outlook"),
]

# Maps each DOC_SECTIONS key to the canonical-design field key(s) whose section
# files (written by ArtifactStore.build_manifest, keyed by canonical field name)
# the document writer should read for that section. Keeps the writer's
# read_section() calls aligned with the files the judge/manifest actually wrote.
DOC_SECTION_SOURCES = {
    "executive_summary": ["executive_summary"],
    "context_goals": ["context"],
    "requirements_nfrs": ["requirements_mapping", "nfrs"],
    "proposed_architecture": ["components", "data_flows"],
    "technology_choices": ["tech_stack"],
    "decisions_risks": ["decisions", "risks", "open_questions"],
    "cost_outlook": ["cost_estimate"],
}

# Stakeholder review lenses run in parallel (one DeepSeek call each). Reuses the
# existing REVIEW_ROLES set so the DB/UI roles are unchanged.
STAKEHOLDER_LENSES = {
    "compliance": "regulatory exposure, data residency, policy and audit posture",
    "security": "identity, network boundaries, data protection, threat surface",
    "finops": "cost assumptions, cost risk, and optimisation opportunities",
    "cto": "overall viability, key trade-offs, and what must be resolved before proceeding",
}
