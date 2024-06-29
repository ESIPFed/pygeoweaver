from pydantic import BaseModel

class LogActivity(BaseModel):
    id: str
    operator: str
    category: str
    objectid: str
    objname: str
    operation: str
    