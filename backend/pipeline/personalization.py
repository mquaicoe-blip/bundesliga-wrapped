"""
personalization.py
==================
The brain of Bundesliga Wrapped — decides which stats, players, and moments
are most relevant for each user and assembles a PersonalizationContext.

This module is pure logic with no AWS calls. It takes pre-loaded data objects
and produces the context that drives all 7 Wrapped slides.

Usage:
    from backend.pipeline.personalization import build_context

    ctx = build_context(user, club, players, matches)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from backend.data.schema import (
    ClubStats,
    MatchRecord,
    PersonalizationContext,
    PlayerStats,
    Tone,
    UserProfile,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Rivalry pairs — matches between these clubs get a drama bonus
RIVALRY_PAIRS: set[frozenset[str]] = {
    frozenset({"DFL-CLU-00000G", "DFL-CLU-000007"}),  # Bayern vs Dortmund
    frozenset({"DFL-CLU-00000G", "DFL-CLU-000017"}),  # Bayern vs Leipzig
    frozenset({"DFL-CLU-000007", "DFL-CLU-000017"}),  # Dortmund vs Leipzig
    frozenset({"DFL-CLU-00000B", "DFL-CLU-000007"}),  # Leverkusen vs Dortmund
    frozenset({"DFL-CLU-000004", "DFL-CLU-000007"}),  # Gladbach vs Dortmund
}


# ---------------------------------------------------------------------------
# Player importance scoring
# ---------------------------------------------------------------------------

def score_player_importance(user: UserProfile, player: PlayerStats) -> float:
    """Score how important a player is to this specific user.

    Returns a value between 0.0 and 1.0 combining three weighted signals:
      - Is the player in the user's explicit favorites? (+0.5)
      - How productive is the player (goals + assists)? (+0.3, normalised)
      - How many appearances did the player make? (+0.2, normalised)

    The normalisation uses reasonable season maximums so the score stays
    in [0, 1] even for extreme values.

    Args:
        user: The user profile with favorite_player_ids populated.
        player: The player to score.

    Returns:
        Float in [0.0, 1.0] — higher means more relevant to this user.
    """
    score = 0.0

    # Signal 1: User explicitly follows this player (strongest signal)
    # This is the most direct indicator of personal relevance
    if player.player_id in user.favorite_player_ids:
        score += 0.5

    # Signal 2: Player productivity (goals + assists)
    # Normalised against a realistic season max of ~40 goal involvements
    # (Kane had 26 goals + assists in 24-25 — 40 is generous ceiling)
    productivity = player.goals + player.assists
    max_productivity = 40
    score += 0.3 * min(productivity / max_productivity, 1.0)

    # Signal 3: Appearances — a player who plays every week is more visible
    # to the fan than a squad player who appears 3 times
    # Max appearances in a Bundesliga season = 34
    max_appearances = 34
    score += 0.2 * min(player.appearances / max_appearances, 1.0)

    return round(min(score, 1.0), 4)


# ---------------------------------------------------------------------------
# Season narrative classification
# ---------------------------------------------------------------------------

def classify_season_narrative(club: ClubStats) -> str:
    """Determine the overall season narrative arc for a club.

    Returns one of four narrative types that frame the entire Wrapped
    experience differently:
      - "title_race"  — dominant season, competing for the championship
      - "comeback"    — poor start but strong finish (or vice versa)
      - "solid"       — consistent mid-table, no drama
      - "struggle"    — relegation battle or disappointing season

    The thresholds are calibrated against typical Bundesliga distributions:
      - Champion usually has 70-85 points (23-28 wins)
      - Relegation zone is ~27-33 points (7-10 wins)
      - Mid-table is 40-55 points (12-17 wins)

    Args:
        club: ClubStats with wins/draws/losses populated.

    Returns:
        One of: "title_race", "comeback", "solid", "struggle".
    """
    # Title race: dominant performance — top of the table
    if club.wins >= 20:
        return "title_race"

    # Struggle: too many losses, likely in relegation danger
    if club.losses >= 17 or club.points <= 33:
        return "struggle"

    # Comeback: decent final record but had a rough patch
    # Heuristic: if they lost their worst match badly (3+ goal margin)
    # but still ended with a respectable points total, they recovered
    if club.losses < 12 and club.worst_loss_matchday > 0:
        worst_loss_margin = 0
        if club.worst_loss_result:
            try:
                parts = club.worst_loss_result.split(":")
                h, a = int(parts[0]), int(parts[1])
                worst_loss_margin = abs(h - a)
            except (ValueError, IndexError):
                pass
        # Big loss early + decent final record = comeback narrative
        if worst_loss_margin >= 3 and club.worst_loss_matchday <= 17 and club.points >= 45:
            return "comeback"

    # Solid: everything else — consistent, unremarkable
    return "solid"


# ---------------------------------------------------------------------------
# Match drama scoring
# ---------------------------------------------------------------------------

def score_match_drama(match: MatchRecord, club_id: str) -> float:
    """Score how dramatic a match was from the perspective of a specific club.

    Drama factors (additive):
      - High total goals (+0.2 per goal above 3)
      - Close result / one-goal margin (+0.3)
      - Sold-out stadium (+0.1)
      - Rivalry match (+0.3)
      - Club won (+0.2) or lost by 1 (+0.1 — heartbreak is dramatic too)

    Args:
        match: The match record to score.
        club_id: The club we're scoring drama *for* (perspective matters).

    Returns:
        Float drama score (unbounded above 0, typically 0.0–2.0).
    """
    score = 0.0

    # High-scoring matches are inherently more exciting
    if match.total_goals > 3:
        score += 0.2 * (match.total_goals - 3)

    # Close results create tension — one-goal margins are the most dramatic
    goal_diff = abs(match.home_goals - match.away_goals)
    if goal_diff == 1:
        score += 0.3
    elif goal_diff == 0:
        # Draws are tense but less dramatic than a narrow win/loss
        score += 0.15

    # Sold-out atmosphere amplifies drama
    if match.sold_out:
        score += 0.1

    # Rivalry matches carry extra weight regardless of result
    match_pair = frozenset({match.home_team_id, match.away_team_id})
    if match_pair in RIVALRY_PAIRS:
        score += 0.3

    # Did our club win? Wins are more shareable than losses
    is_home = match.home_team_id == club_id
    club_goals = match.home_goals if is_home else match.away_goals
    opp_goals = match.away_goals if is_home else match.home_goals

    if club_goals > opp_goals:
        score += 0.2  # Victory bonus
    elif club_goals < opp_goals and goal_diff == 1:
        score += 0.1  # Heartbreak bonus — narrow losses are memorable

    return round(score, 3)


# ---------------------------------------------------------------------------
# Fan DNA scoring
# ---------------------------------------------------------------------------

def compute_fan_dna(user: UserProfile) -> tuple[int, dict[str, int], str]:
    """Compute the Fan DNA Score (0–100) and breakdown for a user.

    Three dimensions:
      - Loyalty (0–100): How consistently the user opens the app across months
      - Intensity (0–100): How deep they go per session (match centre views)
      - Breadth (0–100): How much varied content they consume (articles + stories + video)

    The overall score is a weighted average: loyalty 40%, intensity 35%, breadth 25%.
    These weights reflect that consistency is the strongest fandom signal.

    Also assigns an archetype label based on the dominant dimension.

    Args:
        user: Aggregated UserProfile.

    Returns:
        Tuple of (overall_score, breakdown_dict, archetype_string).
    """
    # Loyalty: active_months out of 12 possible
    loyalty = int(min(user.active_months / 12, 1.0) * 100)

    # Intensity: match centre views per active month
    # A "hardcore" fan checks match centre ~50+ times per month
    mc_per_month = (
        user.total_match_center_views / max(user.active_months, 1)
    )
    intensity = int(min(mc_per_month / 50, 1.0) * 100)

    # Breadth: total content pieces (articles + stories + videos) per month
    # A broad consumer reads/watches ~30+ pieces per month across types
    total_content = user.total_article_views + user.total_story_views + user.total_video_views
    content_per_month = total_content / max(user.active_months, 1)
    breadth = int(min(content_per_month / 30, 1.0) * 100)

    # Weighted overall score
    overall = int(loyalty * 0.40 + intensity * 0.35 + breadth * 0.25)

    breakdown = {"loyalty": loyalty, "intensity": intensity, "breadth": breadth}

    # Archetype based on dominant dimension
    if loyalty >= intensity and loyalty >= breadth:
        archetype = "The Season Ticket Holder"  # consistent, always there
    elif intensity >= loyalty and intensity >= breadth:
        archetype = "The Matchday Obsessive"    # deep diver on game days
    else:
        archetype = "The Football Scholar"      # reads/watches everything

    return overall, breakdown, archetype


# ---------------------------------------------------------------------------
# Personal fun fact generation
# ---------------------------------------------------------------------------

def derive_personal_fun_fact(user: UserProfile, club: ClubStats) -> str:
    """Generate a surprising personal stat about the user's fandom.

    Picks the most interesting fact from available data. Priority order:
      1. Extreme app usage (top/bottom)
      2. Content consumption patterns
      3. Engagement consistency

    The goal is to surface something the user didn't know about themselves —
    this is the "top 0.1%" moment from Spotify Wrapped.

    Args:
        user: Aggregated UserProfile.
        club: ClubStats for context.

    Returns:
        A single sentence string describing the fun fact.
    """
    facts: list[tuple[float, str]] = []

    # High app opens — "You opened the app X times this season"
    if user.total_app_opens > 200:
        facts.append((0.9, f"You opened the Bundesliga app {user.total_app_opens} times this season"))
    elif user.total_app_opens > 100:
        facts.append((0.6, f"You checked in {user.total_app_opens} times — that's almost every other day"))

    # Stats nerd detection
    if user.stats_focus_ratio > 0.5 and user.total_match_center_views > 50:
        facts.append((0.85, "You spent more time on match stats than any other screen"))

    # Ticker addict
    if user.ticker_focus_ratio > 0.5 and user.total_match_center_views > 50:
        facts.append((0.8, "You followed the live ticker more than anything else — a true second-screen fan"))

    # Video consumer
    if user.total_video_views > 50:
        facts.append((0.7, f"You watched {user.total_video_views} videos — that's a highlight reel marathon"))

    # Article reader
    if user.total_article_views > 80:
        facts.append((0.75, f"You read {user.total_article_views} articles — more than most journalists"))

    # Perfect attendance
    if user.active_months == 12:
        facts.append((0.8, "You were active every single month — zero off-season for you"))

    # Lineups obsessive
    if user.lineups_focus_ratio > 0.3 and user.total_match_center_views > 30:
        facts.append((0.65, "You checked lineups religiously — always prepared before kickoff"))

    # Fallback — always have something
    if not facts:
        facts.append((0.3, f"You followed {club.club_name} through {club.matches_played} matches this season"))

    # Return the highest-scored fact (most surprising/interesting)
    facts.sort(key=lambda x: -x[0])
    return facts[0][1]


# ---------------------------------------------------------------------------
# Favorite stat category inference
# ---------------------------------------------------------------------------

def infer_favorite_stat_category(user: UserProfile) -> str:
    """Infer which stat category resonates most with this user.

    Based on their engagement patterns:
      - Stats-heavy users → "goals" or "xG" (they care about numbers)
      - Ticker followers → "assists" (they follow the flow of play)
      - Lineups watchers → "clean_sheets" (they care about team shape)
      - Video watchers → "goals" (they want highlights)
      - Default → "goals" (universally appealing)

    Args:
        user: Aggregated UserProfile.

    Returns:
        One of: "goals", "assists", "clean_sheets", "possession".
    """
    if user.stats_focus_ratio > 0.4:
        # Stats nerds appreciate advanced metrics
        return "goals"
    elif user.lineups_focus_ratio > 0.3:
        # Lineups watchers care about defensive shape
        return "clean_sheets"
    elif user.ticker_focus_ratio > 0.4:
        # Ticker followers appreciate playmaking
        return "assists"
    elif user.total_video_views > user.total_article_views:
        # Video consumers want highlight-worthy stats
        return "goals"
    else:
        # Default — goals are universally engaging
        return "goals"


# ---------------------------------------------------------------------------
# Hero stat selection
# ---------------------------------------------------------------------------

def select_hero_stat(user: UserProfile, club: ClubStats) -> tuple[str, int]:
    """Select the single most impactful stat for the hero slide.

    The hero stat should be:
      - Personal (tied to the user's behaviour, not just the club)
      - Big (a number that feels impressive when displayed large)
      - Shareable (something that signals fandom identity)

    Priority: total app opens > match centre views > content views.
    Falls back to club goals if user data is too sparse.

    Args:
        user: Aggregated UserProfile.
        club: ClubStats for fallback.

    Returns:
        Tuple of (label, value) for the hero stat.
    """
    # Best case: user has high app engagement — personal and impressive
    if user.total_app_opens > 50:
        return ("times you showed up for your club", user.total_app_opens)

    # Second: match centre views — shows active match following
    if user.total_match_center_views > 30:
        return ("match moments you followed live", user.total_match_center_views)

    # Third: total content consumed
    total_content = user.total_article_views + user.total_story_views + user.total_video_views
    if total_content > 20:
        return ("pieces of content consumed", total_content)

    # Fallback: club-level stat (still meaningful, less personal)
    return ("goals your club scored", club.goals_scored)


# ---------------------------------------------------------------------------
# Key moments selection
# ---------------------------------------------------------------------------

def select_key_moments(
    matches: dict[str, MatchRecord],
    club_id: str,
    user: UserProfile,
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """Select the top N most dramatic/relevant matches for this user's club.

    Scoring combines:
      - Match drama score (goals, closeness, rivalry, atmosphere)
      - User watched bonus (if match_id is in user's most_watched_match_ids)

    Each returned moment includes a human-readable description generated
    from the match data (no Bedrock needed — pure template logic).

    Args:
        matches: Dict of match_id → MatchRecord (all 306 matches).
        club_id: The user's club DFL-CLU-* ID.
        user: UserProfile (for watched-match bonus).
        top_n: Number of moments to return.

    Returns:
        List of dicts with keys: match_id, description, type, drama_score, matchday.
    """
    # Filter to only this club's matches
    club_matches = [
        m for m in matches.values()
        if m.home_team_id == club_id or m.away_team_id == club_id
    ]

    if not club_matches:
        return []

    # Score each match
    scored: list[tuple[float, MatchRecord]] = []
    for match in club_matches:
        drama = score_match_drama(match, club_id)

        # Bonus if the user actually watched this match (from engagement data)
        if match.match_id in user.most_watched_match_ids:
            drama += 0.4  # significant bonus — makes it personal

        scored.append((drama, match))

    # Sort by drama score descending, take top N
    scored.sort(key=lambda x: -x[0])
    top_matches = scored[:top_n]

    # Build human-readable descriptions
    moments: list[dict[str, Any]] = []
    for drama_score, match in top_matches:
        is_home = match.home_team_id == club_id
        opponent = match.away_team_name if is_home else match.home_team_name
        club_goals = match.home_goals if is_home else match.away_goals
        opp_goals = match.away_goals if is_home else match.home_goals
        venue = "home" if is_home else "away"

        # Determine moment type and description
        if club_goals > opp_goals:
            moment_type = "victory"
            desc = f"Matchday {match.matchday}: {match.result} win vs {opponent} ({venue})"
        elif club_goals < opp_goals:
            moment_type = "heartbreak"
            desc = f"Matchday {match.matchday}: {match.result} loss to {opponent} ({venue})"
        else:
            moment_type = "thriller"
            desc = f"Matchday {match.matchday}: {match.result} draw with {opponent} ({venue})"

        # Add extra flavour for high-scoring or sold-out matches
        if match.total_goals >= 5:
            desc += f" — {match.total_goals} goals"
        if match.sold_out:
            desc += " — sold out"

        moments.append({
            "match_id": match.match_id,
            "description": desc,
            "type": moment_type,
            "drama_score": drama_score,
            "matchday": match.matchday,
        })

    return moments


# ---------------------------------------------------------------------------
# Main entry point: build_context
# ---------------------------------------------------------------------------

def build_context(
    user: UserProfile,
    club: ClubStats,
    players: list[PlayerStats],
    matches: dict[str, MatchRecord],
    tone: Tone = "commentator",
) -> PersonalizationContext:
    """Assemble a complete PersonalizationContext for one user.

    This is the main entry point for the personalization engine. It takes
    all pre-loaded data and produces the context object that drives all 7
    Wrapped slides and their Bedrock narrative generation.

    The logic flow:
      1. Select the top player (user's favourite or club's best scorer)
      2. Classify the season narrative arc
      3. Score and select key match moments
      4. Compute Fan DNA Score
      5. Select the hero stat
      6. Derive a personal fun fact
      7. Infer favourite stat category

    Args:
        user: Aggregated UserProfile for this user.
        club: ClubStats for the user's favourite club.
        players: List of PlayerStats for the club's roster.
        matches: Dict of all match_id → MatchRecord.
        tone: Narrative tone to embed in the context.

    Returns:
        Fully populated PersonalizationContext ready for Bedrock.
    """
    # ── 1. Select top player ──────────────────────────────────────────────────
    # If the user has explicit favourites that overlap with the club roster,
    # use the highest-scored one. Otherwise fall back to the club's top scorer.
    top_player: Optional[PlayerStats] = None

    if players:
        # Score all players by importance to this user
        player_scores = [
            (score_player_importance(user, p), p)
            for p in players
            if p.appearances > 0  # exclude players who never played
        ]
        player_scores.sort(key=lambda x: -x[0])

        if player_scores:
            top_player = player_scores[0][1]

    # Determine the player bond stat — pick their most impressive stat
    player_bond_label = ""
    player_bond_value: Any = None
    if top_player:
        if top_player.goals >= top_player.assists:
            player_bond_label = "goals this season"
            player_bond_value = top_player.goals
        else:
            player_bond_label = "assists this season"
            player_bond_value = top_player.assists

    # ── 2. Season narrative ───────────────────────────────────────────────────
    season_narrative = classify_season_narrative(club)

    # ── 3. Key moments ────────────────────────────────────────────────────────
    key_moments = select_key_moments(matches, club.club_id, user, top_n=3)

    # Build season arc from key moments (ordered by matchday)
    season_arc_moments = [
        m["description"] for m in sorted(key_moments, key=lambda x: x["matchday"])
    ]

    # Select the best match (highest drama) for Slide 4
    best_match: Optional[MatchRecord] = None
    best_match_reason = ""
    if key_moments:
        best_moment = key_moments[0]  # already sorted by drama score
        best_match = matches.get(best_moment["match_id"])
        best_match_reason = best_moment["description"]

    # ── 4. Fan DNA Score ──────────────────────────────────────────────────────
    fan_dna_score, fan_dna_breakdown, fan_dna_archetype = compute_fan_dna(user)

    # ── 5. Hero stat ──────────────────────────────────────────────────────────
    hero_label, hero_value = select_hero_stat(user, club)

    # ── 6. Personal fun fact ──────────────────────────────────────────────────
    personal_angle = derive_personal_fun_fact(user, club)

    # ── 7. Assemble context ───────────────────────────────────────────────────
    ctx = PersonalizationContext(
        user=user,
        club=club,
        hero_stat_label=hero_label,
        hero_stat_value=hero_value,
        fan_dna_score=fan_dna_score,
        fan_dna_breakdown=fan_dna_breakdown,
        fan_dna_archetype=fan_dna_archetype,
        favourite_player=top_player,
        player_bond_stat_label=player_bond_label,
        player_bond_stat_value=player_bond_value,
        best_match=best_match,
        best_match_reason=best_match_reason,
        season_arc_moments=season_arc_moments,
        personal_angle_stat=personal_angle,
        tone=tone,
    )

    logger.info(
        "Built PersonalizationContext for user=%s, club=%s, narrative=%s, "
        "fan_dna=%d, top_player=%s",
        user.user_id[:12],
        club.club_name,
        season_narrative,
        fan_dna_score,
        top_player.name if top_player else "none",
    )

    return ctx


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    """Demo: build a sample context with mock data and pretty-print it."""
    import json as _json

    logging.basicConfig(level=logging.INFO)

    # Create mock data that exercises all code paths
    mock_user = UserProfile(
        user_id="demo-user-001",
        favorite_club="FC Bayern München",
        favorite_club_id="DFL-CLU-00000G",
        age_group="25-34",
        country="DE",
        language="de_DE",
        platform="iOS",
        total_article_views=45,
        total_story_views=20,
        total_video_views=60,
        total_match_center_views=180,
        total_app_opens=220,
        active_months=11,
        stats_focus_ratio=0.45,
        ticker_focus_ratio=0.30,
        lineups_focus_ratio=0.15,
        favorite_player_ids=["DFL-OBJ-J00ZZ3"],  # Harry Kane
        app_opens_per_week=4.7,
    )

    mock_club = ClubStats(
        club_id="DFL-CLU-00000G",
        club_name="FC Bayern München",
        primary_color_hex="#DC052D",
        secondary_color_hex="#0066B2",
        matches_played=34,
        wins=23,
        draws=5,
        losses=6,
        goals_scored=87,
        goals_conceded=38,
        goal_difference=49,
        points=74,
        top_scorer_id="DFL-OBJ-J00ZZ3",
        top_scorer_name="Harry Kane",
        top_scorer_goals=26,
        best_win_matchday=9,
        best_win_result="8:0",
        best_win_opponent="VfL Bochum 1848",
        worst_loss_matchday=5,
        worst_loss_result="1:4",
        worst_loss_opponent="FC Barcelona",
    )

    mock_players = [
        PlayerStats(
            player_id="DFL-OBJ-J00ZZ3", name="Harry Kane",
            club_id="DFL-CLU-00000G", position="offense",
            goals=26, assists=10, appearances=33,
            xg=22.54, normalized_minutes=2800,
        ),
        PlayerStats(
            player_id="DFL-OBJ-002GBK", name="Jamal Musiala",
            club_id="DFL-CLU-00000G", position="midfield",
            goals=12, assists=8, appearances=30,
            xg=9.2, normalized_minutes=2400,
        ),
        PlayerStats(
            player_id="DFL-OBJ-0001UP", name="Joshua Kimmich",
            club_id="DFL-CLU-00000G", position="midfield",
            goals=3, assists=12, appearances=32,
            xg=2.1, normalized_minutes=2700,
        ),
    ]

    mock_matches = {
        "DFL-MAT-J04034": MatchRecord(
            match_id="DFL-MAT-J04034", matchday=1,
            home_team_id="DFL-CLU-000004", home_team_name="Borussia Mönchengladbach",
            away_team_id="DFL-CLU-00000B", away_team_name="Bayer 04 Leverkusen",
            result="2:3", home_goals=2, away_goals=3, total_goals=5,
            spectators=54042, sold_out=True,
        ),
        "DFL-MAT-DEMO01": MatchRecord(
            match_id="DFL-MAT-DEMO01", matchday=10,
            home_team_id="DFL-CLU-00000G", home_team_name="FC Bayern München",
            away_team_id="DFL-CLU-000007", away_team_name="Borussia Dortmund",
            result="4:2", home_goals=4, away_goals=2, total_goals=6,
            spectators=75000, sold_out=True,
        ),
        "DFL-MAT-DEMO02": MatchRecord(
            match_id="DFL-MAT-DEMO02", matchday=29,
            home_team_id="DFL-CLU-00000G", home_team_name="FC Bayern München",
            away_team_id="DFL-CLU-000017", away_team_name="RB Leipzig",
            result="3:2", home_goals=3, away_goals=2, total_goals=5,
            spectators=75000, sold_out=True,
        ),
        "DFL-MAT-DEMO03": MatchRecord(
            match_id="DFL-MAT-DEMO03", matchday=15,
            home_team_id="DFL-CLU-00000G", home_team_name="FC Bayern München",
            away_team_id="DFL-CLU-00000A", away_team_name="Sport-Club Freiburg",
            result="2:1", home_goals=2, away_goals=1, total_goals=3,
        ),
    }

    # Build context
    ctx = build_context(mock_user, mock_club, mock_players, mock_matches, tone="fan")

    # Pretty-print
    print("\n" + "=" * 60)
    print("  PERSONALIZATION CONTEXT — Demo Output")
    print("=" * 60)
    print(f"\n  User:           {ctx.user.user_id}")
    print(f"  Club:           {ctx.club.club_name}")
    print(f"  Tone:           {ctx.tone}")
    print(f"\n  [Slide 1] Hero: {ctx.hero_stat_value} {ctx.hero_stat_label}")
    print(f"  [Slide 2] Fan DNA: {ctx.fan_dna_score}/100 — {ctx.fan_dna_archetype}")
    print(f"            Breakdown: {ctx.fan_dna_breakdown}")
    print(f"  [Slide 3] Player: {ctx.favourite_player.name if ctx.favourite_player else 'N/A'}")
    print(f"            Stat: {ctx.player_bond_stat_value} {ctx.player_bond_stat_label}")
    print(f"  [Slide 4] Best match: {ctx.best_match_reason}")
    print(f"  [Slide 5] Season arc:")
    for moment in ctx.season_arc_moments:
        print(f"            • {moment}")
    print(f"  [Slide 6] Personal: {ctx.personal_angle_stat}")
    print("\n" + "=" * 60)
