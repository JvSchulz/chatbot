"""
Testes unitários para construção de payloads de resposta (botões e listas de seções).
"""

from pywa.types import Button, SectionList
from src.models.menu_model import Menu
from src.services.webhook.message_handler import (
    ACTION_ASK_QUESTION,
    build_root_response_object,
    build_child_response_object,
    build_child_menu_buttons,
    build_child_menu_section_list,
    build_root_menu_buttons,
    build_root_menu_section_list,
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
    assert row_map["menu:1"].description is None
    assert row_map["menu:2"].title == "Pós-Graduação"
    assert row_map["menu:2"].description is None
    assert row_map["menu:3"].title == "Extensão"
    assert row_map["menu:3"].description is None

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
    assert row_map["menu:10"].description is None
    assert row_map["menu:11"].title == "Calendário"
    assert row_map["menu:11"].description is None
    assert row_map["menu:12"].title == "Horários"
    assert row_map["menu:12"].description is None
    assert row_map["menu:13"].title == "Histórico Escolar"
    assert row_map["menu:13"].description is None


def test_build_child_response_object_with_empty_submenus():
    """
    Quando não há submenus filhos, deve retornar lista de botões vazia.
    """
    result = build_child_response_object(menus=[], intro_text="Vazio")
    assert result["text"] == "Vazio"
    assert result["buttons"] == []



def test_root_menu_buttons_never_exceed_the_quick_reply_limit():
    menus = [_make_menu(1, "A"), _make_menu(2, "B"), _make_menu(3, "C")]

    buttons = build_root_menu_buttons(menus)

    assert [b.callback_data for b in buttons] == ["menu:1", "menu:2", "menu:3"]


def _menu_with_distinct_selection_name() -> Menu:
    return Menu(id=7, name="nome_interno", selection_name="Texto do botão", message="m", parent_id=1)


def _menu_without_selection_name() -> Menu:
    return Menu(id=8, name="nome_interno", selection_name="", message="m", parent_id=1)


def test_buttons_use_the_selection_name_and_fall_back_to_the_name():
    buttons = build_child_menu_buttons([_menu_with_distinct_selection_name(), _menu_without_selection_name()])

    assert [b.title for b in buttons] == ["Texto do botão", "nome_interno"]


def test_root_and_child_rows_use_the_selection_name_and_fall_back_to_the_name():
    menus = [_menu_with_distinct_selection_name(), _menu_without_selection_name()]

    for section_list in (build_root_menu_section_list(menus), build_child_menu_section_list(menus)):
        rows = list(list(section_list.sections)[0].rows)
        assert [row.title for row in rows[:2]] == ["Texto do botão", "nome_interno"]
        assert [row.description for row in rows[:2]] == [None, None]


def test_menu_rows_never_carry_a_description():
    nameless = Menu(id=9, name="", selection_name="Só título", message="m", parent_id=1)
    named = Menu(id=10, name="menu_interno", selection_name="Título", message="m", parent_id=1)

    for section_list in (build_root_menu_section_list([nameless, named]), build_child_menu_section_list([nameless, named])):
        menu_rows = [row for row in _rows(section_list) if row.callback_data.startswith("menu:")]
        assert [row.description for row in menu_rows] == [None, None]


def _rows(section_list) -> list:
    return list(list(section_list.sections)[0].rows)


def test_root_list_is_truncated_to_ten_rows_keeping_the_ask_option_last():
    menus = [_make_menu(index, f"Menu {index}") for index in range(1, 13)]

    rows = _rows(build_root_menu_section_list(menus))

    assert len(rows) == 10
    assert [row.callback_data for row in rows[:9]] == [f"menu:{index}" for index in range(1, 10)]
    assert rows[-1].callback_data == ACTION_ASK_QUESTION


def test_child_list_is_truncated_to_ten_rows():
    menus = [_make_menu(index, f"Menu {index}", parent_id=99) for index in range(1, 14)]

    rows = _rows(build_child_menu_section_list(menus))

    assert [row.callback_data for row in rows] == [f"menu:{index}" for index in range(1, 11)]


def test_lists_at_the_limit_are_not_truncated():
    root_rows = _rows(build_root_menu_section_list([_make_menu(index, "M") for index in range(1, 10)]))
    child_rows = _rows(build_child_menu_section_list([_make_menu(index, "M", 99) for index in range(1, 11)]))

    assert (len(root_rows), len(child_rows)) == (10, 10)
    assert root_rows[-1].callback_data == ACTION_ASK_QUESTION


def test_truncation_is_reported_in_the_log(caplog):
    menus = [_make_menu(index, "M", parent_id=99) for index in range(1, 13)]

    with caplog.at_level("WARNING", logger="Chatbot"):
        build_child_menu_section_list(menus)

    assert caplog.messages == ["[MENU] Lista com 12 opções excede o limite do WhatsApp; exibindo 10."]


def test_lists_within_the_limit_log_nothing(caplog):
    with caplog.at_level("WARNING", logger="Chatbot"):
        build_child_menu_section_list([_make_menu(1, "M", 99)])
        build_root_menu_section_list([_make_menu(1, "M")])

    assert caplog.messages == []


def _internal_names(count: int, parent_id: int | None) -> list[Menu]:
    return [
        Menu(id=index, name=f"menu_interno_{index}", selection_name=f"Opção {index}", message="m", parent_id=parent_id)
        for index in range(1, count + 1)
    ]


def _all_row_text(section_list) -> str:
    return " ".join(f"{row.title} {row.description or ''}" for row in _rows(section_list))


def test_root_list_rows_carry_no_internal_name():
    payload = build_root_response_object(menus=_internal_names(6, None), intro_text="Escolha:")

    assert "menu_interno" not in _all_row_text(payload["buttons"])


def test_child_list_rows_carry_no_internal_name():
    payload = build_child_response_object(menus=_internal_names(6, 99), intro_text="Escolha:")

    assert "menu_interno" not in _all_row_text(payload["buttons"])
    assert [row.title for row in _rows(payload["buttons"])] == [f"Opção {index}" for index in range(1, 7)]


def test_the_ask_row_keeps_its_fixed_description():
    rows = _rows(build_root_menu_section_list(_internal_names(4, None)))

    assert rows[-1].description == "Tirar dúvidas com nosso assistente virtual"
