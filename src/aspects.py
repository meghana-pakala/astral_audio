"""
get natal + transit aspects for a given birth profile and specified transit
"""
import os
from datetime import datetime
from kerykeion import AstrologicalSubject, SynastryAspects

# suppress kerykeion geonames warning
os.environ.setdefault('KERYKEION_GEONAMES_USERNAME', 'test')

# ── Planet colours used by the transit wheel ──────────────────────────────
PLANET_COLORS = {
    'Sun':     '#c8a84b',
    'Moon':    '#e8d9a8',
    'Mercury': '#aaaaaa',
    'Venus':   '#c47a8a',
    'Mars':    '#b85c38',
    'Jupiter': '#8bbf8e',
    'Saturn':  '#7ab3c8',
    'Uranus':  '#9db8d2',
    'Neptune': '#7ab3c8',
    'Pluto':   '#a08abf',
    'Chiron':  '#c47a8a',
}

# kerykeion attribute names for each planet
_PLANET_ATTRS = {
    'Sun': 'sun', 'Moon': 'moon', 'Mercury': 'mercury',
    'Venus': 'venus', 'Mars': 'mars', 'Jupiter': 'jupiter',
    'Saturn': 'saturn', 'Uranus': 'uranus', 'Neptune': 'neptune',
    'Pluto': 'pluto',
}

# which planets to pull for each ring of the wheel (all planets, no Chiron)
NATAL_PLANETS_LIST   = ['Sun', 'Moon', 'Mercury', 'Venus', 'Mars', 'Jupiter',
                         'Saturn', 'Uranus', 'Neptune', 'Pluto']
TRANSIT_PLANETS_LIST = ['Sun', 'Moon', 'Mercury', 'Venus', 'Mars', 'Jupiter',
                         'Saturn', 'Uranus', 'Neptune', 'Pluto']


def get_planet_list(subject, planet_names):
    """Return [{name, deg, color}, …] for the given kerykeion subject."""
    planets = []
    for name in planet_names:
        attr = _PLANET_ATTRS.get(name)
        if not attr:
            continue
        try:
            p = getattr(subject, attr)
            planets.append({
                'name':  name,
                'deg':   round(float(p.abs_pos), 1),
                'color': PLANET_COLORS.get(name, '#aaaaaa'),
            })
        except AttributeError:
            continue
    return planets

# limit to key aspects
VALID_ASPECTS = {'conjunction', 'opposition', 'trine', 'square', 'sextile'}

# set orb limits by planet and aspect type
ASPECT_ORBS = {
    'Moon':    {'conjunction': 8, 'opposition': 7, 'trine': 7, 'square': 6, 'sextile': 5},
    'Sun':     {'conjunction': 7, 'opposition': 6, 'trine': 6, 'square': 5, 'sextile': 4},
    'Mercury': {'conjunction': 6, 'opposition': 5, 'trine': 5, 'square': 4, 'sextile': 3},
    'Venus':   {'conjunction': 6, 'opposition': 5, 'trine': 5, 'square': 4, 'sextile': 3},
    'Mars':    {'conjunction': 6, 'opposition': 5, 'trine': 5, 'square': 4, 'sextile': 3},
    'Jupiter': {'conjunction': 4, 'opposition': 3, 'trine': 3, 'square': 3, 'sextile': 2},
    'Saturn':  {'conjunction': 3, 'opposition': 3, 'trine': 3, 'square': 2, 'sextile': 2},
    'Uranus':  {'conjunction': 3, 'opposition': 2, 'trine': 2, 'square': 2, 'sextile': 1},
    'Neptune': {'conjunction': 2, 'opposition': 2, 'trine': 2, 'square': 1, 'sextile': 1},
    'Pluto':   {'conjunction': 2, 'opposition': 1, 'trine': 1, 'square': 1, 'sextile': 1}
    }

# function to get filtered transit aspects given birth data and transit time/location
def get_transit_aspects(birth_info: dict, transit_dt: datetime = None, transit_loc: dict = None):
    """
    birth_info (dict): {date (YYYY-MM-DD), time (HH:MM), lat, lng, tz}
    transit_dt (datetime): defaults to now
    transit_loc (dict): {lat, lng, tz} defaults to birth location
    """
    birth_dt = datetime.strptime(f"{birth_info['date']} {birth_info['time']}", '%Y-%m-%d %H:%M')

    natal = AstrologicalSubject(
        name='Natal',
        year=birth_dt.year, month=birth_dt.month, day=birth_dt.day,
        hour=birth_dt.hour, minute=birth_dt.minute,
        lat=birth_info['lat'], lng=birth_info['lng'],
        tz_str=birth_info['tz'], online=False
        )

    if transit_dt is None:
        transit_dt = datetime.now()

    if transit_loc is None:
        transit_loc = {'lat': birth_info['lat'], 'lng': birth_info['lng'], 'tz': birth_info['tz']}

    transit = AstrologicalSubject(
        name='Transit',
        year=transit_dt.year, month=transit_dt.month, day=transit_dt.day,
        hour=transit_dt.hour, minute=transit_dt.minute,
        lat=transit_loc['lat'], lng=transit_loc['lng'],
        tz_str=transit_loc['tz'], online=False
        )

    aspects = []
    for a in SynastryAspects(natal, transit).relevant_aspects:
        aspect_type    = a.aspect
        natal_planet   = a.p1_name
        transit_planet = a.p2_name
        orb            = abs(a.orbit)

        if aspect_type not in VALID_ASPECTS:
            continue
        if natal_planet not in ASPECT_ORBS:
            continue
        if transit_planet not in ASPECT_ORBS:
            continue

        natal_orb   = ASPECT_ORBS[natal_planet].get(aspect_type)
        transit_orb = ASPECT_ORBS[transit_planet].get(aspect_type)
        if natal_orb is None or transit_orb is None:
            continue
        # moiety: average of each planet's orb limits
        orb_limit = (natal_orb + transit_orb) / 2
        if orb > orb_limit:
            continue

        aspects.append(a)

    # return aspects AND the two subjects so callers can extract planet positions
    return aspects, natal, transit

# format aspect list for readability and LLM input
def format_aspects(aspects):
    return '\n'.join([
        f'Natal {a.p1_name} in {a.aspect} with transiting {a.p2_name} (orb: {abs(a.orbit):.2f}°)'
        for a in aspects
        ])