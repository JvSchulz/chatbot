"""
Controlador da página de histórico de conversas do painel administrativo.
"""

from typing import Annotated
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from src.core import config
from src.core.db import SessionDep
from src.core.security import generate_csrf_token, get_session_token_from_request
from src.models.user_model import User
from src.controllers.auth_controller import get_current_admin
from src.services.webhook.chat_history_log import list_history

router = APIRouter(tags=["historico"])
templates = config.templates


def parse_page_number(raw_page: str) -> int:
    """
    Converte o parâmetro de página da URL em número; valores inválidos viram a primeira página.

    Args:
        raw_page: Texto recebido em ?page=.

    Returns:
        O número interpretado, ou 1 quando o texto não é um inteiro.
    """
    try:
        return int(raw_page)
    except ValueError:
        return 1


@router.get("/historico", response_class=HTMLResponse)
def chat_history(
    request: Request,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_admin)],
    page: str = "1",
):
    """
    Renderiza o histórico de conversas do WhatsApp, da mensagem mais recente para a mais antiga.

    Args:
        request: Objeto da requisição HTTP.
        session: Sessão ativa do banco de dados.
        current_user: Usuário autenticado.
        page: Página solicitada; valores inválidos ou fora do intervalo caem na página válida mais próxima.

    Returns:
        Template HTML com a tabela paginada ou o aviso de histórico vazio.
    """
    session_id = get_session_token_from_request(request)
    return templates.TemplateResponse(
        request=request,
        name="chat_history.html",
        context={
            "history": list_history(session, parse_page_number(page)),
            "current_user": current_user,
            "csrf_token": generate_csrf_token(session_id) if session_id else "",
        },
    )
