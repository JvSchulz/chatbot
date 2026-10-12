"""
Testes E2E da política de segurança de conteúdo: nenhuma página ou fragmento do painel pode
depender de script, manipulador de evento ou estilo embutido, e os ativos precisam estar versionados.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from main import app
from src.models.chat_history_model import ChatHistory
from src.services.menu_service import MenuData, create_menu

PROJECT_ROOT = Path(__file__).resolve().parents[2]

INLINE_SCRIPT = re.compile(r"<script(?![^>]*\ssrc=)[^>]*>", re.IGNORECASE)
INLINE_HANDLER = re.compile(r"\son[a-z]+\s*=", re.IGNORECASE)
INLINE_STYLE = re.compile(r"\sstyle\s*=", re.IGNORECASE)
SCRIPT_URL = re.compile(r"""\shref\s*=\s*["']\s*javascript:""", re.IGNORECASE)

PAGES = ["/menus", "/usuarios", "/historico"]
FRAGMENTS = [
    "/menus/lista",
    "/menus/aviso-raiz",
    "/menus/novo/card",
    "/menus/{root_id}/card",
    "/menus/{child_id}/card",
    "/usuarios/lista",
    "/usuarios/novo/card",
    "/usuarios/1/card",
]


@pytest.fixture(name="seeded_ids")
def seeded_ids_fixture(session: Session) -> dict[str, int]:
    """Cria uma raiz, um filho e uma linha de histórico para que as páginas renderizem dados reais."""
    root = create_menu(session, data=MenuData(name="raiz", selection_name="Raiz", message="Olá", is_root=True))
    child = create_menu(
        session, data=MenuData(name="filho", selection_name="Filho", message="Oi", parent_id=root.id)
    )
    session.add(ChatHistory(user_id="BR.1234567890123", role="user", content="Oi", menu_id=child.id))
    session.commit()
    return {"root_id": root.id, "child_id": child.id}  # type: ignore


def assert_no_inline_code(html: str) -> None:
    """Falha se o HTML contiver script embutido, manipulador on*=, atributo style ou URL javascript:."""
    assert INLINE_SCRIPT.search(html) is None
    assert INLINE_HANDLER.search(html) is None
    assert INLINE_STYLE.search(html) is None
    assert SCRIPT_URL.search(html) is None


def assert_strict_csp(response) -> None:
    """Falha se a política de segurança de conteúdo permitir 'unsafe-inline'."""
    policy = response.headers["Content-Security-Policy"]
    assert "'unsafe-inline'" not in policy


@pytest.mark.parametrize("path", PAGES)
def test_admin_pages_have_no_inline_code(auth_client: TestClient, seeded_ids, path: str):
    response = auth_client.get(path)

    assert response.status_code == 200
    assert_no_inline_code(response.text)


@pytest.mark.parametrize("path", PAGES)
def test_admin_pages_send_a_strict_csp(auth_client: TestClient, seeded_ids, path: str):
    assert_strict_csp(auth_client.get(path))


@pytest.mark.parametrize("path", FRAGMENTS)
def test_htmx_fragments_have_no_inline_code(auth_client: TestClient, seeded_ids, path: str):
    response = auth_client.get(path.format(**seeded_ids), headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert_no_inline_code(response.text)


def test_login_page_has_no_inline_code_and_a_strict_csp():
    response = TestClient(app).get("/login")

    assert response.status_code == 200
    assert_no_inline_code(response.text)
    assert_strict_csp(response)


def test_login_failure_fragments_have_no_inline_code():
    client = TestClient(app)

    htmx_failure = client.post(
        "/login", data={"username": "x", "password": "y"}, headers={"HX-Request": "true"}
    )
    page_failure = client.post("/login", data={"username": "x", "password": "y"})

    assert htmx_failure.status_code == 401
    assert_no_inline_code(htmx_failure.text)
    assert_no_inline_code(page_failure.text)


def test_page_scripts_are_only_the_two_static_files(auth_client: TestClient, seeded_ids):
    response = auth_client.get("/menus")

    assert re.findall(r'<script[^>]*\ssrc="([^"]+)"', response.text) == ["/static/htmx.min.js", "/static/app.js"]


def test_logo_is_served_from_static(auth_client: TestClient):
    response = auth_client.get("/static/img/logo.svg")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")


def test_logo_carries_no_embedded_stylesheet(auth_client: TestClient):
    """O SVG recebe a mesma política de conteúdo das páginas; um bloco <style> interno seria bloqueado."""
    response = auth_client.get("/static/img/logo.svg")

    assert "<style" not in response.text
    assert "class=" not in response.text


def test_assets_mount_is_gone(auth_client: TestClient):
    assert auth_client.get("/assets/vertical_negativo.svg").status_code == 404


def test_fresh_clone_without_untracked_assets_starts(tmp_path: Path):
    """
    Uma cópia do projeto sem src/assets (ignorado pelo git), com .env vindo de example_env,
    deve importar a aplicação e servir a logo.
    """
    clone = tmp_path / "clone"
    shutil.copytree(
        PROJECT_ROOT / "src", clone / "src", ignore=shutil.ignore_patterns("assets", "__pycache__")
    )
    shutil.copy(PROJECT_ROOT / "main.py", clone / "main.py")
    shutil.copy(PROJECT_ROOT / "example_env", clone / ".env")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    program = (
        "from fastapi.testclient import TestClient; import main; "
        "print(TestClient(main.app).get('/static/img/logo.svg').status_code)"
    )

    result = subprocess.run(
        [sys.executable, "-c", program],
        cwd=elsewhere,
        env={"PATH": os.environ["PATH"], "PYTHONPATH": str(clone)},
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr[-500:]
    assert result.stdout.strip().splitlines()[-1] == "200"
