import os
from dotenv import load_dotenv

load_dotenv()

# LLM — Google Gemini (free tier)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
MODEL_NAME = "gemini-2.0-flash"
MAX_TOKENS = 8096

# Search
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# SEC EDGAR
EDGAR_USER_AGENT = os.getenv("EDGAR_USER_AGENT", "DueDiligenceAgent contact@example.com")

# Persistence
CHECKPOINT_DB_PATH = os.getenv("CHECKPOINT_DB_PATH", "./checkpoints.db")

# Output
REPORTS_DIR = os.getenv("REPORTS_DIR", "./reports")

def validate_config() -> list[str]:
    """Return list of missing required config keys."""
    missing = []
    if not GOOGLE_API_KEY:
        missing.append("GOOGLE_API_KEY")
    if not TAVILY_API_KEY:
        missing.append("TAVILY_API_KEY")
    return missing
