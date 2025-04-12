import asyncio
from typing import List

from loguru import logger
from sqlmodel import Session, select

from src.database.mail_db import MailDB, MailMessageSQL
from src.event_bus import Event, EventBus, EventCategories, EventTypes
from src.imap import IMAPClient
from src.imap.ImapClientInterface import ImapClientInterface

# Get the singleton event bus.
event_bus = EventBus()


async def refresh_mailbox(
    db: MailDB,
    mailbox: str,
    client: ImapClientInterface,
) -> None:
    """
    Sync a single mailbox by fetching new messages and saving them.
    Publishes an event when completed.

    """

    try:
        new_mail_ids = client.fetch_uids_after_date(mailbox=mailbox)

        with Session(db.engine) as session:
            already_saved = session.exec(
                select(MailMessageSQL.imap_uid).where(MailMessageSQL.mailbox == mailbox)
            ).all()

        # Determine which UIDs need to be fetched.
        to_fetch: List[int] = list(set(new_mail_ids).difference(already_saved))
        logger.info(f"Mailbox '{mailbox}': new UIDs to fetch: {to_fetch}")

        for uid in to_fetch:
            # Offload the blocking fetch operation.
            try:
                mail = await asyncio.to_thread(client.fetch_email_by_uid, uid, mailbox)
                if mail is None:
                    logger.error(f"Can't fetch mail with UID {uid}")
                    continue
                logger.debug(f"Fetched mail UID {uid} from '{mailbox}'. Saving...")
                # Save mail using a blocking call offloaded to a thread.
                await asyncio.to_thread(db.save_email, mail)
            except Exception:
                logger.exception(f"saving mail with {uid} failed for {mailbox}")

        # Publish a "new" event for the mailbox.
        event = Event(
            type=EventTypes.NEW,
            category=EventCategories.MAIL,
            identifier=mailbox,
            message="Mailbox refreshed",
        )
        await event_bus.publish(event)
        logger.info(f"Mailbox '{mailbox}' refreshed and event published.")
    except Exception as e:
        await event_bus.publish(
            Event(
                type=EventTypes.FAILURE,
                category=EventCategories.MAIL,
                identifier=mailbox,
                message="Failed Mailbox refreshed",
            )
        )
        logger.exception(f"Failed to refresh mailbox '{mailbox}': {e}")


async def update_flags_for_mailbox(
    db: MailDB, client: ImapClientInterface, mailbox: str
) -> None:
    """
    Update flags for a given mailbox.
    Publishes an event on success or error.
    """
    try:
        flags = client.fetch_all_flags_off_mailbox(mailbox=mailbox)
        db.update_flags(data=flags, mailbox=mailbox)
        event = Event(
            type=EventTypes.UPDATED,
            category=EventCategories.FLAGS,
            identifier=mailbox,
            message="Flags updated",
        )
        await event_bus.publish(event)
        logger.info(f"Flags updated for mailbox '{mailbox}'.")
    except Exception as e:
        logger.error(f"Failed to update flags for mailbox '{mailbox}': {e}")
        event = Event(
            type=EventTypes.FAILURE,
            category=EventCategories.FLAGS,
            identifier=mailbox,
            message=f"Flag update failed: {e}",
        )
        await event_bus.publish(event)


async def delete_mailbox(db: MailDB, client: ImapClientInterface, mailbox: str) -> None:
    try:
        logger.info(f"Deleting mailbox '{mailbox}' locally.")

        def _del_records():
            db.delete_records(MailMessageSQL, MailMessageSQL.mailbox == mailbox)

        await asyncio.to_thread(_del_records)
        await event_bus.publish(
            Event(
                type=EventTypes.DELETED,
                category=EventCategories.MAILBOX,
                identifier=mailbox,
                message="Mailbox is no longer on the IMAP server",
            )
        )
        logger.info(f"Mailbox '{mailbox}' deleted successfully.")
    except Exception as e:
        logger.error(f"Failed to delete mailbox '{mailbox}': {e}")
        await event_bus.publish(
            Event(
                type=EventTypes.FAILURE,
                category=EventCategories.MAILBOX,
                identifier=mailbox,
                message=f"Failed to delete mailbox: {e}",
            )
        )


async def sync_account(db: MailDB) -> None:
    """
    Sync all mailboxes by performing discrete jobs:
      - For each mailbox, refresh messages.
      - Update flags.
    """

    # Get locally known mailboxes.
    def sort_mailboxes(mailboxes: set[str]) -> List[str]:
        priorities = {db.account.imap_inbox_folder: 0, db.account.imap_sent_folder: 1}
        return sorted(mailboxes, key=lambda m: priorities.get(m, 2))

    last_mailboxes = {mail.mailbox for mail in db.query_table(MailMessageSQL)}
    with IMAPClient(account=db.account, settings=db.settings) as client:
        current_mailboxes = set(client.list_mailboxes())

        # Process deleted mailboxes.
        for mailbox in last_mailboxes.difference(current_mailboxes):
            delete_mailbox(db=db, client=client, mailbox=mailbox)

        # Process new mailboxes.
        for mailbox in sort_mailboxes(current_mailboxes.difference(last_mailboxes)):
            logger.info(f"New mailbox detected: '{mailbox}'. Syncing...")
            await refresh_mailbox(db=db, client=client, mailbox=mailbox)

        # For unchanged mailboxes, update differences.
        for mailbox in sort_mailboxes(last_mailboxes.intersection(current_mailboxes)):
            logger.info(f"Refreshing unchanged mailbox '{mailbox}'.")
            await refresh_mailbox(db=db, client=client, mailbox=mailbox)

        # Update flags for all current mailboxes.
        for mailbox in sort_mailboxes(current_mailboxes):
            await update_flags_for_mailbox(db, client, mailbox)
