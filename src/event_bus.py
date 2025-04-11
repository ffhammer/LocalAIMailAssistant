import asyncio
from enum import StrEnum
from typing import Optional

from loguru import logger
from pydantic import BaseModel


class EventTypes(StrEnum):
    NEW = "new"
    UPDATED = "updated"
    DELETED = "deleted"
    FAILURE = "failure"


class EventCategories(StrEnum):
    MAIL = "mail"
    SUMMARY = "SUMMARY"
    MAILBOX = "mailbox"
    DRAFT = "draft"
    FLAGS = "flags"


class Event(BaseModel):
    type: EventTypes
    category: EventCategories
    identifier: Optional[str] = None
    message: Optional[str] = None


class EventBus:
    _instance: "EventBus" = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.queue = asyncio.Queue()
        return cls._instance

    async def publish(self, event: "Event") -> None:
        logger.debug(
            f"Publishing event - Type: {event.type}, Category: {event.category}, Identifier: {event.identifier}, Message: {event.message}"
        )
        await self.queue.put(event)

    async def subscribe(self):
        while True:
            event = await self.queue.get()
            yield event
