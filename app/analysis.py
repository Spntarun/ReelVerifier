import os
import json
import re
import time
import logging
from datetime import datetime, timezone
from typing import List, Optional, Literal, Dict, Any, Tuple
from pydantic import BaseModel, Field, field_validator, ConfigDict

logger = logging.getLogger(__name__)

# Try importing official google-genai SDK
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None


# --- Pydantic Schemas ---

class ClaimExtraction(BaseModel):
    """Structured extraction of promotional claim details from social media media."""
    model_config = ConfigDict(extra="ignore")

    category: str = Field(
        default="other",
        description="One of: job, internship, scholarship, free_course, giveaway, coupon, ai_tool, product_offer, other",
    )
    brand_or_company: str = Field(default="")
    offer: str = Field(default="")
    role_or_item: str = Field(default="")
    location: str = Field(default="")
    eligibility: str = Field(default="")
    deadline: str = Field(default="")
    creator_handle: str = Field(default="")
    call_to_action: str = Field(default="")
    link_shown: str = Field(default="")
    urgency_or_pressure_phrases: List[str] = Field(default_factory=list)
    unclear: List[str] = Field(default_factory=list)

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, v):
        if not v or not isinstance(v, str):
            return "other"
        allowed = {
            "job", "internship", "scholarship", "free_course",
            "giveaway", "coupon", "ai_tool", "product_offer", "other"
        }
        clean = v.strip().lower().replace(" ", "_").replace("-", "_")
        return clean if clean in allowed else "other"

    @field_validator("urgency_or_pressure_phrases", "unclear", mode="before")
    @classmethod
    def ensure_string_list(cls, v):
        if isinstance(v, list):
            return [str(x) for x in v if x is not None]
        if isinstance(v, str) and v.strip():
            return [v.strip()]
        return []


class OfficialLink(BaseModel):
    """Verified official website or announcement link."""
    model_config = ConfigDict(extra="ignore")

    title: str = Field(default="")
    url: str = Field(default="")

    @field_validator("url")
    @classmethod
    def validate_http_url(cls, v):
        clean = str(v).strip()
        if clean.startswith("http://") or clean.startswith("https://"):
            return clean
        return ""


class VerificationResult(BaseModel):
    """Final AI verification verdict and detailed breakdown."""
    model_config = ConfigDict(extra="ignore")

    verdict: str = Field(
        default="unverified",
        description="One of: verified, partial, unverified, suspicious",
    )
    confidence: int = Field(
        default=0,
        ge=0,
        le=100,
        description="Confidence score from 0 to 100 representing strength of available evidence.",
    )
    summary: str = Field(default="")
    official_links: List[OfficialLink] = Field(default_factory=list)
    red_flags: List[str] = Field(default_factory=list)
    advice: str = Field(default="")

    @field_validator("verdict", mode="before")
    @classmethod
    def normalize_verdict(cls, v):
        if not v or not isinstance(v, str):
            return "unverified"
        clean = v.strip().lower()
        if any(w in clean for w in ("suspicious", "scam", "warning", "fraud", "fake", "deceptive")):
            return "suspicious"
        if any(w in clean for w in ("partial", "mixed", "misleading", "exaggerated", "expired")):
            return "partial"
        if any(w in clean for w in ("verified", "genuine", "legitimate", "authentic", "confirmed")):
            return "verified"
        return "unverified"

    @field_validator("confidence", mode="before")
    @classmethod
    def coerce_confidence(cls, v):
        if isinstance(v, (int, float)):
            return max(0, min(100, int(v)))
        if isinstance(v, str):
            clean = v.strip().lower()
            if "high" in clean:
                return 85
            if "medium" in clean:
                return 60
            if "low" in clean:
                return 25
            digits = re.sub(r"[^\d]", "", clean)
            if digits:
                try:
                    return max(0, min(100, int(digits)))
                except Exception:
                    pass
        return 50

    @field_validator("red_flags", mode="before")
    @classmethod
    def ensure_red_flags_list(cls, v):
        if isinstance(v, list):
            return [str(x) for x in v if x is not None]
        if isinstance(v, str) and v.strip():
            return [v.strip()]
        return []

    @field_validator("official_links", mode="before")
    @classmethod
    def filter_links(cls, v):
        if not isinstance(v, list):
            return []
        cleaned = []
        for item in v:
            if isinstance(item, dict):
                url = str(item.get("url", "")).strip()
                if url.startswith("http://") or url.startswith("https://"):
                    cleaned.append(item)
            elif isinstance(item, OfficialLink):
                if item.url:
                    cleaned.append(item)
        return cleaned


# --- Helper JSON extraction ---

def extract_json_block(text: str) -> str:
    """Extract JSON string from potential markdown code fences or conversational text."""
    if not text:
        return ""

    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return text[first_brace:last_brace + 1].strip()

    return text.strip()


def safe_parse_json(text: str) -> dict:
    """
    Safely parse JSON from LLM output. Resilient to markdown fences,
    extraneous trailing text, or secondary JSON objects (avoiding Extra data errors).
    """
    if not text:
        return {}

    # Check for markdown code fences
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    candidate_text = match.group(1).strip() if match else text.strip()

    try:
        return json.loads(candidate_text)
    except Exception:
        pass

    # Use raw_decode to parse first complete JSON object if extra text exists
    first_brace = text.find("{")
    if first_brace != -1:
        try:
            decoder = json.JSONDecoder()
            obj, _ = decoder.raw_decode(text[first_brace:])
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

    # Fallback to candidate text raw_decode
    first_cand = candidate_text.find("{")
    if first_cand != -1:
        try:
            decoder = json.JSONDecoder()
            obj, _ = decoder.raw_decode(candidate_text[first_cand:])
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

    # If all fail, let standard json.loads raise descriptive error
    return json.loads(candidate_text)


# --- Analysis Pipeline ---

class ReelAnalysisPipeline:
    """
    Two-stage AI verification pipeline:
    Stage B: Gemini Claim Extraction (synthesizing visual observations, frames, transcript, caption)
    Stage C: Gemini Web Verification with Google Search grounding
    """

    def __init__(self, config):
        self.config = config
        if hasattr(config, "get"):
            self.api_key = config.get("GEMINI_API_KEY", "")
            self.model_name = config.get("GEMINI_MODEL", "gemini-2.5-flash")
        else:
            self.api_key = getattr(config, "GEMINI_API_KEY", "")
            self.model_name = getattr(config, "GEMINI_MODEL", "gemini-2.5-flash")
        self._client = None

    def get_client(self):
        """Initialize and return the google-genai Client with robust connection options."""
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY is not configured. Please set GEMINI_API_KEY in your environment or .env file."
            )
        if genai is None:
            raise RuntimeError(
                "The 'google-genai' SDK is not installed. Please install it using: pip install google-genai"
            )
        if self._client is None:
            http_options = None
            try:
                import httpx
                if types and hasattr(types, "HttpOptions"):
                    # Use HTTP/1.1 on Windows to prevent TCP RST / WinError 10053 during long grounding searches
                    http_options = types.HttpOptions(
                        timeout=120000,
                        httpx_client=httpx.Client(http2=False, timeout=120.0),
                    )
            except Exception as e:
                logger.debug(f"HttpOptions initialization: {e}")

            if http_options:
                self._client = genai.Client(api_key=self.api_key, http_options=http_options)
            else:
                self._client = genai.Client(api_key=self.api_key)
        return self._client

    def _generate_with_retry(self, client, model, contents, config=None, max_retries=3):
        """Execute generate_content with automatic retry and backoff on transient errors."""
        last_err = None
        for attempt in range(max_retries):
            try:
                return client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )
            except Exception as e:
                last_err = e
                err_str = str(e).lower()
                is_transient = any(
                    token in err_str
                    for token in (
                        "503",
                        "unavailable",
                        "resource_exhausted",
                        "429",
                        "10053",
                        "connection",
                        "aborted",
                        "timeout",
                        "readerror",
                    )
                )
                if is_transient and attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    logger.warning(f"Gemini API transient rate/network error. Retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                else:
                    raise
        raise last_err

    def extract_claim(
        self,
        visual_observations: Optional[str],
        frames_bytes: List[Tuple[bytes, str]],
        transcript: str,
        caption: str,
    ) -> ClaimExtraction:
        """
        Stage B: Combine multimodal evidence into a validated ClaimExtraction JSON.
        """
        client = self.get_client()

        # Build context prompt
        prompt_parts = [
            "You are an objective claim extraction AI for social media reels.",
            "Analyze the provided reel evidence (visual observations, image frames, audio transcript, and user caption).",
            "Your job is to extract the promotional offer and claims made in the reel into a clean JSON structure.",
            "\nRules:",
            "- Return ONLY a valid JSON object matching the requested schema.",
            "- Do NOT fabricate, assume, or invent details. If a piece of information is missing, return an empty string or empty list.",
            "- Allowed categories: job, internship, scholarship, free_course, giveaway, coupon, ai_tool, product_offer, other.",
            "\nExpected JSON schema:",
            json.dumps({
                "category": "job | internship | scholarship | free_course | giveaway | coupon | ai_tool | product_offer | other",
                "brand_or_company": "Company or platform name",
                "offer": "Core offer or claim (e.g. Free certification, $500 gift card, hiring freshers)",
                "role_or_item": "Specific role or product",
                "location": "Location or Remote if specified",
                "eligibility": "Eligibility requirements or prerequisites",
                "deadline": "Deadline or expiration date if mentioned",
                "creator_handle": "Creator or channel handle if visible",
                "call_to_action": "e.g. comment LINK, check bio, click link",
                "link_shown": "Any URL shown or mentioned",
                "urgency_or_pressure_phrases": ["list of urgency phrases like 'only 2 hours left', 'limited seats'"],
                "unclear": ["list of elements that were ambiguous or unstated"]
            }, indent=2),
            "\n--- REEL EVIDENCE ---",
        ]

        if caption:
            prompt_parts.append(f"USER CAPTION:\n{caption.strip()}")
        if transcript:
            prompt_parts.append(f"AUDIO TRANSCRIPT:\n{transcript.strip()}")
        if visual_observations:
            prompt_parts.append(f"VISUAL OBSERVATIONS FROM VISION MODEL:\n{visual_observations.strip()}")

        # Content list passed to Gemini
        contents: List[Any] = ["\n\n".join(prompt_parts)]

        # If local vision model was disabled or did not provide observations, attach image frames directly
        if not visual_observations and frames_bytes:
            # Attach up to 4 key frames directly as multimodal parts
            for img_bytes, mime_type in frames_bytes[:4]:
                if types:
                    part = types.Part.from_bytes(data=img_bytes, mime_type=mime_type)
                    contents.append(part)

        try:
            config = None
            if types:
                config = types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                )

            response = self._generate_with_retry(
                client=client,
                model=self.model_name,
                contents=contents,
                config=config,
            )

            raw_text = response.text or ""
            data = safe_parse_json(raw_text)
            return ClaimExtraction.model_validate(data)

        except Exception as e:
            logger.error(f"Stage B claim extraction failed: {e}")
            raise RuntimeError(f"Claim extraction failed: {e}")

    def verify_claim(self, claim: ClaimExtraction) -> VerificationResult:
        """
        Stage C: Verify the extracted claim using Gemini with Google Search Grounding.
        """
        client = self.get_client()
        today_date = datetime.now(timezone.utc).strftime("%B %d, %Y")

        system_instruction = (
            "You are a rigorous, objective fact-checking AI verifying promotional claims from social media reels "
            "(jobs, scholarships, free courses, giveaways, tech tools, coupons). "
            f"Today's date is: {today_date}. Use this date when checking deadlines and expirations.\n\n"
            "CRITICAL VERIFICATION PRINCIPLES:\n"
            "1. Search specifically for the offer and the company mentioned.\n"
            "2. Prioritize official company websites, official career portals (.com, verified portals), government domains (.gov, .edu), "
            "official course platforms (Coursera, edX, LinkedIn Learning), and verified press releases.\n"
            "3. Compare the reel's claim against what is officially announced. Verify eligibility, deadlines, prerequisites, and payment demands.\n"
            "4. Identify expired listings, outdated promotions, mismatched URLs (e.g. claiming to be Google but using a bit.ly or unofficial domain), "
            "and false urgency (e.g. artificial countdowns or fake limited seats).\n"
            "5. TONE & ETHICS:\n"
            "   - Never judge the creator's character or call anyone a scammer or fraudster.\n"
            "   - Focus solely on the evidence for the specific offer.\n"
            "   - Never invent or hallucinate official links. ONLY include real links discovered during search grounding.\n"
            "   - Use 'unverified' when public evidence is insufficient. Distinguish lack of evidence from active deception.\n"
            "   - Treat expired offers as partly matched or unverified.\n"
            "   - Do not claim an offer is genuine based solely on a high-production video or brand logo.\n"
            "6. Allowed verdicts:\n"
            "   - verified: Offer is confirmed on official company/platform channels with matching terms.\n"
            "   - partial: Offer exists but key details in the reel are misleading, exaggerated, or expired.\n"
            "   - unverified: Insufficient public evidence found on official sources to confirm or deny.\n"
            "   - suspicious: Strong warning signs found (mismatched domains, unverified payment request, non-existent program).\n"
            "7. Confidence must be an integer from 0 to 100 representing the strength of available evidence.\n"
            "8. Return ONLY a valid JSON object matching the specified structure."
        )

        user_prompt = f"""Verify the following extracted promotional claim:

{json.dumps(claim.model_dump(), indent=2)}

Return ONLY a valid JSON object with this exact structure:
{{
  "verdict": "verified | partial | unverified | suspicious",
  "confidence": 85,
  "summary": "Clear, objective plain-language explanation of what was verified or what could not be found.",
  "official_links": [
    {{
      "title": "Official Portal Name",
      "url": "https://official-domain.com/path"
    }}
  ],
  "red_flags": [
    "Specific warning sign 1 (e.g. domain mismatch, expired deadline, fee requested)"
  ],
  "advice": "Actionable, safe guidance for the user (e.g. 'Apply directly on careers.google.com; never pay an application fee')."
}}"""

        try:
            # Configure Search Grounding
            # In google-genai SDK, Search grounding is enabled with types.Tool(google_search=types.GoogleSearch())
            # or tools=[{"google_search": {}}]
            tools = []
            if types:
                tools = [types.Tool(google_search=types.GoogleSearch())]
            else:
                tools = [{"google_search": {}}]

            config = None
            if types:
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=tools,
                    temperature=0.1,
                )

            # Generate content
            response = self._generate_with_retry(
                client=client,
                model=self.model_name,
                contents=user_prompt,
                config=config,
            )

            raw_text = response.text or ""

            # Check for continuation / truncated response
            if hasattr(response, "candidates") and response.candidates:
                candidate = response.candidates[0]
                finish_reason = getattr(candidate, "finish_reason", None)
                if finish_reason and "MAX_TOKENS" in str(finish_reason):
                    logger.warning("Verification response was truncated due to MAX_TOKENS. Continuing turn...")
                    # Continue the turn to retrieve the remaining JSON
                    continuation_prompt = "Continue immediately from where you stopped. Return only the rest of the JSON."
                    cont_response = self._generate_with_retry(
                        client=client,
                        model=self.model_name,
                        contents=[user_prompt, raw_text, continuation_prompt],
                        config=config,
                    )
                    if cont_response.text:
                        raw_text += cont_response.text

            data = safe_parse_json(raw_text)

            # Extract any grounding metadata links if present and merge with official_links
            grounding_links = []
            try:
                if hasattr(response, "candidates") and response.candidates:
                    metadata = getattr(response.candidates[0], "grounding_metadata", None)
                    if metadata:
                        chunks = getattr(metadata, "grounding_chunks", []) or []
                        for chunk in chunks:
                            web = getattr(chunk, "web", None)
                            if web:
                                uri = getattr(web, "uri", "")
                                title = getattr(web, "title", "") or uri
                                if uri.startswith("http://") or uri.startswith("https://"):
                                    grounding_links.append({"title": title, "url": uri})
            except Exception as e:
                logger.debug(f"Grounding metadata inspection note: {e}")

            # Merge grounding links into official_links if official_links is empty
            if not data.get("official_links") and grounding_links:
                data["official_links"] = grounding_links[:5]

            result = VerificationResult.model_validate(data)
            return result

        except Exception as e:
            logger.error(f"Stage C web verification failed: {e}")
            # If quota or API failure, raise or return a friendly fallback
            error_msg = str(e)
            if "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg:
                raise RuntimeError("Gemini API quota exceeded. Please check your quota or try again in a few minutes.")
            elif "API_KEY_INVALID" in error_msg or "403" in error_msg:
                raise RuntimeError("Invalid Gemini API key. Please check GEMINI_API_KEY in server configuration.")
            else:
                return VerificationResult(
                    verdict="unverified",
                    confidence=0,
                    summary=f"Automated verification could not be completed due to a temporary service issue: {error_msg[:120]}.",
                    official_links=[],
                    red_flags=["Verification service encountered an unexpected error."],
                    advice="Please verify this offer directly on the official company website before taking action.",
                )
