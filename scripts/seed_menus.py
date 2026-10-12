#!/usr/bin/env python3
"""
Seed script for Chatbot menus table.
Populates the menus table with one root menu (the greeting container) whose children are the
top-level options, plus a realistic hierarchical menu structure for testing navigation
(depth 0, 1, 2 and 3), button/section list responses, and LLM fallback context.

Usage (from the project root):
    python -m scripts.seed_menus           # Seeds only if table is empty
    python -m scripts.seed_menus --reset   # Clears menus and reseeds from scratch
"""

import argparse
from collections.abc import Sequence
from pathlib import Path
from sqlalchemy import create_engine, delete, event
from sqlmodel import Session, SQLModel, func, select
from src.core.db import DB_PATH, set_sqlite_pragma
from src.models import chat_history_model, menu_model, session_model, user_model, user_session_model  # noqa: F401
from src.models.menu_model import Menu

MENUS_DATA = [
    # --- LEVEL 0: Root menu (container: its message is the greeting, its children are the options) ---
    {
        "id": 1,
        "name": "menu_inicio",
        "selection_name": "Início",
        "message": (
            "👋 *Bem-vindo ao atendimento da UDESC!*\n\n"
            "Escolha uma das opções abaixo ou toque em *Fazer Pergunta* para falar com nosso assistente:"
        ),
        "parent_id": None,
    },

    # --- LEVEL 1: Top-level menus, children of the root (parent_id: 1) ---
    {
        "id": 2,
        "name": "menu_cursos",
        "selection_name": "1 - Graduação",
        "message": (
            "🎓 *Cursos de Graduação - UDESC*\n\n"
            "Selecione um dos cursos abaixo para ver detalhes, duração, turno e contatos da coordenação:"
        ),
        "parent_id": 1,
    },
    {
        "id": 3,
        "name": "menu_secretaria",
        "selection_name": "2 - Secretaria",
        "message": (
            "📋 *Secretaria Acadêmica*\n\n"
            "Escolha um dos serviços abaixo para obter orientações, prazos e emissão de documentos:"
        ),
        "parent_id": 1,
    },
    {
        "id": 4,
        "name": "menu_suporte",
        "selection_name": "3 - Suporte e TI",
        "message": (
            "💻 *Suporte de TI e Sistemas*\n\n"
            "Como podemos ajudar com os sistemas institucionais? Escolha uma opção:"
        ),
        "parent_id": 1,
    },
    {
        "id": 5,
        "name": "menu_atendente",
        "selection_name": "4 - Atendente",
        "message": (
            "📞 *Atendimento Presencial e Contato*\n\n"
            "Nossa equipe atende de segunda a sexta-feira, das 08h às 20h.\n"
            "• E-mail: secretaria.cct@udesc.br\n"
            "• Telefone: (47) 3803-7200\n"
            "• Endereço: Campus Universitário Prof. Collaço, Bloco Central\n\n"
            "Caso prefira, digite sua dúvida em texto livre a qualquer momento para falar com nossa IA!"
        ),
        "parent_id": 1,
    },

    # --- LEVEL 1: Submenus of 'Cursos de Graduação' (parent_id: 2) ---
    {
        "id": 6,
        "name": "curso_cc",
        "selection_name": "1.1 - Computação",
        "message": (
            "💻 *Bacharelado em Ciência da Computação*\n\n"
            "• Duração: 4 anos (8 semestres)\n"
            "• Turno: Integral (matutino/vespertino)\n"
            "• Vagas: 40 por semestre\n"
            "• Coordenação: coord.dcc@udesc.br\n"
            "• Foco: Inteligência Artificial, Engenharia de Software e Algoritmos Avançados."
        ),
        "parent_id": 2,
    },
    {
        "id": 7,
        "name": "curso_si",
        "selection_name": "1.2 - Sist. Inform.",
        "message": (
            "📊 *Bacharelado em Sistemas de Informação*\n\n"
            "• Duração: 4 anos (8 semestres)\n"
            "• Turno: Noturno\n"
            "• Vagas: 40 por semestre\n"
            "• Coordenação: coord.bsi@udesc.br\n"
            "• Foco: Governança de TI, Gestão de Negócios Digitais e Engenharia de Dados."
        ),
        "parent_id": 2,
    },
    {
        "id": 8,
        "name": "curso_ep",
        "selection_name": "1.3 - Eng. Produção",
        "message": (
            "⚙️ *Engenharia de Produção e Sistemas*\n\n"
            "• Duração: 5 anos (10 semestres)\n"
            "• Turno: Integral\n"
            "• Vagas: 35 por semestre\n"
            "• Coordenação: coord.eps@udesc.br\n"
            "• Foco: Gestão da Cadeia de Suprimentos, Logística, Qualidade e Processos Industriais."
        ),
        "parent_id": 2,
    },

    # --- LEVEL 1: Submenus of 'Secretaria Acadêmica' (parent_id: 3) ---
    {
        "id": 9,
        "name": "sec_calendario",
        "selection_name": "2.1 - Calendário",
        "message": (
            "📅 *Calendário Acadêmico 2026*\n\n"
            "• Início das Aulas: 23/02/2026\n"
            "• Prazo Limite para Trancamento: 30/03/2026\n"
            "• Período de Avaliações Finais: 01/07 a 10/07/2026\n"
            "• Recesso Escolar: 15/07 a 01/08/2026\n\n"
            "Consulte as resoluções oficiais em: udesc.br/calendario"
        ),
        "parent_id": 3,
    },
    {
        "id": 10,
        "name": "sec_documentos",
        "selection_name": "2.2 - Documentos",
        "message": (
            "📄 *Solicitação de Documentos Acadêmicos*\n\n"
            "Selecione o documento que deseja solicitar ou consultar:"
        ),
        "parent_id": 3,
    },
    {
        "id": 11,
        "name": "sec_matricula",
        "selection_name": "2.3 - Matrícula",
        "message": (
            "📝 *Matrícula e Rematrícula Online*\n\n"
            "• A rematrícula é realizada semestralmente via SIGA (siga.udesc.br).\n"
            "• 1ª Etapa: Solicitação de turmas e disciplinas obrigatórias/optativas.\n"
            "• 2ª Etapa: Ajustes de horário e pedidos de quebra de pré-requisitos.\n"
            "Fique atento aos editais publicados pela Pró-Reitoria de Ensino (PROEN)!"
        ),
        "parent_id": 3,
    },

    # --- LEVEL 2: Sub-submenus of 'Solicitação de Documentos' (parent_id: 10) ---
    {
        "id": 12,
        "name": "doc_atestado",
        "selection_name": "2.2.1 - Atestado",
        "message": (
            "📑 *Atestado de Matrícula Instantâneo*\n\n"
            "Você pode gerar seu atestado oficial com assinatura digital autenticada:\n"
            "1. Acesse siga.udesc.br com seu CPF e senha institucional.\n"
            "2. No menu principal, clique em 'Documentos' > 'Atestado de Matrícula'.\n"
            "3. O PDF é emitido imediatamente com código verificador e QR Code."
        ),
        "parent_id": 10,
    },
    {
        "id": 13,
        "name": "doc_historico",
        "selection_name": "2.2.2 - Histórico",
        "message": (
            "📜 *Histórico Escolar*\n\n"
            "• Histórico Simples (para estágio/conferência): Emissão imediata pelo SIGA.\n"
            "• Histórico Oficial (com carimbo/formatura): Abra um requerimento online na secretaria com antecedência mínima de 3 dias úteis."
        ),
        "parent_id": 10,
    },
    {
        "id": 14,
        "name": "doc_trancamento",
        "selection_name": "2.2.3 - Trancamento",
        "message": (
            "⏸️ *Trancamento de Matrícula*\n\n"
            "• O trancamento deve ser solicitado até a data limite estipulada no calendário acadêmico.\n"
            "• O aluno pode usufruir de até 4 semestres de trancamento durante o curso.\n"
            "• Para solicitar, acesse 'Requerimentos Gerais' no SIGA e anexe a justificativa."
        ),
        "parent_id": 10,
    },

    # --- LEVEL 1: Submenus of 'Suporte e Tecnologia' (parent_id: 4) ---
    {
        "id": 15,
        "name": "sup_siga",
        "selection_name": "3.1 - Acesso ao SIGA",
        "message": (
            "🔑 *Acesso e Recuperação de Senha do SIGA*\n\n"
            "• Acesse siga.udesc.br e informe seu CPF no campo de usuário.\n"
            "• Caso tenha esquecido a senha, clique em 'Primeiro Acesso / Esqueci a Senha'.\n"
            "• As instruções serão enviadas para o e-mail cadastrado no vestibular.\n"
            "• Dificuldades adicionais? Envie documento com foto para suporte.ti@udesc.br"
        ),
        "parent_id": 4,
    },
    {
        "id": 16,
        "name": "sup_wifi",
        "selection_name": "3.2 - Wi-Fi Eduroam",
        "message": (
            "📶 *Configuração da Rede Eduroam (Wi-Fi)*\n\n"
            "1. Conecte-se à rede Wi-Fi 'eduroam' no seu celular ou computador.\n"
            "2. Identidade/Usuário: seu_cpf@udesc.br\n"
            "3. Senha: a mesma senha do seu ID UDESC / SIGA.\n"
            "4. Segurança EAP: PEAP | Autenticação fase 2: MSCHAPV2.\n"
            "5. Certificado CA: 'Não validar' ou 'Usar certificados do sistema'."
        ),
        "parent_id": 4,
    },
    {
        "id": 17,
        "name": "sup_labs",
        "selection_name": "3.3 - Laboratórios",
        "message": (
            "🖥️ *Laboratórios de Informática*\n\n"
            "• Localização: Bloco F (Salas F-101 a F-108).\n"
            "• Horário de Acesso: Segunda a Sexta, das 07h30 às 22h30.\n"
            "• Alunos regularmente matriculados possuem livre acesso nos horários sem aulas agendadas.\n"
            "• Para dúvidas de softwares ou licenças, consulte a monitoria na sala F-100."
        ),
        "parent_id": 4,
    },
]


def seed_menus(db_path: Path, reset: bool = False) -> None:
    """
    Seed the menus table with the initial hierarchical data.

    Args:
        db_path: Path to the SQLite database file (created if missing).
        reset: Wipe existing menus before seeding. History and sessions that referenced them
            are kept with the menu reference cleared.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(f"sqlite:///{db_path}")
    event.listen(engine, "connect", set_sqlite_pragma)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        count = session.exec(select(func.count()).select_from(Menu)).one()
        if count > 0:
            if not reset:
                print(f"[INFO] The 'menus' table already contains {count} records.")
                print("[INFO] Use '--reset' flag to wipe existing records and reseed.")
                return
            print(f"[RESET] Clearing existing {count} records from 'menus' table...")
            session.exec(delete(Menu))  # type: ignore
            session.commit()

        print(f"[SEEDING] Inserting {len(MENUS_DATA)} menu items into {db_path.name}...")
        session.add_all(Menu(**item) for item in MENUS_DATA)
        session.commit()

    engine.dispose()
    print("[SUCCESS] Seeding complete! Menu tree summary:")
    print_tree(MENUS_DATA)


def print_tree(data: Sequence[dict]) -> None:
    """Render a visual tree representation in terminal output."""
    by_parent: dict[int | None, list[dict]] = {}
    for item in data:
        by_parent.setdefault(item["parent_id"], []).append(item)

    def _render(parent_id: int | None, prefix: str = "") -> None:
        items = by_parent.get(parent_id, [])
        for i, item in enumerate(items):
            is_last = i == (len(items) - 1)
            connector = "└── " if is_last else "├── "
            print(f"{prefix}{connector}[ID {item['id']}] {item['selection_name']} (name: {item['name']})")
            next_prefix = prefix + ("    " if is_last else "│   ")
            _render(item["id"], next_prefix)

    _render(None)


def main(argv: Sequence[str] | None = None) -> None:
    """
    Command line entry point.

    Args:
        argv: Command line arguments; sys.argv is used when omitted.
    """
    parser = argparse.ArgumentParser(description="Seed chatbot menus database")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe existing menus before seeding",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DB_PATH,
        help=f"Path to SQLite database file (default: {DB_PATH})",
    )
    args = parser.parse_args(argv)
    seed_menus(db_path=args.db, reset=args.reset)


if __name__ == "__main__":
    main()
