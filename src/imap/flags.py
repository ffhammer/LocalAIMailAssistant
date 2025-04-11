import re
from typing import Optional

from loguru import logger

from ..models import MailFlag

FLAG_PATTERN = re.compile(r"(\d+)\s+\((?:UID\s+\d+\s+)?FLAGS\s+\((.*?)\)\)")


def parse_all_flags(data: str) -> Optional[tuple[int, tuple[str, ...]]]:
    """
    Parse flags from a line of IMAP fetch response.
    Accepts optional UID field.

    Example inputs:
      '1 (FLAGS (\\Seen))'
      '1 (UID 202 FLAGS (\\Seen))'

    Returns:
      Tuple of (sequence_number, (flags...)) or None if no match.
    """
    match = FLAG_PATTERN.search(data)
    if match:
        flags = match.group(2).split()
        return int(match.group(1)), tuple(flags)
    else:
        logger.debug(f"Can't match flags regex for {data}")
        return None


def parse_flags_filtered(data: list[bytes]) -> dict[int, list[MailFlag]]:
    """
    Parse flags from a client.fetch(msg_range, '(FLAGS)') using re
    If can't match, does not include id in result dict.
    """
    result = {}
    for item in data:
        val = parse_all_flags(item.decode())

        if val is None:
            continue
        msg_id, flags = val

        parsed_flags = [i.lstrip("$").title() for i in flags]

        result[msg_id] = tuple(
            MailFlag(flag)
            for flag in parsed_flags
            if flag in MailFlag._value2member_map_
        )

    return result
