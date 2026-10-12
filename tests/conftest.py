import os

os.environ["SECRET_KEY"] = "test-secret-key-for-csrf-and-sessions"
os.environ["WA_VERIFY_TOKEN"] = "test-verify-token"
os.environ["APP_SECRET"] = "test-app-secret"
os.environ["WA_TOKEN"] = "test-wa-token"
os.environ["WA_PHONE_ID"] = "123456789012345"

TEST_ADMIN_PASSWORD = "SenhaInicial123"

import hashlib
import hmac
import json
import uuid
import pytest
from unittest.mock import MagicMock
from sqlalchemy.pool import StaticPool
from sqlalchemy import event
from sqlmodel import SQLModel, Session, create_engine
from pywa.client import WhatsApp
from pywa.types import Message, CallbackButton, CallbackSelection
from pywa.types.base_update import User as WaUser
from src.models.user_model import User
from src.models import menu_model, user_model, chat_history_model, user_session_model, session_model  # noqa: F401


def sign_webhook(body: bytes) -> str:
    """
    Calcula o valor do cabeçalho X-Hub-Signature-256 que a Meta enviaria para o corpo informado.

    Args:
        body: Corpo bruto da requisição de webhook.

    Returns:
        Assinatura no formato sha256=<hex do HMAC-SHA256 com APP_SECRET>.
    """
    digest = hmac.new(os.environ["APP_SECRET"].encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def seed_test_admin(session: Session) -> User:
    """
    Cria o administrador 'admin' de testes em um banco vazio usando a senha inicial de testes.

    Args:
        session: Sessão ativa do banco de dados de testes.

    Returns:
        O administrador recém-criado.
    """
    from src.services.user_service import seed_first_admin

    admin = seed_first_admin(session, TEST_ADMIN_PASSWORD)
    assert admin is not None
    return admin


def make_user_client(session: Session, user: User):
    """
    Cria um cliente de teste autenticado como o usuário informado, com cookie de sessão e token CSRF.

    Args:
        session: Sessão ativa do banco de dados de testes.
        user: Usuário já persistido, dono da nova sessão administrativa.

    Returns:
        TestClient com o cookie de sessão e o cabeçalho X-CSRF-Token configurados.
    """
    from datetime import datetime, timedelta, timezone
    from fastapi.testclient import TestClient
    from main import app
    from src.core.security import SESSION_COOKIE_NAME, generate_csrf_token, generate_session_token
    from src.models.session_model import AdminSession

    token = generate_session_token()
    session.add(
        AdminSession(
            id=token,
            user_id=user.id,  # type: ignore
            expires_at=datetime.now(timezone.utc) + timedelta(hours=12),
        )
    )
    session.commit()

    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE_NAME, token)
    client.headers.update({"X-CSRF-Token": generate_csrf_token(token)})
    return client


@pytest.fixture(name="engine")
def engine_fixture():
    """
    Cria um motor SQLite isolado em memória, com chaves estrangeiras ativas como em produção.

    Yields:
        Instância de Engine configurada com banco de dados em memória.
    """
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(test_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(test_engine)
    yield test_engine
    SQLModel.metadata.drop_all(test_engine)


@pytest.fixture(name="session", autouse=True)
def session_fixture(engine, monkeypatch):
    """
    Fornece uma sessão ativa no banco de dados isolado e injeta o motor de teste.

    Args:
        engine: Motor SQLite de teste em memória.
        monkeypatch: Utilitário pytest para sobrescrever referências globais.

    Yields:
        Sessão ativa do SQLModel para operações no teste.
    """
    monkeypatch.setattr("src.core.db.engine", engine)

    with Session(engine) as session:
        yield session


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """
    Reseta o armazenamento do slowapi antes e depois de cada teste para evitar falsos 429.
    """
    from src.controllers.auth_controller import limiter
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture(name="auth_client")
def auth_client_fixture(session: Session):
    """
    Fornece um TestClient com sessão de administrador ativa e cabeçalhos de segurança configurados.
    """
    from src.core.security import SESSION_COOKIE_NAME, generate_session_token, generate_csrf_token
    from src.models.session_model import AdminSession
    from datetime import datetime, timezone, timedelta
    from starlette.testclient import TestClient
    from main import app

    admin = seed_test_admin(session)
    token = generate_session_token()
    csrf = generate_csrf_token(token)

    admin_session = AdminSession(
        id=token,
        user_id=admin.id,  # type: ignore
        expires_at=datetime.now(timezone.utc) + timedelta(hours=12),
    )
    session.add(admin_session)
    session.commit()

    client = TestClient(app, base_url="https://testserver", follow_redirects=True)
    client.cookies.set(SESSION_COOKIE_NAME, token)
    client.headers.update({"X-CSRF-Token": csrf})
    return client


@pytest.fixture(name="mock_wa_client")
def mock_wa_client_fixture():
    """
    Gera um mock do cliente WhatsApp da biblioteca PyWa.

    Returns:
        Mock simulando o cliente WhatsApp com retorno fixo para envio de mensagens.
    """
    client = MagicMock(spec=WhatsApp)
    client.send_message.return_value = "wamid.TEST_MESSAGE_ID_12345"
    return client


@pytest.fixture(name="message_factory")
def message_factory_fixture():
    """
    Fábrica auxiliar para criar instâncias mock de mensagens recebidas.

    Returns:
        Função criadora de mensagens WhatsApp para testes.
    """
    def _create_message(
        wa_id: str | None = "554798765432",
        name: str = "Usuário Teste",
        text: str = "Olá",
        bsuid: str = "BR.1234567890123",
    ) -> Message:
        msg = MagicMock(spec=Message)
        user = MagicMock(spec=WaUser)
        user.bsuid = bsuid
        user.wa_id = wa_id
        user.name = name
        msg.from_user = user
        msg.text = text
        return msg

    return _create_message


@pytest.fixture(name="button_factory")
def button_factory_fixture():
    """
    Fábrica auxiliar para criar instâncias mock de botões de resposta rápida clicados.

    Returns:
        Função criadora de eventos CallbackButton.
    """
    def _create_button(
        wa_id: str | None = "554798765432",
        data: str = "menu:1",
        title: str = "Opção",
        bsuid: str = "BR.1234567890123",
    ) -> CallbackButton:
        btn = MagicMock(spec=CallbackButton)
        user = MagicMock(spec=WaUser)
        user.bsuid = bsuid
        user.wa_id = wa_id
        user.name = "Usuário Teste"
        btn.from_user = user
        btn.data = data
        btn.title = title
        return btn

    return _create_button


@pytest.fixture(name="selection_factory")
def selection_factory_fixture():
    """
    Fábrica auxiliar para criar instâncias mock de seleção em listas interativas.

    Returns:
        Função criadora de eventos CallbackSelection.
    """
    def _create_selection(
        wa_id: str | None = "554798765432",
        data: str = "menu:1",
        title: str = "Opção",
        bsuid: str = "BR.1234567890123",
    ) -> CallbackSelection:
        sel = MagicMock(spec=CallbackSelection)
        user = MagicMock(spec=WaUser)
        user.bsuid = bsuid
        user.wa_id = wa_id
        user.name = "Usuário Teste"
        sel.from_user = user
        sel.data = data
        sel.title = title
        return sel

    return _create_selection


@pytest.fixture(name="webhook_body")
def webhook_body_fixture():
    """
    Fábrica de corpos de webhook no formato da Meta, com identificador único por mensagem.

    O identificador é único no processo inteiro: a PyWa descarta atualizações repetidas, e o cliente
    WhatsApp da aplicação vive além de cada teste.

    Returns:
        Função que recebe o tipo (text, button ou list), o conteúdo, o wa_id (None simula usuário
        com nome de usuário, sem telefone), o BSUID e o título da opção, e devolve o corpo em bytes.
    """
    def _build(
        kind: str = "text",
        content: str = "Olá",
        wa_id: str | None = "554798765432",
        bsuid: str = "BR.1234567890123",
        title: str = "Opção",
    ) -> bytes:
        message: dict = {
            "from": wa_id or bsuid,
            "id": f"wamid.TEST{uuid.uuid4().hex}",
            "timestamp": "1700000000",
        }
        if kind == "button":
            message["type"] = "interactive"
            message["interactive"] = {
                "type": "button_reply",
                "button_reply": {"id": content, "title": title},
            }
        elif kind == "list":
            message["type"] = "interactive"
            message["interactive"] = {
                "type": "list_reply",
                "list_reply": {"id": content, "title": title},
            }
            message["context"] = {"from": os.environ["WA_PHONE_ID"], "id": "wamid.CONTEXTO"}
        else:
            message["type"] = "text"
            message["text"] = {"body": content}

        contact: dict = {"profile": {"name": "Usuário Teste"}, "user_id": bsuid}
        if wa_id:
            contact["wa_id"] = wa_id

        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "1234567890",
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": "15550000000",
                                    "phone_number_id": os.environ["WA_PHONE_ID"],
                                },
                                "contacts": [contact],
                                "messages": [message],
                            },
                        }
                    ],
                }
            ],
        }
        return json.dumps(payload).encode("utf-8")

    return _build
