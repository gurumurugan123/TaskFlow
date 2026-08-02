"""Idempotency helpers: prevent duplicate jobs for the same client action."""

import hashlib
import json

from redis_client import redis_client

IDEMPOTENCY_TTL_SECONDS = 24 * 60 * 60  # 24 hours


class IdempotencyConflict(Exception):
    """Same key was already used with a different request body."""


def _payload_hash(payload: dict) -> str:
    """Stable hash so we can compare two requests with the same key."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _idempotency_redis_key(idempotency_key: str) -> str:
    return f"idempotency:{idempotency_key}"


def lookup_idempotent_job(idempotency_key: str, payload: dict) -> tuple[str | None, bool]:
    """
    Check if this idempotency key was used before.

    Returns:
        (job_id, is_replay)
        - (None, False)  → key not seen before, create a new job
        - (job_id, True) → same key + same body, return existing job

    Raises:
        IdempotencyConflict → same key but different body (409)
    """
    redis_key = _idempotency_redis_key(idempotency_key)
    stored = redis_client.hgetall(redis_key)

    if not stored:
        return None, False

    stored_hash = stored.get("payload_hash", "")
    if stored_hash != _payload_hash(payload):
        raise IdempotencyConflict(
            f"Idempotency key '{idempotency_key}' was already used with different data."
        )

    return stored["job_id"], True


def save_idempotency_record(idempotency_key: str, job_id: str, payload: dict) -> None:
    """Remember key → job_id + body hash for future duplicate requests."""
    redis_key = _idempotency_redis_key(idempotency_key)
    redis_client.hset(
        redis_key,
        mapping={
            "job_id": job_id,
            "payload_hash": _payload_hash(payload),
        },
    )
    redis_client.expire(redis_key, IDEMPOTENCY_TTL_SECONDS)
