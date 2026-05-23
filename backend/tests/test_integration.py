"""
test_integration.py
===================
End-to-end integration tests for the Bundesliga Wrapped pipeline.

Validates the full flow: data → context → narratives → slides, using dry_run
mode so no AWS calls are made. Also proves the automation layer produces
different outputs for different clubs.

Run: py -m pytest backend/tests/test_integration.py -v
"""

import pytest

from backend.data.schema import (
    ClubStats,
    MatchRecord,
    PersonalizationContext,
    PlayerStats,
    UserProfile,
    WrappedSlide,
)
from backend.pipeline.personalization import build_context
from backend.pipeline.narrative_generator import generate_all_slides
from backend.pipeline.slide_assembler import assemble_slides, get_club_theme

# Valid values for assertion

VALID_SLIDE_TYPES = {"hero", "fan_dna", "player_bond", "goal_of_season", "match_of_season", "season_arc", "personal_angle", "share"}
VALID_ANIMATIONS = {"counter", "fade", "slide_up", "pulse"}
VALID_TONES = {"commentator", "analyst", "fan"}


# Fixtures

@pytest.fixture
def bayern_user() -> UserProfile:
    return UserProfile(
        user_id="integration-test-user-bayern",
        favorite_club="FC Bayern München",
        favorite_club_id="DFL-CLU-00000G",
        total_app_opens=150,
        total_match_center_views=120,
        total_article_views=40,
        total_story_views=15,
        total_video_views=50,
        active_months=10,
        stats_focus_ratio=0.4,
        ticker_focus_ratio=0.35,
        lineups_focus_ratio=0.15,
        favorite_player_ids=["DFL-OBJ-J00ZZ3"],
        app_opens_per_week=3.5,
    )


@pytest.fixture
def dortmund_user() -> UserProfile:
    return UserProfile(
        user_id="integration-test-user-dortmund",
        favorite_club="Borussia Dortmund",
        favorite_club_id="DFL-CLU-000007",
        total_app_opens=80,
        total_match_center_views=60,
        total_article_views=25,
        total_story_views=10,
        total_video_views=30,
        active_months=8,
        stats_focus_ratio=0.3,
        ticker_focus_ratio=0.4,
        lineups_focus_ratio=0.2,
        favorite_player_ids=[],
        app_opens_per_week=2.3,
    )


@pytest.fixture
def bayern_club() -> ClubStats:
    return ClubStats(
        club_id="DFL-CLU-00000G",
        club_name="FC Bayern München",
        primary_color_hex="#DC052D",
        secondary_color_hex="#0066B2",
        matches_played=34, wins=23, draws=5, losses=6,
        goals_scored=87, goals_conceded=38, points=74,
        top_scorer_id="DFL-OBJ-J00ZZ3",
        top_scorer_name="Harry Kane",
        top_scorer_goals=26,
        best_win_matchday=9, best_win_result="8:0",
        best_win_opponent="VfL Bochum 1848",
        worst_loss_matchday=5, worst_loss_result="1:4",
        worst_loss_opponent="Eintracht Frankfurt",
    )


@pytest.fixture
def dortmund_club() -> ClubStats:
    return ClubStats(
        club_id="DFL-CLU-000007",
        club_name="Borussia Dortmund",
        primary_color_hex="#FDE100",
        secondary_color_hex="#000000",
        matches_played=34, wins=18, draws=7, losses=9,
        goals_scored=68, goals_conceded=52, points=61,
        top_scorer_id="DFL-OBJ-DORTMUND-01",
        top_scorer_name="Serhou Guirassy",
        top_scorer_goals=18,
        best_win_matchday=12, best_win_result="4:0",
        best_win_opponent="FC Augsburg",
        worst_loss_matchday=8, worst_loss_result="1:3",
        worst_loss_opponent="VfB Stuttgart",
    )


@pytest.fixture
def bayern_players() -> list[PlayerStats]:
    return [
        PlayerStats(
            player_id="DFL-OBJ-J00ZZ3", name="Harry Kane",
            club_id="DFL-CLU-00000G", position="offense",
            goals=26, assists=10, appearances=33,
            xg=22.54, xg_efficiency=3.46,
            distance_covered_m=297100, max_speed_kmh=34.2,
            pass_accuracy=0.82,
        ),
        PlayerStats(
            player_id="DFL-OBJ-002GBK", name="Jamal Musiala",
            club_id="DFL-CLU-00000G", position="midfield",
            goals=12, assists=8, appearances=30,
            xg=9.2, xg_efficiency=2.8,
            distance_covered_m=280000, max_speed_kmh=32.5,
            pass_accuracy=0.88,
        ),
    ]


@pytest.fixture
def dortmund_players() -> list[PlayerStats]:
    return [
        PlayerStats(
            player_id="DFL-OBJ-DORTMUND-01", name="Serhou Guirassy",
            club_id="DFL-CLU-000007", position="offense",
            goals=18, assists=5, appearances=28,
            xg=15.2, xg_efficiency=2.8,
            distance_covered_m=240000, max_speed_kmh=33.1,
            pass_accuracy=0.75,
        ),
        PlayerStats(
            player_id="DFL-OBJ-DORTMUND-02", name="Julian Brandt",
            club_id="DFL-CLU-000007", position="midfield",
            goals=8, assists=12, appearances=32,
            xg=5.5, xg_efficiency=2.5,
            distance_covered_m=310000, max_speed_kmh=31.8,
            pass_accuracy=0.86,
        ),
    ]


@pytest.fixture
def sample_matches() -> dict[str, MatchRecord]:
    return {
        "DFL-MAT-INT01": MatchRecord(
            match_id="DFL-MAT-INT01", matchday=10,
            home_team_id="DFL-CLU-00000G", home_team_name="FC Bayern München",
            away_team_id="DFL-CLU-000007", away_team_name="Borussia Dortmund",
            result="4:2", home_goals=4, away_goals=2, total_goals=6,
            stadium_name="Allianz Arena", spectators=75000, sold_out=True,
        ),
        "DFL-MAT-INT02": MatchRecord(
            match_id="DFL-MAT-INT02", matchday=27,
            home_team_id="DFL-CLU-000007", home_team_name="Borussia Dortmund",
            away_team_id="DFL-CLU-00000G", away_team_name="FC Bayern München",
            result="1:0", home_goals=1, away_goals=0, total_goals=1,
            stadium_name="Signal Iduna Park", spectators=81365, sold_out=True,
        ),
    }


# End-to-end pipeline test

class TestEndToEndPipeline:
    """Full pipeline integration test using dry_run mode."""

    def test_full_pipeline_produces_valid_slides(
        self, bayern_user, bayern_club, bayern_players, sample_matches
    ):
        """Pipeline produces 7 slides with all required fields populated."""
        # Step 1: Build context
        ctx = build_context(bayern_user, bayern_club, bayern_players, sample_matches, tone="fan")

        # Step 2: Generate narratives (dry_run)
        narratives = generate_all_slides(ctx, dry_run=True)

        # Step 3: Assemble slides
        slides = assemble_slides(ctx, narratives)

        # Assert: correct number of slides
        assert 5 <= len(slides) <= 8, f"Expected 5-8 slides, got {len(slides)}"
        assert len(slides) == 8  # our pipeline now produces exactly 8

        # Assert: all required fields are non-empty strings
        for slide in slides:
            assert isinstance(slide, WrappedSlide)
            assert slide.slide_id, f"slide_id empty on {slide.slide_type}"
            assert slide.slide_type in VALID_SLIDE_TYPES, f"Invalid type: {slide.slide_type}"
            assert slide.headline, f"headline empty on {slide.slide_type}"
            assert slide.subtext, f"subtext empty on {slide.slide_type}"
            assert slide.club_color_hex.startswith("#"), f"Invalid color: {slide.club_color_hex}"
            assert slide.animation_type in VALID_ANIMATIONS, f"Invalid animation: {slide.animation_type}"
            assert slide.tone in VALID_TONES, f"Invalid tone: {slide.tone}"

    def test_slide_types_are_complete(
        self, bayern_user, bayern_club, bayern_players, sample_matches
    ):
        """All 7 expected slide types are present in the output."""
        ctx = build_context(bayern_user, bayern_club, bayern_players, sample_matches)
        narratives = generate_all_slides(ctx, dry_run=True)
        slides = assemble_slides(ctx, narratives)

        slide_types = {s.slide_type for s in slides}
        expected = {"hero", "fan_dna", "player_bond", "goal_of_season", "match_of_season", "season_arc", "personal_angle", "share"}
        assert slide_types == expected

    def test_slides_are_ordered_correctly(
        self, bayern_user, bayern_club, bayern_players, sample_matches
    ):
        """Slides are in the correct sequence (1-7)."""
        ctx = build_context(bayern_user, bayern_club, bayern_players, sample_matches)
        narratives = generate_all_slides(ctx, dry_run=True)
        slides = assemble_slides(ctx, narratives)

        expected_order = ["hero", "fan_dna", "player_bond", "goal_of_season", "match_of_season", "season_arc", "personal_angle", "share"]
        actual_order = [s.slide_type for s in slides]
        assert actual_order == expected_order

    def test_club_colors_applied(
        self, bayern_user, bayern_club, bayern_players, sample_matches
    ):
        """Club colors from the theme are applied to all slides."""
        ctx = build_context(bayern_user, bayern_club, bayern_players, sample_matches)
        narratives = generate_all_slides(ctx, dry_run=True)
        slides = assemble_slides(ctx, narratives)

        for slide in slides:
            assert slide.club_color_hex == "#DC052D"  # Bayern red
            assert slide.club_color_secondary_hex == "#0066B2"  # Bayern blue

    def test_tone_propagates_to_all_slides(
        self, bayern_user, bayern_club, bayern_players, sample_matches
    ):
        """The tone parameter is set on every slide."""
        ctx = build_context(bayern_user, bayern_club, bayern_players, sample_matches, tone="analyst")
        narratives = generate_all_slides(ctx, dry_run=True)
        slides = assemble_slides(ctx, narratives)

        for slide in slides:
            assert slide.tone == "analyst"


# Automation / multi-club test

class TestMultiClubAutomation:
    """Proves the pipeline produces different outputs for different clubs."""

    def test_different_clubs_produce_different_output(
        self,
        bayern_user, bayern_club, bayern_players,
        dortmund_user, dortmund_club, dortmund_players,
        sample_matches,
    ):
        """Bayern and Dortmund Wraps have different content (proves reusability)."""
        # Bayern pipeline
        ctx_bayern = build_context(bayern_user, bayern_club, bayern_players, sample_matches)
        narr_bayern = generate_all_slides(ctx_bayern, dry_run=True)
        slides_bayern = assemble_slides(ctx_bayern, narr_bayern)

        # Dortmund pipeline
        ctx_dortmund = build_context(dortmund_user, dortmund_club, dortmund_players, sample_matches)
        narr_dortmund = generate_all_slides(ctx_dortmund, dry_run=True)
        slides_dortmund = assemble_slides(ctx_dortmund, narr_dortmund)

        # Both produce 8 slides
        assert len(slides_bayern) == 8
        assert len(slides_dortmund) == 8

        # Colors are different (Bayern red vs Dortmund yellow)
        assert slides_bayern[0].club_color_hex != slides_dortmund[0].club_color_hex

        # Headlines reference different clubs
        bayern_headlines = " ".join(s.headline for s in slides_bayern)
        dortmund_headlines = " ".join(s.headline for s in slides_dortmund)
        assert "Bayern" in bayern_headlines or "Kane" in bayern_headlines
        assert "Dortmund" in dortmund_headlines or "Guirassy" in dortmund_headlines

        # Stat values differ (different engagement levels)
        assert slides_bayern[0].stat_value != slides_dortmund[0].stat_value

    def test_club_theme_differs_per_club(self):
        """get_club_theme returns different colors for different clubs."""
        bayern_theme = get_club_theme("DFL-CLU-00000G")
        dortmund_theme = get_club_theme("DFL-CLU-000007")

        assert bayern_theme["primary_hex"] != dortmund_theme["primary_hex"]
        assert bayern_theme["primary_hex"] == "#DC052D"
        assert dortmund_theme["primary_hex"] == "#FDE100"

    def test_unknown_club_gets_default_theme(self):
        """Unknown club ID returns sensible defaults without crashing."""
        theme = get_club_theme("DFL-CLU-UNKNOWN")
        assert theme["primary_hex"] == "#1A1A2E"
        assert theme["text_hex"] == "#FFFFFF"
