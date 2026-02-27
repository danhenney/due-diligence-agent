import os
from dotenv import load_dotenv

load_dotenv()

# LLM — Anthropic Claude
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL_NAME = "claude-sonnet-4-6"
MAX_TOKENS = 8096

# Search
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# SEC EDGAR
EDGAR_USER_AGENT = os.getenv("EDGAR_USER_AGENT", "DueDiligenceAgent contact@example.com")

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

def validate_config() -> list[str]:
    """Return list of missing required config keys."""
    missing = []
    if not ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY")
    if not TAVILY_API_KEY:
        missing.append("TAVILY_API_KEY")
    return missing
