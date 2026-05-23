# Bundesliga Wrapped ⚽🏆

> *"From 500 million global fans to 500 million individual stories."*

**AWS World Sports Innovation Cup 2026 — Challenge 1: Build Bundesliga Wrapped**

---

## Overview

Bundesliga Wrapped is a Spotify Wrapped–style personalized season summary for the official Bundesliga app. It transforms raw match data, player statistics, and individual app engagement into a 7-slide swipeable story experience that makes every fan feel seen — their club, their player, their season, their way.

Powered by Amazon Bedrock (Claude Sonnet) for AI narrative generation and built on the DFL's existing AWS data infrastructure, the system automatically generates unique Wraps for any of the 18 Bundesliga clubs with zero manual reconfiguration. One `club_id` parameter change produces an entirely different, club-themed experience. The tone selector lets fans choose how their story is told: Commentator, Analyst, or Fan voice.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    BUNDESLIGA WRAPPED                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────┐    ┌──────────────┐    ┌───────────────────┐     │
│  │  AWS S3  │───▶│  Data Loader │───▶│  Personalization  │     │
│  │  (Data)  │    │  (boto3/XML) │    │  Engine (Scoring) │     │
│  └──────────┘    └──────────────┘    └────────┬──────────┘     │
│                                               │                 │
│                                               ▼                 │
│  ┌──────────┐    ┌──────────────┐    ┌───────────────────┐     │
│  │  React   │◀───│   Slide      │◀───│  Amazon Bedrock   │     │
│  │  Native  │    │  Assembler   │    │  (Claude Sonnet)  │     │
│  │  (Expo)  │    │  (JSON out)  │    │  Narrative Gen    │     │
│  └──────────┘    └──────────────┘    └───────────────────┘     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

Layer 1: Data         → S3 bucket (match XMLs, player rosters, user JSON, videos)
Layer 2: Processing   → Python pipeline (boto3, pandas, XML parsing)
Layer 3: Scoring      → PersonalizationContext assembly (Fan DNA, drama scoring)
Layer 4: AI Narrative → Amazon Bedrock (tone-aware narrative generation)
Layer 5: Delivery     → React Native (Expo) swipeable story UI
```

---

## Slide Sequence

| # | Slide | Animation | Description |
|---|-------|-----------|-------------|
| 1 | Hero / Identity Card | fade | Your season in one hero stat |
| 2 | Fan DNA Score | counter | Your fandom profile (0–100) with archetype |
| 3 | Player Bond | slide_up | Your player of the season + AI narrative |
| 4 | Match of the Season | slide_up | AI-selected drama peak + highlight clip |
| 5 | Season Arc | counter | Your club's season told through your eyes |
| 6 | Personal Angle | pulse | Your most surprising fan behaviour stat |
| 7 | Share | fade | Branded card with social caption + share button |

---

## Prerequisites

- Python 3.11+ (`py --version`)
- AWS CLI v2 with valid credentials
- Node.js 20+ and npm (for frontend)
- Expo CLI (`npm install -g expo-cli`)

---

## Setup

### 1. AWS credentials

Get fresh credentials from the SSO portal and set them:

```bash
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_SESSION_TOKEN="..."
```

Or paste them into a `.env` file (copy from `.env.example`).

### 2. Python environment

```bash
cd bundesliga-wrapped
py -m venv venv
venv\Scripts\activate          # Windows
pip install -r backend/requirements.txt
```

### 3. Environment variables

```bash
cp .env.example .env
# Edit .env: set HACKATHON_BUCKET=hackathon-data-<your-account-id>
```

### 4. Copy S3 data (if not already done)

```bash
export CHALLENGE="Challenge 1 – Build Bundesliga Wrapped"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws s3 mb s3://hackathon-data-$ACCOUNT_ID --region eu-central-1
aws s3 cp "s3://aws-world-sports-innovation-cup-data/$CHALLENGE/" \
          "s3://hackathon-data-$ACCOUNT_ID/$CHALLENGE/" --recursive
```

### 5. Explore the data

```bash
jupyter lab notebooks/01_explore_data.ipynb
```

### 6. Run the pipeline

```bash
# Dry-run (no Bedrock calls, uses templated narratives):
py -m backend.pipeline.slide_assembler --dry-run --tone fan

# Full run (requires Bedrock access):
py -m backend.pipeline.slide_assembler --club-id DFL-CLU-00000G --user-id <hash>

# Batch run for multiple users:
py -m backend.pipeline.automation --clubs DFL-CLU-00000G --users user1,user2 --dry-run
```

### 7. Start the React Native app

```bash
cd frontend/BundesligaWrapped
npm install
npx expo start
```

Serve the backend output locally:
```bash
py -m http.server 8000 --directory output
```

---

## Adding a New Club

No code changes needed. Just ensure the S3 bucket has:
1. Player roster XML: `data/feeds-exports-24-25/players/01.05.<ClubId>_DFL-SEA-0001K8.xml`
2. Match XMLs (shared): `data/feeds-exports-24-25/matches/*.xml`
3. User engagement JSON (shared): `data/bundesliga_wrapped_challenge_dataset.json`

Then run:
```bash
py -m backend.pipeline.slide_assembler --club-id <NEW_CLUB_ID> --user-id <USER> --dry-run
```

The pipeline auto-resolves club colors, player data, and match history.

---

## Running Tests

```bash
# All tests (33 total):
py -m pytest backend/tests/ backend/pipeline/test_personalization.py -v

# Integration tests only:
py -m pytest backend/tests/test_integration.py -v

# Personalization unit tests only:
py -m pytest backend/pipeline/test_personalization.py -v
```

---

## Project Structure

```
bundesliga-wrapped/
├── backend/
│   ├── config/
│   │   └── aws_config.py              # AWS session factory (SSO + env var fallback)
│   ├── data/
│   │   ├── schema.py                  # All dataclasses (PlayerStats, ClubStats, etc.)
│   │   ├── data_loader.py            # S3 → dataclass loaders with caching
│   │   └── s3_loader.py              # Low-level S3 operations
│   ├── pipeline/
│   │   ├── personalization.py        # Scoring engine (Fan DNA, drama, player importance)
│   │   ├── narrative_generator.py    # Amazon Bedrock narrative generation
│   │   ├── slide_assembler.py        # Final assembly + JSON export + orchestrator
│   │   ├── automation.py             # Batch runner + validation
│   │   └── test_personalization.py   # 25 unit tests
│   ├── tests/
│   │   └── test_integration.py       # 8 end-to-end integration tests
│   └── requirements.txt
├── frontend/BundesligaWrapped/
│   ├── App.tsx
│   └── src/
│       ├── types/wrapped.ts           # TS interfaces matching Python schema
│       ├── utils/{colors,animations}.ts
│       ├── hooks/{useWrappedData,useSlideTimer}.ts
│       ├── components/
│       │   ├── SlideContainer.tsx     # Full-screen swipeable wrapper
│       │   ├── AnimatedStat.tsx       # Counting animation
│       │   ├── ProgressBar.tsx        # Story-style progress dots
│       │   └── slides/{Hero,TopPlayer,SeasonJourney,Moment,Share}Slide.tsx
│       └── screens/{Loading,Wrapped}Screen.tsx
├── notebooks/
│   ├── 01_explore_data.ipynb          # Data exploration
│   └── 02_demo.ipynb                  # Presentation demo
├── docs/
│   ├── strategy.md                    # Research & strategy (Section 0)
│   └── business_plan.md              # Business plan (Section 7)
├── .env.example
├── .gitignore
├── Makefile
└── README.md
```

---

## AWS Services Used

| Service | Role |
|---------|------|
| Amazon S3 | Data lake — match XMLs, player data, video assets, output JSON |
| Amazon Bedrock (Claude Sonnet) | AI narrative generation in 3 tones |
| AWS Lambda (production) | Serverless pipeline execution |
| Amazon CloudFront (production) | Global CDN for wrapped.json + share cards |

---

## Narrative Tone System

The `tone` parameter shifts the entire narrative voice across all 7 slides:

| Tone | Style | Example |
|------|-------|---------|
| `commentator` | Dramatic, broadcast-style | "What a season it's been at the Allianz Arena!" |
| `analyst` | Data-forward, tactical | "26 goals from 22.54 xG — a +3.46 overperformance." |
| `fan` | Casual, Gen Z energy | "bro 220 times you opened the app?? that's dedication 🔥" |

---

## Team

AWS World Sports Innovation Cup 2026 — Challenge 1

---

## License

Hackathon submission — not for redistribution.
