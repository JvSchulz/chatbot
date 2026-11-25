"""
Testes de higiene do repositório público: configurações portáteis, modelos de deploy
sanitizados e documentação alinhada ao escopo atual.
"""

import json
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_DIR = PROJECT_ROOT / "deploy"
WINDOWS_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:[\\/]")
IPV4_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
URL_HOST_PATTERN = re.compile(r"https?://([a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+)")
DOMAIN_PATTERN = re.compile(
    r"\b([a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.(?:com|net|org|io|dev|gov|edu|br)(?:\.[a-z]{2})?)\b",
    re.IGNORECASE,
)
CADDY_SITE_PATTERN = re.compile(r"^\s*([a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+)\s*\{", re.MULTILINE)
PORT_CLAUSE_PATTERN = re.compile(r"\bportas?\b[^.\n]*", re.IGNORECASE)
PORT_NUMBER_PATTERN = re.compile(r"(?<!-)\b\d{2,5}\b(?!-)")

ALLOWED_DEPLOY_IPS = {"127.0.0.1", "1.1.1.1"}
ALLOWED_DEPLOY_HOSTS = {
    "chatbot.example.com",
    "example.com",
    "127.0.0.1",
    "github.com",
    "astral.sh",
    "dl.cloudsmith.io",
    "letsencrypt.status.io",
    "archive.canonical.com",
}
ALLOWED_DEPLOY_PORTS = {"22", "80", "443", "2019", "8000"}
FORBIDDEN_GENERIC_DEPLOY_PATTERNS = [
    "~/",
    "/home/",
    "/users/",
    "codespace",
    "--branch",
    "login de root",
    "permitrootlogin",
]


def _deploy_files() -> list[Path]:
    files = sorted(path for path in DEPLOY_DIR.rglob("*") if path.is_file())
    assert files, "Nenhum arquivo encontrado em deploy/"
    return files


def _is_absolute_path(value: str) -> bool:
    return (
        Path(value).is_absolute()
        or value.startswith(("/", "\\"))
        or bool(WINDOWS_DRIVE_PREFIX.match(value))
    )


def test_pyrightconfig_uses_relative_paths_and_includes_scripts():
    config = json.loads((PROJECT_ROOT / "pyrightconfig.json").read_text(encoding="utf-8"))

    venv_path = config.get("venvPath")
    extra_paths = config.get("extraPaths")
    include = config.get("include", [])

    assert isinstance(venv_path, str) and venv_path.strip() != ""
    assert not _is_absolute_path(venv_path), venv_path
    assert isinstance(extra_paths, list) and len(extra_paths) > 0
    for path in extra_paths:
        assert isinstance(path, str) and path.strip() != ""
        assert not _is_absolute_path(path), path
    for required in ("src", "tests", "scripts", "main.py"):
        assert required in include


def test_deploy_files_only_contain_allowed_ipv4_addresses():
    unexpected: list[str] = []
    for path in _deploy_files():
        text = path.read_text(encoding="utf-8")
        for ip in IPV4_PATTERN.findall(text):
            if ip not in ALLOWED_DEPLOY_IPS:
                unexpected.append(f"{path.name}: {ip}")

    assert unexpected == []


def test_deploy_files_only_contain_allowed_hostnames_and_domains():
    unexpected: list[str] = []
    for path in _deploy_files():
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        if ".com.br" in lowered:
            unexpected.append(f"{path.name}: .com.br")
        for host in URL_HOST_PATTERN.findall(text):
            if host.lower() not in ALLOWED_DEPLOY_HOSTS:
                unexpected.append(f"{path.name} (url): {host}")
        for domain in DOMAIN_PATTERN.findall(text):
            if domain.lower() not in ALLOWED_DEPLOY_HOSTS:
                unexpected.append(f"{path.name} (domain): {domain}")

    caddy_sites = CADDY_SITE_PATTERN.findall((DEPLOY_DIR / "Caddyfile").read_text(encoding="utf-8"))
    assert caddy_sites
    for site in caddy_sites:
        if site.lower() not in ALLOWED_DEPLOY_HOSTS:
            unexpected.append(f"Caddyfile (site): {site}")

    assert unexpected == []


@pytest.mark.parametrize("pattern", FORBIDDEN_GENERIC_DEPLOY_PATTERNS)
def test_deploy_files_exclude_local_paths_stale_branches_and_ssh_posture(pattern: str):
    offending = [
        path.name
        for path in _deploy_files()
        if pattern in path.read_text(encoding="utf-8").lower()
    ]

    assert offending == []


def test_deploy_readme_avoids_unexpected_third_party_ports():
    content = (DEPLOY_DIR / "README.md").read_text(encoding="utf-8")
    unexpected: list[str] = []
    for clause in PORT_CLAUSE_PATTERN.findall(content):
        for port in PORT_NUMBER_PATTERN.findall(clause):
            if port not in ALLOWED_DEPLOY_PORTS:
                unexpected.append(f"{port} ({clause.strip()})")

    assert unexpected == []


def test_caddyfile_uses_example_domain_and_preserves_tls_alpn_proxy():
    content = (DEPLOY_DIR / "Caddyfile").read_text(encoding="utf-8")

    assert "chatbot.example.com" in content
    assert "auto_https disable_redirects" in content
    assert "disable_http_challenge" in content
    assert "reverse_proxy 127.0.0.1:8000" in content


def test_arquitetura_overview_concisely_states_current_scope():
    content = (PROJECT_ROOT / "arquitetura.md").read_text(encoding="utf-8")
    overview = content.split("## Stack", maxsplit=1)[0].lower()

    assert "whatsapp" in overview
    assert "pywa" in overview
    assert "menus hierárquicos" in overview
    assert overview.count("telegram") <= 1
    assert overview.count("retirado do escopo") <= 1


def test_menu_seeder_script_is_removed():
    assert not (PROJECT_ROOT / "scripts" / "seed_menus.py").exists()


@pytest.mark.parametrize("rel_path", ["README.md", "deploy/README.md"])
def test_docs_do_not_reference_removed_menu_seeder(rel_path: str):
    content = (PROJECT_ROOT / rel_path).read_text(encoding="utf-8").lower()

    assert "seed_menus" not in content
