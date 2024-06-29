from pydantic import BaseModel, Field
from typing import Optional

class Environment(BaseModel):
    id: str
    name: str
    type: str
    bin: str
    pyenv: str
    basedir: str
    hostid: Optional[str] = None  # Use Optional to allow for null values
    settings: Optional[str] = None  # Use Optional to allow for null values
