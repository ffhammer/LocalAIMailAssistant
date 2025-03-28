import asyncio
from datetime import datetime, timedelta
from typing import List, Optional

from loguru import logger
from sqlmodel import Session, select

from src.mail_db import (
    MailDB,
    MailMessageSQL,
    UpdateStatus,
)

from .imap_querying import IMAPClient


async def fetch_and_save_mails(db: MailDB, uids: List[int], mailbox: str):
    """Async generator: for each UID, fetch and save the mail, then yield the UID."""
    with IMAPClient(settings=db.settings) as client:
        for uid in uids:
            # Offload the blocking fetch operation
            mail = await asyncio.to_thread(client.fetch_email_by_uid, uid, mailbox)
            if mail is None:
                logger.error(f"Can't fetch mail with uid {uid}")
                continue
            # Save email offloaded as well
            logger.debug(f"Succesfully saved email with uid {uid}")
            await asyncio.to_thread(db.save_email, mail)
            yield mail.Message_ID


async def refresh_mailbox(
    db: MailDB, mailbox: str, after_date: Optional[datetime] = None
):
    """Async generator: refresh mailbox and yield each new UID as it’s saved."""
    start_to_update = datetime.now()
    if after_date is None:
        status = db.get_update_status()
        if status:
            after_date = status.last_updated
        else:
            after_date = datetime.now() - timedelta(days=60)

    with IMAPClient(settings=db.settings) as client:
        new_mail_ids = client.fetch_uids_after_date(
            after_date=after_date, mailbox=mailbox
        )

    with Session(db.engine) as session:
        already_saved = session.exec(select(MailMessageSQL.imap_uid)).all()

    to_do = list(set(new_mail_ids).difference(already_saved))
    logger.info(f"Fetching these uids {to_do}")
    # Yield each message_id as soon as it’s processed.
    async for message_id in fetch_and_save_mails(db=db, uids=to_do, mailbox=mailbox):
        yield message_id

    status = db.get_update_status()
    if status is None:
        status = UpdateStatus(last_update=start_to_update)
    else:
        status.last_update = start_to_update
