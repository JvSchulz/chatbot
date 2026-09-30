from typing import Annotated
from fastapi import APIRouter, Request, Form, HTTPException, status, Depends
from fastapi.responses import HTMLResponse

from src.core import config
from src.core.db import SessionDep
from src.core.security import generate_csrf_token, get_session_token_from_request
from src.models.user_model import User
from src.services.user_service import (
    get_all_users,
    get_user_by_id,
    create_user,
    update_user,
    delete_user,
    require_admin_user,
    UserData,
)

router = APIRouter(
    prefix="/usuarios",
    tags=["usuario"],
    dependencies=[Depends(require_admin_user)],
)
templates = config.templates


@router.get("", response_class=HTMLResponse)
def user_split_view(
    request: Request,
    session: SessionDep,
    current_user: Annotated[User, Depends(require_admin_user)],
):
    """
    Renderiza a visualização master-detail principal de gerenciamento de usuários.

    Args:
        request: Objeto da requisição HTTP.
        session: Sessão ativa do banco de dados.
        current_user: Usuário administrador autenticado.

    Returns:
        Template HTML com lista de usuários à esquerda e primeiro usuário à direita.
    """
    all_users = get_all_users(session)
    selected_user = all_users[0] if all_users else None
    session_id = get_session_token_from_request(request)
    csrf_token = generate_csrf_token(session_id) if session_id else ""

    return templates.TemplateResponse(
        request=request,
        name="users.html",
        context={
            "users": all_users,
            "selected_user": selected_user,
            "current_user": current_user,
            "csrf_token": csrf_token,
        },
    )


@router.get("/lista", response_class=HTMLResponse)
def user_list_partial(request: Request, session: SessionDep, selected_id: int | None = None):
    """
    Retorna apenas a lista de usuários para recarregamento reativo via HTMX.

    Args:
        request: Objeto da requisição HTTP.
        session: Sessão ativa do banco de dados.
        selected_id: Identificador opcional do usuário atualmente selecionado.

    Returns:
        Fragmento HTML com os itens de usuário.
    """
    all_users = get_all_users(session)
    selected_user = get_user_by_id(session, selected_id) if selected_id else None

    return templates.TemplateResponse(
        request=request,
        name="partials/_user_list_items.html",
        context={
            "users": all_users,
            "selected_user": selected_user,
        },
    )


@router.get("/novo/card", response_class=HTMLResponse)
def user_new_card(request: Request):
    """
    Retorna o formulário em branco para cadastro de novo usuário.

    Args:
        request: Objeto da requisição HTTP.

    Returns:
        Fragmento HTML do card de criação de usuário.
    """
    return templates.TemplateResponse(
        request=request,
        name="partials/_user_card.html",
        context={"user": None},
    )


@router.get("/{user_id}/card", response_class=HTMLResponse)
def user_detail_card(request: Request, user_id: int, session: SessionDep):
    """
    Retorna o card com os dados de um usuário selecionado para edição.

    Args:
        request: Objeto da requisição HTTP.
        user_id: Identificador do usuário.
        session: Sessão ativa do banco de dados.

    Returns:
        Fragmento HTML preenchido com as credenciais do usuário.
    """
    user = get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")

    return templates.TemplateResponse(
        request=request,
        name="partials/_user_card.html",
        context={"user": user},
    )


def parse_user_form(
    login: Annotated[str, Form()],
    password: Annotated[str | None, Form()] = None,
    is_admin: Annotated[bool, Form()] = False,
) -> UserData:
    """Extrai e valida dados de formulário HTML para criação ou edição de usuários."""
    clean_password = password if password and password.strip() else None
    return UserData(login=login, password=clean_password, is_admin=is_admin)


@router.post("", response_class=HTMLResponse)
def user_create_submit(
    request: Request,
    session: SessionDep,
    user_data: Annotated[UserData, Depends(parse_user_form)],
):
    """
    Processa a criação de um novo usuário administrador.

    Args:
        request: Objeto da requisição HTTP.
        session: Sessão ativa do banco de dados.
        user_data: Dados estruturados do novo usuário.

    Returns:
        Card do usuário criado ou alerta de erro caso o login já esteja em uso.
    """
    try:
        new_user = create_user(session, user_data)
        return templates.TemplateResponse(
            request=request,
            name="partials/_user_card.html",
            context={"user": new_user},
            headers={"HX-Trigger": "userListChanged"},
        )
    except ValueError as exc:
        return templates.TemplateResponse(
            request=request,
            name="partials/_user_card.html",
            context={"user": None, "draft": user_data, "error": str(exc)},
            status_code=status.HTTP_400_BAD_REQUEST,
        )


@router.post("/{user_id}", response_class=HTMLResponse)
def user_update_submit(
    request: Request,
    user_id: int,
    session: SessionDep,
    user_data: Annotated[UserData, Depends(parse_user_form)],
):
    """
    Atualiza dados de um usuário existente.

    Args:
        request: Objeto da requisição HTTP.
        user_id: Identificador do usuário a ser atualizado.
        session: Sessão ativa do banco de dados.
        user_data: Dados estruturados do formulário.

    Returns:
        Card do usuário atualizado ou mensagem de erro 400.
    """
    try:
        updated_user = update_user(session, user_id, user_data)
        return templates.TemplateResponse(
            request=request,
            name="partials/_user_card.html",
            context={"user": updated_user},
            headers={"HX-Trigger": "userListChanged"},
        )
    except ValueError as exc:
        user = get_user_by_id(session, user_id)
        return templates.TemplateResponse(
            request=request,
            name="partials/_user_card.html",
            context={"user": user, "draft": user_data, "error": str(exc)},
            status_code=status.HTTP_400_BAD_REQUEST,
        )


@router.delete("/{user_id}", response_class=HTMLResponse)
def user_delete_submit(
    request: Request,
    user_id: int,
    session: SessionDep,
    current_user: Annotated[User, Depends(require_admin_user)],
):
    """
    Exclui um usuário do sistema.

    Args:
        request: Objeto da requisição HTTP.
        user_id: Identificador do usuário a ser removido.
        session: Sessão ativa do banco de dados.
        current_user: Usuário administrador autenticado executando a exclusão.

    Returns:
        Card em branco se removido com sucesso ou alerta 400 se autoexclusão for bloqueada.
    """
    try:
        delete_user(session, target_user_id=user_id, current_user_id=current_user.id)
        return templates.TemplateResponse(
            request=request,
            name="partials/_user_card.html",
            context={"user": None},
            headers={"HX-Trigger": "userListChanged"},
        )
    except ValueError as exc:
        user = get_user_by_id(session, user_id)
        return templates.TemplateResponse(
            request=request,
            name="partials/_user_card.html",
            context={"user": user, "error": str(exc)},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
