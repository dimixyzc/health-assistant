"""Create the direct OpenAI coaching client."""

from ai.openai_client import OpenAIHealthAssistant
from config import settings


def build_ai_client() -> OpenAIHealthAssistant:
    return OpenAIHealthAssistant(settings.openai_api_key, settings.openai_model, settings.data_dir)
