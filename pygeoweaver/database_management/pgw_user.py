from pydantic import BaseModel
from typing import Optional
from datetime import date
from typing import Optional

class GWUser(BaseModel):
    id: str
    username: str
    password: str
    role: Optional[str]
    email: Optional[str]
    isactive: Optional[bool]
    registration_date: Optional[date]
    last_login_date: Optional[date]
    loggedIn: Optional[bool]
