from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime
from typing import List, Optional
import uvicorn

from src.accounts_loading import load_accounts
from src.mail_db import MailDB, MailMessageSQL
from src.ollama_background_processor import BackgroundOllamaProcessor
from src.message import MailMessage
from src.chats import EmailChat, generate_default_chat
from src.imap_querying import list_mailboxes_of_account


app = FastAPI(title="Local Email Summarization API")

# Load accounts from configuration (assumes a YAML file with multiple accounts)
accounts = load_accounts("secrets/accounts.yaml")
# For simplicity, create a MailDB instance per account (keyed by account_id)
dbs = {account_id: MailDB("db", settings) for account_id, settings in accounts.items()}
# Create a background processor per account
processors = {
    account_id: BackgroundOllamaProcessor(db) for account_id, db in dbs.items()
}


@app.get("/accounts", response_model=List[dict])
def list_accounts():
    """
    Lists configured accounts.
    """
    return [
        {
            "account_id": key,
            "apple_mail_name": settings.apple_mail_name,
            "imap_server": settings.imap_server,
            "user": settings.user,
            "name": settings.user_for_mail,
        }
        for key, settings in accounts.items()
    ]


@app.get("/accounts/{account_id}/mailboxes", response_model=List[str])
def list_mailboxes(account_id: str):
    """
    Lists mailboxes for the specified account.
    """
    if account_id not in dbs:
        raise HTTPException(status_code=404, detail="Account not found")
    return list_mailboxes_of_account(accounts[account_id])


@app.get(
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
    if account_id not in dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    if mailbox not in list_mailboxes_of_account(accounts[account_id]):
        raise HTTPException(status_code=404, detail="Mailbox not found")

    db = dbs[account_id]

    args = [MailMessageSQL.mailbox == mailbox]
    if from_date is not None:
        args.append(MailMessageSQL.date_sent > from_date)
    if to_date is not None:
        args.append(MailMessageSQL.date_sent < to_date)

    return db.query_emails(*args)


@app.get("/accounts/{account_id}/emails/{message_id}", response_model=MailMessage)
def get_email_details(
    account_id: str,
    message_id: str,
):
    """
    Retrieves full details of a single email by its message_id.
    Here, we assume a single account (the first one) for simplicity.
    """
    if account_id not in dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    db = dbs[account_id]
    email = db.get_email_by_message_id(message_id)
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")
    return email


@app.get("/accounts/{account_id}/chats/{message_id}", response_model=EmailChat)
def get_email_chat(
    account_id: str,
    message_id: str,
):
    if account_id not in dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    db = dbs[account_id]

    chat = db.get_mail_chat(email_id=message_id)

    if chat is not None:
        return chat

    email = db.get_email_by_message_id(message_id)
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")

    return generate_default_chat(email)


@app.get("/accounts/{account_id}/summaries/{message_id}", response_model=Optional[str])
def get_email_summary(
    account_id: str,
    message_id: str,
):
    if account_id not in dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    db = dbs[account_id]
    return db.get_mail_summary(email_id=message_id)


@app.post("/accounts/{account_id}/emails/{message_id}/summary")
def post_generate_summary(account_id: str, message_id: str):
    if account_id not in dbs:
        raise HTTPException(status_code=404, detail="Account not found")
    processors[account_id].generate_and_save_summary(message_id)
    return JSONResponse(
        content={"message_id": message_id, "status": "Summary generation triggered."}
    )


@app.post("/accounts/{account_id}/emails/{message_id}/chat")
def post_generate_chat(account_id: str, message_id: str):
    if account_id not in dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    processors[account_id].generate_and_save_chat(message_id)
    return JSONResponse(
        content={"message_id": message_id, "status": "Chat generation triggered."}
    )


@app.post("/accounts/{account_id}/emails/{message_id}/draft")
def post_generate_draft(account_id: str, message_id: str):
    if account_id not in dbs:
        raise HTTPException(status_code=404, detail="Account not found")
    return JSONResponse(
        content={
            "message_id": message_id,
            "status": "Draft generation not yet implemented.",
        }
    )


@app.get("/background/status", response_model=dict)
def get_background_status():
    """
    Returns background processing status.
    This is a placeholder. In a full implementation, background tasks should update status info.
    """
    return {
        "pending_chats": 0,
        "pending_summaries": 0,
        "last_run": datetime.now().isoformat(),
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
