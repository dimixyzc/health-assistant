import asyncio
import json
import logging
import unittest
import tempfile
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import AsyncMock, patch

from ai.openai_client import OpenAIHealthAssistant, _briefing_knowledge_query
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
                    self.assertTrue(json.loads(messages[1]["content"].split("\n", 1)[1])["book_available"])
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

    def test_history_is_bounded_without_another_model_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            assistant, completions = self._assistant(tmp)
            with patch("ai.openai_client.db.get_recent_coach_messages", AsyncMock(return_value=["previous advice " * 500] * 3)) as history:
                result = asyncio.run(assistant._recent_coaching("morning"))
            self.assertLessEqual(len(result), 725)
            self.assertEqual(history.call_args.kwargs["limit"], 2)
            self.assertIsNone(completions.kwargs)

    def test_narrow_sleep_question_does_not_send_unrelated_weight_or_workouts(self):
        with tempfile.TemporaryDirectory() as tmp:
            assistant, completions = self._assistant(tmp)
            question = "Ich habe neue Schmerzen. Wie kann ich besser schlafen?"
            asyncio.run(assistant.answer_free_question(
                question, {}, [{"name": "private workout label"}],
                {"available": True, "latest_weight": 123.456},
            ))
            prompt = completions.kwargs["messages"][-1]["content"]
            self.assertIn(question, prompt)  # Never trim the actual question/symptoms.
            self.assertNotIn("123.456", prompt)
            self.assertNotIn("private workout label", prompt)
            self.assertEqual(completions.kwargs["max_completion_tokens"], 750)

    def test_weight_question_keeps_relevant_body_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            assistant, completions = self._assistant(tmp)
            asyncio.run(assistant.answer_free_question(
                "Wie verändert sich mein Gewicht?", {}, [],
                {"available": True, "latest_weight": 123.456},
            ))
            self.assertIn("123.456", completions.kwargs["messages"][-1]["content"])

    def test_retries_intermittent_model_access_denial(self):
        import httpx
        from openai import PermissionDeniedError

        request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        response = httpx.Response(403, request=request)
        error = PermissionDeniedError("unavailable", response=response, body={"code": "model_not_found"})
        result = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="OK", refusal=None), finish_reason="stop")],
            usage=None,
        )
        with tempfile.TemporaryDirectory() as tmp:
            assistant, _ = self._assistant(tmp)
            create = AsyncMock(side_effect=[error, error, result])
            assistant._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
            with patch("ai.openai_client.asyncio.sleep", new_callable=AsyncMock) as sleep:
                self.assertEqual(asyncio.run(assistant._chat("test")), "OK")
            self.assertEqual(create.await_count, 3)
            self.assertEqual(sleep.await_count, 2)

    def test_briefing_source_query_uses_present_context_not_missing_values(self):
        morning = _briefing_knowledge_query({"readiness": {"limiting_factors": ["Schlafschuld"]}, "avg_stress": 55})
        self.assertIn("Schlafschuld", morning)
        self.assertIn("Stress", morning)
        self.assertNotIn("Stress", _briefing_knowledge_query({"avg_stress": None}))
        self.assertIn("Abendroutine", _briefing_knowledge_query({}, evening=True))
        first = _briefing_knowledge_query({"date": "2026-11-14"})
        second = _briefing_knowledge_query({"date": "2026-11-15"})
        self.assertNotEqual(first, second)

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
                prompt_tokens_details=SimpleNamespace(cached_tokens=88),
            ),
        )
        completions = _FakeCompletions(response)
        assistant = OpenAIHealthAssistant.__new__(OpenAIHealthAssistant)
        assistant._model = "gpt-6-luna"
        assistant._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

        with self.assertLogs("ai.openai_client", level=logging.INFO) as logs:
            result = asyncio.run(assistant._chat("prompt"))

        self.assertEqual(result, "private health analysis")
        self.assertEqual(completions.kwargs["max_completion_tokens"], 450)
        self.assertEqual(completions.kwargs["reasoning_effort"], "none")
        joined_logs = "\n".join(logs.output)
        self.assertIn("input_tokens=123", joined_logs)
        self.assertIn("output_tokens=45", joined_logs)
        self.assertIn("reasoning_tokens=7", joined_logs)
        self.assertIn("cached_input_tokens=88", joined_logs)
        self.assertNotIn("private health analysis", joined_logs)
