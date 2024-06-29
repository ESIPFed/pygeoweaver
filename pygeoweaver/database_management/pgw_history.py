from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class History(BaseModel):
    history_id: str
    history_input: Optional[str]
    history_output: Optional[str]
    history_begin_time: Optional[datetime]
    history_end_time: Optional[datetime]
    history_notes: Optional[str]
    history_process: Optional[str]
    host_id: Optional[str]
    indicator: Optional[str]
