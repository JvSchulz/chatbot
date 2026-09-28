#!/usr/bin/env python3
"""
Seed script for Chatbot menus table.
Populates the menus table with a realistic hierarchical menu structure for testing
navigation (depth 0, 1, and 2), button/section list responses, and LLM fallback context.

Usage:
    python3 scripts/seed_menus.py           # Seeds only if table is empty
    python3 scripts/seed_menus.py --reset   # Clears menus and reseeds from scratch
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "database.db"

MENUS_DATA = [
    # --- LEVEL 0: Root Menus (parent_id: None) ---
    {
        "id": 1,
        "name": "menu_cursos",
        "selection_name": "1 - Cursos de Graduação",
        "message": (
            "🎓 *Cursos de Graduação - UDESC*\n\n"
            "Selecione um dos cursos abaixo para ver detalhes, duração, turno e contatos da coordenação:"
        ),
        "parent_id": None,
    },
    {
        "id": 2,
        "name": "menu_secretaria",
        "selection_name": "2 - Secretaria Acadêmica",
        "message": (
            "📋 *Secretaria Acadêmica*\n\n"
            "Escolha um dos serviços abaixo para obter orientações, prazos e emissão de documentos:"
        ),
        "parent_id": None,
    },
    {
        "id": 3,
        "name": "menu_suporte",
        "selection_name": "3 - Suporte e Tecnologia",
        "message": (
            "💻 *Suporte de TI e Sistemas*\n\n"
            "Como podemos ajudar com os sistemas institucionais? Escolha uma opção:"
        ),
        "parent_id": None,
    },
    {
        "id": 4,
        "name": "menu_atendente",
        "selection_name": "4 - Falar com Atendente",
        "message": (
            "📞 *Atendimento Presencial e Contato*\n\n"
            "Nossa equipe atende de segunda a sexta-feira, das 08h às 20h.\n"
            "• E-mail: secretaria.cct@udesc.br\n"
            "• Telefone: (47) 3803-7200\n"
            "• Endereço: Campus Universitário Prof. Collaço, Bloco Central\n\n"
            "Caso prefira, digite sua dúvida em texto livre a qualquer momento para falar com nossa IA!"
        ),
        "parent_id": None,
    },

    # --- LEVEL 1: Submenus of 'Cursos de Graduação' (parent_id: 1) ---
    {
        "id": 5,
        "name": "curso_cc",
        "selection_name": "1.1 - Ciência da Computação",
        "message": (
            "💻 *Bacharelado em Ciência da Computação*\n\n"
            "• Duração: 4 anos (8 semestres)\n"
            "• Turno: Integral (matutino/vespertino)\n"
            "• Vagas: 40 por semestre\n"
            "• Coordenação: coord.dcc@udesc.br\n"
            "• Foco: Inteligência Artificial, Engenharia de Software e Algoritmos Avançados."
        ),
        "parent_id": 1,
    },
    {
        "id": 6,
        "name": "curso_si",
        "selection_name": "1.2 - Sistemas de Informação",
        "message": (
            "📊 *Bacharelado em Sistemas de Informação*\n\n"
            "• Duração: 4 anos (8 semestres)\n"
            "• Turno: Noturno\n"
            "• Vagas: 40 por semestre\n"
            "• Coordenação: coord.bsi@udesc.br\n"
            "• Foco: Governança de TI, Gestão de Negócios Digitais e Engenharia de Dados."
        ),
        "parent_id": 1,
    },
    {
        "id": 7,
        "name": "curso_ep",
        "selection_name": "1.3 - Engenharia de Produção",
        "message": (
            "⚙️ *Engenharia de Produção e Sistemas*\n\n"
            "• Duração: 5 anos (10 semestres)\n"
            "• Turno: Integral\n"
            "• Vagas: 35 por semestre\n"
            "• Coordenação: coord.eps@udesc.br\n"
            "• Foco: Gestão da Cadeia de Suprimentos, Logística, Qualidade e Processos Industriais."
        ),
        "parent_id": 1,
    },

    # --- LEVEL 1: Submenus of 'Secretaria Acadêmica' (parent_id: 2) ---
    {
        "id": 8,
        "name": "sec_calendario",
        "selection_name": "2.1 - Calendário Acadêmico",
        "message": (
            "📅 *Calendário Acadêmico 2026*\n\n"
            "• Início das Aulas: 23/02/2026\n"
            "• Prazo Limite para Trancamento: 30/03/2026\n"
            "• Período de Avaliações Finais: 01/07 a 10/07/2026\n"
            "• Recesso Escolar: 15/07 a 01/08/2026\n\n"
            "Consulte as resoluções oficiais em: udesc.br/calendario"
        ),
        "parent_id": 2,
    },
    {
        "id": 9,
        "name": "sec_documentos",
        "selection_name": "2.2 - Solicitação de Documentos",
        "message": (
            "📄 *Solicitação de Documentos Acadêmicos*\n\n"
            "Selecione o documento que deseja solicitar ou consultar:"
        ),
        "parent_id": 2,
    },
    {
        "id": 10,
        "name": "sec_matricula",
        "selection_name": "2.3 - Matrícula e Rematrícula",
        "message": (
            "📝 *Matrícula e Rematrícula Online*\n\n"
            "• A rematrícula é realizada semestralmente via SIGA (siga.udesc.br).\n"
            "• 1ª Etapa: Solicitação de turmas e disciplinas obrigatórias/optativas.\n"
            "• 2ª Etapa: Ajustes de horário e pedidos de quebra de pré-requisitos.\n"
            "Fique atento aos editais publicados pela Pró-Reitoria de Ensino (PROEN)!"
        ),
        "parent_id": 2,
    },

    # --- LEVEL 2: Sub-submenus of 'Solicitação de Documentos' (parent_id: 9) ---
    {
        "id": 11,
        "name": "doc_atestado",
        "selection_name": "2.2.1 - Atestado de Matrícula",
        "message": (
            "📑 *Atestado de Matrícula Instantâneo*\n\n"
            "Você pode gerar seu atestado oficial com assinatura digital autenticada:\n"
            "1. Acesse siga.udesc.br com seu CPF e senha institucional.\n"
            "2. No menu principal, clique em 'Documentos' > 'Atestado de Matrícula'.\n"
            "3. O PDF é emitido imediatamente com código verificador e QR Code."
        ),
        "parent_id": 9,
    },
    {
        "id": 12,
        "name": "doc_historico",
        "selection_name": "2.2.2 - Histórico Escolar",
        "message": (
            "📜 *Histórico Escolar*\n\n"
            "• Histórico Simples (para estágio/conferência): Emissão imediata pelo SIGA.\n"
            "• Histórico Oficial (com carimbo/formatura): Abra um requerimento online na secretaria com antecedência mínima de 3 dias úteis."
        ),
        "parent_id": 9,
    },
    {
        "id": 13,
        "name": "doc_trancamento",
        "selection_name": "2.2.3 - Trancamento de Matrícula",
        "message": (
            "⏸️ *Trancamento de Matrícula*\n\n"
            "• O trancamento deve ser solicitado até a data limite estipulada no calendário acadêmico.\n"
            "• O aluno pode usufruir de até 4 semestres de trancamento durante o curso.\n"
            "• Para solicitar, acesse 'Requerimentos Gerais' no SIGA e anexe a justificativa."
        ),
        "parent_id": 9,
    },

    # --- LEVEL 1: Submenus of 'Suporte e Tecnologia' (parent_id: 3) ---
    {
        "id": 14,
        "name": "sup_siga",
        "selection_name": "3.1 - Acesso ao SIGA",
        "message": (
            "🔑 *Acesso e Recuperação de Senha do SIGA*\n\n"
            "• Acesse siga.udesc.br e informe seu CPF no campo de usuário.\n"
            "• Caso tenha esquecido a senha, clique em 'Primeiro Acesso / Esqueci a Senha'.\n"
            "• As instruções serão enviadas para o e-mail cadastrado no vestibular.\n"
            "• Dificuldades adicionais? Envie documento com foto para suporte.ti@udesc.br"
        ),
        "parent_id": 3,
    },
    {
        "id": 15,
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
        "parent_id": 3,
    },
    {
        "id": 16,
        "name": "sup_labs",
        "selection_name": "3.3 - Laboratórios de Informática",
        "message": (
            "🖥️ *Laboratórios de Informática*\n\n"
            "• Localização: Bloco F (Salas F-101 a F-108).\n"
            "• Horário de Acesso: Segunda a Sexta, das 07h30 às 22h30.\n"
            "• Alunos regularmente matriculados possuem livre acesso nos horários sem aulas agendadas.\n"
            "• Para dúvidas de softwares ou licenças, consulte a monitoria na sala F-100."
        ),
        "parent_id": 3,
    },
]


def ensure_schema(conn: sqlite3.Connection):
    """Ensure the menus table exists matching the SQLModel Menu definition."""
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS menus (
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at DATETIME,
            name VARCHAR NOT NULL,
            selection_name VARCHAR NOT NULL,
            message VARCHAR NOT NULL,
            parent_id INTEGER,
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            FOREIGN KEY (parent_id) REFERENCES menus(id)
        );
        """
    )
    conn.commit()


def seed_menus(db_path: Path, reset: bool = False):
    """Seed the menus table with initial hierarchical data."""
    if not db_path.parent.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON;")
    ensure_schema(conn)

    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM menus;")
    count = cur.fetchone()[0]

    if count > 0:
        if not reset:
            print(f"[INFO] The 'menus' table already contains {count} records.")
            print("[INFO] Use '--reset' flag to wipe existing records and reseed.")
            conn.close()
            return
        print(f"[RESET] Clearing existing {count} records from 'menus' table...")
        conn.execute("PRAGMA foreign_keys=OFF;")
        cur.execute("DELETE FROM menus;")
        cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sqlite_sequence';")
        if cur.fetchone():
            cur.execute("DELETE FROM sqlite_sequence WHERE name='menus';")
        conn.commit()
        conn.execute("PRAGMA foreign_keys=ON;")

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    print(f"[SEEDING] Inserting {len(MENUS_DATA)} menu items into {db_path.name}...")
    for item in MENUS_DATA:
        cur.execute(
            """
            INSERT INTO menus (id, name, selection_name, message, parent_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                item["id"],
                item["name"],
                item["selection_name"],
                item["message"],
                item["parent_id"],
                now_iso,
                now_iso,
            ),
        )

    conn.commit()
    conn.close()

    print("[SUCCESS] Seeding complete! Menu tree summary:")
    print_tree(MENUS_DATA)


def print_tree(data):
    """Render a visual tree representation in terminal output."""
    by_parent = {}
    for item in data:
        p = item["parent_id"]
        by_parent.setdefault(p, []).append(item)

    def _render(parent_id, prefix=""):
        items = by_parent.get(parent_id, [])
        for i, item in enumerate(items):
            is_last = i == (len(items) - 1)
            connector = "└── " if is_last else "├── "
            print(f"{prefix}{connector}[ID {item['id']}] {item['selection_name']} (name: {item['name']})")
            next_prefix = prefix + ("    " if is_last else "│   ")
            _render(item["id"], next_prefix)

    _render(None)


def main():
    parser = argparse.ArgumentParser(description="Seed chatbot menus database")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe existing menus and reset auto-increment before seeding",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite database file (default: {DEFAULT_DB_PATH})",
    )
    args = parser.parse_args()
    seed_menus(db_path=args.db, reset=args.reset)


if __name__ == "__main__":
    main()
