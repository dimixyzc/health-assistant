import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AddonReleaseTest(unittest.TestCase):
    def test_shared_runtime_modules_match_addon_build_context(self):
        for name in ["ai/openai_client.py", "ai/client_factory.py", "bot/handlers/commands.py",
                     "knowledge/__init__.py", "knowledge/library.py", "knowledge/import_epub.py"]:
            self.assertEqual((ROOT / name).read_bytes(), (ROOT / "dimi_health_assistant" / name).read_bytes(), name)

    def test_saved_legacy_models_migrate_and_explicit_alternative_survives(self):
        script = (ROOT / "dimi_health_assistant/run.sh").read_text()
        # Run only configuration logic with bashio stubs; never start the bot
        # or touch the real /data and /share directories.
        config = script.split('bashio::log.info "Starting')[0]
        stub = '''
        bashio::config() {
            if [ "$1" = openai_model ]; then printf '%s' "$TEST_MODEL";
            else printf '%s' "${2:-}"; fi
        }
        bashio::log.info() { :; }
        '''
        for saved, expected in [("gpt-4o", "gpt-6-luna"), ("gpt-5.5", "gpt-6-luna"),
                                ("gpt-5.6-terra", "gpt-6-luna"), ("", "gpt-6-luna"),
                                ("gpt-6-luna", "gpt-6-luna"), ("custom-model", "custom-model")]:
            process = subprocess.run(["bash", "-c", stub + config + '\nprintf "%s" "$OPENAI_MODEL"'],
                                     env={**os.environ, "TEST_MODEL": saved}, capture_output=True, text=True, check=True)
            self.assertEqual(process.stdout, expected)


if __name__ == "__main__":
    unittest.main()
