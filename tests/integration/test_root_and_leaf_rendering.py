"""
Testes de integração da renderização do menu raiz como contêiner e das folhas com navegação de retorno.
"""

from unittest.mock import MagicMock
from sqlmodel import Session, select
from pywa.types import Button, SectionList
from src.models.chat_history_model import ChatHistory
from src.models.menu_model import Menu
from src.services.webhook.message_handler import (
    ACTION_ASK_QUESTION,
    ACTION_ROOT,
    NO_ROOT_MESSAGE,
    MessageContext,
    build_root_view,
    handle_menu_navigation,
    send_root_menu,
)

ROOT_MESSAGE = "Bem-vindo ao atendimento da UDESC"


def _context(session: Session, wa_id: str | None = "554798765432") -> MessageContext:
    return MessageContext(
        session=session,
        user_id="BR.1234567890123",
        wa_id=wa_id,
        reply_to=wa_id or "BR.1234567890123",
        user_name="Aluno",
        message_text="Olá",
    )


def _add(
    session: Session,
    name: str,
    parent_id: int | None = None,
    message: str | None = None,
    selection_name: str | None = None,
) -> Menu:
    menu = Menu(
        name=name,
        selection_name=selection_name or name,
        message=message or f"Mensagem {name}",
        parent_id=parent_id,
    )
    session.add(menu)
    session.commit()
    session.refresh(menu)
    return menu


def _root_with_children(session: Session, children: int) -> Menu:
    root = _add(session, "menu_inicio", message=ROOT_MESSAGE)
    for index in range(children):
        _add(session, f"Filho {index + 1}", parent_id=root.id)
    return root


def _sent(client: MagicMock) -> dict:
    client.send_message.assert_called_once()
    return client.send_message.call_args.kwargs


def test_root_with_two_children_sends_three_quick_reply_buttons(session: Session, mock_wa_client: MagicMock):
    root = _root_with_children(session, 2)

    send_root_menu(mock_wa_client, _context(session))

    sent = _sent(mock_wa_client)
    assert sent["text"] == ROOT_MESSAGE
    buttons = sent["buttons"]
    assert all(isinstance(button, Button) for button in buttons)
    assert [b.title for b in buttons] == ["Filho 1", "Filho 2", "Fazer Pergunta"]
    assert buttons[-1].callback_data == ACTION_ASK_QUESTION
    assert root.id is not None and all(b.callback_data != f"menu:{root.id}" for b in buttons)


def test_root_with_three_children_sends_a_section_list(session: Session, mock_wa_client: MagicMock):
    _root_with_children(session, 3)

    send_root_menu(mock_wa_client, _context(session))

    sent = _sent(mock_wa_client)
    assert sent["text"] == ROOT_MESSAGE
    assert isinstance(sent["buttons"], SectionList)
    rows = list(list(sent["buttons"].sections)[0].rows)
    assert [row.title for row in rows] == ["Filho 1", "Filho 2", "Filho 3", "Fazer uma pergunta"]


def test_root_without_children_sends_only_the_ask_button(session: Session, mock_wa_client: MagicMock):
    _root_with_children(session, 0)

    send_root_menu(mock_wa_client, _context(session))

    sent = _sent(mock_wa_client)
    assert sent["text"] == ROOT_MESSAGE
    assert [b.callback_data for b in sent["buttons"]] == [ACTION_ASK_QUESTION]


def test_without_root_sends_unavailable_message_without_buttons(session: Session, mock_wa_client: MagicMock):
    send_root_menu(mock_wa_client, _context(session))

    sent = _sent(mock_wa_client)
    assert sent["text"] == NO_ROOT_MESSAGE
    assert sent["buttons"] is None


def test_build_root_view_uses_intro_text_instead_of_the_root_message(session: Session):
    _root_with_children(session, 1)

    view = build_root_view(session, "Aviso")

    assert view["text"] == "Aviso"


def test_send_root_menu_targets_the_resolved_reply_target(session: Session, mock_wa_client: MagicMock):
    _root_with_children(session, 1)

    send_root_menu(mock_wa_client, _context(session, wa_id=None))

    assert _sent(mock_wa_client)["to"] == "BR.1234567890123"


def test_navigating_to_the_root_id_renders_the_root_view(session: Session, mock_wa_client: MagicMock):
    root = _root_with_children(session, 2)
    assert root.id is not None

    handle_menu_navigation(mock_wa_client, _context(session), root.id)

    sent = _sent(mock_wa_client)
    assert sent["text"] == ROOT_MESSAGE
    assert [b.title for b in sent["buttons"]][-1] == "Fazer Pergunta"


def test_submenu_with_two_children_sends_them_then_back_as_buttons(session: Session, mock_wa_client: MagicMock):
    root = _root_with_children(session, 0)
    parent = _add(session, "Cursos", parent_id=root.id, message="Nossos cursos")
    engineering = _add(session, "Engenharia", parent_id=parent.id)
    law = _add(session, "Direito", parent_id=parent.id)
    assert parent.id is not None

    handle_menu_navigation(mock_wa_client, _context(session), parent.id)

    sent = _sent(mock_wa_client)
    assert sent["to"] == "554798765432"
    assert sent["text"] == "Nossos cursos"
    assert [(b.title, b.callback_data) for b in sent["buttons"]] == [
        ("Direito", f"menu:{law.id}"),
        ("Engenharia", f"menu:{engineering.id}"),
        ("Voltar", f"menu:{root.id}"),
    ]


def test_submenu_with_three_children_sends_a_list_with_a_navigation_section(
    session: Session, mock_wa_client: MagicMock
):
    root = _root_with_children(session, 0)
    parent = _add(session, "Cursos", parent_id=root.id, message="Nossos cursos")
    for name in ("Engenharia", "Direito", "Artes"):
        _add(session, name, parent_id=parent.id)
    assert parent.id is not None

    handle_menu_navigation(mock_wa_client, _context(session), parent.id)

    sent = _sent(mock_wa_client)
    assert sent["text"] == "Nossos cursos"
    assert isinstance(sent["buttons"], SectionList)
    sections = list(sent["buttons"].sections)
    assert [section.title for section in sections] == ["Menu", "Navegação"]
    assert [row.title for row in sections[0].rows] == ["Artes", "Direito", "Engenharia"]
    assert [(row.title, row.callback_data) for row in sections[1].rows] == [("Voltar", f"menu:{root.id}")]
    all_callbacks = [row.callback_data for section in sections for row in section.rows]
    assert ACTION_ASK_QUESTION not in all_callbacks and ACTION_ROOT not in all_callbacks


def test_submenu_at_depth_two_goes_back_to_its_own_parent(session: Session, mock_wa_client: MagicMock):
    root = _root_with_children(session, 0)
    parent = _add(session, "Cursos", parent_id=root.id)
    child = _add(session, "Engenharia", parent_id=parent.id)
    grandchild = _add(session, "Civil", parent_id=child.id)
    assert child.id is not None

    handle_menu_navigation(mock_wa_client, _context(session), child.id)

    buttons = _sent(mock_wa_client)["buttons"]
    assert [(b.title, b.callback_data) for b in buttons] == [
        ("Civil", f"menu:{grandchild.id}"),
        ("Voltar", f"menu:{parent.id}"),
    ]


def test_submenu_over_the_limit_is_truncated_with_back_kept_and_a_warning(
    session: Session, mock_wa_client: MagicMock, caplog
):
    root = _root_with_children(session, 0)
    parent = _add(session, "Cursos", parent_id=root.id)
    for index in range(10):
        _add(session, f"Curso {index:02d}", parent_id=parent.id)
    assert parent.id is not None

    with caplog.at_level("WARNING", logger="Chatbot"):
        handle_menu_navigation(mock_wa_client, _context(session), parent.id)

    sections = list(_sent(mock_wa_client)["buttons"].sections)
    assert [row.title for row in sections[0].rows] == [f"Curso {index:02d}" for index in range(9)]
    assert [row.callback_data for row in sections[1].rows] == [f"menu:{root.id}"]
    assert "[MENU] Lista com 11 opções excede o limite do WhatsApp; exibindo 10." in caplog.messages


def test_root_options_are_sent_in_natural_order(session: Session, mock_wa_client: MagicMock):
    root = _add(session, "menu_inicio", message=ROOT_MESSAGE)
    for selection_name in ("10 - X", "Ácido", "2 - Y", "abacate"):
        _add(session, selection_name.lower(), parent_id=root.id, selection_name=selection_name)

    send_root_menu(mock_wa_client, _context(session))

    rows = list(list(_sent(mock_wa_client)["buttons"].sections)[0].rows)
    assert [row.title for row in rows] == ["2 - Y", "10 - X", "abacate", "Ácido", "Fazer uma pergunta"]


def test_root_children_created_out_of_order_are_sent_in_order(session: Session, mock_wa_client: MagicMock):
    root = _add(session, "menu_inicio", message=ROOT_MESSAGE)
    _add(session, "tutoria", parent_id=root.id, selection_name="2-Tutoria")
    _add(session, "monitoria", parent_id=root.id, selection_name="1-Monitoria")

    send_root_menu(mock_wa_client, _context(session))

    assert [b.title for b in _sent(mock_wa_client)["buttons"]] == ["1-Monitoria", "2-Tutoria", "Fazer Pergunta"]


def test_submenu_reply_never_carries_the_internal_menu_name(session: Session, mock_wa_client: MagicMock):
    root = _root_with_children(session, 0)
    parent = _add(session, "menu_cursos", parent_id=root.id, message="Escolha um curso")
    _add(session, "Engenharia", parent_id=parent.id)
    _add(session, "Direito", parent_id=parent.id)
    assert parent.id is not None

    handle_menu_navigation(mock_wa_client, _context(session), parent.id)

    assert _sent(mock_wa_client)["text"] == "Escolha um curso"


def test_submenu_reply_logged_for_the_history_has_no_internal_name(session: Session, mock_wa_client: MagicMock):
    root = _root_with_children(session, 0)
    parent = _add(session, "menu_cursos", parent_id=root.id, message="Escolha um curso")
    _add(session, "Engenharia", parent_id=parent.id)
    assert parent.id is not None

    handle_menu_navigation(mock_wa_client, _context(session), parent.id)

    session.expire_all()
    reply = session.exec(select(ChatHistory).where(ChatHistory.role == "bot")).one()
    assert reply.content == "Escolha um curso"


def test_leaf_whose_parent_is_a_submenu_offers_both_back_buttons(session: Session, mock_wa_client: MagicMock):
    root = _root_with_children(session, 0)
    parent = _add(session, "Cursos", parent_id=root.id)
    leaf = _add(session, "Engenharia", parent_id=parent.id, message="Informações sobre Engenharia")
    assert leaf.id is not None

    handle_menu_navigation(mock_wa_client, _context(session), leaf.id)

    sent = _sent(mock_wa_client)
    assert sent["to"] == "554798765432"
    assert sent["text"] == "Informações sobre Engenharia\n\nDeseja realizar outra consulta?"
    assert [(b.title, b.callback_data) for b in sent["buttons"]] == [
        ("Voltar", f"menu:{parent.id}"),
        ("Voltar ao início", ACTION_ROOT),
    ]


def test_leaf_whose_parent_is_the_root_offers_back_to_the_root_and_back_to_start(
    session: Session, mock_wa_client: MagicMock
):
    root = _root_with_children(session, 0)
    leaf = _add(session, "Aviso", parent_id=root.id, message="Aviso importante")
    assert leaf.id is not None

    handle_menu_navigation(mock_wa_client, _context(session), leaf.id)

    sent = _sent(mock_wa_client)
    assert sent["text"] == "Aviso importante\n\nDeseja realizar outra consulta?"
    assert [(b.title, b.callback_data) for b in sent["buttons"]] == [
        ("Voltar", f"menu:{root.id}"),
        ("Voltar ao início", ACTION_ROOT),
    ]


def test_leaf_at_depth_three_goes_back_to_its_own_parent(session: Session, mock_wa_client: MagicMock):
    root = _root_with_children(session, 0)
    first = _add(session, "Cursos", parent_id=root.id)
    second = _add(session, "Engenharia", parent_id=first.id)
    leaf = _add(session, "Civil", parent_id=second.id)
    assert leaf.id is not None

    handle_menu_navigation(mock_wa_client, _context(session), leaf.id)

    callbacks = [b.callback_data for b in _sent(mock_wa_client)["buttons"]]
    assert callbacks == [f"menu:{second.id}", ACTION_ROOT]


def test_leaf_without_parent_that_is_not_the_root_offers_only_back_to_start(
    session: Session, mock_wa_client: MagicMock
):
    _root_with_children(session, 0)
    orphan = _add(session, "Órfão", parent_id=None)
    assert orphan.id is not None

    handle_menu_navigation(mock_wa_client, _context(session), orphan.id)

    sent = _sent(mock_wa_client)
    assert [b.callback_data for b in sent["buttons"]] == [ACTION_ROOT]


def test_navigating_to_a_deleted_menu_falls_back_to_the_root_view(session: Session, mock_wa_client: MagicMock):
    _root_with_children(session, 1)

    handle_menu_navigation(mock_wa_client, _context(session), 99999)

    sent = _sent(mock_wa_client)
    assert sent["text"].startswith("Esse menu não está mais disponível")
    assert [b.callback_data for b in sent["buttons"]][-1] == ACTION_ASK_QUESTION


def test_navigation_reports_the_menu_left_on_screen(session: Session, mock_wa_client: MagicMock):
    root = _root_with_children(session, 0)
    parent = _add(session, "Cursos", parent_id=root.id)
    leaf = _add(session, "Engenharia", parent_id=parent.id)
    assert parent.id is not None and leaf.id is not None

    assert handle_menu_navigation(mock_wa_client, _context(session), parent.id) == parent.id
    assert handle_menu_navigation(mock_wa_client, _context(session), leaf.id) == leaf.id


def test_navigation_reports_no_menu_when_the_root_is_shown(session: Session, mock_wa_client: MagicMock):
    root = _root_with_children(session, 1)
    assert root.id is not None

    assert handle_menu_navigation(mock_wa_client, _context(session), root.id) is None
    assert handle_menu_navigation(mock_wa_client, _context(session), 99999) is None


def test_navigation_reports_the_menu_even_when_the_send_fails(session: Session, mock_wa_client: MagicMock):
    root = _root_with_children(session, 0)
    leaf = _add(session, "Aviso", parent_id=root.id)
    mock_wa_client.send_message.side_effect = RuntimeError("Meta fora do ar")
    assert leaf.id is not None

    assert handle_menu_navigation(mock_wa_client, _context(session), leaf.id) == leaf.id
