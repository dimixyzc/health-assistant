import asyncio
import logging
import unittest
from types import SimpleNamespace

from ai.openai_client import OpenAIHealthAssistant


class _FakeCompletions:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


class OpenAIClientTest(unittest.TestCase):
    def test_chat_caps_output_and_logs_usage_without_content(self):
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="private health analysis", refusal=None),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=123,
                completion_tokens=45,
                total_tokens=168,
                completion_tokens_details=SimpleNamespace(reasoning_tokens=7),
            ),
        )
        completions = _FakeCompletions(response)
        assistant = OpenAIHealthAssistant.__new__(OpenAIHealthAssistant)
        assistant._model = "gpt-5.6-terra"
        assistant._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

        with self.assertLogs("ai.openai_client", level=logging.INFO) as logs:
            result = asyncio.run(assistant._chat("prompt"))

        self.assertEqual(result, "private health analysis")
        self.assertEqual(completions.kwargs["max_completion_tokens"], 500)
        joined_logs = "\n".join(logs.output)
        self.assertIn("input_tokens=123", joined_logs)
        self.assertIn("output_tokens=45", joined_logs)
        self.assertIn("reasoning_tokens=7", joined_logs)
        self.assertNotIn("private health analysis", joined_logs)
