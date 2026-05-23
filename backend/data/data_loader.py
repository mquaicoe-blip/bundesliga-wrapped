"""
data_loader.py
==============
Functions for loading and parsing hackathon data from S3 into schema dataclasses.

Each loader:
  - Reads from S3 via get_s3_client() (no local file assumptions)
  - Parses the raw XML or JSON into typed dataclasses
  - Caches results in a module-level dict to avoid redundant S3 fetches
  - Logs at INFO level so progress is visible in notebooks and pipeline runs

Data sources (all under CHALLENGE_PREFIX in S3):
  data/1K8_Bayern.xml                          → load_club_season_stats()
  data/feeds-exports-24-25/players/*.xml       → load_player_roster()
  data/feeds-exports-24-25/matches/*.xml       → load_match(), load_all_matches()
  data/bundesliga_wrapped_challenge_dataset.json → load_user_profiles()
"""

from __future__ import annotations

import io
import json
import logging
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Optional

from backend.config.aws_config import CHALLENGE_PREFIX, _get_bucket_name, get_s3_client
from backend.data.schema import (
    ClubStats,
    MatchRecord,
    MonthlyEngagement,
    PlayerStats,
    UserProfile,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level caches — avoids re-fetching the same S3 object twice per run.
# Keys are S3 object keys or logical identifiers (club_id, match_id, etc.)
# ---------------------------------------------------------------------------
_cache_player_roster: dict[str, list[PlayerStats]] = {}   # keyed by club_id
_cache_match: dict[str, MatchRecord] = {}                  # keyed by match_id
_cache_all_matches: Optional[list[MatchRecord]] = None
_cache_user_profiles: Optional[dict[str, UserProfile]] = None
_cache_club_season_stats: Optional[dict[str, PlayerStats]] = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _s3_get_text(s3_key: str) -> str:
    """Download an S3 object and return its content as a UTF-8 string.

    We stream directly into memory rather than writing to disk so the loader
    works in any environment (Lambda, SageMaker, local) without filesystem
    assumptions.

    Args:
        s3_key: Full S3 object key.

    Returns:
        Decoded string content of the object.
    """
    bucket = _get_bucket_name()
    s3 = get_s3_client()
    logger.info("Fetching s3://%s/%s", bucket, s3_key)
    response = s3.get_object(Bucket=bucket, Key=s3_key)
    return response["Body"].read().decode("utf-8")


def _s3_get_bytes(s3_key: str) -> bytes:
    """Download an S3 object and return raw bytes (for binary files)."""
    bucket = _get_bucket_name()
    s3 = get_s3_client()
    logger.info("Fetching bytes s3://%s/%s", bucket, s3_key)
    response = s3.get_object(Bucket=bucket, Key=s3_key)
    return response["Body"].read()


def _challenge_key(relative_path: str) -> str:
    """Build a full S3 key from a path relative to the challenge root."""
    return f"{CHALLENGE_PREFIX}/{relative_path.lstrip('/')}"


def _safe_int(value: Optional[str], default: int = 0) -> int:
    """Parse a string to int, returning default on None or parse failure."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _safe_float(value: Optional[str], default: float = 0.0) -> float:
    """Parse a string to float, returning default on None or parse failure."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# Club ID → name mapping (from DATA_REFERENCE.md — avoids an extra S3 fetch)
# ---------------------------------------------------------------------------

CLUB_ID_TO_NAME: dict[str, str] = {
    "DFL-CLU-00000G": "FC Bayern München",
    "DFL-CLU-000007": "Borussia Dortmund",
    "DFL-CLU-00000B": "Bayer 04 Leverkusen",
    "DFL-CLU-000017": "RB Leipzig",
    "DFL-CLU-00000F": "Eintracht Frankfurt",
    "DFL-CLU-00000D": "VfB Stuttgart",
    "DFL-CLU-00000A": "Sport-Club Freiburg",
    "DFL-CLU-00000E": "SV Werder Bremen",
    "DFL-CLU-000004": "Borussia Mönchengladbach",
    "DFL-CLU-000003": "VfL Wolfsburg",
    "DFL-CLU-000006": "1. FSV Mainz 05",
    "DFL-CLU-000010": "FC Augsburg",
    "DFL-CLU-00000V": "1. FC Union Berlin",
    "DFL-CLU-000002": "TSG Hoffenheim",
    "DFL-CLU-000018": "1. FC Heidenheim 1846",
    "DFL-CLU-00000H": "FC St. Pauli",
    "DFL-CLU-00000S": "VfL Bochum 1848",
    "DFL-CLU-000N5P": "Holstein Kiel",
}

# Reverse map: club name → club_id (for resolving UserProfile.favorite_club)
CLUB_NAME_TO_ID: dict[str, str] = {v: k for k, v in CLUB_ID_TO_NAME.items()}


# ---------------------------------------------------------------------------
# 1. load_club_season_stats
#    Source: data/1K8_Bayern.xml
#    Returns per-player season stats for FC Bayern (the only club with this
#    detailed breakdown in the dataset).
# ---------------------------------------------------------------------------

def load_club_season_stats() -> dict[str, PlayerStats]:
    """Load cumulative season statistics for FC Bayern München.

    Parses ``data/1K8_Bayern.xml`` which contains one ``<PlayerStatistic>``
    element per player with ~166 attributes covering goals, passes, duels,
    physical tracking, and goalkeeping.

    The result is cached after the first call — subsequent calls return the
    cached dict without hitting S3 again.

    Returns:
        Dict mapping player_id (DFL-OBJ-*) → PlayerStats.
    """
    global _cache_club_season_stats
    if _cache_club_season_stats is not None:
        # Return cached result — avoids re-parsing the large XML on every call
        logger.debug("Returning cached Bayern season stats (%d players).",
                     len(_cache_club_season_stats))
        return _cache_club_season_stats

    key = _challenge_key("data/1K8_Bayern.xml")
    xml_text = _s3_get_text(key)
    root = ET.fromstring(xml_text)

    # The XML structure is:
    # PutDataRequest > SeasonStatistic > TeamStatistic > PlayerStatistic*
    stats: dict[str, PlayerStats] = {}

    for ps in root.iter("PlayerStatistic"):
        a = ps.attrib  # shorthand — all data lives in XML attributes

        player_id = a.get("PlayerId", "")
        if not player_id:
            continue  # skip malformed elements

        passes_total = _safe_int(a.get("PassesSum"))
        passes_ok = _safe_int(a.get("PassesSuccessfulSum"))
        # Compute pass accuracy here rather than in the scoring engine so
        # every consumer gets a consistent value
        pass_acc = (passes_ok / passes_total) if passes_total > 0 else 0.0

        p = PlayerStats(
            player_id=player_id,
            first_name=a.get("PlayerFirstName", "").strip(),
            last_name=a.get("PlayerLastName", "").strip(),
            name=a.get("PlayerAlias") or a.get("PlayerLastName", "").strip(),
            club_id="DFL-CLU-00000G",   # Bayern — only club in this file
            club_name="FC Bayern München",
            is_goalkeeper=a.get("GoalKeeper", "false").lower() == "true",
            playing_time_hms=a.get("PlayingTime", ""),
            normalized_minutes=_safe_int(a.get("NormalizedPlayerMinutes")),
            appearances=_safe_int(a.get("MatchesPlayedScouting")),
            substitutions_in=_safe_int(a.get("SubstitutionsIn")),
            substitutions_out=_safe_int(a.get("SubstitutionsOut")),
            goals=_safe_int(a.get("ShotsAtGoalSuccessfull")),
            shots_total=_safe_int(a.get("ShotsAtGoalSum")),
            shots_on_target=_safe_int(a.get("ShotsOnTarget")),
            xg=_safe_float(a.get("xG")),
            xg_efficiency=_safe_float(a.get("xGEfficiency")),
            penalties_scored=_safe_int(a.get("PenaltiesSuccessful")),
            own_goals=_safe_int(a.get("OwnGoals")),
            assists=_safe_int(a.get("Assists")),
            second_assists=_safe_int(a.get("SecondAssists")),
            goal_participations=_safe_int(a.get("ParticipationsGoal")),
            key_passes=_safe_int(a.get("AssistsShotAtGoal")),
            goal_opportunities=_safe_int(a.get("GoalOpportunities")),
            passes_total=passes_total,
            passes_successful=passes_ok,
            pass_accuracy=round(pass_acc, 4),
            crosses_total=_safe_int(a.get("CrossesSum")),
            crosses_successful=_safe_int(a.get("CrossesSuccessfulSum")),
            tackles_won=_safe_int(a.get("TacklingGamesWon")),
            tackles_total=_safe_int(a.get("TacklingGamesSum")),
            defensive_clearances=_safe_int(a.get("DefensiveClearances")),
            fouls_committed=_safe_int(a.get("FoulsSum")),
            fouls_suffered=_safe_int(a.get("FoulsSuffered")),
            cards_yellow=_safe_int(a.get("CardsYellow")),
            cards_yellow_red=_safe_int(a.get("CardsYellowRed")),
            cards_red=_safe_int(a.get("CardsRed")),
            offsides=_safe_int(a.get("Offsides")),
            dribbles_total=_safe_int(a.get("DribblingsSum")),
            dribbles_successful=_safe_int(a.get("DribblingsSuccessful")),
            distance_covered_m=_safe_float(a.get("DistanceCovered")),
            max_speed_kmh=_safe_float(a.get("MaximumSpeed")),
            # Goalkeeping fields (non-zero only for is_goalkeeper=True)
            saves=_safe_int(a.get("GoalkeeperSaves")),
            goals_conceded=_safe_int(a.get("GoalsConceded")),
            clean_sheets=_safe_int(a.get("CleanSheetsComplete")),
            shots_faced=_safe_int(a.get("ShotsFaced")),
            penalties_saved=_safe_int(a.get("PenaltiesSaved")),
        )
        stats[player_id] = p

    logger.info("Loaded Bayern season stats: %d players.", len(stats))
    _cache_club_season_stats = stats
    return stats


# ---------------------------------------------------------------------------
# 2. load_player_roster
#    Source: data/feeds-exports-24-25/players/01.05.<ClubId>_DFL-SEA-0001K8.xml
# ---------------------------------------------------------------------------

def load_player_roster(club_id: str) -> list[PlayerStats]:
    """Load biographical player data for a club from the roster XML.

    Each roster file contains one ``<Object>`` element per player with bio
    fields: name, position, nationality, height, weight, shirt number.
    These are the fields NOT present in the season stats file.

    The result is cached per club_id.

    Args:
        club_id: DFL-CLU-* identifier (e.g. "DFL-CLU-00000G" for Bayern).

    Returns:
        List of PlayerStats with bio fields populated.
        Stats fields (goals, assists, etc.) are left at defaults — merge with
        load_club_season_stats() output using player_id as the join key.
    """
    if club_id in _cache_player_roster:
        logger.debug("Returning cached roster for %s.", club_id)
        return _cache_player_roster[club_id]

    # Filename pattern: 01.05.<ClubId>_DFL-SEA-0001K8.xml
    filename = f"01.05.{club_id}_DFL-SEA-0001K8.xml"
    key = _challenge_key(f"data/feeds-exports-24-25/players/{filename}")
    xml_text = _s3_get_text(key)
    root = ET.fromstring(xml_text)

    players: list[PlayerStats] = []
    club_name = CLUB_ID_TO_NAME.get(club_id, "")

    for obj in root.iter("Object"):
        a = obj.attrib
        if a.get("Type") != "player":
            continue  # skip non-player objects (coaches etc.)

        # Use Alias if present (e.g. "Jamal Musiala"), else fall back to Name
        display_name = a.get("Alias") or a.get("Name", "")

        p = PlayerStats(
            player_id=a.get("ObjectId", ""),
            name=display_name,
            first_name=a.get("FirstName", ""),
            last_name=a.get("LastName", ""),
            short_name=a.get("ShortName", ""),
            club_id=club_id,
            club_name=club_name,
            shirt_number=_safe_int(a.get("ShirtNumber")),
            # Position is stored in English in the roster XML
            position=a.get("PlayingPositionEnglish", ""),
            birth_date=a.get("BirthDate", ""),
            nationality=a.get("NationalityEnglish", ""),
            height_cm=_safe_int(a.get("Height")),
            weight_kg=_safe_int(a.get("Weight")),
        )
        players.append(p)

    logger.info("Loaded roster for %s (%s): %d players.", club_id, club_name, len(players))
    _cache_player_roster[club_id] = players
    return players


def load_player_stats(club_id: str) -> list[PlayerStats]:
    """Return merged PlayerStats for a club: bio + season stats where available.

    For FC Bayern (DFL-CLU-00000G), merges roster bio with season stats from
    1K8_Bayern.xml.  For all other clubs, returns roster bio only (season stats
    file only covers Bayern in this dataset).

    Args:
        club_id: DFL-CLU-* identifier.

    Returns:
        List of PlayerStats with all available fields populated.
    """
    roster = load_player_roster(club_id)

    # Only Bayern has the detailed season stats file
    if club_id != "DFL-CLU-00000G":
        return roster

    # Merge: start from season stats (richer), fill in bio from roster
    season_stats = load_club_season_stats()
    roster_by_id = {p.player_id: p for p in roster}

    merged: list[PlayerStats] = []
    for player_id, stats in season_stats.items():
        bio = roster_by_id.get(player_id)
        if bio:
            # Copy bio fields that are missing from the season stats XML
            stats.short_name = bio.short_name
            stats.position = bio.position
            stats.birth_date = bio.birth_date
            stats.nationality = bio.nationality
            stats.height_cm = bio.height_cm
            stats.weight_kg = bio.weight_kg
            stats.shirt_number = bio.shirt_number
        merged.append(stats)

    # Also include roster players who have no season stats (e.g. left mid-season)
    for player_id, bio in roster_by_id.items():
        if player_id not in season_stats:
            merged.append(bio)

    logger.info("Merged stats+roster for Bayern: %d players total.", len(merged))
    return merged


# ---------------------------------------------------------------------------
# 3. load_match / load_all_matches
#    Source: data/feeds-exports-24-25/matches/<MatchId>.xml  (306 files)
# ---------------------------------------------------------------------------

def load_match(match_id: str) -> MatchRecord:
    """Load and parse a single match XML file.

    The match XML contains lineup, environment, and result data but NO
    goal/card event timestamps — only the final Result string (e.g. "2:3").

    Args:
        match_id: DFL-MAT-* identifier (e.g. "DFL-MAT-J04034").

    Returns:
        Populated MatchRecord.
    """
    if match_id in _cache_match:
        return _cache_match[match_id]

    key = _challenge_key(f"data/feeds-exports-24-25/matches/{match_id}.xml")
    xml_text = _s3_get_text(key)
    root = ET.fromstring(xml_text)

    mi = root.find("MatchInformation")
    if mi is None:
        raise ValueError(f"No <MatchInformation> in {match_id}.xml")

    gen = mi.find("General")
    env = mi.find("Environment")
    g = gen.attrib if gen is not None else {}
    e = env.attrib if env is not None else {}

    # Parse result string "home:away" → separate ints
    result_str = g.get("Result", "0:0")
    try:
        home_g, away_g = (int(x) for x in result_str.split(":"))
    except ValueError:
        home_g, away_g = 0, 0

    # Extract lineups from both Team elements
    home_starters: list[str] = []
    away_starters: list[str] = []
    home_formation = ""
    away_formation = ""
    home_shirt = ""
    away_shirt = ""

    for team_el in mi.findall(".//Team"):
        role = team_el.attrib.get("Role", "")
        formation = team_el.attrib.get("LineUp", "")
        shirt_color = team_el.attrib.get("PlayerShirtMainColor", "")
        starters = [
            p.attrib["PersonId"]
            for p in team_el.findall(".//Player")
            if p.attrib.get("Starting", "false").lower() == "true"
        ]
        if role == "home":
            home_starters = starters
            home_formation = formation
            home_shirt = shirt_color
        else:
            away_starters = starters
            away_formation = formation
            away_shirt = shirt_color

    # Parse playing time from OtherGameInformation if present
    ogi = mi.find("OtherGameInformation")
    first_half_ms = 0
    second_half_ms = 0
    if ogi is not None:
        first_half_ms = _safe_int(ogi.attrib.get("PlayingTimeFirstHalf"))
        second_half_ms = _safe_int(ogi.attrib.get("PlayingTimeSecondHalf"))

    record = MatchRecord(
        match_id=match_id,
        matchday=_safe_int(g.get("MatchDay")),
        season_id=g.get("SeasonId", ""),
        competition_id=g.get("CompetitionId", ""),
        home_team_id=g.get("HomeTeamId", ""),
        home_team_name=g.get("HomeTeamName", ""),
        home_team_code=g.get("HomeTeamThreeLetterCode", ""),
        away_team_id=g.get("GuestTeamId", ""),
        away_team_name=g.get("GuestTeamName", ""),
        away_team_code=g.get("GuestTeamThreeLetterCode", ""),
        result=result_str,
        home_goals=home_g,
        away_goals=away_g,
        total_goals=home_g + away_g,
        planned_kickoff=g.get("PlannedKickoffTime", ""),
        actual_kickoff=g.get("KickoffTime", ""),
        first_half_duration_ms=first_half_ms,
        second_half_duration_ms=second_half_ms,
        stadium_id=e.get("StadiumId", ""),
        stadium_name=e.get("StadiumName", ""),
        spectators=_safe_int(e.get("NumberOfSpectators")),
        stadium_capacity=_safe_int(e.get("StadiumCapacity")),
        sold_out=e.get("SoldOut", "false").lower() == "true",
        temperature_c=_safe_int(e.get("Temperature")),
        precipitation=e.get("Precipitation", "none"),
        home_starters=home_starters,
        away_starters=away_starters,
        home_formation=home_formation,
        away_formation=away_formation,
        home_shirt_color=home_shirt,
        away_shirt_color=away_shirt,
    )

    _cache_match[match_id] = record
    return record


def load_match_overview() -> dict[str, MatchRecord]:
    """Load all 306 match records and return them keyed by match_id.

    This is the expensive call — it fetches 306 XML files from S3.
    Results are cached after the first call.

    Returns:
        Dict mapping match_id → MatchRecord for all 306 matches.
    """
    global _cache_all_matches
    if _cache_all_matches is not None:
        return {m.match_id: m for m in _cache_all_matches}

    from backend.data.s3_loader import list_challenge_files

    # List all match XML keys
    match_keys = [
        k for k in list_challenge_files("data/feeds-exports-24-25/matches/")
        if k.endswith(".xml")
    ]
    logger.info("Loading %d match files from S3...", len(match_keys))

    matches: list[MatchRecord] = []
    for key in match_keys:
        # Extract match_id from filename: .../matches/DFL-MAT-J04034.xml
        match_id = key.split("/")[-1].replace(".xml", "")
        try:
            matches.append(load_match(match_id))
        except Exception as exc:
            logger.warning("Failed to parse match %s: %s", match_id, exc)

    logger.info("Loaded %d matches successfully.", len(matches))
    _cache_all_matches = matches
    return {m.match_id: m for m in matches}


# ---------------------------------------------------------------------------
# 4. load_user_profiles
#    Source: data/bundesliga_wrapped_challenge_dataset.json
# ---------------------------------------------------------------------------

def load_user_profiles() -> dict[str, UserProfile]:
    """Load and aggregate all user engagement data from the JSON dataset.

    The JSON is a flat array of 26,242 monthly records across 2,765 users.
    This function:
      1. Parses each record into a MonthlyEngagement dataclass
      2. Groups records by user_id
      3. Aggregates totals and derives engagement ratios per user
      4. Resolves favorite_club name → club_id using CLUB_NAME_TO_ID

    The result is cached after the first call.

    Returns:
        Dict mapping user_id → UserProfile for all 2,765 users.
    """
    global _cache_user_profiles
    if _cache_user_profiles is not None:
        logger.debug("Returning cached user profiles (%d users).",
                     len(_cache_user_profiles))
        return _cache_user_profiles

    key = _challenge_key("data/bundesliga_wrapped_challenge_dataset.json")
    raw_text = _s3_get_text(key)
    records_raw: list[dict] = json.loads(raw_text)
    logger.info("Loaded JSON dataset: %d raw records.", len(records_raw))

    # Group monthly records by user_id
    # Strip the surrounding single-quotes that wrap the SHA-256 hash in the data
    by_user: dict[str, list[dict]] = defaultdict(list)
    for rec in records_raw:
        uid = rec.get("user_id", "").strip("'")
        by_user[uid].append(rec)

    profiles: dict[str, UserProfile] = {}

    for user_id, monthly_recs in by_user.items():
        # Build MonthlyEngagement objects for each record
        monthly: list[MonthlyEngagement] = []
        for rec in monthly_recs:
            me = MonthlyEngagement(
                user_id=user_id,
                month=rec.get("month", ""),
                article_view_count=rec.get("article_view_count"),
                story_view_count=rec.get("story_view_count"),
                video_view_count=rec.get("video_view_count"),
                favorite_video_title=rec.get("favorite_video_title"),
                screen_view_home_count=rec.get("screen_view_home_count"),
                screen_view_table_count=rec.get("screen_view_table_count"),
                screen_view_profile_count=rec.get("screen_view_profile_count"),
                screen_view_match_center_total_count=rec.get(
                    "screen_view_match_center_total_count"),
                screen_view_match_center_ticker_count=rec.get(
                    "screen_view_match_center_ticker_count"),
                screen_view_match_center_stats_count=rec.get(
                    "screen_view_match_center_stats_count"),
                screen_view_match_center_lineups_count=rec.get(
                    "screen_view_match_center_lineups_count"),
                screen_view_match_center_table_count=rec.get(
                    "screen_view_match_center_table_count"),
            )
            monthly.append(me)

        # Use the first record for static profile fields (they're consistent
        # across months for the same user)
        first = monthly_recs[0]
        fav_club_name = first.get("favorite_club", "")

        # Aggregate totals — use 0 for null values so sums are meaningful
        def _sum(field: str) -> int:
            return sum(r.get(field) or 0 for r in monthly_recs)

        total_mc = _sum("screen_view_match_center_total_count")
        total_stats = _sum("screen_view_match_center_stats_count")
        total_ticker = _sum("screen_view_match_center_ticker_count")
        total_lineups = _sum("screen_view_match_center_lineups_count")

        # Compute engagement ratios for Fan DNA Score (Section 4)
        # These tell us whether the user is a stats-nerd, live-ticker follower,
        # or lineup-obsessive — each maps to a different DNA archetype
        stats_ratio = (total_stats / total_mc) if total_mc > 0 else 0.0
        ticker_ratio = (total_ticker / total_mc) if total_mc > 0 else 0.0
        lineups_ratio = (total_lineups / total_mc) if total_mc > 0 else 0.0

        # Find most common video title (mode) — proxy for favourite player
        video_titles = [
            r.get("favorite_video_title")
            for r in monthly_recs
            if r.get("favorite_video_title")
        ]
        fav_video = max(set(video_titles), key=video_titles.count) if video_titles else None

        # Count active months (months with any recorded screen view)
        active = sum(
            1 for r in monthly_recs
            if any(r.get(f) for f in [
                "screen_view_home_count",
                "screen_view_match_center_total_count",
                "article_view_count",
            ])
        )

        profile = UserProfile(
            user_id=user_id,
            favorite_club=fav_club_name,
            # Resolve club name → DFL-CLU-* ID; empty string if not in Bundesliga
            favorite_club_id=CLUB_NAME_TO_ID.get(fav_club_name, ""),
            age_group=first.get("age_group", ""),
            country=first.get("country", ""),
            language=first.get("language", ""),
            platform=first.get("platform", ""),
            device_family=first.get("device_family", ""),
            gender=first.get("gender"),
            total_article_views=_sum("article_view_count"),
            total_story_views=_sum("story_view_count"),
            total_video_views=_sum("video_view_count"),
            total_match_center_views=total_mc,
            total_app_opens=_sum("screen_view_home_count"),
            active_months=active,
            favorite_video_title=fav_video,
            stats_focus_ratio=round(stats_ratio, 4),
            ticker_focus_ratio=round(ticker_ratio, 4),
            lineups_focus_ratio=round(lineups_ratio, 4),
            monthly_records=monthly,
            # app_opens_per_week: approximate (active_months * 4.3 weeks/month)
            app_opens_per_week=round(
                _sum("screen_view_home_count") / max(active * 4.3, 1), 2
            ),
        )
        profiles[user_id] = profile

    logger.info("Built %d user profiles from %d monthly records.",
                len(profiles), len(records_raw))
    _cache_user_profiles = profiles
    return profiles


def load_user_profile(user_id: str) -> UserProfile:
    """Load a single user's profile by user_id.

    Loads all profiles on first call (cached), then returns the requested one.

    Args:
        user_id: SHA-256 hash string (with or without surrounding quotes).

    Returns:
        UserProfile for the given user.

    Raises:
        KeyError: If user_id is not found in the dataset.
    """
    # Strip quotes in case the caller passes the raw JSON value
    clean_id = user_id.strip("'")
    profiles = load_user_profiles()
    if clean_id not in profiles:
        raise KeyError(
            f"User '{clean_id}' not found in dataset. "
            f"Dataset contains {len(profiles)} users."
        )
    return profiles[clean_id]


def load_club_stats(club_id: str) -> ClubStats:
    """Derive season-level ClubStats by aggregating all 306 match records.

    Computes wins/draws/losses/goals from the match files and identifies
    the top scorer from the Bayern season stats file (Bayern only).

    Args:
        club_id: DFL-CLU-* identifier.

    Returns:
        Populated ClubStats for the given club.
    """
    all_matches = load_match_overview()
    club_name = CLUB_ID_TO_NAME.get(club_id, "")

    wins = draws = losses = goals_for = goals_against = 0
    best_win_margin = -1
    best_win_match: Optional[MatchRecord] = None
    worst_loss_margin = -1
    worst_loss_match: Optional[MatchRecord] = None

    for match in all_matches.values():
        is_home = match.home_team_id == club_id
        is_away = match.away_team_id == club_id
        if not (is_home or is_away):
            continue

        gf = match.home_goals if is_home else match.away_goals
        ga = match.away_goals if is_home else match.home_goals
        goals_for += gf
        goals_against += ga

        if gf > ga:
            wins += 1
            margin = gf - ga
            if margin > best_win_margin:
                best_win_margin = margin
                best_win_match = match
        elif gf == ga:
            draws += 1
        else:
            losses += 1
            margin = ga - gf
            if margin > worst_loss_margin:
                worst_loss_margin = margin
                worst_loss_match = match

    # Top scorer — only available for Bayern
    top_scorer_id = top_scorer_name = ""
    top_scorer_goals = 0
    top_assister_id = top_assister_name = ""
    top_assister_assists = 0

    if club_id == "DFL-CLU-00000G":
        players = load_player_stats(club_id)
        if players:
            top_scorer = max(players, key=lambda p: p.goals)
            top_scorer_id = top_scorer.player_id
            top_scorer_name = top_scorer.name
            top_scorer_goals = top_scorer.goals
            top_assister = max(players, key=lambda p: p.assists)
            top_assister_id = top_assister.player_id
            top_assister_name = top_assister.name
            top_assister_assists = top_assister.assists

    matches_played = wins + draws + losses

    return ClubStats(
        club_id=club_id,
        club_name=club_name,
        season="2024-25",
        matches_played=matches_played,
        wins=wins,
        draws=draws,
        losses=losses,
        goals_scored=goals_for,
        goals_conceded=goals_against,
        goal_difference=goals_for - goals_against,
        points=wins * 3 + draws,
        top_scorer_id=top_scorer_id,
        top_scorer_name=top_scorer_name,
        top_scorer_goals=top_scorer_goals,
        top_assister_id=top_assister_id,
        top_assister_name=top_assister_name,
        top_assister_assists=top_assister_assists,
        best_win_matchday=best_win_match.matchday if best_win_match else 0,
        best_win_result=best_win_match.result if best_win_match else "",
        best_win_opponent=(
            best_win_match.away_team_name
            if best_win_match and best_win_match.home_team_id == club_id
            else (best_win_match.home_team_name if best_win_match else "")
        ),
        worst_loss_matchday=worst_loss_match.matchday if worst_loss_match else 0,
        worst_loss_result=worst_loss_match.result if worst_loss_match else "",
        worst_loss_opponent=(
            worst_loss_match.away_team_name
            if worst_loss_match and worst_loss_match.home_team_id == club_id
            else (worst_loss_match.home_team_name if worst_loss_match else "")
        ),
    )
