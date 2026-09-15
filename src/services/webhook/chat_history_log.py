from datetime import datetime, timezone
from pywa.types.message import Message
from models.chat_history_model import ChatHistory
from src.core.db import engine

from sqlmodel import Session


def save_message_log(msg: Message, acessed_menu_id: int):
    record: ChatHistory = ChatHistory(
        sender_id=str(msg.from_user.wa_id or ""),
        content=msg.text or "",
        acessed_menu=acessed_menu_id,
        datetime=datetime.now(timezone.utc),
    )
    with Session(engine) as session:
        session.add(record)
        session.commit()
        session.refresh(record)
    return
