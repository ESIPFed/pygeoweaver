from pydantic import BaseModel
from typing import Optional

class Workflow(BaseModel):
    id: str
    name: Optional[str]
    description: Optional[str]
    owner: Optional[str]
    confidential: Optional[str]
    edges: Optional[str]
    nodes: Optional[str]
