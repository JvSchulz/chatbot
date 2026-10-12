"""
Utilitários de segurança, criptografia Argon2id, tokens de sessão e proteção CSRF.
"""

import hmac
import hashlib
import secrets
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from src.core.config import settings

SECRET_KEY = settings.secret_key.get_secret_value()
SESSION_COOKIE_NAME = "session"
SECURE_SESSION_COOKIE_NAME = "__Host-session"
DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$cRbAtTw3BHnG+HktOVbxHg$OUm6fvlyOXHRn/yrYrlqFJmYZJqQk9FisS7R/7WTILc"

_password_hasher = PasswordHash((Argon2Hasher(),))


def session_cookie_name(is_https: bool) -> str:
    """
    Escolhe o nome do cookie de sessão conforme o esquema da conexão.

    Args:
        is_https: True quando a requisição chegou por HTTPS, direta ou via proxy.

    Returns:
        __Host-session sobre HTTPS e session sobre HTTP simples, onde o navegador recusaria Secure.
    """
    return SECURE_SESSION_COOKIE_NAME if is_https else SESSION_COOKIE_NAME


def get_session_token_from_request(request) -> str | None:
    """Extrai o token de sessão da requisição, priorizando o cookie __Host-session sobre o session."""
    return request.cookies.get(SECURE_SESSION_COOKIE_NAME) or request.cookies.get(SESSION_COOKIE_NAME)


def hash_password(password: str) -> str:
    """
    Gera hash seguro Argon2id para uma senha informada.

    Args:
        password: Senha em texto puro a ser criptografada.

    Returns:
        String contendo o hash formatado em Argon2id.
    """
    return _password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Valida senha contra hash Argon2id de forma segura e com mitigação de temporização.

    Args:
        plain_password: Senha informada pelo usuário.
        hashed_password: Hash armazenado no banco de dados.

    Returns:
        True se a senha corresponder ao hash, False caso contrário.
    """
    try:
        return _password_hasher.verify(plain_password, hashed_password)
    except Exception:
        return False


def generate_session_token() -> str:
    """
    Gera token criptográfico aleatório para identificação de sessão administrativa.

    Returns:
        String alfanumérica gerada de forma segura com alta entropia.
    """
    return secrets.token_urlsafe(32)


def generate_csrf_token(session_id: str) -> str:
    """
    Gera token CSRF baseado em HMAC vinculado ao identificador de sessão.

    Args:
        session_id: Identificador da sessão autenticada.

    Returns:
        Hexadecimal do HMAC-SHA256 representando o token CSRF.
    """
    return hmac.new(
        SECRET_KEY.encode("utf-8"),
        session_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_csrf_token(csrf_token: str, session_id: str) -> bool:
    """
    Valida token CSRF em tempo constante comparando com o token derivado da sessão.

    Args:
        csrf_token: Token recebido no cabeçalho da requisição.
        session_id: Identificador da sessão autenticada.

    Returns:
        True se o token corresponder exatamente, False caso contrário.
    """
    if not csrf_token or not session_id:
        return False
    expected = generate_csrf_token(session_id)
    return hmac.compare_digest(expected, csrf_token)
