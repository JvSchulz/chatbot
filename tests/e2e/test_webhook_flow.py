"""
Testes de ponta a ponta (E2E) simulando o ciclo de vida completo do webhook do WhatsApp.
"""

from unittest.mock import MagicMock
from sqlmodel import Session, select
from pywa.client import WhatsApp
from pywa.types import Button
from src.models.menu_model import Menu
from src.models.chat_history_model import ChatHistory
from src.services.webhook.message_handler import (
    ACTION_ASK_QUESTION,
    ACTION_ROOT,
    handle_message,
    handle_callback_button,
    handle_callback_selection,
)


def _seed_test_menus(session: Session) -> dict[str, Menu]:
    """Cria uma árvore representativa de menus para os testes E2E."""
    root_grad = Menu(name="Graduação", selection_name="Grad", message="Cursos de Graduação", parent_id=None)
    root_pos = Menu(name="Pós-Graduação", selection_name="Pós", message="Cursos de Pós-Graduação", parent_id=None)
    session.add(root_grad)
    session.add(root_pos)
    session.commit()
    session.refresh(root_grad)
    session.refresh(root_pos)

    sub_matr = Menu(name="Matrícula", selection_name="Matr", message="Opções de matrícula", parent_id=root_grad.id)
    sub_cal = Menu(name="Calendário", selection_name="Cal", message="Calendário acadêmico", parent_id=root_grad.id)
    session.add(sub_matr)
    session.add(sub_cal)
    session.commit()
    session.refresh(sub_matr)
    session.refresh(sub_cal)

    leaf_docs = Menu(
        name="Documentos",
        selection_name="Docs",
        message="Apresente RG, CPF e Histórico.",
        parent_id=sub_matr.id,
    )
    session.add(leaf_docs)
    session.commit()
    session.refresh(leaf_docs)

    return {
        "root_grad": root_grad,
        "root_pos": root_pos,
        "sub_matr": sub_matr,
        "sub_cal": sub_cal,
        "leaf_docs": leaf_docs,
    }


def test_e2e_1_first_inbound_message(session: Session, mock_wa_client: MagicMock, message_factory):
    """
    E2E 1 - Primeira mensagem recebida: deve responder com menu raiz interativo e salvar log.
    """
    _seed_test_menus(session)
    msg = message_factory(wa_id="5547999990001", name="Aluno Novo", text="Olá!")

    handle_message(client=mock_wa_client, msg=msg)

    # 1. Verifica despacho da mensagem
    mock_wa_client.send_message.assert_called_once()
    call_kwargs = mock_wa_client.send_message.call_args.kwargs
    assert call_kwargs["to"] == "5547999990001"
    assert "Aluno Novo" in call_kwargs["text"]
    buttons = call_kwargs["buttons"]
    assert isinstance(buttons, list)
    callbacks = [b.callback_data for b in buttons]
    assert ACTION_ASK_QUESTION in callbacks

    # 2. Verifica registro de log no banco de dados
    history = session.exec(select(ChatHistory).where(ChatHistory.sender_id == "5547999990001")).all()
    assert len(history) >= 1
    inbound_record = next(h for h in history if h.role == "user")
    assert inbound_record.content == "Olá!"


def test_e2e_2_submenu_navigation(session: Session, mock_wa_client: MagicMock, button_factory):
    """
    E2E 2 - Navegação em submenu: deve enviar os filhos diretos sem o botão de pergunta.
    """
    menus = _seed_test_menus(session)
    grad_id = menus["root_grad"].id

    btn = button_factory(wa_id="5547999990002", data=f"menu:{grad_id}")

    handle_callback_button(client=mock_wa_client, btn=btn)

    mock_wa_client.send_message.assert_called_once()
    call_kwargs = mock_wa_client.send_message.call_args.kwargs
    assert call_kwargs["to"] == "5547999990002"
    buttons = call_kwargs.get("buttons")
    assert isinstance(buttons, list)
    assert len(buttons) == 2  # Matrícula e Calendário
    callbacks = [b.callback_data for b in buttons]
    assert f"menu:{menus['sub_matr'].id}" in callbacks
    assert f"menu:{menus['sub_cal'].id}" in callbacks
    assert ACTION_ASK_QUESTION not in callbacks


def test_e2e_3_leaf_menu_and_back_navigation(session: Session, mock_wa_client: MagicMock, button_factory):
    """
    E2E 3 - Menu folha: deve renderizar mensagem de conteúdo com botões 'Voltar' e 'Voltar ao início'.
    """
    menus = _seed_test_menus(session)
    leaf_id = menus["leaf_docs"].id
    parent_id = menus["sub_matr"].id

    btn = button_factory(wa_id="5547999990003", data=f"menu:{leaf_id}")

    handle_callback_button(client=mock_wa_client, btn=btn)

    mock_wa_client.send_message.assert_called_once()
    call_kwargs = mock_wa_client.send_message.call_args.kwargs
    assert call_kwargs["to"] == "5547999990003"
    assert "Apresente RG, CPF e Histórico." in call_kwargs["text"]
    buttons = call_kwargs["buttons"]
    assert len(buttons) == 2

    back_button = next(b for b in buttons if b.callback_data == f"menu:{parent_id}")
    assert back_button.title == "Voltar"

    root_button = next(b for b in buttons if b.callback_data == ACTION_ROOT)
    assert root_button.title == "Voltar ao início"


def test_e2e_4_parent_back_action(session: Session, mock_wa_client: MagicMock, button_factory):
    """
    E2E 4 - Ação de voltar para o menu pai a partir de um menu folha.
    """
    menus = _seed_test_menus(session)
    parent_id = menus["sub_matr"].id

    btn = button_factory(wa_id="5547999990004", data=f"menu:{parent_id}")

    handle_callback_button(client=mock_wa_client, btn=btn)

    mock_wa_client.send_message.assert_called_once()
    call_kwargs = mock_wa_client.send_message.call_args.kwargs
    assert call_kwargs["to"] == "5547999990004"
    assert "Opções de matrícula" in call_kwargs["text"]


def test_e2e_5_model_unavailable_fallback(session: Session, mock_wa_client: MagicMock, button_factory):
    """
    E2E 5 - Fallback de modelo indisponível: clicar em 'Fazer Pergunta' restaura menu raiz com aviso.
    """
    _seed_test_menus(session)
    btn = button_factory(wa_id="5547999990005", data=ACTION_ASK_QUESTION)

    handle_callback_button(client=mock_wa_client, btn=btn)

    mock_wa_client.send_message.assert_called_once()
    call_kwargs = mock_wa_client.send_message.call_args.kwargs
    assert call_kwargs["to"] == "5547999990005"
    assert "temporariamente indisponível" in call_kwargs["text"]


def test_e2e_6_deleted_menu_edge_case(session: Session, mock_wa_client: MagicMock, button_factory):
    """
    E2E 6 - Caso de borda: callback para menu excluído do banco direciona ao menu principal.
    """
    _seed_test_menus(session)
    btn = button_factory(wa_id="5547999990006", data="menu:99999")

    handle_callback_button(client=mock_wa_client, btn=btn)

    mock_wa_client.send_message.assert_called_once()
    call_kwargs = mock_wa_client.send_message.call_args.kwargs
    assert call_kwargs["to"] == "5547999990006"
    assert "Esse menu não está mais disponível" in call_kwargs["text"]
