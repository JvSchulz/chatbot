import re
import unicodedata
from typing import Sequence, Any
from dataclasses import dataclass, replace
from sqlmodel import Session, func, select
from src.models.menu_model import Menu


MENU_FIELDS_REQUIRED_MESSAGE = "Preencha nome, texto de seleção e mensagem."

# Uma lista interativa do WhatsApp aceita no máximo 10 linhas; uma delas é sempre reservada
# ("Fazer uma pergunta" na raiz, "Voltar" nos demais menus), então todo pai comporta 9 filhos.
WHATSAPP_LIST_LIMIT = 10
MENU_CHILDREN_LIMIT = WHATSAPP_LIST_LIMIT - 1
MENU_CHILDREN_LIMIT_MESSAGE = (
    f"Este menu já tem o máximo de {MENU_CHILDREN_LIMIT} opções permitido pelo WhatsApp."
)

# Sufixo que o bot acrescenta à mensagem de uma folha; o corpo interativo da Meta aceita 1024
# caracteres, então a mensagem cadastrada precisa deixar espaço para ele.
LEAF_SUFFIX = "\n\nDeseja realizar outra consulta?"
WHATSAPP_BODY_LIMIT = 1024

# O título de um botão de resposta rápida (o limite mais estrito em que o texto de seleção aparece)
# aceita 20 caracteres.
MAX_SELECTION_NAME_LEN = 20
MAX_MESSAGE_LEN = WHATSAPP_BODY_LIMIT - len(LEAF_SUFFIX)

# Limites entregues aos templates do formulário, que os usam em maxlength e no contador.
MENU_TEXT_LIMITS = {"selection_name": MAX_SELECTION_NAME_LEN, "message": MAX_MESSAGE_LEN}

SELECTION_NAME_LABEL = "Texto de seleção"
MESSAGE_LABEL = "Mensagem"

# Sequências de dígitos maiores que isto são cortadas na chave de ordenação: o Python recusa
# converter números gigantes e a lista de menus não pode quebrar por causa de um nome.
MAX_SORT_DIGITS = 100

DIGIT_RUNS_PATTERN = re.compile(r"(\d+)")


@dataclass
class MenuData:
    """Objeto de parâmetros para criação e atualização de nós de menu."""
    name: str
    selection_name: str
    message: str
    parent_id: int | None = None
    is_root: bool = False


def _clean_menu_data(data: MenuData) -> MenuData:
    """
    Remove os espaços das pontas dos campos de texto do menu, exige que nenhum fique vazio e
    confere os limites de tamanho do texto de seleção e da mensagem.

    O navegador envia quebras de linha como CRLF, mas conta e exibe cada quebra como um só
    caractere; a mensagem é normalizada para LF para que o contador do formulário e o limite
    do servidor concordem.

    Args:
        data: Dados de menu recebidos do formulário.

    Returns:
        Cópia dos dados com nome, texto de seleção e mensagem sem espaços nas pontas.

    Raises:
        ValueError: Se algum dos três campos estiver vazio ou contiver apenas espaços, ou se o
            texto de seleção ou a mensagem passar do limite de caracteres do WhatsApp.
    """
    cleaned = replace(
        data,
        name=data.name.strip(),
        selection_name=data.selection_name.strip(),
        message=data.message.replace("\r\n", "\n").strip(),
    )
    if not (cleaned.name and cleaned.selection_name and cleaned.message):
        raise ValueError(MENU_FIELDS_REQUIRED_MESSAGE)
    _ensure_within_limit(SELECTION_NAME_LABEL, cleaned.selection_name, MAX_SELECTION_NAME_LEN)
    _ensure_within_limit(MESSAGE_LABEL, cleaned.message, MAX_MESSAGE_LEN)
    return cleaned


def _ensure_within_limit(label: str, text: str, limit: int) -> None:
    """
    Garante que um texto enviado ao WhatsApp não passa do limite de caracteres da Meta.

    Args:
        label: Nome do campo no formulário, usado na mensagem de erro.
        text: Texto já sem espaços nas pontas.
        limit: Máximo de caracteres permitido.

    Raises:
        ValueError: Se o texto tiver mais caracteres que o limite.
    """
    if len(text) > limit:
        raise ValueError(f"{label} pode ter no máximo {limit} caracteres.")


def menu_sort_key(text: str) -> tuple[tuple[int, int | str], ...]:
    """
    Gera a chave de ordenação natural de um texto de menu.

    Ignora maiúsculas, minúsculas e acentos e compara sequências de dígitos como números, então
    "2 - Y" vem antes de "10 - X". Cada trecho recebe uma etiqueta (0 para número, 1 para texto),
    o que mantém as tuplas comparáveis quando um número encontra um texto na mesma posição.

    Args:
        text: Nome ou texto de seleção do menu.

    Returns:
        Tupla de trechos etiquetados, própria para o parâmetro key de sorted().
    """
    decomposed = unicodedata.normalize("NFKD", text)
    folded = "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()
    return tuple(
        (0, int(part[:MAX_SORT_DIGITS])) if part.isdecimal() else (1, part)
        for part in DIGIT_RUNS_PATTERN.split(folded)
        if part
    )


def _sorted_by_name(menus: Sequence[Menu]) -> list[Menu]:
    """Ordena os menus pelo nome interno com a chave natural; empates seguem o id."""
    return sorted(menus, key=lambda menu: (menu_sort_key(menu.name), menu.id or 0))


def _sorted_by_selection_name(menus: Sequence[Menu]) -> list[Menu]:
    """Ordena os menus pelo texto de seleção com a chave natural; empates seguem o id."""
    return sorted(menus, key=lambda menu: (menu_sort_key(menu.selection_name), menu.id or 0))


def is_root_toggle_allowed(has_root: bool, is_current_root: bool) -> bool:
    """
    Indica se o checkbox de menu raiz pode ser alterado no formulário.

    Args:
        has_root: Se já existe um menu raiz cadastrado.
        is_current_root: Se o menu exibido é a própria raiz (ou o rascunho da primeira raiz).

    Returns:
        True apenas quando não há raiz ou o menu exibido é a raiz.
    """
    return (not has_root) or is_current_root


def get_all_menus(session: Session) -> Sequence[Menu]:
    """
    Retorna todos os menus ordenados pelo nome com a chave natural (sem distinguir caixa e acentos).

    Args:
        session: Sessão ativa do banco de dados.

    Returns:
        Sequência de todos os menus cadastrados.
    """
    return _sorted_by_name(session.exec(select(Menu)).all())


def get_root_menus(session: Session) -> Sequence[Menu]:
    """
    Retorna todos os menus de nível raiz (onde parent_id é nulo), do menor id para o maior.

    Args:
        session: Sessão ativa do banco de dados.

    Returns:
        Sequência de instâncias de Menu raiz.
    """
    return session.exec(select(Menu).where(Menu.parent_id == None).order_by(Menu.id)).all()  # type: ignore


def get_root_menu(session: Session) -> Menu | None:
    """
    Retorna o único menu raiz ativo do sistema (o de menor id se houver mais de um sem pai).

    Args:
        session: Sessão ativa do banco de dados.

    Returns:
        Instância de Menu raiz ou None se nenhum estiver configurado.
    """
    roots = get_root_menus(session)
    return roots[0] if roots else None


def get_root_children(session: Session) -> Sequence[Menu]:
    """
    Retorna os filhos diretos do menu raiz, ou uma lista vazia se não houver raiz.

    Args:
        session: Sessão ativa do banco de dados.

    Returns:
        Sequência de menus cujo pai é o menu raiz.
    """
    root = get_root_menu(session)
    if root is None or root.id is None:
        return []
    return get_submenus(session, root.id)


def get_submenus(session: Session, parent_id: int) -> Sequence[Menu]:
    """
    Retorna os submenus de um menu pai, na ordem em que o WhatsApp os exibe.

    Args:
        session: Sessão ativa do banco de dados.
        parent_id: Identificador do menu pai.

    Returns:
        Submenus ordenados pelo texto de seleção com a chave natural.
    """
    return _sorted_by_selection_name(session.exec(select(Menu).where(Menu.parent_id == parent_id)).all())


def get_menu_by_id(session: Session, menu_id: int) -> Menu | None:
    """
    Busca um registro de menu pelo seu identificador primário.

    Args:
        session: Sessão ativa do banco de dados.
        menu_id: Identificador numérico do menu no banco de dados.

    Returns:
        Instância de Menu encontrada ou None caso não exista.
    """
    return session.get(Menu, menu_id)


def get_valid_parent_menus(
    session: Session,
    exclude_id: int | None = None,
) -> Sequence[Menu]:
    """
    Retorna lista de menus elegíveis a serem pais, prevenindo ciclos hierárquicos.

    Args:
        session: Sessão ativa do banco de dados.
        exclude_id: Identificador do menu sendo editado (exclui ele e seus descendentes).

    Returns:
        Menus que podem atuar como pai sem gerar ciclos, ordenados pelo nome.
    """
    all_menus = get_all_menus(session)
    if exclude_id is None:
        return all_menus

    excluded_ids = _collect_descendant_ids(all_menus, exclude_id)
    valid = [m for m in all_menus if m.id not in excluded_ids]
    if not valid:
        return [m for m in all_menus if m.id != exclude_id]
    return valid


def build_menu_split_view_context(
    session: Session,
    selected_id: int | None = None,
) -> dict[str, Any]:
    """
    Constrói o dicionário de contexto para a visualização split-view de menus.

    Args:
        session: Sessão ativa do banco de dados.
        selected_id: Identificador opcional do menu a ser exibido selecionado.

    Returns:
        Dicionário com menus, menu selecionado, menu raiz, flags de validação de raiz e limites de texto.
    """
    all_menus = get_all_menus(session)
    root_menu = get_root_menu(session)
    has_root = root_menu is not None

    if selected_id is not None:
        selected_menu = get_menu_by_id(session, selected_id)
    else:
        selected_menu = root_menu or (all_menus[0] if all_menus else None)

    # Sem menus, o card é o rascunho do primeiro menu, que obrigatoriamente será a raiz.
    is_current_root = selected_menu.parent_id is None if selected_menu else not has_root
    can_toggle_root = is_root_toggle_allowed(has_root, is_current_root)
    valid_parents = get_valid_parent_menus(session, selected_menu.id if selected_menu else None)

    return {
        "menus": all_menus,
        "selected_menu": selected_menu,
        "root_menu": root_menu,
        "has_root": has_root,
        "is_current_root": is_current_root,
        "can_toggle_root": can_toggle_root,
        "valid_parents": valid_parents,
        "limits": MENU_TEXT_LIMITS,
    }



def can_delete_menu(session: Session, menu_id: int) -> bool:
    """
    Verifica se um menu pode ser excluído com segurança (sem submenus vinculados).

    Args:
        session: Sessão ativa do banco de dados.
        menu_id: Identificador do menu a verificar.

    Returns:
        True se o menu não possuir submenus; False caso possua filhos.
    """
    submenus = session.exec(select(Menu).where(Menu.parent_id == menu_id)).all()
    return len(submenus) == 0


def _ensure_parent_has_room(session: Session, parent_id: int) -> None:
    """
    Garante que o menu pai comporta mais um filho dentro do limite de linhas de uma lista do WhatsApp.

    Só é chamada para novos filhos e para menus movidos de outro pai, então o filho nunca já está contado.

    Args:
        session: Sessão ativa do banco de dados.
        parent_id: Identificador do menu que receberá o filho.

    Raises:
        ValueError: Se o pai já tem o máximo de filhos (9, uma linha fica reservada à navegação).
    """
    parent = session.get(Menu, parent_id)
    if parent is None:
        return
    count_children = select(func.count()).select_from(Menu).where(Menu.parent_id == parent_id)
    if session.exec(count_children).one() >= MENU_CHILDREN_LIMIT:
        raise ValueError(MENU_CHILDREN_LIMIT_MESSAGE)


def _second_root_message(existing_root: Menu) -> str:
    """Monta a mensagem de erro para a tentativa de definir uma segunda raiz."""
    return f"Já existe um menu raiz definido ('{existing_root.name}'). Não é permitido ter mais de um menu raiz."


def create_menu(session: Session, data: MenuData) -> Menu:
    """
    Persiste um novo nó de menu no banco de dados com validação de raiz única.

    Args:
        session: Sessão ativa do banco de dados.
        data: Dados estruturados do menu a criar.

    Returns:
        Instância do menu persistido com ID gerado.

    Raises:
        ValueError: Caso se tente criar um segundo menu raiz, um submenu sem pai ou sem raiz, ou um
            filho além do limite de opções por lista do WhatsApp.
    """
    menu_data = _clean_menu_data(data)
    existing_root = get_root_menu(session)

    if menu_data.is_root:
        if existing_root is not None:
            raise ValueError(_second_root_message(existing_root))
        target_parent_id = None
    else:
        if existing_root is None:
            raise ValueError("Nenhum menu raiz está configurado. O menu deve ser definido como raiz.")
        if menu_data.parent_id is None:
            raise ValueError("Um submenu deve ter um menu pai selecionado.")
        target_parent_id = menu_data.parent_id
        _ensure_parent_has_room(session, target_parent_id)

    new_menu = Menu(
        name=menu_data.name,
        selection_name=menu_data.selection_name,
        message=menu_data.message,
        parent_id=target_parent_id,
    )
    session.add(new_menu)
    session.commit()
    session.refresh(new_menu)
    return new_menu


def update_menu(session: Session, menu_id: int, data: MenuData) -> Menu:
    """
    Atualiza as propriedades de um menu existente com proteção contra ciclos e raiz única.

    Args:
        session: Sessão ativa do banco de dados.
        menu_id: Identificador do menu a ser atualizado.
        data: Novos dados estruturados para o menu.

    Returns:
        Instância do menu atualizado.

    Raises:
        ValueError: Caso o menu não exista, tente violar raiz única, gere ciclo hierárquico ou seja movido
            para um pai que já tem o máximo de opções por lista do WhatsApp.
    """
    menu = session.get(Menu, menu_id)
    if not menu:
        raise ValueError(f"Menu com ID {menu_id} não encontrado.")

    menu_data = _clean_menu_data(data)
    existing_root = get_root_menu(session)

    if menu_data.is_root:
        if existing_root is not None and existing_root.id != menu_id:
            raise ValueError(_second_root_message(existing_root))
        target_parent_id = None
    else:
        if menu_data.parent_id is None and existing_root is not None and existing_root.id != menu_id:
            raise ValueError("Selecione um menu pai para este submenu.")
        target_parent_id = menu_data.parent_id

    if target_parent_id is not None:
        all_menus = session.exec(select(Menu)).all()
        invalid_parent_ids = _collect_descendant_ids(all_menus, menu_id)
        if target_parent_id in invalid_parent_ids:
            raise ValueError("Ciclo hierárquico detectado: um menu não pode ser filho de si mesmo ou de seus descendentes.")
        if target_parent_id != menu.parent_id:
            _ensure_parent_has_room(session, target_parent_id)

    menu.name = menu_data.name
    menu.selection_name = menu_data.selection_name
    menu.message = menu_data.message
    menu.parent_id = target_parent_id

    session.add(menu)
    session.commit()
    session.refresh(menu)
    return menu


def delete_menu(session: Session, menu_id: int) -> bool:
    """
    Remove um menu do banco de dados se não possuir submenus vinculados.

    Args:
        session: Sessão ativa do banco de dados.
        menu_id: Identificador do menu a remover.

    Returns:
        True indicando sucesso da remoção.

    Raises:
        ValueError: Se o menu possuir submenus vinculados ou não for encontrado.
    """
    menu = session.get(Menu, menu_id)
    if not menu:
        raise ValueError(f"Menu com ID {menu_id} não encontrado.")

    if not can_delete_menu(session, menu_id):
        raise ValueError("Não é possível excluir um menu que possui submenus vinculados.")

    session.delete(menu)
    session.commit()
    return True


def _collect_descendant_ids(all_menus: Sequence[Menu], root_id: int) -> set[int]:
    """
    Coleta recursivamente os IDs do nó raiz e de todos os seus descendentes.

    Args:
        all_menus: Sequência completa de menus no banco.
        root_id: Identificador do menu base.

    Returns:
        Conjunto contendo o ID base e todos os IDs descendentes.
    """
    descendants: set[int] = {root_id}
    queue = [root_id]
    while queue:
        current_id = queue.pop(0)
        for m in all_menus:
            if m.parent_id == current_id and m.id is not None and m.id not in descendants:
                descendants.add(m.id)
                queue.append(m.id)
    return descendants
