"""
LLM horoscope generation via Gemini
"""
import json
import logging
import os
import re
from google import genai
from aspects import format_aspects

# define LLM prompt
SYSTEM_PROMPT = """You are an astrology interpreter. Given today's planetary aspects, generate a daily horoscope and select the aspects that will shape a personalized music playlist.

Instructions:

1. Select the 3 most significant aspects for today's emotional character.
   Prioritize:
   - Personal planets (Moon, Sun, Mercury, Venus, Mars) over outer planets
   - Aspects that form a coherent emotional theme rather than contradicting each other
   - Tighter orbs over wider ones, but not at the expense of personal relevance

2. For each selected aspect provide:
   - "aspect": the aspect label exactly as given, e.g. "Natal Moon in square with transiting Saturn"
   - "meaning": 1-2 sentences. Describe the psychological and felt quality of this energy — how it shows up in mood, attention, or the texture of the day. Subtly hint at its sonic character (e.g. something restless and percussive, something slow and reverb-heavy, something bright and melodic) without making it explicitly about music.

3. Synthesize into:
   - "daily_summary": 2-3 sentences. Capture the overall feeling of the day — what kind of inner weather it brings, and implicitly what it might sound like. Write for a general audience; keep it grounded and personal, but hint at the sonic character similar to the aspect descriptions. 
   - "daily_keywords": exactly 3 single-word adjectives describing today's mood. Each must be one word only — no hyphens, no phrases. Choose words that work both emotionally and sonically (e.g. "tender", "electric", "grounded", "restless", "luminous", "raw"). Avoid abstract nouns like "growth" or "maturity".

Return only valid JSON with no markdown fences:
{"daily_summary": "...",
 "daily_keywords": ["word", "word", "word"],
 "aspects": [{"aspect": "...", "meaning": "..."},
             {"aspect": "...", "meaning": "..."},
             {"aspect": "...", "meaning": "..."}
             ]}"""

# stub horoscope for running without API call
STUB_HOROSCOPE = {
    'daily_summary': (
        'Today brings a dynamic blend of mental clarity and emotional intensity, urging you to assert '
        'your authentic self. You might find yourself communicating with precision and purpose, while '
        'also navigating potent urges for freedom in relationships and personal values. Expect a charged '
        'atmosphere where inner feelings seek direct expression, creating a day that feels both urgent '
        'and unexpectedly liberating.'
        ),
    'daily_keywords': ['dynamic', 'assertive', 'unconventional'],
    'aspects': [
        {'aspect': 'Natal Mars in trine with transiting Mercury',
         'meaning': ('Your thoughts are sharp and decisive, making it easy to cut through mental clutter and '
                     'communicate with directness. This energy feels purposeful and quick, like a focused, '
                     'rhythmic beat driving a clear melody forward.'
                     )},
        {'aspect': 'Natal Venus in opposition with transiting Uranus',
         'meaning': ('A potent urge for freedom and authenticity in your connections and values may surface, '
                     'leading to unexpected shifts or a desire to break free from old patterns. This creates '
                     'a sparky, unpredictable atmosphere, like sudden, electrifying guitar riffs disrupting '
                     'a smooth rhythm.'
                     )},
        {'aspect': 'Natal Moon in opposition with transiting Mars',
         'meaning': ('Emotions run high, perhaps manifesting as an urgent need to assert yourself or feeling '
                     'easily provoked if your boundaries are challenged. There\'s an underlying tension, a '
                     'driving pulse that can feel both stimulating and a little restless, like a powerful, '
                     'insistent bassline.'
                     )}]
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
        return STUB_HOROSCOPE

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