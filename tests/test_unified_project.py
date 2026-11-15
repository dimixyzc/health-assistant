import asyncio
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock,patch

from training_plan.config import Settings as TrainingSettings
from training_plan import history
from bot.handlers import commands


class UnifiedProjectTest(unittest.TestCase):
    def test_cli_configuration_uses_shared_token_and_separate_training_store(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'DATA_DIR':tmp},clear=True):
            with patch('training_plan.config._load_dotenv'):
                config=TrainingSettings.from_env()
            self.assertEqual(config.data_dir,Path(tmp)/'training')
            self.assertEqual(config.garmin_token_dir,Path(tmp)/'.garminconnect')
            self.assertEqual(config.mode,'DRY_RUN')

    def test_bot_plan_is_read_only_and_needs_no_ai(self):
        from types import SimpleNamespace
        event=SimpleNamespace(chat=SimpleNamespace(id=1),answer=AsyncMock())
        with patch.object(commands.settings,'telegram_chat_id',1),patch.object(commands.insights,'get_scheduled_training',AsyncMock(return_value={'available':False})),patch.object(commands,'get_ai',side_effect=AssertionError('AI must not be needed')):
            asyncio.run(commands.cmd_plan(event))
        self.assertEqual(event.answer.await_count,2)
        self.assertIn('kein gespeicherter',event.answer.call_args.args[0])

    def test_history_missing_database_is_optional(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(history.recent_strength(tmp),[])
            self.assertEqual(list(Path(tmp).rglob('*')),[])

    def test_bot_never_imports_planner_or_publish_code(self):
        import ast
        for path in Path('bot').rglob('*.py'):
            tree=ast.parse(path.read_text())
            imports=[node.module or '' for node in ast.walk(tree) if isinstance(node,ast.ImportFrom)]
            self.assertFalse(any(name.startswith(('training_plan.plan','training_plan.garmin_publish','training_plan.huberman','training_plan.cli')) for name in imports))

    def test_calendar_module_does_not_call_garmin_write_methods(self):
        import ast
        from training_plan import context
        tree=ast.parse(Path(context.__file__).read_text())
        names={node.attr for node in ast.walk(tree) if isinstance(node,ast.Attribute)}
        self.assertFalse(names & {'schedule_workout','unschedule_workout','delete_workout','upload_workout','update_workout','push_workout_to_device'})
