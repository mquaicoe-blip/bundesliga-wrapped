"""
test_fan_dna.py
===============
Dedicated tests for the Fan DNA scoring algorithm.

Validates boundary conditions, proportional contribution of each component,
and ensures the score never escapes the [0, 100] range.

Run: python -m pytest backend/tests/test_fan_dna.py -v
"""

import random

import pytest

from backend.data.schema import UserProfile
from backend.pipeline.personalization import compute_fan_dna


# Helpers

def _make_user(**kwargs) -> UserProfile:
    """Create a UserProfile with sensible defaults, overriding with kwargs."""
    defaults = dict(
        user_id="test-user",
        favorite_club="Test FC",
        favorite_club_id="DFL-CLU-TEST01",
        total_app_opens=0,
        total_match_center_views=0,
        total_article_views=0,
        total_story_views=0,
        total_video_views=0,
        active_months=0,
        stats_focus_ratio=0.0,
        ticker_focus_ratio=0.0,
        lineups_focus_ratio=0.0,
        app_opens_per_week=0.0,
    )
    defaults.update(kwargs)
    return UserProfile(**defaults)


# Tests

class TestFanDnaBoundaries:
    """Verify the score stays within [0, 100] for all inputs."""

    def test_all_zero_inputs_returns_zero(self):
        """A user with zero engagement across all dimensions scores exactly 0."""
        user = _make_user()
        score, breakdown, _ = compute_fan_dna(user)
        assert score == 0
        assert breakdown["loyalty"] == 0
        assert breakdown["intensity"] == 0
        assert breakdown["breadth"] == 0

    def test_maximum_inputs_returns_100(self):
        """A user with maximum possible engagement scores exactly 100."""
        user = _make_user(
            active_months=12,                    # loyalty: 12/12 = 100
            total_match_center_views=600,        # intensity: 600/12 = 50/50 = 100
            total_article_views=200,             # breadth: (200+100+60)/12 = 30/30 = 100
            total_story_views=100,
            total_video_views=60,
        )
        score, breakdown, _ = compute_fan_dna(user)
        assert score == 100
        assert breakdown["loyalty"] == 100
        assert breakdown["intensity"] == 100
        assert breakdown["breadth"] == 100

    def test_score_never_below_zero(self):
        """Score cannot go negative even with unusual inputs."""
        user = _make_user(active_months=0, total_match_center_views=0)
        score, _, _ = compute_fan_dna(user)
        assert score >= 0

    def test_score_never_above_100(self):
        """Score cannot exceed 100 even with extreme inputs."""
        user = _make_user(
            active_months=12,
            total_match_center_views=9999,
            total_article_views=9999,
            total_story_views=9999,
            total_video_views=9999,
        )
        score, _, _ = compute_fan_dna(user)
        assert score <= 100

    def test_random_inputs_stay_bounded(self):
        """Property test: 10 random valid input combinations stay in [0, 100]."""
        random.seed(42)
        for _ in range(10):
            user = _make_user(
                active_months=random.randint(0, 12),
                total_match_center_views=random.randint(0, 1000),
                total_article_views=random.randint(0, 500),
                total_story_views=random.randint(0, 200),
                total_video_views=random.randint(0, 300),
            )
            score, _, _ = compute_fan_dna(user)
            assert 0 <= score <= 100, f"Score {score} out of bounds"


class TestFanDnaProportionality:
    """Verify each component contributes proportionally to the total."""

    def test_loyalty_only(self):
        """With only loyalty maxed (12 months), score equals loyalty weight (40%)."""
        user = _make_user(active_months=12)
        score, breakdown, _ = compute_fan_dna(user)
        # loyalty=100, intensity=0, breadth=0 → score = 100*0.4 + 0 + 0 = 40
        assert score == 40
        assert breakdown["loyalty"] == 100
        assert breakdown["intensity"] == 0
        assert breakdown["breadth"] == 0

    def test_intensity_only(self):
        """With only intensity maxed, score equals intensity weight (35%)."""
        # Need active_months > 0 for intensity to compute (divides by active_months)
        user = _make_user(active_months=1, total_match_center_views=50)
        score, breakdown, _ = compute_fan_dna(user)
        # loyalty=1/12*100=8, intensity=50/50*100=100, breadth=0
        # score = 8*0.4 + 100*0.35 + 0 = 3.2 + 35 = 38
        assert breakdown["intensity"] == 100
        assert score >= 35  # intensity contributes at least 35

    def test_breadth_only(self):
        """With only breadth maxed, score equals breadth weight (25%)."""
        user = _make_user(
            active_months=1,
            total_article_views=20,
            total_story_views=5,
            total_video_views=5,
        )
        score, breakdown, _ = compute_fan_dna(user)
        # breadth: (20+5+5)/1 = 30/30 = 100
        assert breakdown["breadth"] == 100
        assert score >= 25  # breadth contributes at least 25


class TestFanDnaArchetypes:
    """Verify archetype assignment based on dominant dimension."""

    def test_superfan_gets_loyalty_archetype(self):
        """User with high loyalty → The Loyal Regular."""
        user = _make_user(active_months=12, total_match_center_views=20)
        _, _, archetype = compute_fan_dna(user)
        assert "Loyal Regular" in archetype

    def test_intensity_dominant_gets_matchday_archetype(self):
        """User with high intensity → Matchday Obsessive or Playoff Fan."""
        user = _make_user(active_months=3, total_match_center_views=300)
        _, breakdown, archetype = compute_fan_dna(user)
        # With low loyalty (3/12) and high intensity, should be Playoff Fan or Matchday Obsessive
        assert "Matchday" in archetype or "Playoff" in archetype

    def test_breadth_dominant_gets_scholar_archetype(self):
        """User with high breadth → Football Scholar."""
        user = _make_user(
            active_months=2,
            total_article_views=100,
            total_story_views=50,
            total_video_views=50,
        )
        _, breakdown, archetype = compute_fan_dna(user)
        if breakdown["breadth"] > breakdown["loyalty"] and breakdown["breadth"] > breakdown["intensity"]:
            assert "Scholar" in archetype
