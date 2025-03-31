from datetime import datetime

from pydantic import BaseModel


class UpdateStatus(BaseModel):
    last_update: datetime
