import json
from unittest.mock import patch
from datetime import datetime, timezone
from app.models import db, Check, User
from app.media import compute_deterministic_hash


def test_cache_hit_returns_existing_check(auth_client, test_user, app):
    """Submitting identical files and caption should return the cached check."""
    # Pre-populate a check for test_user
    input_hash = compute_deterministic_hash([], "Free Google Certificate 2026")

    with app.app_context():
        existing_check = Check(
            user_id=test_user.id,
            input_hash=input_hash,
            claim_json=json.dumps({"brand_or_company": "Google", "offer": "Free Certificate"}),
            verdict_json=json.dumps({"verdict": "verified", "confidence": 95, "summary": "Confirmed on Google Blog"}),
            verdict="verified",
            confidence=95,
        )
        db.session.add(existing_check)
        db.session.commit()
        check_id = existing_check.id

    # Post identical caption
    response = auth_client.post("/api/analyze", data={"caption": "Free Google Certificate 2026"})
    assert response.status_code == 200
    data = response.get_json()

    assert data["success"] is True
    assert data["cached"] is True
    assert data["id"] == check_id
    assert data["verdict"] == "verified"
    assert data["confidence"] == 95


def test_daily_limit_enforcement(auth_client, test_user, app):
    """When user reaches DAILY_LIMIT_PER_USER, /api/analyze must return HTTP 429."""
    # TestConfig sets DAILY_LIMIT_PER_USER = 3
    now = datetime.now(timezone.utc)

    with app.app_context():
        for i in range(3):
            c = Check(
                user_id=test_user.id,
                input_hash=f"hash_{i}",
                claim_json="{}",
                verdict_json="{}",
                verdict="unverified",
                confidence=10,
                created_at=now,
            )
            db.session.add(c)
        db.session.commit()

    # Attempt a 4th new check
    response = auth_client.post("/api/analyze", data={"caption": "New brand offer check #4"})
    assert response.status_code == 429
    data = response.get_json()
    assert data["success"] is False
    assert data["limit_reached"] is True
    assert "daily limit" in data["error"].lower()


def test_cached_request_does_not_consume_daily_limit(auth_client, test_user, app):
    """Cached requests must still be served even if daily limit is reached."""
    now = datetime.now(timezone.utc)
    target_hash = compute_deterministic_hash([], "Cached Offer Topic")

    with app.app_context():
        # Insert 3 checks to hit the limit
        for i in range(2):
            c = Check(
                user_id=test_user.id,
                input_hash=f"some_hash_{i}",
                claim_json="{}",
                verdict_json="{}",
                verdict="unverified",
                confidence=10,
                created_at=now,
            )
            db.session.add(c)

        # 3rd check is our cached target
        cached_c = Check(
            user_id=test_user.id,
            input_hash=target_hash,
            claim_json=json.dumps({"brand_or_company": "Microsoft", "offer": "Scholarship"}),
            verdict_json=json.dumps({"verdict": "verified", "confidence": 90}),
            verdict="verified",
            confidence=90,
            created_at=now,
        )
        db.session.add(cached_c)
        db.session.commit()

    # Now total checks today = 3 (the limit).
    # Requesting the cached offer should succeed (not 429)!
    response = auth_client.post("/api/analyze", data={"caption": "Cached Offer Topic"})
    assert response.status_code == 200
    data = response.get_json()
    assert data["cached"] is True
    assert data["verdict"] == "verified"
