import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ALPHAVANTAGE_API_KEY: str = os.getenv("ALPHAVANTAGE_API_KEY", "")
TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")
EXA_API_KEY: str = os.getenv("EXA_API_KEY", "")
POLYGON_API_KEY: str = os.getenv("POLYGON_API_KEY", "")

DATABASE_PATH: Path = Path(os.getenv("DATABASE_PATH", "trading.db"))
REPORT_OUTPUT_DIR: Path = Path(os.getenv("REPORT_OUTPUT_DIR", "reports"))

# Cache TTLs in minutes
CACHE_TTL_QUOTE: int = 15
CACHE_TTL_FUNDAMENTALS: int = 1440  # 24 hours
CACHE_TTL_NEWS: int = 60  # 1 hour

# Rate limits (requests per minute)
ALPHAVANTAGE_RATE_LIMIT: int = 5
YAHOO_RATE_LIMIT: int = 60
