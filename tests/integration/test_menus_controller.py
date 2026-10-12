"""
Testes de integração para as rotas administrativas de MenusController.
"""

import re
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from src.models.chat_history_model import ChatHistory
from src.models.menu_model import Menu
from src.models.user_session_model import UserSession
from src.models.session_model import AdminSession
from tests.conftest import seed_test_admin
from src.core.security import SESSION_COOKIE_NAME, generate_session_token, generate_csrf_token
from main import app


def make_client(session: Session) -> TestClient:
    """
    Cria cliente de teste autenticado com sessão de administrador e CSRF token.
    """
    admin = seed_test_admin(session)
    token = generate_session_token()
    csrf = generate_csrf_token(token)

    admin_session = AdminSession(
        id=token,
        user_id=admin.id,  # type: ignore
        expires_at=datetime.now(timezone.utc) + timedelta(hours=12),
    )
    session.add(admin_session)
    session.commit()

    c = TestClient(app)
    c.cookies.set(SESSION_COOKIE_NAME, token)
    c.headers.update({"X-CSRF-Token": csrf})
    return c


def test_get_menus_renders_split_view_page(session: Session):
    """
    GET /menus deve retornar status 200 e carregar o layout master-detail.
    """
    m1 = Menu(name="Graduação", selection_name="Grad", message="Opções", parent_id=None)
    session.add(m1)
    session.commit()

    client = make_client(session)
    response = client.get("/menus")

    assert response.status_code == 200
    assert "Graduação" in response.text
    assert 'id="detail-pane"' in response.text


def test_get_menus_shows_warning_when_no_root(session: Session):
    """
    GET /menus sem menu raiz deve exibir banner vermelho de alerta.
    """
    client = make_client(session)
    response = client.get("/menus")

    assert response.status_code == 200
    assert "Atenção: Nenhum menu está definido como Raiz" in response.text


ROOT_WARNING = "Atenção: Nenhum menu está definido como Raiz"


def test_root_warning_reloads_whenever_the_menu_list_changes(session: Session):
    client = make_client(session)

    page = client.get("/menus").text

    container = re.search(r'<div id="root-warning"[^>]*>', page)
    assert container is not None
    assert 'hx-get="/menus/aviso-raiz"' in container.group(0)
    assert 'hx-trigger="menuListChanged from:body"' in container.group(0)


def test_first_menu_form_on_an_empty_database_is_already_marked_as_root(session: Session):
    client = make_client(session)

    page = client.get("/menus").text

    checkbox = re.search(r'<input type="checkbox"[^>]*id="is_root"[^>]*>', page, re.S)
    assert checkbox is not None
    assert "checked" in checkbox.group(0)
    assert "disabled" not in checkbox.group(0)


def test_root_warning_container_is_present_when_a_root_exists(session: Session):
    session.add(Menu(name="Raiz", selection_name="Raiz", message="Olá", parent_id=None))
    session.commit()
    client = make_client(session)

    page = client.get("/menus").text

    assert 'id="root-warning"' in page
    assert ROOT_WARNING not in page


def test_root_warning_fragment_disappears_after_saving_a_root(session: Session):
    client = make_client(session)
    assert ROOT_WARNING in client.get("/menus/aviso-raiz").text

    saved = client.post(
        "/menus", data={"name": "Raiz", "selection_name": "Raiz", "message": "Olá", "is_root": "on"}
    )

    assert saved.headers["HX-Trigger"] == "menuListChanged"
    assert ROOT_WARNING not in client.get("/menus/aviso-raiz").text


def test_root_warning_fragment_returns_after_deleting_the_root(session: Session):
    root = Menu(name="Raiz", selection_name="Raiz", message="Olá", parent_id=None)
    session.add(root)
    session.commit()
    client = make_client(session)

    client.delete(f"/menus/{root.id}")

    assert ROOT_WARNING in client.get("/menus/aviso-raiz").text


def test_get_menu_list_partial(session: Session):
    """
    GET /menus/lista deve retornar o fragmento HTML com itens da lista.
    """
    m1 = Menu(name="ListaMenu", selection_name="LM", message="Msg", parent_id=None)
    session.add(m1)
    session.commit()

    client = make_client(session)
    response = client.get(f"/menus/lista?selected_id={m1.id}")
    assert response.status_code == 200
    assert "ListaMenu" in response.text


def test_get_menu_card_partial_via_htmx(session: Session):
    """
    GET /menus/{id}/card deve retornar apenas o partial do formulário para o menu.
    """
    m1 = Menu(name="Pesquisa", selection_name="Pesq", message="Iniciação científica", parent_id=None)
    session.add(m1)
    session.commit()
    session.refresh(m1)

    client = make_client(session)
    response = client.get(f"/menus/{m1.id}/card", headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert "Pesquisa" in response.text
    assert "Iniciação científica" in response.text
    assert "<form" in response.text


def test_get_menu_card_not_found(session: Session):
    """
    GET /menus/{id}/card com ID inexistente deve retornar 404.
    """
    client = make_client(session)
    response = client.get("/menus/99999/card")
    assert response.status_code == 404


def test_get_new_menu_card_provides_clean_draft(session: Session):
    """
    GET /menus/novo/card deve carregar formulário com nome default 'Novo Menu'.
    """
    client = make_client(session)
    response = client.get("/menus/novo/card", headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert "Novo Menu" in response.text


def test_post_create_root_menu_success(session: Session):
    """
    POST /menus com is_root=true deve criar a raiz com sucesso.
    """
    client = make_client(session)
    payload = {
        "name": "Extensão Universitária",
        "selection_name": "Ext",
        "message": "Projetos de extensão",
        "is_root": "true",
    }
    response = client.post("/menus", data=payload, headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert "Extensão Universitária" in response.text
    assert "menuListChanged" in response.headers.get("HX-Trigger", "")


def test_post_create_second_root_rejected_with_422(session: Session):
    """
    POST /menus tentando criar uma segunda raiz deve retornar 422.
    """
    m1 = Menu(name="Primeira Raiz", selection_name="R1", message="M1", parent_id=None)
    session.add(m1)
    session.commit()

    client = make_client(session)
    payload = {
        "name": "Segunda Raiz",
        "selection_name": "R2",
        "message": "M2",
        "is_root": "true",
    }
    response = client.post("/menus", data=payload, headers={"HX-Request": "true"})

    assert response.status_code == 422
    assert "Já existe um menu raiz definido" in response.text


def test_post_update_menu_cycle_rejection(session: Session):
    """
    POST /menus/{id} deve rejeitar ciclo hierárquico com código 422.
    """
    root = Menu(name="Pai", selection_name="P", message="P", parent_id=None)
    session.add(root)
    session.commit()
    session.refresh(root)

    child = Menu(name="Filho", selection_name="F", message="F", parent_id=root.id)
    session.add(child)
    session.commit()
    session.refresh(child)

    client = make_client(session)
    payload = {
        "name": "Pai",
        "selection_name": "P",
        "message": "P",
        "parent_id": str(child.id),
        "is_root": "false",
    }
    response = client.post(f"/menus/{root.id}", data=payload, headers={"HX-Request": "true"})

    assert response.status_code == 422
    assert "Ciclo" in response.text


def test_delete_menu_with_submenus_blocked(session: Session):
    """
    DELETE /menus/{id} deve rejeitar exclusão de menu com filhos com status 400.
    """
    parent = Menu(name="Diretoria", selection_name="Dir", message="Dir", parent_id=None)
    session.add(parent)
    session.commit()
    session.refresh(parent)

    child = Menu(name="Secretaria", selection_name="Sec", message="Sec", parent_id=parent.id)
    session.add(child)
    session.commit()

    client = make_client(session)
    response = client.delete(f"/menus/{parent.id}", headers={"HX-Request": "true"})

    assert response.status_code == 400
    assert "submenus vinculados" in response.text


def test_delete_menu_not_found_returns_400(session: Session):
    """
    DELETE /menus/{id} com ID inexistente deve capturar ValueError e retornar 400.
    """
    client = make_client(session)
    response = client.delete("/menus/99999", headers={"HX-Request": "true"})
    assert response.status_code == 400


def test_delete_menu_success_triggers_menu_list_changed(session: Session):
    """
    DELETE /menus/{id} em menu folha deve retornar 200 com HX-Trigger: menuListChanged.
    """
    root = Menu(name="Root", selection_name="R", message="R", parent_id=None)
    session.add(root)
    session.commit()
    session.refresh(root)

    leaf = Menu(name="Leaf", selection_name="L", message="L", parent_id=root.id)
    session.add(leaf)
    session.commit()
    session.refresh(leaf)

    leaf_id = leaf.id
    client = make_client(session)
    response = client.delete(f"/menus/{leaf_id}", headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert response.headers.get("HX-Trigger") == "menuListChanged"
    session.expire_all()
    assert session.get(Menu, leaf_id) is None


def test_update_menu_second_root_rejected_without_changing_hierarchy(session: Session):
    """
    POST /menus/{id} com is_root=true em um submenu deve responder 422 e manter a hierarquia intacta.
    """
    old_root = Menu(name="OldRoot", selection_name="OR", message="OR", parent_id=None)
    session.add(old_root)
    session.commit()
    session.refresh(old_root)

    child = Menu(name="Child", selection_name="C", message="C", parent_id=old_root.id)
    session.add(child)
    session.commit()
    session.refresh(child)

    client = make_client(session)
    payload = {
        "name": "Child",
        "selection_name": "C",
        "message": "Nova Raiz",
        "is_root": "true",
    }
    response = client.post(f"/menus/{child.id}", data=payload, headers={"HX-Request": "true"})

    assert response.status_code == 422
    assert "Já existe" in response.text
    assert "HX-Trigger" not in response.headers
    session.refresh(child)
    session.refresh(old_root)
    assert child.parent_id == old_root.id
    assert child.message == "C"
    assert old_root.parent_id is None


def test_update_menu_uncheck_root_without_parent(session: Session):
    """
    POST /menus/{id} desmarcando is_root na raiz e deixando parent_id vazio salva o menu sem pai.
    """
    root = Menu(name="Principal", selection_name="P", message="P", parent_id=None)
    session.add(root)
    session.commit()
    session.refresh(root)

    client = make_client(session)
    payload = {
        "name": "Principal",
        "selection_name": "P",
        "message": "P",
        "parent_id": "",
        "is_root": "false",
    }
    response = client.post(f"/menus/{root.id}", data=payload, headers={"HX-Request": "true"})

    assert response.status_code == 200
    session.refresh(root)
    assert root.parent_id is None


def _root_checkbox(html: str) -> str:
    """Extrai a tag <input> do checkbox 'Menu Raiz' do card renderizado."""
    match = re.search(r'<input[^>]*id="is_root"[^>]*>', html, re.DOTALL)
    assert match is not None
    return match.group(0)


def _tree(session: Session) -> tuple[Menu, Menu]:
    """Cria uma raiz com um filho e devolve ambos."""
    root = Menu(name="menu_inicio", selection_name="Início", message="Bem-vindo")
    session.add(root)
    session.commit()
    child = Menu(name="Cursos", selection_name="Cursos", message="C", parent_id=root.id)
    session.add(child)
    session.commit()
    return root, child


def test_child_card_disables_root_checkbox_and_names_the_existing_root(session: Session):
    root, child = _tree(session)

    response = make_client(session).get(f"/menus/{child.id}/card")

    assert "disabled" in _root_checkbox(response.text)
    assert "menu_inicio" in response.text
    assert "passará a ser um submenu" not in response.text


def test_root_card_keeps_root_checkbox_enabled_and_checked(session: Session):
    root, _ = _tree(session)

    response = make_client(session).get(f"/menus/{root.id}/card")

    checkbox = _root_checkbox(response.text)
    assert "disabled" not in checkbox
    assert "checked" in checkbox


def test_new_card_disables_root_checkbox_when_a_root_exists(session: Session):
    _tree(session)

    response = make_client(session).get("/menus/novo/card")

    assert "disabled" in _root_checkbox(response.text)


def test_new_card_enables_root_checkbox_when_there_is_no_root(session: Session):
    response = make_client(session).get("/menus/novo/card")

    checkbox = _root_checkbox(response.text)
    assert "disabled" not in checkbox
    assert "checked" in checkbox


def test_update_error_card_disables_root_checkbox_for_a_child(session: Session):
    root, child = _tree(session)
    payload = {"name": "Cursos", "selection_name": "C", "message": "C", "is_root": "true"}

    response = make_client(session).post(f"/menus/{child.id}", data=payload)

    assert response.status_code == 422
    assert "disabled" in _root_checkbox(response.text)


def test_update_success_card_disables_root_checkbox_for_a_child(session: Session):
    root, child = _tree(session)
    payload = {
        "name": "Cursos", "selection_name": "C", "message": "novo",
        "parent_id": str(root.id), "is_root": "false",
    }

    response = make_client(session).post(f"/menus/{child.id}", data=payload)

    assert response.status_code == 200
    assert "disabled" in _root_checkbox(response.text)


def test_create_success_card_keeps_root_checkbox_enabled_for_the_first_root(session: Session):
    payload = {"name": "menu_inicio", "selection_name": "I", "message": "M", "is_root": "true"}

    response = make_client(session).post("/menus", data=payload)

    checkbox = _root_checkbox(response.text)
    assert "disabled" not in checkbox
    assert "checked" in checkbox


def test_create_error_card_disables_root_checkbox_when_a_root_exists(session: Session):
    _tree(session)
    payload = {"name": "Outra", "selection_name": "O", "message": "M", "is_root": "true"}

    response = make_client(session).post("/menus", data=payload)

    assert response.status_code == 422
    assert "disabled" in _root_checkbox(response.text)


def test_delete_leaf_referenced_by_history_and_sessions_succeeds(session: Session):
    """
    DELETE /menus/{id} em folha visitada deve responder 200 e manter histórico e sessão com menu nulo.
    """
    _, leaf = _tree(session)
    leaf_id = leaf.id
    session.add(ChatHistory(user_id="BR.1000000000001", role="user", content="Cursos", menu_id=leaf_id))
    session.add(UserSession(user_id="BR.1000000000001", current_menu_id=leaf_id))
    session.commit()

    response = make_client(session).delete(f"/menus/{leaf_id}", headers={"HX-Request": "true"})

    assert response.status_code == 200
    session.expire_all()
    assert session.get(Menu, leaf_id) is None
    history = session.exec(select(ChatHistory)).one()
    assert (history.content, history.menu_id) == ("Cursos", None)
    assert session.exec(select(UserSession)).one().current_menu_id is None


BLANK_FIELDS_MESSAGE = "Preencha nome, texto de seleção e mensagem."


def test_create_menu_with_blank_selection_name_returns_422_and_saves_nothing(session: Session):
    client = make_client(session)

    response = client.post(
        "/menus",
        data={"name": "Cursos", "selection_name": "   ", "message": "Texto", "is_root": "true"},
    )

    assert response.status_code == 422
    assert BLANK_FIELDS_MESSAGE in response.text
    assert session.exec(select(Menu)).all() == []


def test_update_menu_with_blank_message_returns_422_and_keeps_the_menu(session: Session):
    client = make_client(session)
    root = Menu(name="Raiz", selection_name="R", message="Original")
    session.add(root)
    session.commit()

    response = client.post(
        f"/menus/{root.id}",
        data={"name": "Raiz", "selection_name": "R", "message": "  ", "is_root": "true"},
    )

    assert response.status_code == 422
    assert BLANK_FIELDS_MESSAGE in response.text
    session.refresh(root)
    assert root.message == "Original"


def test_create_menu_trims_padded_values(session: Session):
    client = make_client(session)

    response = client.post(
        "/menus",
        data={"name": "  Cursos  ", "selection_name": " Cursos ", "message": " Texto ", "is_root": "true"},
    )

    assert response.status_code == 200
    stored = session.exec(select(Menu)).one()
    assert (stored.name, stored.selection_name, stored.message) == ("Cursos", "Cursos", "Texto")


def test_menu_list_items_carry_their_id_and_the_card_carries_the_entity_id(session: Session):
    client = make_client(session)
    first = Menu(name="Primeiro", selection_name="P", message="M")
    second = Menu(name="Segundo", selection_name="S", message="M", parent_id=1)
    session.add(first)
    session.add(second)
    session.commit()

    listing = client.get("/menus/lista")
    card = client.get(f"/menus/{second.id}/card")

    assert re.findall(r'data-id="(\d+)"', listing.text) == [str(first.id), str(second.id)]
    assert re.findall(r'data-entity-id="(\d+)"', card.text) == [str(second.id)]


def test_new_menu_card_has_no_entity_id(session: Session):
    client = make_client(session)

    response = client.get("/menus/novo/card")

    assert "data-entity-id" not in response.text


def test_menus_page_renders_the_selected_card_and_its_active_list_item(session: Session):
    client = make_client(session)
    root = Menu(name="Raiz", selection_name="R", message="M")
    session.add(root)
    session.commit()

    response = client.get("/menus")

    assert f'data-entity-id="{root.id}"' in response.text
    assert re.search(rf'data-id="{root.id}"\s+class="split-list-item active"', response.text)


LIST_LIMIT_MESSAGE = "Este menu já tem o máximo de 9 opções permitido pelo WhatsApp."


def _root_with_children(session: Session, children: int) -> Menu:
    root = Menu(name="raiz", selection_name="R", message="M")
    session.add(root)
    session.commit()
    session.add_all(Menu(name=f"filho {i}", selection_name="F", message="M", parent_id=root.id) for i in range(children))
    session.commit()
    return root


def test_create_tenth_child_under_the_root_returns_422_with_the_limit_message(session: Session):
    client = make_client(session)
    root = _root_with_children(session, 9)

    response = client.post(
        "/menus",
        data={"name": "extra", "selection_name": "E", "message": "M", "parent_id": str(root.id), "is_root": "false"},
    )

    assert response.status_code == 422
    assert LIST_LIMIT_MESSAGE in response.text
    assert len(session.exec(select(Menu)).all()) == 10


def test_create_tenth_child_under_a_submenu_returns_422_with_the_limit_message(session: Session):
    client = make_client(session)
    root = _root_with_children(session, 1)
    submenu = session.exec(select(Menu).where(Menu.parent_id == root.id)).one()
    session.add_all(
        Menu(name=f"neto {i}", selection_name="N", message="M", parent_id=submenu.id) for i in range(9)
    )
    session.commit()

    response = client.post(
        "/menus",
        data={"name": "extra", "selection_name": "E", "message": "M", "parent_id": str(submenu.id), "is_root": "false"},
    )

    assert response.status_code == 422
    assert LIST_LIMIT_MESSAGE in response.text
    assert len(session.exec(select(Menu).where(Menu.parent_id == submenu.id)).all()) == 9


def test_create_ninth_child_under_the_root_succeeds(session: Session):
    client = make_client(session)
    root = _root_with_children(session, 8)

    response = client.post(
        "/menus",
        data={"name": "extra", "selection_name": "E", "message": "M", "parent_id": str(root.id), "is_root": "false"},
    )

    assert response.status_code == 200


def test_moving_a_menu_under_a_full_parent_returns_422(session: Session):
    client = make_client(session)
    root = _root_with_children(session, 9)
    first_child = session.exec(select(Menu).where(Menu.parent_id == root.id)).first()
    assert first_child is not None
    leaf = Menu(name="folha", selection_name="L", message="M", parent_id=first_child.id)
    session.add(leaf)
    session.commit()

    response = client.post(
        f"/menus/{leaf.id}",
        data={"name": "folha", "selection_name": "L", "message": "M", "parent_id": str(root.id), "is_root": "false"},
    )

    assert response.status_code == 422
    assert LIST_LIMIT_MESSAGE in response.text
    session.refresh(leaf)
    assert leaf.parent_id == first_child.id


def test_create_menu_422_keeps_what_the_admin_typed(session: Session):
    client = make_client(session)
    root = Menu(name="raiz", selection_name="R", message="M")
    session.add(root)
    session.commit()

    response = client.post(
        "/menus",
        data={"name": "Digitado", "selection_name": "  ", "message": "Meu texto longo", "parent_id": str(root.id), "is_root": "false"},
    )

    assert response.status_code == 422
    assert 'value="Digitado"' in response.text
    assert ">Meu texto longo</textarea>" in response.text
    assert re.search(rf'<option value="{root.id}"\s+selected>', response.text)
    assert 'value="Novo Menu"' not in response.text


def test_create_menu_422_keeps_the_root_checkbox_when_no_root_exists(session: Session):
    client = make_client(session)

    response = client.post(
        "/menus", data={"name": "Raiz nova", "selection_name": "", "message": "M", "is_root": "true"}
    )

    assert response.status_code == 422
    assert re.search(r'id="is_root"[^>]*\bchecked\b', response.text, re.S)
    assert 'value="Raiz nova"' in response.text


def test_create_menu_422_without_the_root_flag_keeps_the_checkbox_unchecked(session: Session):
    client = make_client(session)

    response = client.post(
        "/menus", data={"name": "Sub", "selection_name": "", "message": "M", "is_root": "false"}
    )

    assert response.status_code == 422
    assert not re.search(r'id="is_root"[^>]*\bchecked\b', response.text, re.S)


def test_update_menu_422_keeps_the_submitted_values(session: Session):
    client = make_client(session)
    root = Menu(name="raiz", selection_name="R", message="Original")
    session.add(root)
    session.commit()

    response = client.post(
        f"/menus/{root.id}",
        data={"name": "Nome digitado", "selection_name": "Sel digitada", "message": "  ", "is_root": "true"},
    )

    assert response.status_code == 422
    assert 'value="Nome digitado"' in response.text
    assert 'value="Sel digitada"' in response.text
    assert "Editar Menu: raiz" in response.text


def test_create_menu_422_escapes_the_echoed_values(session: Session):
    client = make_client(session)

    response = client.post(
        "/menus", data={"name": '"><script>alert(1)</script>', "selection_name": "", "message": "M", "is_root": "true"}
    )

    assert response.status_code == 422
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text
