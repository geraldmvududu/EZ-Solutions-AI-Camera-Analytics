from pydantic import BaseModel


class PushTokenRegister(BaseModel):
    token: str
    platform: str = "expo"


class PushTokenUnregister(BaseModel):
    token: str
