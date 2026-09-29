"""
Testes de integração para as rotas administrativas de UsersController.
"""

from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlmodel import Session
from src.models.user_model import User
from src.models.session_model import AdminSession
from src.services.user_service import seed_default_admin
from src.core.security import SESSION_COOKIE_NAME, generate_session_token, generate_csrf_token
from main import app


def make_user_client(session: Session, user: User) -> TestClient:
    """
    Cria cliente de teste autenticado com a sessão do usuário especificado e token CSRF.
    """
    token = generate_session_token()
    csrf = generate_csrf_token(token)

    admin_session = AdminSession(
        id=token,
        user_id=user.id,  # type: ignore
        expires_at=datetime.now(timezone.utc) + timedelta(hours=12),
    )
    session.add(admin_session)
    session.commit()

    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE_NAME, token)
    client.headers.update({"X-CSRF-Token": csrf})
    return client


def make_admin_client(session: Session) -> TestClient:
    """
    Cria cliente de teste autenticado como o administrador padrão.
    """
    admin = seed_default_admin(session)
    return make_user_client(session, admin)


def test_get_users_renders_split_view_page(session: Session):
    """
    GET /usuarios deve retornar status 200 e carregar a listagem e card de usuários.
    """
    u1 = User(login="superadmin", password="hash_password", is_admin=True)
    session.add(u1)
    session.commit()

    client = make_admin_client(session)
    response = client.get("/usuarios")

    assert response.status_code == 200
    assert "superadmin" in response.text
    assert 'id="user-detail-pane"' in response.text


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
    res_ok = client.post(f"/usuarios/{u.id}", data={"login": "operador_chefe", "password": "new", "is_admin": "true"})
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
