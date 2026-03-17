import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# X API
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN", "")
X_API_KEY = os.getenv("X_API_KEY", "")
X_API_SECRET = os.getenv("X_API_SECRET", "")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN", "")
X_ACCESS_TOKEN_SECRET = os.getenv("X_ACCESS_TOKEN_SECRET", "")

# Anthropic API
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# 設定
TARGET_USERNAME = os.getenv("TARGET_USERNAME", "shodousan")
MAX_TWEETS = int(os.getenv("MAX_TWEETS", "20"))

BASE_DIR = Path(__file__).parent
NOTES_DIR = BASE_DIR / os.getenv("NOTES_DIR", "notes")
NOTES_DIR.mkdir(exist_ok=True)
