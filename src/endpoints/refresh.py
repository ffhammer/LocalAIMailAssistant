import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException

from src.app_context import AppContext, Application
from src.imap_client_management.refresh import sync_account
from src.models import UpdateStatus

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
)
async def refresh_account(
    account_id: str,
):
    context: AppContext = Application.get_current_context()
    if account_id not in context.dbs:
        raise HTTPException(status_code=404, detail="Account not found")

        # start sync_account in th background
    asyncio.create_task(sync_account(context.dbs[account_id]))
    return {"status": "sync started"}
