from __future__ import annotations

import base64
import email
import hashlib
import re
from datetime import datetime
from email.message import EmailMessage, Message
from email.utils import parseaddr
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import bleach.sanitizer
import chardet
from bleach import Cleaner
from bleach.css_sanitizer import CSSSanitizer
from bs4 import BeautifulSoup
from loguru import logger

from src.models import Attachment, MailFlag, MailMessage  # adapt import path

# ---------------------------------------------------------------------------
# constants & regex helpers
# ---------------------------------------------------------------------------
UNSAFE_EXT = {".exe", ".js", ".vbs", ".bat", ".com", ".scr", ".msi", ".cmd"}
CID_RE = re.compile(r"cid:([\w\.\-@]+)", re.I)

# ---------------------------------------------------------------------------
# low‑level helpers (decode, security, etc.)
# ---------------------------------------------------------------------------


def _decode_bytes(part: Message) -> bytes:
    """Return decoded payload or b'' when empty."""
    return part.get_payload(decode=True) or b""


def _decode_text(data: bytes, charset: Optional[str]) -> str:
    if not data:
        return ""
    if charset:
        try:
            return data.decode(charset, "replace")
        except LookupError:
            pass
    return data.decode(chardet.detect(data)["encoding"] or "utf-8", "replace")


def _attachment_safe(filename: str, mime: str) -> bool:
    ext = Path(filename).suffix.lower()
    return ext not in UNSAFE_EXT and not mime.startswith(
        ("application/x-ms", "application/x-dosexec")
    )


def _auth_results(msg: Message) -> Tuple[Optional[str], Optional[str]]:
    dkim = dmarc = None
    for h in msg.get_all("Authentication-Results", failobj=[]):
        low = h.lower()
        if "dkim=" in low and dkim is None:
            dkim = low.split("dkim=")[1].split()[0]
        if "dmarc=" in low and dmarc is None:
            dmarc = low.split("dmarc=")[1].split()[0]
    return dkim, dmarc


def _parse_flags(flag_hdr: str) -> Set[MailFlag]:
    return {f for f in MailFlag if f.value in flag_hdr}


def _safe_date(hdr: Optional[str]) -> datetime:
    try:
        tpl = email.utils.parsedate_tz(hdr)
        if tpl and tpl[9] is not None:  # Check if timezone offset is present
            return datetime(
                *tpl[:6], tzinfo=datetime.timezone(datetime.timedelta(seconds=tpl[9]))
            )
        return datetime(*tpl[:6]) if tpl else datetime.min
    except Exception:
        return datetime.min


# ---------------------------------------------------------------------------
# MIME walk & collection
# ---------------------------------------------------------------------------


def _collect_parts(
    msg: EmailMessage,
) -> Tuple[str, str, str, Dict[str, Tuple[bytes, str]], List[Attachment]]:
    plain = html = html_raw = None
    cid_map: Dict[str, Tuple[bytes, str]] = {}
    attachments: List[Attachment] = []

    for part in msg.walk():
        if part.is_multipart():
            continue
        ctype = part.get_content_type()
        payload = _decode_bytes(part)
        if not payload:
            continue

        disp = (part.get("Content-Disposition") or "").lower()
        cid = part.get("Content-ID", "").strip("<>")
        charset = part.get_content_charset()
        filename = part.get_filename() or cid or hashlib.sha1(payload).hexdigest()[:10]

        try:
            if ctype == "text/plain" and plain is None:
                plain = _decode_text(payload, charset)
            elif ctype == "text/html" and html is None:
                html_raw = _decode_text(payload, charset)
                html = html_raw
            else:
                inline = "inline" in disp or bool(cid)
                safe = _attachment_safe(filename, ctype)
                if inline and cid:
                    cid_map[cid] = (payload, ctype)
                else:
                    attachments.append(
                        Attachment(
                            part_id=part.get_param("part", header=""),
                            size=len(payload),
                            possibly_dangerous=int(not safe),
                            filename=filename,
                            path=None,
                            mime_type=ctype,
                            email=None,
                            email_message_id=msg.get("Message-ID", ""),
                        )
                    )
        except Exception as e:
            logger.warning(f"Attachment processing failed: {e}")
            continue

    return plain or "", html or "", html_raw or "", cid_map, attachments


# ---------------------------------------------------------------------------
# HTML utilities
# ---------------------------------------------------------------------------


def _inline_cids(html: str, cid_map: Dict[str, Tuple[bytes, str]]) -> str:
    def repl(m):
        cid = m.group(1)
        if cid in cid_map:
            data, mime = cid_map[cid]
            return f"data:{mime};base64,{base64.b64encode(data).decode()}"
        return m.group(0)

    return CID_RE.sub(repl, html)


def _clean_html(html: str, cid_map: Dict[str, Tuple[bytes, str]]) -> str:
    try:
        html = _inline_cids(html, cid_map)
        allowed_tags = bleach.sanitizer.ALLOWED_TAGS | {"img", "style", "link"}
        allowed_attrs = {
            **bleach.sanitizer.ALLOWED_ATTRIBUTES,
            "img": ["src", "alt"],
            "link": ["rel", "href"],
        }
        cleaner = Cleaner(
            tags=allowed_tags,
            attributes=allowed_attrs,
            css_sanitizer=CSSSanitizer(),
            protocols=["http", "https", "data"],
            strip=True,
        )
        return cleaner.clean(html)
    except Exception as e:
        logger.error(f"HTML sanitisation failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# main high‑level function
# ---------------------------------------------------------------------------


def parse_message(
    msg: EmailMessage, mailbox: str, uid: int
) -> Optional[Tuple[MailMessage, List[Attachment]]]:
    """Return (MailMessage, attachments) or None on fatal error."""
    try:
        plain, html, html_raw, cid_map, attachments = _collect_parts(msg)

        # generate fallback plain if needed
        if not plain and html_raw:
            try:
                plain = BeautifulSoup(html_raw, "html.parser").get_text(separator="\n")
            except Exception as e:
                logger.warning(f"BeautifulSoup fallback failed: {e}")
                plain = ""

        html_clean = _clean_html(html, cid_map) if html else None

        from_hdr = msg.get("From", "")
        disp_name, addr = parseaddr(from_hdr)
        mismatch = bool(disp_name) and disp_name.lower().strip() not in addr.lower()
        dkim, dmarc = _auth_results(msg)

        flags = _parse_flags(msg.get("Flags", ""))

        mail = MailMessage(
            mailbox=mailbox,
            date_received=_safe_date(msg.get("Date")),
            date_sent=_safe_date(msg.get("Date")),
            deleted_status=MailFlag.Deleted in flags,
            junk_mail_status="Junk"
            in (msg.get("X-Folder", "") + msg.get("X-Spam-Flag", "")),
            message_id=msg.get("Message-ID", ""),
            reply_to=msg.get("In-Reply-To"),
            sender=addr,
            subject=msg.get("Subject"),
            was_replied_to=msg.get("In-Reply-To") is not None,
            uid=uid,
            display_name_mismatch=mismatch,
            dkim_result=dkim,
            dmarc_result=dmarc,
            plain_text=plain,
            html_clean=html_clean,
            html_raw=html_raw,
            seen=MailFlag.Seen in flags,
            answered=MailFlag.Answered in flags,
            flagged=MailFlag.Flagged in flags,
        )

        for att in attachments:
            att.email = mail

        return mail, attachments

    except Exception as fatal:
        logger.error(f"parse_message failed for uid={uid}: {fatal}")
        return None
