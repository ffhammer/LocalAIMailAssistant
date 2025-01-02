import os
from pathlib import Path
from datetime import datetime, timedelta
from .accounts_loading import AccountSettings
from .data_formats import MailMessage
from .imap_querying import IMAPClient
from .apple_mail_io import fetch_for_new_mail, load_mail_my_messageId
from hashlib import sha1
from loguru import logger
from tqdm import tqdm
import pandas as pd


class MailDB:
    last_updated_name: str = "last_updated.txt"
    content_folder_name: str = "contents"
    meta_info_name: str = "meta.csv"
    last_updated: datetime = datetime(1970, 1, 1)
    imap_batchsize : int = 50
    csv_columns = ( # aline with MailMessage Model
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
        "Content_SHA"
    )

    time_span_keeping_date: timedelta = timedelta(
        days=31 * 3
    )  # how much is backtracked

    def update(self):
        
        update_start = datetime.now()
        
        fetch_for_new_mail()
        
        with IMAPClient(settings=self.settings) as client:
            new_inbox_mails = client.fetch_emails_after_date(
                mailbox=self.settings.inbox_folder,
                after_date=self.last_updated,
                batch_size=50,
            )
            new_sent_mails = client.fetch_emails_after_date(
                mailbox=self.settings.sent_folder,
                after_date=self.last_updated,
                batch_size=50,
            )
    
        for message in tqdm(new_inbox_mails, desc= "Loading and saving new apple mail inbox"):
            
            if message.email_id in self.meta_info.Message_ID:
                logger.info(f"'{message}' already savec")
                continue
            
            self.load_from_apple_mail_and_save(message.email_id, self.settings.apple_mail_inbox_folder)
        
        for message in tqdm(new_sent_mails, desc= "Loading and saving new apple mail sent"):
            
            if message.email_id in self.meta_info.Message_ID:
                logger.info(f"'{message}' already savec")
                continue
            
            self.load_from_apple_mail_and_save(message.email_id, self.settings.apple_mail_inbox_folder)
        
        self.clean_old_mails()
        
        self.last_updated = update_start
        
        with open(self.path / self.last_updated_path, "w") as f:
            f.write(self.last_updated.isoformat())
        
    def clean_old_mails(self):
        
        dropMask = self.meta_info.Sent_Date < (datetime.now() - self.time_span_keeping_date)
        
        for contentSha in self.meta_info.loc[dropMask, "Content_SHA"].values:
            
            file_path : Path= self.content_folder / contentSha
            try:
                os.remove(file_path)
            except Exception as e:
                logger.info(f"cant delete {file_path} because {e}")

        self.meta_info = self.meta_info[~dropMask]
        
    
    def load_from_apple_mail_and_save(self, messageId : str, appleMailbox: str) -> None:
        
        try: 
            message : MailMessage = load_mail_my_messageId(messageId, account=self.settings.apple_mail_name, mailbox=appleMailbox)
        except RuntimeError as e:
            logger.info(f"Could not load message '{messageId}' from apple mail because of:\n{e}")
            return None
        # overwrite mailbox for safety
        message.Mailbox = appleMailbox
        message_dict = message.model_dump()
        message_dict["Content_SHA"] = sha1(message.Message_ID).hexdigest()
        
        with open(self.content_folder/message_dict["Content_SHA"], "w") as f:
            f.write(message.Content)
        
        self.meta_info[len(self.meta_info)] = pd.Series({row: message_dict[row] for row in self.csv_columns })
        
    def __init__(self, base_dir: str, settings: AccountSettings):
        self.settings : AccountSettings = settings
        self.path = Path(base_dir) / settings.apple_mail_name

        self.path.mkdir(parents=True, exist_ok=True)

        self.content_folder: Path = self.path / self.content_folder_name
        self.content_folder.mkdir(exist_ok=True)
        
        last_updated_path = self.path / self.last_updated_name
        
        if last_updated_path.exists():
            with open(last_updated_path, "r") as f:
                self.lastupdated : datetime = datetime.fromisoformat(f.read())
        else:
            self.lastupdated : datetime = datetime.now() - self.time_span_keeping_date
        
        self.meta_info_path: Path = self.path / self.meta_info_name
        
        if not self.meta_info_path.exists():
            self.meta_info : pd.DataFrame = pd.DataFrame([], columns=self.csv_columns)
        else:
            self.meta_info : pd.DataFrame = pd.read_csv(self.meta_info_path, parse_dates=["Date_Sent", "Date_received"])
            
    