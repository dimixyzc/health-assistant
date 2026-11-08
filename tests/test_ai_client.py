import asyncio
import logging
import unittest
import tempfile
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import AsyncMock, patch

from ai.openai_client import OpenAIHealthAssistant
from knowledge import KnowledgeBase
from test_knowledge import make_epub


class _FakeCompletions:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


class OpenAIClientTest(unittest.TestCase):
    def _assistant(self, tmp, content="• 💡 Test answer", finish_reason="stop"):
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content, refusal=None), finish_reason=finish_reason)],
            usage=None,
        )
        assistant = OpenAIHealthAssistant("sk-test", data_dir=tmp)
        completions = _FakeCompletions(response)
        assistant._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        return assistant, completions

    def test_all_coaching_surfaces_receive_book_and_safety_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "book.epub"
            make_epub(source)
            assistant, completions = self._assistant(tmp)
            assistant._knowledge = KnowledgeBase(tmp, str(source))
            calls = [
                lambda: assistant.generate_morning_briefing({}),
                lambda: assistant.generate_evening_summary({}, []),
                lambda: assistant.generate_weekly_summary({}),
                lambda: assistant.generate_weight_insight({"available": True}),
                lambda: assistant.generate_plan_explanation({}),
                lambda: assistant.generate_training_tip({}, []),
                lambda: assistant.answer_free_question("Wie besser schlafen?", {}, []),
            ]
            with patch.object(assistant, "_recent_coaching", AsyncMock(return_value="")), patch.object(assistant, "_remember_coaching", AsyncMock()):
                for call in calls:
                    self.assertTrue(asyncio.run(call()))
                    messages = completions.kwargs["messages"]
                    self.assertEqual(completions.kwargs["model"], "gpt-6-luna")
                    self.assertIn("Behandlungs-/Reha-Plan", messages[0]["content"])
                    self.assertIn("keine Supplement-Stacks", messages[0]["content"])
                    self.assertEqual(messages[1]["role"], "user")
                    self.assertIn('"book_available": true', messages[1]["content"])
                    self.assertIn("Protocol", messages[1]["content"])

    def test_free_question_retrieves_question_not_boilerplate_sensor_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            assistant, completions = self._assistant(tmp)
            assistant._knowledge = SimpleNamespace(prompt_context=lambda query: f"query={query}")
            asyncio.run(assistant.answer_free_question("Protein?", {"sleep_score": 50}, []))
            self.assertEqual(completions.kwargs["messages"][1]["content"], "query=Protein?")

    def test_truncated_answer_is_not_delivered_as_complete_advice(self):
        with tempfile.TemporaryDirectory() as tmp:
            assistant, _ = self._assistant(tmp, finish_reason="length")
            self.assertEqual(asyncio.run(assistant._chat("question")), "")

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
        assistant._model = "gpt-6-luna"
        assistant._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

        with self.assertLogs("ai.openai_client", level=logging.INFO) as logs:
            result = asyncio.run(assistant._chat("prompt"))

        self.assertEqual(result, "private health analysis")
        self.assertEqual(completions.kwargs["max_completion_tokens"], 900)
        self.assertEqual(completions.kwargs["reasoning_effort"], "none")
        joined_logs = "\n".join(logs.output)
        self.assertIn("input_tokens=123", joined_logs)
        self.assertIn("output_tokens=45", joined_logs)
        self.assertIn("reasoning_tokens=7", joined_logs)
        self.assertNotIn("private health analysis", joined_logs)
