"""
slide_assembler.py
==================
Final assembly stage — combines AI-generated narratives, media assets, and club
theming into WrappedSlide objects ready for the React Native frontend.

Also provides the full end-to-end pipeline orchestrator ``run_pipeline()``.

S3 path conventions for media assets:
  Player images:  Challenge 1 – .../data/260210 Hackathon 2026 Recherche/...
  Goal clips:     Challenge 1 – .../data/260210 Hackathon 2026 Recherche/Goal Clips/...
  Highlights:     Challenge 1 – .../data/260210 Hackathon 2026 Recherche/Spiel-Highlights/...

Usage:
    from backend.pipeline.slide_assembler import run_pipeline

    slides = run_pipeline("DFL-CLU-00000G", "user-hash-123", dry_run=True)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from backend.config.aws_config import CHALLENGE_PREFIX, _get_bucket_name
from backend.data.schema import PersonalizationContext, Tone, WrappedSlide

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Club themes — all 18 Bundesliga clubs
# ---------------------------------------------------------------------------

CLUB_THEMES: dict[str, dict[str, str]] = {
    "DFL-CLU-00000G": {"primary_hex": "#DC052D", "secondary_hex": "#0066B2", "text_hex": "#FFFFFF"},  # Bayern
    "DFL-CLU-000007": {"primary_hex": "#FDE100", "secondary_hex": "#000000", "text_hex": "#000000"},  # Dortmund
    "DFL-CLU-00000B": {"primary_hex": "#E32221", "secondary_hex": "#000000", "text_hex": "#FFFFFF"},  # Leverkusen
    "DFL-CLU-000017": {"primary_hex": "#DD0741", "secondary_hex": "#FFFFFF", "text_hex": "#FFFFFF"},  # Leipzig
    "DFL-CLU-00000F": {"primary_hex": "#E1000F", "secondary_hex": "#000000", "text_hex": "#FFFFFF"},  # Frankfurt
    "DFL-CLU-00000D": {"primary_hex": "#E32219", "secondary_hex": "#FFFFFF", "text_hex": "#FFFFFF"},  # Stuttgart
    "DFL-CLU-00000A": {"primary_hex": "#000000", "secondary_hex": "#E2001A", "text_hex": "#FFFFFF"},  # Freiburg
    "DFL-CLU-00000E": {"primary_hex": "#1D9053", "secondary_hex": "#FFFFFF", "text_hex": "#FFFFFF"},  # Bremen
    "DFL-CLU-000004": {"primary_hex": "#000000", "secondary_hex": "#1DB954", "text_hex": "#FFFFFF"},  # Gladbach
    "DFL-CLU-000003": {"primary_hex": "#65B32E", "secondary_hex": "#FFFFFF", "text_hex": "#FFFFFF"},  # Wolfsburg
    "DFL-CLU-000006": {"primary_hex": "#C3002F", "secondary_hex": "#FFFFFF", "text_hex": "#FFFFFF"},  # Mainz
    "DFL-CLU-000010": {"primary_hex": "#BA3733", "secondary_hex": "#006B3F", "text_hex": "#FFFFFF"},  # Augsburg
    "DFL-CLU-00000V": {"primary_hex": "#EB1923", "secondary_hex": "#FFFFFF", "text_hex": "#FFFFFF"},  # Union Berlin
    "DFL-CLU-000002": {"primary_hex": "#1961B5", "secondary_hex": "#FFFFFF", "text_hex": "#FFFFFF"},  # Hoffenheim
    "DFL-CLU-000018": {"primary_hex": "#004B91", "secondary_hex": "#E2001A", "text_hex": "#FFFFFF"},  # Heidenheim
    "DFL-CLU-00000H": {"primary_hex": "#6B3A2A", "secondary_hex": "#FFFFFF", "text_hex": "#FFFFFF"},  # St. Pauli
    "DFL-CLU-00000S": {"primary_hex": "#005BA1", "secondary_hex": "#FFFFFF", "text_hex": "#FFFFFF"},  # Bochum
    "DFL-CLU-000N5P": {"primary_hex": "#003D7C", "secondary_hex": "#FFFFFF", "text_hex": "#FFFFFF"},  # Holstein Kiel
}

DEFAULT_THEME = {"primary_hex": "#1A1A2E", "secondary_hex": "#E94560", "text_hex": "#FFFFFF"}


def get_club_theme(club_id: str) -> dict[str, str]:
    """Return the color theme for a club.

    Looks up the club in CLUB_THEMES. Returns sensible dark defaults if the
    club is not found (e.g. 2. Bundesliga clubs in user data).

    Args:
        club_id: DFL-CLU-* identifier.

    Returns:
        Dict with keys: primary_hex, secondary_hex, text_hex.
    """
    theme = CLUB_THEMES.get(club_id, DEFAULT_THEME)
    logger.debug("Theme for %s: %s", club_id, theme)
    return theme


# ---------------------------------------------------------------------------
# 2. Media resolution
# ---------------------------------------------------------------------------

# Known video clips in the dataset (mapped by keyword for fuzzy matching)
_VIDEO_KEYWORDS = {
    "Kane": "2425_MDC_MD19_KaneGoalSMMF_916_ENG_01.mp4",
    "Davies": "9x16_DaviesGoalMD15_VJ_DIR_GOL_241223_03_MDF_4372981.mp4",
    "Musiala": "9x16_GoalMusiala_VJ_DIR_HED_250224_MDF_4486194.mp4",
    "Müller": "9x16_JamalMusialaGoalSMMF_VJ_DIR_GOL_241223_MDF_4373229.mp4",
}

# Goal clips with metadata for "Goal of the Season" selection
# Each entry: keyword → (filename, scorer_name, matchday, description)
GOAL_CLIPS: dict[str, dict] = {
    "Kane_MD19": {
        "filename": "2425_MDC_MD19_KaneGoalSMMF_916_ENG_01.mp4",
        "scorer": "Harry Kane",
        "player_id": "DFL-OBJ-J00ZZ3",
        "matchday": 19,
        "description": "Kane's clinical finish on Matchday 19",
    },
    "Davies_MD15": {
        "filename": "9x16_DaviesGoalMD15_VJ_DIR_GOL_241223_03_MDF_4372981.mp4",
        "scorer": "Alphonso Davies",
        "player_id": "DFL-OBJ-002G9V",
        "matchday": 15,
        "description": "Davies' surging run and finish on Matchday 15",
    },
    "Musiala_MD24": {
        "filename": "9x16_GoalMusiala_VJ_DIR_HED_250224_MDF_4486194.mp4",
        "scorer": "Jamal Musiala",
        "player_id": "DFL-OBJ-002GBK",
        "matchday": 24,
        "description": "Musiala's dazzling solo goal on Matchday 24",
    },
    "Musiala_MD15": {
        "filename": "9x16_JamalMusialaGoalSMMF_VJ_DIR_GOL_241223_MDF_4373229.mp4",
        "scorer": "Jamal Musiala",
        "player_id": "DFL-OBJ-002GBK",
        "matchday": 15,
        "description": "Musiala's instinctive strike on Matchday 15",
    },
}

_HIGHLIGHT_KEYWORDS = {
    "Leipzig": "Highlights-International-HD-1-BL-2024-2025-15-Spieltag-FC-Bayern-Muenchen-vs-RB-Leipzig-PGM_4366841.mp4",
    "Dortmund": "Highlights-International-HD-1-BL-2024-2025-29-Spieltag-FC-Bayern-Muenchen-vs-Borussia-Dortmund-PGM_4580319.mp4",
    "Kiel": "Highlights-International-HD-1-BL-2024-2025-3-Spieltag-Holstein-Kiel-vs-FC-Bayern-Muenchen-PGM_4182701.mp4",
    "Frankfurt": "Highlights-International-HD-1-BL-2024-2025-6-Spieltag-Eintracht-Frankfurt-vs-FC-Bayern-Muenchen-PGM_4222188.mp4",
}


def resolve_media(
    club_id: str,
    player_id: str,
    match_id: Optional[str] = None,
    player_name: str = "",
    opponent_name: str = "",
) -> dict[str, str]:
    """Resolve pre-signed S3 URLs for player images and highlight videos.

    Tries to find a matching video clip based on player name or opponent name.
    Returns placeholder URLs if no matching asset is found — never crashes.

    Args:
        club_id: DFL-CLU-* for the user's club.
        player_id: DFL-OBJ-* for the top player.
        match_id: Optional match ID for highlight video lookup.
        player_name: Player display name (for fuzzy video matching).
        opponent_name: Opponent name (for highlight video matching).

    Returns:
        Dict with keys: player_image_url, highlight_video_url (may be empty string).
    """
    from backend.data.s3_loader import get_presigned_url

    result = {"player_image_url": "", "highlight_video_url": ""}

    # ── Player image / goal clip ──────────────────────────────────────────────
    # Try to find a goal clip featuring this player (best visual asset we have)
    for keyword, filename in _VIDEO_KEYWORDS.items():
        if keyword.lower() in player_name.lower():
            s3_key = f"{CHALLENGE_PREFIX}/data/260210 Hackathon 2026 Recherche/Goal Clips/{filename}"
            try:
                result["player_image_url"] = get_presigned_url(s3_key, expiry=3600)
                logger.info("Resolved player media for '%s': %s", player_name, filename)
            except Exception as exc:
                logger.debug("Could not resolve player media: %s", exc)
            break

    # ── Highlight video ───────────────────────────────────────────────────────
    # Try to match opponent name to a highlight package
    if opponent_name:
        for keyword, filename in _HIGHLIGHT_KEYWORDS.items():
            if keyword.lower() in opponent_name.lower():
                s3_key = f"{CHALLENGE_PREFIX}/data/260210 Hackathon 2026 Recherche/Spiel-Highlights/{filename}"
                try:
                    result["highlight_video_url"] = get_presigned_url(s3_key, expiry=3600)
                    logger.info("Resolved highlight for opponent '%s': %s", opponent_name, filename)
                except Exception as exc:
                    logger.debug("Could not resolve highlight: %s", exc)
                break

    return result


# ---------------------------------------------------------------------------
# 2b. Goal of the Season selection
# ---------------------------------------------------------------------------

def select_goal_of_season(
    ctx: "PersonalizationContext",
) -> dict[str, str]:
    """Select the "Goal of the Season" for this user and return media info.

    Selection logic:
      1. Find all goal clips available for the user's club's players
      2. Score each clip:
         - Player is user's favourite: +0.5
         - Player has high xG efficiency (overperformance): +0.3
         - Clip exists (we can actually show it): +0.2
      3. Pick the highest-scored goal
      4. Return the clip URL + description

    If no clips are available for the user's club, returns empty strings
    (the slide will use Bedrock to describe the top scorer's best goal instead).

    Args:
        ctx: PersonalizationContext with user, club, and player data.

    Returns:
        Dict with keys: goal_clip_url, scorer_name, description, matchday.
    """
    from backend.data.s3_loader import get_presigned_url

    result = {"goal_clip_url": "", "scorer_name": "", "description": "", "matchday": 0}

    # Only Bayern has goal clips in this dataset
    if ctx.club.club_id != "DFL-CLU-00000G":
        # Fallback: use the top scorer's stats to describe their best goal
        if ctx.favourite_player and ctx.favourite_player.goals > 0:
            result["scorer_name"] = ctx.favourite_player.name
            result["description"] = (
                f"{ctx.favourite_player.name}'s best goal this season "
                f"(xG efficiency: {ctx.favourite_player.xg_efficiency:+.2f})"
            )
        return result

    # Score each available goal clip for relevance to this user
    user_fav_ids = set(ctx.user.favorite_player_ids)
    scored_clips: list[tuple[float, str, dict]] = []

    for clip_key, clip_info in GOAL_CLIPS.items():
        score = 0.2  # base score for having a clip at all

        # Bonus if the scorer is the user's favourite player
        if clip_info["player_id"] in user_fav_ids:
            score += 0.5

        # Bonus for xG efficiency (find the player in our context)
        if ctx.favourite_player and ctx.favourite_player.player_id == clip_info["player_id"]:
            # Higher xG efficiency = more spectacular goal
            efficiency = ctx.favourite_player.xg_efficiency
            score += min(0.3, max(0, efficiency / 10))  # normalise to 0-0.3

        scored_clips.append((score, clip_key, clip_info))

    if not scored_clips:
        return result

    # Pick the best
    scored_clips.sort(key=lambda x: -x[0])
    best_score, best_key, best_info = scored_clips[0]

    # Generate pre-signed URL for the clip
    s3_key = f"{CHALLENGE_PREFIX}/data/260210 Hackathon 2026 Recherche/Goal Clips/{best_info['filename']}"
    try:
        clip_url = get_presigned_url(s3_key, expiry=3600)
    except Exception:
        clip_url = ""

    result["goal_clip_url"] = clip_url
    result["scorer_name"] = best_info["scorer"]
    result["description"] = best_info["description"]
    result["matchday"] = best_info["matchday"]

    logger.info("Goal of the Season: %s (score=%.2f)", best_info["description"], best_score)
    return result


# ---------------------------------------------------------------------------
# 3. Slide assembly
# ---------------------------------------------------------------------------

# Animation type mapping — each slide type gets a specific animation hint
ANIMATION_MAP: dict[str, str] = {
    "hero": "fade",
    "fan_dna": "counter",
    "player_bond": "slide_up",
    "goal_of_season": "slide_up",
    "match_of_season": "slide_up",
    "season_arc": "counter",
    "personal_angle": "pulse",
    "share": "fade",
}


def assemble_slides(
    ctx: PersonalizationContext,
    narratives: list[dict],
) -> list[WrappedSlide]:
    """Combine narrative copy, media URLs, and club theme into WrappedSlide objects.

    Takes the raw narrative dicts from generate_all_slides() and enriches them
    with theming, media, and animation hints to produce the final output objects
    consumed by the React Native frontend.

    Args:
        ctx: The PersonalizationContext used to generate narratives.
        narratives: Output from generate_all_slides() — list of 7 dicts.

    Returns:
        Ordered list of WrappedSlide objects (one per slide).
    """
    theme = get_club_theme(ctx.club.club_id)

    # Resolve media assets
    player_name = ctx.favourite_player.name if ctx.favourite_player else ""
    opponent_name = ""
    if ctx.best_match:
        is_home = ctx.best_match.home_team_id == ctx.club.club_id
        opponent_name = ctx.best_match.away_team_name if is_home else ctx.best_match.home_team_name

    try:
        media = resolve_media(
            club_id=ctx.club.club_id,
            player_id=ctx.favourite_player.player_id if ctx.favourite_player else "",
            match_id=ctx.best_match.match_id if ctx.best_match else None,
            player_name=player_name,
            opponent_name=opponent_name,
        )
    except Exception as exc:
        logger.warning("Media resolution failed: %s. Using empty URLs.", exc)
        media = {"player_image_url": "", "highlight_video_url": ""}

    # Resolve Goal of the Season clip
    try:
        goal_info = select_goal_of_season(ctx)
    except Exception as exc:
        logger.warning("Goal of season selection failed: %s", exc)
        goal_info = {"goal_clip_url": "", "scorer_name": "", "description": "", "matchday": 0}

    slides: list[WrappedSlide] = []

    for narr in narratives:
        slide_type = narr.get("slide_type", "hero")
        slide_num = narr.get("slide_number", 0)

        # Determine media URL for this specific slide
        media_url = ""
        media_type = "none"
        if slide_type == "player_bond" and media["player_image_url"]:
            media_url = media["player_image_url"]
            media_type = "video_thumbnail"
        elif slide_type == "goal_of_season" and goal_info["goal_clip_url"]:
            media_url = goal_info["goal_clip_url"]
            media_type = "video_thumbnail"
        elif slide_type == "match_of_season" and media["highlight_video_url"]:
            media_url = media["highlight_video_url"]
            media_type = "video_thumbnail"

        # Determine stat value/label for slides that have them
        stat_value = ""
        stat_label = ""
        if slide_type == "hero":
            stat_value = str(ctx.hero_stat_value)
            stat_label = ctx.hero_stat_label
        elif slide_type == "fan_dna":
            stat_value = str(ctx.fan_dna_score)
            stat_label = f"/100 — {ctx.fan_dna_archetype}"
        elif slide_type == "player_bond" and ctx.favourite_player:
            stat_value = str(ctx.player_bond_stat_value or "")
            stat_label = ctx.player_bond_stat_label
        elif slide_type == "goal_of_season" and goal_info["scorer_name"]:
            stat_value = goal_info["scorer_name"]
            stat_label = f"Matchday {goal_info['matchday']}" if goal_info["matchday"] else ""

        slide = WrappedSlide(
            slide_id=f"slide-{slide_num}-{slide_type}",
            slide_type=slide_type,
            headline=narr.get("headline", ""),
            subtext=narr.get("subtext", narr.get("narrative_text", narr.get("caption", ""))),
            stat_value=stat_value,
            stat_label=stat_label,
            media_url=media_url,
            media_type=media_type,
            club_color_hex=theme["primary_hex"],
            club_color_secondary_hex=theme["secondary_hex"],
            animation_type=ANIMATION_MAP.get(slide_type, "fade"),
            tone=ctx.tone,
        )
        slides.append(slide)

    logger.info("Assembled %d WrappedSlide objects.", len(slides))
    return slides


# ---------------------------------------------------------------------------
# 4. Export to JSON + S3
# ---------------------------------------------------------------------------

def export_wrapped_json(
    slides: list[WrappedSlide],
    output_path: str,
    club_id: str = "",
    user_id: str = "",
    upload_to_s3: bool = False,
) -> None:
    """Serialize slides to JSON and optionally upload to S3.

    The JSON output is the contract between the backend pipeline and the
    React Native frontend. The app fetches this file to render all slides.

    S3 upload path: wrapped/{club_id}/{user_id}/wrapped.json

    Args:
        slides: List of assembled WrappedSlide objects.
        output_path: Local filesystem path to write the JSON file.
        club_id: DFL-CLU-* (used for S3 key if uploading).
        user_id: User hash (used for S3 key if uploading).
        upload_to_s3: If True, also uploads to S3.
    """
    # Serialize using dataclasses.asdict for clean JSON output
    data = [asdict(slide) for slide in slides]
    json_str = json.dumps(data, indent=2, ensure_ascii=False)

    # Write locally
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json_str, encoding="utf-8")
    logger.info("Exported %d slides to %s (%.1f KB)", len(slides), dest, len(json_str) / 1024)

    # Upload to S3 if requested
    if upload_to_s3 and club_id and user_id:
        try:
            from backend.config.aws_config import get_s3_client
            bucket = _get_bucket_name()
            s3_key = f"wrapped/{club_id}/{user_id}/wrapped.json"
            s3 = get_s3_client()
            s3.put_object(
                Bucket=bucket,
                Key=s3_key,
                Body=json_str.encode("utf-8"),
                ContentType="application/json",
            )
            logger.info("Uploaded wrapped.json to s3://%s/%s", bucket, s3_key)
        except Exception as exc:
            logger.error("S3 upload failed: %s. Local file still saved.", exc)


# ---------------------------------------------------------------------------
# 5. Full pipeline orchestrator
# ---------------------------------------------------------------------------

def run_pipeline(
    club_id: str,
    user_id: str,
    tone: Tone = "commentator",
    dry_run: bool = False,
    output_dir: str = "output",
) -> list[WrappedSlide]:
    """Run the full Bundesliga Wrapped pipeline end-to-end.

    Steps:
      1. Load user profile from JSON dataset
      2. Load club stats (derived from match files)
      3. Load player stats for the club
      4. Build PersonalizationContext (scoring engine)
      5. Generate AI narratives (Bedrock or dry-run)
      6. Assemble final WrappedSlide objects
      7. Export to JSON

    Each step is timed and logged for observability.

    Args:
        club_id: DFL-CLU-* identifier for the club.
        user_id: SHA-256 hash of the user (from JSON dataset).
        tone: Narrative tone ("commentator" | "analyst" | "fan").
        dry_run: If True, skip Bedrock calls and use templated narratives.
        output_dir: Directory for the output JSON file.

    Returns:
        List of assembled WrappedSlide objects.
    """
    total_start = time.time()

    # ── Step 1: Load user profile ─────────────────────────────────────────────
    t = time.time()
    if dry_run:
        # Use a mock user for dry-run — dynamically uses the requested club_id
        from backend.data.schema import UserProfile
        from backend.data.data_loader import CLUB_ID_TO_NAME
        club_name_resolved = CLUB_ID_TO_NAME.get(club_id, "Unknown Club")
        user = UserProfile(
            user_id=user_id,
            favorite_club_id=club_id,
            favorite_club=club_name_resolved,
            total_app_opens=220,
            total_match_center_views=180,
            total_article_views=45,
            total_story_views=20,
            total_video_views=60,
            active_months=11,
            stats_focus_ratio=0.45,
            ticker_focus_ratio=0.30,
            lineups_focus_ratio=0.15,
            favorite_player_ids=[],
            app_opens_per_week=4.7,
        )
    else:
        from backend.data.data_loader import load_user_profile
        user = load_user_profile(user_id)
    logger.info("Step 1 — User profile loaded (%.1fs)", time.time() - t)

    # ── Step 2: Load club stats ───────────────────────────────────────────────
    t = time.time()
    if dry_run:
        from backend.data.schema import ClubStats
        theme = get_club_theme(club_id)
        club = ClubStats(
            club_id=club_id,
            club_name=club_name_resolved,
            primary_color_hex=theme["primary_hex"],
            secondary_color_hex=theme["secondary_hex"],
            matches_played=34, wins=18, draws=8, losses=8,
            goals_scored=62, goals_conceded=45, points=62,
            top_scorer_id=f"DFL-OBJ-MOCK-{club_id[-4:]}",
            top_scorer_name=f"Top Scorer ({club_name_resolved})",
            top_scorer_goals=16,
            best_win_matchday=12, best_win_result="4:0",
            best_win_opponent="Opponent FC",
            worst_loss_matchday=7, worst_loss_result="0:3",
            worst_loss_opponent="Rival FC",
        )
    else:
        from backend.data.data_loader import load_club_stats
        club = load_club_stats(club_id)
    logger.info("Step 2 — Club stats loaded (%.1fs)", time.time() - t)

    # ── Step 3: Load player stats ─────────────────────────────────────────────
    t = time.time()
    if dry_run:
        from backend.data.schema import PlayerStats
        players = [
            PlayerStats(
                player_id=f"DFL-OBJ-MOCK-{club_id[-4:]}-01",
                name=f"Star Player ({club_name_resolved})",
                club_id=club_id, position="offense",
                goals=16, assists=8, appearances=32,
                xg=13.5, xg_efficiency=2.5,
                distance_covered_m=280000, max_speed_kmh=33.5,
                pass_accuracy=0.80,
            ),
            PlayerStats(
                player_id=f"DFL-OBJ-MOCK-{club_id[-4:]}-02",
                name=f"Midfield Engine ({club_name_resolved})",
                club_id=club_id, position="midfield",
                goals=6, assists=12, appearances=30,
                xg=4.2, xg_efficiency=1.8,
                distance_covered_m=320000, max_speed_kmh=31.0,
                pass_accuracy=0.87,
            ),
        ]
    else:
        from backend.data.data_loader import load_player_stats
        players = load_player_stats(club_id)
    logger.info("Step 3 — Player stats loaded: %d players (%.1fs)", len(players), time.time() - t)

    # ── Step 4: Load matches + build context ──────────────────────────────────
    t = time.time()
    if dry_run:
        from backend.data.schema import MatchRecord
        # Generate mock matches featuring the requested club (not hardcoded Bayern)
        matches = {
            "DFL-MAT-MOCK01": MatchRecord(
                match_id="DFL-MAT-MOCK01", matchday=10,
                home_team_id=club_id, home_team_name=club_name_resolved,
                away_team_id="DFL-CLU-000007", away_team_name="Borussia Dortmund",
                result="3:1", home_goals=3, away_goals=1, total_goals=4,
                stadium_name="Home Stadium", spectators=50000, sold_out=True,
            ),
            "DFL-MAT-MOCK02": MatchRecord(
                match_id="DFL-MAT-MOCK02", matchday=25,
                home_team_id="DFL-CLU-000017", home_team_name="RB Leipzig",
                away_team_id=club_id, away_team_name=club_name_resolved,
                result="1:2", home_goals=1, away_goals=2, total_goals=3,
                stadium_name="Red Bull Arena", spectators=47000, sold_out=True,
            ),
        }
    else:
        from backend.data.data_loader import load_match_overview
        matches = load_match_overview()

    from backend.pipeline.personalization import build_context
    ctx = build_context(user, club, players, matches, tone=tone)
    logger.info("Step 4 — Context built (%.1fs)", time.time() - t)

    # ── Step 5: Generate narratives ───────────────────────────────────────────
    t = time.time()
    from backend.pipeline.narrative_generator import generate_all_slides
    narratives = generate_all_slides(ctx, dry_run=dry_run)
    logger.info("Step 5 — Narratives generated: %d slides (%.1fs)", len(narratives), time.time() - t)

    # ── Step 6: Assemble slides ───────────────────────────────────────────────
    t = time.time()
    slides = assemble_slides(ctx, narratives)
    logger.info("Step 6 — Slides assembled (%.1fs)", time.time() - t)

    # ── Step 7: Export ────────────────────────────────────────────────────────
    t = time.time()
    output_path = f"{output_dir}/{club_id}/{user_id}/wrapped.json"
    export_wrapped_json(
        slides, output_path,
        club_id=club_id, user_id=user_id,
        upload_to_s3=(not dry_run),
    )
    logger.info("Step 7 — Exported (%.1fs)", time.time() - t)

    total_elapsed = time.time() - total_start
    logger.info(
        "Pipeline complete: %d slides for user=%s, club=%s in %.1fs (dry_run=%s)",
        len(slides), user_id[:12], club_id, total_elapsed, dry_run,
    )

    return slides


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Bundesliga Wrapped — Full pipeline runner"
    )
    parser.add_argument(
        "--club-id",
        default="DFL-CLU-00000G",
        help="DFL-CLU-* identifier (default: Bayern München)",
    )
    parser.add_argument(
        "--user-id",
        default="demo-user-001",
        help="User ID hash (default: demo-user-001)",
    )
    parser.add_argument(
        "--tone",
        choices=["commentator", "analyst", "fan"],
        default="commentator",
        help="Narrative tone (default: commentator)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use mock data and skip Bedrock calls",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Output directory for wrapped.json (default: output/)",
    )
    args = parser.parse_args()

    slides = run_pipeline(
        club_id=args.club_id,
        user_id=args.user_id,
        tone=args.tone,
        dry_run=args.dry_run,
        output_dir=args.output_dir,
    )

    # Pretty-print summary
    print("\n" + "=" * 60)
    print("  BUNDESLIGA WRAPPED — Pipeline Output")
    print(f"  Club: {args.club_id} | User: {args.user_id} | Tone: {args.tone}")
    print("=" * 60)

    for slide in slides:
        print(f"\n  [{slide.slide_id}] {slide.slide_type.upper()}")
        print(f"    Headline:  {slide.headline}")
        print(f"    Subtext:   {slide.subtext[:80]}{'...' if len(slide.subtext) > 80 else ''}")
        if slide.stat_value:
            print(f"    Stat:      {slide.stat_value} {slide.stat_label}")
        if slide.media_url:
            print(f"    Media:     {slide.media_type} ({slide.media_url[:60]}...)")
        print(f"    Animation: {slide.animation_type}")
        print(f"    Colors:    {slide.club_color_hex} / {slide.club_color_secondary_hex}")

    print("\n" + "=" * 60)
    print(f"  Output: {args.output_dir}/{args.club_id}/{args.user_id}/wrapped.json")
    print("=" * 60 + "\n")
