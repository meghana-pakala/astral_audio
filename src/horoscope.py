"""
LLM horoscope generation via Gemini
Takes daily aspect text and returns structured horoscope dict
"""
import json
import logging
import os
import re
from google import genai
from aspects import format_aspects

SYSTEM_PROMPT = """You are an astrology interpreter. Given today's planetary aspects, you generate a daily horoscope and select the aspects that will shape a personalized music playlist.

Instructions:

1. Select the 3 most significant aspects for today's emotional character.
   Prioritize:
   - Personal planets (Moon, Sun, Mercury, Venus, Mars) over outer planets
   - Aspects that form a coherent emotional theme rather than contradicting each other
   - Tighter orbs over wider ones, but not at the expense of personal relevance

2. For each selected aspect provide:
   - "aspect": the aspect label exactly as given, e.g. "Natal Moon in square with transiting Saturn"
   - "meaning": 1-2 sentences. Describe the psychological and felt quality of this energy — how it shows up in mood, attention, or the texture of the day. Subtly hint at its sonic character (e.g. something restless and percussive, something slow and reverb-heavy, something bright and melodic) without making it explicitly about music.
   - "keywords": 2-3 single-word descriptors for the aspect energy

3. Synthesize into:
   - "daily_summary": 2-3 sentences. Capture the overall feeling of the day — what kind of inner weather it brings, and implicitly what it might sound like. Write for a general audience; keep it grounded and personal, but hint at the sonic character similar to the aspect descriptions. 
   - "daily_keywords": exactly 3 single-word adjectives describing today's mood. Each must be one word only — no hyphens, no phrases. Choose words that work both emotionally and sonically (e.g. "tender", "electric", "grounded", "restless", "luminous", "raw"). Avoid abstract nouns like "growth" or "maturity".

Return only valid JSON with no markdown fences:
{"daily_summary": "...",
 "daily_keywords": ["word", "word", "word"],
 "aspects": [{"aspect": "...", "meaning": "...", "keywords": ["...", "..."]},
             {"aspect": "...", "meaning": "...", "keywords": ["...", "..."]},
             {"aspect": "...", "meaning": "...", "keywords": ["...", "..."]}
             ]}"""

def _stub_horoscope(transit_aspects):
    """
    Build a valid horoscope dict from real aspects without calling Gemini.
    Uses the first 3 aspects so the rest of the pipeline runs normally.
    Enable with BYPASS_GEMINI=1 in your environment.
    """
    selected = transit_aspects[:3]
    stub_meanings = {
        'conjunction': 'These two energies merge, intensifying their shared themes.',
        'opposition':  'A push-pull dynamic invites reflection and balance.',
        'trine':       'A harmonious flow supports ease and creative expression.',
        'square':      'Friction between these planets sparks growth and action.',
        'sextile':     'A cooperative energy opens up new opportunities.',
    }
    stub_keywords = {
        'conjunction': ['electric', 'focused', 'charged'],
        'opposition':  ['restless', 'searching', 'open'],
        'trine':       ['fluid', 'warm', 'luminous'],
        'square':      ['driven', 'edgy', 'kinetic'],
        'sextile':     ['bright', 'curious', 'light'],
    }
    aspects_out = []
    all_keywords = []
    for a in selected:
        key = f'Natal {a.p1_name} in {a.aspect} with transiting {a.p2_name}'
        kws = stub_keywords.get(a.aspect, ['reflection', 'energy', 'movement'])
        aspects_out.append({
            'aspect':   key,
            'meaning':  f'{a.p1_name} and {a.p2_name}: {stub_meanings.get(a.aspect, "Notable planetary contact today.")}',
            'keywords': kws[:2],
        })
        all_keywords.extend(kws[:1])

    daily_keywords = list(dict.fromkeys(all_keywords))[:3] or ['reflection', 'flow', 'presence']
    summary_planets = ' and '.join({a.p1_name for a in selected} | {a.p2_name for a in selected})
    return {
        'daily_summary': (
            f'Today\'s chart highlights {summary_planets}, '
            'weaving a mood that calls for presence and attunement. '
            'Let the music reflect where you are right now.'
        ),
        'daily_keywords': daily_keywords,
        'aspects': aspects_out,
    }


# call Gemini to interpret aspects and generate horoscope
def _call_gemini(api_key, prompt):
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt
    )
    raw = response.text.strip()
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)
    return json.loads(raw)

def get_horoscope(transit_aspects):
    if os.environ.get('BYPASS_GEMINI', '').strip() not in ('', '0', 'false', 'False'):
        return _stub_horoscope(transit_aspects)

    primary_key = os.environ.get('GEMINI_API_KEY')
    backup_key = os.environ.get('GEMINI_API_KEY_2')
    if not primary_key:
        raise ValueError('GEMINI_API_KEY not set')

    aspects_text = format_aspects(transit_aspects)
    prompt = f"{SYSTEM_PROMPT}\n\nAspects:\n{aspects_text}"

    try:
        return _call_gemini(primary_key, prompt)
    except Exception as e:
        # retry with backup key on rate limit (429) or quota errors
        err_str = str(e).lower()
        if backup_key and any(x in err_str for x in ('429', 'quota', 'rate limit', 'resource exhausted')):
            logging.warning(f'[horoscope] Primary key hit rate limit, falling back to backup key. Error: {e}')
            return _call_gemini(backup_key, prompt)
        raise

# match selected aspects from horoscope back to transit aspect objects
def get_select_aspects(transit_aspects: list, horoscope: dict) -> list:
    selected = {a['aspect'].split(' (orb:')[0].strip() for a in horoscope.get('aspects', [])}
    return [
        a for a in transit_aspects
        if f'Natal {a.p1_name} in {a.aspect} with transiting {a.p2_name}' in selected
    ]