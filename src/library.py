"""
load music library from:
- user upload - Exportify CSV with audio features (new tracks merged into local library)
- local library - persistent pool CSV; supports genre and decade filtering
"""
import logging
import pandas as pd
from pathlib import Path
from typing import Optional

AUDIO_FEATURES = ['valence', 'energy', 'danceability', 'acousticness', 'tempo', 'mode']
REQUIRED_COLS  = ['track_uri', 'track_name', 'artist_names', 'release_date'] + AUDIO_FEATURES

# lowercase column names, replace spaces with underscores, fix plurals
def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.lower().replace(' ', '_').replace('(s)', 's') for c in df.columns]
    return df

# load Exportify CSV and return normalised df with audio feature columns
def load_user_playlist(path: str) -> pd.DataFrame:
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

# map spotify + mb genres to broad category labels used for filtering
def _categorize_genres(genre_str, mb_genre_str='') -> str:
    def _clean(s):
        if s is None or (isinstance(s, float)):
            return ''
        return str(s).replace('-', ' ')

    combined = ' '.join(filter(None, [_clean(genre_str), _clean(mb_genre_str)]))
    if not combined.strip():
        return ''
    g = combined.lower()
    categories = set()
    if 'pop' in g:
        categories.add('pop')
    if any(k in g for k in ['rock', 'punk', 'grunge', 'metal']):
        categories.add('rock')
    if any(k in g for k in ['alternative', 'punk', 'emo', 'indie']):
        categories.add('alternative')
    if any(k in g for k in ['hip hop', 'rap', 'trap', 'afrobeats']):
        categories.add('hip_hop')
    if any(k in g for k in ['r&b', 'soul', 'doo wop', 'new jack swing', 'quiet storm']):
        categories.add('r&b_soul')
    if any(k in g for k in ['electronic', 'edm', 'electro', 'synth', 'house', 'techno', 'trance', 'dubstep']):
        categories.add('electronic')
    if 'country' in g:
        categories.add('country')
    if any(k in g for k in ['folk', 'americana', 'singer songwriter', 'acoustic']):
        categories.add('folk_acoustic')
    if any(k in g for k in ['funk', 'disco']):
        categories.add('funk_disco')
    if any(k in g for k in ['jazz', 'blues']):
        categories.add('jazz_blues')
    return ','.join(sorted(categories))


# append tracks from user playlist to local library
# deduplicate on track_uri and track_name + artist_names, keeping oldest release_date
def merge_into_library(user_csv_path: str, local_library_path: str) -> int:
    try:
        user_df = _normalise_columns(pd.read_csv(user_csv_path))
        user_df = user_df.dropna(subset=AUDIO_FEATURES)
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

    existing_uris = set(local_df['track_uri'])

    # build lookup: (name, artist) -> release year, for tracks already in library
    existing_release = {
        (str(row['track_name']).lower().strip(), str(row['artist_names']).lower().strip()):
        pd.to_numeric(str(row['release_date'])[:4], errors='coerce')
        for _, row in local_df.iterrows()
        }

    truly_new, to_replace = [], []
    for _, row in user_df.iterrows():
        if row['track_uri'] in existing_uris:
            continue  # skip exact URI match
        key = (str(row['track_name']).lower().strip(), str(row['artist_names']).lower().strip())
        if key in existing_release:
            upload_year = pd.to_numeric(str(row['release_date'])[:4], errors='coerce')
            if upload_year < existing_release[key]:
                to_replace.append(key)  # replace library entry with earlier release
            continue 
        truly_new.append(row)

    new_tracks = pd.DataFrame(truly_new)

    # replace library entries where upload has an older release
    if to_replace:
        replace_keys = set(to_replace)
        local_df = local_df[~local_df.apply(
            lambda r: (str(r['track_name']).lower().strip(),
                       str(r['artist_names']).lower().strip()) in replace_keys, axis=1
                       )]
        replacements = user_df[user_df.apply(
            lambda r: (str(r['track_name']).lower().strip(),
                       str(r['artist_names']).lower().strip()) in replace_keys, axis=1
                       )]
        new_tracks = pd.concat([new_tracks, replacements], ignore_index=True)

    if new_tracks.empty:
        return 0

    new_tracks = new_tracks.copy()

    # copy mb_genres from existing library entries for matching artists
    existing_mb = (
        local_df[local_df['mb_genres'].notna() &
                 (local_df['mb_genres'].astype(str).str.strip() != '') &
                 (local_df['mb_genres'].astype(str).str.strip() != 'none')]
        .drop_duplicates('artist_names')
        .set_index('artist_names')['mb_genres']
        .to_dict()
        )
    if 'mb_genres' not in new_tracks.columns:
        new_tracks['mb_genres'] = ''
    missing_mb = new_tracks['mb_genres'].isna() | (new_tracks['mb_genres'].astype(str).str.strip() == '')
    new_tracks.loc[missing_mb, 'mb_genres'] = new_tracks.loc[missing_mb, 'artist_names'].map(existing_mb)

    # populate genre_categories from spotify + mb genres
    new_tracks['genre_categories'] = new_tracks.apply(
        lambda r: _categorize_genres(r.get('genres', ''), r.get('mb_genres', '')), axis=1
        )

    pd.concat([local_df, new_tracks], ignore_index=True).to_csv(local_library_path, index=False)
    return len(new_tracks)

# filter library by genre/decade, return original if no filters set
def apply_library_filters(df: pd.DataFrame,
                          genre_filters: Optional[list] = None,
                          decade_filters: Optional[list] = None) -> pd.DataFrame:
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

# load full music library for track scoring (user uploads merged into local library)
def load_music_library(local_library_path: str = '',
                       genre_filters: Optional[list] = None,
                       decade_filters: Optional[list] = None) -> pd.DataFrame:
    if not local_library_path or not Path(local_library_path).exists():
        raise FileNotFoundError(
            'No local music library found. '
            'Please ensure the local library file exists.'
            )

    df = load_user_playlist(local_library_path)
    df = apply_library_filters(df, genre_filters, decade_filters)
    logging.info(f'Library loaded: {len(df)} tracks')
    return df