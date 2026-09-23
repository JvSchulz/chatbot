"""
Testes unitários para cobrir ramificações de eventos e casos de borda em message_handler.
"""

from unittest.mock import MagicMock
from sqlmodel import Session
from pywa.client import WhatsApp
from pywa.types import CallbackButton, CallbackSelection, Message, MessageStatus
from pywa.types.base_update import User
from src.models.menu_model import Menu
from src.services.webhook.message_handler import (
    ACTION_ASK_QUESTION,
    ACTION_ROOT,
    SESSION_MODE_CONVERSATIONAL,
    build_mode_response,
    extract_message_context,
    handle_callback_button,
    handle_callback_selection,
    handle_menu_navigation,
    handle_message,
    handle_status,
)


def test_handle_callback_button_without_user_id(mock_wa_client: MagicMock):
    """
    CallbackButton sem from_user deve registrar aviso e abortar sem falhas.
    """
    btn = MagicMock(spec=CallbackButton)
    btn.from_user = None

    handle_callback_button(client=mock_wa_client, btn=btn)

    mock_wa_client.send_message.assert_not_called()


def test_handle_callback_button_action_root(mock_wa_client: MagicMock, button_factory):
    """
    CallbackButton para ACTION_ROOT deve despachar o menu raiz.
    """
    btn = button_factory(wa_id="5547998887770", data=ACTION_ROOT)

    handle_callback_button(client=mock_wa_client, btn=btn)

    mock_wa_client.send_message.assert_called_once()
    kwargs = mock_wa_client.send_message.call_args.kwargs
    assert kwargs["to"] == "5547998887770"
    assert "Aqui está o menu principal" in kwargs["text"]


def test_handle_callback_button_action_ask_question(mock_wa_client: MagicMock, button_factory):
    """
    CallbackButton para ACTION_ASK_QUESTION deve despachar aviso de indisponibilidade com menu raiz.
    """
    btn = button_factory(wa_id="5547998887778", data=ACTION_ASK_QUESTION)

    handle_callback_button(client=mock_wa_client, btn=btn)

    mock_wa_client.send_message.assert_called_once()
    kwargs = mock_wa_client.send_message.call_args.kwargs
    assert kwargs["to"] == "5547998887778"
    assert "temporariamente indisponível" in kwargs["text"]


def test_handle_callback_button_action_ask_question_normalizes_12_digit_phone(
    mock_wa_client: MagicMock, button_factory
):
    """
    CallbackButton de número brasileiro de 12 dígitos deve ser normalizado para 13 dígitos no envio.
    """
    btn = button_factory(wa_id="554797865306", data=ACTION_ASK_QUESTION)

    handle_callback_button(client=mock_wa_client, btn=btn)

    mock_wa_client.send_message.assert_called_once()
    kwargs = mock_wa_client.send_message.call_args.kwargs
    assert kwargs["to"] == "5547997865306"
    assert "temporariamente indisponível" in kwargs["text"]


def test_handle_callback_button_prefix_menu(
    session: Session, mock_wa_client: MagicMock, button_factory
):
    """
    CallbackButton com prefixo 'menu:' deve navegar para o submenu correspondente.
    """
    menu = Menu(name="Financeiro", selection_name="Fin", message="Setor financeiro", parent_id=None)
    session.add(menu)
    session.commit()
    session.refresh(menu)

    btn = button_factory(wa_id="5547998887779", data=f"menu:{menu.id}")

    handle_callback_button(client=mock_wa_client, btn=btn)

    mock_wa_client.send_message.assert_called_once()
    kwargs = mock_wa_client.send_message.call_args.kwargs
    assert kwargs["to"] == "5547998887779"



def test_handle_callback_selection_without_user_id(mock_wa_client: MagicMock):
    """
    CallbackSelection sem from_user deve registrar aviso e abortar sem falhas.
    """
    sel = MagicMock(spec=CallbackSelection)
    sel.from_user = None

    handle_callback_selection(client=mock_wa_client, sel=sel)

    mock_wa_client.send_message.assert_not_called()


def test_handle_callback_selection_action_ask_question(mock_wa_client: MagicMock, selection_factory):
    """
    CallbackSelection para ACTION_ASK_QUESTION deve disparar o menu raiz com mensagem de indisponibilidade.
    """
    sel = selection_factory(wa_id="5547998887771", data=ACTION_ASK_QUESTION)

    handle_callback_selection(client=mock_wa_client, sel=sel)

    mock_wa_client.send_message.assert_called_once()
    kwargs = mock_wa_client.send_message.call_args.kwargs
    assert kwargs["to"] == "5547998887771"
    assert "temporariamente indisponível" in kwargs["text"]


def test_handle_callback_selection_action_root(mock_wa_client: MagicMock, selection_factory):
    """
    CallbackSelection para ACTION_ROOT deve despachar o menu principal.
    """
    sel = selection_factory(wa_id="5547998887772", data=ACTION_ROOT)

    handle_callback_selection(client=mock_wa_client, sel=sel)

    mock_wa_client.send_message.assert_called_once()
    kwargs = mock_wa_client.send_message.call_args.kwargs
    assert kwargs["to"] == "5547998887772"
    assert "Aqui está o menu principal" in kwargs["text"]


def test_handle_callback_selection_prefix_menu(
    session: Session, mock_wa_client: MagicMock, selection_factory
):
    """
    CallbackSelection com prefixo 'menu:' deve navegar para o submenu correspondente.
    """
    menu = Menu(name="Secretaria", selection_name="Sec", message="Atendimento geral", parent_id=None)
    session.add(menu)
    session.commit()
    session.refresh(menu)

    sel = selection_factory(wa_id="5547998887773", data=f"menu:{menu.id}")

    handle_callback_selection(client=mock_wa_client, sel=sel)

    mock_wa_client.send_message.assert_called_once()
    kwargs = mock_wa_client.send_message.call_args.kwargs
    assert kwargs["to"] == "5547998887773"


def test_handle_menu_navigation_without_user_id(mock_wa_client: MagicMock):
    """
    handle_menu_navigation sem from_user deve encerrar sem exceção.
    """
    btn = MagicMock(spec=CallbackButton)
    btn.from_user = None

    handle_menu_navigation(client=mock_wa_client, callback=btn, menu_id=1)

    mock_wa_client.send_message.assert_not_called()


def test_handle_menu_navigation_leaf_without_parent(
    session: Session, mock_wa_client: MagicMock, button_factory
):
    """
    Menu folha raiz (parent_id=None e sem filhos) deve conter apenas botão 'Voltar ao início'.
    """
    leaf_root = Menu(
        name="Aviso Importante",
        selection_name="Aviso",
        message="Mensagem do aviso sem submenus",
        parent_id=None,
    )
    session.add(leaf_root)
    session.commit()
    session.refresh(leaf_root)

    btn = button_factory(wa_id="5547998887774", data=f"menu:{leaf_root.id}")

    handle_menu_navigation(client=mock_wa_client, callback=btn, menu_id=leaf_root.id)  # type: ignore

    mock_wa_client.send_message.assert_called_once()
    reply_kwargs = mock_wa_client.send_message.call_args.kwargs
    buttons = reply_kwargs["buttons"]
    assert len(buttons) == 1
    assert buttons[0].callback_data == ACTION_ROOT
    assert buttons[0].title == "Voltar ao início"


def test_handle_menu_navigation_leaf_with_parent(
    session: Session, mock_wa_client: MagicMock, button_factory
):
    """
    Menu folha com parent_id deve conter botões 'Voltar' e 'Voltar ao início'.
    """
    parent = Menu(name="Cursos", selection_name="Cursos", message="Menu de cursos", parent_id=None)
    session.add(parent)
    session.commit()
    session.refresh(parent)

    leaf = Menu(
        name="Engenharia",
        selection_name="Eng",
        message="Informações sobre Engenharia",
        parent_id=parent.id,
    )
    session.add(leaf)
    session.commit()
    session.refresh(leaf)

    btn = button_factory(wa_id="5547998887780", data=f"menu:{leaf.id}")

    handle_menu_navigation(client=mock_wa_client, callback=btn, menu_id=leaf.id)  # type: ignore

    mock_wa_client.send_message.assert_called_once()
    reply_kwargs = mock_wa_client.send_message.call_args.kwargs
    assert reply_kwargs["text"] == "Informações sobre Engenharia\n\nDeseja realizar outra consulta?"
    buttons = reply_kwargs["buttons"]
    assert len(buttons) == 2
    assert buttons[0].callback_data == f"menu:{parent.id}"
    assert buttons[0].title == "Voltar"
    assert buttons[1].callback_data == ACTION_ROOT
    assert buttons[1].title == "Voltar ao início"



def test_handle_message_when_context_extraction_fails(mock_wa_client: MagicMock):
    """
    handle_message deve abortar antecipadamente caso a extração de contexto retorne None.
    """
    msg = MagicMock(spec=Message)
    user = MagicMock(spec=User)
    user.wa_id = None
    msg.from_user = user

    handle_message(client=mock_wa_client, msg=msg)

    mock_wa_client.send_message.assert_not_called()


def test_handle_message_dispatch_fails_does_not_save_bot_reply(
    mock_wa_client: MagicMock, monkeypatch
):
    """
    Quando dispatch_reply retorna None, save_bot_reply_log não deve ser acionado.
    """
    msg = MagicMock(spec=Message)
    user = MagicMock(spec=User)
    user.wa_id = "5547998887781"
    user.name = "Teste"
    msg.from_user = user
    msg.text = "Olá"

    monkeypatch.setattr("src.services.webhook.message_handler.dispatch_reply", lambda **kwargs: None)
    mock_bot_log = MagicMock()
    monkeypatch.setattr("src.services.webhook.message_handler.save_bot_reply_log", mock_bot_log)

    handle_message(client=mock_wa_client, msg=msg)

    mock_bot_log.assert_not_called()



def test_build_mode_response_conversational_mode(session: Session):
    """
    build_mode_response em modo conversacional deve retornar fallback com menu raiz.
    """
    msg = MagicMock(spec=Message)
    user = MagicMock(spec=User)
    user.wa_id = "5547998887775"
    user.name = "Juliana"
    msg.from_user = user
    msg.text = "Gostaria de falar com atendente"

    context = extract_message_context(msg)
    assert context is not None

    response = build_mode_response(mode=SESSION_MODE_CONVERSATIONAL, context=context)

    assert "temporariamente indisponível" in response["text"]
    assert "buttons" in response


def test_handle_status_success(mock_wa_client: MagicMock, caplog):
    """
    handle_status para mensagem entregue com sucesso.
    """
    status = MagicMock(spec=MessageStatus)
    status.id = "wamid.STATUS_001"
    status.status.value = "delivered"
    user = MagicMock(spec=User)
    user.wa_id = "5547998887776"
    status.from_user = user
    status.error = None

    with caplog.at_level("INFO"):
        handle_status(mock_wa_client, status)

    assert "[STATUS UPDATE] ID: wamid.STATUS_001 | Destino: 5547998887776 | Status: delivered" in caplog.text


def test_handle_status_with_error(mock_wa_client: MagicMock, caplog):
    """
    handle_status quando ocorre erro na entrega da mensagem pela Meta.
    """
    status = MagicMock(spec=MessageStatus)
    status.id = "wamid.STATUS_ERR_002"
    status.status = "failed"
    user = MagicMock(spec=User)
    user.wa_id = "5547998887777"
    status.from_user = user
    err = MagicMock()
    err.code = 131047
    err.message = "Re-engagement message window expired"
    err.details = "Customer service window closed"
    status.error = err

    with caplog.at_level("WARNING"):
        handle_status(mock_wa_client, status)

    assert "[STATUS UPDATE] ID: wamid.STATUS_ERR_002 | Destino: 5547998887777 | Status: failed" in caplog.text
    assert "Erro 131047: Re-engagement message window expired (Customer service window closed)" in caplog.text


def test_handle_status_without_from_user(mock_wa_client: MagicMock, caplog):
    """
    handle_status quando status não possui from_user.
    """
    status = MagicMock(spec=MessageStatus)
    status.id = "wamid.STATUS_NO_USER"
    status.status = "sent"
    status.from_user = None
    status.error = None

    with caplog.at_level("INFO"):
        handle_status(mock_wa_client, status)

    assert "[STATUS UPDATE] ID: wamid.STATUS_NO_USER | Destino: Desconhecido | Status: sent" in caplog.text

