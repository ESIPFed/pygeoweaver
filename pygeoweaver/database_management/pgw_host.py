from pydantic import BaseModel, Field
from typing import Optional, Set

class Host(BaseModel):
    id: str
    name: str
    ip: str
    port: str
    username: str
    owner: str
    type: str
    url: str
    confidential: bool
    envs: Optional[Set[str]] = None

