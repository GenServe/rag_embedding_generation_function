import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    """Configuration settings for the application."""
    SECRET_KEY: str = os.getenv("SECRET_KEY") or ""
    ALGORITHM: str = os.getenv("ALGORITHM") or "HS256"

settings = Settings()