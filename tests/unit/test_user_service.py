"""
Testes unitários para as operações de CRUD e regras de validação de UserService.
"""

import pytest
from sqlmodel import Session
from src.models.user_model import User
from src.services.user_service import (
    get_all_users,
    get_user_by_id,
    create_user,
    update_user,
    delete_user,
    seed_default_admin,
)


def test_get_all_users_returns_list(session: Session):
    """
    get_all_users deve retornar todos os usuários cadastrados ordenados por login.
    """
    u1 = User(login="ze", password="hash1", is_admin=False)
    u2 = User(login="ana", password="hash2", is_admin=True)
    session.add(u1)
    session.add(u2)
    session.commit()

    users = get_all_users(session)
    assert len(users) == 2
    assert users[0].login == "ana"
    assert users[1].login == "ze"


def test_get_user_by_id_returns_correct_entity(session: Session):
    """
    get_user_by_id deve recuperar usuário por ID ou retornar None.
    """
    u = User(login="admin", password="hash", is_admin=True)
    session.add(u)
    session.commit()
    session.refresh(u)

    found = get_user_by_id(session, u.id)  # type: ignore
    assert found is not None
    assert found.login == "admin"
    assert get_user_by_id(session, 99999) is None


def test_create_user_persists_new_user(session: Session):
    """
    create_user deve criar um novo usuário e persistir no banco de dados.
    """
    user = create_user(
        session=session,
        login="novousuario",
        password="SenhaValida123",
        is_admin=True,
    )
    assert user.id is not None
    assert user.login == "novousuario"
    assert user.is_admin is True


def test_create_user_raises_value_error_on_duplicate_login(session: Session):
    """
    create_user deve lançar ValueError caso o login já esteja em uso.
    """
    create_user(session=session, login="admin", password="Senha123", is_admin=True)

    with pytest.raises(ValueError, match="já está em uso"):
        create_user(session=session, login="admin", password="OutraSenha123", is_admin=False)


def test_update_user_preserves_password_when_none_or_empty(session: Session):
    """
    update_user deve atualizar login e is_admin mantendo a senha intacta quando omitida.
    """
    user = create_user(session=session, login="orig", password="SenhaOriginal123", is_admin=False)
    original_password = user.password

    updated = update_user(
        session=session,
        user_id=user.id,  # type: ignore
        login="novo_login",
        password=None,
        is_admin=True,
    )
    assert updated.login == "novo_login"
    assert updated.is_admin is True
    assert updated.password == original_password


def test_update_user_updates_password_when_provided(session: Session):
    """
    update_user deve alterar a senha quando uma nova for fornecida.
    """
    user = create_user(session=session, login="user", password="OldPassword123", is_admin=False)

    updated = update_user(
        session=session,
        user_id=user.id,  # type: ignore
        login="user",
        password="NewPassword123",
        is_admin=False,
    )
    assert updated.password != "OldPassword123"


def test_delete_user_blocks_self_deletion(session: Session):
    """
    delete_user deve lançar ValueError se o usuário tentar excluir sua própria conta em uso.
    """
    user = create_user(session=session, login="eu", password="Senha123", is_admin=True)

    with pytest.raises(ValueError, match="não pode excluir sua própria conta"):
        delete_user(session=session, target_user_id=user.id, current_user_id=user.id)  # type: ignore


def test_delete_user_deletes_other_user(session: Session):
    """
    delete_user deve remover o usuário alvo quando diferente do usuário atual.
    """
    admin1 = create_user(session=session, login="admin1", password="Senha123", is_admin=True)
    admin2 = create_user(session=session, login="admin2", password="Senha123", is_admin=True)

    assert delete_user(session=session, target_user_id=admin2.id, current_user_id=admin1.id) is True  # type: ignore
    assert get_user_by_id(session, admin2.id) is None  # type: ignore


def test_seed_default_admin_creates_new_admin(session: Session):
    """
    seed_default_admin deve criar o usuário 'admin' com senha 'admin' e is_admin=True caso inexista.
    """
    admin = seed_default_admin(session)
    assert admin.id is not None
    assert admin.login == "admin"
    assert admin.password == "admin"
    assert admin.is_admin is True


def test_seed_default_admin_idempotent_when_exists(session: Session):
    """
    seed_default_admin deve retornar o usuário 'admin' existente sem duplicar ou alterar.
    """
    first_admin = seed_default_admin(session)
    second_admin = seed_default_admin(session)
    assert first_admin.id == second_admin.id
    assert len(get_all_users(session)) == 1

