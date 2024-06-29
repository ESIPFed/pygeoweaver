from pydantic import BaseModel
from typing import Optional

class GWProcess(BaseModel):
    id: str
    name: Optional[str]
    description: Optional[str]
    code: Optional[str]
    lang: Optional[str]
    owner: Optional[str]
    confidential: Optional[bool]

