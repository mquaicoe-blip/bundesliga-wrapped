"""
aws_config.py
=============
Central AWS session and client factory for Bundesliga Wrapped.

Authentication strategy (in priority order):
  1. AWS SSO profile named "hackathon" (preferred for local dev)
  2. Explicit environment variables: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,
     AWS_SESSION_TOKEN (useful in CI or when SSO is unavailable)

Usage:
    from backend.config.aws_config import get_session, get_s3_client, get_bedrock_client

    session = get_session()
    s3      = get_s3_client()
    bedrock = get_bedrock_client()
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import boto3
from botocore.exceptions import ProfileNotFound, NoCredentialsError

# Load .env file if present (no-op if python-dotenv is not installed yet)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: AWS region for all services.
AWS_REGION: str = "eu-central-1"

#: Named AWS profile to try first.
#: Set to "hackathon" if you configure SSO via `aws configure sso --profile hackathon`.
#: Falls back to env vars (AWS_ACCESS_KEY_ID etc.) if the profile is not found.
SSO_PROFILE: str = os.environ.get("AWS_PROFILE", "default")

#: S3 prefix for Challenge 1 data inside the bucket.
CHALLENGE_PREFIX: str = "Challenge 1 \u2013 Build Bundesliga Wrapped"


def _get_bucket_name() -> str:
    """Read the S3 bucket name from the environment.

    Returns:
        The bucket name string.

    Raises:
        EnvironmentError: If HACKATHON_BUCKET is not set.
    """
    bucket = os.environ.get("HACKATHON_BUCKET")
    if not bucket:
        raise EnvironmentError(
            "HACKATHON_BUCKET environment variable is not set. "
            "Add it to your .env file or export it before running. "
            "Example: HACKATHON_BUCKET=hackathon-data-119997536330"
        )
    return bucket


@property  # type: ignore[misc]
def BUCKET_NAME() -> str:  # noqa: N802
    """Lazy property wrapper — evaluated on first access so the module can be
    imported even before the env var is set (e.g. during test collection)."""
    return _get_bucket_name()


# Eagerly expose as a plain string for convenience; callers that need the
# lazy version can call _get_bucket_name() directly.
try:
    BUCKET_NAME: str = _get_bucket_name()  # type: ignore[assignment]
except EnvironmentError:
    BUCKET_NAME = ""  # type: ignore[assignment]  # will raise at runtime if used

# Module-level session cache — avoids re-authenticating on every client call
_session_cache: Optional["boto3.Session"] = None


def get_session(profile: Optional[str] = SSO_PROFILE) -> boto3.Session:
    """Create and return a boto3 Session.

    Tries the SSO profile first; falls back to environment-variable credentials
    if the profile is not found or has no valid credentials.
    Result is cached at module level so repeated calls don't re-authenticate.

    Args:
        profile: Named AWS profile to use. Defaults to ``SSO_PROFILE``.

    Returns:
        An authenticated :class:`boto3.Session`.

    Raises:
        NoCredentialsError: If neither SSO profile nor environment variables
            provide valid credentials.
    """
    global _session_cache
    if _session_cache is not None:
        return _session_cache
    # --- Attempt 1: SSO profile ---
    try:
        session = boto3.Session(profile_name=profile, region_name=AWS_REGION)
        # Trigger a lightweight credentials check to surface SSO token issues early.
        creds = session.get_credentials()
        if creds is not None:
            creds.get_frozen_credentials()
        logger.info("AWS session created using SSO profile '%s'.", profile)
        return session
    except ProfileNotFound:
        logger.debug(
            "AWS profile '%s' not found — using environment variable credentials.",
            profile,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "AWS profile '%s' unavailable (%s) — using environment variable credentials.",
            profile,
            exc,
        )

    # --- Attempt 2: Environment variables ---
    access_key = os.environ.get("AWS_ACCESS_KEY_ID")
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
    session_token = os.environ.get("AWS_SESSION_TOKEN")

    if access_key and secret_key:
        session = boto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            aws_session_token=session_token,  # None is fine if not using temp creds
            region_name=AWS_REGION,
        )
        logger.info("AWS session created using environment variable credentials.")
        _session_cache = session
        return session

    # --- Attempt 3: default profile (covers refreshed STS/SSO tokens in ~/.aws/credentials) ---
    try:
        session = boto3.Session(profile_name="default", region_name=AWS_REGION)
        creds = session.get_credentials()
        if creds is not None:
            creds.get_frozen_credentials()
        logger.info("AWS session created using 'default' profile.")
        return session
    except Exception as exc:  # noqa: BLE001
        logger.debug("Default profile also unavailable (%s).", exc)

    raise NoCredentialsError()


def get_s3_client(session: Optional[boto3.Session] = None) -> "boto3.client":
    """Return a boto3 S3 client.

    Args:
        session: An existing :class:`boto3.Session`. If ``None``, a new session
            is created via :func:`get_session`.

    Returns:
        A boto3 S3 client configured for ``AWS_REGION``.
    """
    s3 = (session or get_session()).client("s3", region_name=AWS_REGION)
    logger.debug("S3 client created (region=%s).", AWS_REGION)
    return s3


def get_bedrock_client(session: Optional[boto3.Session] = None) -> "boto3.client":
    """Return a boto3 Bedrock Runtime client.

    The Bedrock Runtime endpoint is used for ``InvokeModel`` calls (i.e. sending
    prompts and receiving completions).

    Args:
        session: An existing :class:`boto3.Session`. If ``None``, a new session
            is created via :func:`get_session`.

    Returns:
        A boto3 ``bedrock-runtime`` client configured for ``AWS_REGION``.
    """
    bedrock = (session or get_session()).client(
        "bedrock-runtime", region_name=AWS_REGION
    )
    logger.debug("Bedrock Runtime client created (region=%s).", AWS_REGION)
    return bedrock
