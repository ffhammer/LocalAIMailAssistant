import asyncio
from datetime import datetime, timedelta
from typing import List, Optional

from loguru import logger
from result import Err, Result, is_err
from sqlmodel import Session, select

from src.db.mail_db import MailDB, MailMessage, MailMessageSQL, UpdateStatus
from src.imap.imap_client import IMAPClient, ImapClientInterface
from src.models import MailFlag


async def fetch_and_save_mails(db: MailDB, uids: List[int], mailbox: str):
    """Async generator: for each UID, fetch and save the mail, then yield the UID."""
    with IMAPClient(account=db.account, settings=db.settings) as client:
        for uid in uids:
            # Offload the blocking fetch operation
            mail = await asyncio.to_thread(client.fetch_email_by_uid, uid, mailbox)
            if mail is None:
                logger.error(f"Can't fetch mail with uid {uid}")
                continue
            # Save email offloaded as well
            logger.debug(f"Succesfully saved email with uid {uid}")
            await asyncio.to_thread(db.save_email, mail)
            yield mail.message_id


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

    with IMAPClient(account=db.account, settings=db.settings) as client:
        new_mail_ids = client.fetch_uids_after_date(
            after_date=after_date, mailbox=mailbox
        )

    with Session(db.engine) as session:
        already_saved = session.exec(
            select(MailMessageSQL.imap_uid).where(MailMessageSQL.mailbox == mailbox)
        ).all()

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


async def sync_account(db: MailDB):
    last_mailboxes = {mail.mailbox for mail in db.query_table(MailMessageSQL)}

    with IMAPClient(account=db.account, settings=db.settings) as client:
        client: ImapClientInterface
        current_mailboxes = set(client.list_mailboxes())

        deleted_mailboxes = last_mailboxes.difference(current_mailboxes)
        for mailbox in deleted_mailboxes:
            logger.info(f"Deleting Mailbox {mailbox}")
            db.delete_records(MailMessageSQL, MailMessageSQL.mailbox == mailbox)

        new_mailboxes = current_mailboxes.difference(last_mailboxes)
        for mailbox in new_mailboxes:
            logger.info(f"Creating New Mailbox {mailbox}")
            new_mail_ids = client.fetch_uids_after_date(mailbox=mailbox)
            async for _ in fetch_and_save_mails(
                db=db, uids=new_mail_ids, mailbox=mailbox
            ):
                pass

        unchanged_mailboxes = last_mailboxes.intersection(current_mailboxes)
        for mailbox in unchanged_mailboxes:
            mail_ids = set(client.fetch_uids_after_date(mailbox=mailbox))

            with Session(db.engine) as session:
                already_saved = set(
                    session.exec(
                        select(MailMessageSQL.imap_uid).where(
                            MailMessageSQL.mailbox == mailbox
                        )
                    ).all()
                )

            deleted_mails = already_saved.difference(mail_ids)
            if deleted_mails:
                db.delete_records(
                    MailMessageSQL,
                    MailMessageSQL.imap_uid.in_(deleted_mails),
                    MailMessageSQL.mailbox == mailbox,
                )

            new_mails = mail_ids.difference(already_saved)
            async for _ in fetch_and_save_mails(
                db=db, uids=list(new_mails), mailbox=mailbox
            ):
                pass

        # update flags
        for mailbox in current_mailboxes:
            flags = client.fetch_all_flags_off_mailbox(mailbox=mailbox)
            db.update_flags(data=flags, mailbox=mailbox)


def toggle_flag(
    db: MailDB,
    email_message_id: str,
    flag: MailFlag,
) -> Result[MailMessage, str]:
    """Toggle a flag for an email message in the database and update it on the server."""
    # Toggle the flag in the database
    res = db.toggle_flag(email_message_id=email_message_id, flag=flag)
    if is_err(res):
        return res

    try:
        # Update the flag on the IMAP server
        with IMAPClient(account=db.account, settings=db.settings) as client:
            client: ImapClientInterface
            client.update_flags(mail=res.value)
    except Exception as e:
        logger.exception(
            f"Failed to update flags on server for {email_message_id}: {e}"
        )

        # Attempt to revert the flag change in the database
        revert_res = db.toggle_flag(email_message_id=email_message_id, flag=flag)
        if is_err(revert_res):
            logger.warning(
                f"Failed to revert flag change in database for {email_message_id} with flag {flag}"
            )

        return Err(
            "Failed to update flags on server and revert changes in the database."
        )

    return res
