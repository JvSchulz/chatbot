from typing import Sequence
from dataclasses import dataclass
from fastapi import Request, HTTPException, status
from sqlmodel import Session, col, delete, select
from src.core.db import SessionDep
from src.core.security import hash_password
from src.models.session_model import AdminSession
from src.models.user_model import User


MIN_PASSWORD_LENGTH = 12
ADMIN_REQUIRED_MESSAGE = "Deve existir pelo menos um administrador."
PASSWORD_LENGTH_MESSAGE = f"A senha deve ter pelo menos {MIN_PASSWORD_LENGTH} caracteres."


@dataclass
class UserData:
    """Objeto de parâmetros para criação e atualização de usuários administradores."""
    login: str
    password: str | None = None
    is_admin: bool = False


def seed_first_admin(session: Session, initial_password: str | None) -> User | None:
    """
    Cria o primeiro administrador 'admin' somente quando não existe nenhum usuário cadastrado.

    Nunca cria nem altera usuários quando a tabela já possui registros. Falha na inicialização
    quando a tabela está vazia sem senha inicial válida, ou quando há usuários sem administrador.

    Args:
        session: Sessão ativa do banco de dados.
        initial_password: Senha inicial vinda de ADMIN_INITIAL_PASSWORD, se configurada.

    Returns:
        O administrador recém-criado, ou None quando nada foi criado.

    Raises:
        RuntimeError: Se o banco está vazio sem senha inicial válida, ou se existem usuários
            e nenhum deles é administrador.
    """
    if session.exec(select(User)).first() is None:
        if initial_password is None or len(initial_password) < MIN_PASSWORD_LENGTH:
            raise RuntimeError(
                f"Banco sem usuários: defina ADMIN_INITIAL_PASSWORD com pelo menos "
                f"{MIN_PASSWORD_LENGTH} caracteres para criar o primeiro administrador."
            )
        return create_user(session, UserData(login="admin", password=initial_password, is_admin=True))

    if session.exec(select(User).where(col(User.is_admin).is_(True))).first() is None:
        raise RuntimeError("Nenhum administrador existe: há usuários cadastrados, mas nenhum com is_admin.")
    return None


def _hash_new_password(password: str | None) -> str:
    """
    Valida o tamanho mínimo e gera o hash Argon2id de uma senha em texto puro.

    Qualquer valor informado é tratado como texto puro, inclusive os que começam com '$argon2id$'.

    Args:
        password: Senha em texto puro informada pelo administrador.

    Returns:
        Hash Argon2id da senha.

    Raises:
        ValueError: Se a senha estiver ausente ou tiver menos de MIN_PASSWORD_LENGTH caracteres.
    """
    if password is None or len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(PASSWORD_LENGTH_MESSAGE)
    return hash_password(password)


def _ensure_admin_remains(session: Session, leaving_user: User) -> None:
    """
    Garante que ao menos um administrador continue existindo sem o usuário informado.

    Usuários sem privilégio de administrador nunca violam a regra.

    Args:
        session: Sessão ativa do banco de dados.
        leaving_user: Usuário que será excluído ou perderá o privilégio de administrador.

    Raises:
        ValueError: Se o usuário é o único administrador cadastrado.
    """
    if not leaving_user.is_admin:
        return
    other_admin = session.exec(
        select(User.id).where(col(User.is_admin).is_(True), User.id != leaving_user.id)
    ).first()
    if other_admin is None:
        raise ValueError(ADMIN_REQUIRED_MESSAGE)


def _revoke_sessions(session: Session, user_id: int) -> None:
    """
    Remove todas as sessões administrativas de um usuário, encerrando seus acessos ativos.

    A remoção entra na transação corrente e é confirmada junto com a alteração que a motivou.

    Args:
        session: Sessão ativa do banco de dados.
        user_id: Identificador do usuário cujas sessões serão removidas.
    """
    session.exec(delete(AdminSession).where(col(AdminSession.user_id) == user_id))  # type: ignore


def require_admin_user(
    request: Request,
    session: SessionDep,
) -> User:
    """
    Garante que o usuário requisitante possua privilégios de administrador.

    Args:
        request: Objeto da requisição HTTP.
        session: Sessão ativa do banco de dados.

    Returns:
        Instância do usuário administrador confirmado.

    Raises:
        HTTPException: Status 403 caso o usuário não possua privilégios de admin.
    """
    from src.controllers.auth_controller import get_current_admin
    current_user = get_current_admin(request, session)
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito ao administrador.",
        )
    return current_user



def get_all_users(session: Session) -> Sequence[User]:
    """
    Retorna todos os usuários cadastrados ordenados por login.

    Args:
        session: Sessão ativa do banco de dados.

    Returns:
        Sequência de todos os usuários cadastrados.
    """
    return session.exec(select(User).order_by(User.login)).all()  # type: ignore


def get_user_by_id(session: Session, user_id: int) -> User | None:
    """
    Busca um usuário pelo identificador primário.

    Args:
        session: Sessão ativa do banco de dados.
        user_id: Identificador numérico do usuário.

    Returns:
        Instância de User encontrada ou None caso inexistente.
    """
    return session.get(User, user_id)


def create_user(session: Session, data: UserData) -> User:
    """
    Cria e persiste um novo usuário no banco de dados.

    Args:
        session: Sessão ativa do banco de dados.
        data: Dados estruturados do novo usuário.

    Returns:
        Instância de User persistida com ID gerado.

    Raises:
        ValueError: Caso o login já esteja cadastrado no sistema.
    """
    existing = session.exec(select(User).where(User.login == data.login)).first()
    if existing:
        raise ValueError(f"O nome de usuário '{data.login}' já está em uso.")

    new_user = User(
        login=data.login,
        password=_hash_new_password(data.password),
        is_admin=data.is_admin,
    )
    session.add(new_user)
    session.commit()
    session.refresh(new_user)
    return new_user


def update_user(session: Session, user_id: int, data: UserData) -> User:
    """
    Atualiza credenciais e permissões de um usuário existente.

    Args:
        session: Sessão ativa do banco de dados.
        user_id: Identificador do usuário a ser atualizado.
        data: Novos dados para o usuário.

    Returns:
        Instância de User atualizada.

    Raises:
        ValueError: Se o usuário não existir, o novo login já estiver em uso, a nova senha for
            curta demais ou a alteração removesse o último administrador.
    """
    user = session.get(User, user_id)
    if not user:
        raise ValueError(f"Usuário com ID {user_id} não encontrado.")

    if data.login != user.login:
        existing = session.exec(select(User).where(User.login == data.login)).first()
        if existing and existing.id != user_id:
            raise ValueError(f"O nome de usuário '{data.login}' já está em uso.")

    if user.is_admin and not data.is_admin:
        _ensure_admin_remains(session, user)

    new_password_hash = _hash_new_password(data.password) if data.password else None

    user.login = data.login
    if new_password_hash:
        user.password = new_password_hash
        _revoke_sessions(session, user_id)

    user.is_admin = data.is_admin

    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def delete_user(
    session: Session,
    target_user_id: int,
    current_user_id: int | None = None,
) -> bool:
    """
    Exclui um usuário do sistema com proteção contra autoexclusão.

    Args:
        session: Sessão ativa do banco de dados.
        target_user_id: Identificador do usuário a ser removido.
        current_user_id: Identificador do administrador que executa a operação.

    Returns:
        True indicando sucesso da remoção.

    Raises:
        ValueError: Caso o usuário tente excluir a própria conta, o alvo não exista ou seja o
            último administrador.
    """
    if current_user_id is not None and target_user_id == current_user_id:
        raise ValueError("Você não pode excluir sua própria conta em uso.")

    user = session.get(User, target_user_id)
    if not user:
        raise ValueError(f"Usuário com ID {target_user_id} não encontrado.")

    _ensure_admin_remains(session, user)

    _revoke_sessions(session, target_user_id)
    session.delete(user)
    session.commit()
    return True
