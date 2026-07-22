import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Конфигурация приложения."""
    MODEL_ID: str = "qwen/qwen3-next-80b-a3b-thinking"
    BASE_URL: str = "https://openrouter.ai/api/v1"
    API_KEY: Optional[str] = os.getenv("OPENROUTER_API_KEY")