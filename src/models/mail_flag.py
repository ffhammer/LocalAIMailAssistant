from enum import StrEnum


class MailFlag(StrEnum):
    Seen = "seen"
    Flagged = "flagged"
    Answered = "answered"
