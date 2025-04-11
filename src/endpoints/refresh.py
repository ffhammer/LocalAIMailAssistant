import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger

from ..app_context import AppContext, Application
from ..background_tasks.refresh import refresh_mailbox
from ..imap.imap_client import list_mailboxes_of_account
from ..models import UpdateStatus

router = APIRouter(tags=["Refresh"])


@router.get("/accounts/{account_id}/status/", response_model=Optional[UpdateStatus])
def get_last_update_status(account_id: str):
    context: AppContext = Application.get_current_context()
    if account_id not in context.dbs:
        raise HTTPException(status_code=404, detail="Account not found")
    db = context.dbs[account_id]
    return db.get_update_status()


@router.post(
    "/accounts/{account_id}/refresh",
    response_class=StreamingResponse,
    response_description="A stream of message_ids for each succesfully saved new mail",
)
async def post_update_account(
    account_id: str,
    mailbox: str,
    after_date: Optional[datetime] = None,
):
    context: AppContext = Application.get_current_context()
    if account_id not in context.dbs:
        raise HTTPException(status_code=404, detail="Account not found")
    if mailbox not in list_mailboxes_of_account(
        context.accounts[account_id], settings=context.settings
    ):
        raise HTTPException(status_code=404, detail="Mailbox not found")

    async def event_generator():
        async for message_id in refresh_mailbox(
            db=context.dbs[account_id], mailbox=mailbox, after_date=after_date
        ):
            logger.debug(f"yielding new message {message_id}")
            yield f"data: {message_id}\n\n"
            await asyncio.sleep(0.02)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
