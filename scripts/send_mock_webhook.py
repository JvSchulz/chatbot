"""
Envia ao webhook local um evento no formato da Meta, assinado com APP_SECRET.

Uso (a partir da raiz do projeto, com as variáveis de ambiente ou o .env configurados):
    python -m scripts.send_mock_webhook --text "Olá"
    python -m scripts.send_mock_webhook --button "menu:1" --url http://127.0.0.1:8000/webhook

O corpo é assinado exatamente como a Meta faz (X-Hub-Signature-256), portanto a validação
do servidor permanece ligada. Não há atalho para desativá-la.
"""

import argparse
import hashlib
import hmac
import json
import sys
import time
import urllib.error
import urllib.request
from src.core.config import settings

DEFAULT_URL = "http://127.0.0.1:8000/webhook"
DEFAULT_WA_ID = "554798765432"
DEFAULT_USER_ID = "BR.1234567890123"


def build_payload(kind: str, content: str, wa_id: str) -> bytes:
    """
    Monta o corpo JSON de um evento de mensagem recebida no formato do webhook da Meta.

    Args:
        kind: Tipo do evento, 'text' para mensagem de texto ou 'button' para clique em botão.
        content: Texto da mensagem ou identificador (dados) do botão clicado.
        wa_id: Identificador WhatsApp do remetente simulado.

    Returns:
        Corpo da requisição serializado em bytes UTF-8.
    """
    message: dict = {
        "from": wa_id,
        "id": f"wamid.MOCK{time.time_ns()}",
        "timestamp": str(int(time.time())),
    }
    if kind == "button":
        message["type"] = "interactive"
        message["interactive"] = {"type": "button_reply", "button_reply": {"id": content, "title": "Opção"}}
    else:
        message["type"] = "text"
        message["text"] = {"body": content}

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "0",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "0",
                                "phone_number_id": settings.wa_phone_id,
                            },
                            "contacts": [
                                {
                                    "profile": {"name": "Usuário Simulado"},
                                    "wa_id": wa_id,
                                    "user_id": DEFAULT_USER_ID,
                                }
                            ],
                            "messages": [message],
                        },
                    }
                ],
            }
        ],
    }
    return json.dumps(payload).encode("utf-8")


def sign_body(body: bytes) -> str:
    """
    Calcula o valor do cabeçalho X-Hub-Signature-256 para o corpo informado.

    Args:
        body: Corpo bruto da requisição.

    Returns:
        Assinatura no formato sha256=<hex do HMAC-SHA256 com APP_SECRET>.
    """
    secret = settings.app_secret.get_secret_value().encode("utf-8")
    return "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()


def post_webhook(url: str, body: bytes) -> tuple[int, str]:
    """
    Envia o corpo assinado ao webhook e devolve o status e a resposta recebidos.

    Args:
        url: Endereço completo do webhook.
        body: Corpo bruto da requisição, já serializado.

    Returns:
        Tupla com o código HTTP e o texto da resposta.
    """
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sign_body(body)},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """
    Interpreta os argumentos de linha de comando do simulador de webhook.

    Args:
        argv: Lista de argumentos, ou None para usar sys.argv.

    Returns:
        Argumentos interpretados, com exatamente um entre --text e --button.
    """
    parser = argparse.ArgumentParser(description="Envia um webhook simulado e assinado ao servidor local.")
    kind = parser.add_mutually_exclusive_group(required=True)
    kind.add_argument("--text", help="Texto da mensagem recebida")
    kind.add_argument("--button", help="Dados (id) do botão de resposta rápida clicado")
    parser.add_argument("--url", default=DEFAULT_URL, help=f"Endereço do webhook (padrão: {DEFAULT_URL})")
    parser.add_argument("--wa-id", default=DEFAULT_WA_ID, help=f"wa_id do remetente (padrão: {DEFAULT_WA_ID})")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """
    Ponto de entrada: monta, assina e envia o evento simulado.

    Args:
        argv: Lista de argumentos, ou None para usar sys.argv.

    Returns:
        Código de saída do processo, 0 quando o servidor responde 2xx e 1 caso contrário.
    """
    args = parse_args(argv)
    if args.button is not None:
        body = build_payload("button", args.button, args.wa_id)
    else:
        body = build_payload("text", args.text, args.wa_id)
    try:
        status, response_text = post_webhook(args.url, body)
    except urllib.error.URLError as error:
        print(f"Servidor inacessível em {args.url}: {error.reason}", file=sys.stderr)
        return 1
    print(f"{status} {response_text}")
    return 0 if 200 <= status < 300 else 1


if __name__ == "__main__":
    sys.exit(main())
