from pydantic import BaseModel
from datetime import datetime
class UnProccesedMailMessage(BaseModel):
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
    
class ProccesedMailMessage(BaseModel):
    Id: int
    Mailbox: str
    Content: str
    Date_Received: datetime
    Date_Sent: datetime
    Deleted_Status: bool
    Junk_Mail_Status: bool
    Message_ID: str
    Reply_To: str
    Sender: str
    Subject: str
    Was_Replied_To: bool
    
    
    
