"""
Testes do script de carga de menus, sempre contra bancos temporários.
"""

from collections import Counter
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlmodel import Session, select
from src.core.db import set_sqlite_pragma
from src.models.chat_history_model import ChatHistory
from src.models.menu_model import Menu
from src.models.user_session_model import UserSession
from scripts.seed_menus import MENUS_DATA, main, seed_menus
from src.services.menu_service import MAX_MESSAGE_LEN, MAX_SELECTION_NAME_LEN, MENU_CHILDREN_LIMIT, menu_sort_key

TOP_LEVEL = ["1 menu_cursos", "2 menu_secretaria", "3 menu_suporte", "4 menu_atendente"]


def _open(path: Path) -> Session:
    engine = create_engine(f"sqlite:///{path}")
    event.listen(engine, "connect", set_sqlite_pragma)
    return Session(engine)


def _by_name(session: Session) -> dict[str, Menu]:
    return {menu.name: menu for menu in session.exec(select(Menu)).all()}


def test_seed_creates_one_root_whose_children_are_the_top_level_menus(tmp_path: Path):
    database = tmp_path / "seed.db"

    seed_menus(database)

    with _open(database) as session:
        menus = _by_name(session)
        roots = [menu for menu in menus.values() if menu.parent_id is None]
        assert [root.name for root in roots] == ["menu_inicio"]
        root_id = menus["menu_inicio"].id
        children = [menu.name for menu in menus.values() if menu.parent_id == root_id]
        assert sorted(children) == sorted(TOP_LEVEL)


def test_seed_keeps_the_existing_subtrees(tmp_path: Path):
    database = tmp_path / "seed.db"

    seed_menus(database)

    with _open(database) as session:
        menus = _by_name(session)
        assert len(menus) == 17
        assert menus["1.1 curso_cc"].parent_id == menus["1 menu_cursos"].id
        assert menus["2.2 sec_documentos"].parent_id == menus["2 menu_secretaria"].id
        assert menus["2.2.3 doc_trancamento"].parent_id == menus["2.2 sec_documentos"].id
        assert menus["3.3 sup_labs"].parent_id == menus["3 menu_suporte"].id


def test_seed_root_has_a_greeting_message_and_selection_name(tmp_path: Path):
    database = tmp_path / "seed.db"

    seed_menus(database)

    with _open(database) as session:
        root = _by_name(session)["menu_inicio"]
        assert root.message.strip() != ""
        assert root.selection_name.strip() != ""


def test_seed_does_nothing_when_menus_already_exist(tmp_path: Path, capsys):
    database = tmp_path / "seed.db"
    seed_menus(database)
    with _open(database) as session:
        first_ids = sorted(menu.id for menu in session.exec(select(Menu)).all() if menu.id)

    seed_menus(database)

    with _open(database) as session:
        assert sorted(menu.id for menu in session.exec(select(Menu)).all() if menu.id) == first_ids
    assert "--reset" in capsys.readouterr().out


def test_reset_replaces_menus_even_with_history_and_sessions_referencing_them(tmp_path: Path):
    database = tmp_path / "seed.db"
    seed_menus(database)
    with _open(database) as session:
        leaf = _by_name(session)["2.2.1 doc_atestado"]
        session.add(ChatHistory(user_id="BR.1000000000001", role="user", content="Atestado", menu_id=leaf.id))
        session.add(UserSession(user_id="BR.1000000000001", current_menu_id=leaf.id))
        session.commit()

    seed_menus(database, reset=True)

    with _open(database) as session:
        assert len(session.exec(select(Menu)).all()) == 17
        history = session.exec(select(ChatHistory)).one()
        assert (history.content, history.menu_id) == ("Atestado", None)
        assert session.exec(select(UserSession)).one().current_menu_id is None


def test_main_accepts_db_and_reset_arguments(tmp_path: Path):
    database = tmp_path / "seed.db"
    main(["--db", str(database)])

    main(["--db", str(database), "--reset"])

    with _open(database) as session:
        assert len(session.exec(select(Menu)).all()) == 17


def test_seed_creates_missing_parent_directories(tmp_path: Path):
    database = tmp_path / "nested" / "dir" / "seed.db"

    seed_menus(database)

    assert database.exists()


def test_seed_titles_and_messages_fit_the_whatsapp_limits():
    for item in MENUS_DATA:
        assert len(item["selection_name"]) <= MAX_SELECTION_NAME_LEN, item["selection_name"]
        assert len(item["message"]) <= MAX_MESSAGE_LEN, item["name"]


def test_seed_parents_stay_within_the_children_limit():
    children_per_parent = Counter(item["parent_id"] for item in MENUS_DATA if item["parent_id"] is not None)

    assert max(children_per_parent.values()) <= MENU_CHILDREN_LIMIT


def test_seed_keeps_the_numbered_titles_in_reading_order():
    by_parent: dict[int, list[str]] = {}
    for item in MENUS_DATA:
        if item["parent_id"] is not None:
            by_parent.setdefault(item["parent_id"], []).append(item["selection_name"])

    for titles in by_parent.values():
        assert sorted(titles, key=menu_sort_key) == titles


def test_seed_names_sort_in_the_same_order_as_the_numbered_titles():
    by_parent: dict[int, list[dict]] = {}
    for item in MENUS_DATA:
        if item["parent_id"] is not None:
            by_parent.setdefault(item["parent_id"], []).append(item)

    for siblings in by_parent.values():
        by_name = sorted(siblings, key=lambda item: menu_sort_key(item["name"]))
        assert [item["selection_name"] for item in by_name] == [item["selection_name"] for item in siblings]
