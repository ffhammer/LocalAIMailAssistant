from src.accounts_loading import load_accounts
from src.mail_db import MailDB
from src.ollama_background_processor import BackgroundOllamaProcessor
from loguru import logger
import sys

logger.remove()
logger.add("summary.log", level="DEBUG", rotation="10 MB")
logger.add(sys.stdout, level="DEBUG", format="{time} {level} {message}")


logger.info("Starting background email chat processor")

settings = load_accounts("secrets/accounts.yaml")["gmx"]
db = MailDB("db", settings)
processor = BackgroundOllamaProcessor(db)
# processor.generate_missing_chats()

processor.generate_missing_summaries()

logger.info("Background processing complete")
