"""
- Define feature targets per planet
- Create target audio vector based on horoscope aspects
- Score library tracks against target ranges, return top N
"""
import pandas as pd
import numpy as np

# --- Planet Profiles ---
# valence, energy, danceability, acousticness: 0-1
# tempo_bias: BPM offset from neutral (120 BPM)
# mode: 1 = major, 0 = minor, None = no preference

PLANET_PROFILES = {
    # MOON — emotional tone, instinctive reactions, moment-to-moment feeling
    'Moon': {'valence': 0.4, 'energy': 0.5, 'danceability': 0.5,
             'acousticness': 0.3, 'tempo_bias':   -5, 'mode': None
             },
    # SUN — vitality, identity, conscious self-expression
    'Sun': {'valence': 0.7, 'energy': 0.6, 'danceability': 0.6,
            'acousticness': 0.2, 'tempo_bias': 5, 'mode': 1
            },
    # MERCURY — mind, communication, nervous energy
    'Mercury': {'valence': 0.6, 'energy': 0.8, 'danceability': 0.7,
                'acousticness': 0.1, 'tempo_bias': 15, 'mode': 1
                },
    # VENUS — aesthetic pleasure, beauty, sensory enjoyment
    'Venus': {'valence': 0.8, 'energy': 0.4, 'danceability': 0.5,
              'acousticness': 0.4, 'tempo_bias': -10, 'mode': 1
              },
    # MARS — physical drive, energy, assertiveness
    'Mars': {'valence': 0.2, 'energy': 0.9, 'danceability': 0.8,
             'acousticness': 0.1, 'tempo_bias': 25, 'mode': 0
             },
    # JUPITER — expansion, abundance, optimism
    'Jupiter': {'valence': 0.8, 'energy': 0.7, 'danceability': 0.6,
                'acousticness': 0.2, 'tempo_bias': 5, 'mode': 1
                },
    # SATURN — discipline, restriction, melancholy
    'Saturn': {'valence': 0.1, 'energy': 0.3, 'danceability': 0.3,
               'acousticness': 0.5, 'tempo_bias': -20, 'mode': 0
               },
    # URANUS — disruption, rebellion, the unexpected
    'Uranus': {'valence': 0.4, 'energy': 0.7, 'danceability': 0.6,
               'acousticness': 0.1, 'tempo_bias': 10, 'mode': None
               },
    # NEPTUNE — dreams, dissolution, transcendence
    'Neptune': {'valence': 0.5, 'energy': 0.3, 'danceability': 0.3,
                'acousticness': 0.4, 'tempo_bias': -20, 'mode': None
                },
    # PLUTO — transformation, intensity, depth
    'Pluto': {'valence': 0.1, 'energy': 0.6, 'danceability': 0.4,
              'acousticness': 0.2, 'tempo_bias': -10, 'mode': 0
              }
              }

CONTINUOUS_FEATURES = ['valence', 'energy', 'danceability', 'acousticness']

# compute target audio profile for a single aspect - average of two planets
def aspect_audio_profile(aspect):
    p1 = PLANET_PROFILES[aspect.p1_name]  # natal planet
    p2 = PLANET_PROFILES[aspect.p2_name]  # transit planet

    blended = {f: (p1[f] + p2[f]) / 2 for f in CONTINUOUS_FEATURES}
    blended['tempo_bias'] = (p1['tempo_bias'] + p2['tempo_bias']) / 2
    blended['mode_votes'] = [v for v in [p1['mode'], p2['mode']] if v is not None]

    return blended

# aggregate aspect profiles into single target audio vector
def build_target_vector(selected_aspects):
    # get profiles for each aspect
    profiles = [aspect_audio_profile(a) for a in selected_aspects]
    # weight using inverse square law: tighter orb = stronger signal
    weights  = [1 / (abs(a.orbit) ** 2 + 1) for a in selected_aspects]
    total    = sum(weights)

    target = {f: sum(p[f] * w for p, w in zip(profiles, weights)) / total
              for f in CONTINUOUS_FEATURES}
    
    # average tempo bias, shift from neutral at 120 BPM
    avg_bias = sum(p['tempo_bias'] * w for p, w in zip(profiles, weights)) / total
    target['tempo'] = 120 + avg_bias

    # mode: weighted vote- majority preference wins
    mode_score, mode_weight = 0, 0
    for p, w in zip(profiles, weights):
        for vote in p['mode_votes']:
            mode_score  += vote * w
            mode_weight += w

    if mode_weight == 0:
        target['mode'] = None
    else:
        wm = mode_score / mode_weight
        target['mode'] = 1 if wm > 0.6 else (0 if wm < 0.4 else None)

    return target


# feature weights for track scoring - reflects reliability of measurement
FEATURE_WEIGHTS = {'valence':      2.0,
                   'energy':       1.5,
                   'danceability': 1.5,
                   'acousticness': 1.0}

# score and rank tracks by distance from target vector: lower score = better match
def score_tracks(library_df, target: dict, top_n: int = 20):
    df = library_df.copy()

    # weighted Euclidean distance for continuous features
    distance = np.zeros(len(df))
    for feature, weight in FEATURE_WEIGHTS.items():
        if feature in df.columns and feature in target:
            distance += weight * (df[feature] - target[feature]) ** 2

    df['score'] = np.sqrt(distance)

    # soft mode penalty - nudges ranking without hard filter
    if target.get('mode') is not None and 'mode' in df.columns:
        df['score'] += (df['mode'] != target['mode']).astype(float) * 0.3

    return df.sort_values('score').head(top_n).reset_index(drop=True)
