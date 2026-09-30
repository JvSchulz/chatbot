"""
Testes unitários para utilitários de segurança e criptografia.
"""

from src.core.security import (
    hash_password,
    verify_password,
    generate_session_token,
    generate_csrf_token,
    verify_csrf_token,
    DUMMY_HASH,
    SESSION_COOKIE_NAME,
    SECURE_SESSION_COOKIE_NAME,
    session_cookie_name,
)


def test_hash_password_generates_argon2_hash():
    """
    Verifica se hash_password gera um hash Argon2id válido.
    """
    password = "SuperSecretPassword123"
    hashed = hash_password(password)

    assert hashed is not None
    assert hashed != password
    assert "$argon2id$" in hashed


def test_verify_password_matches_correct_password():
    """
    Verifica se a validação retorna True para senha correta.
    """
    password = "CorrectPassword456"
    hashed = hash_password(password)

    assert verify_password(password, hashed) is True


def test_verify_password_rejects_incorrect_password():
    """
    Verifica se a validação retorna False para senha incorreta.
    """
    password = "CorrectPassword456"
    hashed = hash_password(password)

    assert verify_password("WrongPassword789", hashed) is False


def test_verify_password_malformed_hash_returns_false():
    """
    Verifica se hash malformado captura exceção e retorna False com segurança.
    """
    assert verify_password("qualquer_senha", "hash_invalido_malformado") is False


def test_verify_password_against_dummy_hash_returns_false():
    """
    Garante que a verificação contra DUMMY_HASH sempre retorne False.
    """
    assert DUMMY_HASH is not None
    assert "$argon2id$" in DUMMY_HASH
    assert verify_password("any_arbitrary_attempt", DUMMY_HASH) is False


def test_generate_session_token_produces_unique_cryptographic_strings():
    """
    Garante que generate_session_token gera tokens únicos e com entropia adequada.
    """
    token1 = generate_session_token()
    token2 = generate_session_token()

    assert isinstance(token1, str)
    assert len(token1) >= 42
    assert token1 != token2


def test_csrf_token_generation_and_validation():
    """
    Garante integridade e validação de tokens CSRF.
    """
    session_id_1 = "test-session-id-123"
    session_id_2 = "test-session-id-456"
    token1 = generate_csrf_token(session_id_1)
    token2 = generate_csrf_token(session_id_2)

    assert isinstance(token1, str)
    assert len(token1) == 64
    assert token1 != token2
    assert verify_csrf_token(token1, session_id_1) is True
    assert verify_csrf_token(token1, session_id_2) is False
    assert verify_csrf_token("invalid_token", session_id_1) is False
    assert verify_csrf_token("", session_id_1) is False
    assert verify_csrf_token(token1, "") is False

    # Valida que sessão vazia com hash esperado ainda é rejeitada
    empty_session_token = generate_csrf_token("")
    assert verify_csrf_token(empty_session_token, "") is False


def test_session_cookie_name_is_host_prefixed_over_https():
    """
    Sobre HTTPS o cookie de sessão deve usar o prefixo __Host-.
    """
    assert SECURE_SESSION_COOKIE_NAME == "__Host-session"
    assert session_cookie_name(True) == "__Host-session"


def test_session_cookie_name_is_plain_over_http():
    """
    Sobre HTTP simples (desenvolvimento local) o cookie de sessão deve se chamar apenas session.
    """
    assert SESSION_COOKIE_NAME == "session"
    assert session_cookie_name(False) == "session"


def test_generate_session_token_has_256_bits_of_entropy():
    """
    O token de sessão deve ter 32 bytes aleatórios, o que resulta em 43 caracteres URL-safe.
    """
    assert len(generate_session_token()) == 43
