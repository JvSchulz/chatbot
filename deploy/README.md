# Implantação no VPS

Roda ao lado do site do dono do VPS, sem alterá-lo: o Node continua na porta 80, o Caddy atende
só a 443 e o uvicorn fica em `127.0.0.1:8000`. Não aplique um firewall restritivo neste servidor:
ele cortaria as portas 5000, 8080 e 8081 do dono.

Todos os comandos rodam como `root` no VPS, salvo indicação.

## 1. DNS

No painel da Locaweb, crie apenas o registro `A chatbot -> 62.4.16.72`, sem `AAAA` (o VPS não tem
IPv6). Não altere os registros existentes. Confirme na sua máquina antes de continuar:

```bash
dig +short A chatbot.lucianaritaguedes.com.br @1.1.1.1
```

## 2. Estado inicial

O plano do VPS não inclui backups, então registre o estado do site para comparar no final:

```bash
ss -tlnp > /root/antes-chatbot-portas.txt
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:80/ | tee /root/antes-chatbot-site.txt
```

## 3. Aplicação

```bash
apt update && apt install --yes sqlite3
curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
useradd --system --home-dir /opt/chatbot --shell /usr/sbin/nologin chatbot
git clone https://github.com/JvSchulz/chatbot.git /opt/chatbot
cd /opt/chatbot
UV_PYTHON_INSTALL_DIR=/opt/uv-python uv python install 3.12
UV_PYTHON_INSTALL_DIR=/opt/uv-python uv venv -p 3.12 .venv
VIRTUAL_ENV=/opt/chatbot/.venv uv pip install -r requirements.txt
cp example_env .env
chmod 600 .env
nano .env
chown -R chatbot:chatbot /opt/chatbot
```

No `.env`, use valores novos e longos em `SECRET_KEY`, `WA_VERIFY_TOKEN` e
`ADMIN_INITIAL_PASSWORD` (`openssl rand -base64 32` gera um por vez). Os demais vêm do aplicativo
da Meta. Nunca carregue esse arquivo no shell: variáveis exportadas têm prioridade sobre ele.

Crie os menus de exemplo, somente com o banco vazio, e inicie o serviço:

```bash
cd /opt/chatbot
runuser -u chatbot -- .venv/bin/python -m scripts.seed_menus
cp deploy/chatbot.service /etc/systemd/system/chatbot.service
systemctl daemon-reload
systemctl enable --now chatbot
systemctl is-active chatbot
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/login
```

O último comando deve mostrar `200`.

## 4. Caddy

O Caddyfile entra antes do pacote porque a configuração padrão do Caddy usa a porta 80:

```bash
mkdir -p /etc/caddy
cp /opt/chatbot/deploy/Caddyfile /etc/caddy/Caddyfile
apt install --yes debian-keyring debian-archive-keyring apt-transport-https curl gnupg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
apt update
apt install --yes -o Dpkg::Options::=--force-confold caddy
systemctl is-active caddy
journalctl -u caddy -n 30 --no-pager
```

## 5. Verificação

```bash
curl -sI https://chatbot.lucianaritaguedes.com.br/login | head -1
ss -tlnp | diff /root/antes-chatbot-portas.txt -
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:80/
for host in lucianaritaguedes.com.br pacman.lucianaritaguedes.com.br obiexplorer.lucianaritaguedes.com.br; do
  curl -s -o /dev/null -w "$host %{http_code}\n" "http://$host/"
done
```

O `/login` deve responder `200`. O `diff` deve mostrar só as portas novas 443 e 8000 (além de
portas internas do Caddy em `127.0.0.1`), e o site deve responder o mesmo código de antes. Os
outros nomes continuam só em `http://`: em `https://` eles passam a dar erro de certificado.

## 6. Meta

Em WhatsApp > Configuração, defina a URL de retorno
`https://chatbot.lucianaritaguedes.com.br/webhook` e o token igual a `WA_VERIFY_TOKEN`, e assine o
campo `messages`. Envie "Oi" pelo telefone e confira a resposta e a tela de Histórico.

## 7. Backups

```bash
systemctl is-active cron
install -d -o chatbot -g chatbot -m 700 /var/backups/chatbot
echo '30 3 * * * chatbot /bin/sh /opt/chatbot/deploy/backup-db.sh' > /etc/cron.d/chatbot-backup
runuser -u chatbot -- /bin/sh /opt/chatbot/deploy/backup-db.sh
ls -l /var/backups/chatbot
```

As cópias ficam no próprio VPS: protegem contra erro humano, não contra a perda do servidor.

## Atualização

```bash
cd /opt/chatbot
runuser -u chatbot -- git pull --ff-only
VIRTUAL_ENV=/opt/chatbot/.venv uv pip install -r requirements.txt
chown -R chatbot:chatbot /opt/chatbot
systemctl restart chatbot
```

Depois de alterar o `.env`, reinicie com `systemctl restart chatbot`. Não há migrações: `create_all`
não altera tabelas existentes, então mudanças de esquema precisam de um plano próprio.
