"""
Middlewares de segurança para injeção de cabeçalhos HTTP e proteção contra CSRF.
"""

from typing import Callable, Awaitable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from src.core.security import verify_csrf_token, get_session_token_from_request


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Injeta cabeçalhos de segurança obrigatórios para proteção contra ataques comuns.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """
        Processa a requisição e aplica cabeçalhos de mitigação de vulnerabilidades web.

        Args:
            request: Objeto da requisição HTTP recebida.
            call_next: Função para chamar o próximo manipulador na cadeia ASGI.

        Returns:
            Resposta HTTP com os cabeçalhos de segurança definidos.
        """
        response = await call_next(request)

        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none';"
        )

        return response


class CSRFProtectionMiddleware(BaseHTTPMiddleware):
    """
    Valida a presença e integridade do token CSRF em requisições de alteração de estado.
    """

    SAFE_METHODS = ("GET", "HEAD", "OPTIONS")

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """
        Verifica o token CSRF contra a sessão ativa, ignorando métodos seguros e rotas públicas.

        Args:
            request: Requisição HTTP interceptada.
            call_next: Próximo manipulador na cadeia de middlewares.

        Returns:
            Resposta da requisição ou 403 Forbidden caso o token CSRF seja inválido.
        """
        if request.method in self.SAFE_METHODS:
            return await call_next(request)

        if self._is_path_exempt(request.url.path):
            return await call_next(request)

        session_id = get_session_token_from_request(request)
        if not session_id:
            return JSONResponse(
                status_code=403,
                content={"detail": "Token CSRF ausente ou inválido: sessão ausente."},
            )

        csrf_token = request.headers.get("X-CSRF-Token")
        if not csrf_token or not verify_csrf_token(csrf_token, session_id):
            return JSONResponse(
                status_code=403,
                content={"detail": "Token CSRF ausente ou inválido."},
            )

        return await call_next(request)

    def _is_path_exempt(self, path: str) -> bool:
        """
        Avalia se a rota requisitada está na lista de isenção de validação CSRF.

        Args:
            path: Caminho da URL requisitada.

        Returns:
            True se a rota for isenta, False caso contrário.
        """
        return path.startswith("/webhook") or path in ("/login", "/logout")
