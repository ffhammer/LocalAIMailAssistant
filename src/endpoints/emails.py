from datetime import datetime
from enum import Enum
from typing import Generic, List, Optional, TypeVar

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.app_context import Application
from src.imap import list_mailboxes_of_account
from src.imap_client_management.flag import toggle_flag
from src.models import MailFlag, MailHeader, MailMessage

router = APIRouter(tags=["Emails"])

T = TypeVar("T")


class SortField(str, Enum):
    DATE_SENT = "date_sent"
    DATE_RECEIVED = "date_received"
    SUBJECT = "subject"
    SENDER = "sender"


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    limit: int
    offset: int
    has_more: bool


@router.get(
    "/accounts/{account_id}/mailboxes/{mailbox}/emails",
    response_model=PaginatedResponse[MailHeader],
)
def list_emails(
    account_id: str,
    mailbox: str,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    sender: Optional[str] = None,
    subject: Optional[str] = None,
    seen: Optional[bool] = None,
    answered: Optional[bool] = None,
    flagged: Optional[bool] = None,
    deleted: Optional[bool] = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort_by: SortField = SortField.DATE_SENT,
    sort_desc: bool = True,
):
    """
    Lists emails from a given mailbox with filtering, sorting, and pagination capabilities.

    Args:
        account_id: The account identifier
        mailbox: The mailbox to list emails from
        from_date: Filter emails sent after this date
        to_date: Filter emails sent before this date
        sender: Filter by sender email (partial match)
        subject: Filter by subject (partial match)
        seen: Filter by seen status
        answered: Filter by answered status
        flagged: Filter by flagged status
        deleted: Filter by deleted status
        limit: Number of emails to return (1-100)
        offset: Number of emails to skip
        sort_by: Field to sort by (date_sent, date_received, subject, sender)
        sort_desc: Whether to sort in descending order
    """
    context = Application.get_current_context()
    if account_id not in context.dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    if mailbox not in list_mailboxes_of_account(
        context.accounts[account_id], settings=context.settings
    ):
        raise HTTPException(status_code=404, detail="Mailbox not found")

    db = context.dbs[account_id]

    args = [MailMessage.mailbox == mailbox]

    # Date filters
    if from_date is not None:
        args.append(MailMessage.date_sent > from_date)
    if to_date is not None:
        args.append(MailMessage.date_sent < to_date)

    # Sender and subject filters (case-insensitive partial matches)
    if sender:
        args.append(MailMessage.sender.ilike(f"%{sender}%"))
    if subject:
        args.append(MailMessage.subject.ilike(f"%{subject}%"))

    # Flag filters
    if seen is not None:
        args.append(MailMessage.seen == seen)
    if answered is not None:
        args.append(MailMessage.answered == answered)
    if flagged is not None:
        args.append(MailMessage.flagged == flagged)
    if deleted is not None:
        args.append(MailMessage.deleted_status == deleted)

    # Get total count for pagination
    total_emails = db.count_email_headers(*args)

    # Get paginated and sorted results
    emails = db.query_email_headers(
        *args, limit=limit, offset=offset, order_by=sort_by.value, order_desc=sort_desc
    )

    return PaginatedResponse(
        items=emails,
        total=total_emails,
        limit=limit,
        offset=offset,
        has_more=offset + limit < total_emails,
    )


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


@router.put(
    "/accounts/{account_id}/emails/{message_id}/flag",
)
def toggle_flag_endpoint(
    account_id: str,
    message_id: str,
    flag: MailFlag,
):
    """
    Retrieves full details of a single email by its message_id.
    Here, we assume a single account (the first one) for simplicity.
    """
    context = Application.get_current_context()
    if account_id not in context.dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    db = context.dbs[account_id]
    res = toggle_flag(db=db, email_message_id=message_id, flag=flag)
    if res.is_err():
        raise HTTPException(status_code=400, detail=res.unwrap_err())
