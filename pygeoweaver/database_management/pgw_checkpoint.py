from pydantic import BaseModel
from typing import Optional
import uuid
from datetime import datetime

class Checkpoint(BaseModel):
    id: Optional[uuid.UUID]
    executionId: str
    edges: str
    nodes: str
    workflow: Optional[str]
    createdAt: Optional[datetime]
