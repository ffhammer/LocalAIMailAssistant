from pydantic import BaseModel

class MailMessage(BaseModel):
    Id: str
    Mailbox: str
    Content: str
    Date_Received: str
    Date_Sent: str
    Deleted_Status: str
    Junk_Mail_Status: str
    Message_ID: str
    Reply_To: str
    Sender: str
    Subject: str
    Was_Replied_To: str