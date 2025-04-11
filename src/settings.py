from typing import Literal

from pydantic import BaseModel
from pydantic_settings import BaseSettings


class ImapSettings(BaseModel):
    max_retries: int = 3
    retry_delay: float = 2.0  # delay in seconds


class Settings(BaseSettings):
    TEST_BACKEND: str = "False"
    PATH_TO_TEST_DATA: str = "test_data/data.json"
    LOG_LEVEL: str = "DEBUG"
    TEST_DB_PATH: str = "test_db"
    DEFAULT_DB_DIR: str = "db"
    LOAD_TEST_DATA: bool = True
    llm_provider: Literal["ollama", "gemini"] = "ollama"
    imap_settings: ImapSettings = ImapSettings()


class LLMSettings(BaseSettings):
    chat_extractor_moedel: str = "gemma3:12b"
    summary_model: str = "llama3.2"
    draft_generator_model: str = "gemma3:12b"
    gemini_model: str = "gemini-2.0-flash"
