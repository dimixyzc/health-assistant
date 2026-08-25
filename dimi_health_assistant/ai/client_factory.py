"""Create the coaching client from direct OpenAI or CHECK24 LLM Proxy settings."""

from ai.openai_client import OpenAIHealthAssistant
from config import settings


def build_ai_client() -> OpenAIHealthAssistant:
    if settings.llm_proxy_api_key:
        return OpenAIHealthAssistant(
            settings.llm_proxy_api_key,
            settings.openai_model,
            base_url=settings.llm_proxy_base_url,
            default_headers={
                "X-LLM-Proxy-App": settings.llm_proxy_app,
                "X-LLM-Proxy-Usecase": settings.llm_proxy_usecase,
                "X-LLM-Proxy-Env": settings.llm_proxy_env,
            },
            trace_proxy_requests=True,
        )

    return OpenAIHealthAssistant(settings.openai_api_key, settings.openai_model)
