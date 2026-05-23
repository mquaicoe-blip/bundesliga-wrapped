"""
s3_loader.py
============
Utilities for listing and downloading hackathon data from S3.

All operations use the shared session/client from ``aws_config`` and log at
INFO level so progress is visible when running scripts or notebooks.

Usage:
    from backend.data.s3_loader import list_challenge_files, download_file

    keys = list_challenge_files()          # all files under the challenge prefix
    keys = list_challenge_files("data/feeds-exports-24-25/matches/")
    download_file(keys[0], "data/raw/match.xml")
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from backend.config.aws_config import (
    CHALLENGE_PREFIX,
    _get_bucket_name,
    get_s3_client,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _full_prefix(sub_prefix: str = "") -> str:
    """Combine the challenge root prefix with an optional sub-prefix.

    Args:
        sub_prefix: Path segment relative to the challenge root, e.g.
            ``"data/feeds-exports-24-25/matches/"``.

    Returns:
        Full S3 prefix string.
    """
    if sub_prefix:
        return f"{CHALLENGE_PREFIX}/{sub_prefix.lstrip('/')}"
    return CHALLENGE_PREFIX


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_challenge_files(prefix: str = "") -> list[str]:
    """List all S3 object keys under the challenge prefix.

    Uses paginated ``list_objects_v2`` so it handles buckets with more than
    1 000 objects correctly.

    Args:
        prefix: Optional sub-prefix relative to the challenge root.
            E.g. ``"data/feeds-exports-24-25/matches/"`` to list only match XMLs.
            Pass ``""`` (default) to list everything.

    Returns:
        Sorted list of S3 object key strings.
    """
    bucket = _get_bucket_name()
    full = _full_prefix(prefix)
    s3 = get_s3_client()

    logger.info("Listing S3 objects: s3://%s/%s", bucket, full)

    keys: list[str] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=full):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])

    logger.info("Found %d objects under prefix '%s'.", len(keys), full)
    return sorted(keys)


def download_file(s3_key: str, local_path: str | Path) -> None:
    """Download a single S3 object to a local path.

    Parent directories are created automatically.

    Args:
        s3_key: Full S3 object key (e.g. as returned by :func:`list_challenge_files`).
        local_path: Destination path on the local filesystem.
    """
    bucket = _get_bucket_name()
    dest = Path(local_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    s3 = get_s3_client()
    logger.info("Downloading s3://%s/%s → %s", bucket, s3_key, dest)
    s3.download_file(bucket, s3_key, str(dest))
    logger.info("Download complete: %s (%.1f KB)", dest, dest.stat().st_size / 1024)


def download_folder(prefix: str, local_dir: str | Path) -> None:
    """Download all S3 objects under a prefix into a local directory.

    The S3 key structure is preserved relative to the challenge root.
    For example, a key ``Challenge 1 – .../data/feeds/match.xml`` is saved to
    ``<local_dir>/data/feeds/match.xml``.

    Args:
        prefix: Sub-prefix relative to the challenge root (e.g.
            ``"data/feeds-exports-24-25/players/"``).
        local_dir: Root directory on the local filesystem to download into.
    """
    keys = list_challenge_files(prefix)
    if not keys:
        logger.warning("No objects found under prefix '%s'. Nothing downloaded.", prefix)
        return

    local_root = Path(local_dir)
    challenge_root = CHALLENGE_PREFIX + "/"

    logger.info(
        "Downloading %d objects from prefix '%s' into '%s'.",
        len(keys),
        prefix,
        local_root,
    )

    for key in keys:
        # Strip the challenge root so local paths are relative to local_dir
        relative = key.removeprefix(challenge_root)
        dest = local_root / relative
        download_file(key, dest)

    logger.info("Folder download complete: %d files saved to '%s'.", len(keys), local_root)


def get_presigned_url(s3_key: str, expiry: int = 3600) -> str:
    """Generate a pre-signed URL for temporary public access to an S3 object.

    Useful for embedding video/image assets in the React Native app during
    development without making the bucket public.

    Args:
        s3_key: Full S3 object key.
        expiry: URL validity in seconds. Defaults to 3600 (1 hour).

    Returns:
        Pre-signed HTTPS URL string.
    """
    bucket = _get_bucket_name()
    s3 = get_s3_client()

    url: str = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": s3_key},
        ExpiresIn=expiry,
    )
    logger.info(
        "Pre-signed URL generated for '%s' (expires in %ds).", s3_key, expiry
    )
    return url
