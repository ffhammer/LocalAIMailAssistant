from enum import StrEnum


class MailFlag(StrEnum):
    Seen = "\Seen"
    Flagged = "\Flagged"
    Answered = "\Answered"
