import re

from loguru import logger

from ..models import MailFlag


def parse_flags(data: list[bytes]) -> dict[int, list[MailFlag]]:
    """
    Parse flags from a client.fetch(msg_range, '(FLAGS)') using re
    If can't match, does not include id in result dict.
    """
    pattern = re.compile(rb"(\d+)\s+\(FLAGS\s+\((.*?)\)\)")
    result = {}
    for item in data:
        match = pattern.match(item)
        if match:
            msg_id = int(match.group(1))
            flags = match.group(2).decode().split()
            parsed_flags = [i.lstrip(r"\$").lower() for i in flags]

            result[msg_id] = tuple(
                MailFlag(flag)
                for flag in parsed_flags
                if flag in MailFlag._value2member_map_
            )
        else:
            logger.debug(f"Can't match flags regex for {item.decode()}")
    return result
