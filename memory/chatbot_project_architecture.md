# Chatbot Project Architecture and State

## Project Overview

- **Location:** `~/code/codespace/chatbot` (`/home/rhyno/code/codespace/chatbot`)
- **Type:** Hybrid Chatbot System (Hierarchical Structured Menus + Conversational LLM)
- **Primary Design Doc:** `chatbot/arquitetura llm.md`

## Tech Stack

- **Backend / API:** Python, FastAPI (`app.py`)
- **Database / ORM:** SQLite, SQLModel (`src/core/db.py`)
- **Frontend / Admin UI:** Jinja2 templates + HTMX (`src/views/templates/index.html`)
- **LLM Provider:** Local Ollama (mini model with guardrails for conversational queries)
- **Messaging Channels:**
  - Telegram (`InlineKeyboardMarkup`)
  - WhatsApp (interactive list/button messages)

## Core Entities & Models

1. **Menu:**
   - Fields: `id`, `nome`, `nome_selecao`, `mensagem`, `id_pai` (self-referencing FK), `submenus`, `menu_pai`.
   - Logic: Root menus have `id_pai == None`. Selecting a menu displays its message and lists child menus (`id_pai == id_selecionado`).
2. **Usuario (Admin):**
   - Fields: `id`, `username`, `password_hash`, `is_master`, `is_active`.
   - Used for authentication on the web admin dashboard for CRUD operations on menus and users.
3. **HistoricoConversa (Analytics & Operations):**
   - Fields: `id`, `canal` (telegram/whatsapp), `id_usuario_canal`, `remetente`, `conteudo`, `id_menu_acessado`, `timestamp`.

## Architecture Flow

- User interacts via Telegram/WhatsApp -> API handles navigation through Menu nodes.
- When user enters free-form text -> API sends prompt + menu context to Ollama LLM to generate a grounded response.
- Admins log into HTMX dashboard to manage menus, inspect conversation logs, and administer users.

## Current Codebase State

- `app.py`: FastAPI entrypoint.
- `requirements.txt`: Dependencies (`fastapi`, `uvicorn`, `sqlmodel`, `jinja2`, etc.).
- `src/core/db.py`: Database engine & session setup.
- `src/views/templates/index.html`: Admin dashboard layout.
- `arquitetura llm.md`: Authoritative specification and Mermaid diagrams.
