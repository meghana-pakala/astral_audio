"""
Load music library from:
- user upload - Exportify CSV with audio features (preferred)
- local library - music_library.csv (~12k tracks) - supports genre and decade filtering.
"""
import os
import pandas as pd
from pathlib import Path
from typing import Optional

AUDIO_FEATURES = ['valence', 'energy', 'danceability', 'acousticness', 'tempo', 'mode']
REQUIRED_COLS  = ['track_uri', 'track_name', 'artist_names', 'release_date'] + AUDIO_FEATURES

# upload user exported playlist
def load_user_playlist(path):
    """
    Load an Exportify CSV export.
    Returns a normalised DataFrame with lowercase feature column names.
    """
    try:
        df = pd.read_csv(path)
    except Exception as e:
        raise ValueError(f'Could not read CSV file: {e}')
    
    # standardize to lowercase, remove spaces
    df.columns = [c.lower().replace(' ', '_').replace('(s)', 's') for c in df.columns]
    
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f'CSV missing columns: {missing}\n'
                         f'Make sure you exported from exportify.net.')
    
    # drop rows with missing audio features
    df = df.dropna(subset=AUDIO_FEATURES)

    # extract Spotify track ID and build open URL
    df['spotify_id']  = df['track_uri'].str.split(':').str[-1]
    df['spotify_url'] = 'https://open.spotify.com/track/' + df['spotify_id']

    print(f'Loaded {len(df)} tracks from {Path(path).name}')
    return df

# option to filter local library by decade/genre
def apply_library_filters(df: pd.DataFrame, 
                          genre_filters: Optional[list] = None,
                          decade_filters: Optional[list] = None):
    
    filtered = df.copy()

    if genre_filters and 'genre_categories' in filtered.columns:
        mask = pd.Series(False, index=filtered.index)
        for g in genre_filters:
            mask = mask | filtered['genre_categories'].str.contains(g, case=False, na=False)
        if mask.sum() > 0:
            filtered = filtered[mask]

    if decade_filters and 'release_date' in filtered.columns:
        years = pd.to_numeric(filtered['release_date'].str[:4], errors='coerce')
        mask = pd.Series(False, index=filtered.index)
        for d in decade_filters:
            if d == 'pre1960':
                mask = mask | (years < 1960)
            else:
                start = int(d)
                mask = mask | ((years >= start) & (years < start + 10))
        if mask.sum() > 0:
            filtered = filtered[mask]

    return filtered

# merge user upload into local library (dedup by track_uri)
def merge_into_library(user_csv_path: str, local_library_path: str) -> int:
    """
    Normalize user upload and append any tracks not already in the local library.
    Deduplication key: track_uri.
    Returns the number of new tracks added (0 on any error).
    """
    try:
        user_raw = pd.read_csv(user_csv_path)
        user_raw.columns = [
            c.lower().replace(' ', '_').replace('(s)', 's') for c in user_raw.columns
        ]
        user_raw = user_raw.dropna(subset=[c for c in AUDIO_FEATURES if c in user_raw.columns])
        if 'track_uri' not in user_raw.columns:
            return 0
    except Exception:
        return 0

    if not Path(local_library_path).exists():
        user_raw.to_csv(local_library_path, index=False)
        return len(user_raw)

    try:
        local_raw = pd.read_csv(local_library_path)
        local_raw.columns = [
            c.lower().replace(' ', '_').replace('(s)', 's') for c in local_raw.columns
        ]
    except Exception:
        return 0

    if 'track_uri' not in local_raw.columns:
        return 0

    existing_uris = set(local_raw['track_uri'].dropna())
    new_tracks = user_raw[~user_raw['track_uri'].isin(existing_uris)]

    if len(new_tracks) == 0:
        return 0

    combined = pd.concat([local_raw, new_tracks], ignore_index=True)
    combined.to_csv(local_library_path, index=False)
    return len(new_tracks)


# load music library from best source, apply filters to local file
def load_music_library(user_playlist_path: Optional[str] = None,
                       local_library_path: str = '',
                       genre_filters: Optional[list] = None,
                       decade_filters: Optional[list] = None
                       ):
    if user_playlist_path and Path(user_playlist_path).exists():
        try:
            df = load_user_playlist(user_playlist_path)
            print('Using personal library.')
            return df
        except Exception as e:
            print(f'Could not load Exportify CSV ({e}), falling back to local library.')

    if not local_library_path or not Path(local_library_path).exists():
        raise FileNotFoundError(
            'No local music library found. '
            'Please upload your Exportify CSV or ensure the local library file exists.'
            )

    df = load_user_playlist(local_library_path)
    df = apply_library_filters(df, genre_filters, decade_filters)
    print('Using local music library.')
    return df
