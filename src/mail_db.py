import os
from pathlib import Path
from datetime import datetime, timedelta
import time
from .accounts_loading import AccountSettings
from .data_formats import UnProccesedMailMessage, ProccesedMailMessage
from .email_cleaning import clean_email_content
from .imap_querying import IMAPClient
from .apple_mail_io import fetch_for_new_mail, load_mail_my_messageId
from hashlib import sha1
from loguru import logger
from tqdm import tqdm
import pandas as pd
from typing import Optional
import numpy as np


class MailDB:
    last_updated_name: str = "last_updated.txt"
    content_folder_name: str = "contents"
    meta_info_name: str = "meta.csv"
    last_updated: datetime = datetime(1970, 1, 1)
    imap_batchsize: int = 50
    csv_columns = (
        "Id",
        "Mailbox",
        "Date_Received",
        "Date_Sent",
        "Deleted_Status",
        "Junk_Mail_Status",
        "Message_ID",
        "Reply_To",
        "Sender",
        "Subject",
        "Was_Replied_To",
        "Content_SHA",
    )

    time_span_keeping_date: timedelta = timedelta(
        days=31 * 3
    )  # how much is backtracked

    def update(self):

        update_start = datetime.now()

        fetch_for_new_mail()
        time.sleep(3)

        with IMAPClient(settings=self.settings) as client:
            new_inbox_mails = client.fetch_emails_after_date(
                mailbox=self.settings.imap_inbox_folder,
                after_date=self.last_updated,
                batch_size=50,
            )
            new_sent_mails = client.fetch_emails_after_date(
                mailbox=self.settings.imap_sent_folder,
                after_date=self.last_updated,
                batch_size=50,
            )

        if len(new_sent_mails) == 0 and len(new_inbox_mails) == 0:
            return

        for messageId in tqdm(
            new_inbox_mails, desc="Loading and saving new apple mail inbox"
        ):

            if messageId in self.meta_info.Message_ID:
                logger.info(f"'{messageId}' already saved")
                continue

            self.load_from_apple_mail_and_save(
                messageId, self.settings.apple_mail_inbox_folder
            )

        for messageId in tqdm(
            new_sent_mails, desc="Loading and saving new apple mail sent"
        ):

            if messageId in self.meta_info.Message_ID:
                logger.info(f"'{messageId}' already saved")
                continue

            self.load_from_apple_mail_and_save(
                messageId, self.settings.apple_mail_sent_folder
            )

        self.clean_old_mails()

        self.last_updated = update_start

        last_updated_path = self.path / self.last_updated_name
        with open(last_updated_path, "w") as f:
            f.write(self.last_updated.isoformat())

        self.meta_info.index = np.arange(len(self.meta_info))
        self.meta_info.to_csv(self.meta_info_path, index=False)

    def clean_old_mails(self, reference_date: datetime = None):

        if reference_date is None:
            reference_date = datetime.now()

        drop_mask = self.meta_info.Date_Sent < (
            reference_date - self.time_span_keeping_date
        )

        for content_sha in self.meta_info.loc[drop_mask, "Content_SHA"].values:

            file_path: Path = self.content_folder / content_sha
            try:
                os.remove(file_path)
            except Exception as e:
                logger.info(f"Can't delete {file_path} because {e}")

        self.meta_info = self.meta_info[~drop_mask]

    def load_from_apple_mail_and_save(
        self, message_id: str, apple_mailbox: str
    ) -> None:

        if message_id in self.meta_info.Message_ID.values:
            logger.warning(f"{message_id} alrady saved")
            return

        try:
            message: UnProccesedMailMessage = load_mail_my_messageId(
                message_id, account=self.settings.apple_mail_name, mailbox=apple_mailbox
            )
        except RuntimeError as e:
            logger.info(
                f"Could not load message '{message_id}' from apple mail because of:\n{e}"
            )
            return None

        if message.Message_ID != message_id:
            logger.info(f"{message_id} could not be retrievend from apple mail")
            return

        # overwrite mailbox for safety
        message.Mailbox = apple_mailbox
        message_dict = message.model_dump()
        message_dict["Content_SHA"] = sha1(str(message.Message_ID).encode()).hexdigest()
        message_dict["Date_Sent"] = pd.to_datetime(
            message_dict["Date_Sent"], format="%A, %d. %B %Y at %H:%M:%S"
        )
        message_dict["Date_Received"] = pd.to_datetime(
            message_dict["Date_Received"], format="%A, %d. %B %Y at %H:%M:%S"
        )

        with open(
            self.content_folder / message_dict["Content_SHA"], "w", encoding="utf-8"
        ) as f:
            f.write(str(message.Content))

        new_row = pd.Series({row: message_dict[row] for row in self.csv_columns})
        self.meta_info = pd.concat(
            [self.meta_info, pd.DataFrame([new_row])], ignore_index=True
        )

    def __init__(self, base_dir: str, settings: AccountSettings):
        self.settings: AccountSettings = settings
        self.path = Path(base_dir) / settings.apple_mail_name

        self.path.mkdir(parents=True, exist_ok=True)

        self.content_folder: Path = self.path / self.content_folder_name
        self.content_folder.mkdir(exist_ok=True)

        last_updated_path = self.path / self.last_updated_name

        if last_updated_path.exists():
            with open(last_updated_path, "r") as f:
                self.last_updated: datetime = datetime.fromisoformat(f.read())
        else:
            self.last_updated: datetime = datetime.now() - self.time_span_keeping_date

        self.meta_info_path: Path = self.path / self.meta_info_name

        if not self.meta_info_path.exists():
            self.meta_info: pd.DataFrame = pd.DataFrame([], columns=self.csv_columns)
            self.meta_info.Date_Sent = pd.to_datetime(self.meta_info.Date_Sent)
            self.meta_info.Date_Received = pd.to_datetime(self.meta_info.Date_Received)
        else:
            self.meta_info = pd.read_csv(
                self.meta_info_path, parse_dates=["Date_Sent", "Date_Received"]
            )

    def __len__(self):
        return len(self.meta_info)

    def __getitem__(self, index: int) -> ProccesedMailMessage:

        row = self.meta_info.iloc[index]

        with open(self.content_folder / row.Content_SHA, "r") as f:
            content = clean_email_content(f.read())

        return ProccesedMailMessage(
            Id=row.Id,
            Mailbox=row.Mailbox,
            Content=content,
            Date_Received=row.Date_Received,
            Date_Sent=row.Date_Sent,
            Deleted_Status=row.Deleted_Status,
            Junk_Mail_Status=row.Junk_Mail_Status,
            Message_ID=row.Message_ID,
            Reply_To=row.Reply_To,
            Sender=row.Sender,
            Subject=row.Subject,
            Was_Replied_To=row.Was_Replied_To,
        )

    @property
    def inbox_df(self) -> pd.DataFrame:
        inbox_name = self.settings.apple_mail_inbox_folder
        return self.meta_info.query("Mailbox == @inbox_name").copy()

    # def get_code

    def load_all_inbox_mails(
        self, from_date: Optional[datetime]
    ) -> list[ProccesedMailMessage]:

        inbox_name = self.settings.apple_mail_inbox_folder
        df = self.meta_info.copy()
        df["original_pos"] = df.index.copy()
        df = df.query("Mailbox == @inbox_name")
        if from_date is not None:
            df = df.loc[self.meta_info.Date_Sent > from_date]

        sorted_index = df.sort_values("Date_Sent", ascending=False).original_pos.values
        return [self[i] for i in sorted_index]
