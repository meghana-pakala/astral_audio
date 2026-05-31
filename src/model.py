"""
Lasso regression model - learn aspect-driven shifts from user's baseline taste
Based on user upload (Liked Songs), using save date as signal of mood shift

Training:
- for each liked song, compute aspects active on save date
- encode aspects as a fixed-size feature vector (one slot per natal/aspect/transit combo)
- target = deviation of song's audio features from user's mean (the "mood shift")
- fit one LassoCV model per audio feature

Prediction:
- encode current aspects in same vector format
- predict delta per feature, add to user mean, get personalized target vector
"""

import pickle
import logging
import numpy as np
import pandas as pd
from itertools import product
from sklearn.linear_model import LassoCV
from sklearn.preprocessing import StandardScaler

from aspects import get_transit_aspects, PLANET_LIST, ASPECT_LIST


# audio features to predict shifts for (mode excluded bc binary)
LEARNABLE_FEATURES = ['valence', 'energy', 'danceability', 'acousticness', 'tempo']


# all possible natal/aspect/transit combinations
# use as fixed feature space so train/predict vectors align
_ALL_COMBOS = [
    f'{p1}_{asp}_{p2}'
    for p1, asp, p2 in product(PLANET_LIST, ASPECT_LIST, PLANET_LIST)
]
FEATURE_NAMES = _ALL_COMBOS  # 10 x 5 x 10 = 500 features


# encode aspects to vector using inverse orb squared (tighter orbs = larger values)
def encode_aspects(aspects: list) -> np.ndarray:
    vec = dict.fromkeys(FEATURE_NAMES, 0.0)
    for a in aspects:
        key = f'{a.p1_name}_{a.aspect}_{a.p2_name}'
        if key in vec:
            vec[key] = 1.0 / (abs(a.orbit) ** 2 + 1)
    return np.array([vec[k] for k in FEATURE_NAMES])


# build X (aspect feature matrix) and y (per-feature deltas from user mean)
# liked_df must include all learnable features + added_at
# returns: X, y_dict, user_mean - or None if not enough data
def build_training_data(liked_df: pd.DataFrame, birth_info: dict, max_samples: int = None, progress_cb=None):
    """
    max_samples: randomly sample this many songs before training — useful in
    web contexts where training all 2000 songs would be too slow. None = use all.
    """
    if 'added_at' not in liked_df.columns:
        raise ValueError("Liked songs CSV is missing 'added_at' column. Re-export from exportify.net.")

    df = liked_df.dropna(subset=['added_at'] + LEARNABLE_FEATURES).copy()
    df['added_at'] = pd.to_datetime(df['added_at'], errors='coerce', utc=True)
    df = df.dropna(subset=['added_at'])

    if len(df) < 50:
        raise ValueError(f'Not enough liked songs with valid dates ({len(df)}). Need at least 50.')

    if max_samples and len(df) > max_samples:
        df = df.sample(n=max_samples, random_state=42)
        logging.info(f'Sampled {max_samples} songs from {len(liked_df)} for training.')

    user_mean = {f: df[f].mean() for f in LEARNABLE_FEATURES}

    rows, valid_idx = [], []
    for i, (_, row) in enumerate(df.iterrows()):
        dt = row['added_at'].to_pydatetime().replace(tzinfo=None)
        try:
            aspects, _, _ = get_transit_aspects(birth_info, transit_dt=dt)
            rows.append(encode_aspects(aspects))
            valid_idx.append(i)
        except Exception as e:
            logging.debug(f'Skipping row {i}: {e}')
            continue

        if (i + 1) % 50 == 0:
            logging.info(f'  Processed {i + 1}/{len(df)} songs...')
        if progress_cb:
            progress_cb(i + 1, len(df))

    if len(rows) < 50:
        raise ValueError(f'Only {len(rows)} songs had valid aspect data. Need at least 50.')

    X = np.array(rows)
    valid_df = df.iloc[valid_idx]
    y = {f: (valid_df[f].values - user_mean[f]) for f in LEARNABLE_FEATURES}

    logging.info(f'Training data: {X.shape[0]} samples, {X.shape[1]} features')
    return X, y, user_mean


# train one LassoCV model per audio feature
# returns model bundle dict for use with predict_target_vector and save_model
def train_model(liked_df: pd.DataFrame, birth_info: dict, max_samples: int = None, progress_cb=None):
    logging.info('Building training data (this may take a few minutes)...')
    X, y, user_mean = build_training_data(liked_df, birth_info, max_samples=max_samples, progress_cb=progress_cb)

    # scale features — Lasso is sensitive to feature magnitude
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # drop zero-variance columns (combos that never appeared)
    nonzero_mask = X_scaled.std(axis=0) > 0
    X_scaled = X_scaled[:, nonzero_mask]
    active_features = [f for f, keep in zip(FEATURE_NAMES, nonzero_mask) if keep]
    logging.info(f'Active aspect features: {nonzero_mask.sum()} / {len(FEATURE_NAMES)}')

    models = {}
    for feat in LEARNABLE_FEATURES:
        lasso = LassoCV(cv=5, max_iter=20000, n_jobs=-1)
        lasso.fit(X_scaled, y[feat])
        n_nonzero = np.sum(lasso.coef_ != 0)
        logging.info(f'  {feat}: alpha={lasso.alpha_:.4f}, nonzero coefs={n_nonzero}')
        models[feat] = lasso

    return {
        'models':          models,
        'scaler':          scaler,
        'nonzero_mask':    nonzero_mask,
        'active_features': active_features,
        'user_mean':       user_mean,
        'feature_names':   FEATURE_NAMES,
    }


# given aspects and trained model bundle, returns personalized target vector
# falls back to user_mean if model predicts nothing useful
def predict_target_vector(aspects: list, bundle: dict):
  
    x = encode_aspects(aspects).reshape(1, -1)
    x_scaled = bundle['scaler'].transform(x)
    x_active = x_scaled[:, bundle['nonzero_mask']]

    target = {}
    for feat in LEARNABLE_FEATURES:
        delta = bundle['models'][feat].predict(x_active)[0]
        raw = bundle['user_mean'][feat] + delta
        # clamp 0–1 features; tempo left unclamped (reasonable BPM range)
        if feat != 'tempo':
            raw = float(np.clip(raw, 0.0, 1.0))
        target[feat] = raw

    # mode - keep rule-based (majority vote across active aspect planet pairs)
    target['mode'] = _infer_mode(aspects)

    return target

# simple majority vote on mode preference from active planet profiles
def _infer_mode(aspects: list):
    from score import PLANET_PROFILES
    votes, weights = [], []
    for a in aspects:
        for planet in [a.p1_name, a.p2_name]:
            m = PLANET_PROFILES.get(planet, {}).get('mode')
            if m is not None:
                votes.append(m)
                weights.append(1.0 / (abs(a.orbit) ** 2 + 1))
    if not votes:
        return None
    wm = np.average(votes, weights=weights)
    return 1 if wm > 0.6 else (0 if wm < 0.4 else None)


# blend model prediction with predefined target vector 
def blend_target_vectors(model_target: dict, handcoded_target: dict, model_weight: float = 0.3):
    blended = {}
    for feat in LEARNABLE_FEATURES:
        blended[feat] = model_weight * model_target[feat] + (1 - model_weight) * handcoded_target[feat]
        if feat != 'tempo':
            blended[feat] = float(np.clip(blended[feat], 0.0, 1.0))
    # mode: prefer model's inference if it has one, otherwise fall back to hand-coded
    blended['mode'] = model_target.get('mode') if model_target.get('mode') is not None else handcoded_target.get('mode')
    return blended


def save_model(bundle: dict, path: str):
    with open(path, 'wb') as f:
        pickle.dump(bundle, f)
    logging.info(f'Model saved to {path}')


def load_model(path: str) -> dict:
    with open(path, 'rb') as f:
        return pickle.load(f)
