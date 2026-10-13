from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    supabase_url: str
    supabase_publishable_key: str
    supabase_secret_key: str | None = None
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174"
    ai_provider: str = "deterministic"
    groq_api_key: str | None = None
    groq_model: str | None = None
    huggingface_token: str | None = None
    huggingface_model: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_from_name: str = "CrisisWatch"
    smtp_use_tls: bool = True
    public_app_url: str = "http://127.0.0.1:5173"
    email_scheduler_poll_seconds: int = 30
    pinecone_rag_enabled: bool = False
    pinecone_api_key: str | None = None
    pinecone_index_name: str = "crisiswatch-playbooks"
    pinecone_index_host: str | None = None
    pinecone_namespace: str = "approved-playbooks"
    pinecone_embedding_model: str = "llama-text-embed-v2"
    pinecone_top_k: int = 5
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"

    model_config = SettingsConfigDict(env_file=(".env", "backend/.env"), env_file_encoding="utf-8", extra="ignore")

    @property
    def origins(self) -> list[str]:
        configured = [item.strip() for item in self.allowed_origins.split(",") if item.strip()]
        # Local development scripts advertise 127.0.0.1 while the default
        # environment value historically used localhost. Treat both loopback
        # spellings as the same development origin so the dashboard can call
        # the API regardless of which URL the user opens.
        origins = set(configured)
        for origin in configured:
            if origin.startswith("http://localhost:"):
                origins.add(origin.replace("http://localhost:", "http://127.0.0.1:"))
            elif origin.startswith("http://127.0.0.1:"):
                origins.add(origin.replace("http://127.0.0.1:", "http://localhost:"))
        return sorted(origins)

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from_email)


@lru_cache
def get_settings() -> Settings:
    return Settings()
