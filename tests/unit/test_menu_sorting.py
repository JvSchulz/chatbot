"""
Testes unitários da chave de ordenação natural dos menus e da ordem das consultas do serviço.
"""

from sqlmodel import Session

from src.models.menu_model import Menu
from src.services.menu_service import (
    get_all_menus,
    get_root_children,
    get_submenus,
    get_valid_parent_menus,
    menu_sort_key,
)


def add(session: Session, name: str, selection_name: str | None = None, parent_id: int | None = None) -> Menu:
    menu = Menu(name=name, selection_name=selection_name or name, message="M", parent_id=parent_id)
    session.add(menu)
    session.commit()
    session.refresh(menu)
    return menu


def ordered(texts: list[str]) -> list[str]:
    return sorted(texts, key=menu_sort_key)


def test_digit_runs_are_compared_as_numbers():
    assert ordered(["10 - X", "2 - Y", "1 - Z"]) == ["1 - Z", "2 - Y", "10 - X"]


def test_dotted_numbering_follows_each_number():
    assert ordered(["2.10 - A", "2.2 - B", "10.1 - C", "2.1 - D"]) == ["2.1 - D", "2.2 - B", "2.10 - A", "10.1 - C"]


def test_accents_are_ignored():
    assert ordered(["Ácido", "abacate", "Zebra"]) == ["abacate", "Ácido", "Zebra"]


def test_case_is_ignored():
    assert ordered(["menu b", "Menu A", "MENU C"]) == ["Menu A", "menu b", "MENU C"]


def test_numbers_come_before_text_at_the_same_position():
    assert ordered(["abacate", "10 - X", "2 - Y", "Ácido"]) == ["2 - Y", "10 - X", "abacate", "Ácido"]


def test_a_prefix_comes_before_its_extension():
    assert ordered(["Duvidas 2", "Dúvidas"]) == ["Dúvidas", "Duvidas 2"]


def test_leading_zeros_do_not_change_the_value():
    assert menu_sort_key("007") == menu_sort_key("7")


def test_the_key_tags_numbers_and_text_apart():
    assert menu_sort_key("Ab12c") == ((1, "ab"), (0, 12), (1, "c"))


def test_the_empty_text_has_an_empty_key():
    assert menu_sort_key("") == ()


def test_compatibility_forms_fold_to_plain_digits():
    assert menu_sort_key("²") == menu_sort_key("2")


def test_a_huge_digit_run_does_not_raise():
    assert menu_sort_key("9" * 6000)[0][0] == 0


def test_submenus_are_ordered_by_selection_name_not_by_creation(session: Session):
    parent = add(session, "pai")
    add(session, "a", "10 - X", parent.id)
    add(session, "b", "Ácido", parent.id)
    add(session, "c", "2 - Y", parent.id)
    add(session, "d", "abacate", parent.id)

    assert [m.selection_name for m in get_submenus(session, parent.id)] == [  # type: ignore
        "2 - Y",
        "10 - X",
        "abacate",
        "Ácido",
    ]


def test_submenus_are_not_ordered_by_internal_name(session: Session):
    parent = add(session, "pai")
    add(session, "z", "1 - Primeiro", parent.id)
    add(session, "a", "2 - Segundo", parent.id)

    assert [m.name for m in get_submenus(session, parent.id)] == ["z", "a"]  # type: ignore


def test_equal_titles_are_ordered_by_id(session: Session):
    parent = add(session, "pai")
    first = add(session, "x", "Mesmo", parent.id)
    second = add(session, "y", "mesmo", parent.id)
    third = add(session, "z", "MESMO", parent.id)

    assert [m.id for m in get_submenus(session, parent.id)] == [first.id, second.id, third.id]  # type: ignore


def test_root_children_are_ordered_by_selection_name(session: Session):
    root = add(session, "raiz")
    add(session, "a", "2-Tutoria", root.id)
    add(session, "b", "1-Monitoria", root.id)

    assert [m.selection_name for m in get_root_children(session)] == ["1-Monitoria", "2-Tutoria"]


def test_the_admin_list_is_ordered_by_internal_name(session: Session):
    add(session, "menu b")
    add(session, "Dúvidas")
    add(session, "Duvidas 2")
    add(session, "Menu A")

    assert [m.name for m in get_all_menus(session)] == ["Dúvidas", "Duvidas 2", "Menu A", "menu b"]


def test_the_admin_list_is_not_ordered_by_selection_name(session: Session):
    add(session, "a", "Z")
    add(session, "b", "A")

    assert [m.name for m in get_all_menus(session)] == ["a", "b"]


def test_the_parent_selector_is_ordered_by_internal_name(session: Session):
    add(session, "menu 10")
    add(session, "menu 2")
    add(session, "Ácido")

    assert [m.name for m in get_valid_parent_menus(session)] == ["Ácido", "menu 2", "menu 10"]


def test_the_parent_selector_keeps_the_order_when_excluding_descendants(session: Session):
    keep_b = add(session, "b")
    keep_a = add(session, "A")
    excluded = add(session, "c")
    add(session, "filho", parent_id=excluded.id)

    assert [m.id for m in get_valid_parent_menus(session, excluded.id)] == [keep_a.id, keep_b.id]
