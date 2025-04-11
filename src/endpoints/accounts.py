from fastapi import APIRouter, HTTPException

from ..app_context import AppContext, Application
from ..imap import list_mailboxes_of_account

router = APIRouter()


@router.get("/accounts", response_model=list[dict])
def list_accounts():
    """
    Lists configured accounts.
    """
    context: AppContext = Application.get_current_context()

    return [
        {
            "account_id": key,
            "apple_mail_name": settings.apple_mail_name,
            "imap_server": settings.imap_server,
            "user": settings.user,
            "name": settings.user_for_mail,
        }
        for key, settings in context.accounts.items()
    ]


@router.get("/accounts/{account_id}/mailboxes", response_model=list[str])
def list_mailboxes(account_id: str):
    """
    Lists mailboxes for the specified account.
    """
    context: AppContext = Application.get_current_context()
    if account_id not in context.dbs:
        raise HTTPException(status_code=404, detail="Account not found")
    return list_mailboxes_of_account(
        context.accounts[account_id], settings=context.settings
    )
