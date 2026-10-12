"""
Testes unitários para as operações de CRUD e regras de validação de UserService.
"""

import pytest
from datetime import datetime, timezone, timedelta
from sqlmodel import Session, select
from src.core.security import verify_password
from src.models.session_model import AdminSession
from src.models.user_model import User
from src.services.user_service import (
    get_all_users,
    get_user_by_id,
    create_user,
    update_user,
    delete_user,
    seed_first_admin,
    UserData,
    MIN_PASSWORD_LENGTH,
    PASSWORD_LENGTH_MESSAGE,
    ADMIN_REQUIRED_MESSAGE,
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
    user = create_user(session, UserData(login="novousuario", password="SenhaValida123", is_admin=True))
    assert user.id is not None
    assert user.login == "novousuario"
    assert user.is_admin is True
    assert user.password.startswith("$argon2id$")
    assert verify_password("SenhaValida123", user.password) is True


def test_create_user_raises_value_error_on_duplicate_login(session: Session):
    """
    create_user deve lançar ValueError caso o login já esteja em uso.
    """
    create_user(session, UserData(login="admin", password="SenhaValida123", is_admin=True))

    with pytest.raises(ValueError, match="já está em uso"):
        create_user(session, UserData(login="admin", password="OutraSenha123", is_admin=False))


def test_update_user_preserves_password_when_none_or_empty(session: Session):
    """
    update_user deve atualizar login e is_admin mantendo a senha intacta quando omitida.
    """
    user = create_user(session, UserData(login="orig", password="SenhaOriginal123", is_admin=False))
    original_password = user.password

    updated = update_user(session, user.id, UserData(login="novo_login", password=None, is_admin=True))  # type: ignore
    assert updated.login == "novo_login"
    assert updated.is_admin is True
    assert updated.password == original_password


def test_update_user_updates_password_when_provided(session: Session):
    """
    update_user deve alterar a senha quando uma nova for fornecida.
    """
    user = create_user(session, UserData(login="user", password="OldPassword123", is_admin=False))

    updated = update_user(session, user.id, UserData(login="user", password="NewPassword123", is_admin=False))  # type: ignore
    assert updated.password != "OldPassword123"
    assert updated.password.startswith("$argon2id$")
    assert verify_password("NewPassword123", updated.password) is True


def test_delete_user_blocks_self_deletion(session: Session):
    """
    delete_user deve lançar ValueError se o usuário tentar excluir sua própria conta em uso.
    """
    user = create_user(session, UserData(login="eu", password="SenhaValida123", is_admin=True))

    with pytest.raises(ValueError, match="não pode excluir sua própria conta"):
        delete_user(session=session, target_user_id=user.id, current_user_id=user.id)  # type: ignore


def test_delete_user_deletes_other_user(session: Session):
    """
    delete_user deve remover o usuário alvo quando diferente do usuário atual.
    """
    admin1 = create_user(session, UserData(login="admin1", password="SenhaValida123", is_admin=True))
    admin2 = create_user(session, UserData(login="admin2", password="SenhaValida123", is_admin=True))

    assert delete_user(session=session, target_user_id=admin2.id, current_user_id=admin1.id) is True  # type: ignore
    assert get_user_by_id(session, admin2.id) is None  # type: ignore


def test_seed_first_admin_creates_admin_on_empty_database(session: Session):
    """
    seed_first_admin deve criar o administrador 'admin' com a senha inicial hasheada em banco vazio.
    """
    admin = seed_first_admin(session, "SenhaInicial123")

    assert admin is not None
    assert admin.id is not None
    assert admin.login == "admin"
    assert admin.is_admin is True
    assert admin.password.startswith("$argon2id$")
    assert verify_password("SenhaInicial123", admin.password) is True
    assert len(get_all_users(session)) == 1


def test_seed_first_admin_accepts_password_of_exactly_minimum_length(session: Session):
    """
    seed_first_admin deve aceitar senha inicial com exatamente 12 caracteres.
    """
    admin = seed_first_admin(session, "a" * 12)

    assert admin is not None


@pytest.mark.parametrize("initial_password", [None, "", "a" * 11])
def test_seed_first_admin_fails_on_empty_database_without_valid_password(
    session: Session, initial_password: str | None
):
    """
    seed_first_admin deve falhar nomeando ADMIN_INITIAL_PASSWORD e não criar usuários.
    """
    with pytest.raises(RuntimeError, match="ADMIN_INITIAL_PASSWORD"):
        seed_first_admin(session, initial_password)

    assert len(get_all_users(session)) == 0


def test_seed_first_admin_fails_when_users_exist_without_administrator(session: Session):
    """
    seed_first_admin deve falhar informando que não existe administrador quando há apenas usuários comuns.
    """
    session.add(User(login="comum", password="hash", is_admin=False))
    session.commit()

    with pytest.raises(RuntimeError, match="^Nenhum administrador existe"):
        seed_first_admin(session, "SenhaInicial123")

    assert len(get_all_users(session)) == 1


def test_seed_first_admin_does_nothing_when_administrator_exists(session: Session):
    """
    seed_first_admin não deve criar nem alterar usuários quando já existe um administrador.
    """
    session.add(User(login="coord", password="hash", is_admin=True))
    session.commit()

    assert seed_first_admin(session, "SenhaInicial123") is None
    assert [user.login for user in get_all_users(session)] == ["coord"]


def test_seed_first_admin_does_not_resurrect_renamed_admin(session: Session):
    """
    seed_first_admin não deve recriar o usuário 'admin' após o administrador ser renomeado.
    """
    seed_first_admin(session, "SenhaInicial123")
    admin = get_all_users(session)[0]
    update_user(session, admin.id, UserData(login="coord", is_admin=True))  # type: ignore

    assert seed_first_admin(session, "SenhaInicial123") is None
    assert [user.login for user in get_all_users(session)] == ["coord"]


def test_password_length_message_matches_the_spec():
    """
    A constante de mensagem deve trazer o texto exigido pela especificação.
    """
    assert MIN_PASSWORD_LENGTH == 12
    assert PASSWORD_LENGTH_MESSAGE == "A senha deve ter pelo menos 12 caracteres."


@pytest.mark.parametrize("password", ["", "a" * 11])
def test_create_user_rejects_short_password(session: Session, password: str):
    """
    create_user deve rejeitar senhas vazias ou com menos de 12 caracteres e não persistir o usuário.
    """
    with pytest.raises(ValueError) as error:
        create_user(session, UserData(login="curta", password=password))

    assert str(error.value) == PASSWORD_LENGTH_MESSAGE
    assert len(get_all_users(session)) == 0


def test_create_user_rejects_missing_password(session: Session):
    """
    create_user deve rejeitar criação sem senha informada.
    """
    with pytest.raises(ValueError, match="pelo menos 12 caracteres"):
        create_user(session, UserData(login="semsenha", password=None))


def test_create_user_accepts_password_of_exactly_minimum_length(session: Session):
    """
    create_user deve aceitar senha com exatamente 12 caracteres.
    """
    user = create_user(session, UserData(login="limite", password="a" * 12))

    assert verify_password("a" * 12, user.password) is True


def test_update_user_rejects_short_non_blank_password(session: Session):
    """
    update_user deve rejeitar nova senha não vazia com menos de 12 caracteres e manter a senha atual.
    """
    user = create_user(session, UserData(login="troca", password="SenhaOriginal123"))
    original_hash = user.password

    with pytest.raises(ValueError) as error:
        update_user(session, user.id, UserData(login="troca", password="a" * 11))  # type: ignore

    assert str(error.value) == PASSWORD_LENGTH_MESSAGE
    session.refresh(user)
    assert user.password == original_hash


def test_update_user_accepts_password_of_exactly_minimum_length(session: Session):
    """
    update_user deve aceitar nova senha com exatamente 12 caracteres.
    """
    user = create_user(session, UserData(login="troca", password="SenhaOriginal123"))

    updated = update_user(session, user.id, UserData(login="troca", password="b" * 12))  # type: ignore

    assert verify_password("b" * 12, updated.password) is True


def test_create_user_hashes_argon2id_shaped_input(session: Session):
    """
    create_user deve tratar valores que parecem hash Argon2id como senha em texto puro e hasheá-los.
    """
    submitted = "$argon2id$v=19$m=65536,t=3,p=4$abc$def"

    user = create_user(session, UserData(login="forjado", password=submitted))

    assert user.password != submitted
    assert verify_password(submitted, user.password) is True


def test_update_user_hashes_argon2id_shaped_input(session: Session):
    """
    update_user deve tratar valores que parecem hash Argon2id como senha em texto puro e hasheá-los.
    """
    submitted = "$argon2id$v=19$m=65536,t=3,p=4$abc$def"
    user = create_user(session, UserData(login="forjado", password="SenhaOriginal123"))

    updated = update_user(session, user.id, UserData(login="forjado", password=submitted))  # type: ignore

    assert updated.password != submitted
    assert verify_password(submitted, updated.password) is True


def test_admin_required_message_matches_the_spec():
    """
    A constante de mensagem deve trazer o texto exigido pela especificação.
    """
    assert ADMIN_REQUIRED_MESSAGE == "Deve existir pelo menos um administrador."


def test_update_user_rejects_demoting_the_last_admin(session: Session):
    """
    update_user deve rejeitar a remoção do privilégio do único administrador.
    """
    admin = create_user(session, UserData(login="chefe", password="SenhaValida123", is_admin=True))

    with pytest.raises(ValueError) as error:
        update_user(session, admin.id, UserData(login="chefe", is_admin=False))  # type: ignore

    assert str(error.value) == ADMIN_REQUIRED_MESSAGE
    session.refresh(admin)
    assert admin.is_admin is True


def test_update_user_allows_demoting_an_admin_when_another_remains(session: Session):
    """
    update_user deve permitir rebaixar um administrador quando outro permanece.
    """
    create_user(session, UserData(login="chefe", password="SenhaValida123", is_admin=True))
    second = create_user(session, UserData(login="vice", password="SenhaValida123", is_admin=True))

    updated = update_user(session, second.id, UserData(login="vice", is_admin=False))  # type: ignore

    assert updated.is_admin is False


def test_update_user_allows_keeping_the_last_admin_as_admin(session: Session):
    """
    update_user deve permitir editar o único administrador mantendo o privilégio.
    """
    admin = create_user(session, UserData(login="chefe", password="SenhaValida123", is_admin=True))

    updated = update_user(session, admin.id, UserData(login="coord", is_admin=True))  # type: ignore

    assert updated.login == "coord"


def test_update_user_allows_non_admin_to_stay_non_admin(session: Session):
    """
    update_user não deve acionar a regra do último administrador para usuários comuns.
    """
    create_user(session, UserData(login="chefe", password="SenhaValida123", is_admin=True))
    common = create_user(session, UserData(login="comum", password="SenhaValida123", is_admin=False))

    updated = update_user(session, common.id, UserData(login="comum2", is_admin=False))  # type: ignore

    assert updated.login == "comum2"


def test_delete_user_rejects_deleting_the_last_admin(session: Session):
    """
    delete_user deve rejeitar a exclusão do único administrador, mesmo existindo outros usuários.
    """
    admin = create_user(session, UserData(login="chefe", password="SenhaValida123", is_admin=True))
    create_user(session, UserData(login="comum", password="SenhaValida123", is_admin=False))

    with pytest.raises(ValueError) as error:
        delete_user(session, admin.id)  # type: ignore

    assert str(error.value) == ADMIN_REQUIRED_MESSAGE
    assert get_user_by_id(session, admin.id) is not None  # type: ignore


def test_delete_user_allows_deleting_a_non_admin_when_one_admin_exists(session: Session):
    """
    delete_user deve permitir excluir usuários comuns quando resta um administrador.
    """
    create_user(session, UserData(login="chefe", password="SenhaValida123", is_admin=True))
    common = create_user(session, UserData(login="comum", password="SenhaValida123", is_admin=False))

    assert delete_user(session, common.id) is True  # type: ignore


def _open_session(session: Session, user: User, token: str) -> None:
    """Registra uma sessão administrativa ativa para o usuário informado."""
    session.add(
        AdminSession(
            id=token,
            user_id=user.id,  # type: ignore
            expires_at=datetime.now(timezone.utc) + timedelta(hours=12),
        )
    )
    session.commit()


def _session_ids(session: Session) -> set[str]:
    """Lista os identificadores de todas as sessões administrativas persistidas."""
    return {row.id for row in session.exec(select(AdminSession)).all()}


def test_delete_user_removes_all_sessions_of_the_deleted_user(session: Session):
    """
    delete_user deve remover todas as sessões do usuário excluído e preservar as dos demais.
    """
    admin = create_user(session, UserData(login="chefe", password="SenhaValida123", is_admin=True))
    target = create_user(session, UserData(login="alvo", password="SenhaValida123"))
    _open_session(session, admin, "sessao-admin")
    _open_session(session, target, "sessao-alvo-1")
    _open_session(session, target, "sessao-alvo-2")

    delete_user(session, target.id, admin.id)  # type: ignore

    assert _session_ids(session) == {"sessao-admin"}
    assert get_user_by_id(session, target.id) is None  # type: ignore


def test_update_user_password_change_removes_sessions_of_that_user(session: Session):
    """
    update_user deve remover as sessões do usuário cuja senha foi alterada, sem afetar as dos demais.
    """
    admin = create_user(session, UserData(login="chefe", password="SenhaValida123", is_admin=True))
    target = create_user(session, UserData(login="alvo", password="SenhaValida123"))
    _open_session(session, admin, "sessao-admin")
    _open_session(session, target, "sessao-alvo")

    update_user(session, target.id, UserData(login="alvo", password="NovaSenhaValida123"))  # type: ignore

    assert _session_ids(session) == {"sessao-admin"}


def test_update_user_without_password_keeps_sessions(session: Session):
    """
    update_user sem nova senha não deve encerrar as sessões do usuário.
    """
    target = create_user(session, UserData(login="alvo", password="SenhaValida123"))
    _open_session(session, target, "sessao-alvo")

    update_user(session, target.id, UserData(login="alvo2", password=None))  # type: ignore

    assert _session_ids(session) == {"sessao-alvo"}


def test_rejected_password_change_keeps_sessions(session: Session):
    """
    Uma troca de senha rejeitada por tamanho não deve encerrar as sessões do usuário.
    """
    target = create_user(session, UserData(login="alvo", password="SenhaValida123"))
    _open_session(session, target, "sessao-alvo")

    with pytest.raises(ValueError):
        update_user(session, target.id, UserData(login="alvo", password="curta"))  # type: ignore

    assert _session_ids(session) == {"sessao-alvo"}


def test_get_all_users_orders_by_login(session: Session):
    """
    get_all_users deve devolver os usuários ordenados por login.
    """
    session.add(User(login="ze", password="hash", is_admin=False))
    session.add(User(login="ana", password="hash", is_admin=True))
    session.commit()

    assert [user.login for user in get_all_users(session)] == ["ana", "ze"]


def test_update_user_rejects_login_already_in_use(session: Session):
    """
    update_user deve rejeitar o login de outro usuário com a mensagem de nome em uso.
    """
    create_user(session, UserData(login="ana", password="SenhaValida123"))
    create_user(session, UserData(login="bia", password="SenhaValida123"))
    caio = create_user(session, UserData(login="caio", password="SenhaValida123"))

    with pytest.raises(ValueError) as error:
        update_user(session, caio.id, UserData(login="ana"))  # type: ignore

    assert str(error.value) == "O nome de usuário 'ana' já está em uso."
    session.refresh(caio)
    assert caio.login == "caio"


def test_update_user_allows_keeping_own_login(session: Session):
    """
    update_user com o mesmo login do próprio usuário não deve acusar duplicidade.
    """
    user = create_user(session, UserData(login="ana", password="SenhaValida123"))

    updated = update_user(session, user.id, UserData(login="ana", is_admin=False))  # type: ignore

    assert updated.login == "ana"


def test_update_user_reports_missing_user_with_its_id(session: Session):
    """
    update_user deve informar o ID inexistente na mensagem de erro.
    """
    with pytest.raises(ValueError) as error:
        update_user(session, 999, UserData(login="x"))

    assert str(error.value) == "Usuário com ID 999 não encontrado."


def test_delete_user_reports_missing_user_with_its_id(session: Session):
    """
    delete_user deve informar o ID inexistente na mensagem de erro.
    """
    with pytest.raises(ValueError) as error:
        delete_user(session, 999)

    assert str(error.value) == "Usuário com ID 999 não encontrado."


def test_delete_user_self_deletion_message_is_exact(session: Session):
    """
    delete_user deve bloquear a autoexclusão com a mensagem exata definida para a regra.
    """
    user = create_user(session, UserData(login="eu", password="SenhaValida123", is_admin=True))

    with pytest.raises(ValueError) as error:
        delete_user(session, user.id, user.id)  # type: ignore

    assert str(error.value) == "Você não pode excluir sua própria conta em uso."
