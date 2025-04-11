from enum import StrEnum


class MailFlag(StrEnum):
    Seen = r"\Seen"
    Flagged = r"\Flagged"
    Answered = r"\Answered"
