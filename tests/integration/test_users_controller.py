"""
Testes de integração para as rotas administrativas de UsersController.
"""

import re
from fastapi.testclient import TestClient
import pytest
from sqlmodel import Session, select
from src.models.user_model import User
from src.models.session_model import AdminSession
from src.services.user_service import UserData, create_user
from tests.conftest import TEST_ADMIN_PASSWORD, make_user_client, seed_test_admin


def make_admin_client(session: Session) -> TestClient:
    """
    Cria cliente de teste autenticado como o administrador 'admin', mesmo com outros usuários já cadastrados.
    """
    admin = create_user(session, UserData(login="admin", password=TEST_ADMIN_PASSWORD, is_admin=True))
    return make_user_client(session, admin)


def test_get_users_renders_split_view_page(session: Session):
    """
    GET /usuarios deve retornar status 200, carregar a listagem e card de usuários, e injetar o token CSRF.
    """
    u1 = User(login="superadmin", password="hash_password", is_admin=True)
    session.add(u1)
    session.commit()

    client = make_admin_client(session)
    response = client.get("/usuarios")

    assert response.status_code == 200
    assert "superadmin" in response.text
    assert 'id="user-detail-pane"' in response.text
    assert 'hx-headers=' in response.text
    assert 'X-CSRF-Token' in response.text
    assert 'name="csrf-token"' not in response.text


def test_get_user_list_partial(session: Session):
    """
    GET /usuarios/lista deve retornar fragmento HTML com a lista de usuários.
    """
    u1 = User(login="listuser", password="hash", is_admin=False)
    session.add(u1)
    session.commit()

    client = make_admin_client(session)
    response = client.get(f"/usuarios/lista?selected_id={u1.id}")
    assert response.status_code == 200
    assert "listuser" in response.text


def test_get_user_card_partial_via_htmx(session: Session):
    """
    GET /usuarios/{id}/card deve retornar o partial do formulário de usuário.
    """
    u1 = User(login="editor", password="hash_password", is_admin=False)
    session.add(u1)
    session.commit()
    session.refresh(u1)

    client = make_admin_client(session)
    response = client.get(f"/usuarios/{u1.id}/card", headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert "editor" in response.text
    assert "<form" in response.text


def test_get_user_card_not_found(session: Session):
    """
    GET /usuarios/{id}/card com ID inexistente deve retornar 404.
    """
    client = make_admin_client(session)
    response = client.get("/usuarios/99999/card")
    assert response.status_code == 404


def test_post_create_user_persists_and_returns_card(session: Session):
    """
    POST /usuarios deve criar um novo usuário e retornar o card atualizado com trigger.
    """
    client = make_admin_client(session)
    payload = {
        "login": "novofuncionario",
        "password": "SenhaSegura123",
        "is_admin": "true",
    }
    response = client.post("/usuarios", data=payload, headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert "novofuncionario" in response.text
    assert "userListChanged" in response.headers.get("HX-Trigger", "")


def test_post_create_user_duplicate_login_rejected(session: Session):
    """
    POST /usuarios deve rejeitar login duplicado com status 400.
    """
    u1 = User(login="gerente", password="hash", is_admin=False)
    session.add(u1)
    session.commit()

    client = make_admin_client(session)
    payload = {
        "login": "gerente",
        "password": "OutraSenha123",
    }
    response = client.post("/usuarios", data=payload, headers={"HX-Request": "true"})

    assert response.status_code == 400
    assert "já está em uso" in response.text


def test_post_update_user_success_and_error(session: Session):
    """
    POST /usuarios/{id} deve atualizar com sucesso ou retornar erro 400 caso inválido.
    """
    u = User(login="operador", password="hash", is_admin=False)
    session.add(u)
    session.commit()
    session.refresh(u)

    client = make_admin_client(session)
    # Sucesso
    res_ok = client.post(f"/usuarios/{u.id}", data={"login": "operador_chefe", "password": "NovaSenha12345", "is_admin": "true"})
    assert res_ok.status_code == 200
    assert "operador_chefe" in res_ok.text

    # Erro (ID inexistente)
    res_err = client.post("/usuarios/99999", data={"login": "fail", "password": "new"})
    assert res_err.status_code == 400


def test_delete_user_success_and_error(session: Session):
    """
    DELETE /usuarios/{id} deve remover o usuário com sucesso ou retornar 400 em caso de erro.
    """
    u = User(login="temporario", password="hash", is_admin=False)
    session.add(u)
    session.commit()
    session.refresh(u)

    client = make_admin_client(session)
    response = client.delete(f"/usuarios/{u.id}", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "userListChanged" in response.headers.get("HX-Trigger", "")

    # Erro (ID inexistente)
    res_err = client.delete("/usuarios/99999")
    assert res_err.status_code == 400


def test_delete_user_self_deletion_blocked(session: Session):
    """
    DELETE /usuarios/{id} deve bloquear a autoexclusão da conta atualmente conectada com status 400.
    """
    admin = seed_test_admin(session)
    client = make_user_client(session, admin)

    response = client.delete(f"/usuarios/{admin.id}")
    assert response.status_code == 400
    assert "Você não pode excluir sua própria conta em uso" in response.text


def test_users_route_forbidden_for_non_admin(session: Session):
    """
    Rotas de /usuarios devem retornar 403 Forbidden para usuários sem privilégios de administrador.
    """
    editor = User(login="editor_sem_admin", password="123", is_admin=False)
    session.add(editor)
    session.commit()
    session.refresh(editor)

    client = make_user_client(session, editor)

    # GET /usuarios
    res_get = client.get("/usuarios")
    assert res_get.status_code == 403
    assert "Acesso restrito ao administrador" in res_get.text

    # POST /usuarios
    res_post = client.post("/usuarios", data={"login": "x", "password": "y"})
    assert res_post.status_code == 403

    # DELETE /usuarios
    res_delete = client.delete(f"/usuarios/{editor.id}")
    assert res_delete.status_code == 403


def test_navigation_tabs_reflect_user_permissions(session: Session):
    """
    O cabeçalho não deve conter a aba 'Início'.
    A aba 'Usuários' deve ser visível apenas para administradores.
    """
    admin = User(login="admin_chefe", password="123", is_admin=True)
    editor = User(login="editor_comum", password="123", is_admin=False)
    session.add(admin)
    session.add(editor)
    session.commit()
    session.refresh(admin)
    session.refresh(editor)

    client_admin = make_user_client(session, admin)
    res_admin = client_admin.get("/")
    assert res_admin.status_code == 200
    assert "Início" not in res_admin.text
    assert 'href="/usuarios"' in res_admin.text

    client_editor = make_user_client(session, editor)
    res_editor = client_editor.get("/")
    assert res_editor.status_code == 200
    assert "Início" not in res_editor.text
    assert 'href="/usuarios"' not in res_editor.text


def test_post_update_demoting_last_admin_returns_400(session: Session):
    """
    POST /usuarios/{id} que removeria o último administrador deve retornar 400 com a mensagem da regra.
    """
    admin = create_user(session, UserData(login="admin", password=TEST_ADMIN_PASSWORD, is_admin=True))
    client = make_user_client(session, admin)

    response = client.post(f"/usuarios/{admin.id}", data={"login": "admin"})

    assert response.status_code == 400
    assert "Deve existir pelo menos um administrador." in response.text
    session.refresh(admin)
    assert admin.is_admin is True


def test_post_create_user_with_short_password_returns_400(session: Session):
    """
    POST /usuarios com senha de menos de 12 caracteres deve retornar 400 e não criar o usuário.
    """
    client = make_admin_client(session)

    response = client.post("/usuarios", data={"login": "curto", "password": "a" * 11})

    assert response.status_code == 400
    assert "A senha deve ter pelo menos 12 caracteres." in response.text
    assert session.exec(select(User).where(User.login == "curto")).first() is None


def test_post_update_user_with_short_password_returns_400(session: Session):
    """
    POST /usuarios/{id} com nova senha curta deve retornar 400 e manter a senha atual.
    """
    client = make_admin_client(session)
    target = create_user(session, UserData(login="alvo", password="SenhaOriginal123"))
    original_hash = target.password

    response = client.post(f"/usuarios/{target.id}", data={"login": "alvo", "password": "curta"})

    assert response.status_code == 400
    assert "A senha deve ter pelo menos 12 caracteres." in response.text
    session.refresh(target)
    assert target.password == original_hash


def test_post_update_user_with_blank_password_keeps_password(session: Session):
    """
    POST /usuarios/{id} com senha em branco deve manter a senha atual e responder 200.
    """
    client = make_admin_client(session)
    target = create_user(session, UserData(login="alvo", password="SenhaOriginal123"))
    original_hash = target.password

    response = client.post(f"/usuarios/{target.id}", data={"login": "alvo", "password": "   "})

    assert response.status_code == 200
    session.refresh(target)
    assert target.password == original_hash


def test_delete_logged_in_user_returns_200_and_ends_their_access(session: Session):
    """
    DELETE /usuarios/{id} de um usuário com sessão ativa deve retornar 200, e o acesso dele deixa de valer.
    """
    admin_client = make_admin_client(session)
    target = create_user(session, UserData(login="logado", password="SenhaOriginal123"))
    target_id = target.id
    target_client = make_user_client(session, target)
    assert target_client.get("/menus", follow_redirects=False).status_code == 200

    response = admin_client.delete(f"/usuarios/{target_id}")

    assert response.status_code == 200
    session.expire_all()
    assert session.get(User, target_id) is None
    assert session.exec(select(AdminSession).where(AdminSession.user_id == target_id)).first() is None
    assert target_client.get("/menus", follow_redirects=False).status_code == 303


def test_password_change_ends_sessions_of_that_user(session: Session):
    """
    Trocar a senha de um usuário deve invalidar as sessões dele, que passa a ser redirecionado ao login.
    """
    admin_client = make_admin_client(session)
    target = create_user(session, UserData(login="logado", password="SenhaOriginal123"))
    target_client = make_user_client(session, target)
    assert target_client.get("/menus", follow_redirects=False).status_code == 200

    response = admin_client.post(f"/usuarios/{target.id}", data={"login": "logado", "password": "NovaSenha12345"})

    assert response.status_code == 200
    assert target_client.get("/menus", follow_redirects=False).status_code == 303


def test_non_admin_forbidden_response_carries_the_exact_detail(session: Session):
    """
    O 403 para usuários sem privilégio deve trazer exatamente a mensagem de acesso restrito.
    """
    editor = create_user(session, UserData(login="editor", password="SenhaOriginal123", is_admin=False))
    client = make_user_client(session, editor)

    response = client.get("/usuarios")

    assert response.status_code == 403
    assert response.json() == {"detail": "Acesso restrito ao administrador."}


def test_user_list_items_carry_their_id_and_the_card_carries_the_entity_id(session: Session):
    client = make_admin_client(session)
    other = create_user(session, UserData(login="outro", password="SenhaOriginal123"))

    listing = client.get("/usuarios/lista")
    card = client.get(f"/usuarios/{other.id}/card")

    ids = re.findall(r'data-id="(\d+)"', listing.text)
    assert str(other.id) in ids and len(ids) == 2
    assert re.findall(r'data-entity-id="(\d+)"', card.text) == [str(other.id)]


def test_new_user_card_has_no_entity_id(session: Session):
    client = make_admin_client(session)

    assert "data-entity-id" not in client.get("/usuarios/novo/card").text


def test_users_page_marks_the_selected_user_active(session: Session):
    client = make_admin_client(session)

    response = client.get("/usuarios")

    admin = session.exec(select(User)).one()
    assert f'data-entity-id="{admin.id}"' in response.text
    assert re.search(rf'data-id="{admin.id}"\s+class="split-list-item active"', response.text)


def test_create_user_400_keeps_login_and_admin_flag_but_never_the_password(session: Session):
    client = make_admin_client(session)

    response = client.post(
        "/usuarios", data={"login": "digitado", "password": "curta", "is_admin": "true"}
    )

    assert response.status_code == 400
    assert 'value="digitado"' in response.text
    assert re.search(r'id="is_admin"[^>]*\bchecked\b', response.text, re.S)
    assert "curta" not in response.text


def test_create_user_400_without_admin_flag_keeps_it_unchecked(session: Session):
    client = make_admin_client(session)

    response = client.post("/usuarios", data={"login": "digitado", "password": "curta"})

    assert response.status_code == 400
    assert not re.search(r'id="is_admin"[^>]*\bchecked\b', response.text, re.S)


def test_update_user_400_keeps_the_submitted_login(session: Session):
    client = make_admin_client(session)
    other = create_user(session, UserData(login="outro", password="SenhaOriginal123"))

    response = client.post(f"/usuarios/{other.id}", data={"login": "novo_login", "password": "curta"})

    assert response.status_code == 400
    assert 'value="novo_login"' in response.text
    assert "Editar Usuário: outro" in response.text
    assert "curta" not in response.text
