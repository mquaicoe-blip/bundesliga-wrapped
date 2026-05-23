"""
test_personalization.py
=======================
Unit tests for the personalization engine.

Tests three user archetypes (super fan, casual, stats nerd) and validates
all scoring functions with edge cases.

Run: py -m pytest backend/pipeline/test_personalization.py -v
"""

import pytest

from backend.data.schema import ClubStats, MatchRecord, PlayerStats, UserProfile
from backend.pipeline.personalization import (
    build_context,
    classify_season_narrative,
    compute_fan_dna,
    derive_personal_fun_fact,
    infer_favorite_stat_category,
    score_match_drama,
    score_player_importance,
    select_hero_stat,
)


# ---------------------------------------------------------------------------
# Fixtures — reusable mock data
# ---------------------------------------------------------------------------

@pytest.fixture
def bayern_club() -> ClubStats:
    """Title-race club: 23 wins, 74 points."""
    return ClubStats(
        club_id="DFL-CLU-00000G",
        club_name="FC Bayern München",
        primary_color_hex="#DC052D",
        wins=23, draws=5, losses=6,
        goals_scored=87, goals_conceded=38,
        points=74, matches_played=34,
        top_scorer_id="DFL-OBJ-J00ZZ3",
        top_scorer_name="Harry Kane",
        top_scorer_goals=26,
    )


@pytest.fixture
def midtable_club() -> ClubStats:
    """Solid mid-table club: 13 wins, 49 points."""
    return ClubStats(
        club_id="DFL-CLU-000006",
        club_name="1. FSV Mainz 05",
        wins=13, draws=10, losses=11,
        goals_scored=48, goals_conceded=45,
        points=49, matches_played=34,
    )


@pytest.fixture
def struggling_club() -> ClubStats:
    """Relegation-threatened club: 7 wins, 30 points."""
    return ClubStats(
        club_id="DFL-CLU-00000S",
        club_name="VfL Bochum 1848",
        wins=7, draws=9, losses=18,
        goals_scored=32, goals_conceded=65,
        points=30, matches_played=34,
    )


@pytest.fixture
def comeback_club() -> ClubStats:
    """Comeback club: decent final record but big early loss."""
    return ClubStats(
        club_id="DFL-CLU-00000F",
        club_name="Eintracht Frankfurt",
        wins=16, draws=7, losses=11,
        goals_scored=55, goals_conceded=48,
        points=55, matches_played=34,
        worst_loss_matchday=5,
        worst_loss_result="0:4",
        worst_loss_opponent="Bayer 04 Leverkusen",
    )


@pytest.fixture
def kane() -> PlayerStats:
    return PlayerStats(
        player_id="DFL-OBJ-J00ZZ3", name="Harry Kane",
        club_id="DFL-CLU-00000G", position="offense",
        goals=26, assists=10, appearances=33,
    )


@pytest.fixture
def musiala() -> PlayerStats:
    return PlayerStats(
        player_id="DFL-OBJ-002GBK", name="Jamal Musiala",
        club_id="DFL-CLU-00000G", position="midfield",
        goals=12, assists=8, appearances=30,
    )


@pytest.fixture
def bench_player() -> PlayerStats:
    """Player with zero appearances — should score low."""
    return PlayerStats(
        player_id="DFL-OBJ-BENCH1", name="Bench Warmer",
        club_id="DFL-CLU-00000G", position="defense",
        goals=0, assists=0, appearances=0,
    )


@pytest.fixture
def super_fan() -> UserProfile:
    """Hardcore fan: high engagement, explicit favourites, 12 active months."""
    return UserProfile(
        user_id="super-fan-001",
        favorite_club="FC Bayern München",
        favorite_club_id="DFL-CLU-00000G",
        total_app_opens=250,
        total_match_center_views=200,
        total_article_views=60,
        total_story_views=30,
        total_video_views=80,
        active_months=12,
        stats_focus_ratio=0.45,
        ticker_focus_ratio=0.30,
        lineups_focus_ratio=0.15,
        favorite_player_ids=["DFL-OBJ-J00ZZ3"],
        app_opens_per_week=4.8,
    )


@pytest.fixture
def casual_fan() -> UserProfile:
    """Casual fan: low engagement, no explicit favourites, 4 active months."""
    return UserProfile(
        user_id="casual-fan-001",
        favorite_club="FC Bayern München",
        favorite_club_id="DFL-CLU-00000G",
        total_app_opens=15,
        total_match_center_views=10,
        total_article_views=5,
        total_story_views=2,
        total_video_views=3,
        active_months=4,
        stats_focus_ratio=0.1,
        ticker_focus_ratio=0.2,
        lineups_focus_ratio=0.1,
        favorite_player_ids=[],
        app_opens_per_week=0.9,
    )


@pytest.fixture
def stats_nerd() -> UserProfile:
    """Stats nerd: high stats focus, reads articles, moderate app opens."""
    return UserProfile(
        user_id="stats-nerd-001",
        favorite_club="FC Bayern München",
        favorite_club_id="DFL-CLU-00000G",
        total_app_opens=120,
        total_match_center_views=150,
        total_article_views=100,
        total_story_views=10,
        total_video_views=20,
        active_months=10,
        stats_focus_ratio=0.6,
        ticker_focus_ratio=0.2,
        lineups_focus_ratio=0.1,
        favorite_player_ids=[],
        app_opens_per_week=2.8,
    )


@pytest.fixture
def sample_matches() -> dict[str, MatchRecord]:
    return {
        "DFL-MAT-DEMO01": MatchRecord(
            match_id="DFL-MAT-DEMO01", matchday=10,
            home_team_id="DFL-CLU-00000G", home_team_name="FC Bayern München",
            away_team_id="DFL-CLU-000007", away_team_name="Borussia Dortmund",
            result="4:2", home_goals=4, away_goals=2, total_goals=6,
            spectators=75000, sold_out=True,
        ),
        "DFL-MAT-DEMO02": MatchRecord(
            match_id="DFL-MAT-DEMO02", matchday=20,
            home_team_id="DFL-CLU-00000G", home_team_name="FC Bayern München",
            away_team_id="DFL-CLU-000006", away_team_name="1. FSV Mainz 05",
            result="1:0", home_goals=1, away_goals=0, total_goals=1,
        ),
        "DFL-MAT-DEMO03": MatchRecord(
            match_id="DFL-MAT-DEMO03", matchday=30,
            home_team_id="DFL-CLU-000017", home_team_name="RB Leipzig",
            away_team_id="DFL-CLU-00000G", away_team_name="FC Bayern München",
            result="2:3", home_goals=2, away_goals=3, total_goals=5,
            spectators=47000, sold_out=True,
        ),
    }


# ---------------------------------------------------------------------------
# Tests: score_player_importance
# ---------------------------------------------------------------------------

class TestScorePlayerImportance:
    def test_favourite_player_gets_high_score(self, super_fan, kane):
        """User's explicit favourite should score >= 0.5."""
        score = score_player_importance(super_fan, kane)
        assert score >= 0.5

    def test_non_favourite_productive_player(self, casual_fan, kane):
        """Productive player without being a favourite still scores well."""
        score = score_player_importance(casual_fan, kane)
        # No favourite bonus (0.5), but high goals+assists and appearances
        assert 0.3 <= score <= 0.6

    def test_bench_player_scores_low(self, super_fan, bench_player):
        """Player with 0 appearances and 0 goals should score near 0."""
        score = score_player_importance(super_fan, bench_player)
        assert score < 0.1

    def test_score_bounded_0_to_1(self, super_fan, kane):
        """Score should never exceed 1.0."""
        score = score_player_importance(super_fan, kane)
        assert 0.0 <= score <= 1.0

    def test_favourite_bonus_is_dominant(self, super_fan, bench_player):
        """Even a bench player who is a favourite gets the 0.5 bonus."""
        # Add bench player to favourites
        super_fan.favorite_player_ids.append("DFL-OBJ-BENCH1")
        score = score_player_importance(super_fan, bench_player)
        assert score >= 0.5


# ---------------------------------------------------------------------------
# Tests: classify_season_narrative
# ---------------------------------------------------------------------------

class TestClassifySeasonNarrative:
    def test_title_race(self, bayern_club):
        """23 wins → title_race."""
        assert classify_season_narrative(bayern_club) == "title_race"

    def test_solid(self, midtable_club):
        """13 wins, 49 points → solid."""
        assert classify_season_narrative(midtable_club) == "solid"

    def test_struggle(self, struggling_club):
        """7 wins, 30 points → struggle."""
        assert classify_season_narrative(struggling_club) == "struggle"

    def test_comeback(self, comeback_club):
        """Big early loss + decent final record → comeback."""
        assert classify_season_narrative(comeback_club) == "comeback"

    def test_edge_case_20_wins(self):
        """Exactly 20 wins → title_race threshold."""
        club = ClubStats(wins=20, draws=5, losses=9, points=65, matches_played=34)
        assert classify_season_narrative(club) == "title_race"

    def test_edge_case_19_wins_not_title(self):
        """19 wins → not title_race (below threshold)."""
        club = ClubStats(wins=19, draws=5, losses=10, points=62, matches_played=34)
        assert classify_season_narrative(club) != "title_race"


# ---------------------------------------------------------------------------
# Tests: score_match_drama
# ---------------------------------------------------------------------------

class TestScoreMatchDrama:
    def test_rivalry_match_scores_higher(self, sample_matches):
        """Bayern vs Dortmund (rivalry) should score higher than Bayern vs Mainz."""
        rivalry = score_match_drama(sample_matches["DFL-MAT-DEMO01"], "DFL-CLU-00000G")
        normal = score_match_drama(sample_matches["DFL-MAT-DEMO02"], "DFL-CLU-00000G")
        assert rivalry > normal

    def test_sold_out_bonus(self, sample_matches):
        """Sold-out match gets a bonus."""
        sold_out = score_match_drama(sample_matches["DFL-MAT-DEMO01"], "DFL-CLU-00000G")
        # DEMO01 is sold out, DEMO02 is not
        not_sold_out = score_match_drama(sample_matches["DFL-MAT-DEMO02"], "DFL-CLU-00000G")
        assert sold_out > not_sold_out

    def test_high_scoring_match(self, sample_matches):
        """6-goal match (DEMO01) should score higher than 1-goal match (DEMO02)."""
        high = score_match_drama(sample_matches["DFL-MAT-DEMO01"], "DFL-CLU-00000G")
        low = score_match_drama(sample_matches["DFL-MAT-DEMO02"], "DFL-CLU-00000G")
        assert high > low

    def test_close_result_bonus(self, sample_matches):
        """1-goal margin (DEMO02: 1:0) gets close-result bonus."""
        drama = score_match_drama(sample_matches["DFL-MAT-DEMO02"], "DFL-CLU-00000G")
        assert drama > 0  # should have at least the close-result + win bonus


# ---------------------------------------------------------------------------
# Tests: compute_fan_dna
# ---------------------------------------------------------------------------

class TestComputeFanDna:
    def test_super_fan_high_score(self, super_fan):
        score, breakdown, archetype = compute_fan_dna(super_fan)
        assert score >= 60
        assert breakdown["loyalty"] >= 80  # 12/12 months

    def test_casual_fan_low_score(self, casual_fan):
        score, breakdown, archetype = compute_fan_dna(casual_fan)
        assert score < 40
        assert breakdown["loyalty"] < 50  # 4/12 months

    def test_archetype_assignment(self, super_fan, stats_nerd):
        _, _, archetype_super = compute_fan_dna(super_fan)
        # Super fan has high loyalty (12 months) → Season Ticket Holder
        assert "Season Ticket" in archetype_super or "Matchday" in archetype_super

    def test_score_bounded(self, super_fan):
        score, _, _ = compute_fan_dna(super_fan)
        assert 0 <= score <= 100


# ---------------------------------------------------------------------------
# Tests: build_context (integration)
# ---------------------------------------------------------------------------

class TestBuildContext:
    def test_super_fan_context(self, super_fan, bayern_club, kane, musiala, sample_matches):
        """Super fan with Kane as favourite → Kane should be top_player."""
        players = [kane, musiala]
        ctx = build_context(super_fan, bayern_club, players, sample_matches, tone="fan")

        assert ctx.favourite_player is not None
        assert ctx.favourite_player.player_id == "DFL-OBJ-J00ZZ3"  # Kane
        assert ctx.fan_dna_score > 50
        assert ctx.hero_stat_value > 0
        assert ctx.tone == "fan"

    def test_casual_fan_context(self, casual_fan, bayern_club, kane, musiala, sample_matches):
        """Casual fan with no favourites → falls back to top scorer."""
        players = [kane, musiala]
        ctx = build_context(casual_fan, bayern_club, players, sample_matches)

        # Should still get a top player (Kane has highest score without favourite bonus)
        assert ctx.favourite_player is not None
        assert ctx.fan_dna_score < 40

    def test_stats_nerd_context(self, stats_nerd, bayern_club, kane, musiala, sample_matches):
        """Stats nerd → should get stats-related fun fact."""
        players = [kane, musiala]
        ctx = build_context(stats_nerd, bayern_club, players, sample_matches)

        # Stats nerd should have stats-related personal angle
        assert "stats" in ctx.personal_angle_stat.lower() or "app" in ctx.personal_angle_stat.lower()

    def test_empty_players_handled(self, super_fan, bayern_club, sample_matches):
        """Empty player list shouldn't crash."""
        ctx = build_context(super_fan, bayern_club, [], sample_matches)
        assert ctx.favourite_player is None

    def test_empty_matches_handled(self, super_fan, bayern_club, kane):
        """Empty match dict shouldn't crash."""
        ctx = build_context(super_fan, bayern_club, [kane], {})
        assert ctx.best_match is None
        assert ctx.season_arc_moments == []

    def test_tone_propagates(self, super_fan, bayern_club, kane, sample_matches):
        """Tone parameter should be set on the context."""
        ctx = build_context(super_fan, bayern_club, [kane], sample_matches, tone="analyst")
        assert ctx.tone == "analyst"
