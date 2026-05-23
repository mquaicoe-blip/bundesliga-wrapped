# Submission Checklist — AWS World Sports Innovation Cup 2026

## Required deliverables

- [ ] `github_link.txt` — contains the URL to this repository
- [ ] All source code committed (no hackathon data files — .gitignore handles this)
- [ ] `README.md` complete with setup instructions and architecture overview
- [ ] `backend/tests/` — all 33 tests pass (`py -m pytest backend/ -v`)
- [ ] `presentation_video.mp4` — max 3 minutes, ≤720p, demonstrates the product
- [ ] `executive_summary.pdf` — max 5 slides covering problem/solution/architecture/business
- [ ] `MyTeamName.zip` created containing all 4 items above
- [ ] Repository visibility set to public (or MoellerO invited if private)

## Pre-submission verification

- [ ] `py -m backend.pipeline.automation --clubs all --validate-only` passes
- [ ] `py -m backend.pipeline.automation --clubs DFL-CLU-00000G --users demo-001 --dry-run` produces output
- [ ] `output/DFL-CLU-00000G/demo-001/wrapped.json` exists and is valid JSON
- [ ] No AWS credentials or secrets in committed files
- [ ] `.env` is in `.gitignore` (not committed)
- [ ] `docs/business_plan.md` is complete
- [ ] `docs/strategy.md` contains the Section 0 research output

## Demo notebook verification

- [ ] `notebooks/02_demo.ipynb` runs top-to-bottom without errors (dry_run mode)
- [ ] Shows all 7 slides with formatted output
- [ ] Demonstrates multi-club reusability (Bayern + Dortmund)
- [ ] Share caption is under 240 characters

## Video recording notes

- Show the demo notebook running (cells 1–6)
- Highlight the tone selector (run with different tones)
- Show the React Native UI mockup or screenshots
- Mention: "Same pipeline, any club, zero reconfiguration"
- Close with business value: cost per user, engagement projections
