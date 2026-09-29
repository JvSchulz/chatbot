"""
Testes de integração para as rotas administrativas de MenusController.
"""

from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlmodel import Session
from src.models.menu_model import Menu
from src.models.session_model import AdminSession
from src.services.user_service import seed_default_admin
from src.core.security import SESSION_COOKIE_NAME, generate_session_token, generate_csrf_token
from main import app


def make_client(session: Session) -> TestClient:
    """
    Cria cliente de teste autenticado com sessão de administrador e CSRF token.
    """
    admin = seed_default_admin(session)
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


def test_update_menu_promote_child_to_root_transfers_hierarchy(session: Session):
    """
    POST /menus/{id} com is_root=true em um submenu deve promovê-lo a raiz e vincular a raiz antiga como filha.
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

    assert response.status_code == 200
    assert response.headers.get("HX-Trigger") == "menuListChanged"
    session.refresh(child)
    session.refresh(old_root)
    assert child.parent_id is None
    assert old_root.parent_id == child.id


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
