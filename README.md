# Bundesliga Wrapped

A personalized season summary for Bundesliga fans — think Spotify Wrapped, but for football. Built for the AWS World Sports Innovation Cup 2026 (Challenge 1).

You give it a club and a user. It gives back an 8-slide story experience telling that fan what their season meant — their stats, their player, their moments, their way.

## What it does

The pipeline takes raw DFL match data (306 XML files), player rosters (18 clubs), and anonymized app engagement data (26,242 records across 2,765 users) and turns it into a personalized Wrapped for any fan of any club. No hardcoding. Change the `club_id` parameter and you get a completely different experience — different colors, different players, different narrative.

Each Wrapped has 8 slides:

1. **Hero card** — one big number that defines your season
2. **Fan DNA** — a 0-100 score with a personality archetype (8 types)
3. **Player bond** — your player of the season with an AI-written sentence about them
4. **Goal of the season** — with the actual video clip if available
5. **Match of the season** — the most dramatic match you followed
6. **Season arc** — month-by-month timeline of your engagement
7. **Personal angle** — a surprising stat about your own behaviour
8. **Share card** — pre-written caption ready for Instagram/WhatsApp/X

The fan picks a narrative tone before starting: Commentator (dramatic), Analyst (data-forward), or Fan (casual/Gen Z). One parameter change shifts the entire voice across all 8 slides.

## How it works

```
S3 data (XMLs, JSON, video clips)
    → Python scoring engine (Fan DNA, drama ranking, player importance)
        → Amazon Bedrock (Claude Sonnet — generates narrative copy per slide)
            → JSON output (consumed by React Native frontend)
```

The scoring engine figures out what matters most to each user — which player they followed, which matches were dramatic, how consistent their engagement was. Then Bedrock writes the copy in the chosen tone. The frontend renders it as swipeable story slides with animations.

## Running it

### Prerequisites

- Python 3.11+
- AWS credentials with access to the hackathon S3 bucket
- Node.js 20-22 (for the React Native app — optional for demo)

### Quick start

```bash
git clone https://github.com/mquaicoe-blip/bundesliga-wrapped.git
cd bundesliga-wrapped

# Set up Python
python -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows
pip install -r backend/requirements.txt

# Copy .env and fill in your bucket name
cp .env.example .env

# Run the pipeline (dry-run, no AWS calls needed)
python -m backend.pipeline.slide_assembler --dry-run --tone fan

# Run for a different club
python -m backend.pipeline.slide_assembler --dry-run --club-id DFL-CLU-000007 --tone commentator

# Run tests
python -m pytest backend/tests/ -v
```

### Running with real data from S3

You need valid AWS credentials. Get them from the SSO portal, set them as environment variables, then drop the `--dry-run` flag. The pipeline will fetch data from S3 and (if Bedrock model access is enabled) generate real AI narratives.

### React Native app

```bash
cd frontend/BundesligaWrapped
npm install
npx expo start --web
```

Requires Node 20-22 (Node 24 is incompatible with Expo 52). The app fetches `wrapped.json` from whatever URL you set in `EXPO_PUBLIC_API_URL`.

## The automation proof

This is what the challenge brief specifically asks for — "input data for a second club, get equally relevant output without manual reconfiguration."

We tested all 18 Bundesliga clubs. Same code, different `club_id`:

- Bayern → red (#DC052D), title-race narrative, Kane goal clip
- Dortmund → yellow (#FDE100), solid narrative, different players
- Freiburg → black (#000000), different stats, different moments
- ...all 18 work

58 automated tests verify this.

## Project structure

```
backend/
  config/aws_config.py          — AWS session factory
  data/schema.py                — all dataclasses (single source of truth)
  data/data_loader.py           — S3 → typed objects with caching
  data/s3_loader.py             — low-level S3 operations
  pipeline/personalization.py   — scoring engine (Fan DNA, drama, player ranking)
  pipeline/narrative_generator.py — Bedrock prompts + response parsing
  pipeline/slide_assembler.py   — final assembly + full pipeline orchestrator
  pipeline/automation.py        — batch runner + validation
  tests/                        — 58 tests across 4 files

frontend/BundesligaWrapped/     — React Native (Expo) swipeable story UI
notebooks/                      — data exploration + demo notebook
docs/                           — strategy, business plan, executive summary
```

## Key decisions

- **Why dataclasses, not Pydantic?** Zero dependencies. `dataclasses.asdict()` gives free JSON serialization. Reviewers can read it without knowing a library.
- **Why dry_run on everything?** Bedrock costs money. Every function that calls Bedrock has a `dry_run=True` path that returns templated output. Development costs $0.
- **Why 8 archetypes?** Spotify's personality features are their most-shared element. More specific = more viral. "The Stats Geek" is more shareable than "Engaged Fan."
- **Why tone as a single parameter?** No separate code paths. One field on PersonalizationContext gets injected into every Bedrock prompt. Change it once, entire narrative shifts.

## Cost

~$0.12 per user Wrapped at scale (Bedrock tokens + S3 + Lambda). At 1M users that's $120K/year for a full AI personalization layer — a rounding error compared to the engagement value.

## What's in docs/

- `strategy.md` — competitive research (what Spotify/YouTube/NBA/Strava do)
- `business_plan.md` — delivery frequency, engagement strategy, monetization, KPIs
- `executive_summary.md` — 5-slide pitch deck content
- `advanced_features_plan.md` — roadmap features inspired by 2025 platform recaps

---

Built for the AWS World Sports Innovation Cup 2026. Challenge 1: Build Bundesliga Wrapped.
