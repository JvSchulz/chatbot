from typing import Annotated, Any
from fastapi import APIRouter, Request, Form, HTTPException, status, Depends
from fastapi.responses import HTMLResponse, Response
from sqlmodel import Session

from src.core import config
from src.core.db import SessionDep
from src.core.security import generate_csrf_token, get_session_token_from_request
from src.models.user_model import User
from src.models.menu_model import Menu
from src.controllers.auth_controller import get_current_admin
from src.services.menu_service import (
    get_all_menus,
    get_root_menu,
    get_menu_by_id,
    get_valid_parent_menus,
    is_root_toggle_allowed,
    build_menu_split_view_context,
    create_menu,
    update_menu,
    delete_menu,
    MenuData,
)

router = APIRouter(
    prefix="/menus",
    tags=["menu"],
    dependencies=[Depends(get_current_admin)],
)
templates = config.templates


@router.get("", response_class=HTMLResponse)
def menu_split_view(
    request: Request,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_admin)],
):
    """
    Renderiza a visualização master-detail principal de gerenciamento de menus.

    Args:
        request: Objeto da requisição HTTP.
        session: Sessão ativa do banco de dados.
        current_user: Usuário atualmente autenticado.

    Returns:
        Template HTML com lista à esquerda e menu raiz carregado à direita.
    """
    context = build_menu_split_view_context(session)
    context["current_user"] = current_user
    session_id = get_session_token_from_request(request)
    context["csrf_token"] = generate_csrf_token(session_id) if session_id else ""

    return templates.TemplateResponse(
        request=request,
        name="menus.html",
        context=context,
    )


@router.get("/lista", response_class=HTMLResponse)
def menu_list_partial(request: Request, session: SessionDep, selected_id: int | None = None):
    """
    Retorna apenas a lista de menus para recarregamento reativo via HTMX.

    Args:
        request: Objeto da requisição HTTP.
        session: Sessão ativa do banco de dados.
        selected_id: Identificador opcional do menu atualmente ativo.

    Returns:
        Fragmento HTML com os itens de menu.
    """
    all_menus = get_all_menus(session)
    selected_menu = get_menu_by_id(session, selected_id) if selected_id else None

    return templates.TemplateResponse(
        request=request,
        name="partials/_menu_list_items.html",
        context={
            "menus": all_menus,
            "selected_menu": selected_menu,
        },
    )


def _card_context(session: Session, menu: Menu | None, is_current_root: bool | None = None) -> dict[str, Any]:
    """
    Monta o contexto do card de menu: raiz atual, flags do checkbox de raiz e pais válidos.

    Args:
        session: Sessão ativa do banco de dados.
        menu: Menu exibido no card, ou None para o formulário de um novo menu.
        is_current_root: Se o card representa a raiz (ou o rascunho da primeira raiz); None deriva
            do menu: um menu existente é a raiz quando não tem pai, e o rascunho é a primeira raiz
            enquanto não existir nenhuma.

    Returns:
        Dicionário com as seis chaves que o template do card exige.
    """
    root_menu = get_root_menu(session)
    has_root = root_menu is not None
    if is_current_root is None:
        is_current_root = menu.parent_id is None if menu else not has_root
    return {
        "menu": menu,
        "root_menu": root_menu,
        "has_root": has_root,
        "is_current_root": is_current_root,
        "can_toggle_root": is_root_toggle_allowed(has_root, is_current_root),
        "valid_parents": get_valid_parent_menus(session, exclude_id=menu.id if menu else None),
    }


def _card_response(request: Request, context: dict[str, Any], status_code: int = status.HTTP_200_OK) -> Response:
    """
    Renderiza o card de menu com o contexto informado.

    Args:
        request: Objeto da requisição HTTP.
        context: Contexto montado por _card_context, acrescido das chaves opcionais 'error' e
            'draft' (valores enviados no formulário, exibidos de volta quando a validação falha).
        status_code: Status HTTP da resposta.

    Returns:
        Resposta HTML com o fragmento do card.
    """
    return templates.TemplateResponse(
        request=request,
        name="partials/_menu_card.html",
        context=context,
        status_code=status_code,
    )


def _reload_menu_list(response: Response) -> Response:
    """Pede ao navegador que recarregue a lista de menus após a resposta."""
    response.headers["HX-Trigger"] = "menuListChanged"
    return response


@router.get("/novo/card", response_class=HTMLResponse)
def menu_new_card(request: Request, session: SessionDep):
    """
    Retorna o formulário em branco para criação de novo menu.

    Args:
        request: Objeto da requisição HTTP.
        session: Sessão ativa do banco de dados.

    Returns:
        Fragmento HTML do card de criação com nome pré-definido.
    """
    return _card_response(request, _card_context(session, None))


@router.get("/{menu_id}/card", response_class=HTMLResponse)
def menu_detail_card(request: Request, menu_id: int, session: SessionDep):
    """
    Retorna o card de visualização e edição de um menu específico.

    Args:
        request: Objeto da requisição HTTP.
        menu_id: Identificador do menu selecionado.
        session: Sessão ativa do banco de dados.

    Returns:
        Fragmento HTML com os dados do menu preenchidos.
    """
    menu = get_menu_by_id(session, menu_id)
    if not menu:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu não encontrado.")

    return _card_response(request, _card_context(session, menu))


def parse_menu_form(
    name: Annotated[str, Form()],
    selection_name: Annotated[str, Form()],
    message: Annotated[str, Form()],
    parent_id: Annotated[str | None, Form()] = None,
    is_root: Annotated[bool, Form()] = False,
) -> MenuData:
    """Extrai e valida dados de formulário HTML para criação ou edição de nós de menu."""
    parsed_parent_id = None if is_root else (int(parent_id) if parent_id and parent_id.isdigit() else None)
    return MenuData(
        name=name,
        selection_name=selection_name,
        message=message,
        parent_id=parsed_parent_id,
        is_root=is_root,
    )


@router.post("", response_class=HTMLResponse)
def menu_create_submit(
    request: Request,
    session: SessionDep,
    menu_data: Annotated[MenuData, Depends(parse_menu_form)],
):
    """
    Processa a criação de um novo menu com validação de raiz única.

    Args:
        request: Objeto da requisição HTTP.
        session: Sessão ativa do banco de dados.
        menu_data: Dados estruturados do novo menu.

    Returns:
        Card do menu recém-criado ou erro 422 em caso de violação de regras.
    """
    try:
        new_menu = create_menu(session, menu_data)
    except ValueError as exc:
        is_draft_root = menu_data.is_root and get_root_menu(session) is None
        context = _card_context(session, None, is_current_root=is_draft_root)
        return _card_response(
            request, {**context, "draft": menu_data, "error": str(exc)}, status.HTTP_422_UNPROCESSABLE_ENTITY
        )
    return _reload_menu_list(_card_response(request, _card_context(session, new_menu)))


@router.post("/{menu_id}", response_class=HTMLResponse)
def menu_update_submit(
    request: Request,
    menu_id: int,
    session: SessionDep,
    menu_data: Annotated[MenuData, Depends(parse_menu_form)],
):
    """
    Atualiza um menu existente com validação contra ciclos e raiz única.

    Args:
        request: Objeto da requisição HTTP.
        menu_id: Identificador do menu a ser atualizado.
        session: Sessão ativa do banco de dados.
        menu_data: Dados estruturados do formulário.

    Returns:
        Card atualizado ou alerta de erro 422 em caso de ciclo ou violação de raiz.
    """
    try:
        updated_menu = update_menu(session, menu_id, menu_data)
    except ValueError as exc:
        context = _card_context(session, get_menu_by_id(session, menu_id))
        return _card_response(
            request, {**context, "draft": menu_data, "error": str(exc)}, status.HTTP_422_UNPROCESSABLE_ENTITY
        )
    return _reload_menu_list(_card_response(request, _card_context(session, updated_menu)))


@router.delete("/{menu_id}", response_class=HTMLResponse)
def menu_delete_submit(
    request: Request,
    menu_id: int,
    session: SessionDep,
):
    """
    Remove um menu do sistema ou bloqueia caso possua submenus dependentes.

    Args:
        request: Objeto da requisição HTTP.
        menu_id: Identificador do menu a ser excluído.
        session: Sessão ativa do banco de dados.

    Returns:
        Card em branco se removido com sucesso ou alerta 400 se bloqueado por submenus.
    """
    try:
        delete_menu(session, menu_id)
    except ValueError as exc:
        context = _card_context(session, get_menu_by_id(session, menu_id))
        return _card_response(request, {**context, "error": str(exc)}, status.HTTP_400_BAD_REQUEST)
    return _reload_menu_list(menu_new_card(request, session))
