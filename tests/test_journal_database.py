import tempfile
import unittest

from storage import database as db


class JournalDatabaseTest(unittest.IsolatedAsyncioTestCase):
    async def test_journal_entry_is_upserted_and_scores_are_clamped(self):
        with tempfile.TemporaryDirectory() as tmp:
            await db.init_db(tmp)

            saved = await db.upsert_journal_entry(tmp, {
                "date": "2026-06-28",
                "mood": 11,
                "energy": 0,
                "stress": 6,
                "tags": "kaffee, spaetessen",
                "note": "unruhiger tag",
            })

            self.assertEqual(saved["mood"], 10)
            self.assertEqual(saved["energy"], 1)
            self.assertEqual(saved["stress"], 6)

            updated = await db.upsert_journal_entry(tmp, {
                "date": "2026-06-28",
                "energy": 7,
                "sleep_quality": 8,
            })

            self.assertEqual(updated["mood"], 10)
            self.assertEqual(updated["energy"], 7)
            self.assertEqual(updated["sleep_quality"], 8)
            self.assertEqual(updated["note"], "unruhiger tag")

    async def test_active_experiments_exclude_finished_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            await db.init_db(tmp)

            active = await db.create_experiment(tmp, {
                "name": "Koffein vor 12",
                "hypothesis": "Schlaf wird besser",
                "target_metric": "sleep_quality",
                "start_date": "2026-06-28",
                "duration_days": 14,
            })
            await db.create_experiment(tmp, {
                "name": "Altes Experiment",
                "start_date": "2026-01-01",
                "duration_days": 3,
            })

            experiments = await db.get_active_experiments(tmp)

            self.assertEqual([e["id"] for e in experiments], [active["id"]])
            self.assertEqual(experiments[0]["name"], "Koffein vor 12")


if __name__ == "__main__":
    unittest.main()
