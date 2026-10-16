from dataclasses import dataclass
import logging
import re
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
from pywa.types.user import User
from sqlmodel import Session
from src.models.menu_model import Menu
from src.services.menu_service import (
    LEAF_SUFFIX,
    get_menu_by_id,
    get_root_children,
    get_root_menu,
    get_submenus,
)
from src.services.session_service import (
    get_or_create_session,
    update_session_activity,
)
from src.services.webhook.chat_history_log import (
    save_bot_reply_log,
    save_user_log,
)

logger = logging.getLogger("Chatbot")

# Limites estruturais da API WhatsApp Cloud da Meta
MAX_QUICK_REPLY_BUTTONS = 3
MAX_BUTTON_TITLE_LEN = 20
MAX_ROW_TITLE_LEN = 24
MAX_LIST_ROWS = 10

# Constantes de ação e prefixos de callback
ACTION_ROOT = "action:root"
PREFIX_MENU = "menu:"

# Títulos dos botões e das seções de navegação
BACK_TITLE = "Voltar"
BACK_TO_START_TITLE = "Voltar ao início"
MENU_SECTION_TITLE = "Menu"
NAVIGATION_SECTION_TITLE = "Navegação"

NO_ROOT_MESSAGE = "Atendimento indisponível no momento. Tente novamente mais tarde."

# Máximo de dígitos aceito em um identificador de menu (cabe no INTEGER do SQLite e
# evita o limite de conversão de strings numéricas longas do Python)
MAX_MENU_ID_DIGITS = 18

# Trechos de textos externos que identificam o usuário: telefones (8+ dígitos) e BSUIDs
PERSONAL_DATA_PATTERN = re.compile(r"\d{8,}|\b[A-Z]{2}\.\d+")

# Quantidade de caracteres finais do identificador que aparecem nos logs
MASKED_ID_VISIBLE_CHARS = 4

MENU_UNAVAILABLE_MESSAGE = "Esse menu não está mais disponível. Aqui estão as opções principais:"

@dataclass(frozen=True)
class MessageContext:
    """
    Estrutura de dados base contendo o contexto normalizado do evento recebido.

    Attributes:
        session: Sessão do banco de dados dona da transação do evento (confirmada ao final do tratador).
        user_id: BSUID do usuário (sempre presente).
        wa_id: Telefone do usuário, ausente quando ele usa apenas nome de usuário.
        reply_to: Destinatário das respostas, definido por resolve_reply_target.
        user_name: Nome de exibição do usuário remetente.
        message_text: Texto da mensagem ou título da opção selecionada.
    """

    session: Session
    user_id: str
    wa_id: str | None
    reply_to: str
    user_name: str
    message_text: str


def handle_message(client: WhatsApp, msg: Message, session: Session) -> None:
    """
    Orquestra o fluxo de processamento para mensagens de texto recebidas pelo webhook.

    Tudo que o evento grava (sessão, mensagem recebida e resposta) entra em uma única transação,
    confirmada só no fim: se qualquer gravação falhar, nada do evento fica no banco. As gravações
    ficam pendentes até o commit, então o bloqueio de escrita do SQLite não cobre o envio à Meta.

    Esteira arquitetural de execução:
    1. Extração do contexto base da mensagem recebida (MessageContext).
    2. Recuperação da sessão (TTL avaliado).
    3. Registro da mensagem recebida no histórico de auditoria.
    4. Construção e despacho da resposta ao usuário via WhatsApp.
    5. Registro da resposta enviada e da atividade da sessão.
    6. Confirmação da transação do evento.

    Args:
        client: Cliente WhatsApp do PyWa.
        msg: Mensagem recebida contendo remetente e conteúdo textual.
        session: Sessão do banco de dados que abrange o evento inteiro.
    """
    context = extract_message_context(msg, session)
    if not context:
        logger.warning("[INBOUND] Mensagem recebida sem BSUID de usuário válido.")
        return

    logger.info(f"[INBOUND] Tipo: texto | Usuário: {mask_user_id(context.user_id)}")

    user_session = get_or_create_session(session, context.user_id, context.wa_id)
    save_user_log(context)

    response_payload = build_root_view(session)

    msg_id = dispatch_reply(
        client=client,
        to=context.reply_to,
        response_payload=response_payload,
    )
    if msg_id:
        save_bot_reply_log(context, response_payload["text"])
    update_session_activity(user_session, None)
    session.commit()


def handle_callback(
    client: WhatsApp,
    callback: CallbackButton | CallbackSelection,
    session: Session,
) -> None:
    """
    Processa cliques em botões de resposta rápida e seleções em listas interativas.

    Payloads não reconhecidos (prefixo desconhecido ou identificador não numérico) são
    ignorados e o usuário recebe o menu raiz. Como em handle_message, o evento inteiro
    é uma única transação, confirmada só no fim.

    Args:
        client: Cliente WhatsApp do PyWa.
        callback: Evento de clique contendo os dados e o título da opção escolhida.
        session: Sessão do banco de dados que abrange o evento inteiro.
    """
    context = extract_callback_context(callback, session)
    if not context:
        logger.warning("[CALLBACK] Evento recebido sem BSUID de usuário válido.")
        return

    user_session = get_or_create_session(session, context.user_id, context.wa_id)

    payload = str(callback.data)
    menu_id = parse_menu_id(payload)
    selected_menu_id = menu_id if menu_id is not None and get_menu_by_id(session, menu_id) else None
    save_user_log(context, menu_id=selected_menu_id)
    logger.info(f"[CALLBACK] Usuário: {mask_user_id(context.user_id)} | Menu: {menu_id}")

    current_menu_id = None
    if menu_id is not None:
        current_menu_id = handle_menu_navigation(client, context, menu_id)
    else:
        send_root_menu(client, context)
    update_session_activity(user_session, current_menu_id)
    session.commit()


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
    recipient = (
        mask_user_id(status.from_user.bsuid or status.from_user.wa_id)
        if status.from_user
        else "Desconhecido"
    )

    if status.error:
        err = status.error
        logger.warning(
            f"[STATUS UPDATE] Destino: {recipient} | Status: {status_name} | "
            f"Erro {err.code}: {redact(f'{err.message} ({err.details})')}"
        )
    else:
        logger.info(f"[STATUS UPDATE] Destino: {recipient} | Status: {status_name}")


def parse_menu_id(payload: str) -> int | None:
    """
    Extrai o identificador de menu de um payload de callback no formato 'menu:<id>'.

    Args:
        payload: Dados do botão ou da linha selecionada.

    Returns:
        Identificador numérico do menu ou None se o payload não for um menu válido.
    """
    if not payload.startswith(PREFIX_MENU):
        return None
    raw_id = payload.removeprefix(PREFIX_MENU)
    if not (raw_id.isascii() and raw_id.isdigit()) or len(raw_id) > MAX_MENU_ID_DIGITS:
        return None
    return int(raw_id)


def mask_user_id(value: str | None) -> str:
    """
    Mascara um identificador de usuário para uso seguro em logs.

    Args:
        value: BSUID, telefone ou None.

    Returns:
        '***' seguido dos últimos caracteres do identificador, ou apenas '***' se for curto ou vazio.
    """
    if not value or len(value) <= MASKED_ID_VISIBLE_CHARS:
        return "***"
    return f"***{value[-MASKED_ID_VISIBLE_CHARS:]}"


def redact(text: str) -> str:
    """
    Mascara telefones e BSUIDs em textos de erro vindos da Meta antes de registrá-los em log.

    Args:
        text: Texto externo que pode citar o usuário.

    Returns:
        O texto com sequências de 8 ou mais dígitos e tokens no formato de BSUID trocados por '***'.
    """
    return PERSONAL_DATA_PATTERN.sub("***", text)


def resolve_reply_target(user_id: str, wa_id: str | None) -> str:
    """
    Define o destinatário das respostas: o telefone normalizado quando existe, senão o BSUID.

    Args:
        user_id: BSUID do usuário.
        wa_id: Telefone do usuário ou None quando ele usa apenas nome de usuário.

    Returns:
        Identificador aceito pela API da Meta como destino da mensagem.
    """
    return normalize_phone_number(wa_id) or user_id


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


def _build_context(session: Session, user: User | None, text: str) -> MessageContext | None:
    """
    Normaliza o remetente de um evento no contexto usado pelo restante do fluxo.

    Args:
        session: Sessão do banco de dados do evento.
        user: Remetente do evento recebido.
        text: Texto digitado ou título da opção selecionada.

    Returns:
        Instância de MessageContext, ou None se o remetente não tiver BSUID.
    """
    if user is None or not user.bsuid:
        return None

    wa_id = user.wa_id or None
    return MessageContext(
        session=session,
        user_id=user.bsuid,
        wa_id=wa_id,
        reply_to=resolve_reply_target(user.bsuid, wa_id),
        user_name=user.name or "Usuário",
        message_text=text,
    )


def extract_message_context(msg: Message, session: Session) -> MessageContext | None:
    """
    Extrai e normaliza os dados essenciais da mensagem recebida via WhatsApp.

    Args:
        msg: Mensagem bruta recebida do webhook.
        session: Sessão do banco de dados do evento.

    Returns:
        Instância de MessageContext com dados sanitizados ou None caso o BSUID inexista.
    """
    return _build_context(session, msg.from_user, msg.text or "")


def extract_callback_context(
    callback: CallbackButton | CallbackSelection,
    session: Session,
) -> MessageContext | None:
    """
    Extrai e normaliza os dados essenciais de um clique em botão ou linha de lista.

    Args:
        callback: Evento de clique recebido do webhook.
        session: Sessão do banco de dados do evento.

    Returns:
        Instância de MessageContext cujo message_text é o título da opção, ou None sem BSUID.
    """
    return _build_context(session, callback.from_user, callback.title or "")


def build_root_view(session: Session, intro_text: str | None = None) -> dict[str, Any]:
    """
    Monta a resposta do menu raiz: a mensagem da raiz e seus filhos diretos como opções.

    Args:
        session: Sessão ativa do banco de dados.
        intro_text: Texto que substitui a mensagem da raiz (avisos e fallbacks).

    Returns:
        Dicionário com 'text' e 'buttons'; sem botões se não houver menu raiz configurado.
    """
    root = get_root_menu(session)
    if root is None:
        return {"text": NO_ROOT_MESSAGE}
    return build_root_response_object(
        menus=get_root_children(session),
        intro_text=intro_text or root.message,
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
        to: Destinatário (telefone normalizado ou BSUID).
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
        logger.info(f"[OUTBOUND SUCESSO] Para: {mask_user_id(to)}")
        return str(response_msg_id)
    except Exception as error:
        logger.error(
            f"[OUTBOUND FALHA] Para: {mask_user_id(to)} | "
            f"Erro ao despachar requisição para a Meta: {redact(str(error))}"
        )
        return None


def handle_menu_navigation(
    client: WhatsApp,
    context: MessageContext,
    menu_id: int,
) -> int | None:
    """
    Processa a navegação hierárquica e renderiza o próximo nível de menus.

    A raiz é renderizada como menu raiz; submenus mostram os filhos e "Voltar"; folhas oferecem
    "Voltar" e "Voltar ao início".

    Args:
        client: Cliente WhatsApp do PyWa para despacho de mensagens.
        context: Contexto do usuário que selecionou o menu.
        menu_id: Identificador do menu selecionado.

    Returns:
        Identificador do menu que ficou exibido ao usuário, ou None quando ele viu o menu raiz.
    """
    menu = get_menu_by_id(context.session, menu_id)

    # Proteção contra caso de borda: Menu foi excluído ou desativado no painel administrativo
    if not menu:
        send_root_menu(client, context, intro_text=MENU_UNAVAILABLE_MESSAGE)
        return None

    root = get_root_menu(context.session)
    if root is not None and root.id == menu_id:
        send_root_menu(client, context)
        return None

    submenus = get_submenus(context.session, menu_id)
    if submenus:
        response = build_child_response_object(
            menus=submenus,
            back=build_back_button(menu),
            intro_text=menu.message,
        )
    else:
        response = build_leaf_response_object(menu)

    msg_id = dispatch_reply(
        client=client,
        to=context.reply_to,
        response_payload=response,
    )
    if msg_id:
        save_bot_reply_log(context, response["text"], menu_id=menu_id)
    return menu_id


def build_back_button(menu: Menu) -> Button:
    """
    Constrói o botão "Voltar" de um menu: leva ao menu pai, ou ao início se o menu não tem pai.

    Args:
        menu: Menu exibido ao usuário.

    Returns:
        Botão "Voltar" com o callback do menu pai.
    """
    target = ACTION_ROOT if menu.parent_id is None else f"{PREFIX_MENU}{menu.parent_id}"
    return Button(title=BACK_TITLE, callback_data=target)


def build_leaf_response_object(menu: Menu) -> dict[str, Any]:
    """
    Constrói o payload de um menu folha: a mensagem final e os botões de retorno.

    Args:
        menu: Menu folha a ser exibido.

    Returns:
        Dicionário com 'text' e 'buttons': "Voltar" (ao pai) e "Voltar ao início". Um menu sem pai
        só oferece "Voltar ao início", porque os dois botões levariam ao mesmo lugar.
    """
    back = build_back_button(menu)
    start = Button(title=BACK_TO_START_TITLE, callback_data=ACTION_ROOT)
    buttons = [start] if back.callback_data == start.callback_data else [back, start]
    return {
        "text": f"{menu.message}{LEAF_SUFFIX}",
        "buttons": buttons,
    }


def send_root_menu(
    client: WhatsApp,
    context: MessageContext,
    intro_text: str | None = None,
) -> None:
    """
    Envia o menu raiz interativo para o usuário do contexto informado.

    Args:
        client: Cliente PyWa configurado.
        context: Contexto do usuário destinatário.
        intro_text: Texto que substitui a mensagem da raiz (avisos e fallbacks).
    """
    response = build_root_view(context.session, intro_text)
    msg_id = dispatch_reply(
        client=client,
        to=context.reply_to,
        response_payload=response,
    )
    if msg_id:
        save_bot_reply_log(context, response["text"])


def build_root_response_object(
    menus: Sequence[Menu],
    intro_text: str,
) -> dict[str, Any]:
    """
    Constrói o payload para o menu raiz, que apresenta apenas os filhos diretos da raiz.

    Args:
        menus: Sequência de menus raiz a serem apresentados.
        intro_text: Texto principal exibido no corpo da mensagem.

    Returns:
        Dicionário com 'text' apenas, se não houver filhos (a Meta recusa mensagem interativa
        sem opções); com 'text' e botões de resposta rápida, se houver até três filhos; com 'text'
        e uma lista de seções, se houver mais.
    """
    if not menus:
        return {"text": intro_text}

    if len(menus) <= MAX_QUICK_REPLY_BUTTONS:
        return {
            "text": intro_text,
            "buttons": build_child_menu_buttons(menus),
        }

    return {
        "text": intro_text,
        "buttons": build_root_menu_section_list(menus),
    }


def build_child_response_object(
    menus: Sequence[Menu],
    back: Button,
    intro_text: str,
) -> dict[str, Any]:
    """
    Constrói o payload para submenus: as opções filhas seguidas do botão "Voltar".

    Args:
        menus: Sequência de submenus a serem apresentados.
        back: Botão "Voltar" do menu exibido.
        intro_text: Texto principal exibido no corpo da mensagem.

    Returns:
        Dicionário com 'text' e 'buttons': botões de resposta rápida se filhos e "Voltar" couberem
        em três, senão uma lista de seções.
    """
    if len(menus) + 1 <= MAX_QUICK_REPLY_BUTTONS:
        return {
            "text": intro_text,
            "buttons": [*build_child_menu_buttons(menus), back],
        }

    return {
        "text": intro_text,
        "buttons": build_child_menu_section_list(menus, back),
    }


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


def limit_list_menus(menus: Sequence[Menu], reserved_rows: int) -> Sequence[Menu]:
    """
    Corta os menus que não cabem nas linhas de uma lista interativa do WhatsApp.

    O cadastro de menus já impede excedentes; este corte evita que dados antigos façam a Meta
    recusar a mensagem inteira.

    Args:
        menus: Menus candidatos a linhas da lista.
        reserved_rows: Linhas fixas da lista que não vêm de menus (0 na raiz,
            1 para "Voltar" nos demais menus).

    Returns:
        Os primeiros menus que cabem, mantendo a ordem.
    """
    room = MAX_LIST_ROWS - reserved_rows
    if len(menus) > room:
        logger.warning(
            f"[MENU] Lista com {len(menus) + reserved_rows} opções excede o limite do WhatsApp; "
            f"exibindo {MAX_LIST_ROWS}."
        )
    return menus[:room]


def build_root_menu_section_list(menus: Sequence[Menu]) -> SectionList:
    """
    Monta a lista de seções do menu raiz: uma única seção "Menu" só com os filhos da raiz.

    Args:
        menus: Sequência de registros de menu raiz.

    Returns:
        Instância de SectionList com uma linha por filho, sem descrição.
    """
    rows = [
        SectionRow(
            title=(m.selection_name or m.name)[:MAX_ROW_TITLE_LEN],
            callback_data=f"{PREFIX_MENU}{m.id}",
        )
        for m in limit_list_menus(menus, reserved_rows=0)
    ]
    return SectionList(button_title="Ver Opções", sections=[Section(title=MENU_SECTION_TITLE, rows=rows)])


def build_child_menu_section_list(menus: Sequence[Menu], back: Button) -> SectionList:
    """
    Monta a lista de seções de um submenu: os filhos em "Menu" e o "Voltar" em "Navegação".

    Args:
        menus: Sequência de registros de submenus.
        back: Botão "Voltar" do menu exibido, que vira a única linha da seção de navegação.

    Returns:
        Instância de SectionList com a linha de "Voltar" reservada fora do corte dos filhos.
    """
    rows = [
        SectionRow(
            title=(m.selection_name or m.name)[:MAX_ROW_TITLE_LEN],
            callback_data=f"{PREFIX_MENU}{m.id}",
        )
        for m in limit_list_menus(menus, reserved_rows=1)
    ]
    navigation_row = SectionRow(title=back.title[:MAX_ROW_TITLE_LEN], callback_data=back.callback_data)
    return SectionList(
        button_title="Ver Opções",
        sections=[
            Section(title=MENU_SECTION_TITLE, rows=rows),
            Section(title=NAVIGATION_SECTION_TITLE, rows=[navigation_row]),
        ],
    )
