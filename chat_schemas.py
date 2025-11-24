# file: chat_schemas.py
from typing import List, Optional
from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str


class ChatReply(BaseModel):
    reply: str
    suggested_questions: Optional[List[str]] = None
