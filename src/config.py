import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

class Config:
    ROOT_DIR: Path = ROOT_DIR
    DATA_PATH: Path = ROOT_DIR / os.getenv("DATA_PATH", "data/raw")
    KNOWLEDGE_BASE_PATH: Path = ROOT_DIR / os.getenv("KNOWLEDGE_BASE_PATH", "data/knowledge_base")
    OUTPUT_PATH: Path = ROOT_DIR / os.getenv("OUTPUT_PATH", "outputs/output.csv")
    TRANSCRIPT_PATH: Path = ROOT_DIR / os.getenv("TRANSCRIPT_PATH", "outputs/chat_transcript.md")
    
    DEFAULT_LLM_PROVIDER: str = os.getenv("DEFAULT_LLM_PROVIDER", "google").lower()
    DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "gemini/gemini-3.8-flash")
    TEMPERATURE: float = float(os.getenv("TEMPERATURE", "0.0"))
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
    TIMEOUT_SECONDS: int = int(os.getenv("TIMEOUT_SECONDS", "30"))

    # API Keys & Endpoints
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    
    # Ollama (Local or Cloud/Remote)
    OLLAMA_API_BASE: str = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")
    OLLAMA_API_KEY: str = os.getenv("OLLAMA_API_KEY", "")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2")

    @classmethod
    def get_active_model(cls) -> str:
        """Determines best active model based on provider preference and available credentials."""
        # 1. Explicit Ollama Provider
        if cls.DEFAULT_LLM_PROVIDER == "ollama":
            return f"ollama/{cls.OLLAMA_MODEL}"
        
        # 2. Cloud Providers
        if cls.GEMINI_API_KEY and not cls.GEMINI_API_KEY.startswith("your_"):
            return "gemini/gemini-3.8-flash"
        if cls.GROQ_API_KEY and not cls.GROQ_API_KEY.startswith("your_"):
            return "groq/llama-3.3-70b-versatile"
        if cls.OPENAI_API_KEY and not cls.OPENAI_API_KEY.startswith("your_"):
            return "openai/gpt-4o-mini"
        if cls.ANTHROPIC_API_KEY and not cls.ANTHROPIC_API_KEY.startswith("your_"):
            return "anthropic/claude-3-5-sonnet-20241022"
        
        # 3. Fallback to local Ollama if configured
        if cls.OLLAMA_MODEL and cls.DEFAULT_LLM_PROVIDER != "mock":
            return f"ollama/{cls.OLLAMA_MODEL}"

        return "mock/rule-based"
