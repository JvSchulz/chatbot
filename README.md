# Chatbot UDESC

Chatbot de atendimento no WhatsApp com navegação em menus hierárquicos configuráveis e painel web de administração.
O bot integra-se à WhatsApp Cloud API da Meta (via PyWa); o painel (FastAPI, Jinja2 e HTMX) gerencia menus,
usuários administradores e o histórico das conversas.

A especificação arquitetural completa está em [arquitetura.md](arquitetura.md).

## Principais recursos

- **Navegação hierárquica no WhatsApp:** menu raiz como contêiner de boas-vindas, até 9 submenus por nível (botões de resposta rápida para até 3 opções e listas interativas acima disso), ordenação natural sem diferenciar maiúsculas ou acentos e sessões identificadas por BSUID com expiração de 15 minutos.
- **Painel administrativo:** gestão de menus, gestão de usuários (restrita a administradores) e visualização paginada do histórico de conversas.
- **Segurança e confiabilidade:** senhas protegidas com Argon2id, cookies `HttpOnly` (`__Host-session` em HTTPS), proteção CSRF via cabeçalho `X-CSRF-Token`, limite de 5 tentativas de login por minuto por IP, política CSP restrita (sem `'unsafe-inline'`), validação de assinatura `X-Hub-Signature-256` nos webhooks, logs com dados pessoais mascarados e SQLite em modo WAL com uma transação por evento.

## Pré-requisitos

- Python 3.12
- Node.js (opcional, necessário apenas para a verificação estática de tipos com `pyright` via `npx`)
- Para atendimento real no WhatsApp: um número configurado na WhatsApp Cloud API da Meta e uma URL pública em HTTPS apontando para `/webhook`

## Instalação

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

`requirements.txt` contém apenas as dependências de execução; `requirements-dev.txt` adiciona as ferramentas de teste.
Todas as versões são fixadas para garantir instalações reproduzíveis.

## Configuração

Copie o modelo e preencha os valores. O arquivo `.env` não é versionado no git.

```bash
cp example_env .env
```

| Variável | Finalidade |
|---|---|
| `SECRET_KEY` | Chave utilizada para assinar os tokens CSRF do painel; use uma sequência longa e aleatória. |
| `WA_VERIFY_TOKEN` | Token de verificação do webhook; deve coincidir com o valor cadastrado no painel da Meta. |
| `APP_SECRET` | Segredo do aplicativo Meta, usado na validação da assinatura `X-Hub-Signature-256` de cada evento. |
| `WA_TOKEN` | Token de acesso permanente da WhatsApp Cloud API, usado para envio de mensagens. |
| `WA_PHONE_ID` | Identificador do número de telefone (Phone Number ID) na Meta. |
| `ADMIN_INITIAL_PASSWORD` | Senha inicial do primeiro administrador `admin` (mínimo de 12 caracteres); usada apenas quando não há usuários cadastrados. |

As cinco primeiras variáveis são sempre obrigatórias: a aplicação não inicia se alguma estiver ausente ou em branco e informa todas as pendências no erro. `ADMIN_INITIAL_PASSWORD` também é obrigatória na primeira inicialização (com o banco de usuários vazio).

## Banco de dados

O banco SQLite é armazenado em `database.db` na raiz do projeto (fora do git) e tem suas tabelas criadas automaticamente na primeira inicialização, com modo WAL e chaves estrangeiras ativados. Os menus são configurados pelo painel administrativo.

## Executando localmente

```bash
uvicorn main:app --reload
```

Acesse `http://127.0.0.1:8000`. Na primeira inicialização sem usuários no banco, a conta `admin` é criada com a senha definida em `ADMIN_INITIAL_PASSWORD`. O painel conta com três telas: **Menus**, **Usuários** (restrita a administradores) e **Histórico**.

Para receber mensagens reais, cadastre manualmente `https://<seu-domínio>/webhook` no painel da Meta (*WhatsApp > Configuração > Webhook*), informe o mesmo `WA_VERIFY_TOKEN` e assine o campo `messages`. A documentação interativa do FastAPI (`/docs`) permanece desabilitada por segurança.

### Simulando eventos localmente

O script `scripts/send_mock_webhook.py` envia ao servidor local eventos no formato da Meta assinados com `APP_SECRET`, mantendo a validação de assinatura ativa. As respostas de saída continuam sendo enviadas para a API da Meta: utilize um número de teste autorizado; em caso de falha no envio, o erro é registrado nos logs e apenas a mensagem recebida do usuário é gravada no histórico.

```bash
python -m scripts.send_mock_webhook --text "Olá"
python -m scripts.send_mock_webhook --button "menu:2" --url http://127.0.0.1:8000/webhook
python -m scripts.send_mock_webhook --text "Oi" --wa-id 554798765432
```

## Implantação

Os arquivos de produção e o roteiro passo a passo de implantação em VPS estão em [`deploy/`](deploy/README.md), incluindo:

- Proxy reverso com HTTPS automático via Caddy (`deploy/Caddyfile`)
- Serviço gerenciado pelo `systemd` (`deploy/chatbot.service`)
- Rotina de backup diário compatível com SQLite WAL e retenção de 14 dias (`deploy/backup-db.sh`)

Em produção, a aplicação deve ser executada com **um único worker** do Uvicorn (`--workers 1`), pois a deduplicação de eventos da PyWa ocorre em memória no processo e o SQLite opera com um único escritor por vez.

## Qualidade e testes

Execute os comandos a partir da raiz do projeto com o ambiente virtual ativo:

```bash
python -m pytest tests -q
python -m pytest --cov=src --cov-fail-under=95 tests/
npx pyright src main.py tests scripts
```

O projeto também conta com configuração para testes de mutação com `mutmut` em `setup.cfg` (meta acima de 85% de mutantes detectados).

## Estrutura do projeto

| Caminho | Conteúdo |
|---|---|
| `main.py` | Ponto de entrada da aplicação: roteadores, middlewares, handlers de exceção e cliente PyWa. |
| `src/core/` | Configuração (`config.py`), acesso ao banco (`db.py`), segurança e middlewares (`security.py`, `middleware.py`). |
| `src/models/` | Entidades SQLModel: `Menu`, `User`, `AdminSession`, `UserSession` e `ChatHistory`. |
| `src/services/` | Regras de negócio: menus, usuários, sessões e, em `webhook/`, tratamento de eventos e histórico. |
| `src/controllers/` | Rotas HTTP: autenticação, menus, usuários, histórico e webhook. |
| `src/views/` | Templates Jinja2 (`templates/`) e arquivos estáticos (`htmx.min.js`, `app.js`, `style.css` e logotipo). |
| `scripts/` | Simulador local de eventos de webhook (`send_mock_webhook.py`). |
| `deploy/` | Arquivos e guia de implantação em VPS (`Caddyfile`, `chatbot.service`, `backup-db.sh` e `deploy/README.md`). |
| `tests/` | Suítes de testes unitários, de integração e ponta a ponta. |
| `example_env` | Modelo do arquivo `.env`. |

## Licença

Distribuído sob a [PolyForm Noncommercial License 1.0.0](LICENSE). O código pode ser compartilhado, estudado e modificado gratuitamente para fins acadêmicos, educacionais ou pessoais sem fins lucrativos. É proibida a venda ou o uso comercial do software como produto ou serviço para geração de receita.
