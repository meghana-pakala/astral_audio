"""
get natal + transit aspects for a given birth profile and specified transit
"""
import os
from datetime import datetime
from kerykeion import AstrologicalSubject, SynastryAspects

# suppress kerykeion geonames warning
os.environ.setdefault('KERYKEION_GEONAMES_USERNAME', 'test')

# limit to key planets
PLANET_LIST = ['Sun', 'Moon', 'Mercury', 'Venus', 'Mars', 'Jupiter',
               'Saturn', 'Uranus', 'Neptune', 'Pluto']

# kerykeion returns 3-letter sign abbreviations; normalize to full names
SIGN_ABBR_TO_FULL = {
    'Ari': 'Aries', 'Tau': 'Taurus', 'Gem': 'Gemini',  'Can': 'Cancer',
    'Leo': 'Leo',   'Vir': 'Virgo',  'Lib': 'Libra',   'Sco': 'Scorpio',
    'Sag': 'Sagittarius', 'Cap': 'Capricorn', 'Aqu': 'Aquarius', 'Pis': 'Pisces',
}

# limit to key aspects
ASPECT_LIST = {'conjunction', 'opposition', 'trine', 'square', 'sextile'}

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

# function to get filtered aspects given birth data and transit time/location
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
        tz_str=birth_info['tz'], online=False,
        zodiac_type='Sidereal', sidereal_mode='LAHIRI'
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
        tz_str=transit_loc['tz'], online=False,
        zodiac_type='Sidereal', sidereal_mode='LAHIRI'
        )

    aspects = []
    for a in SynastryAspects(natal, transit).relevant_aspects:
        aspect_type    = a.aspect
        natal_planet   = a.p1_name
        transit_planet = a.p2_name
        orb            = abs(a.orbit)

        if aspect_type not in ASPECT_LIST:
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

    # return aspects and the two subjects to extract planet positions
    return aspects, natal, transit

# format aspect list for readability and LLM input
def format_aspects(aspects):
    return '\n'.join([
        f'Natal {a.p1_name} in {a.aspect} with transiting {a.p2_name} (orb: {abs(a.orbit):.2f}°)'
        for a in aspects
        ])


# --- FOR APP DESIGN ONLY ---

# planet colors for transit wheel
PLANET_COLORS = {
    'Sun':     '#c8a84b',
    'Moon':    '#e8d9a8',
    'Mercury': '#aaaaaa',
    'Venus':   '#c47a8a',
    'Mars':    '#b85c38',
    'Jupiter': '#8bbf8e',
    'Saturn':  '#7ab3c8',
    'Uranus':  '#9db8d2',
    'Neptune': '#8888cc',
    'Pluto':   '#a08abf',
}

# planet info for transit wheel
def get_planet_list(subject, planet_names):
    """Return [{name, deg, color}, …] for the given kerykeion subject."""
    planets = []
    for name in planet_names:
        try:
            p = getattr(subject, name.lower())
            planets.append({
                'name':  name,
                'deg':   round(float(p.abs_pos), 1),
                'sign':  SIGN_ABBR_TO_FULL.get(p.sign, p.sign),
                'color': PLANET_COLORS.get(name, '#aaaaaa'),
            })
        except AttributeError:
            continue
    return planets

# tooltip descriptions for planet positions table
PLANET_DESCRIPTIONS = {
    'Sun':     'core identity — who you are at your most essential',
    'Moon':    'emotional nature — what you need to feel at home in yourself',
    'Mercury': 'the mind — how you think, learn, and express yourself',
    'Venus':   'the heart — what you love, desire, and find beautiful',
    'Mars':    'drive — how you pursue what you want and assert yourself',
    'Jupiter': 'growth — where life expands and fortune finds you',
    'Saturn':  'discipline — where life asks the most of you',
    'Uranus':  'rebellion — where you break from convention and demand freedom',
    'Neptune': 'longing — what you seek beyond the material and rational',
    'Pluto':   'transformation — where you go deepest and change the most',
}

NATAL_MEANINGS = {
    'Sun':     {'Aries':'you are bold, self-driven, and at your best when leading','Taurus':'you are grounded, persistent, and built for the long game','Gemini':'you are curious, adaptable, and most alive in conversation','Cancer':'you are deeply feeling, nurturing, and rooted in the personal','Leo':'you are expressive, warm, and meant to be seen','Virgo':'you are precise, discerning, and driven by a need to improve','Libra':'you are fair-minded, relational, and drawn to beauty and balance','Scorpio':'you are intense, perceptive, and forged through transformation','Sagittarius':'you are expansive, philosophical, and always seeking more','Capricorn':'you are disciplined, ambitious, and built to achieve','Aquarius':'you are original, idealistic, and driven by a vision of what could be','Pisces':'you are empathetic, imaginative, and deeply attuned to the unseen'},
    'Moon':    {'Aries':"you feel things fast and fierce, then move on just as quickly",'Taurus':'you feel safest when life is stable, beautiful, and predictable','Gemini':'you feel through thinking — your moods shift with your mind','Cancer':"you feel everything deeply and carry others' emotions as your own",'Leo':'you feel most yourself when seen, loved, and warmly received','Virgo':"you feel better when things are in order and you've been useful",'Libra':'you feel unsettled by conflict and restored by harmony','Scorpio':'you feel with an intensity you rarely show to anyone','Sagittarius':"you feel most alive when you're free, moving, and hopeful",'Capricorn':'you feel more than you let on and process everything privately','Aquarius':"you feel best at a slight emotional distance — it's how you stay clear",'Pisces':'you feel in waves, absorbing the mood of everyone around you'},
    'Mercury': {'Aries':'your mind moves fast, decides quickly, and rarely second-guesses','Taurus':'your mind is deliberate, practical, and resistant to being rushed','Gemini':'your mind makes connections at speed and never stays still for long','Cancer':'your mind is intuitive and stores emotional detail like memory foam','Leo':'your mind thinks in stories and you communicate with natural flair','Virgo':"your mind is analytical, precise, and always looking for what's off",'Libra':'your mind weighs every angle before committing to a position','Scorpio':'your mind digs beneath the surface and rarely accepts things at face value','Sagittarius':'your mind chases ideas across the horizon and resists narrow thinking','Capricorn':'your mind is strategic, structured, and built for long-range thinking','Aquarius':'your mind is unconventional, future-focused, and hard to predict','Pisces':'your mind thinks in feelings, images, and intuitive leaps'},
    'Venus':   {'Aries':'you love boldly and pursue what you want without hesitation','Taurus':'you love through loyalty, presence, and slow-built trust','Gemini':'you love through wit, play, and the pleasure of good conversation','Cancer':'you love by nurturing deeply and remembering every detail','Leo':'you love with your whole heart and expect to be met there','Virgo':"you love through acts of care that most people wouldn't even notice",'Libra':'you love through fairness, beauty, and a deep need for reciprocity','Scorpio':"you love with an all-or-nothing intensity that doesn't do shallow",'Sagittarius':"you love freely and need a partner who won't clip your wings",'Capricorn':'you love with devotion and take commitment seriously','Aquarius':'you love with your mind first and need space to stay close','Pisces':'you love without conditions and feel everything your partner feels'},
    'Mars':    {'Aries':'your drive is immediate, competitive, and fueled by instinct','Taurus':'your drive is slow to ignite but nearly impossible to stop','Gemini':'your energy scatters across many things at once and thrives on variety','Cancer':'your drive is powered by protection — you fight hardest for others','Leo':'your ambition burns bright and you perform best with an audience','Virgo':'your drive is quiet and relentless, channeled into getting things right','Libra':'your energy moves through strategy, persuasion, and careful timing','Scorpio':'your drive is focused, covert, and built for the long pursuit','Sagittarius':'your energy is restless, optimistic, and always aimed at the next horizon','Capricorn':'your drive is disciplined, patient, and plays the long game','Aquarius':'your energy is sparked by disruption, originality, and a cause worth fighting for','Pisces':'your drive flows through creativity, empathy, and quiet persistence'},
    'Jupiter': {'Aries':'you grow through bold action, risk-taking, and going first','Taurus':'you find abundance through patience, beauty, and mastery of the material','Gemini':'you expand through learning, teaching, and following your curiosity','Cancer':'you grow through emotional depth, family, and caring for others','Leo':"you flourish when you're creating, leading, and giving generously",'Virgo':'you grow through service, refinement, and the pursuit of improvement','Libra':'you expand through partnership, collaboration, and the art of diplomacy','Scorpio':"you grow through transformation, deep research, and facing what's hidden",'Sagittarius':"you thrive when you're exploring, philosophizing, and pushing boundaries",'Capricorn':'you find growth through discipline, strategy, and earned achievement','Aquarius':'you expand through community, innovation, and championing bold ideas','Pisces':'you grow through spirituality, compassion, and creative surrender'},
    'Saturn':  {'Aries':'you\'re learning to act with courage without burning everything down','Taurus':'you\'re learning to build real security without clinging to it','Gemini':'you\'re learning to think with discipline and say only what you mean','Cancer':'you\'re learning to hold others without losing your own ground','Leo':'you\'re learning to lead and be seen without needing constant approval','Virgo':'you\'re learning that refinement has limits and done is better than perfect','Libra':'you\'re learning that real commitment requires honesty over harmony','Scorpio':'you\'re learning to face your shadow without being consumed by it','Sagittarius':'you\'re learning that real wisdom is tested, not just believed','Capricorn':'you\'re learning that ambition without rest is just fear in a suit','Aquarius':'you\'re learning to build lasting change rather than just imagining it','Pisces':'you\'re learning to live with uncertainty and still show up'},
    'Uranus':  {'Aries':'you disrupt through radical self-reinvention and refusal to be defined','Taurus':'you challenge conventional ideas of security, value, and material worth','Gemini':'you revolutionize how you think, speak, and exchange information','Cancer':'you break from inherited ideas of home, family, and emotional safety','Leo':'you express yourself in ways that challenge what self-expression even means','Virgo':'you reinvent your approach to work, health, and what it means to be useful','Libra':'you disrupt conventional ideas of relationship, fairness, and partnership','Scorpio':'you transform your relationship with power, secrecy, and what lies beneath','Sagittarius':'you break from inherited beliefs to construct your own philosophy','Capricorn':'you dismantle old structures of authority and rebuild them on your terms','Aquarius':'you redefine your role in the collective and push society forward','Pisces':'you dissolve old spiritual frameworks and reimagine what lies beyond'},
    'Neptune': {'Aries':"you're drawn to the idea of yourself as pioneer, hero, and originator",'Taurus':'you seek the sacred in beauty, nature, and the physical world','Gemini':"you're drawn to ideas that blur the line between truth and imagination",'Cancer':'you seek transcendence through emotional belonging and the idea of home','Leo':"you're drawn to art, romance, and the pursuit of something sublime",'Virgo':'you seek meaning through healing, service, and devotion to the details','Libra':"you're drawn to the ideal of perfect love and harmonious union",'Scorpio':"you seek depth beyond the visible and are drawn to what can't be named",'Sagittarius':"you're drawn to spiritual truth and seek it across cultures and traditions",'Capricorn':'you seek transcendence through purpose, legacy, and meaningful structure','Aquarius':"you're drawn to the vision of a liberated, unified humanity",'Pisces':'you seek to dissolve the self into something larger and more beautiful'},
    'Pluto':   {'Aries':'you transform through radical self-assertion and the courage to begin again','Taurus':'you transform your relationship with security, worth, and the material world','Gemini':'you transform through the death and rebirth of how you think and communicate','Cancer':'you transform through confronting the roots of your emotional life','Leo':'you transform through creative power, ego death, and owning your light','Virgo':'you transform through relentless self-refinement and service to something greater','Libra':'you transform through the collapse and rebuilding of your closest bonds','Scorpio':'you transform by going all the way into the dark and finding yourself there','Sagittarius':'you transform by dismantling belief systems that no longer hold truth','Capricorn':'you transform by tearing down false authority and rebuilding from integrity','Aquarius':'you transform through reinventing your place in the larger human story','Pisces':'you transform through surrender, dissolution, and rebirth from the formless'},
}

TRANSIT_MEANINGS = {
    'Sun':     {'Aries':'the spotlight is on bold beginnings and the courage to act first','Taurus':'the focus shifts to slowing down, grounding, and building with care','Gemini':'the energy is curious, social, and scattered in the best way','Cancer':'attention turns inward toward home, feeling, and what needs tending','Leo':'the mood is expressive, warm, and hungry for recognition','Virgo':'the focus sharpens on detail, improvement, and getting things right','Libra':'the energy favors diplomacy, beauty, and the rebalancing of relationships','Scorpio':"the mood deepens — surface answers won't satisfy right now",'Sagittarius':'the energy is expansive, restless, and pointed toward the horizon','Capricorn':"the focus turns to discipline, ambition, and what's worth building",'Aquarius':'the energy favors originality, community, and questioning the status quo','Pisces':"the mood is dreamy, compassionate, and attuned to what's unseen"},
    'Moon':    {'Aries':'emotions are quick and reactive — feelings arrive fast and leave faster','Taurus':'the emotional tone is steady, sensory, and craving comfort','Gemini':'the mood is restless and curious — feelings are fleeting and hard to pin','Cancer':'emotions run deep today and sensitivity is at its highest','Leo':'the emotional tone is warm and expressive — people need to feel seen','Virgo':'the mood is analytical — feelings get processed through doing and fixing','Libra':'the emotional tone seeks peace, connection, and fairness','Scorpio':'feelings are intense, private, and closer to the surface than they appear','Sagittarius':'the mood is optimistic and restless — heaviness feels hard to hold','Capricorn':'the emotional tone is reserved, controlled, and quietly heavy','Aquarius':'feelings are detached and observational — the mood is cool and analytical','Pisces':'the emotional tone is fluid, empathetic, and easily overwhelmed'},
    'Mercury': {'Aries':'thinking is fast, direct, and impatient with anything slow','Taurus':'communication slows down and ideas need time to take shape','Gemini':'the mental energy is sharp, quick, and hungry for stimulation','Cancer':'thinking is intuitive and colored by feeling over logic','Leo':'communication is confident, expressive, and a little theatrical','Virgo':'the mind is precise and detail-oriented — analysis comes easily','Libra':'thinking is balanced and diplomatic — every side gets considered','Scorpio':"the mind is investigative and drawn to what's beneath the surface",'Sagittarius':'thinking is big-picture and ideas flow freely without much filter','Capricorn':'communication is measured, strategic, and focused on outcomes','Aquarius':'the mind is inventive and drawn to unconventional ideas','Pisces':'thinking is impressionistic and intuition overrides logic today'},
    'Venus':   {'Aries':'desire is direct and immediate — people want what they want now','Taurus':'the energy favors pleasure, comfort, and slow sensory enjoyment','Gemini':'connection is light, playful, and fueled by good conversation','Cancer':'the mood in relationships is tender, protective, and deeply feeling','Leo':'love is generous and dramatic — affection wants to be performed','Virgo':'care is expressed through thoughtfulness, service, and small gestures','Libra':'the energy favors beauty, harmony, and genuine reciprocity','Scorpio':'attraction is intense and connections feel all-or-nothing','Sagittarius':'the mood in love is free-spirited, honest, and adventure-seeking','Capricorn':'connection is serious and steady — depth is valued over novelty','Aquarius':'the energy favors friendship, independence, and unconventional bonds','Pisces':'the mood is romantic, dissolving, and deeply compassionate'},
    'Mars':    {'Aries':'energy is high and assertive — the drive to act is impossible to ignore','Taurus':'energy is slow to build but once moving, nearly impossible to stop','Gemini':'energy is scattered and restless — multiple things demand attention at once','Cancer':'drive is fueled by emotion — people fight hardest for what they love','Leo':'energy is bold and performative — ambition wants an audience','Virgo':"drive is channeled into work, precision, and fixing what's broken",'Libra':'energy moves through negotiation — direct confrontation feels off','Scorpio':'drive is covert, focused, and playing a longer game than it appears','Sagittarius':'energy is optimistic and restless — the urge to move is strong','Capricorn':'drive is disciplined and strategic — effort is directed, not scattered','Aquarius':'energy is rebellious and principle-driven — people act on what they believe','Pisces':'drive is elusive and creative — energy flows better than it pushes'},
    'Jupiter': {'Aries':'growth comes through bold action and the willingness to go first','Taurus':'abundance flows through patience, beauty, and material steadiness','Gemini':'expansion happens through curiosity, learning, and the exchange of ideas','Cancer':'growth is found in emotional depth, home, and caring for others','Leo':'abundance flows through creative expression and generous leadership','Virgo':'growth comes through refinement, service, and meaningful improvement','Libra':'expansion happens through partnership, fairness, and diplomatic skill','Scorpio':"growth is found in transformation, research, and what's hidden",'Sagittarius':'abundance flows through exploration, philosophy, and open horizons','Capricorn':'growth comes through discipline, strategy, and earned achievement','Aquarius':'expansion happens through community, innovation, and collective vision','Pisces':'abundance flows through compassion, spirituality, and creative surrender'},
    'Saturn':  {'Aries':'the lesson is in acting with intention rather than pure impulse','Taurus':'the lesson is in building real security rather than hoarding false comfort','Gemini':'the lesson is in disciplined communication and saying only what is true','Cancer':'the lesson is in emotional responsibility and maintaining your own ground','Leo':'the lesson is in leading authentically without needing constant validation','Virgo':'the lesson is in knowing when good enough is genuinely enough','Libra':'the lesson is in choosing honesty over harmony in your closest bonds','Scorpio':"the lesson is in facing what's buried without being consumed by it",'Sagittarius':'the lesson is in testing beliefs against lived reality, not just theory','Capricorn':'the lesson is in sustainable ambition — what gets built to last','Aquarius':'the lesson is in turning visionary ideas into concrete, lasting change','Pisces':'the lesson is in finding structure within uncertainty and still showing up'},
    'Uranus':  {'Aries':'the unexpected arrives through identity, initiative, and new beginnings','Taurus':'disruption moves through material systems, value, and what feels stable','Gemini':'the unexpected arrives through communication, information, and ideas','Cancer':'disruption moves through home, family, and emotional foundations','Leo':'the unexpected arrives through creative expression and questions of ego','Virgo':'disruption moves through work, health, and daily systems','Libra':'the unexpected arrives through relationships and questions of fairness','Scorpio':"disruption moves through power, secrets, and what's been suppressed",'Sagittarius':'the unexpected arrives through belief systems and the search for meaning','Capricorn':'disruption moves through institutions, authority, and established order','Aquarius':'the unexpected arrives through technology, community, and collective change','Pisces':'disruption moves through spirituality, imagination, and the unconscious'},
    'Neptune': {'Aries':'idealism around identity and the heroic self colors the collective mood','Taurus':'a longing for beauty, simplicity, and sacred material experience runs deep','Gemini':'the line between information and illusion is harder to find than usual','Cancer':'a collective longing for home, safety, and emotional belonging runs deep','Leo':'creative and romantic idealism is in the air — art feels transcendent','Virgo':'the desire to serve something meaningful blurs into martyrdom if unchecked','Libra':'the collective is searching for ideal love and perfect harmony','Scorpio':'the veil between surface and depth is thin — nothing stays hidden long','Sagittarius':'a collective yearning for spiritual truth and higher meaning runs deep','Capricorn':'the desire to dissolve old structures in service of something greater is strong','Aquarius':'a collective dream of liberation and human unity colors the mood','Pisces':'the boundary between self and other softens — compassion and confusion travel together'},
    'Pluto':   {'Aries':'transformation is driven by radical self-assertion and the will to begin again','Taurus':'deep change moves through material systems, worth, and relationship to the earth','Gemini':'transformation is driven by how information flows and ideas rise and fall','Cancer':'deep change moves through home, ancestry, and emotional inheritance','Leo':'transformation is driven by creative power and the collapse of false ego','Virgo':'deep change moves through work, health systems, and the meaning of service','Libra':'transformation is driven by the collapse and rebuilding of how we relate','Scorpio':'deep change moves through power, sexuality, and what we collectively bury','Sagittarius':'transformation is driven by the death and rebirth of belief and meaning','Capricorn':'deep change moves through institutions, authority, and inherited power','Aquarius':'transformation is driven by technology and the reinvention of collective life','Pisces':'deep change moves through spirituality, the unconscious, and collective dissolution'},
}

