## Arquitetura - Overview

A aplicação consiste em um sistema de chatbot híbrido que combina navegação estruturada via menus hierárquicos e atendimento conversacional alimentado por um modelo de linguagem (LLM).

O sistema expõe interfaces de atendimento para plataformas de mensageria (Telegram e WhatsApp), integra-se a um provedor local de LLM (Ollama) com acesso ao contexto dos menus e disponibiliza um painel administrativo web com autenticação para gestão das estruturas de menus e histórico. A hospedagem é projetada para ambientes em nuvem, VPS ou infraestrutura auto-hospedada (self-hosted).
## Stack

- **Linguagem / Backend:** Python
    
- **Framework Web / API:** FastAPI
    
- **ORM:** SQLModel
    
- **Banco de Dados:** SQLite
    
- **Frontend:** HTMX e Jinja2
    
- **Provedor LLM:** Ollama (modelo de porte reduzido/mini com guardrails)
    
- **Canais de Mensageria:** Telegram (`InlineKeyboardMarkup`) e WhatsApp
## Regras de Negócio e Funcionalidades

### 1. Atendimento e Navegação (Chatbot)

- **Inicialização:** A sessão inicia exibindo o menu raiz (onde `id_pai` é nulo) ou é acionada por comando do usuário.
    
- **Navegação em Menus:** Ao selecionar um item, o sistema recupera a mensagem correspondente e lista as opções filhas imediatas vinculadas àquele menu (`id_pai == id_selecionado`).
    
- **Transição Conversacional:** O fluxo disponibiliza a opção para o envio de mensagens de texto livre. A entrada é encaminhada ao modelo LLM para gerar uma resposta conversacional fundamentada nas informações dos menus.
    
- **Renderização de Interface:** No Telegram, a interação é realizada via teclados interativos inline (`keyboard_inline`). O WhatsApp opera sob mecânica análoga de mensagens interativas.
### 2. Painel Administrativo (Frontend / Web Service)

- **Autenticação:** Mecanismo de autenticação de administradores, prevendo perfil de administrador principal (master) e controle de criação/remoção de novos usuários.
    
- **Gestão de Menus (CRUD):** Interface para listagem, criação, edição e exclusão de itens de menu.
    
- **Vínculo Hierárquico:** O formulário de cadastro/edição contém um campo de seleção simples para definir o menu pai (`id_pai`), estabelecendo auto-relacionamento de forma direta.
### 3. Persistência e Dados

- **Armazenamento de Estrutura:** Persistência relacional dos nós de menu e seus apontamentos hierárquicos.
    
- **Armazenamento de Sessões e Mensagens:** Registro de identificadores de conversas e histórico de mensagens para fins operacionais e de análise (analytics).
## Diagrama de Fluxo de Dados (DFD)

```Snippet de código
flowchart LR
    subgraph Entidades["Entidades Externas"]
        U[Usuário]
        A[Admin]
        LLM[LLM / Ollama]
    end

    subgraph Processo["Processamento Central"]
        API((API / Web Service))
    end

    subgraph Armazenamento["Bases de Dados / Conhecimento"]
        DB_HIST[(Histórico de Conversas)]
        DB_MENU[(Menus)]
        DB_USER[(Usuários)]
        KB[(Conhecimento de Processos)]
    end

    %% Fluxos do Usuário
    U -->|Mensagens e seleções| API
    API -->|Respostas e menus interativos| U

    %% Fluxos do Admin
    A -->|Credenciais e gestão de menus/usuários| API
    API -->|Interfaces HTML / confirmações| A

    %% Acessos a dados
    API <-->|Leitura e escrita de histórico| DB_HIST
    API <-->|Leitura e escrita de menus| DB_MENU
    API <-->|Autenticação e gestão| DB_USER

    %% Integração LLM
    API -->|Prompt e contexto do menu| LLM
    LLM -->|Resposta gerada| API
    LLM --- KB
```
## Diagramas de Classes

### Classe Menu

Representa a árvore hierárquica de menus e mensagens estáticas.

```Snippet de código
classDiagram
    class Menu {
        +int id
        +string nome
        +string nome_selecao
        +string mensagem
        +int? id_pai
        +List~Menu~ submenus
        +Menu? menu_pai
    }
    Menu "0..1" <-- "0..*" Menu : id_pai
```
### Classe Usuário (Administrador)

Representa os registros de credenciais e permissões para acesso ao painel administrativo.

```Snippet de código
classDiagram
    class Usuario {
        +int id
        +string username
        +string password_hash
        +bool is_master
        +bool is_active
    }
```
### Classe Histórico de Mensagens

Representa o registro das conversas, mensagens trocadas e sessões dos usuários nos canais de atendimento.

```Snippet de código 
classDiagram 
    class HistoricoConversa {
        +int id
        +string canal
        +string id_usuario_canal
        +string remetente
        +string conteudo
        +int? id_menu_acessado
        +datetime timestamp
    }
```

![[External Entity Processing-2026-08-24-155043.png]]

![[External Entity Processing-2026-08-24-155151.png]]

![[External Entity Processing-2026-08-24-155205.png]]

![[External Entity Processing-2026-08-24-155245.png]]