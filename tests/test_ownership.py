import json
from app.models import db, Check


def test_user_can_view_own_result(auth_client, test_user, app):
    """User can view their own check report."""
    with app.app_context():
        check = Check(
            user_id=test_user.id,
            input_hash="hash_user1",
            claim_json=json.dumps({"brand_or_company": "OpenAI", "offer": "Grant"}),
            verdict_json=json.dumps({
                "verdict": "verified",
                "confidence": 92,
                "summary": "Confirmed on official openai.com blog",
                "official_links": [{"title": "OpenAI Grants", "url": "https://openai.com/grants"}],
                "red_flags": [],
                "advice": "Apply directly on official site."
            }),
            verdict="verified",
            confidence=92,
        )
        db.session.add(check)
        db.session.commit()
        check_id = check.id

    response = auth_client.get(f"/result/{check_id}")
    assert response.status_code == 200
    assert b"OpenAI" in response.data
    assert b"Confirmed on official openai.com blog" in response.data
    assert b"https://openai.com/grants" in response.data


def test_user_cannot_view_other_user_result(auth_client_2, test_user, app):
    """User 2 must be denied access (HTTP 403) when attempting to view User 1's report."""
    with app.app_context():
        check = Check(
            user_id=test_user.id,
            input_hash="hash_user1_private",
            claim_json=json.dumps({"brand_or_company": "PrivateCorp"}),
            verdict_json=json.dumps({"verdict": "verified", "confidence": 80}),
            verdict="verified",
            confidence=80,
        )
        db.session.add(check)
        db.session.commit()
        check_id = check.id

    # User 2 attempts to view User 1's check
    response = auth_client_2.get(f"/result/{check_id}")
    assert response.status_code == 403


def test_history_shows_only_current_user_checks(auth_client, auth_client_2, test_user, test_user_2, app):
    """User history must only display checks belonging to the current user."""
    with app.app_context():
        check_u1 = Check(
            user_id=test_user.id,
            input_hash="hash_u1",
            claim_json=json.dumps({"brand_or_company": "Apple", "category": "job"}),
            verdict_json=json.dumps({"verdict": "verified", "confidence": 90}),
            verdict="verified",
            confidence=90,
        )
        check_u2 = Check(
            user_id=test_user_2.id,
            input_hash="hash_u2",
            claim_json=json.dumps({"brand_or_company": "Amazon", "category": "internship"}),
            verdict_json=json.dumps({"verdict": "suspicious", "confidence": 15}),
            verdict="suspicious",
            confidence=15,
        )
        db.session.add_all([check_u1, check_u2])
        db.session.commit()

    # User 1 history
    res1 = auth_client.get("/history")
    assert res1.status_code == 200
    assert b"Apple" in res1.data
    assert b"Amazon" not in res1.data

    # User 2 history
    res2 = auth_client_2.get("/history")
    assert res2.status_code == 200
    assert b"Amazon" in res2.data
    assert b"Apple" not in res2.data

