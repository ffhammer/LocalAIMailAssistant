from dataclasses import dataclass
from typing import Optional

from fastapi import FastAPI
from pydantic_settings import BaseSettings

from src.accounts.accounts_loading import AccountSettings
from src.background_tasks.background_manager import BackgroundTaskManager
from src.db import MailDB


class ApiSettings(BaseSettings):
    TEST_BACKEND: str = "False"
    PATH_TO_TEST_DATA: str = "test_data/data.json"
    LOG_LEVEL: str = "DEBUG"
    TEST_DB_PATH: str = "test_db"
    DEFAULT_DB_DIR: str = "db"
    LOAD_TEST_DATA: bool = True


@dataclass
class AppContext:
    accounts: dict[str, AccountSettings]
    dbs: dict[str, MailDB]
    background_manager: BackgroundTaskManager


class Application:
    current: Optional["Application"] = None

    def __new__(cls, *args, **kwargs):
        cls.current = super().__new__(cls)
        return cls.current

    def __init__(self, app: FastAPI, context: AppContext, settings=ApiSettings):
        self.app: FastAPI = app
        self.context: AppContext = context
        self.settings: ApiSettings = settings

    @classmethod
    def get_current_context(cls) -> AppContext:
        if cls.current is None:
            raise ValueError("Application not instantiated")

        return cls.current.context
