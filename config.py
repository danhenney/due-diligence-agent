import os
from dotenv import load_dotenv

load_dotenv()

# LLM — Anthropic Claude
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL_NAME = "claude-sonnet-4-6"
MAX_TOKENS = 16000

# Hard cost cap per analysis (USD). Pipeline aborts early if exceeded.
MAX_COST_PER_ANALYSIS = 7.00

# Search
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# SEC EDGAR
EDGAR_USER_AGENT = os.getenv("EDGAR_USER_AGENT", "DueDiligenceAgent contact@example.com")

# DART (Korean FSS) — free key at opendart.fss.or.kr
DART_API_KEY = os.getenv("DART_API_KEY", "")

# Optional — improves macro data (free key at fred.stlouisfed.org)
FRED_API_KEY = os.getenv("FRED_API_KEY", "")

# Optional — increases GitHub API rate limit from 60 to 5000 req/hr
# Create a free token at github.com/settings/tokens (no scopes needed)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# Optional — USPTO patent search (free key at search.patentsview.org/docs)
PATENTSVIEW_API_KEY = os.getenv("PATENTSVIEW_API_KEY", "")

# Optional — KIPRIS Korean patent search (free key at plus.kipris.or.kr)
KIPRIS_API_KEY = os.getenv("KIPRIS_API_KEY", "")

# Optional — KOSIS Korean national statistics (free key at kosis.kr/openapi)
KOSIS_API_KEY = os.getenv("KOSIS_API_KEY", "")

# Persistence
CHECKPOINT_DB_PATH = os.getenv("CHECKPOINT_DB_PATH", "./checkpoints.db")

# Output
REPORTS_DIR = os.getenv("REPORTS_DIR", "./reports")

# ── Analysis Modes ────────────────────────────────────────────────────────
MODE_REGISTRY = {
    "due-diligence": {
        "phase1_agents": [
            "market_analysis", "competitor_analysis", "financial_analysis",
            "tech_analysis", "legal_regulatory", "team_analysis",
        ],
        "phase2_parallel": ["ra_synthesis", "risk_assessment"],
        "phase2_sequential": ["strategic_insight"],
        "phase3_agents": ["review_agent", "critique_agent", "dd_questions"],
        "phase4_sections": 6,
        "report_type": "due_diligence",
        "has_feedback_loop": True,
        "has_recommendation": True,
    },
    "industry-research": {
        "phase1_agents": ["market_analysis", "competitor_analysis", "tech_analysis"],
        "phase2_parallel": ["industry_synthesis"],
        "phase2_sequential": [],
        "phase3_agents": ["critique_agent"],
        "phase4_sections": 3,
        "report_type": "industry_research",
        "has_feedback_loop": False,
        "has_recommendation": False,
    },
    "deep-dive": {
        "phase1_agents": [
            "financial_analysis", "tech_analysis", "team_analysis", "legal_regulatory",
        ],
        "phase2_parallel": ["ra_synthesis", "risk_assessment"],
        "phase2_sequential": [],
        "phase3_agents": ["review_agent", "critique_agent"],
        "phase4_sections": 4,
        "report_type": "deep_dive",
        "has_feedback_loop": True,
        "has_recommendation": False,
    },
    "benchmark": {
        "phase1_agents": ["competitor_analysis", "financial_analysis", "tech_analysis"],
        "phase2_parallel": ["benchmark_synthesis"],
        "phase2_sequential": [],
        "phase3_agents": ["critique_agent"],
        "phase4_sections": 3,
        "report_type": "benchmark",
        "has_feedback_loop": False,
        "has_recommendation": False,
    },
}

VALID_MODES = list(MODE_REGISTRY.keys()) + ["custom"]

# ── Valid agent names ────────────────────────────────────────────────────────
VALID_PHASE1_AGENTS = [
    "market_analysis", "competitor_analysis", "financial_analysis",
    "tech_analysis", "legal_regulatory", "team_analysis",
]
VALID_PHASE2_AGENTS = [
    "ra_synthesis", "risk_assessment", "strategic_insight",
    "industry_synthesis", "benchmark_synthesis",
]
VALID_PHASE3_AGENTS = ["review_agent", "critique_agent", "dd_questions"]

# ── Dependencies ─────────────────────────────────────────────────────────────
# strategic_insight reads ra_synthesis + risk_assessment outputs
_PHASE2_DEPS = {
    "strategic_insight": {"ra_synthesis", "risk_assessment"},
}


def register_custom_mode(
    phase1: list[str],
    phase2_parallel: list[str],
    phase2_sequential: list[str] | None = None,
    phase3: list[str] | None = None,
    feedback_loop: bool = False,
    recommendation: bool = False,
    mode_key: str = "custom",
) -> str:
    """Validate and register a custom agent selection into MODE_REGISTRY.

    Returns the mode_key used (for thread-safe unique keys).
    Raises ValueError on invalid configuration.
    """
    phase2_sequential = phase2_sequential or []
    phase3 = phase3 if phase3 is not None else ["critique_agent"]

    # ── Validate agent names ──────────────────────────────────────────────
    errors = []
    for a in phase1:
        if a not in VALID_PHASE1_AGENTS:
            errors.append(f"Unknown Phase 1 agent: {a}")
    for a in phase2_parallel + phase2_sequential:
        if a not in VALID_PHASE2_AGENTS:
            errors.append(f"Unknown Phase 2 agent: {a}")
    for a in phase3:
        if a not in VALID_PHASE3_AGENTS:
            errors.append(f"Unknown Phase 3 agent: {a}")

    if not phase1:
        errors.append("At least 1 Phase 1 agent is required.")
    if not phase2_parallel and not phase2_sequential:
        errors.append("At least 1 Phase 2 agent is required.")

    # ── Validate dependencies ─────────────────────────────────────────────
    all_phase2 = set(phase2_parallel + phase2_sequential)
    for agent, deps in _PHASE2_DEPS.items():
        if agent in all_phase2 and not deps.issubset(all_phase2):
            missing = deps - all_phase2
            errors.append(f"{agent} requires {missing} in Phase 2.")

    if feedback_loop and "critique_agent" not in phase3:
        errors.append("Feedback loop requires critique_agent in Phase 3.")
    if recommendation and "strategic_insight" not in phase2_sequential:
        errors.append("Recommendation requires strategic_insight in Phase 2 sequential.")

    if errors:
        raise ValueError("Invalid custom mode config:\n" + "\n".join(f"  - {e}" for e in errors))

    # ── Build and register ────────────────────────────────────────────────
    cfg = {
        "phase1_agents": list(phase1),
        "phase2_parallel": list(phase2_parallel),
        "phase2_sequential": list(phase2_sequential),
        "phase3_agents": list(phase3),
        "phase4_sections": max(len(phase1), 3),
        "report_type": "custom",
        "has_feedback_loop": feedback_loop,
        "has_recommendation": recommendation,
    }
    MODE_REGISTRY[mode_key] = cfg
    return mode_key


def unregister_custom_mode(mode_key: str = "custom") -> None:
    """Remove a dynamically registered mode (cleanup after run)."""
    MODE_REGISTRY.pop(mode_key, None)


def validate_config() -> list[str]:
    """Return list of missing required config keys."""
    missing = []
    if not ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY")
    if not TAVILY_API_KEY:
        missing.append("TAVILY_API_KEY")
    return missing
