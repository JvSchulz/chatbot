# Implantação no VPS

Este guia permite refazer a implantação do zero, entender o que está no servidor e desfazer tudo
se preciso. Nenhum segredo fica aqui: os valores ficam apenas em `/opt/chatbot/.env`, no servidor.
Nos exemplos abaixo, substitua `chatbot.example.com`, `example.com` e `<IP_DO_VPS>` pelos dados do
seu ambiente.

## Como funciona

```text
Usuário no WhatsApp -> Meta -> https://chatbot.example.com/webhook
                                 |
                                 | o DNS traduz o nome para <IP_DO_VPS>
                                 v
                      VPS: Caddy, porta 443 (HTTPS e certificado)
                                 |
                                 v
                      VPS: aplicação, 127.0.0.1:8000 (só o próprio servidor alcança)
                                 |
                                 v
                      /opt/chatbot/database.db (SQLite)
```

| Peça | O que faz | Por que é necessária |
|---|---|---|
| Registro DNS `chatbot` | Aponta o nome para o IP do VPS | A Meta precisa de um nome com certificado válido, não de um IP |
| Caddy | Atende o HTTPS, renova o certificado sozinho e repassa as requisições à aplicação | A Meta só aceita webhook em HTTPS, e o uso da porta 443 com TLS-ALPN-01 evita conflito caso a porta 80 já esteja em uso |
| Let's Encrypt | Emite o certificado gratuito | O Caddy o solicita e renova sem intervenção |
| Serviço `chatbot` (systemd) | Mantém a aplicação rodando e a reinicia em falhas e no boot | Sem ele, a aplicação pararia ao fechar o SSH |
| `.env` | Guarda os segredos e as credenciais da Meta | Fica fora do git |
| Backup diário (cron) | Copia o banco toda madrugada | Protege o banco contra erro humano sem depender de snapshots externos |

## Cuidados em um servidor compartilhado

Se o VPS já hospedar outros sites ou serviços, a implantação não deve interferir neles:

- **Porta 80 e serviços existentes:** confira quais portas já estão escutando (`ss -tlnp`) e nunca as ocupe nem as bloqueie. O `Caddyfile` deste projeto usa apenas a porta 443 (TLS-ALPN-01) para não disputar a porta 80.
- **Firewall:** não aplique regras restritivas sem antes mapear todas as portas usadas pelos serviços já presentes no servidor.
- **`apt upgrade`:** evite executar atualizações globais sem validar antes se há serviços legados dependentes das versões atuais dos pacotes.
- **Docker:** em contêineres OpenVZ ou ambientes sem virtualização aninhada, o Docker costuma não funcionar; por isso este guia instala a aplicação diretamente via `systemd` e `uv`.
- **DNS:** altere apenas o registro do subdomínio do chatbot (`chatbot`), preservando os demais registros da zona (como `MX`, e-mail e o domínio raiz).

## O que existe no servidor

| Caminho | Conteúdo |
|---|---|
| `/opt/chatbot/` | Código, ambiente Python (`.venv`), `.env` e `database.db` |
| `/opt/uv-python/` | Python 3.12, sem alterar o Python do sistema |
| `/usr/local/bin/uv`, `uvx` | Instalador do Python e dos pacotes |
| `/etc/systemd/system/chatbot.service` | Serviço da aplicação |
| `/etc/caddy/Caddyfile` | Configuração do Caddy |
| `/etc/apt/sources.list.d/caddy-stable.list` e `/usr/share/keyrings/caddy-stable-archive-keyring.gpg` | Origem do pacote do Caddy |
| `/var/lib/caddy/` | Certificado e conta do Let's Encrypt |
| `/etc/cron.d/chatbot-backup` e `/var/backups/chatbot/` | Agendamento e cópias do banco |
| `/root/antes-chatbot-*.txt` | Estado das portas e do serviço HTTP antes da implantação |

Pacotes instalados pelo `apt`: `caddy` e `sqlite3`. Usuário criado: `chatbot`, sem login.

## Implantação do zero

Os comandos rodam como `root` no VPS, salvo indicação. Execute um bloco por vez e confira o
resultado antes de seguir.

### 1. DNS

No painel do seu provedor de DNS, abra a zona de `example.com` e adicione uma entrada:

| Tipo de Entrada | Nome / Host / Alias | Conteúdo / Valor / Aponta para |
|---|---|---|
| `A` | `chatbot` | `<IP_DO_VPS>` |

Não crie registro `AAAA` se o VPS não tiver IPv6 configurado. Para conferir, em qualquer máquina com `dig`:

```bash
dig +short A chatbot.example.com @1.1.1.1
```

### 2. Estado inicial

Registre o estado inicial das portas e de eventual serviço na porta 80 para comparar no final:

```bash
ss -tlnp > /root/antes-chatbot-portas.txt
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:80/ | tee /root/antes-chatbot-site.txt
```

### 3. Aplicação

```bash
apt update
apt install --simulate sqlite3
```

Confira as linhas `Inst`: devem aparecer só `sqlite3` e, no máximo, `libsqlite3-0`. Depois:

```bash
apt install --yes sqlite3
curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
useradd --system --home-dir /opt/chatbot --shell /usr/sbin/nologin chatbot
git clone https://github.com/JvSchulz/chatbot.git /opt/chatbot
cd /opt/chatbot
UV_PYTHON_INSTALL_DIR=/opt/uv-python uv python install 3.12
UV_PYTHON_INSTALL_DIR=/opt/uv-python uv venv -p 3.12 .venv
VIRTUAL_ENV=/opt/chatbot/.venv uv pip install -r requirements.txt
```

### 4. Segredos

Na **sua máquina** (a partir da raiz do projeto), envie o `.env` que já tem as credenciais da Meta. Cole em uma única linha:

```bash
scp ./.env root@<IP_DO_VPS>:/opt/chatbot/.env
```

Se não houver um `.env` local, copie `example_env` para `.env` no VPS e preencha `WA_TOKEN`,
`WA_PHONE_ID` e `APP_SECRET` com os valores do aplicativo da Meta.

No **VPS**, gere valores próprios para os outros segredos e proteja o arquivo:

```bash
cd /opt/chatbot
for k in SECRET_KEY WA_VERIFY_TOKEN ADMIN_INITIAL_PASSWORD; do sed -i "s|^$k=.*|$k=$(openssl rand -hex 32)|" .env; done
chown -R chatbot:chatbot /opt/chatbot
chmod 600 .env
```

Nunca carregue o `.env` no shell: variáveis exportadas têm prioridade sobre o arquivo.

### 5. Iniciar a aplicação

```bash
cd /opt/chatbot
cp deploy/chatbot.service /etc/systemd/system/chatbot.service
systemctl daemon-reload
systemctl enable --now chatbot
sleep 15
systemctl is-active chatbot
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/login
```

O resultado esperado é `active` e `200`. A aplicação leva cerca de 7 segundos para iniciar.

### 6. Caddy

O DNS do passo 1 precisa estar ativo. Copie o `Caddyfile` antes de instalar o pacote e substitua
`chatbot.example.com` pelo seu domínio real, porque a configuração padrão do Caddy tenta usar a
porta 80:

```bash
command -v gpg || apt install --yes gnupg
mkdir -p /etc/caddy
cp /opt/chatbot/deploy/Caddyfile /etc/caddy/Caddyfile
# Edite /etc/caddy/Caddyfile e substitua chatbot.example.com pelo domínio real antes de instalar.
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
apt update
apt install --simulate caddy
```

Confira as linhas `Inst`: deve aparecer só `caddy`. Depois:

```bash
apt install --yes -o Dpkg::Options::=--force-confold caddy
sleep 45
journalctl -u caddy --since "-2min" --no-pager -o cat | grep -E 'certificate obtained|challenge failed|"level":"error"' | cut -c1-300
```

O esperado é uma linha `certificate obtained`. Se não aparecer, veja "Problemas conhecidos".

### 7. Verificação

```bash
curl -s -m 15 -o /dev/null -w '%{http_code}\n' https://chatbot.example.com/login
ss -tlnp | diff /root/antes-chatbot-portas.txt -
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:80/
```

- O `/login` deve responder `200`.
- O `diff` deve mostrar só as novidades: `443`, `8000` e `127.0.0.1:2019` (administração interna
  do Caddy). Os números de processo também podem mudar.
- Se já havia um serviço na porta 80, ele deve responder o mesmo código salvo em
  `/root/antes-chatbot-site.txt`.
- Outros domínios que operam apenas em `http://` no mesmo servidor continuam acessíveis em `http://`.

### 8. Meta

Leia o token de verificação no servidor, sem colá-lo em conversas ou documentos:

```bash
grep '^WA_VERIFY_TOKEN=' /opt/chatbot/.env
```

No painel da Meta, em WhatsApp > Configuração:

1. URL de retorno: `https://chatbot.example.com/webhook`.
2. Token de verificação: o valor lido acima.
3. Assine o campo `messages`.

O aplicativo aceita só uma URL, então isso desconecta qualquer túnel de teste. Envie "Oi" pelo
telefone, confira a resposta e veja a mensagem na tela de Histórico.

### 9. Painel

Abra `https://chatbot.example.com/login` com o usuário `admin` e a senha lida com:

```bash
grep '^ADMIN_INITIAL_PASSWORD=' /opt/chatbot/.env
```

### 10. Backups

```bash
systemctl is-active cron
install -d -o chatbot -g chatbot -m 700 /var/backups/chatbot
echo '30 3 * * * chatbot /bin/sh /opt/chatbot/deploy/backup-db.sh' > /etc/cron.d/chatbot-backup
runuser -u chatbot -- /bin/sh /opt/chatbot/deploy/backup-db.sh
ls -l /var/backups/chatbot
```

As cópias ficam no próprio VPS por 14 dias: protegem contra erro humano, não contra a perda do
servidor. O banco guarda telefones e mensagens, então defina com cuidado qualquer destino externo.

## Uso no dia a dia

| Para | Comando |
|---|---|
| Ver se está tudo no ar | `systemctl is-active chatbot caddy` |
| Logs da aplicação | `journalctl -u chatbot -n 50 --no-pager` |
| Logs do Caddy | `journalctl -u caddy -n 50 --no-pager` |
| Acompanhar ao vivo | `journalctl -u chatbot -f` (Ctrl+C para sair) |
| Reiniciar a aplicação (também após mudar o `.env`) | `systemctl restart chatbot` |
| Aplicar mudança no Caddyfile | `systemctl reload caddy` |

### Atualizar a aplicação

```bash
cd /opt/chatbot
runuser -u chatbot -- git pull --ff-only
VIRTUAL_ENV=/opt/chatbot/.venv uv pip install -r requirements.txt
chown -R chatbot:chatbot /opt/chatbot
systemctl restart chatbot
```

Não há migrações: `create_all` não altera tabelas existentes, então mudanças de esquema precisam
de um plano próprio. Faça um backup antes.

### Restaurar um backup

Substitua a data pela da cópia desejada. Isso descarta o que foi gravado depois dela:

```bash
systemctl stop chatbot
cd /opt/chatbot
rm -f database.db-wal database.db-shm
gzip -dc /var/backups/chatbot/db-2026-01-31.sqlite.gz > database.db
chown chatbot:chatbot database.db
systemctl start chatbot
```

## Problemas conhecidos

| Sintoma | Causa | O que fazer |
|---|---|---|
| `curl` em `/login` mostra `000` logo após iniciar | A aplicação ainda está subindo (cerca de 7 s) | Aguarde 15 s e repita |
| `E: Unable to locate package caddy` | A origem do pacote ainda não foi configurada | Rode o primeiro bloco do passo 6 antes |
| `scp` mostra só o texto de uso | O comando foi quebrado em duas linhas ao colar | Cole em uma única linha |
| `archive.canonical.com` falha no `apt update` | Origem antiga do servidor, sem relação com o Caddy | Ignore |
| `failed to set GOMAXPROCS` no log do Caddy | Limitação do contêiner OpenVZ | Ignore |
| `creating new account` no log do Caddy, com erro `no such file` | Primeira execução, a conta ainda não existe | Ignore |
| `curl -I` em `/login` mostra `405` | `-I` envia `HEAD`, e a rota aceita só `GET`. O HTTPS está funcionando | Teste sem `-I`. Em monitores de disponibilidade, use `GET` |
| `tlsv1 alert internal error` em `https://chatbot...` | O Caddy ainda não tem certificado | Veja o log do Caddy e as linhas abaixo |
| `DNS problem: query timed out` no log do Caddy | Uma das verificações do Let's Encrypt não obteve resposta do DNS | Aguarde e veja a linha abaixo |
| Log mostra `acme-staging-v02` com `connection reset` ou tempo esgotado | Depois de uma falha, o Caddy repete pelo servidor de testes do Let's Encrypt, que pode estar fora do ar. Consulte <https://letsencrypt.status.io> | `systemctl restart caddy` volta a tentar pelo servidor principal. Aguarde 15 min entre reinícios: o limite é de 5 falhas por hora |
| Webhook responde 403 com o `APP_SECRET` correto | Variável antiga exportada no ambiente tem prioridade sobre o `.env` | Não use `export`; reinicie pelo `systemctl` |
| Nenhuma resposta no WhatsApp e nenhum erro | `WA_PHONE_ID` diferente do número: a PyWa descarta o evento em silêncio | Confira o valor na Meta e reinicie |

## Desfazer a implantação

Exporte o banco antes se o histórico importar: estes comandos o apagam. Nenhum deles altera outros
serviços já existentes no servidor.

```bash
systemctl disable --now caddy chatbot
apt remove --purge --yes caddy
rm -f /etc/apt/sources.list.d/caddy-stable.list /usr/share/keyrings/caddy-stable-archive-keyring.gpg
rm -f /etc/systemd/system/chatbot.service /etc/cron.d/chatbot-backup
systemctl daemon-reload
rm -rf /opt/chatbot /opt/uv-python /var/backups/chatbot /var/lib/caddy /etc/caddy
rm -f /usr/local/bin/uv /usr/local/bin/uvx
userdel chatbot
```

Depois, apague a entrada `chatbot` no painel do seu provedor de DNS e retire a URL de retorno na
Meta. O pacote `sqlite3` pode permanecer, pois é inofensivo.
