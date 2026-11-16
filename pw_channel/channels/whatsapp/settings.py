import os
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _swap_db(url: str, db: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "/" + db, parts.query, parts.fragment))


def _company() -> str:
    return os.getenv("COMPANY_NAME", "PlaceholderWorks")


def _agent() -> str:
    return os.getenv("AGENT_NAME", "Aria")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    whatsapp_token: str = ""
    whatsapp_phone_number_id: str = ""
    webhook_verify_token: str = ""
    whatsapp_api_version: str = "v22.0"
    whatsapp_bot_phone_number: str = ""

    chat_service_endpoint: str = "http://localhost:8010/api/pw-ai-service/chat"
    brain_api_token: str = Field(default_factory=lambda: os.getenv("PW_CHAT_API_TOKEN", "") or os.getenv("PW_LLM_API_TOKEN", ""))

    host: str = "0.0.0.0"
    port: int = 8420
    public_base_url: str = ""

    dev_test_number_one: str = ""
    dev_tunnel_webhook_one: str = ""
    dev_test_number_two: str = ""
    dev_tunnel_webhook_two: str = ""
    staging_numbers: str = ""
    staging_webhook_url: str = ""
    staging_karix_number: str = ""

    session_timeout: int = 86400
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""
    redis_key_prefix: str = "whatsapp_bot:"

    database_url: str = ""
    campaign_cache_ttl: int = 30
    admin_secret: str = ""
    openai_api_key: str = ""

    karix_username: str = ""
    karix_password: str = ""
    karix_scenario_key: str = ""
    karix_sender_numbers: str = ""
    karix_api_base_url: str = "https://rcmapi.instaalerts.zone/services/rcm"

    nowonextel_sender_numbers: str = ""
    nowonextel_api_url: str = "https://api.onexaura.com/send_sms"
    nowonextel_api_key: str = ""
    nowonextel_country_prefix: str = "+91"
    nowonextel_webhook_secret: str = ""
    nowonextel_media_auth: bool = False
    nowonextel_media_api_url: str = "https://api.onexaura.com/oapi/wa"

    duplicate_message_ttl: int = 21600
    duplicate_message_repeat_threshold: int = 2
    duplicate_message_reply: str = Field(default_factory=lambda: (
        f"Hi! I'm {_agent()} from {_company()}. Ask me anything, or say \"talk to the team\" to reach a person."
    ))
    opt_out_reply: str = Field(default_factory=lambda: (
        f"You won't get more messages from {_company()} here. Reply START any time to talk to us again."
    ))

    voicebot_api_secret: str = ""
    voicebot_cart_link_base: str = ""
    voicebot_send_timeout: float = 6.0
    voicebot_dedupe_ttl: int = 3600
    voicebot_sender_number: str = ""

    embracebot_base_url: str = ""
    embracebot_company_id: str = ""
    embracebot_flow_timeout: int = 86400
    agent_handoff_signal: str = "__CONNECT_AGENT__"
    agent_chat_ended_marker: str = Field(default_factory=lambda: f"back with {_agent()}")
    ai_flow_keywords: list[str] = Field(default_factory=lambda: [f"hi {_agent().lower()}", f"hey {_agent().lower()}",
                                                                 f"talk to {_agent().lower()}"])

    @property
    def company_name(self) -> str:
        return _company()

    @property
    def dev_tunnel_map(self) -> dict[str, str]:
        pairs = [(self.dev_test_number_one, self.dev_tunnel_webhook_one), (self.dev_test_number_two, self.dev_tunnel_webhook_two)]
        return {number.strip().lstrip("+"): hook.strip() for number, hook in pairs if number.strip() and hook.strip()}

    @property
    def staging_numbers_list(self) -> list[str]:
        return [n.strip().lstrip("+") for n in self.staging_numbers.split(",") if n.strip()]

    @property
    def karix_numbers_list(self) -> list[str]:
        return [n.strip().lstrip("+") for n in self.karix_sender_numbers.split(",") if n.strip()]

    @property
    def nowonextel_numbers_list(self) -> list[str]:
        return ["".join(c for c in n if c.isdigit()) for n in self.nowonextel_sender_numbers.split(",") if n.strip()]

    @property
    def meta_number(self) -> str:
        return (self.whatsapp_bot_phone_number or "").strip().lstrip("+")

    @property
    def meta_numbers_list(self) -> list[str]:
        return [self.meta_number] if self.meta_number else []

    @property
    def meta_configured(self) -> bool:
        return bool(self.whatsapp_token and self.whatsapp_phone_number_id)

    @property
    def campaign_numbers_list(self) -> list[str]:
        seen, out = set(), []
        for num in [*self.karix_numbers_list, *self.nowonextel_numbers_list, *self.meta_numbers_list]:
            if num and num not in seen:
                seen.add(num)
                out.append(num)
        return out

    @property
    def pg_app_dsn(self) -> str:
        return self.database_url.strip()

    @property
    def campaign_db_name(self) -> str:
        return urlsplit(self.pg_app_dsn).path.lstrip("/") or "postgres"

    @property
    def pg_maintenance_dsn(self) -> str:
        return _swap_db(self.pg_app_dsn, "postgres")


settings = Settings()
