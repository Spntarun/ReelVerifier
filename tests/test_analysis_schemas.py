import json
from app.analysis import ClaimExtraction, VerificationResult, OfficialLink, extract_json_block


def test_claim_extraction_normalization():
    """Test category normalization and default field fallbacks."""
    raw_data = {
        "category": "FREE COURSE",
        "brand_or_company": "Harvard",
        "offer": "CS50 Free Certificate",
        "urgency_or_pressure_phrases": "Limited spots available",
        "unclear": None,
    }
    claim = ClaimExtraction.model_validate(raw_data)
    assert claim.category == "free_course"
    assert claim.brand_or_company == "Harvard"
    assert claim.urgency_or_pressure_phrases == ["Limited spots available"]
    assert claim.unclear == []

    # Invalid category defaults to 'other'
    claim_unknown = ClaimExtraction.model_validate({"category": "unknown_nonsense"})
    assert claim_unknown.category == "other"


def test_verification_result_validation():
    """Test confidence bounds and HTTP link filtering."""
    raw_data = {
        "verdict": "verified",
        "confidence": 150,  # exceeds 100, should be coerced to 100
        "summary": "Verified via official site.",
        "official_links": [
            {"title": "Valid Link", "url": "https://example.com/careers"},
            {"title": "Insecure XSS Attempt", "url": "javascript:alert(1)"},
            {"title": "Valid HTTP", "url": "http://sub.example.com"},
        ],
        "red_flags": "Payment requested upfront",
    }
    result = VerificationResult.model_validate(raw_data)
    assert result.confidence == 100
    assert result.verdict == "verified"
    assert len(result.official_links) == 2
    assert result.official_links[0].url == "https://example.com/careers"
    assert result.official_links[1].url == "http://sub.example.com"
    assert result.red_flags == ["Payment requested upfront"]


def test_extract_json_block_helper():
    """Test extracting JSON from diverse LLM output shapes."""
    # Plain JSON
    plain = '{"verdict": "verified", "confidence": 90}'
    assert json.loads(extract_json_block(plain))["verdict"] == "verified"

    # Markdown fenced json
    fenced = 'Here is the output:\n```json\n{"verdict": "suspicious", "confidence": 20}\n```\nHope this helps!'
    assert json.loads(extract_json_block(fenced))["verdict"] == "suspicious"

    # Unlabeled code fence
    unlabeled = '```\n{"category": "scholarship"}\n```'
    assert json.loads(extract_json_block(unlabeled))["category"] == "scholarship"

