from src.mail_db import MailDB
from src.accounts_loading import load_accounts
from datetime import timedelta
from loguru import logger
import sys
from shutil import rmtree
# Remove default handler if needed
logger.remove()


# Add a new handler for INFO and higher levels
logger.add(sys.stdout, level="INFO")

settings = load_accounts("secrets/accounts.yaml")["uni"]

rmtree(f"db/{settings.apple_mail_name}")

MailDB.time_span_keeping_date = timedelta(
        days=20
    ) 
db = MailDB("db", settings)
db.update()