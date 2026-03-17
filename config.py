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

VALID_MODES = list(MODE_REGISTRY.keys())


def validate_config() -> list[str]:
    """Return list of missing required config keys."""
    missing = []
    if not ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY")
    if not TAVILY_API_KEY:
        missing.append("TAVILY_API_KEY")
    return missing
