"""Create the coaching client from direct OpenAI or CHECK24 LLM Proxy settings."""

from ai.openai_client import OpenAIHealthAssistant
from ai.llm_proxy_transport import LLMProxyFailoverTransport
from config import settings
import httpx


def build_ai_client() -> OpenAIHealthAssistant:
    if settings.llm_proxy_api_key:
        return OpenAIHealthAssistant(
            settings.llm_proxy_api_key,
            settings.openai_model,
            base_url="http://placeholder/v1/proxy/openai/auto",
            default_headers={
                "X-LLM-Proxy-App": settings.llm_proxy_app,
                "X-LLM-Proxy-Usecase": settings.llm_proxy_usecase,
                "X-LLM-Proxy-Env": settings.llm_proxy_env,
            },
            trace_proxy_requests=True,
            http_client=httpx.AsyncClient(
                transport=LLMProxyFailoverTransport(
                    "_baseurls-api-proxy-de.llmproxy.check24.global"
                )
            ),
        )

    return OpenAIHealthAssistant(settings.openai_api_key, settings.openai_model)
