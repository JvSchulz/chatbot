from pathlib import Path
from fastapi.templating import Jinja2Templates
from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """
    Configuração de execução lida do ambiente ou do arquivo .env, sem valores padrão para segredos.

    Uma variável obrigatória ausente ou em branco impede a inicialização e o erro lista todas elas.
    """

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        extra="ignore",
        alias_generator=str.upper,
    )

    secret_key: SecretStr
    wa_verify_token: SecretStr
    app_secret: SecretStr
    wa_token: SecretStr
    wa_phone_id: str
    admin_initial_password: SecretStr | None = None

    @field_validator("secret_key", "wa_verify_token", "app_secret", "wa_token", "wa_phone_id")
    @classmethod
    def reject_blank(cls, value: SecretStr | str) -> SecretStr | str:
        """
        Rejeita valores vazios ou compostos apenas por espaços nas variáveis obrigatórias.

        Args:
            value: Valor lido do ambiente para a variável obrigatória.

        Returns:
            O próprio valor quando contém algum caractere visível.

        Raises:
            ValueError: Quando o valor está em branco.
        """
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if not raw.strip():
            raise ValueError("a variável não pode ficar em branco")
        return value


settings = Settings()  # pyright: ignore[reportCallIssue]

templates = Jinja2Templates(directory=BASE_DIR / "src" / "views" / "templates")
