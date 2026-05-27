"""
LLM horoscope generation via Gemini
Takes daily aspect text and returns structured horoscope dict
"""
import json
import os
import re
from google import genai
from aspects import format_aspects

SYSTEM_PROMPT = """You are an astrology interpreter using planetary aspects to generate a daily horoscope and music playlist.

Instructions:
1. Select the 3 most significant aspects for today's emotional and sonic character.
   Prioritize:
   - Personal planets (Moon, Sun, Mercury, Venus, Mars) over outer planets
   - Aspects that form a coherent emotional theme rather than contradicting each other
   - Tighter orbs over wider ones, but not at the expense of personal relevance

2. For each selected aspect provide:
   - "aspect": e.g. "Natal Moon in square with transiting Saturn"
   - "meaning": 1-2 sentence interpretation
   - "keywords": 2-3 keywords describing the aspect energy

3. Then synthesize into:
   - "daily_summary": 2-3 sentences capturing the overall energy of the day
   - "daily_keywords": 3 keywords representing today's overall mood
   - "aspects": the 3 selected aspects with meanings and keywords

Return only valid JSON:
{"daily_summary": "...",
 "daily_keywords": ["...", "...", "..."],
 "aspects": [{"aspect": "...", "meaning": "...", "keywords": ["...", "..."]},
             {"aspect": "...", "meaning": "...", "keywords": ["...", "..."]},
             {"aspect": "...", "meaning": "...", "keywords": ["...", "..."]}
             ]}"""

# call Gemini to interpret aspects and generate horoscope
def get_horoscope(transit_aspects):
    if os.environ.get('BYPASS_GEMINI', '').strip() not in ('', '0', 'false', 'False'):
        return _stub_horoscope(transit_aspects)

    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise ValueError('GEMINI_API_KEY not set')
    
    client = genai.Client(api_key=api_key)
    aspects_text = format_aspects(transit_aspects)

    prompt = f"{SYSTEM_PROMPT}\n\nAspects:\n{aspects_text}"
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt
        )
    
    raw = re.sub(r'^```json\s*|```$', '', response.text.strip())
    result = json.loads(raw)
    
    return result

# match selected aspects from horoscope back to transit aspect objects
def get_select_aspects(transit_aspects: list, horoscope: dict):
    # strip orb from returned string
    selected = [a['aspect'].split(' (orb:')[0].strip()
                for a in horoscope.get('aspects', [])]
    return[
        a for a in transit_aspects
        if f'Natal {a.p1_name} in {a.aspect} with transiting {a.p2_name}' in selected]
