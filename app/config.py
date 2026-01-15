from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Base de datos (Supabase Postgres / Pooler)
    DATABASE_URL: str

    # Seguridad JWT
    SECRET_KEY: str = "super_secreta_local_12345"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # Solo DEV local: permite desactivar verificación SSL si tu red/antivirus hace inspección SSL
    DB_SSL_VERIFY: bool = True


settings = Settings()
