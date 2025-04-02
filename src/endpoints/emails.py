from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException

from ..app_context import Application
from ..imap.imap_client import list_mailboxes_of_account
from ..models import MailMessage, MailMessageSQL

router = APIRouter(tags=["Emails"])


@router.get(
    "/accounts/{account_id}/mailboxes/{mailbox}/emails",
    response_model=List[MailMessage],
)
def list_emails(
    account_id: str,
    mailbox: str,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
):
    """
    Lists emails from a given mailbox. For each email, return metadata including
    message_id, subject, sender, date_sent, snippet, and flags indicating if summary,
    draft, and chat are available.
    """
    context = Application.get_current_context()
    if account_id not in context.dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    if mailbox not in list_mailboxes_of_account(context.accounts[account_id]):
        raise HTTPException(status_code=404, detail="Mailbox not found")

    db = context.dbs[account_id]

    args = [MailMessageSQL.mailbox == mailbox]
    if from_date is not None:
        args.append(MailMessageSQL.date_sent > from_date)
    if to_date is not None:
        args.append(MailMessageSQL.date_sent < to_date)

    return db.query_emails(*args)


@router.get("/accounts/{account_id}/emails/{message_id}", response_model=MailMessage)
def get_email_details(
    account_id: str,
    message_id: str,
):
    """
    Retrieves full details of a single email by its message_id.
    Here, we assume a single account (the first one) for simplicity.
    """
    context = Application.get_current_context()
    if account_id not in context.dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    db = context.dbs[account_id]
    email = db.get_email_by_message_id(message_id)
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")
    return email
