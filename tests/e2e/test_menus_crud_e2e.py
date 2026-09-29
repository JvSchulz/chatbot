"""
Testes E2E simulando navegação completa, criação e edição de menus via HTMX.
"""

from fastapi.testclient import TestClient
from sqlmodel import Session
from src.models.menu_model import Menu
from main import app


def test_e2e_menu_crud_lifecycle(session: Session, auth_client: TestClient):
    """
    Fluxo E2E:
    1. Acessa '/' e é redirecionado para '/menus'.
    2. Página renderiza lista de menus.
    3. Clica em '+ Novo Menu' para obter formulário de rascunho.
    4. Submete formulário criando um novo menu raiz (is_root="true").
    5. Cria um submenu filho (is_root="false") apontando para o primeiro menu.
    6. Tenta excluir o menu pai (deve falhar pois tem submenu).
    7. Exclui o submenu com sucesso.
    8. Exclui o menu pai com sucesso.
    """
    client = auth_client

    # 1. Acesso à raiz redireciona para /menus
    res_root = client.get("/")
    assert res_root.status_code == 200
    assert "Gerenciador de Menus" in res_root.text

    # 2. Carrega rascunho de novo menu
    res_draft = client.get("/menus/novo/card", headers={"HX-Request": "true"})
    assert res_draft.status_code == 200
    assert 'value="Novo Menu"' in res_draft.text

    # 3. Cria Menu Pai (Graduação) como Raiz
    payload_parent = {
        "name": "Graduação",
        "selection_name": "1 - Graduação",
        "message": "Informações sobre graduação",
        "is_root": "true",
    }
    res_create_parent = client.post("/menus", data=payload_parent, headers={"HX-Request": "true"})
    assert res_create_parent.status_code == 200
    assert "Graduação" in res_create_parent.text

    # Recupera o ID do menu recém-criado
    all_menus = session.query(Menu).all() if hasattr(session, "query") else session.exec(Menu).all()
    parent_menu = next(m for m in all_menus if m.name == "Graduação")

    # 4. Cria Submenu Filho (Matrícula) como Não-Raiz
    payload_child = {
        "name": "Matrícula",
        "selection_name": "1 - Matrícula",
        "message": "Orientações de matrícula",
        "parent_id": str(parent_menu.id),
        "is_root": "false",
    }
    res_create_child = client.post("/menus", data=payload_child, headers={"HX-Request": "true"})
    assert res_create_child.status_code == 200
    assert "Matrícula" in res_create_child.text

    # 5. Tentativa de excluir o menu pai deve ser bloqueada
    res_del_parent_fail = client.delete(f"/menus/{parent_menu.id}", headers={"HX-Request": "true"})
    assert res_del_parent_fail.status_code == 400
    assert "possui submenus vinculados" in res_del_parent_fail.text

    # 6. Exclui o submenu (filho) com sucesso
    all_menus = session.query(Menu).all() if hasattr(session, "query") else session.exec(Menu).all()
    child_menu = next(m for m in all_menus if m.name == "Matrícula")
    res_del_child = client.delete(f"/menus/{child_menu.id}", headers={"HX-Request": "true"})
    assert res_del_child.status_code == 200

    # 7. Exclui o menu pai agora que está sem filhos
    res_del_parent_ok = client.delete(f"/menus/{parent_menu.id}", headers={"HX-Request": "true"})
    assert res_del_parent_ok.status_code == 200
