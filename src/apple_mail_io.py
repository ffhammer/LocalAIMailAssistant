import subprocess
from typing import List
from .data_formats import UnProccesedMailMessage


def run_apple_script(script: str) -> str:
    process = subprocess.Popen(
        ["/usr/bin/osascript", "-"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    out, err = process.communicate(script)
    if process.returncode != 0:
        raise RuntimeError(f"AppleScript error: {err}")
    return out.strip()


queryFields = {
    "Id": r"""(id of aMessage as text)""",
    "Mailbox": r"""(name of mailbox of aMessage as text)""",
    "Content": r"""(content of aMessage as text)""",
    "Date_Received": r"""date received of aMessage""",
    "Date_Sent": r"""(date sent of aMessage as text)""",
    "Deleted_Status": r"""(deleted status of aMessage as text)""",
    "Junk_Mail_Status": r"""(junk mail status of aMessage as text)""",
    "Message_ID": r"""(message id of aMessage as text)""",
    "Reply_To": r"""(reply to of aMessage as text)""",
    "Sender": r"""(sender of aMessage as text)""",
    "Subject": r"""(subject of aMessage as text)""",
    "Was_Replied_To": r"""(was replied to of aMessage as text)""",
}


def apple_script_snippet_choose_acount_and_mailbox(account, mailbox):
    """selects mailbox as 'targetMailbox' variable"""
    return f"""
        set targetAccount to null
        repeat with acc in accounts
            if name of acc is \"{account}\" then
                set targetAccount to acc
                exit repeat
            end if
        end repeat

        if targetAccount is null then
            error \"Account '{account}' not found.\"
        end if

        set targetMailbox to null
        repeat with mbox in mailboxes of targetAccount
            if name of mbox is \"{mailbox}\" then
                set targetMailbox to mbox
                exit repeat
            end if
        end repeat

        if targetMailbox is null then
            error \"Mailbox '{mailbox}' not found in account '{account}'.\"
        end if
"""


def get_all_mail_ids(account: str, mailbox: str) -> List[str]:
    script = """
    tell application \"Mail\"

{}

        set mailIDs to {{}}
        repeat with msg in messages of targetMailbox
            set end of mailIDs to (id of msg as text) & \"|\"
        end repeat

        return mailIDs as string
    end tell
    """.format(apple_script_snippet_choose_acount_and_mailbox(account, mailbox))
    result = run_apple_script(script)
    return [mail_id.strip() for mail_id in result.split("|") if mail_id.strip()]


def load_mail_from_apple_mail(
    email_id: int, account: str, mailbox: str, id_key: str = "id"
) -> UnProccesedMailMessage:
    """
    Loads a mail message by its ID from the specified account using AppleScript.
    """
    fields = {
        "Id": "id of aMessage as text",
        "Mailbox": "name of mailbox of aMessage as text",
        "Content": "content of aMessage as text",
        "Date_Received": "date received of aMessage as text",
        "Date_Sent": "date sent of aMessage as text",
        "Deleted_Status": "deleted status of aMessage as text",
        "Junk_Mail_Status": "junk mail status of aMessage as text",
        "Message_ID": "message id of aMessage as text",
        "Reply_To": "reply to of aMessage as text",
        "Sender": "sender of aMessage as text",
        "Subject": "subject of aMessage as text",
        "Was_Replied_To": "was replied to of aMessage as text",
    }

    attributes = ' & "|||" & '.join(fields.values())
    script = f"""tell application "Mail"
{apple_script_snippet_choose_acount_and_mailbox(account, mailbox)}

        set theMailID to "{email_id}"
        set aMessage to (first message of targetMailbox whose {id_key} is theMailID)
        delay 0.5
        
        if aMessage is not missing value then
            set output to {attributes}
            return output
        else
            error "Message not found with ID: {email_id}."
        end if
    end tell"""
    output = run_apple_script(script)
    parts = output.split("|||")

    message_data = {key: value for key, value in zip(fields.keys(), parts)}

    return UnProccesedMailMessage(
        Id=message_data["Id"],
        Mailbox=message_data["Mailbox"],
        Content=message_data["Content"],
        Date_Received=message_data["Date_Received"],
        Date_Sent=message_data["Date_Sent"],
        Deleted_Status=message_data["Deleted_Status"],
        Junk_Mail_Status=message_data["Junk_Mail_Status"],
        Message_ID=message_data["Message_ID"],
        Reply_To=message_data["Reply_To"],
        Sender=message_data["Sender"],
        Subject=message_data["Subject"],
        Was_Replied_To=message_data["Was_Replied_To"],
    )


def get_accounts() -> List[str]:
    script = """tell application "Mail"
    set accountList to {}
    repeat with acc in accounts
        set end of accountList to name of acc & "|"
    end repeat
    return accountList as string
end tell"""
    out = run_apple_script(script).strip(" \n|").split("|")
    return out


def get_mailboxes(account):
    script = """tell application "Mail"
    set mailboxDetails to {}
    -- Find the account with the specified name
    set targetAccount to null
    repeat with acc in accounts
        if name of acc is "{}" then
            set targetAccount to acc
            exit repeat
        end if
    end repeat
    
    -- Return an error if the account is not found
    if targetAccount is null then
        error "Account '{}' not found."
    end if
    
    -- Get all mailboxes for the target account
    set accountMailboxes to mailboxes of targetAccount
    repeat with mbox in accountMailboxes
        set mboxName to name of mbox
        set mboxDetails to mboxName
        set end of mailboxDetails to mboxDetails & "|"
    end repeat
    
    return mailboxDetails as string
end tell
"""
    out = run_apple_script(script.format("{ }", account, account))
    return [mailbox for mailbox in out.strip("|\n ").split("|")]


def fetch_for_new_mail():
    try:
        run_apple_script("""
    tell application "Mail"
        check for new mail
    end tell
    """)
    except RuntimeError as e:
        return RuntimeError(f"Could not fetch for new mails because of: {e}")

def load_mail_my_messageId(email_id: int, account: str, mailbox: str) -> UnProccesedMailMessage:
    return load_mail_from_apple_mail(
        email_id=email_id, account=account, mailbox=mailbox, id_key="message id"
    )
    
    
def escape_applescript_string(text: str) -> str:
    """
    Escapes problematic characters in a string for use in AppleScript.
    """
    if not isinstance(text, str):
        raise ValueError("Content must be a string")
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def load_reply_window_for_message(apple_mail_id: int, content: str, account: str, mailbox: str):
    """
    Loads a reply window for a given message, safely handling problematic content strings.
    """
    sanitized_content = escape_applescript_string(content)
        
    return run_apple_script(f"""
tell application "Mail"
{apple_script_snippet_choose_acount_and_mailbox(account=account, mailbox=mailbox)}
    set targetMessage to the first message of targetMailbox whose id is {apple_mail_id}
    set replyMessage to reply targetMessage
    tell replyMessage
        set content to "{sanitized_content}"
        set visible to true
    end tell
end tell
""")
        


