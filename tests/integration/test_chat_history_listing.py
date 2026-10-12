"""
Testes de integração da listagem paginada do histórico de conversas exibida no painel.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session

from src.models.chat_history_model import ChatHistory
from src.models.menu_model import Menu
from src.services.webhook.chat_history_log import HISTORY_PAGE_SIZE, HistoryPage, list_history

BASE_TIME = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
BSUID = "BR.1000000000001"


def add_rows(session: Session, count: int) -> None:
    """Grava `count` linhas de histórico, cada uma um segundo mais recente que a anterior."""
    session.add_all(
        ChatHistory(
            user_id=BSUID,
            role="user",
            content=f"mensagem {index}",
            created_at=BASE_TIME + timedelta(seconds=index),
        )
        for index in range(1, count + 1)
    )
    session.commit()


def contents(page: HistoryPage) -> list[str]:
    return [row.content for row in page.rows]


def test_page_size_is_fifty():
    assert HISTORY_PAGE_SIZE == 50


def test_empty_history_returns_an_empty_first_page(session: Session):
    page = list_history(session, 1)

    assert page == HistoryPage(rows=[], page=1, has_previous=False, has_next=False)


def test_rows_are_listed_newest_first(session: Session):
    add_rows(session, 3)

    page = list_history(session, 1)

    assert contents(page) == ["mensagem 3", "mensagem 2", "mensagem 1"]


def test_rows_with_the_same_timestamp_are_listed_by_descending_id(session: Session):
    session.add_all(ChatHistory(user_id=BSUID, content=f"igual {index}", created_at=BASE_TIME) for index in range(3))
    session.commit()

    page = list_history(session, 1)

    assert contents(page) == ["igual 2", "igual 1", "igual 0"]


def test_row_carries_id_content_and_utc_timestamp(session: Session):
    add_rows(session, 1)

    row = list_history(session, 1).rows[0]

    assert row.id == 1
    assert row.content == "mensagem 1"
    assert row.created_at == BASE_TIME + timedelta(seconds=1)


def test_user_label_prefers_the_phone_number(session: Session):
    session.add(ChatHistory(user_id=BSUID, wa_id="554798765432", content="oi"))
    session.commit()

    assert list_history(session, 1).rows[0].user_label == "554798765432"


def test_user_label_falls_back_to_the_bsuid(session: Session):
    session.add(ChatHistory(user_id=BSUID, wa_id=None, content="oi"))
    session.commit()

    assert list_history(session, 1).rows[0].user_label == BSUID


@pytest.mark.parametrize(("role", "label"), [("user", "Usuário"), ("bot", "Bot")])
def test_role_label_is_portuguese(session: Session, role: str, label: str):
    session.add(ChatHistory(user_id=BSUID, role=role, content="oi"))
    session.commit()

    assert list_history(session, 1).rows[0].role_label == label


def test_menu_name_is_shown_when_the_row_references_a_menu(session: Session):
    menu = Menu(name="Cursos", selection_name="C", message="M")
    session.add(menu)
    session.commit()
    session.add(ChatHistory(user_id=BSUID, content="oi", menu_id=menu.id))
    session.commit()

    assert list_history(session, 1).rows[0].menu_name == "Cursos"


def test_menu_name_is_a_dash_without_a_menu(session: Session):
    session.add(ChatHistory(user_id=BSUID, content="oi", menu_id=None))
    session.commit()

    assert list_history(session, 1).rows[0].menu_name == "-"


def test_menu_name_is_a_dash_after_the_menu_was_deleted(session: Session):
    menu = Menu(name="Cursos", selection_name="C", message="M")
    session.add(menu)
    session.commit()
    session.add(ChatHistory(user_id=BSUID, content="oi", menu_id=menu.id))
    session.commit()
    session.delete(menu)
    session.commit()

    assert list_history(session, 1).rows[0].menu_name == "-"


def test_first_of_several_pages_has_only_a_next_link(session: Session):
    add_rows(session, 120)

    page = list_history(session, 1)

    assert (page.page, page.has_previous, page.has_next) == (1, False, True)
    assert contents(page)[0] == "mensagem 120" and len(page.rows) == 50 and contents(page)[-1] == "mensagem 71"


def test_middle_page_has_both_links_and_the_right_rows(session: Session):
    add_rows(session, 120)

    page = list_history(session, 2)

    assert (page.page, page.has_previous, page.has_next) == (2, True, True)
    assert contents(page)[0] == "mensagem 70" and len(page.rows) == 50 and contents(page)[-1] == "mensagem 21"


def test_last_page_has_the_remaining_rows_and_only_a_previous_link(session: Session):
    add_rows(session, 120)

    page = list_history(session, 3)

    assert (page.page, page.has_previous, page.has_next) == (3, True, False)
    assert contents(page)[0] == "mensagem 20" and len(page.rows) == 20 and contents(page)[-1] == "mensagem 1"


def test_exactly_one_full_page_has_no_next_link(session: Session):
    add_rows(session, 50)

    page = list_history(session, 1)

    assert len(page.rows) == 50
    assert page.has_next is False


def test_one_row_over_a_full_page_creates_a_second_page(session: Session):
    add_rows(session, 51)

    first = list_history(session, 1)
    second = list_history(session, 2)

    assert first.has_next is True
    assert contents(second) == ["mensagem 1"]
    assert (second.has_previous, second.has_next) == (True, False)


@pytest.mark.parametrize("requested", [0, -1, -100])
def test_pages_below_one_fall_back_to_the_first_page(session: Session, requested: int):
    add_rows(session, 120)

    page = list_history(session, requested)

    assert page.page == 1
    assert contents(page)[0] == "mensagem 120"


@pytest.mark.parametrize("requested", [4, 99, 10**30])
def test_pages_past_the_end_fall_back_to_the_last_page(session: Session, requested: int):
    add_rows(session, 120)

    page = list_history(session, requested)

    assert page.page == 3
    assert len(page.rows) == 20


def test_out_of_range_page_on_a_short_history_shows_page_one(session: Session):
    add_rows(session, 10)

    page = list_history(session, 99)

    assert (page.page, len(page.rows), page.has_previous, page.has_next) == (1, 10, False, False)


def test_order_follows_the_timestamp_before_the_id(session: Session):
    session.add(ChatHistory(user_id=BSUID, content="id menor, mais nova", created_at=BASE_TIME + timedelta(hours=1)))
    session.add(ChatHistory(user_id=BSUID, content="id maior, mais antiga", created_at=BASE_TIME))
    session.commit()

    page = list_history(session, 1)

    assert contents(page) == ["id menor, mais nova", "id maior, mais antiga"]
