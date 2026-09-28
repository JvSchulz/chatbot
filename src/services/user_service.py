from typing import Sequence, Annotated
from dataclasses import dataclass
from fastapi import Request, Depends, HTTPException, status
from sqlmodel import Session, select
from src.core.db import engine, SessionDep
from src.models.user_model import User


@dataclass
class UserData:
    """Objeto de parâmetros para criação e atualização de usuários administradores."""
    login: str
    password: str | None = None
    is_admin: bool = False


def seed_default_admin(session: Session) -> User:
    """
    Garante que o usuário administrador padrão 'admin' exista no banco de dados.

    Se não existir, cria o usuário com login 'admin', senha 'admin' e is_admin=True.

    Args:
        session: Sessão ativa do banco de dados.

    Returns:
        Instância do usuário administrador (existente ou recém-criado).
    """
    admin_user = session.exec(select(User).where(User.login == "admin")).first()
    if not admin_user:
        admin_user = User(
            login="admin",
            password="admin",
            is_admin=True,
        )
        session.add(admin_user)
        session.commit()
        session.refresh(admin_user)
    return admin_user


def get_current_user(
    request: Request,
    session: SessionDep,
) -> User:
    """
    Identifica o usuário atual a partir da requisição HTTP.

    Verifica headers, cookies ou parâmetros de consulta. Caso não haja usuário
    especificado, utiliza o usuário administrador padrão do sistema.

    Args:
        request: Objeto da requisição HTTP.
        session: Sessão ativa do banco de dados.

    Returns:
        Instância de User identificada ou administrador padrão.
    """
    user_id_str = (
        request.headers.get("X-User-Id")
        or request.cookies.get("user_id")
        or request.query_params.get("user_id")
    )
    if user_id_str and user_id_str.isdigit():
        user = session.get(User, int(user_id_str))
        if user:
            return user

    return seed_default_admin(session)


def require_admin_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """
    Garante que o usuário requisitante possua privilégios de administrador.

    Args:
        current_user: Usuário autenticado resolvido pela injeção de dependência.

    Returns:
        Instância do usuário administrador confirmado.

    Raises:
        HTTPException: Status 403 caso o usuário não possua privilégios de admin.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito ao administrador.",
        )
    return current_user



def get_all_users(session: Session | None = None) -> Sequence[User]:
    """
    Retorna todos os usuários cadastrados ordenados por login.

    Args:
        session: Sessão do banco de dados (opcional).

    Returns:
        Sequência de todos os usuários cadastrados.
    """
    if session is not None:
        return session.exec(select(User).order_by(User.login)).all()  # type: ignore
    with Session(engine) as s:
        return s.exec(select(User).order_by(User.login)).all()  # type: ignore


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


def create_user(
    session: Session,
    data: UserData | None = None,
    **kwargs,
) -> User:
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
    user_data = data or UserData(
        login=kwargs.get("login", ""),
        password=kwargs.get("password", ""),
        is_admin=kwargs.get("is_admin", False),
    )

    existing = session.exec(select(User).where(User.login == user_data.login)).first()
    if existing:
        raise ValueError(f"O nome de usuário '{user_data.login}' já está em uso.")

    new_user = User(
        login=user_data.login,
        password=user_data.password or "",
        is_admin=user_data.is_admin,
    )
    session.add(new_user)
    session.commit()
    session.refresh(new_user)
    return new_user


def update_user(
    session: Session,
    user_id: int,
    data: UserData | None = None,
    **kwargs,
) -> User:
    """
    Atualiza credenciais e permissões de um usuário existente.

    Args:
        session: Sessão ativa do banco de dados.
        user_id: Identificador do usuário a ser atualizado.
        data: Novos dados para o usuário.

    Returns:
        Instância de User atualizada.

    Raises:
        ValueError: Se o usuário não existir ou o novo login já estiver em uso.
    """
    user = session.get(User, user_id)
    if not user:
        raise ValueError(f"Usuário com ID {user_id} não encontrado.")

    user_data = data or UserData(
        login=kwargs.get("login", user.login),
        password=kwargs.get("password"),
        is_admin=kwargs.get("is_admin", user.is_admin),
    )

    if user_data.login != user.login:
        existing = session.exec(select(User).where(User.login == user_data.login)).first()
        if existing and existing.id != user_id:
            raise ValueError(f"O nome de usuário '{user_data.login}' já está em uso.")
        user.login = user_data.login

    if user_data.password:
        user.password = user_data.password

    user.is_admin = user_data.is_admin

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
        ValueError: Caso o usuário tente excluir a própria conta ou o alvo não exista.
    """
    if current_user_id is not None and target_user_id == current_user_id:
        raise ValueError("Você não pode excluir sua própria conta em uso.")

    user = session.get(User, target_user_id)
    if not user:
        raise ValueError(f"Usuário com ID {target_user_id} não encontrado.")

    session.delete(user)
    session.commit()
    return True
