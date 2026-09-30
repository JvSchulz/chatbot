"""
Testes do script de carga de menus, sempre contra bancos temporários.
"""

from pathlib import Path
from sqlalchemy import create_engine, event
from sqlmodel import Session, select
from src.core.db import set_sqlite_pragma
from src.models.chat_history_model import ChatHistory
from src.models.menu_model import Menu
from src.models.user_session_model import UserSession
from scripts.seed_menus import main, seed_menus

TOP_LEVEL = ["menu_cursos", "menu_secretaria", "menu_suporte", "menu_atendente"]


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
        assert menus["curso_cc"].parent_id == menus["menu_cursos"].id
        assert menus["sec_documentos"].parent_id == menus["menu_secretaria"].id
        assert menus["doc_trancamento"].parent_id == menus["sec_documentos"].id
        assert menus["sup_labs"].parent_id == menus["menu_suporte"].id


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
        leaf = _by_name(session)["doc_atestado"]
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
