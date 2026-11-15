"""Book-based schedule from 2026-11-11; exercise selection is individualized."""
from datetime import date, timedelta
from .models import Exercise, Workout

from .profile import load_profile

START = date.fromisoformat(load_profile(required=False).get('start', '1970-01-01'))
SOURCE = 'Huberman, Protocols, chapter 2, Exercise Protocols 2 and 3; private local reference'


def build_huberman_week(monday: date, *, target: bool = False) -> list[Workout]:
    """Target requires an explicit choice; passage of time never enables hard intervals."""
    if monday.weekday() != 0:
        raise ValueError('monday must be a Monday')
    profile = load_profile()
    splits = {int(day): value for day, value in profile['splits'].items()}
    start = date.fromisoformat(profile['start'])
    result = []
    for offset in range(7):
        day = monday + timedelta(days=offset)
        if day < start or offset == 5:
            continue
        if offset in splits:
            title, movements = splits[offset]
            exercises = tuple(Exercise(name, 2, ('8–15' if iso else '6–10') if target else '10–12', None,
                                       rest_seconds=120 if iso else 180,
                                       notes=('Bis zur Grenze sauberer Technik; keine erzwungenen Wiederholungen.' if target
                                              else 'Leichte Last, etwa 5 saubere Wiederholungen in Reserve.'))
                              for name, iso in movements)
            result.append(Workout(day.isoformat(), 'strength', title,
                'Etwa 5 Min. Ganzkörper erwärmen; Radanfahrt kann dies abdecken. Zusätzlich 1–3 spezifische Aufwärmsätze je Übung, 1–2 Min. Pause.',
                exercises=exercises, main_set='Übungen nacheinander, keine Pflicht-Supersätze. Grundübungen 3–5 Min., Isolation 90–180 s Pause.',
                cooldown='3–5 Min. ruhig ausatmen.', estimated_minutes=75,
                source=SOURCE, rationale='Buchsplit; konkrete Übungen individuell gewählt. Zwei Arbeitssätze je Übung.',
                warnings=('Bei Knieschmerz, Schwellung oder Instabilität stoppen. Last neu bestimmen; alte Lasten sind keine Wiedereinstiegsvorgabe.',)))
        else:
            if offset == 6:
                minutes = 45 if target else 20
                title = 'Lange ruhige Ausdauer — Rad oder Crosstrainer'
                main = f'{minutes} Min. kontinuierlich. Gespräch noch möglich; Buchziel 45–75 Min., etwa 60–70 % HFmax.'
                warm = 'Locker beginnen, dann gleichmäßige Belastung.'
                total = minutes + 5
            elif offset == 1:
                minutes = 25 if target else 20
                title = 'Mittlere Ausdauer — Crosstrainer oder Rad'
                main = (f'{minutes} Min. zügig und kontinuierlich, etwa 75–85 % HFmax; nicht sprinten.' if target else
                        '20 Min. locker bis moderat, ohne Luftnot. Einstiegsanpassung; Buchziel später 25–30 Min. bei 75–85 % HFmax.')
                warm = '5 Min. locker auf dem gewählten Gerät.'
                total = minutes + 10
            else:
                title = 'Kurze intensive Ausdauer — Ergometer' if target else 'Vorbereitung auf Intervalle — Ergometer'
                main = ('6 Runden: 30 s sehr hart, 60 s locker; später bis 12 Runden. Buchziel 90–95 % HFmax in harten Phasen, nicht durch zusätzlichen Widerstand einem verzögerten Puls hinterherjagen.' if target else
                        '15 Min. locker bis moderat, keine Sprints. Bewusste Einstiegsabweichung vom intensiven Buchprotokoll.')
                warm = '10 Min. locker, allmählich etwas zügiger.'
                total = 24 if target else 30
            result.append(Workout(day.isoformat(), 'cardio', title, warm, main_set=main,
                cooldown='5 Min. locker ausfahren.', estimated_minutes=total, source=SOURCE,
                rationale='Drei unterschiedliche Cardioreize gemäß Buch; Einstieg getrennt vom Zielumfang.',
                warnings=('Keine absoluten Pulsziele ohne belastbare HFmax. Ziel-HIIT erst nach vertragenem Wiedereinstieg.',)))
    return result
