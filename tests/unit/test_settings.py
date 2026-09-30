"""
Testes unitários da configuração de execução: segredos obrigatórios, sem valores padrão.
"""

import os
import shutil
import subprocess
import sys
import pytest
from pathlib import Path
from pydantic import ValidationError
from src.core.config import Settings

REQUIRED_VARIABLES = ("SECRET_KEY", "WA_VERIFY_TOKEN", "APP_SECRET", "WA_TOKEN", "WA_PHONE_ID")


@pytest.fixture(name="valid_env")
def valid_env_fixture(monkeypatch):
    """Define todas as variáveis obrigatórias com valores válidos e remove a senha inicial."""
    for name in REQUIRED_VARIABLES:
        monkeypatch.setenv(name, f"valor-{name.lower()}")
    monkeypatch.delenv("ADMIN_INITIAL_PASSWORD", raising=False)
    return monkeypatch


def test_settings_loads_when_every_secret_is_present(valid_env):
    loaded = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert loaded.secret_key.get_secret_value() == "valor-secret_key"
    assert loaded.wa_verify_token.get_secret_value() == "valor-wa_verify_token"
    assert loaded.app_secret.get_secret_value() == "valor-app_secret"
    assert loaded.wa_token.get_secret_value() == "valor-wa_token"
    assert loaded.wa_phone_id == "valor-wa_phone_id"


def test_admin_initial_password_is_optional(valid_env):
    loaded = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert loaded.admin_initial_password is None


def test_admin_initial_password_is_read_when_present(valid_env):
    valid_env.setenv("ADMIN_INITIAL_PASSWORD", "SenhaInicial123")

    loaded = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert loaded.admin_initial_password is not None
    assert loaded.admin_initial_password.get_secret_value() == "SenhaInicial123"


def test_unknown_environment_variables_are_ignored(valid_env):
    valid_env.setenv("APP_ID", "123")

    loaded = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert not hasattr(loaded, "app_id")


@pytest.mark.parametrize("name", REQUIRED_VARIABLES)
def test_missing_secret_fails_naming_the_variable(valid_env, name):
    valid_env.delenv(name)

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert name in str(error.value)


@pytest.mark.parametrize("name", REQUIRED_VARIABLES)
def test_blank_secret_fails_like_a_missing_one(valid_env, name):
    valid_env.setenv(name, "")

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert name in str(error.value)


def test_whitespace_only_secret_is_rejected(valid_env):
    valid_env.setenv("SECRET_KEY", "   ")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # pyright: ignore[reportCallIssue]


def test_every_missing_secret_is_named_in_one_error(valid_env):
    for name in REQUIRED_VARIABLES:
        valid_env.delenv(name)

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert all(name in str(error.value) for name in REQUIRED_VARIABLES)


def test_secret_values_are_not_exposed_in_repr(valid_env):
    loaded = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert "valor-app_secret" not in repr(loaded)


EXAMPLE_ENV = Path(__file__).resolve().parents[2] / "example_env"
CONFIG_SOURCE = Path(__file__).resolve().parents[2] / "src" / "core" / "config.py"


def test_example_env_lets_a_fresh_clone_start(monkeypatch):
    """
    Copiar example_env para .env deve produzir uma configuração válida, com senha inicial aceita.
    """
    for name in (*REQUIRED_VARIABLES, "ADMIN_INITIAL_PASSWORD"):
        monkeypatch.delenv(name, raising=False)

    loaded = Settings(_env_file=EXAMPLE_ENV)  # pyright: ignore[reportCallIssue]

    assert loaded.admin_initial_password is not None
    assert len(loaded.admin_initial_password.get_secret_value()) >= 12


def test_example_env_lists_every_variable_the_application_reads():
    """
    example_env deve declarar cada variável de Settings, cada uma precedida por um comentário.
    """
    lines = EXAMPLE_ENV.read_text(encoding="utf-8").splitlines()
    declared = {line.split("=", 1)[0] for line in lines if "=" in line and not line.startswith("#")}

    assert declared == {*REQUIRED_VARIABLES, "ADMIN_INITIAL_PASSWORD"}
    assert all(lines[index - 1].startswith("# ") for index, line in enumerate(lines) if "=" in line)


def test_dotenv_next_to_the_project_root_is_found_from_any_working_directory(tmp_path):
    """
    O .env na raiz do projeto deve ser lido mesmo quando o processo inicia em outro diretório.
    """
    project = tmp_path / "project"
    (project / "src" / "core").mkdir(parents=True)
    (project / "src" / "__init__.py").touch()
    (project / "src" / "core" / "__init__.py").touch()
    shutil.copy(CONFIG_SOURCE, project / "src" / "core" / "config.py")
    values = {name: f"valor-{name.lower()}" for name in REQUIRED_VARIABLES}
    (project / ".env").write_text("".join(f"{name}={value}\n" for name, value in values.items()))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    result = subprocess.run(
        [sys.executable, "-c", "from src.core.config import settings; print(settings.wa_phone_id)"],
        cwd=elsewhere,
        env={"PATH": os.environ["PATH"], "PYTHONPATH": str(project)},
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr[-300:]
    assert result.stdout.strip() == "valor-wa_phone_id"
