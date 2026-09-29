"""
Testes E2E simulando o ciclo de vida completo de gestão de usuários no painel administrativo.
"""

from fastapi.testclient import TestClient
from sqlmodel import Session
from src.models.user_model import User
from main import app


def test_e2e_user_crud_lifecycle(session: Session, auth_client: TestClient):
    """
    Fluxo E2E:
    1. Acessa '/usuarios' e verifica renderização da página.
    2. Clica em '+ Novo Usuário' e obtém card em branco.
    3. Cadastra novo usuário com sucesso.
    4. Tenta cadastrar outro usuário com o mesmo login (deve ser rejeitado com 400).
    5. Atualiza o usuário alterando privilégios de administrador.
    6. Exclui o usuário com sucesso.
    """
    client = auth_client

    # 1. Acesso à rota de usuários
    res_list = client.get("/usuarios")
    assert res_list.status_code == 200
    assert "Gerenciador de Usuários" in res_list.text

    # 2. Carrega card em branco
    res_new = client.get("/usuarios/novo/card", headers={"HX-Request": "true"})
    assert res_new.status_code == 200
    assert "Novo Usuário" in res_new.text

    # 3. Cadastra novo usuário
    payload_create = {
        "login": "coordenador",
        "password": "SenhaSegura123",
        "is_admin": "true",
    }
    res_create = client.post("/usuarios", data=payload_create, headers={"HX-Request": "true"})
    assert res_create.status_code == 200
    assert "coordenador" in res_create.text

    all_users = session.query(User).all() if hasattr(session, "query") else session.exec(User).all()
    created_user = next(u for u in all_users if u.login == "coordenador")
    assert created_user.is_admin is True

    # 4. Tenta criar usuário duplicado
    res_dup = client.post("/usuarios", data=payload_create, headers={"HX-Request": "true"})
    assert res_dup.status_code == 400
    assert "já está em uso" in res_dup.text

    # 5. Atualiza privilégios do usuário
    payload_update = {
        "login": "coordenador",
        "password": "",  # Manter senha
        "is_admin": "false",
    }
    res_update = client.post(f"/usuarios/{created_user.id}", data=payload_update, headers={"HX-Request": "true"})
    assert res_update.status_code == 200

    session.refresh(created_user)
    assert created_user.is_admin is False

    # 6. Exclusão do usuário
    res_delete = client.delete(f"/usuarios/{created_user.id}", headers={"HX-Request": "true"})
    assert res_delete.status_code == 200
