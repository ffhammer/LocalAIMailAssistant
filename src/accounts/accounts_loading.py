from typing import Optional

import yaml
from pydantic import BaseModel


class AccountSettings(BaseModel):
    name: str
    password: str
    imap_server: str
    user: str
    apple_mail_name: str
    imap_inbox_folder: str
    imap_sent_folder: str
    apple_mail_inbox_folder: str
    apple_mail_sent_folder: str
    user_for_mail: str
    input_port: Optional[int] = 993  # default for imapblib

    def __repr__(self):
        return (
            f"AccountSettings(imap_server={self.imap_server}, user={self.user}, "
            f"apple_mail_name={self.apple_mail_name}, input_port={self.input_port}, password='***REDACTED***')"
        )

    def __str__(self):
        return self.__repr__()


def load_accounts(path: str) -> dict[str, AccountSettings]:
    with open(path, "r") as f:
        yaml_dict = yaml.safe_load(f)

        return {key: AccountSettings(**val) for key, val in yaml_dict.items()}
