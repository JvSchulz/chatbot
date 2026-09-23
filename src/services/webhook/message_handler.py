from dataclasses import dataclass
import logging
from typing import Any, Sequence
from pywa.client import WhatsApp
from pywa.types.callback import (
    Button,
    CallbackButton,
    CallbackSelection,
    Section,
    SectionList,
    SectionRow,
)
from pywa.types.message import Message
from pywa.types.message_status import MessageStatus
from src.models.menu_model import Menu
from src.services.menu_service import get_menu_by_id, get_root_menus, get_submenus
from src.services.session_service import get_or_create_session, update_session_activity
from src.services.webhook.chat_history_log import (
    is_first_interaction,
    save_message_log,
    save_bot_reply_log,
)

logger = logging.getLogger("Chatbot")

# Limites estruturais da API WhatsApp Cloud da Meta
MAX_QUICK_REPLY_BUTTONS = 3
MAX_BUTTON_TITLE_LEN = 20
MAX_ROW_TITLE_LEN = 24
MAX_ROW_DESC_LEN = 72

# Constantes de ação e prefixos de callback
ACTION_ASK_QUESTION = "action:ask_question"
ACTION_ROOT = "action:root"
PREFIX_MENU = "menu:"

# Modos de sessão de conversa
SESSION_MODE_MENU = "menu"
SESSION_MODE_CONVERSATIONAL = "conversational"


@dataclass(frozen=True)
class MessageContext:
    """
    Estrutura de dados base contendo o contexto normalizado da mensagem recebida.

    Attributes:
        sender_phone: Número de telefone de origem (wa_id).
        target_phone: Número normalizado para envio (com nono dígito quando aplicável).
        user_name: Nome de exibição do usuário remetente.
        message_text: Conteúdo textual da mensagem recebida.
    """

    sender_phone: str
    target_phone: str
    user_name: str
    message_text: str


def handle_message(client: WhatsApp, msg: Message) -> None:
    """
    Orquestra o fluxo de processamento para mensagens de texto recebidas pelo webhook.

    Esteira arquitetural de execução:
    1. Extração do contexto base da mensagem recebida (MessageContext).
    2. Verificação de primeira interação do remetente.
    3. Identificação do modo de atendimento (Menu vs Conversacional LLM).
    4. Construção da resposta especializada baseada no modo ativo.
    5. Persistência da interação no histórico de auditoria.
    6. Despacho da resposta ao usuário via WhatsApp.

    Args:
        client: Cliente WhatsApp do PyWa.
        msg: Mensagem recebida contendo remetente e conteúdo textual.
    """
    context = extract_message_context(msg)
    if not context:
        return

    logger.info(
        f"[INBOUND] De: {context.user_name} ({context.sender_phone}) | Texto: '{context.message_text}'"
    )

    # 1. Verifica primeira interação do usuário no histórico
    _first_interaction = is_first_interaction(context.sender_phone)

    # 2. Identifica o modo de atendimento (Menu vs Conversacional LLM)
    session_mode = identify_session_mode(context.sender_phone)

    # 3. Constrói a carga de resposta adequada para o modo
    response_payload = build_mode_response(mode=session_mode, context=context)

    # 4. Registra a interação no histórico de conversas
    save_message_log(msg=msg, accessed_menu_id=None)

    # 5. Despacha a mensagem ao cliente via WhatsApp
    msg_id = dispatch_reply(
        client=client,
        to=context.target_phone,
        response_payload=response_payload,
    )
    if msg_id:
        save_bot_reply_log(
            recipient_id=context.sender_phone,
            content=response_payload["text"],
            accessed_menu_id=None,
        )


def handle_callback_button(client: WhatsApp, btn: CallbackButton) -> None:
    """
    Processa eventos de clique em botões de resposta rápida.

    Args:
        client: Cliente WhatsApp do PyWa.
        btn: Evento de clique contendo os dados do botão.
    """
    user_id = btn.from_user.wa_id if btn.from_user else None
    if not user_id:
        logger.warning("[CALLBACK BUTTON] Recebido sem wa_id de usuário válido.")
        return

    update_session_activity(wa_id=user_id)
    payload = btn.data
    logger.info(f"[CALLBACK BUTTON] De: {user_id} | Payload: '{payload}'")

    if payload == ACTION_ASK_QUESTION:
        send_root_menu(
            client=client,
            to=user_id,
            intro_text="Nosso assistente está temporariamente indisponível. Escolha uma opção do menu:",
        )
        return

    if payload == ACTION_ROOT:
        send_root_menu(client, to=user_id, intro_text="Aqui está o menu principal:")
        return

    if payload.startswith(PREFIX_MENU):
        menu_id = int(payload.removeprefix(PREFIX_MENU))
        handle_menu_navigation(client, callback=btn, menu_id=menu_id)


def handle_callback_selection(client: WhatsApp, sel: CallbackSelection) -> None:
    """
    Processa eventos de seleção em listas interativas (SectionList).

    Args:
        client: Cliente WhatsApp do PyWa.
        sel: Evento de seleção contendo dados da linha clicada.
    """
    user_id = sel.from_user.wa_id if sel.from_user else None
    if not user_id:
        logger.warning("[CALLBACK SELECTION] Recebido sem wa_id de usuário válido.")
        return

    update_session_activity(wa_id=user_id)
    payload = sel.data
    logger.info(f"[CALLBACK SELECTION] De: {user_id} | Payload: '{payload}'")

    if payload == ACTION_ASK_QUESTION:
        send_root_menu(
            client=client,
            to=user_id,
            intro_text="Nosso assistente está temporariamente indisponível. Escolha uma opção do menu:",
        )
        return

    if payload == ACTION_ROOT:
        send_root_menu(client, to=user_id, intro_text="Aqui está o menu principal:")
        return

    if payload.startswith(PREFIX_MENU):
        menu_id = int(payload.removeprefix(PREFIX_MENU))
        handle_menu_navigation(client, callback=sel, menu_id=menu_id)


def handle_status(_: WhatsApp, status: MessageStatus) -> None:
    """
    Registra atualizações de status de entrega das mensagens enviadas pela Meta.

    Args:
        _: Cliente WhatsApp (não utilizado).
        status: Atualização de status da mensagem enviada.
    """
    status_name = (
        status.status.value if hasattr(status.status, "value") else str(status.status)
    )
    recipient = status.from_user.wa_id if status.from_user else "Desconhecido"
    msg_id = status.id

    if status.error:
        err = status.error
        logger.warning(
            f"[STATUS UPDATE] ID: {msg_id} | Destino: {recipient} | Status: {status_name} | "
            f"Erro {err.code}: {err.message} ({err.details})"
        )
    else:
        logger.info(
            f"[STATUS UPDATE] ID: {msg_id} | Destino: {recipient} | Status: {status_name}"
        )


def normalize_phone_number(phone: str | None) -> str:
    """
    Normaliza o número de telefone para o padrão brasileiro com 9º dígito quando aplicável.

    Args:
        phone: String com o número de telefone bruto ou None.

    Returns:
        Número de telefone normalizado.
    """
    if not phone:
        return ""
    clean = str(phone).strip()
    if clean.startswith("55") and len(clean) == 12:
        return f"{clean[:4]}9{clean[4:]}"
    return clean


def extract_message_context(msg: Message) -> MessageContext | None:
    """
    Extrai e normaliza os dados essenciais da mensagem recebida via WhatsApp.

    Args:
        msg: Mensagem bruta recebida do webhook.

    Returns:
        Instância de MessageContext com dados sanitizados ou None caso wa_id inexista.
    """
    sender_phone = str(msg.from_user.wa_id or "")
    if not sender_phone:
        return None

    user_name = msg.from_user.name or "Usuário"
    message_text = msg.text or ""
    target_phone = normalize_phone_number(sender_phone)

    return MessageContext(
        sender_phone=sender_phone,
        target_phone=target_phone,
        user_name=user_name,
        message_text=message_text,
    )


def identify_session_mode(sender_id: str) -> str:
    """
    Identifica o modo de atendimento ativo do usuário (Menu vs Conversacional via LLM).

    Args:
        sender_id: Identificador WhatsApp do remetente (wa_id).

    Returns:
        String indicando o modo ativo (SESSION_MODE_MENU ou SESSION_MODE_CONVERSATIONAL).
    """
    session = get_or_create_session(wa_id=sender_id)
    return session.mode


def build_mode_response(
    mode: str,
    context: MessageContext,
) -> dict[str, Any]:
    """
    Gera a carga de resposta correspondente ao modo de atendimento ativo do usuário.

    Args:
        mode: Modo ativo identificado (SESSION_MODE_MENU ou SESSION_MODE_CONVERSATIONAL).
        context: Contexto sanitizado contendo dados do remetente e mensagem.

    Returns:
        Dicionário contendo as chaves 'text' e opcionalmente 'buttons' para despacho.
    """
    if mode == SESSION_MODE_CONVERSATIONAL:
        # Modo conversacional desativado temporariamente (Ollama não conectado):
        # Dispara mensagem de indisponibilidade com as opções do menu raiz para recuperação.
        root_menus = get_root_menus()
        return build_root_response_object(
            menus=root_menus,
            intro_text="Nosso assistente está temporariamente indisponível. Escolha uma opção do menu:",
        )

    # Modo padrão: Menu hierárquico
    root_menus = get_root_menus()
    return build_root_response_object(
        menus=root_menus,
        intro_text=f"Olá {context.user_name}! Escolha uma das opções abaixo:",
    )


def dispatch_reply(
    client: WhatsApp,
    to: str,
    response_payload: dict[str, Any],
) -> str | None:
    """
    Despacha a mensagem de resposta formatada através da API WhatsApp Cloud da Meta.

    Args:
        client: Cliente WhatsApp do PyWa.
        to: Número de telefone normalizado do destinatário.
        response_payload: Carga de dados contendo 'text' e opcionalmente 'buttons'.

    Returns:
        Identificador da mensagem gerada pela Meta em caso de sucesso, ou None se falhar.
    """
    try:
        buttons = response_payload.get("buttons")
        response_msg_id = client.send_message(
            to=to,
            text=response_payload["text"],
            buttons=buttons,
        )
        logger.info(
            f"[OUTBOUND SUCESSO] Para: {to} | Resposta: '{response_payload['text']}' | ID: {response_msg_id}"
        )
        return str(response_msg_id)
    except Exception as error:
        logger.error(
            f"[OUTBOUND FALHA] Erro ao despachar requisição para a Meta: {error}"
        )
        return None


def handle_menu_navigation(
    client: WhatsApp,
    callback: CallbackSelection | CallbackButton,
    menu_id: int,
) -> None:
    """
    Processa a navegação hierárquica e renderiza o próximo nível de menus.

    Args:
        client: Cliente WhatsApp do PyWa para despacho de mensagens.
        callback: Evento de clique recebido (botão ou item de lista).
        menu_id: Identificador do menu selecionado.
    """
    user_id = callback.from_user.wa_id if callback.from_user else None
    if not user_id:
        logger.warning("[MENU NAV] Callback recebido sem wa_id de usuário válido.")
        return

    menu = get_menu_by_id(menu_id)

    # Proteção contra caso de borda: Menu foi excluído ou desativado no painel administrativo
    if not menu:
        send_root_menu(
            client=client,
            to=user_id,
            intro_text="Esse menu não está mais disponível. Aqui estão as opções principais:",
        )
        return

    submenus = get_submenus(parent_id=menu_id)
    target_phone = normalize_phone_number(user_id)

    if submenus:
        response = build_child_response_object(
            menus=submenus,
            intro_text=f"{menu.name}\n\n{menu.message}",
        )
        msg_id = dispatch_reply(
            client=client,
            to=target_phone,
            response_payload=response,
        )
        if msg_id:
            save_bot_reply_log(
                recipient_id=user_id,
                content=response["text"],
                accessed_menu_id=menu_id,
            )
        update_session_activity(wa_id=user_id, menu_id=menu_id)
        return

    # Menu folha: exibe mensagem final e botões de retorno (anterior e início)
    leaf_buttons: list[Button] = []
    if menu.parent_id is not None:
        leaf_buttons.append(
            Button(
                title="Voltar"[:MAX_BUTTON_TITLE_LEN],
                callback_data=f"{PREFIX_MENU}{menu.parent_id}",
            )
        )
    leaf_buttons.append(
        Button(
            title="Voltar ao início"[:MAX_BUTTON_TITLE_LEN],
            callback_data=ACTION_ROOT,
        )
    )
    leaf_text = f"{menu.message}\n\nDeseja realizar outra consulta?"
    leaf_payload = {
        "text": leaf_text,
        "buttons": leaf_buttons,
    }
    msg_id = dispatch_reply(
        client=client,
        to=target_phone,
        response_payload=leaf_payload,
    )
    if msg_id:
        save_bot_reply_log(
            recipient_id=user_id,
            content=leaf_text,
            accessed_menu_id=menu_id,
        )
    update_session_activity(wa_id=user_id, menu_id=menu_id)


def send_root_menu(
    client: WhatsApp,
    to: str,
    intro_text: str = "Olá! Escolha uma das opções abaixo:",
) -> None:
    """
    Envia o menu raiz interativo para o destinatário informado.

    Args:
        client: Cliente PyWa configurado.
        to: Número de telefone ou wa_id do destinatário.
        intro_text: Texto introdutório da mensagem.
    """
    root_menus = get_root_menus()
    response = build_root_response_object(menus=root_menus, intro_text=intro_text)
    target_phone = normalize_phone_number(to)

    msg_id = dispatch_reply(
        client=client,
        to=target_phone,
        response_payload=response,
    )
    if msg_id:
        save_bot_reply_log(
            recipient_id=to,
            content=response["text"],
            accessed_menu_id=None,
        )
    update_session_activity(wa_id=to, menu_id=None)


def build_root_response_object(
    menus: Sequence[Menu],
    intro_text: str,
) -> dict[str, Any]:
    """
    Constrói o payload para o menu raiz, incluindo a opção de fazer pergunta ao modelo.

    Args:
        menus: Sequência de menus raiz a serem apresentados.
        intro_text: Texto principal exibido no corpo da mensagem.

    Returns:
        Dicionário contendo as chaves 'text' e 'buttons' para despacho via PyWa.
    """
    total_options = len(menus) + 1
    if total_options <= MAX_QUICK_REPLY_BUTTONS:
        return {
            "text": intro_text,
            "buttons": build_root_menu_buttons(menus),
        }

    return {
        "text": intro_text,
        "buttons": build_root_menu_section_list(menus),
    }


def build_child_response_object(
    menus: Sequence[Menu],
    intro_text: str,
) -> dict[str, Any]:
    """
    Constrói o payload para submenus, contendo exclusivamente as opções filhas.

    Args:
        menus: Sequência de submenus a serem apresentados.
        intro_text: Texto principal exibido no corpo da mensagem.

    Returns:
        Dicionário contendo as chaves 'text' e 'buttons' para despacho via PyWa.
    """
    if len(menus) <= MAX_QUICK_REPLY_BUTTONS:
        return {
            "text": intro_text,
            "buttons": build_child_menu_buttons(menus),
        }

    return {
        "text": intro_text,
        "buttons": build_child_menu_section_list(menus),
    }


def build_root_menu_buttons(menus: Sequence[Menu]) -> list[Button]:
    """
    Monta botões para o menu raiz, incluindo o botão de pergunta ao modelo.

    Args:
        menus: Sequência de registros de menu.

    Returns:
        Lista de botões contendo menus e a opção de pergunta.
    """
    buttons = build_child_menu_buttons(menus)
    if len(buttons) < MAX_QUICK_REPLY_BUTTONS:
        buttons.append(
            Button(
                title="Fazer Pergunta"[:MAX_BUTTON_TITLE_LEN],
                callback_data=ACTION_ASK_QUESTION,
            )
        )
    return buttons


def build_child_menu_buttons(menus: Sequence[Menu]) -> list[Button]:
    """
    Monta a lista de botões contendo exclusivamente os menus filhos.

    Args:
        menus: Sequência de registros de menu.

    Returns:
        Lista de instâncias de Button do PyWa.
    """
    return [
        Button(
            title=(m.selection_name or m.name)[:MAX_BUTTON_TITLE_LEN],
            callback_data=f"{PREFIX_MENU}{m.id}",
        )
        for m in menus
    ]


def build_root_menu_section_list(menus: Sequence[Menu]) -> SectionList:
    """
    Monta a lista de seções para o menu raiz com a opção de pergunta inclusa.

    Args:
        menus: Sequência de registros de menu raiz.

    Returns:
        Instância de SectionList configurada com menus e a linha de pergunta.
    """
    rows = [
        SectionRow(
            title=(m.selection_name or m.name)[:MAX_ROW_TITLE_LEN],
            callback_data=f"{PREFIX_MENU}{m.id}",
            description=(m.name[:MAX_ROW_DESC_LEN] if m.name else None),
        )
        for m in menus
    ]
    rows.append(
        SectionRow(
            title="Fazer uma pergunta"[:MAX_ROW_TITLE_LEN],
            callback_data=ACTION_ASK_QUESTION,
            description="Tirar dúvidas com nosso assistente virtual"[:MAX_ROW_DESC_LEN],
        )
    )
    section = Section(title="Menu", rows=rows)
    return SectionList(button_title="Ver Opções", sections=[section])


def build_child_menu_section_list(menus: Sequence[Menu]) -> SectionList:
    """
    Monta a lista de seções contendo estritamente os submenus filhos.

    Args:
        menus: Sequência de registros de submenus.

    Returns:
        Instância de SectionList configurada exclusivamente com os submenus.
    """
    rows = [
        SectionRow(
            title=(m.selection_name or m.name)[:MAX_ROW_TITLE_LEN],
            callback_data=f"{PREFIX_MENU}{m.id}",
            description=(m.name[:MAX_ROW_DESC_LEN] if m.name else None),
        )
        for m in menus
    ]
    section = Section(title="Menu", rows=rows)
    return SectionList(button_title="Ver Opções", sections=[section])
