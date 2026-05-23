"""
narrative_generator.py
======================
Generates personalized narrative copy for each Wrapped slide using Amazon Bedrock
(Claude Sonnet claude-sonnet-4-6).

All prompts use the Messages API format with XML-structured prompts. The tone
parameter on PersonalizationContext shifts the entire narrative voice — no
separate code paths per tone.

Every function supports dry_run=True for testing without burning tokens.

Usage:
    from backend.pipeline.narrative_generator import generate_all_slides

    slides = generate_all_slides(ctx, dry_run=False)
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from backend.config.aws_config import get_bedrock_client
from backend.data.schema import PersonalizationContext, PlayerStats

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODEL_ID = "anthropic.claude-sonnet-4-6-20250514-v1:0"
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0  # seconds — doubles on each retry

# Token usage tracking (module-level accumulator for cost awareness)
_total_input_tokens = 0
_total_output_tokens = 0


# ---------------------------------------------------------------------------
# Core Bedrock call with retry logic
# ---------------------------------------------------------------------------

def _call_bedrock(
    prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 300,
) -> str:
    """Send a prompt to Bedrock and return the text response.

    Implements exponential backoff with up to MAX_RETRIES attempts.
    Logs input/output token counts for cost tracking.

    Args:
        prompt: The user message content.
        temperature: Sampling temperature (0.3 for factual, 0.7 for creative).
        max_tokens: Maximum tokens in the response.

    Returns:
        Raw text response from the model.

    Raises:
        RuntimeError: If all retries are exhausted.
    """
    global _total_input_tokens, _total_output_tokens

    client = get_bedrock_client()
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [
            {"role": "user", "content": prompt}
        ],
    })

    last_error: Optional[Exception] = None

    for attempt in range(MAX_RETRIES):
        try:
            response = client.invoke_model(
                modelId=MODEL_ID,
                contentType="application/json",
                accept="application/json",
                body=body,
            )
            result = json.loads(response["body"].read())

            # Track token usage for cost awareness
            usage = result.get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            _total_input_tokens += input_tokens
            _total_output_tokens += output_tokens
            logger.info(
                "Bedrock call: %d input tokens, %d output tokens (cumulative: %d/%d)",
                input_tokens, output_tokens, _total_input_tokens, _total_output_tokens,
            )

            # Extract text from the response content blocks
            content = result.get("content", [])
            text_parts = [block["text"] for block in content if block.get("type") == "text"]
            return "\n".join(text_parts)

        except Exception as exc:
            last_error = exc
            delay = RETRY_BASE_DELAY * (2 ** attempt)
            logger.warning(
                "Bedrock call failed (attempt %d/%d): %s. Retrying in %.1fs...",
                attempt + 1, MAX_RETRIES, exc, delay,
            )
            time.sleep(delay)

    raise RuntimeError(
        f"Bedrock call failed after {MAX_RETRIES} retries. Last error: {last_error}"
    )


def _parse_json_response(raw: str) -> dict[str, Any]:
    """Parse a JSON response from Bedrock, handling markdown code fences.

    The model sometimes wraps JSON in ```json ... ``` — we strip that.

    Args:
        raw: Raw text response from Bedrock.

    Returns:
        Parsed dict.

    Raises:
        ValueError: If the response cannot be parsed as JSON.
    """
    text = raw.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json) and last line (```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse Bedrock response as JSON: %s", text[:200])
        raise ValueError(f"Invalid JSON from Bedrock: {exc}") from exc


# ---------------------------------------------------------------------------
# Tone descriptions (injected into every prompt)
# ---------------------------------------------------------------------------

TONE_DESCRIPTIONS = {
    "commentator": "Dramatic, broadcast-style. Like a TV commentator narrating the final whistle. Bold, declarative, uses football metaphors.",
    "analyst": "Data-forward, tactical. Like a pundit breaking down the numbers. Precise, insightful, references specific stats.",
    "fan": "Casual, Gen Z energy. Like texting your mate after the match. Short sentences, slang OK, emojis allowed, hype language.",
}


def _tone_instruction(ctx: PersonalizationContext) -> str:
    """Build the tone instruction block for prompts."""
    return TONE_DESCRIPTIONS.get(ctx.tone, TONE_DESCRIPTIONS["commentator"])


# ---------------------------------------------------------------------------
# Slide generators
# ---------------------------------------------------------------------------

def generate_hero_slide(ctx: PersonalizationContext, dry_run: bool = False) -> dict:
    """Generate copy for Slide 1: Hero / Identity card.

    Returns:
        {"headline": str (max 80 chars), "subtext": str (max 120 chars)}
    """
    if dry_run:
        return {
            "headline": f"What a season, {ctx.club.club_name} fan",
            "subtext": f"You showed up {ctx.hero_stat_value} times. That's dedication.",
        }

    prompt = f"""<context>
You are writing copy for a "Bundesliga Wrapped" feature — a Spotify Wrapped-style
personalized season summary for a football fan.

Club: {ctx.club.club_name}
Season narrative: {ctx.club.wins}W {ctx.club.draws}D {ctx.club.losses}L, {ctx.club.goals_scored} goals scored
Hero stat: {ctx.hero_stat_value} {ctx.hero_stat_label}
Fan DNA score: {ctx.fan_dna_score}/100 ({ctx.fan_dna_archetype})
</context>

<instructions>
Write a headline and subtext for the opening "hero" slide of this fan's Wrapped.

Tone: {_tone_instruction(ctx)}

Rules:
- headline: punchy 3-5 words, club-specific, feels like a rallying cry. Max 80 characters.
- subtext: one sentence that makes the fan feel seen. Reference their hero stat. Max 120 characters.
- Do NOT use corporate language like "impressive performance" or "remarkable achievement"
- Do NOT use generic phrases that could apply to any club
- Make it feel personal and specific to THIS fan's season
</instructions>

<format>
Respond with ONLY a JSON object, no other text:
{{"headline": "...", "subtext": "..."}}
</format>"""

    raw = _call_bedrock(prompt, temperature=0.7, max_tokens=150)
    result = _parse_json_response(raw)

    # Enforce length limits — truncate gracefully if model exceeded them
    result["headline"] = result.get("headline", "")[:80]
    result["subtext"] = result.get("subtext", "")[:120]
    return result


def generate_top_player_slide(ctx: PersonalizationContext, dry_run: bool = False) -> dict:
    """Generate copy for Slide 3: Player Bond.

    Returns:
        {"headline": str, "subtext": str, "fun_fact": str}
    """
    player = ctx.favourite_player
    if not player:
        return {"headline": "Your Player", "subtext": "No player data available", "fun_fact": ""}

    if dry_run:
        return {
            "headline": f"{player.name}",
            "subtext": f"{player.goals} goals, {player.assists} assists this season",
            "fun_fact": f"Covered {player.distance_covered_m/1000:.0f}km — enough to run to the next city",
        }

    is_favourite = player.player_id in ctx.user.favorite_player_ids
    personal_touch = "This is the user's explicitly chosen favourite player — make it feel personal." if is_favourite else ""

    prompt = f"""<context>
Bundesliga Wrapped — Player Bond slide.

Player: {player.name} ({player.position})
Club: {ctx.club.club_name}
Goals: {player.goals} | Assists: {player.assists} | Appearances: {player.appearances}
xG: {player.xg:.2f} | xG efficiency: {player.xg_efficiency:+.2f}
Distance covered: {player.distance_covered_m/1000:.1f} km
Pass accuracy: {player.pass_accuracy*100:.1f}%
Max speed: {player.max_speed_kmh:.1f} km/h
{personal_touch}
</context>

<instructions>
Write copy for the player bond slide.

Tone: {_tone_instruction(ctx)}

Rules:
- headline: the player's name styled as a title (2-4 words). Max 50 chars.
- subtext: one sentence about their season impact. Reference a specific stat. Max 120 chars.
- fun_fact: one surprising or unexpected angle on their season. Something the fan probably didn't know. Max 100 chars.
- Do NOT just list stats — tell a micro-story
- Do NOT use "impressive" or "remarkable"
</instructions>

<format>
Respond with ONLY a JSON object:
{{"headline": "...", "subtext": "...", "fun_fact": "..."}}
</format>"""

    raw = _call_bedrock(prompt, temperature=0.7, max_tokens=200)
    result = _parse_json_response(raw)
    result["headline"] = result.get("headline", player.name)[:50]
    result["subtext"] = result.get("subtext", "")[:120]
    result["fun_fact"] = result.get("fun_fact", "")[:100]
    return result


def generate_season_journey_slide(ctx: PersonalizationContext, dry_run: bool = False) -> dict:
    """Generate copy for Slide 5: Season Arc Narrative.

    Returns:
        {"headline": str, "narrative_text": str}
    """
    if dry_run:
        # Include monthly timeline summary if available
        timeline_summary = ""
        if ctx.monthly_timeline:
            peak = next((m for m in ctx.monthly_timeline if m.get("peak")), None)
            if peak:
                timeline_summary = f" Your peak month was {peak['month']}."
        return {
            "headline": "The Season That Was",
            "narrative_text": f"{ctx.club.club_name} scored {ctx.club.goals_scored} goals across 34 matchdays.{timeline_summary} "
                             f"The highlight? {ctx.best_match_reason or 'Every single matchday.'}",
        }

    moments_text = "\n".join(f"- {m}" for m in ctx.season_arc_moments) if ctx.season_arc_moments else "No specific moments available"

    from backend.pipeline.personalization import classify_season_narrative
    narrative_type = classify_season_narrative(ctx.club)

    prompt = f"""<context>
Bundesliga Wrapped — Season Arc slide.

Club: {ctx.club.club_name}
Record: {ctx.club.wins}W {ctx.club.draws}D {ctx.club.losses}L | {ctx.club.goals_scored} scored, {ctx.club.goals_conceded} conceded
Points: {ctx.club.points}
Season type: {narrative_type}
Best win: Matchday {ctx.club.best_win_matchday} — {ctx.club.best_win_result} vs {ctx.club.best_win_opponent}
Worst loss: Matchday {ctx.club.worst_loss_matchday} — {ctx.club.worst_loss_result} vs {ctx.club.worst_loss_opponent}

Key moments for this fan:
{moments_text}
</context>

<instructions>
Write copy for the season journey slide — telling the story of this club's season.

Tone: {_tone_instruction(ctx)}

Adapt the narrative to the season type:
- "title_race": triumphant, dominant, celebrating excellence
- "comeback": resilience, turning point, never giving up
- "solid": consistency, reliability, quiet pride
- "struggle": grit, hope, looking forward

Rules:
- headline: 3-5 words capturing the season's essence. Max 60 chars.
- narrative_text: exactly 2 sentences telling the arc. First sentence = the journey. Second = the payoff or lesson. Max 200 chars total.
- Reference at least one specific match moment
- Do NOT use "impressive" or "remarkable" or "incredible"
</instructions>

<format>
Respond with ONLY a JSON object:
{{"headline": "...", "narrative_text": "..."}}
</format>"""

    raw = _call_bedrock(prompt, temperature=0.7, max_tokens=200)
    result = _parse_json_response(raw)
    result["headline"] = result.get("headline", "")[:60]
    result["narrative_text"] = result.get("narrative_text", "")[:200]
    return result


def generate_share_caption(ctx: PersonalizationContext, dry_run: bool = False) -> str:
    """Generate a shareable social media caption for Slide 7.

    Returns:
        Caption string, max 240 chars, ends with #BundesligaWrapped.
    """
    if dry_run:
        return (
            f"My {ctx.club.club_name} season: {ctx.hero_stat_value} {ctx.hero_stat_label}, "
            f"Fan DNA {ctx.fan_dna_score}/100. "
            f"What a ride. #BundesligaWrapped"
        )[:240]

    prompt = f"""<context>
Bundesliga Wrapped — Share caption for social media.

Club: {ctx.club.club_name}
Hero stat: {ctx.hero_stat_value} {ctx.hero_stat_label}
Fan DNA: {ctx.fan_dna_score}/100 ({ctx.fan_dna_archetype})
Top player: {ctx.favourite_player.name if ctx.favourite_player else 'N/A'}
Season: {ctx.club.wins}W {ctx.club.draws}D {ctx.club.losses}L
</context>

<instructions>
Write a social media caption this fan would share on Instagram/Twitter.

Tone: {_tone_instruction(ctx)}

Rules:
- Max 240 characters total (including hashtag)
- Must end with #BundesligaWrapped
- Include 1-2 specific stats that make the fan look good
- Should feel like something a real fan would post, not a brand
- No corporate language, no "check out my stats"
- Can include 1-2 emojis if tone is "fan"
</instructions>

<format>
Respond with ONLY the caption text, nothing else. No quotes, no JSON.
</format>"""

    raw = _call_bedrock(prompt, temperature=0.8, max_tokens=100)
    caption = raw.strip().strip('"')

    # Ensure hashtag is present and length is within bounds
    if "#BundesligaWrapped" not in caption:
        caption = caption[:220] + " #BundesligaWrapped"

    return caption[:240]


# ---------------------------------------------------------------------------
# Fan DNA slide (Slide 2)
# ---------------------------------------------------------------------------

def generate_fan_dna_slide(ctx: PersonalizationContext, dry_run: bool = False) -> dict:
    """Generate copy for Slide 2: Fan DNA Score.

    Returns:
        {"headline": str, "subtext": str, "archetype_description": str}
    """
    if dry_run:
        return {
            "headline": f"Fan DNA: {ctx.fan_dna_score}",
            "subtext": f"You're {ctx.fan_dna_archetype}",
            "archetype_description": f"{ctx.fan_generation} — {ctx.fan_generation_description}" if ctx.fan_generation else "Loyal, consistent, always there when it matters.",
        }

    prompt = f"""<context>
Bundesliga Wrapped — Fan DNA slide.

Fan DNA Score: {ctx.fan_dna_score}/100
Archetype: {ctx.fan_dna_archetype}
Breakdown: Loyalty {ctx.fan_dna_breakdown.get('loyalty', 0)}/100, Intensity {ctx.fan_dna_breakdown.get('intensity', 0)}/100, Breadth {ctx.fan_dna_breakdown.get('breadth', 0)}/100
Club: {ctx.club.club_name}
Active months: {ctx.user.active_months}/12
</context>

<instructions>
Write copy for the Fan DNA slide — this tells the fan what kind of supporter they are.

Tone: {_tone_instruction(ctx)}

Rules:
- headline: the archetype name styled boldly. Max 40 chars.
- subtext: one sentence explaining what this archetype means. Max 100 chars.
- archetype_description: one sentence about their strongest trait (loyalty/intensity/breadth). Max 120 chars.
- Make the fan feel proud of their type — every archetype is positive
- Do NOT rank archetypes or imply one is better than another
</instructions>

<format>
Respond with ONLY a JSON object:
{{"headline": "...", "subtext": "...", "archetype_description": "..."}}
</format>"""

    raw = _call_bedrock(prompt, temperature=0.7, max_tokens=200)
    result = _parse_json_response(raw)
    result["headline"] = result.get("headline", ctx.fan_dna_archetype)[:40]
    result["subtext"] = result.get("subtext", "")[:100]
    result["archetype_description"] = result.get("archetype_description", "")[:120]
    return result


# ---------------------------------------------------------------------------
# Match of the Season slide (Slide 4)
# ---------------------------------------------------------------------------

def generate_match_slide(ctx: PersonalizationContext, dry_run: bool = False) -> dict:
    """Generate copy for Slide 4: Match of the Season.

    Returns:
        {"headline": str, "subtext": str, "match_description": str}
    """
    match = ctx.best_match
    if not match:
        return {"headline": "Your Match", "subtext": "Every matchday was special", "match_description": ""}

    if dry_run:
        return {
            "headline": f"Matchday {match.matchday}",
            "subtext": f"{match.home_team_name} {match.result} {match.away_team_name}",
            "match_description": ctx.best_match_reason,
        }

    is_home = match.home_team_id == ctx.club.club_id
    opponent = match.away_team_name if is_home else match.home_team_name

    prompt = f"""<context>
Bundesliga Wrapped — Match of the Season slide.

Club: {ctx.club.club_name}
Match: Matchday {match.matchday}
Result: {match.home_team_name} {match.result} {match.away_team_name}
Venue: {match.stadium_name} ({match.spectators:,} spectators)
Sold out: {match.sold_out}
Opponent: {opponent}
Context: {ctx.best_match_reason}
</context>

<instructions>
Write copy for the "Match of the Season" slide.

Tone: {_tone_instruction(ctx)}

Rules:
- headline: the matchday + result in a dramatic framing. Max 50 chars.
- subtext: one sentence about why this match mattered. Max 120 chars.
- match_description: one vivid sentence painting the atmosphere. Max 100 chars.
- Make the fan relive the emotion of that day
- Do NOT just restate the score — tell the story behind it
</instructions>

<format>
Respond with ONLY a JSON object:
{{"headline": "...", "subtext": "...", "match_description": "..."}}
</format>"""

    raw = _call_bedrock(prompt, temperature=0.7, max_tokens=200)
    result = _parse_json_response(raw)
    result["headline"] = result.get("headline", f"Matchday {match.matchday}")[:50]
    result["subtext"] = result.get("subtext", "")[:120]
    result["match_description"] = result.get("match_description", "")[:100]
    return result


# ---------------------------------------------------------------------------
# Personal Angle slide (Slide 6)
# ---------------------------------------------------------------------------

def generate_personal_angle_slide(ctx: PersonalizationContext, dry_run: bool = False) -> dict:
    """Generate copy for Slide 6: Personal Angle.

    Returns:
        {"headline": str, "subtext": str}
    """
    if dry_run:
        return {
            "headline": "Only You",
            "subtext": ctx.personal_angle_stat,
        }

    prompt = f"""<context>
Bundesliga Wrapped — Personal Angle slide (the "surprise" moment).

Personal stat: {ctx.personal_angle_stat}
Club: {ctx.club.club_name}
Fan DNA: {ctx.fan_dna_score}/100 ({ctx.fan_dna_archetype})
</context>

<instructions>
Write copy for the personal angle slide — this is the "did you know?" moment
that surprises the fan with something about their own behaviour.

Tone: {_tone_instruction(ctx)}

Rules:
- headline: 2-4 words that tease the reveal. Max 40 chars.
- subtext: reframe the personal stat in a way that makes the fan feel special. Max 120 chars.
- This should feel like the "top 0.1%" moment from Spotify Wrapped
- Make it feel earned, not just a number
</instructions>

<format>
Respond with ONLY a JSON object:
{{"headline": "...", "subtext": "..."}}
</format>"""

    raw = _call_bedrock(prompt, temperature=0.7, max_tokens=150)
    result = _parse_json_response(raw)
    result["headline"] = result.get("headline", "Only You")[:40]
    result["subtext"] = result.get("subtext", ctx.personal_angle_stat)[:120]
    return result


# ---------------------------------------------------------------------------
# Goal of the Season slide
# ---------------------------------------------------------------------------

def generate_goal_of_season_slide(
    ctx: PersonalizationContext,
    goal_info: dict,
    dry_run: bool = False,
) -> dict:
    """Generate copy for the Goal of the Season slide.

    Args:
        ctx: PersonalizationContext.
        goal_info: Dict from select_goal_of_season() with scorer_name, description, matchday.
        dry_run: If True, return templated copy.

    Returns:
        {"slide_type": "goal_of_season", "headline": str, "subtext": str, "scorer": str}
    """
    scorer = goal_info.get("scorer_name", "")
    description = goal_info.get("description", "")
    matchday = goal_info.get("matchday", 0)

    if dry_run or not scorer:
        return {
            "slide_type": "goal_of_season",
            "headline": "Goal of the Season",
            "subtext": description or f"The best strike from your club's campaign",
            "scorer": scorer,
        }

    prompt = f"""<context>
Bundesliga Wrapped — Goal of the Season slide.

Club: {ctx.club.club_name}
Scorer: {scorer}
Matchday: {matchday}
Description: {description}
Is user's favourite player: {scorer in [ctx.favourite_player.name] if ctx.favourite_player else False}
</context>

<instructions>
Write copy for the "Goal of the Season" slide — celebrating the best goal.

Tone: {_tone_instruction(ctx)}

Rules:
- headline: 3-5 words that capture the moment. Max 50 chars.
- subtext: one sentence about why this goal was special. Max 120 chars.
- Make the fan feel like they were there when it happened
- Reference the scorer by name
- Do NOT use "impressive" or "remarkable"
</instructions>

<format>
Respond with ONLY a JSON object:
{{"headline": "...", "subtext": "..."}}
</format>"""

    raw = _call_bedrock(prompt, temperature=0.7, max_tokens=150)
    result = _parse_json_response(raw)
    result["headline"] = result.get("headline", "Goal of the Season")[:50]
    result["subtext"] = result.get("subtext", description)[:120]
    result["slide_type"] = "goal_of_season"
    result["scorer"] = scorer
    return result


# ---------------------------------------------------------------------------
# Main orchestrator: generate_all_slides
# ---------------------------------------------------------------------------

def generate_all_slides(ctx: PersonalizationContext, dry_run: bool = False) -> list[dict]:
    """Generate narrative copy for all 7 Wrapped slides.

    Calls each slide generator in sequence and assembles the results into
    an ordered list. If any individual Bedrock call fails (after retries),
    falls back to templated strings so the pipeline never crashes.

    Args:
        ctx: Fully populated PersonalizationContext.
        dry_run: If True, return mock data without calling Bedrock.

    Returns:
        List of 7 slide dicts, each with slide_type + generated copy fields.
    """
    slides: list[dict] = []

    # ── Slide 1: Hero / Identity card ─────────────────────────────────────────
    try:
        hero = generate_hero_slide(ctx, dry_run=dry_run)
    except Exception as exc:
        logger.error("Hero slide generation failed: %s. Using fallback.", exc)
        hero = generate_hero_slide(ctx, dry_run=True)
    slides.append({"slide_type": "hero", "slide_number": 1, **hero})

    # ── Slide 2: Fan DNA Score ────────────────────────────────────────────────
    try:
        dna = generate_fan_dna_slide(ctx, dry_run=dry_run)
    except Exception as exc:
        logger.error("Fan DNA slide generation failed: %s. Using fallback.", exc)
        dna = generate_fan_dna_slide(ctx, dry_run=True)
    slides.append({"slide_type": "fan_dna", "slide_number": 2, **dna})

    # ── Slide 3: Player Bond ──────────────────────────────────────────────────
    try:
        player = generate_top_player_slide(ctx, dry_run=dry_run)
    except Exception as exc:
        logger.error("Player slide generation failed: %s. Using fallback.", exc)
        player = generate_top_player_slide(ctx, dry_run=True)
    slides.append({"slide_type": "player_bond", "slide_number": 3, **player})

    # ── Slide 4: Goal of the Season ───────────────────────────────────────────
    # This slide is injected with goal_info from the assembler; in standalone
    # narrative generation we use a placeholder. The assembler will replace it.
    slides.append({
        "slide_type": "goal_of_season",
        "slide_number": 4,
        "headline": "Goal of the Season",
        "subtext": "The strike that defined your club's campaign",
        "scorer": "",
    })

    # ── Slide 5: Match of the Season ──────────────────────────────────────────
    try:
        match = generate_match_slide(ctx, dry_run=dry_run)
    except Exception as exc:
        logger.error("Match slide generation failed: %s. Using fallback.", exc)
        match = generate_match_slide(ctx, dry_run=True)
    slides.append({"slide_type": "match_of_season", "slide_number": 5, **match})

    # ── Slide 6: Season Arc Narrative ─────────────────────────────────────────
    try:
        journey = generate_season_journey_slide(ctx, dry_run=dry_run)
    except Exception as exc:
        logger.error("Season journey slide generation failed: %s. Using fallback.", exc)
        journey = generate_season_journey_slide(ctx, dry_run=True)
    slides.append({"slide_type": "season_arc", "slide_number": 6, **journey})

    # ── Slide 7: Personal Angle ───────────────────────────────────────────────
    try:
        personal = generate_personal_angle_slide(ctx, dry_run=dry_run)
    except Exception as exc:
        logger.error("Personal angle slide generation failed: %s. Using fallback.", exc)
        personal = generate_personal_angle_slide(ctx, dry_run=True)
    slides.append({"slide_type": "personal_angle", "slide_number": 7, **personal})

    # ── Slide 8: Share slide ──────────────────────────────────────────────────
    try:
        caption = generate_share_caption(ctx, dry_run=dry_run)
    except Exception as exc:
        logger.error("Share caption generation failed: %s. Using fallback.", exc)
        caption = generate_share_caption(ctx, dry_run=True)
    slides.append({
        "slide_type": "share",
        "slide_number": 8,
        "caption": caption,
        "headline": "Share Your Wrapped",
        "subtext": caption,
    })

    logger.info(
        "Generated %d slides (dry_run=%s, tone=%s). Total tokens: %d in / %d out.",
        len(slides), dry_run, ctx.tone, _total_input_tokens, _total_output_tokens,
    )

    return slides


def get_token_usage() -> dict[str, int]:
    """Return cumulative token usage for cost tracking.

    Returns:
        Dict with "input_tokens" and "output_tokens" keys.
    """
    return {"input_tokens": _total_input_tokens, "output_tokens": _total_output_tokens}


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    """Demo: generate all slides for a fictional Bayern user in dry-run mode."""
    import json as _json

    logging.basicConfig(level=logging.INFO)

    from backend.data.schema import ClubStats, MatchRecord, PlayerStats, UserProfile
    from backend.pipeline.personalization import build_context

    # Build a realistic mock context
    mock_user = UserProfile(
        user_id="demo-user-001",
        favorite_club="FC Bayern München",
        favorite_club_id="DFL-CLU-00000G",
        total_app_opens=220,
        total_match_center_views=180,
        total_article_views=45,
        total_story_views=20,
        total_video_views=60,
        active_months=11,
        stats_focus_ratio=0.45,
        ticker_focus_ratio=0.30,
        lineups_focus_ratio=0.15,
        favorite_player_ids=["DFL-OBJ-J00ZZ3"],
        app_opens_per_week=4.7,
    )

    mock_club = ClubStats(
        club_id="DFL-CLU-00000G",
        club_name="FC Bayern München",
        primary_color_hex="#DC052D",
        secondary_color_hex="#0066B2",
        matches_played=34,
        wins=23, draws=5, losses=6,
        goals_scored=87, goals_conceded=38,
        points=74,
        top_scorer_id="DFL-OBJ-J00ZZ3",
        top_scorer_name="Harry Kane",
        top_scorer_goals=26,
        best_win_matchday=9,
        best_win_result="8:0",
        best_win_opponent="VfL Bochum 1848",
        worst_loss_matchday=5,
        worst_loss_result="1:4",
        worst_loss_opponent="Eintracht Frankfurt",
    )

    mock_players = [
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

    mock_matches = {
        "DFL-MAT-DEMO01": MatchRecord(
            match_id="DFL-MAT-DEMO01", matchday=10,
            home_team_id="DFL-CLU-00000G", home_team_name="FC Bayern München",
            away_team_id="DFL-CLU-000007", away_team_name="Borussia Dortmund",
            result="4:2", home_goals=4, away_goals=2, total_goals=6,
            stadium_name="Allianz Arena", spectators=75000, sold_out=True,
        ),
        "DFL-MAT-DEMO02": MatchRecord(
            match_id="DFL-MAT-DEMO02", matchday=29,
            home_team_id="DFL-CLU-00000G", home_team_name="FC Bayern München",
            away_team_id="DFL-CLU-000017", away_team_name="RB Leipzig",
            result="3:2", home_goals=3, away_goals=2, total_goals=5,
            stadium_name="Allianz Arena", spectators=75000, sold_out=True,
        ),
    }

    # Build context
    ctx = build_context(mock_user, mock_club, mock_players, mock_matches, tone="fan")

    # Generate slides in dry-run mode (no Bedrock calls)
    slides = generate_all_slides(ctx, dry_run=True)

    print("\n" + "=" * 60)
    print("  NARRATIVE GENERATOR — Dry Run Output")
    print("  Tone: " + ctx.tone)
    print("=" * 60)

    for slide in slides:
        print(f"\n  [Slide {slide['slide_number']}] {slide['slide_type'].upper()}")
        for key, val in slide.items():
            if key not in ("slide_type", "slide_number"):
                print(f"    {key}: {val}")

    print("\n" + "=" * 60)
    print(f"  Token usage: {get_token_usage()}")
    print("=" * 60 + "\n")
