# Astral Audio

Astral Audio is a daily playlist generator that maps your astrological transits to audio features and surfaces songs that match your energetic state for the day.

Astrology has always been a system for mapping cosmic patterns to human experience, and music has always been a medium through which human experience is shared. This project combines the two into a data problem: if planetary configurations correlate with mood and energy, and audio features describe the emotional character of a song, then the sky should tell you something about what music you'll connect with on any given day.

**[Find your astral frequency →](https://astral-audio.onrender.com)**

---

## How It Works

1. Natal & Transit Charts (kerykeion)
   - Compute natal and current planetary positions
   - Filter to active aspects within moiety orb limits
2. LLM Aspect Selection (Gemini Flash)
   - Call Gemini to select the most emotionally coherent aspects
   - Returns daily horoscope + aspect interpretations
3. Target Audio Vector
   - Calculate audio profile for each aspect given predefined planetary audio features
   - Blend aspects into a target audio vector, weighted by orb tightness
4. Personal Lasso Model (optional)
   - Given a user upload, trains a Lasso regression model to learn baseline music taste
   - Model targets are blended 30/70 with the predefined vector
5. Score & Rank
   - Scores tracks based on weighted Euclidean distance from target vector
   - Top 20 tracks returned as playlist 
6. User Feedback / Manual Personalization
   - View audio feature values and adjust with sliders
   - Rate the given tracks with built in like/dislike buttons
   - Removes disliked songs and rescores with adjusted values

---

## The Astro-Logic

A natal chart is a snapshot of the sky at the moment you were born. A transit chart is a map of planet positions in the current sky. An aspect is a meaningful geometric angle formed when a planet in today's sky interacts with a planet in your natal chart. Every planet carries a distinct character across astrological traditions, and aspects are interpreted as energetic influences - they describe which parts of your chart are being activated right now.

### Aspects and Harmony

Johannes Kepler argued in *Harmonices Mundi* (1619) that the same ratios governing musical consonance also govern the geometric relationships between planetary positions. The aspects are defined by the same integer divisions that produce the natural harmonic series, giving us a principled basis for audio feature mapping rather than relying on purely symbolic associations.

| Planetary Aspect | Harmonic Ratio | Character |
|---|---|---|
| Conjunction (0°) | 1:1 - unison | Perfect fusion, amplified energy |
| Opposition (180°) | 2:1 - octave | Polarity, unresolved tension |
| Trine (120°) | 3:2 - perfect fifth | Flow, ease, consonance |
| Square (90°) | 4:3 - perfect fourth | Friction, activation, drive |
| Sextile (60°) | 6:5 - minor third | Warm, cooperative, understated |

When a square is active, we're not just saying "tension therefore sad music" - we're saying the geometric relationship corresponds to the same mathematical ratio that music theory identifies as the boundary between consonance and dissonance.

### Orbs and Signal Strength

Planets are rarely at exactly 90° or 120°. An orb is the allowable margin of deviation for each planet, and moiety is the average orb allowance for two planets in aspect.

Rather than using a flat cutoff, each planet gets its own orb allowance based on orbital speed and astrological significance. Faster planets get wider orbs because their aspects are temporally specific and personally immediate, creating genuine day-to-day variation. Slower planets get tighter orbs because their influence is more diffuse and long-lasting, creating meaningful aspects only when nearly exact.

Once an aspect is identified, its moiety determines how strongly it influences the audio target. Both physics and astrology treat proximity as a nonlinear influence - gravitational and electromagnetic forces both follow the inverse square law (double the distance, quarter the influence). Applied to orbs: `signal_strength = 1 / (orb² + 1)`

A Venus trine Saturn at 0.06° carries near-full weight. The same aspect at 3° carries about 10%. Influence fades continuously rather than cutting off at a hard threshold.

---

## Audio Feature Mapping

Each planet is encoded as a profile across six audio features:

- **Valence** (0–1): musical positivity, from dark/tense to bright/euphoric
- **Energy** (0–1): intensity and activity level, from ambient to driving
- **Danceability** (0–1): rhythmic regularity and groove
- **Acousticness** (0–1): production sound, from electronic to acoustic/natural
- **Tempo** (BPM): continuous, typically 50–200
- **Mode** (0/1): minor vs. major

Each aspect involves a natal and transit planet, and its audio profile is the average of the two planet profiles - reflecting that an aspect is a conversation between energies rather than the expression of either alone.

Valence maps to consonance: high-consonance aspects (trine, conjunction) pull valence up; high-dissonance aspects (square, opposition) pull it down. Energy maps to activation: hard aspects drive energy up, soft aspects let it settle.

The three selected aspect profiles are then blended into a single target vector, weighted by signal strength.

**Excluded Features:** speechiness, instrumentalness, liveness, loudness, and key are dropped. The first two lack consistent distribution across library tracks and add noise; the rest are either unreliably measured or categorical in ways that don't translate cleanly to a continuous target.

### Scoring

Tracks are scored by weighted Euclidean distance from the target vector - lower score = closer match.

| Feature | Weight | Rationale |
|---------|--------|-----------|
| Valence | 2.0× | Most perceptually salient |
| Energy | 1.5× | High listener sensitivity |
| Danceability | 1.5× | Rhythmic feel is immediately noticeable |
| Acousticness | 1.0× | Real but secondary signal |
| Mode | soft penalty | Nudges ranking, doesn't exclude |

### Personal Model

The hand-coded vector captures universal astrological logic but knows nothing about individual taste. The recommended user input is an Exportify CSV of Liked Songs to train a personalized Lasso regression model.

**Training Signal:** Each Liked Song has an `added_at` date - the day the user saved it, treated as a weak proxy for mood. The assumption is that the audio features of a song saved on a given day reflect what the user wanted to hear that day.

**Feature Engineering:** For each save date, active aspects are encoded as a sparse vector - one slot per possible combination (natal planet, aspect type, transit planet), valued at `1 / (orb² + 1)`. Most slots are 0 on any given day.

**Target:** The deviation of each song's audio features from the user's personal mean. Training on deltas anchors the model to the user's taste range - it only needs to explain mood shifts, not absolute preferences.

**Model:** One `LassoCV` per audio feature. Lasso suits this well: the feature space is sparse, the dataset is typically small, and the L1 penalty zeroes out aspect combinations that aren't predictive.

**Blend:** Model prediction is blended with the hand-coded vector at 30/70. This is intentionally conservative - the save-date signal is noisy, and the blend lets the model nudge output toward personal taste without overriding the astrological logic.

After receiving the playlist, the user can manually adjust audio features and like/dislike songs - this shifts the target vector and rescores in-session, allowing a layer of real-time personalization.

---

## Limitations & Future Direction

### Data & Personalization

The Exportify approach adds friction but is a deliberate design choice: it sidesteps Spotify API restrictions that limit developer access to playlist downloads, 50 recently played tracks, and rough top-track aggregates - not enough behavioral signal to meaningfully inform the model.

Save dates are a weak training signal because people save songs for many reasons unrelated to their mood that day. This is reflected in low R² across model features - the model nudges results but cannot make confident predictions, hence the conservative 30/70 blend.

Personalization would meaningfully improve with Extended Listening History, a full streaming history available on request from Spotify. That data would enable stronger signals:

- Listening Frequency - repeated plays within a session are deliberate, mood-driven behavior
- Listening Streaks - returning to songs across multiple days during the same transit period is a stronger signal than a one-time save
- Skipped Tracks - a strong negative signal, especially for songs that are played on other days

The model learns best when it has multiple data points clustered within the same transit period - that's when it can identify "during this aspect configuration, this user consistently gravitates here."

### Audio Feature Limits

Audio features describe the sonic mechanics of a song - they don't capture meaning, association, or emotional resonance. "Here Comes the Sun" and a Vivaldi concerto might score similarly on valence, energy, and acousticness but feel completely different. Two songs can be emotionally identical and numerically far apart in the feature space.

Semantic embeddings would address this more directly, encoding emotional similarity rather than sonic mechanics. Songs could be clustered by genre context, lyrical themes, cultural associations, and listening context, such that tracks similar in mood end up close in that space regardless of BPM or acousticness. This approach would let you directly ask "what songs feel like a Venus-Neptune trine" rather than translating that aspect into an audio feature target. 

This would require training embeddings on astrologically-labeled data (which doesn't really exist) or bridging from aspect descriptions to a semantic embedding space - likely via an LLM.

### Feasible Next Step

Two-User Playlists - separate library uploads per user, both charts computed, target vectors blended, playlist drawn from songs both libraries share

---

## Background

This project grew out of [AnaLyrics](https://github.com/meghana-pakala/capstone), an attempt at classifying song genres from lyrics using NLP and audio features. That project hit the ceiling of what a classification approach could do alone. This one uses those same audio features as a matching target rather than a genre proxy - a different question that is better suited to the structure of the data.

The "astrology was the original data science" framing isn't entirely tongue-in-cheek. Both attempt to find signal in the noise of human experience - the difference is just the geometry of outer space versus a feature space.

---

## Project Structure

```
astral_audio/
├── app.py               # Flask web app
├── src/
│   ├── aspects.py       # natal/transit chart computation, orb filtering
│   ├── horoscope.py     # Gemini integration, aspect selection
│   ├── score.py         # planet profiles, target vector, track scoring
│   ├── library.py       # music library loading and merging
│   └── model.py         # Lasso model training, prediction, blending
├── music_library/
│   └── local_library.csv
├── pipeline.ipynb       # full pipeline walkthrough
└── README.md
```
