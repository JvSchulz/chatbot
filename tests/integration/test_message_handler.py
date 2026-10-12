"""
Testes de integração do tratamento de mensagens, callbacks e status com banco SQLite em memória.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from sqlmodel import Session, select
from pywa.types import MessageStatus
from pywa.types.base_update import User
from src.models.chat_history_model import ChatHistory
from src.models.menu_model import Menu
from src.models.user_session_model import UserSession
from src.services.webhook.message_handler import (
    ACTION_ASK_QUESTION,
    ACTION_ROOT,
    MODEL_UNAVAILABLE_MESSAGE,
    NO_ROOT_MESSAGE,
    handle_callback,
    handle_message,
    handle_status,
)

ROOT_MESSAGE = "Bem-vindo ao atendimento"
BSUID = "BR.1234567890123"


@pytest.fixture(name="callback_factory", params=["button", "selection"])
def callback_factory_fixture(request, button_factory, selection_factory):
    """Executa cada teste de callback para botão e para linha de lista."""
    return button_factory if request.param == "button" else selection_factory


@pytest.fixture(name="tree")
def tree_fixture(session: Session) -> dict[str, Menu]:
    """Raiz com dois filhos, sendo que 'cursos' possui uma folha 'engenharia'."""
    root = Menu(name="menu_inicio", selection_name="Início", message=ROOT_MESSAGE)
    session.add(root)
    session.commit()
    courses = Menu(name="Cursos", selection_name="Cursos", message="Nossos cursos", parent_id=root.id)
    office = Menu(name="Secretaria", selection_name="Secretaria", message="Atendimento", parent_id=root.id)
    session.add(courses)
    session.add(office)
    session.commit()
    engineering = Menu(name="Engenharia", selection_name="Eng", message="Info Eng", parent_id=courses.id)
    session.add(engineering)
    session.commit()
    return {"root": root, "courses": courses, "office": office, "engineering": engineering}


def _rows(session: Session) -> list[ChatHistory]:
    session.expire_all()
    return list(session.exec(select(ChatHistory).order_by(ChatHistory.id)).all())  # type: ignore


def _stored_session(session: Session, user_id: str = BSUID) -> UserSession:
    session.expire_all()
    return session.exec(select(UserSession).where(UserSession.user_id == user_id)).one()


def _sent(client: MagicMock) -> dict:
    client.send_message.assert_called_once()
    return client.send_message.call_args.kwargs


def test_callback_without_user_sends_nothing_and_writes_nothing(
    session: Session, mock_wa_client: MagicMock, callback_factory, caplog
):
    callback = callback_factory()
    callback.from_user = None

    with caplog.at_level("WARNING"):
        handle_callback(mock_wa_client, callback, session)

    mock_wa_client.send_message.assert_not_called()
    assert _rows(session) == []
    assert caplog.messages == ["[CALLBACK] Evento recebido sem BSUID de usuário válido."]


def test_callback_action_root_sends_the_root_message(
    session: Session, mock_wa_client: MagicMock, callback_factory, tree
):
    handle_callback(mock_wa_client, callback_factory(data=ACTION_ROOT, title="Voltar ao início"), session)

    sent = _sent(mock_wa_client)
    assert sent["text"] == ROOT_MESSAGE
    assert [b.callback_data for b in sent["buttons"]][-1] == ACTION_ASK_QUESTION


def test_callback_ask_question_sends_the_unavailable_notice_with_the_root_options(
    session: Session, mock_wa_client: MagicMock, callback_factory, tree
):
    handle_callback(mock_wa_client, callback_factory(data=ACTION_ASK_QUESTION), session)

    sent = _sent(mock_wa_client)
    assert sent["text"] == MODEL_UNAVAILABLE_MESSAGE
    assert [b.callback_data for b in sent["buttons"]][:2] == [
        f"menu:{tree['courses'].id}", f"menu:{tree['office'].id}",
    ]


def test_callback_menu_logs_the_click_and_the_reply_and_tracks_the_menu(
    session: Session, mock_wa_client: MagicMock, callback_factory, tree
):
    engineering = tree["engineering"]

    handle_callback(
        mock_wa_client, callback_factory(data=f"menu:{engineering.id}", title="Engenharia"), session
    )

    click, reply = _rows(session)
    assert (click.role, click.content, click.menu_id) == ("user", "Engenharia", engineering.id)
    assert (click.user_id, click.wa_id) == (BSUID, "554798765432")
    assert (reply.role, reply.menu_id) == ("bot", engineering.id)
    assert reply.content == _sent(mock_wa_client)["text"]
    assert _stored_session(session).current_menu_id == engineering.id


@pytest.mark.parametrize("payload", [ACTION_ROOT, ACTION_ASK_QUESTION, "menu:abc"])
def test_returning_to_the_root_clears_the_current_menu(
    session: Session, mock_wa_client: MagicMock, callback_factory, tree, payload: str
):
    handle_callback(mock_wa_client, callback_factory(data=f"menu:{tree['engineering'].id}"), session)
    assert _stored_session(session).current_menu_id == tree["engineering"].id

    handle_callback(mock_wa_client, callback_factory(data=payload), session)

    assert _stored_session(session).current_menu_id is None


def test_selecting_the_root_menu_clears_the_current_menu(
    session: Session, mock_wa_client: MagicMock, callback_factory, tree
):
    handle_callback(mock_wa_client, callback_factory(data=f"menu:{tree['engineering'].id}"), session)

    handle_callback(mock_wa_client, callback_factory(data=f"menu:{tree['root'].id}"), session)

    assert _stored_session(session).current_menu_id is None


def test_a_deleted_menu_click_clears_the_current_menu(
    session: Session, mock_wa_client: MagicMock, callback_factory, tree
):
    handle_callback(mock_wa_client, callback_factory(data=f"menu:{tree['engineering'].id}"), session)

    handle_callback(mock_wa_client, callback_factory(data="menu:99999"), session)

    assert _stored_session(session).current_menu_id is None


def test_a_text_message_after_navigating_clears_the_current_menu(
    session: Session, mock_wa_client: MagicMock, callback_factory, message_factory, tree
):
    handle_callback(mock_wa_client, callback_factory(data=f"menu:{tree['engineering'].id}"), session)

    handle_message(mock_wa_client, message_factory(), session)

    assert _stored_session(session).current_menu_id is None


def test_callback_menu_of_the_root_renders_the_root_view(
    session: Session, mock_wa_client: MagicMock, callback_factory, tree
):
    handle_callback(mock_wa_client, callback_factory(data=f"menu:{tree['root'].id}", title="Início"), session)

    assert _sent(mock_wa_client)["text"] == ROOT_MESSAGE
    click = _rows(session)[0]
    assert click.menu_id == tree["root"].id


@pytest.mark.parametrize(
    "payload",
    ["menu:abc", "menu:", "menu:-3", "menu:99999999999999999999999", "outro:1", "", "action:desconhecida"],
)
def test_callback_with_malformed_payload_sends_the_root_menu(
    session: Session, mock_wa_client: MagicMock, callback_factory, tree, payload: str
):
    handle_callback(mock_wa_client, callback_factory(data=payload, title="Estranho"), session)

    sent = _sent(mock_wa_client)
    assert sent["text"] == ROOT_MESSAGE
    click = _rows(session)[0]
    assert (click.role, click.content, click.menu_id) == ("user", "Estranho", None)


def test_callback_for_a_deleted_menu_is_logged_without_menu_and_falls_back_to_the_root(
    session: Session, mock_wa_client: MagicMock, callback_factory, tree
):
    handle_callback(mock_wa_client, callback_factory(data="menu:99999", title="Antigo"), session)

    sent = _sent(mock_wa_client)
    assert sent["text"].startswith("Esse menu não está mais disponível")
    click = _rows(session)[0]
    assert (click.content, click.menu_id) == ("Antigo", None)


def test_callback_refreshes_the_session_timestamp(
    session: Session, mock_wa_client: MagicMock, callback_factory, tree
):
    session.add(UserSession(user_id=BSUID, last_interaction_at=datetime.now(timezone.utc) - timedelta(minutes=10)))
    session.commit()

    handle_callback(mock_wa_client, callback_factory(data=ACTION_ROOT), session)

    assert datetime.now(timezone.utc) - _stored_session(session).last_interaction_at < timedelta(minutes=1)


def test_callback_stores_the_wa_id_on_the_session(
    session: Session, mock_wa_client: MagicMock, callback_factory, tree
):
    handle_callback(mock_wa_client, callback_factory(wa_id="554798765432", data=ACTION_ROOT), session)

    assert _stored_session(session).wa_id == "554798765432"


def test_callback_logs_the_masked_user_and_the_menu_id(
    session: Session, mock_wa_client: MagicMock, callback_factory, tree, caplog
):
    engineering = tree["engineering"]

    with caplog.at_level("INFO"):
        handle_callback(mock_wa_client, callback_factory(data=f"menu:{engineering.id}"), session)

    assert f"[CALLBACK] Usuário: ***0123 | Menu: {engineering.id}" in caplog.messages


def test_callback_without_title_is_logged_with_empty_content(
    session: Session, mock_wa_client: MagicMock, callback_factory, tree
):
    callback = callback_factory(data=ACTION_ROOT)
    callback.title = None

    handle_callback(mock_wa_client, callback, session)

    assert _rows(session)[0].content == ""


def test_callback_from_a_user_without_phone_replies_to_the_bsuid(
    session: Session, mock_wa_client: MagicMock, callback_factory, tree
):
    handle_callback(mock_wa_client, callback_factory(wa_id=None, data=ACTION_ROOT), session)

    assert _sent(mock_wa_client)["to"] == BSUID
    assert _stored_session(session).wa_id is None


def test_callback_from_a_12_digit_phone_replies_to_the_normalized_number(
    session: Session, mock_wa_client: MagicMock, callback_factory, tree
):
    handle_callback(mock_wa_client, callback_factory(wa_id="554797865306", data=ACTION_ROOT), session)

    assert _sent(mock_wa_client)["to"] == "5547997865306"


def test_callback_without_root_replies_unavailable(session: Session, mock_wa_client: MagicMock, callback_factory):
    handle_callback(mock_wa_client, callback_factory(data=ACTION_ROOT), session)

    sent = _sent(mock_wa_client)
    assert sent["text"] == NO_ROOT_MESSAGE
    assert sent["buttons"] is None


def test_callback_does_not_log_a_bot_row_when_the_send_fails(
    session: Session, mock_wa_client: MagicMock, callback_factory, tree
):
    mock_wa_client.send_message.side_effect = RuntimeError("Meta fora do ar")

    handle_callback(mock_wa_client, callback_factory(data=ACTION_ROOT, title="Início"), session)

    assert [row.role for row in _rows(session)] == ["user"]



def test_text_message_sends_the_root_view_and_logs_both_rows(
    session: Session, mock_wa_client: MagicMock, message_factory, tree
):
    handle_message(mock_wa_client, message_factory(wa_id="5511999998888", text="Olá, gostaria de informações"), session)

    sent = _sent(mock_wa_client)
    assert sent["to"] == "5511999998888"
    assert sent["text"] == ROOT_MESSAGE
    assert [b.callback_data for b in sent["buttons"]] == [
        f"menu:{tree['courses'].id}", f"menu:{tree['office'].id}", ACTION_ASK_QUESTION,
    ]
    user_row, bot_row = _rows(session)
    assert (user_row.role, user_row.user_id, user_row.wa_id) == ("user", BSUID, "5511999998888")
    assert user_row.content == "Olá, gostaria de informações"
    assert (bot_row.role, bot_row.user_id, bot_row.content) == ("bot", BSUID, ROOT_MESSAGE)


def test_text_message_logs_the_masked_user(
    session: Session, mock_wa_client: MagicMock, message_factory, tree, caplog
):
    with caplog.at_level("INFO"):
        handle_message(mock_wa_client, message_factory(), session)

    assert "[INBOUND] Tipo: texto | Usuário: ***0123" in caplog.messages


def test_text_message_from_a_user_without_phone_is_answered_at_the_bsuid(
    session: Session, mock_wa_client: MagicMock, message_factory, tree
):
    handle_message(mock_wa_client, message_factory(wa_id=None, bsuid="BR.1000000000001"), session)

    assert _sent(mock_wa_client)["to"] == "BR.1000000000001"
    user_row, bot_row = _rows(session)
    assert (user_row.user_id, user_row.wa_id) == ("BR.1000000000001", None)
    assert bot_row.user_id == "BR.1000000000001"


def test_text_message_refreshes_and_persists_the_session(
    session: Session, mock_wa_client: MagicMock, message_factory, tree
):
    session.add(UserSession(user_id=BSUID, last_interaction_at=datetime.now(timezone.utc) - timedelta(minutes=5)))
    session.commit()

    handle_message(mock_wa_client, message_factory(), session)

    assert datetime.now(timezone.utc) - _stored_session(session).last_interaction_at < timedelta(minutes=1)


def test_text_message_stores_the_wa_id_on_the_session(
    session: Session, mock_wa_client: MagicMock, message_factory, tree
):
    handle_message(mock_wa_client, message_factory(wa_id="5511999998888"), session)

    assert _stored_session(session).wa_id == "5511999998888"


def test_text_message_after_expiry_resets_a_conversational_session_and_saves_it(
    session: Session, mock_wa_client: MagicMock, message_factory, tree
):
    session.add(
        UserSession(
            user_id=BSUID,
            mode="conversational",
            current_menu_id=tree["courses"].id,
            last_interaction_at=datetime.now(timezone.utc) - timedelta(minutes=16),
        )
    )
    session.commit()

    handle_message(mock_wa_client, message_factory(), session)

    assert _sent(mock_wa_client)["text"] == ROOT_MESSAGE
    stored = _stored_session(session)
    assert (stored.mode, stored.current_menu_id) == ("menu", None)


def test_text_message_in_an_active_conversational_session_gets_the_unavailable_notice(
    session: Session, mock_wa_client: MagicMock, message_factory, tree
):
    session.add(
        UserSession(
            user_id=BSUID,
            mode="conversational",
            last_interaction_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
    )
    session.commit()

    handle_message(mock_wa_client, message_factory(), session)

    assert _sent(mock_wa_client)["text"] == MODEL_UNAVAILABLE_MESSAGE


def test_text_message_without_root_replies_unavailable(
    session: Session, mock_wa_client: MagicMock, message_factory
):
    handle_message(mock_wa_client, message_factory(), session)

    sent = _sent(mock_wa_client)
    assert (sent["text"], sent["buttons"]) == (NO_ROOT_MESSAGE, None)


def test_text_message_without_bsuid_is_ignored(
    session: Session, mock_wa_client: MagicMock, message_factory, caplog
):
    with caplog.at_level("WARNING"):
        handle_message(mock_wa_client, message_factory(bsuid=""), session)

    mock_wa_client.send_message.assert_not_called()
    assert _rows(session) == []
    assert caplog.messages == ["[INBOUND] Mensagem recebida sem BSUID de usuário válido."]


def test_text_message_with_failed_dispatch_logs_no_bot_row_but_refreshes_the_session(
    session: Session, mock_wa_client: MagicMock, message_factory, tree
):
    mock_wa_client.send_message.side_effect = RuntimeError("Meta fora do ar")

    handle_message(mock_wa_client, message_factory(), session)

    assert [row.role for row in _rows(session)] == ["user"]
    assert datetime.now(timezone.utc) - _stored_session(session).last_interaction_at < timedelta(minutes=1)


def _status(user_id: str | None, wa_id: str | None = None, error=None, name: str = "delivered") -> MagicMock:
    status = MagicMock(spec=MessageStatus)
    status.id = "wamid.STATUS_001"
    status.status.value = name
    if user_id is None:
        status.from_user = None
    else:
        user = MagicMock(spec=User)
        user.bsuid = user_id
        user.wa_id = wa_id
        status.from_user = user
    status.error = error
    return status


def test_status_success_logs_masked_recipient_and_delivery_status(mock_wa_client: MagicMock, caplog):
    with caplog.at_level("INFO"):
        handle_status(mock_wa_client, _status("BR.1234567890123"))

    assert "[STATUS UPDATE] Destino: ***0123 | Status: delivered" in caplog.text


def test_status_falls_back_to_the_wa_id_when_the_bsuid_is_missing(mock_wa_client: MagicMock, caplog):
    with caplog.at_level("INFO"):
        handle_status(mock_wa_client, _status("", wa_id="554799998888"))

    assert "Destino: ***8888" in caplog.text


def test_status_with_error_logs_code_and_message(mock_wa_client: MagicMock, caplog):
    err = MagicMock()
    err.code = 131047
    err.message = "Re-engagement message window expired"
    err.details = "Customer service window closed"

    with caplog.at_level("WARNING"):
        handle_status(mock_wa_client, _status("BR.1234567890123", error=err, name="failed"))

    assert "[STATUS UPDATE] Destino: ***0123 | Status: failed" in caplog.text
    assert "Erro 131047: Re-engagement message window expired (Customer service window closed)" in caplog.text


def test_status_without_user_logs_unknown_recipient(mock_wa_client: MagicMock, caplog):
    with caplog.at_level("INFO"):
        handle_status(mock_wa_client, _status(None, name="sent"))

    assert "[STATUS UPDATE] Destino: Desconhecido | Status: sent" in caplog.text


def test_status_accepts_a_plain_string_status(mock_wa_client: MagicMock, caplog):
    status = _status("BR.1234567890123")
    status.status = "read"

    with caplog.at_level("INFO"):
        handle_status(mock_wa_client, status)

    assert "Status: read" in caplog.text
