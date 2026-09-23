"""
Testes unitários para construção de payloads de resposta (botões e listas de seções).
"""

from pywa.types import Button, SectionList
from src.models.menu_model import Menu
from src.services.webhook.message_handler import (
    ACTION_ASK_QUESTION,
    build_root_response_object,
    build_child_response_object,
)


def _make_menu(menu_id: int, name: str, parent_id: int | None = None) -> Menu:
    """Função auxiliar para instanciar menus para testes."""
    return Menu(
        id=menu_id,
        name=name,
        selection_name=name,
        message=f"Mensagem do menu {name}",
        parent_id=parent_id,
    )


def test_build_root_response_object_with_two_menus_produces_quick_reply_buttons():
    """
    Quando o menu raiz tem 2 itens (total 3 opções com pergunta), deve retornar botões de resposta rápida.
    """
    menus = [
        _make_menu(1, "Graduação"),
        _make_menu(2, "Pós-Graduação"),
    ]
    intro = "Escolha uma opção:"

    result = build_root_response_object(menus=menus, intro_text=intro)

    assert result["text"] == intro
    buttons = result["buttons"]
    assert isinstance(buttons, list)
    assert len(buttons) == 3
    assert all(isinstance(btn, Button) for btn in buttons)

    # Verifica se os menus estão presentes
    callbacks = [btn.callback_data for btn in buttons]
    assert "menu:1" in callbacks
    assert "menu:2" in callbacks
    assert ACTION_ASK_QUESTION in callbacks

    # Verifica botão de pergunta e títulos dos botões
    btn_map = {b.callback_data: b.title for b in buttons}
    assert btn_map["menu:1"] == "Graduação"
    assert btn_map["menu:2"] == "Pós-Graduação"
    assert btn_map[ACTION_ASK_QUESTION] == "Fazer Pergunta"


def test_build_root_response_object_with_three_menus_produces_section_list():
    """
    Quando o menu raiz tem 3 itens (total 4 opções com pergunta), deve alternar para SectionList.
    """
    menus = [
        _make_menu(1, "Graduação"),
        _make_menu(2, "Pós-Graduação"),
        _make_menu(3, "Extensão"),
    ]
    intro = "Menu principal:"

    result = build_root_response_object(menus=menus, intro_text=intro)

    assert result["text"] == intro
    section_list = result["buttons"]
    assert isinstance(section_list, SectionList)
    assert section_list.button_title == "Ver Opções"
    sections = list(section_list.sections)
    assert len(sections) == 1
    assert sections[0].title == "Menu"

    rows = list(sections[0].rows)
    assert len(rows) == 4

    row_callbacks = [row.callback_data for row in rows]
    assert row_callbacks == ["menu:1", "menu:2", "menu:3", ACTION_ASK_QUESTION]

    row_map = {r.callback_data: r for r in rows}
    assert row_map["menu:1"].title == "Graduação"
    assert row_map["menu:1"].description == "Graduação"
    assert row_map["menu:2"].title == "Pós-Graduação"
    assert row_map["menu:2"].description == "Pós-Graduação"
    assert row_map["menu:3"].title == "Extensão"
    assert row_map["menu:3"].description == "Extensão"

    question_row = row_map[ACTION_ASK_QUESTION]
    assert question_row.title == "Fazer uma pergunta"
    assert question_row.description == "Tirar dúvidas com nosso assistente virtual"


def test_build_child_response_object_with_three_submenus_produces_only_child_buttons():
    """
    Submenu com até 3 opções filhas deve gerar botões rápidos sem o botão de pergunta.
    """
    submenus = [
        _make_menu(10, "Matrícula", parent_id=1),
        _make_menu(11, "Calendário", parent_id=1),
        _make_menu(12, "Horários", parent_id=1),
    ]
    intro = "Opções de Graduação:"

    result = build_child_response_object(menus=submenus, intro_text=intro)

    assert result["text"] == intro
    buttons = result["buttons"]
    assert isinstance(buttons, list)
    assert len(buttons) == 3
    assert all(isinstance(btn, Button) for btn in buttons)

    callbacks = [btn.callback_data for btn in buttons]
    assert callbacks == ["menu:10", "menu:11", "menu:12"]
    assert ACTION_ASK_QUESTION not in callbacks

    btn_map = {b.callback_data: b.title for b in buttons}
    assert btn_map["menu:10"] == "Matrícula"
    assert btn_map["menu:11"] == "Calendário"
    assert btn_map["menu:12"] == "Horários"


def test_build_child_response_object_with_four_submenus_produces_section_list_without_question():
    """
    Submenu com mais de 3 opções filhas deve gerar SectionList contendo exclusivamente os filhos.
    """
    submenus = [
        _make_menu(10, "Matrícula", parent_id=1),
        _make_menu(11, "Calendário", parent_id=1),
        _make_menu(12, "Horários", parent_id=1),
        _make_menu(13, "Histórico Escolar", parent_id=1),
    ]
    intro = "Selecione o serviço:"

    result = build_child_response_object(menus=submenus, intro_text=intro)

    assert result["text"] == intro
    section_list = result["buttons"]
    assert isinstance(section_list, SectionList)
    assert section_list.button_title == "Ver Opções"
    sections = list(section_list.sections)
    assert len(sections) == 1
    assert sections[0].title == "Menu"

    rows = list(sections[0].rows)
    assert len(rows) == 4

    row_callbacks = [row.callback_data for row in rows]
    assert row_callbacks == ["menu:10", "menu:11", "menu:12", "menu:13"]
    assert ACTION_ASK_QUESTION not in row_callbacks

    row_map = {r.callback_data: r for r in rows}
    assert row_map["menu:10"].title == "Matrícula"
    assert row_map["menu:10"].description == "Matrícula"
    assert row_map["menu:11"].title == "Calendário"
    assert row_map["menu:11"].description == "Calendário"
    assert row_map["menu:12"].title == "Horários"
    assert row_map["menu:12"].description == "Horários"
    assert row_map["menu:13"].title == "Histórico Escolar"
    assert row_map["menu:13"].description == "Histórico Escolar"


def test_build_child_response_object_with_empty_submenus():
    """
    Quando não há submenus filhos, deve retornar lista de botões vazia.
    """
    result = build_child_response_object(menus=[], intro_text="Vazio")
    assert result["text"] == "Vazio"
    assert result["buttons"] == []

