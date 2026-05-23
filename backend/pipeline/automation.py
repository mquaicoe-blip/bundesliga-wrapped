"""
automation.py
=============
Batch automation layer for Bundesliga Wrapped.

Runs the complete pipeline for one or multiple clubs/users in batch mode,
with validation, progress tracking, and graceful error handling per-user.

This is the script that proves the system is reusable for ANY club with
zero manual reconfiguration — the challenge brief's explicit requirement.

Usage:
    python -m backend.pipeline.automation --clubs DFL-CLU-00000G,DFL-CLU-000007 \
        --users user_001,user_002 --dry-run

    python -m backend.pipeline.automation --validate-only
"""

from __future__ import annotations

import argparse
import logging
import time
from typing import Optional

from backend.config.aws_config import CHALLENGE_PREFIX, _get_bucket_name
from backend.data.data_loader import CLUB_ID_TO_NAME

logger = logging.getLogger(__name__)

# All 18 Bundesliga club IDs
ALL_CLUB_IDS = list(CLUB_ID_TO_NAME.keys())


# ---------------------------------------------------------------------------
# 1. Validation
# ---------------------------------------------------------------------------

def validate_club_data(club_id: str) -> dict:
    """Check that S3 has the expected data files for a club before running.

    Verifies:
      - Player roster XML exists for this club
      - At least one match file exists (shared across all clubs)
      - The main JSON engagement dataset exists

    Does NOT require club-specific images or videos — those are optional
    enrichments handled gracefully by resolve_media().

    Args:
        club_id: DFL-CLU-* identifier.

    Returns:
        Dict with keys:
          valid (bool): True if minimum required data is present.
          missing (list[str]): Files that are required but not found.
          warnings (list[str]): Non-critical issues (e.g. no video assets).
    """
    from backend.data.s3_loader import list_challenge_files

    missing: list[str] = []
    warnings: list[str] = []

    club_name = CLUB_ID_TO_NAME.get(club_id, "Unknown")
    logger.info("Validating data for %s (%s)...", club_id, club_name)

    # Check player roster XML
    roster_filename = f"01.05.{club_id}_DFL-SEA-0001K8.xml"
    roster_prefix = f"data/feeds-exports-24-25/players/{roster_filename}"
    roster_keys = list_challenge_files(roster_prefix)
    if not roster_keys:
        missing.append(f"Player roster: {roster_filename}")

    # Check match files exist (at least 1 — they're shared across clubs)
    match_keys = list_challenge_files("data/feeds-exports-24-25/matches/")
    if len(match_keys) < 10:
        missing.append(f"Match files: found {len(match_keys)}, expected 306")

    # Check engagement JSON exists
    json_keys = [k for k in list_challenge_files("data/") if k.endswith(".json")]
    if not json_keys:
        missing.append("Engagement dataset: bundesliga_wrapped_challenge_dataset.json")

    # Check for Bayern-specific season stats (only required for Bayern)
    if club_id == "DFL-CLU-00000G":
        bayern_keys = list_challenge_files("data/1K8_Bayern.xml")
        if not bayern_keys:
            warnings.append("Bayern season stats (1K8_Bayern.xml) not found — will use roster only")

    # Check for video assets (optional — warn if missing)
    video_keys = [k for k in list_challenge_files("data/260210") if k.endswith(".mp4")]
    if not video_keys:
        warnings.append("No video assets found — slides will render without media")

    valid = len(missing) == 0

    logger.info(
        "Validation %s for %s: %d missing, %d warnings",
        "PASSED" if valid else "FAILED", club_id, len(missing), len(warnings),
    )

    return {"valid": valid, "missing": missing, "warnings": warnings}


# ---------------------------------------------------------------------------
# 2. Batch runner
# ---------------------------------------------------------------------------

def run_batch(
    club_ids: list[str],
    user_ids: list[str],
    tone: str = "commentator",
    dry_run: bool = False,
    output_dir: str = "output",
) -> dict:
    """Run the Wrapped pipeline for each (club_id, user_id) combination.

    Handles failures per-user without aborting the whole batch. Each user's
    Wrapped is independent — one failure doesn't affect others.

    Progress is logged with a simple counter (tqdm used if available).

    Args:
        club_ids: List of DFL-CLU-* identifiers.
        user_ids: List of user hash strings.
        tone: Narrative tone for all generated Wraps.
        dry_run: If True, skip Bedrock calls.
        output_dir: Root output directory.

    Returns:
        Summary dict: {"success": int, "failed": int, "errors": list[dict],
                       "total_time_s": float}
    """
    from backend.pipeline.slide_assembler import run_pipeline

    # Try to use tqdm for progress bars; fall back to simple logging
    try:
        from tqdm import tqdm
        has_tqdm = True
    except ImportError:
        has_tqdm = False

    total_jobs = len(club_ids) * len(user_ids)
    success = 0
    failed = 0
    errors: list[dict] = []

    logger.info(
        "Starting batch: %d clubs × %d users = %d jobs (dry_run=%s)",
        len(club_ids), len(user_ids), total_jobs, dry_run,
    )

    start_time = time.time()

    # Build the job list
    jobs = [(cid, uid) for cid in club_ids for uid in user_ids]

    iterator = tqdm(jobs, desc="Generating Wraps") if has_tqdm else jobs

    for club_id, user_id in iterator:
        try:
            run_pipeline(
                club_id=club_id,
                user_id=user_id,
                tone=tone,
                dry_run=dry_run,
                output_dir=output_dir,
            )
            success += 1
        except Exception as exc:
            failed += 1
            error_entry = {
                "club_id": club_id,
                "user_id": user_id[:16] + "...",
                "error": str(exc),
            }
            errors.append(error_entry)
            logger.error(
                "Failed for club=%s user=%s: %s",
                club_id, user_id[:12], exc,
            )

        # Log progress if no tqdm
        if not has_tqdm and (success + failed) % 10 == 0:
            logger.info("Progress: %d/%d complete", success + failed, total_jobs)

    elapsed = time.time() - start_time

    summary = {
        "success": success,
        "failed": failed,
        "total": total_jobs,
        "errors": errors,
        "total_time_s": round(elapsed, 2),
    }

    logger.info(
        "Batch complete: %d/%d succeeded, %d failed in %.1fs",
        success, total_jobs, failed, elapsed,
    )

    return summary


# ---------------------------------------------------------------------------
# 3. CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Bundesliga Wrapped — Batch automation runner"
    )
    parser.add_argument(
        "--clubs",
        default="DFL-CLU-00000G",
        help="Comma-separated DFL-CLU-* IDs (default: Bayern). Use 'all' for all 18 clubs.",
    )
    parser.add_argument(
        "--users",
        default="demo-user-001,demo-user-002,demo-user-003",
        help="Comma-separated user IDs",
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
        help="Skip Bedrock calls, use mock narratives",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate data availability, don't run pipeline",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Output directory (default: output/)",
    )
    args = parser.parse_args()

    # Parse club IDs
    if args.clubs.lower() == "all":
        club_ids = ALL_CLUB_IDS
    else:
        club_ids = [c.strip() for c in args.clubs.split(",")]

    # Parse user IDs
    user_ids = [u.strip() for u in args.users.split(",")]

    # ── Validate-only mode ────────────────────────────────────────────────────
    if args.validate_only:
        print("\n" + "=" * 60)
        print("  DATA VALIDATION — Checking S3 for all requested clubs")
        print("=" * 60)

        all_valid = True
        for club_id in club_ids:
            result = validate_club_data(club_id)
            club_name = CLUB_ID_TO_NAME.get(club_id, "Unknown")
            status = "✓ PASS" if result["valid"] else "✗ FAIL"
            print(f"\n  {status}  {club_name} ({club_id})")
            for m in result["missing"]:
                print(f"         MISSING: {m}")
            for w in result["warnings"]:
                print(f"         WARNING: {w}")
            if not result["valid"]:
                all_valid = False

        print("\n" + "=" * 60)
        print(f"  {'ALL CLUBS VALID' if all_valid else 'SOME CLUBS HAVE MISSING DATA'}")
        print("=" * 60 + "\n")
        exit(0 if all_valid else 1)

    # ── Batch run mode ────────────────────────────────────────────────────────
    summary = run_batch(
        club_ids=club_ids,
        user_ids=user_ids,
        tone=args.tone,
        dry_run=args.dry_run,
        output_dir=args.output_dir,
    )

    print("\n" + "=" * 60)
    print("  BATCH SUMMARY")
    print("=" * 60)
    print(f"  Total jobs:  {summary['total']}")
    print(f"  Succeeded:   {summary['success']}")
    print(f"  Failed:      {summary['failed']}")
    print(f"  Time:        {summary['total_time_s']}s")

    if summary["errors"]:
        print("\n  Errors:")
        for err in summary["errors"]:
            print(f"    • {err['club_id']} / {err['user_id']}: {err['error']}")

    print("=" * 60 + "\n")
    exit(0 if summary["failed"] == 0 else 1)
