import io
from PIL import Image
from unittest.mock import patch, MagicMock
from app.analysis import ClaimExtraction, VerificationResult, OfficialLink
from app.models import Check


def create_test_image_bytes(format="JPEG", size=(100, 100)):
    """Helper to create valid image bytes using Pillow."""
    img = Image.new("RGB", size, color="green")
    buf = io.BytesIO()
    img.save(buf, format=format)
    return buf.getvalue()


def test_api_analyze_empty_input_rejected(auth_client):
    """Submitting neither files nor caption must return 400."""
    res = auth_client.post("/api/analyze", data={})
    assert res.status_code == 400
    assert "Please provide at least one" in res.get_json()["error"]


def test_api_analyze_oversized_caption_rejected(auth_client):
    """Captions exceeding 2000 characters must return 400."""
    res = auth_client.post("/api/analyze", data={"caption": "A" * 2005})
    assert res.status_code == 400
    assert "too long" in res.get_json()["error"]


def test_api_analyze_unsupported_file_rejected(auth_client):
    """Uploading unsupported format (e.g. .exe or .txt) must return 400."""
    data = {
        "files": (io.BytesIO(b"MZ executable header"), "malicious.exe"),
        "caption": "Check this out",
    }
    res = auth_client.post("/api/analyze", data=data, content_type="multipart/form-data")
    assert res.status_code == 400
    assert "Unsupported file format" in res.get_json()["error"]


@patch("app.routes.ReelAnalysisPipeline")
def test_api_analyze_successful_flow(mock_pipeline_cls, auth_client, test_user, app):
    """Test full successful verification flow through /api/analyze."""
    # Setup mock pipeline
    mock_pipeline = MagicMock()
    mock_pipeline_cls.return_value = mock_pipeline

    mock_pipeline.extract_claim.return_value = ClaimExtraction(
        category="job",
        brand_or_company="Google",
        offer="Software Engineer Fresher 2026",
        role_or_item="Software Engineer",
        location="Remote",
        eligibility="B.Tech 2026 Batch",
        deadline="December 31, 2026",
    )

    mock_pipeline.verify_claim.return_value = VerificationResult(
        verdict="verified",
        confidence=95,
        summary="Confirmed on Google Careers portal.",
        official_links=[OfficialLink(title="Google Careers", url="https://careers.google.com/jobs/123")],
        red_flags=[],
        advice="Apply directly via careers.google.com without paying any fee.",
    )

    jpeg_bytes = create_test_image_bytes()
    data = {
        "files": (io.BytesIO(jpeg_bytes), "screenshot.jpg"),
        "caption": "Google is hiring freshers for 2026 batch!",
    }

    response = auth_client.post("/api/analyze", data=data, content_type="multipart/form-data")
    assert response.status_code == 200
    json_data = response.get_json()

    assert json_data["success"] is True
    assert json_data["cached"] is False
    assert json_data["verdict"] == "verified"
    assert json_data["confidence"] == 95
    assert json_data["verdict_label"] == "Verified"
    assert json_data["summary"] == "Confirmed on Google Careers portal."
    assert len(json_data["official_links"]) == 1
    assert json_data["official_links"][0]["url"] == "https://careers.google.com/jobs/123"

    # Verify record was stored in DB
    with app.app_context():
        stored = Check.query.filter_by(user_id=test_user.id).first()
        assert stored is not None
        assert stored.verdict == "verified"
        assert stored.confidence == 95
        assert stored.get_claim()["brand_or_company"] == "Google"
