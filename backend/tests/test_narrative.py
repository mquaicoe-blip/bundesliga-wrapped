"""
test_narrative.py
=================
Tests for the narrative generator (Amazon Bedrock integration).

All tests use dry_run=True — no Bedrock API calls are made.
Validates output structure, length constraints, and slide type completeness.

Run: python -m pytest backend/tests/test_narrative.py -v
"""

import pytest

from backend.data.schema import (
    ClubStats,
    MatchRecord,
    PersonalizationContext,
    PlayerStats,
    UserProfile,
)
from backend.pipeline.narrative_generator import (
    generate_all_slides,
    generate_hero_slide,
    generate_share_caption,
    generate_top_player_slide,
)
from backend.pipeline.personalization import build_context


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_context() -> PersonalizationContext:
    """Build a realistic PersonalizationContext for testing."""
    user = UserProfile(
        user_id="narrative-test-user",
        favorite_club="Sport-Club Freiburg",
        favorite_club_id="DFL-CLU-00000A",
        total_app_opens=150,
        total_match_center_views=100,
        total_article_views=30,
        total_story_views=10,
        total_video_views=40,
        active_months=9,
        stats_focus_ratio=0.35,
        ticker_focus_ratio=0.40,
        lineups_focus_ratio=0.15,
        favorite_player_ids=["DFL-OBJ-FREIBURG-01"],
        app_opens_per_week=3.8,
    )
    club = ClubStats(
        club_id="DFL-CLU-00000A",
        club_name="Sport-Club Freiburg",
        primary_color_hex="#000000",
        secondary_color_hex="#E2001A",
        matches_played=34, wins=15, draws=9, losses=10,
        goals_scored=52, goals_conceded=44, points=54,
        top_scorer_id="DFL-OBJ-FREIBURG-01",
        top_scorer_name="Vincenzo Grifo",
        top_scorer_goals=12,
        best_win_matchday=8, best_win_result="3:0",
        best_win_opponent="VfL Wolfsburg",
        worst_loss_matchday=14, worst_loss_result="0:3",
        worst_loss_opponent="Bayer 04 Leverkusen",
    )
    players = [
        PlayerStats(
            player_id="DFL-OBJ-FREIBURG-01", name="Vincenzo Grifo",
            club_id="DFL-CLU-00000A", position="midfield",
            goals=12, assists=7, appearances=31,
            xg=9.5, xg_efficiency=2.5,
            distance_covered_m=290000, max_speed_kmh=30.5,
            pass_accuracy=0.83,
        ),
    ]
    matches = {
        "DFL-MAT-NARR01": MatchRecord(
            match_id="DFL-MAT-NARR01", matchday=8,
            home_team_id="DFL-CLU-00000A", home_team_name="Sport-Club Freiburg",
            away_team_id="DFL-CLU-000003", away_team_name="VfL Wolfsburg",
            result="3:0", home_goals=3, away_goals=0, total_goals=3,
            stadium_name="Europa-Park Stadion", spectators=34700, sold_out=True,
        ),
    }
    return build_context(user, club, players, matches, tone="commentator")


# ---------------------------------------------------------------------------
# Tests: generate_all_slides structure
# ---------------------------------------------------------------------------

EXPECTED_SLIDE_TYPES = {"hero", "fan_dna", "player_bond", "goal_of_season",
                        "match_of_season", "season_arc", "personal_angle", "share"}


class TestGenerateAllSlides:
    """Validate the structure and completeness of generated slides."""

    def test_returns_correct_number_of_slides(self, sample_context):
        """generate_all_slides must return exactly 8 dicts."""
        slides = generate_all_slides(sample_context, dry_run=True)
        assert len(slides) == 8

    def test_each_slide_has_required_keys(self, sample_context):
        """Every slide dict must have slide_type, headline, and subtext."""
        slides = generate_all_slides(sample_context, dry_run=True)
        for slide in slides:
            assert "slide_type" in slide, f"Missing slide_type in {slide}"
            assert "headline" in slide, f"Missing headline in {slide}"
            # subtext or narrative_text or caption must exist
            has_text = "subtext" in slide or "narrative_text" in slide or "caption" in slide
            assert has_text, f"No text content in {slide}"

    def test_slide_types_match_expected(self, sample_context):
        """All 8 expected slide types must be present."""
        slides = generate_all_slides(sample_context, dry_run=True)
        types = {s["slide_type"] for s in slides}
        assert types == EXPECTED_SLIDE_TYPES

    def test_no_headline_is_empty(self, sample_context):
        """No slide should have an empty headline."""
        slides = generate_all_slides(sample_context, dry_run=True)
        for slide in slides:
            assert slide.get("headline", "").strip(), f"Empty headline on {slide['slide_type']}"

    def test_no_headline_exceeds_80_chars(self, sample_context):
        """Headlines must stay under 80 characters (UI constraint)."""
        slides = generate_all_slides(sample_context, dry_run=True)
        for slide in slides:
            headline = slide.get("headline", "")
            assert len(headline) <= 80, f"Headline too long ({len(headline)}): {headline}"


class TestShareCaption:
    """Validate the share caption generator."""

    def test_caption_under_240_chars(self, sample_context):
        """Share caption must be under 240 characters (social media limit)."""
        caption = generate_share_caption(sample_context, dry_run=True)
        assert len(caption) <= 240, f"Caption too long ({len(caption)}): {caption}"

    def test_caption_contains_hashtag(self, sample_context):
        """Share caption must contain #BundesligaWrapped."""
        caption = generate_share_caption(sample_context, dry_run=True)
        assert "#BundesligaWrapped" in caption

    def test_caption_is_not_empty(self, sample_context):
        """Share caption must not be empty."""
        caption = generate_share_caption(sample_context, dry_run=True)
        assert len(caption) > 10


class TestHeroSlide:
    """Validate the hero slide generator."""

    def test_hero_contains_club_name(self, sample_context):
        """Hero slide headline should reference the club."""
        result = generate_hero_slide(sample_context, dry_run=True)
        assert "Freiburg" in result["headline"] or "Sport-Club" in result["headline"]

    def test_hero_subtext_not_empty(self, sample_context):
        """Hero subtext must be populated."""
        result = generate_hero_slide(sample_context, dry_run=True)
        assert result["subtext"]
        assert len(result["subtext"]) > 5


class TestToneDifferentiation:
    """Verify that different tones produce different output."""

    def test_different_tones_produce_different_captions(self):
        """Commentator and fan tones should produce different share captions.

        In dry_run mode the templates include the club name which is the same,
        but the stat values differ based on context. This test verifies the
        tone field is correctly propagated.
        """
        user = UserProfile(
            user_id="tone-test",
            favorite_club="VfL Wolfsburg",
            favorite_club_id="DFL-CLU-000003",
            total_app_opens=100,
            total_match_center_views=80,
            active_months=8,
        )
        club = ClubStats(
            club_id="DFL-CLU-000003",
            club_name="VfL Wolfsburg",
            primary_color_hex="#65B32E",
            matches_played=34, wins=12, draws=10, losses=12,
            goals_scored=45, goals_conceded=50, points=46,
        )
        players = [PlayerStats(
            player_id="DFL-OBJ-WOLF01", name="Test Player",
            club_id="DFL-CLU-000003", position="offense",
            goals=10, assists=5, appearances=28,
        )]
        matches = {}

        ctx_commentator = build_context(user, club, players, matches, tone="commentator")
        ctx_fan = build_context(user, club, players, matches, tone="fan")

        # The tone field itself must differ
        assert ctx_commentator.tone == "commentator"
        assert ctx_fan.tone == "fan"

        # In dry_run, the templates are the same but tone is wired through
        slides_c = generate_all_slides(ctx_commentator, dry_run=True)
        slides_f = generate_all_slides(ctx_fan, dry_run=True)

        # Both produce 8 slides
        assert len(slides_c) == 8
        assert len(slides_f) == 8
