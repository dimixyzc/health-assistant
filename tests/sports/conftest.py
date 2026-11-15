"""Fabricated profiles only; never depend on the owner's private training files."""
import json
import pytest


@pytest.fixture(autouse=True)
def synthetic_profile(tmp_path, monkeypatch):
    legacy = []
    for i in range(6):
        legacy.append({'name': 'Langhantel-Kniebeuge / Back Squat' if i == 2 else f'Synthetic exercise {i}',
                       'sets': 2, 'reps': '8–12', 'load_kg': 13.0 if i == 2 else None,
                       'rest_seconds': 60, 'pair_id': 'ABC'[i//2], 'notes': 'Synthetic fixture.'})
    pairs = [{'numberOfIterations':2,'workoutSteps':[
        {'exerciseName':'SYNTHETIC_LIFT','endConditionValue':8,'description':'8–12 Wdh.'},
        {'exerciseName':'SYNTHETIC_PULL','endConditionValue':8,'description':'8–12 Wdh.'},
        {'endConditionValue':75},
    ]} for _ in range(3)]
    profile = {'schema_version':1,'start':'2026-11-11',
               'splits':{'0':['Beine', [['Synthetic leg exercise',False]]],
                         '2':['Brust Rücken Core', [['Synthetic press',False]]],
                         '4':['Schultern Arme Core', [['Synthetic curl',True]]]},
               'legacy_exercises':{str(day):legacy for day in (0,2,4)},
               'publish_templates':{
                   'cardio':{'workoutName':'SkiErg – Wiedereinstieg','estimatedDurationInSecs':1800,
                             'workoutSegments':[{'workoutSteps':[{'endConditionValue':1500},{'endConditionValue':300}]}]},
                   'strength':{'workoutSegments':[{'workoutSteps':pairs}]}},
               'description_targets':{'BARBELL_BACK_SQUAT':'Ziel 13 kg (synthetisch).'}}
    path = tmp_path/'profile.json'
    path.write_text(json.dumps(profile))
    monkeypatch.setenv('TRAINING_PROFILE_PATH', str(path))
    return profile
