"""
Testes de integração para o registro do histórico de mensagens na transação do evento.
"""

from datetime import datetime, timedelta, timezone
from sqlmodel import Session, col, select
from src.models.chat_history_model import ChatHistory
from src.models.menu_model import Menu
from src.services.webhook.chat_history_log import save_bot_reply_log, save_user_log
from src.services.webhook.message_handler import MessageContext


def _context(
    session: Session,
    user_id: str = "BR.1000000000001",
    wa_id: str | None = "5511999998888",
    text: str = "Olá, gostaria de informações",
) -> MessageContext:
    return MessageContext(
        session=session,
        user_id=user_id,
        wa_id=wa_id,
        reply_to=wa_id or user_id,
        user_name="Roberto",
        message_text=text,
    )


def _add_menu(session: Session) -> int:
    menu = Menu(name="Cursos", selection_name="Cursos", message="m")
    session.add(menu)
    session.commit()
    assert menu.id is not None
    return menu.id


def test_save_user_log_persists_inbound_row(session: Session):
    before = datetime.now(timezone.utc)

    save_user_log(_context(session))

    row = session.exec(select(ChatHistory)).one()
    assert (row.user_id, row.wa_id, row.role) == ("BR.1000000000001", "5511999998888", "user")
    assert row.content == "Olá, gostaria de informações"
    assert row.menu_id is None
    assert before - timedelta(seconds=1) <= row.created_at <= datetime.now(timezone.utc)


def test_save_user_log_without_wa_id_stores_null(session: Session):
    save_user_log(_context(session, wa_id=None))

    assert session.exec(select(ChatHistory)).one().wa_id is None


def test_save_user_log_records_the_selected_menu(session: Session):
    menu_id = _add_menu(session)

    save_user_log(_context(session, text="Cursos"), menu_id=menu_id)

    row = session.exec(select(ChatHistory)).one()
    assert (row.role, row.content, row.menu_id) == ("user", "Cursos", menu_id)


def test_save_bot_reply_log_persists_bot_row(session: Session):
    menu_id = _add_menu(session)

    save_bot_reply_log(_context(session), "Aqui estão as opções de pós-graduação:", menu_id=menu_id)

    row = session.exec(select(ChatHistory)).one()
    assert (row.user_id, row.role, row.menu_id) == ("BR.1000000000001", "bot", menu_id)
    assert row.content == "Aqui estão as opções de pós-graduação:"


def test_save_bot_reply_log_defaults_to_no_menu(session: Session):
    save_bot_reply_log(_context(session), "Oi")

    assert session.exec(select(ChatHistory)).one().menu_id is None


def test_log_functions_do_not_commit_the_transaction(session: Session):
    save_user_log(_context(session))
    save_bot_reply_log(_context(session), "Oi")

    session.rollback()

    assert session.exec(select(ChatHistory)).all() == []


def test_log_rows_are_committed_with_the_caller_transaction(session: Session):
    save_user_log(_context(session))
    save_bot_reply_log(_context(session), "Oi")

    session.commit()

    assert [row.role for row in session.exec(select(ChatHistory).order_by(col(ChatHistory.id))).all()] == ["user", "bot"]
