from dataclasses import dataclass
from typing import Optional

from fastapi import FastAPI

from src.accounts.accounts_loading import AccountSettings
from src.background_tasks.background_manager import BackgroundTaskManager
from src.database import MailDB
from src.settings import Settings


@dataclass
class AppContext:
    accounts: dict[str, AccountSettings]
    dbs: dict[str, MailDB]
    background_manager: BackgroundTaskManager
    settings: Settings


class Application:
    current: Optional["Application"] = None

    def __new__(cls, *args, **kwargs):
        cls.current = super().__new__(cls)
        return cls.current

    def __init__(self, app: FastAPI, context: AppContext, settings=Settings):
        self.app: FastAPI = app
        self.context: AppContext = context
        self.settings: Settings = settings

    @classmethod
    def get_current_context(cls) -> AppContext:
        if cls.current is None:
            raise ValueError("Application not instantiated")

        return cls.current.context
