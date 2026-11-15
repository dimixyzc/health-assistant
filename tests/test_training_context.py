import asyncio
from copy import deepcopy
from datetime import datetime,timedelta
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock,Mock,patch

from training_plan import context
from training_plan.migration import migrate_files
from analytics.formatter import scheduled_training

NOW = datetime(2026,11,30,12,tzinfo=context.TZ)


def item(identifier,day,title='Synthetic session'):
    return {'id':identifier,'workoutId':identifier+100,'itemType':'workout','date':day,
            'title':title,'sportTypeKey':'strength_training'}


class TrainingContextTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.client=SimpleNamespace(get_scheduled_workouts=Mock(return_value={'calendarItems':[
            item(1,'2026-11-30'),item(2,'2026-11-30'),item(3,'2026-12-01')]}),
            get_workout_by_id=Mock(return_value={'workoutSegments':[{'workoutSteps':[
                {'description':'Synthetic exercise','exerciseName':'FIXTURE_LIFT'}]}]}))
        self.login=patch.object(context.garmin,'get_client',AsyncMock(return_value=self.client))
        self.login.start();self.addCleanup(self.login.stop)

    async def get(self,**kw):
        return await context.get_context('test','test',self.tmp.name,now=NOW,**kw)

    async def test_preserves_multiple_same_day_entries_month_boundary_and_cache(self):
        value=await self.get()
        self.assertEqual(len(value['workouts']),3)
        self.assertEqual(self.client.get_scheduled_workouts.call_count,2)
        self.assertTrue(value['workouts'][0]['steps'])
        self.assertEqual((await self.get())['workouts'],value['workouts'])
        self.assertEqual(self.client.get_scheduled_workouts.call_count,2)
        self.assertIn('Heute',scheduled_training(value))
        self.assertNotIn('Ruhetag',scheduled_training(value))

    async def test_corrupt_cache_is_ignored(self):
        path=context._cache_path(self.tmp.name)
        path.parent.mkdir(parents=True)
        path.write_text('[]')
        self.assertTrue((await self.get())['available'])
        path.write_text('{"schema_version":1,"fetched_at":"2026-11-30T12:00:00+01:00","workouts":[{}]}')
        self.assertTrue((await self.get())['available'])

    async def test_concurrent_requests_share_fetch(self):
        values=await asyncio.gather(self.get(),self.get(),self.get())
        self.assertEqual(self.client.get_scheduled_workouts.call_count,2)
        self.assertEqual(values[0],values[2])

    async def test_calendar_changes_replace_instead_of_accumulating(self):
        await self.get()
        self.client.get_scheduled_workouts.return_value={'calendarItems':[item(9,'2026-12-01','Updated')]}
        value=await self.get(force=True)
        self.assertEqual([w['title'] for w in value['workouts']],['Updated'])

    async def test_optional_details_failure_does_not_hide_calendar(self):
        self.client.get_workout_by_id.side_effect=RuntimeError('private details')
        value=await self.get()
        self.assertTrue(value['available'])
        self.assertEqual(len(value['workouts']),3)
        self.assertFalse(value['workouts'][0]['steps'])

    async def test_failures_keep_last_success_with_timestamp_and_never_generate_plan(self):
        original=await self.get()
        self.client.get_scheduled_workouts.side_effect=RuntimeError('private data')
        with self.assertLogs('training_plan.context',level='WARNING') as logs:
            value=await self.get(force=True)
        self.assertTrue(value['stale'])
        self.assertEqual(value['fetched_at'],original['fetched_at'])
        self.assertNotIn('private data',str(logs.output))
        self.assertIn('gespeicherte',scheduled_training(value))

    async def test_no_cache_reports_unavailable_and_never_invents_rest_day(self):
        self.client.get_scheduled_workouts.side_effect=RuntimeError()
        value=await self.get()
        self.assertFalse(value['available'])
        self.assertEqual(value['workouts'],[])
        self.assertIn('kein gespeicherter',scheduled_training(value))

    async def test_empty_calendar_success_is_different_from_unavailable(self):
        self.client.get_scheduled_workouts.return_value={'calendarItems':[]}
        value=await self.get()
        self.assertTrue(value['available'])
        self.assertFalse(value['stale'])
        self.assertIn('Keine Einheit',scheduled_training(value))

    async def test_invalid_calendar_does_not_replace_cache(self):
        original=await self.get()
        self.client.get_scheduled_workouts.return_value={}
        value=await self.get(force=True)
        self.assertTrue(value['stale'])
        self.assertEqual(value['workouts'],original['workouts'])

    async def test_completion_requires_explicit_workout_link_and_same_day(self):
        value=await self.get()
        result=context.with_activities(value,[
            {'activity_id':7,'workout_id':101,'start_time':'2026-11-30T10:00'},
            {'activity_id':8,'workout_id':102,'start_time':'2026-11-29T10:00'}])
        self.assertEqual(result['workouts'][0]['completion'],'linked')
        self.assertEqual(result['workouts'][1]['completion'],'unconfirmed')
        self.assertNotIn('completion',value['workouts'][0])

    async def test_prompt_is_bounded_and_external_markup_escaped(self):
        value=await self.get()
        value['workouts'] *= 100
        self.assertLessEqual(len(context.prompt_context(value)),2200)
        value['workouts'][0]['title']='<b>untrusted</b>'
        from bot.delivery import telegram_html
        self.assertIn('&lt;b&gt;',telegram_html(scheduled_training(value)))


class MigrationTest(unittest.TestCase):
    def test_repeatable_copy_preserves_changed_targets_and_database_rows(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'old';source.mkdir()
            (source/'snapshot.json').write_text('{"synthetic":true}')
            with sqlite3.connect(source/'training.sqlite3') as db:
                db.execute('CREATE TABLE sample(id INTEGER PRIMARY KEY)')
                db.execute('INSERT INTO sample VALUES(1)')
            target=Path(tmp)/'new'
            self.assertEqual(migrate_files(source,target),2)
            self.assertEqual(migrate_files(source,target),2)
            with sqlite3.connect(target/'training.sqlite3') as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM sample').fetchone()[0],1)
            (target/'snapshot.json').write_text('changed')
            with self.assertRaises(ValueError):migrate_files(source,target)
            self.assertEqual((target/'snapshot.json').read_text(),'changed')
