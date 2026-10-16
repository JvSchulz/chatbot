# Chatbot UDESC

Chatbot de atendimento no WhatsApp, com menus hierárquicos configuráveis e um painel web de administração.
O bot responde pela WhatsApp Cloud API (biblioteca PyWa); o painel (FastAPI, Jinja2 e HTMX) gerencia menus,
usuários administradores e mostra o histórico das conversas.

O desenho completo está em [arquitetura.md](arquitetura.md).

## Pré-requisitos

- Python 3.12
- Node.js (só para rodar o `pyright` via `npx` nas verificações de qualidade)
- Para receber mensagens reais: um número na WhatsApp Cloud API da Meta e uma URL pública HTTPS apontando
  para `/webhook`

## Instalação

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

`requirements.txt` traz só as dependências de execução; `requirements-dev.txt` acrescenta as de teste.
Todas as versões são fixas para que a instalação seja reproduzível.

## Configuração

Copie o modelo e preencha os valores. O arquivo `.env` fica fora do git.

```bash
cp example_env .env
```

| Variável | Para que serve |
|---|---|
| `SECRET_KEY` | Chave que assina os tokens CSRF do painel; use uma sequência longa e aleatória. |
| `WA_VERIFY_TOKEN` | Token de verificação do webhook; deve ser idêntico ao cadastrado no painel da Meta. |
| `APP_SECRET` | Segredo do aplicativo Meta, usado para validar a assinatura `X-Hub-Signature-256` de cada evento. |
| `WA_TOKEN` | Token de acesso permanente da API, usado para enviar mensagens. |
| `WA_PHONE_ID` | Identificador do número de telefone (Phone Number ID). |
| `ADMIN_INITIAL_PASSWORD` | Senha (mínimo de 12 caracteres) do primeiro administrador `admin`; lida só com o banco sem usuários. |

Todas, exceto `ADMIN_INITIAL_PASSWORD`, são obrigatórias: a aplicação não inicia com alguma ausente ou em branco
e o erro lista todas as que faltam.

## Banco de dados

O SQLite fica em `database.db` na raiz do projeto (fora do git). As tabelas são criadas na primeira
inicialização. Um `database.db` criado antes da remoção do modo de atendimento tem a coluna `mode`
em `user_sessions` e falha ao gravar sessões: apague o arquivo (e `database.db-wal` e `database.db-shm`) e
recrie os menus. Para popular os menus com uma árvore de exemplo:

```bash
python -m scripts.seed_menus           # só se ainda não houver menus
python -m scripts.seed_menus --reset   # apaga os menus e recria a árvore
```

## Executando

```bash
uvicorn main:app --reload
```

Abra `http://127.0.0.1:8000`. No primeiro início, com o banco sem usuários, o administrador `admin` é criado
com a senha de `ADMIN_INITIAL_PASSWORD`. O painel tem três telas: Menus, Usuários (só para administradores)
e Histórico.

Para receber mensagens reais, cadastre `https://<seu-domínio>/webhook` no painel da Meta (WhatsApp, Configuração,
Webhook), informe o mesmo `WA_VERIFY_TOKEN` e assine o campo `messages`. A aplicação não registra o webhook
sozinha. A documentação interativa do FastAPI (`/docs`) fica desligada.

### Simulando eventos sem a Meta

`scripts/send_mock_webhook.py` envia ao servidor local um evento no formato da Meta, assinado com `APP_SECRET`
exatamente como a Meta faz, então a validação de assinatura continua ligada. As respostas continuam saindo pela
API real, portanto use um número de teste ou aceite o erro de envio nos logs; as linhas do histórico são gravadas
de qualquer forma.

```bash
python -m scripts.send_mock_webhook --text "Olá"
python -m scripts.send_mock_webhook --button "menu:2" --url http://127.0.0.1:8000/webhook
python -m scripts.send_mock_webhook --text "Oi" --wa-id 554798765432
```

## Qualidade

Todos os comandos rodam a partir da raiz do projeto, com o ambiente virtual ativo.

```bash
python -m pytest tests -q                                      # 100% dos testes devem passar
python -m pytest --cov=src --cov-fail-under=95 tests/          # cobertura mínima de 95%
npx pyright src main.py tests scripts                          # 0 erros e 0 avisos
```

Teste de mutação com `mutmut`: aponte `source_paths` em `setup.cfg` para os arquivos a mutar, apague a pasta
`mutants` (o mutmut guarda resultados e não percebe mudanças só nos testes) e rode:

```bash
rm -rf mutants
mutmut run
mutmut results
```

A meta é uma taxa de mortes acima de 85%.

## Mapa de pastas

| Caminho | Conteúdo |
|---|---|
| `main.py` | Montagem da aplicação: roteadores, middlewares, tratadores de erro e o cliente PyWa. |
| `src/core/` | Configuração (`config.py`), banco (`db.py`), segurança e middlewares (`security.py`, `middleware.py`). |
| `src/models/` | Entidades SQLModel: `Menu`, `User`, `AdminSession`, `UserSession` e `ChatHistory`. |
| `src/services/` | Regras de negócio: menus, usuários, sessões do bot e, em `webhook/`, o tratamento dos eventos e o histórico. |
| `src/controllers/` | Rotas HTTP: autenticação, menus, usuários, histórico e webhook. |
| `src/views/` | Templates Jinja2 (`templates/`) e arquivos estáticos: `htmx.min.js`, `app.js`, `style.css` e a logo. |
| `scripts/` | Migração do banco, carga de menus de exemplo e simulador de webhook. |
| `tests/` | Testes unitários, de integração e ponta a ponta. |
| `example_env` | Modelo do arquivo `.env`. |

## Convenções

- Identificadores em inglês; comentários e docstrings em português, no formato `Args:` / `Returns:`.
- Textos exibidos ao usuário em português.
- No máximo três parâmetros por função de serviço; nenhum comentário de código morto ou de metadados.
