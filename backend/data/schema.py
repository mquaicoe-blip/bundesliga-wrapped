"""
schema.py
=========
Canonical data models for the Bundesliga Wrapped pipeline.

All classes are plain Python dataclasses — no external ORM or serialisation
library required.  Fields are derived directly from the four data sources
confirmed during exploration:

  1. ``1K8_Bayern.xml``                       → PlayerStats, ClubStats
  2. ``feeds-exports-24-25/players/*.xml``    → PlayerStats (roster/bio)
  3. ``feeds-exports-24-25/matches/*.xml``    → MatchRecord
  4. ``bundesliga_wrapped_challenge_dataset.json`` → UserProfile, MonthlyEngagement

Cross-reference key:
  PlayerStats.player_id  == MatchRecord lineup PersonId == SeasonStat PlayerId
  ClubStats.club_id      == MatchRecord HomeTeamId / GuestTeamId
  UserProfile.user_id    == JSON user_id (strip surrounding single-quotes)

Tone type is defined here so every pipeline stage imports from one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

# ---------------------------------------------------------------------------
# Narrative tone — single parameter, passed into every Bedrock prompt.
# One field change on PersonalizationContext → entire narrative shifts.
# ---------------------------------------------------------------------------

Tone = Literal["commentator", "analyst", "fan"]


# ---------------------------------------------------------------------------
# 1. PlayerStats
#    Source: 1K8_Bayern.xml  (PlayerStatistic element)
#            feeds-exports-24-25/players/*.xml  (Object element — bio fields)
# ---------------------------------------------------------------------------

@dataclass
class PlayerStats:
    """Season statistics and biographical data for a single player.

    Stat fields come from the ``<PlayerStatistic>`` elements in
    ``1K8_Bayern.xml``.  Bio fields (name, position, nationality, physical)
    come from the per-club ``01.05.<ClubId>_<SeasonId>.xml`` roster files.
    The two are joined on ``player_id`` == ``ObjectId``.
    """

    # ── Identity ─────────────────────────────────────────────────────────────
    player_id: str = ""          # DFL-OBJ-* (primary key across all files)
    name: str = ""               # Full display name (LastName or Alias)
    first_name: str = ""
    last_name: str = ""
    short_name: str = ""         # e.g. "H. Kane"
    club_id: str = ""            # DFL-CLU-*
    club_name: str = ""          # e.g. "FC Bayern München"
    shirt_number: int = 0
    is_goalkeeper: bool = False

    # ── Position ─────────────────────────────────────────────────────────────
    # English position category from roster: "goalkeeper" | "defense" |
    # "midfield" | "offense"
    position: str = ""
    # Tactical code from match lineups: "TW", "STZ", "IVZ", etc.
    tactical_position: str = ""

    # ── Bio (from roster XML) ─────────────────────────────────────────────────
    birth_date: str = ""         # DD.MM.YYYY
    nationality: str = ""        # English nationality string
    height_cm: int = 0
    weight_kg: int = 0

    # ── Playing time ─────────────────────────────────────────────────────────
    playing_time_hms: str = ""   # HH:MM:SS (raw from XML)
    normalized_minutes: int = 0  # Minutes normalised to 90-min matches
    appearances: int = 0         # MatchesPlayedScouting
    substitutions_in: int = 0
    substitutions_out: int = 0

    # ── Goals & shooting ─────────────────────────────────────────────────────
    goals: int = 0               # ShotsAtGoalSuccessfull
    shots_total: int = 0         # ShotsAtGoalSum
    shots_on_target: int = 0     # ShotsOnTarget
    xg: float = 0.0              # Expected goals
    xg_efficiency: float = 0.0   # goals − xG (positive = overperformance)
    penalties_scored: int = 0
    own_goals: int = 0

    # ── Assists & chance creation ─────────────────────────────────────────────
    assists: int = 0             # Assists (direct)
    second_assists: int = 0      # Second assists (pre-assist)
    goal_participations: int = 0 # ParticipationsGoal (goals + assists)
    key_passes: int = 0          # AssistsShotAtGoal
    goal_opportunities: int = 0  # GoalOpportunities (shots on target created)

    # ── Passing ──────────────────────────────────────────────────────────────
    passes_total: int = 0        # PassesSum
    passes_successful: int = 0   # PassesSuccessfulSum
    pass_accuracy: float = 0.0   # Derived: passes_successful / passes_total

    # ── Crossing ─────────────────────────────────────────────────────────────
    crosses_total: int = 0
    crosses_successful: int = 0

    # ── Defending ────────────────────────────────────────────────────────────
    tackles_won: int = 0         # TacklingGamesWon
    tackles_total: int = 0       # TacklingGamesSum
    defensive_clearances: int = 0
    fouls_committed: int = 0     # FoulsSum
    fouls_suffered: int = 0
    cards_yellow: int = 0
    cards_yellow_red: int = 0
    cards_red: int = 0
    offsides: int = 0

    # ── Dribbling ────────────────────────────────────────────────────────────
    dribbles_total: int = 0      # DribblingsSum
    dribbles_successful: int = 0

    # ── Physical tracking ────────────────────────────────────────────────────
    distance_covered_m: float = 0.0   # Meters (team total ~4,056 km)
    max_speed_kmh: float = 0.0

    # ── Goalkeeping (populated only when is_goalkeeper=True) ─────────────────
    saves: int = 0               # GoalkeeperSaves
    goals_conceded: int = 0
    clean_sheets: int = 0        # CleanSheetsComplete
    shots_faced: int = 0
    penalties_saved: int = 0


# ---------------------------------------------------------------------------
# 2. ClubStats
#    Source: feeds-exports-24-25/matches/*.xml  (306 files, derived)
#            feeds-exports-24-25/01.04.Clubs.xml (metadata)
# ---------------------------------------------------------------------------

@dataclass
class ClubStats:
    """Season-level statistics for a single Bundesliga club.

    Results (wins/draws/losses/goals) are derived by aggregating the 306
    individual match XML files.  Metadata (name, colors, stadium) comes from
    ``01.04.Clubs.xml``.
    """

    # ── Identity ─────────────────────────────────────────────────────────────
    club_id: str = ""            # DFL-CLU-*
    club_name: str = ""          # e.g. "FC Bayern München"
    short_name: str = ""         # e.g. "Bayern"
    three_letter_code: str = ""  # e.g. "FCB"
    season: str = "2024-25"

    # ── Stadium ───────────────────────────────────────────────────────────────
    stadium_id: str = ""
    stadium_name: str = ""
    stadium_capacity: int = 0

    # ── Club colors (from 01.04.Clubs.xml) ───────────────────────────────────
    # Used to theme the Wrapped slides per club
    primary_color_hex: str = "#FFFFFF"
    secondary_color_hex: str = "#000000"

    # ── Season results (derived from match files) ─────────────────────────────
    matches_played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals_scored: int = 0
    goals_conceded: int = 0
    goal_difference: int = 0     # Derived: goals_scored − goals_conceded
    points: int = 0              # Derived: wins*3 + draws

    # ── Top performers (populated by scoring engine) ──────────────────────────
    top_scorer_id: str = ""      # player_id of top scorer
    top_scorer_name: str = ""
    top_scorer_goals: int = 0
    top_assister_id: str = ""
    top_assister_name: str = ""
    top_assister_assists: int = 0

    # ── Season narrative anchors ──────────────────────────────────────────────
    # Matchday of best win (highest goal margin)
    best_win_matchday: int = 0
    best_win_result: str = ""    # e.g. "8:0"
    best_win_opponent: str = ""
    # Matchday of worst loss
    worst_loss_matchday: int = 0
    worst_loss_result: str = ""
    worst_loss_opponent: str = ""
    # Longest winning streak
    longest_win_streak: int = 0


# ---------------------------------------------------------------------------
# 3. MatchRecord
#    Source: feeds-exports-24-25/matches/<MatchId>.xml
# ---------------------------------------------------------------------------

@dataclass
class MatchRecord:
    """Summary of a single Bundesliga match.

    Note: the XML files contain lineup and environment data but NO goal/card
    event timestamps — only the final ``Result`` string (e.g. "2:3").
    Drama score is computed by the scoring engine from result + context.
    """

    # ── Identity ─────────────────────────────────────────────────────────────
    match_id: str = ""           # DFL-MAT-*
    matchday: int = 0            # 1–34
    season_id: str = ""          # DFL-SEA-*
    competition_id: str = ""     # DFL-COM-000001

    # ── Teams ─────────────────────────────────────────────────────────────────
    home_team_id: str = ""       # DFL-CLU-*
    home_team_name: str = ""
    home_team_code: str = ""     # Three-letter code
    away_team_id: str = ""
    away_team_name: str = ""
    away_team_code: str = ""

    # ── Result ────────────────────────────────────────────────────────────────
    result: str = ""             # Raw string e.g. "2:3"
    home_goals: int = 0
    away_goals: int = 0
    total_goals: int = 0         # Derived: home + away

    # ── Timing ────────────────────────────────────────────────────────────────
    planned_kickoff: str = ""    # ISO 8601 UTC
    actual_kickoff: str = ""
    first_half_duration_ms: int = 0
    second_half_duration_ms: int = 0

    # ── Venue & atmosphere ────────────────────────────────────────────────────
    stadium_id: str = ""
    stadium_name: str = ""
    spectators: int = 0
    stadium_capacity: int = 0
    sold_out: bool = False
    temperature_c: int = 0
    precipitation: str = ""      # "none" | "rain" | "snow" etc.

    # ── Lineups ───────────────────────────────────────────────────────────────
    # List of PersonId strings for starting XI of each team
    home_starters: list[str] = field(default_factory=list)
    away_starters: list[str] = field(default_factory=list)
    home_formation: str = ""     # e.g. "4-3-3"
    away_formation: str = ""

    # ── Shirt colors (for slide theming) ─────────────────────────────────────
    home_shirt_color: str = ""   # Hex
    away_shirt_color: str = ""

    # ── Drama score (computed by scoring engine, not from XML) ───────────────
    # Higher = more dramatic (comeback, rivalry, late winner, etc.)
    drama_score: float = 0.0


# ---------------------------------------------------------------------------
# 4. MonthlyEngagement
#    Source: bundesliga_wrapped_challenge_dataset.json (one record per row)
# ---------------------------------------------------------------------------

@dataclass
class MonthlyEngagement:
    """One month of app engagement for a single user.

    The JSON dataset has 26,242 records across 2,765 unique users.
    Each user can have up to 12 monthly records (Jan–Dec 2025).
    All count fields are nullable in the source — stored as Optional[int].
    """

    user_id: str = ""            # SHA-256 hash (single-quotes stripped)
    month: str = ""              # YYYY-MM-DD (first of month)

    # ── Content consumption ───────────────────────────────────────────────────
    article_view_count: Optional[int] = None
    story_view_count: Optional[int] = None
    video_view_count: Optional[int] = None
    favorite_video_title: Optional[str] = None

    # ── Screen views ──────────────────────────────────────────────────────────
    screen_view_home_count: Optional[int] = None
    screen_view_table_count: Optional[int] = None
    screen_view_profile_count: Optional[int] = None
    # Match centre sub-screens
    screen_view_match_center_total_count: Optional[int] = None
    screen_view_match_center_ticker_count: Optional[int] = None
    screen_view_match_center_stats_count: Optional[int] = None
    screen_view_match_center_lineups_count: Optional[int] = None
    screen_view_match_center_table_count: Optional[int] = None


# ---------------------------------------------------------------------------
# 5. UserProfile
#    Source: bundesliga_wrapped_challenge_dataset.json (aggregated per user)
# ---------------------------------------------------------------------------

@dataclass
class UserProfile:
    """Aggregated profile for a single app user across all monthly records.

    Built by the data loader by grouping MonthlyEngagement records on user_id
    and collapsing static fields (club, demographics) with engagement totals.
    """

    # ── Identity ─────────────────────────────────────────────────────────────
    user_id: str = ""
    favorite_club: str = ""      # Club name string (e.g. "FC Bayern München")
    favorite_club_id: str = ""   # Resolved DFL-CLU-* (mapped by data loader)

    # ── Demographics ─────────────────────────────────────────────────────────
    age_group: str = ""          # "0-17"|"18-24"|"25-34"|"35-44"|"45-54"|"55+"
    country: str = ""            # ISO alpha-2
    language: str = ""           # e.g. "de_DE"
    platform: str = ""           # "iOS" | "Android"
    device_family: str = ""      # e.g. "Apple iPhone"
    gender: Optional[str] = None # "male"|"female"|"other"|None

    # ── Season engagement totals (summed across all monthly records) ──────────
    total_article_views: int = 0
    total_story_views: int = 0
    total_video_views: int = 0
    total_match_center_views: int = 0
    total_app_opens: int = 0     # Proxy: sum of screen_view_home_count
    active_months: int = 0       # Number of months with any recorded activity

    # ── Favourite content ─────────────────────────────────────────────────────
    # Most-seen video title across all monthly records (mode)
    favorite_video_title: Optional[str] = None

    # ── Engagement breakdown (for Fan DNA Score) ──────────────────────────────
    # Proportion of match-centre time spent on stats vs ticker vs lineups
    stats_focus_ratio: float = 0.0    # stats views / total match-centre views
    ticker_focus_ratio: float = 0.0
    lineups_focus_ratio: float = 0.0

    # ── Raw monthly records (kept for per-month analysis) ─────────────────────
    monthly_records: list[MonthlyEngagement] = field(default_factory=list)

    # ── Derived IDs for pipeline (populated by scoring engine) ───────────────
    # IDs of matches the user "attended" (inferred from match-centre activity
    # during the match window — populated in Section 4)
    most_watched_match_ids: list[str] = field(default_factory=list)
    # Player IDs the user engaged with most (from video titles + club mapping)
    favorite_player_ids: list[str] = field(default_factory=list)

    # ── Content preferences (for slide personalisation) ───────────────────────
    content_preferences: dict[str, Any] = field(default_factory=dict)
    # e.g. {"prefers_stats": True, "prefers_video": False, "prefers_stories": True}

    # ── App engagement frequency ──────────────────────────────────────────────
    app_opens_per_week: float = 0.0   # Derived: total_app_opens / active_weeks


# ---------------------------------------------------------------------------
# 6. WrappedSlide
#    The output unit — one per slide in the 7-slide sequence.
# ---------------------------------------------------------------------------

@dataclass
class WrappedSlide:
    """A single rendered slide in the Bundesliga Wrapped experience.

    Produced by the narrative generator (Section 5) and consumed directly
    by the React Native frontend (Section 6).
    """

    slide_id: str = ""
    # Slide type maps to the agreed 7-slide sequence:
    # "hero" | "fan_dna" | "player_bond" | "match_of_season" |
    # "season_arc" | "personal_angle" | "share"
    slide_type: str = ""

    # ── Copy ──────────────────────────────────────────────────────────────────
    headline: str = ""           # Large display text (e.g. "23 Goals Witnessed")
    subtext: str = ""            # AI-generated narrative sentence (Bedrock output)
    stat_value: str = ""         # e.g. "23"
    stat_label: str = ""         # e.g. "goals witnessed this season"

    # ── Media ─────────────────────────────────────────────────────────────────
    media_url: str = ""          # Pre-signed S3 URL (image or video thumbnail)
    media_type: str = ""         # "image" | "video_thumbnail" | "none"

    # ── Theming ───────────────────────────────────────────────────────────────
    club_color_hex: str = "#D4021D"   # Primary club colour for background
    club_color_secondary_hex: str = "#0066B2"

    # ── Animation ─────────────────────────────────────────────────────────────
    # Hint to the React Native animator:
    # "counter"   → number counts up from 0
    # "fade"      → content fades in
    # "slide_up"  → content slides up from bottom
    # "pulse"     → stat pulses once on entry
    animation_type: str = "fade"

    # ── Tone used to generate this slide's narrative ──────────────────────────
    tone: Tone = "commentator"


# ---------------------------------------------------------------------------
# 7. PersonalizationContext
#    The central object assembled by the scoring engine and passed to Bedrock.
# ---------------------------------------------------------------------------

@dataclass
class PersonalizationContext:
    """All data needed to generate a complete personalised Wrapped experience.

    Assembled in Section 4 (scoring engine) from UserProfile + ClubStats +
    PlayerStats + MatchRecord.  The ``tone`` field is the single parameter
    that shifts the entire narrative voice — no separate code paths.

    Slide mapping:
        hero_stat          → Slide 1: Hero / Identity card
        fan_dna_score      → Slide 2: Fan DNA Score
        favourite_player   → Slide 3: Player Bond
        best_match         → Slide 4: Match of the Season
        season_arc_moments → Slide 5: Season Arc Narrative
        personal_angle     → Slide 6: Personal Angle
        (assembled)        → Slide 7: Share slide
    """

    user: UserProfile = field(default_factory=UserProfile)
    club: ClubStats = field(default_factory=ClubStats)

    # Slide 1 — Hero stat
    hero_stat_label: str = ""       # e.g. "Goals witnessed"
    hero_stat_value: int = 0        # e.g. 23

    # Slide 2 — Fan DNA Score (0–100)
    fan_dna_score: int = 0
    fan_dna_breakdown: dict[str, int] = field(default_factory=dict)
    # e.g. {"loyalty": 80, "intensity": 65, "breadth": 50}
    fan_dna_archetype: str = ""     # e.g. "The Stats Geek"

    # Slide 2b — Fan Generation (viral "Listening Age" equivalent)
    fan_generation: str = ""        # e.g. "Gen Z Fan"
    fan_generation_description: str = ""  # One sentence explanation

    # Slide 2c — Monthly Timeline (for Season Arc animation)
    monthly_timeline: list[dict] = field(default_factory=list)
    # List of {"month": "2025-01", "engagement_score": 85, "peak": True, "label": "..."}

    # Slide 3 — Player Bond
    favourite_player: Optional[PlayerStats] = None
    player_bond_stat_label: str = ""   # e.g. "Goals this season"
    player_bond_stat_value: Any = None

    # Slide 4 — Match of the Season
    best_match: Optional[MatchRecord] = None
    best_match_reason: str = ""        # e.g. "comeback from 2-0 down"

    # Slide 5 — Season Arc
    season_arc_moments: list[str] = field(default_factory=list)
    # Ordered list of key moments, e.g. ["Matchday 3: first win", ...]

    # Slide 6 — Personal Angle
    personal_angle_stat: str = ""      # e.g. "You followed 4 stoppage-time deciders"

    # Narrative tone — single parameter, passed into every Bedrock prompt
    tone: Tone = "commentator"
