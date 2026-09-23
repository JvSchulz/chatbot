import pytest
from unittest.mock import MagicMock
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine
from pywa.client import WhatsApp
from pywa.types import Message, CallbackButton, CallbackSelection
from pywa.types.base_update import User
from src.models import menu_model, user_model, chat_history_model, user_session_model  # noqa: F401


@pytest.fixture(name="engine")
def engine_fixture():
    """
    Cria um motor SQLite isolado em memória para execução dos testes.

    Yields:
        Instância de Engine configurada com banco de dados em memória.
    """
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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
    monkeypatch.setattr("src.services.menu_service.engine", engine)
    monkeypatch.setattr("src.services.webhook.chat_history_log.engine", engine)
    # Suporte preventivo caso session_service exista
    try:
        import src.services.session_service
        monkeypatch.setattr("src.services.session_service.engine", engine)
    except (ImportError, AttributeError):
        pass

    with Session(engine) as session:
        yield session


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
        wa_id: str = "554798765432",
        name: str = "Usuário Teste",
        text: str = "Olá",
    ) -> Message:
        msg = MagicMock(spec=Message)
        user = MagicMock(spec=User)
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
        wa_id: str = "554798765432",
        data: str = "menu:1",
    ) -> CallbackButton:
        btn = MagicMock(spec=CallbackButton)
        user = MagicMock(spec=User)
        user.wa_id = wa_id
        btn.from_user = user
        btn.data = data
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
        wa_id: str = "554798765432",
        data: str = "menu:1",
    ) -> CallbackSelection:
        sel = MagicMock(spec=CallbackSelection)
        user = MagicMock(spec=User)
        user.wa_id = wa_id
        sel.from_user = user
        sel.data = data
        return sel

    return _create_selection
