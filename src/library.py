"""
Load music library from:
- user upload  — Exportify CSV with audio features (used directly for that session)
- local library — persistent pool CSV; supports genre and decade filtering
"""
import logging
import pandas as pd
from pathlib import Path
from typing import Optional

AUDIO_FEATURES = ['valence', 'energy', 'danceability', 'acousticness', 'tempo', 'mode']
REQUIRED_COLS  = ['track_uri', 'track_name', 'artist_names', 'release_date'] + AUDIO_FEATURES


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase column names, replace spaces with underscores, fix plural suffix."""
    df.columns = [c.lower().replace(' ', '_').replace('(s)', 's') for c in df.columns]
    return df


def load_user_playlist(path: str) -> pd.DataFrame:
    """Load an Exportify CSV. Returns a normalised DataFrame with audio feature columns."""
    try:
        df = _normalise_columns(pd.read_csv(path))
    except Exception as e:
        raise ValueError(f'Could not read CSV file: {e}')

    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f'CSV missing columns: {missing}\nMake sure you exported from exportify.net.')

    df = df.dropna(subset=AUDIO_FEATURES)
    df['spotify_id']  = df['track_uri'].str.split(':').str[-1]
    df['spotify_url'] = 'https://open.spotify.com/track/' + df['spotify_id']
    logging.info(f'Loaded {len(df)} tracks from {Path(path).name}')
    return df


def apply_library_filters(df: pd.DataFrame,
                          genre_filters: Optional[list] = None,
                          decade_filters: Optional[list] = None) -> pd.DataFrame:
    """Filter a library DataFrame by genre and/or decade. Returns unfiltered df if no matches."""
    filtered = df.copy()

    if genre_filters and 'genre_categories' in filtered.columns:
        mask = pd.Series(False, index=filtered.index)
        for g in genre_filters:
            mask |= filtered['genre_categories'].str.contains(g, case=False, na=False)
        if mask.any():
            filtered = filtered[mask]

    if decade_filters and 'release_date' in filtered.columns:
        years = pd.to_numeric(filtered['release_date'].str[:4], errors='coerce')
        mask  = pd.Series(False, index=filtered.index)
        for d in decade_filters:
            mask |= (years < 1960) if d == 'pre1960' else ((years >= int(d)) & (years < int(d) + 10))
        if mask.any():
            filtered = filtered[mask]

    return filtered


def merge_into_library(user_csv_path: str, local_library_path: str) -> int:
    """
    Append tracks from an Exportify CSV that aren't already in the local library.
    Deduplication key: track_uri.
    Returns the number of new tracks added (0 on any error).
    """
    try:
        user_df = _normalise_columns(pd.read_csv(user_csv_path))
        user_df = user_df.dropna(subset=[c for c in AUDIO_FEATURES if c in user_df.columns])
        if 'track_uri' not in user_df.columns:
            return 0
    except Exception:
        return 0

    local_path = Path(local_library_path)
    if not local_path.exists():
        user_df.to_csv(local_library_path, index=False)
        return len(user_df)

    try:
        local_df = _normalise_columns(pd.read_csv(local_library_path))
    except Exception:
        return 0

    if 'track_uri' not in local_df.columns:
        return 0

    new_tracks = user_df[~user_df['track_uri'].isin(set(local_df['track_uri'].dropna()))]
    if new_tracks.empty:
        return 0

    pd.concat([local_df, new_tracks], ignore_index=True).to_csv(local_library_path, index=False)
    return len(new_tracks)


def load_music_library(user_playlist_path: Optional[str] = None,
                       local_library_path: str = '',
                       genre_filters: Optional[list] = None,
                       decade_filters: Optional[list] = None) -> pd.DataFrame:
    """Return the best available music library as a DataFrame."""
    if user_playlist_path and Path(user_playlist_path).exists():
        try:
            df = load_user_playlist(user_playlist_path)
            logging.info('Using personal library.')
            return df
        except Exception as e:
            logging.warning(f'Could not load Exportify CSV ({e}), falling back to local library.')

    if not local_library_path or not Path(local_library_path).exists():
        raise FileNotFoundError(
            'No local music library found. '
            'Please upload your Exportify CSV or ensure the local library file exists.'
        )

    df = load_user_playlist(local_library_path)
    df = apply_library_filters(df, genre_filters, decade_filters)
    logging.info('Using local music library.')
    return df
