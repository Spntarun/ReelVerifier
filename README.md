# Reel Verifier 🎬🔍

**Reel Verifier** is a production-ready, secure Flask web application designed to fact-check and verify claims made in Instagram reels, TikTok videos, screenshots, and promotional social media posts.

From deceptive job openings and expired scholarships to fake giveaways, suspicious coupon codes, and hype-driven AI tool promotions, Reel Verifier provides users with clear, evidence-backed verification reports powered by a dual-stage AI architecture combining open-source Vision Language Models (Qwen-VL) and Google Gemini with live Google Search grounding.

---

## Table of Contents

1. [Features](#features)
2. [AI Architecture](#ai-architecture)
3. [Prerequisites](#prerequisites)
4. [Google Cloud OAuth Setup](#google-cloud-oauth-setup)
5. [Gemini API Setup & Search Grounding](#gemini-api-setup--search-grounding)
6. [Local Vision Model Setup (Qwen-VL)](#local-vision-model-setup-qwen-vl)
7. [Local Installation](#local-installation)
8. [Configuration (.env)](#configuration-env)
9. [Production Deployment (Render / Railway)](#production-deployment-render--railway)
10. [Testing & Verification Scenarios](#testing--verification-scenarios)
11. [Three End-to-End Walkthrough Examples](#three-end-to-end-walkthrough-examples)
12. [Security Architecture](#security-architecture)

---

## Features

- **Google-Only Secure Authentication**: Seamless OpenID Connect (OIDC) login with domain restriction support and CSRF-protected sessions.
- **Multimodal Video & Screenshot Ingestion**: Accepts up to 4 media files (JPEG, PNG, WebP, GIF, MP4, MOV, WebM), enforcing MIME-type magic byte signatures and size constraints.
- **Automated Video Processing**: Uses FFprobe to inspect video duration (&le; 120s) and FFmpeg to extract up to 10 evenly spaced, 720px chronological frames.
- **Speech-to-Text Transcription**: Optional local audio transcription via `faster-whisper`.
- **Hybrid Vision & Grounded Verification**:
  - **Stage A**: Local open-source Hugging Face Vision Language Model (`Qwen/Qwen3-VL-8B-Instruct` or `Qwen/Qwen2.5-VL-7B-Instruct`) for visual text extraction, brand recognition, and chronological evidence gathering.
  - **Stage B**: Gemini Claim Extraction synthesizing visual observations, video frames, audio transcript, and user captions into validated Pydantic JSON.
  - **Stage C**: Gemini Web Verification grounded in real-time Google Search, cross-referencing claims against official company career portals, `.gov`/`.edu` domains, and verified announcements.
- **Deterministic Caching**: Instant SHA-256 cache hits for duplicate user submissions that do not consume daily verification quotas.
- **Fair Use Daily Quotas**: Configurable per-user daily limits (default: 10/day) with HTTP 429 rate-limiting.
- **Zero Media Retention**: Temporary media files are processed in isolated directories and deleted immediately in `finally` blocks.
- **Instagram-Inspired Minimalist Design System**: Designed according to [DESIGN.md](file:///t:/Intrella/Codes/Flask/ReelVerifier/DESIGN.md) (inspired by [VoltAgent/awesome-design-md](https://github.com/VoltAgent/awesome-design-md)), featuring:
  - Instagram story ring avatars and subtle gradient accents (`#f58529` to `#515bd4`).
  - Native "Create Post"-style drag-and-drop media upload with 9:16 reel preview carousel.
  - Story sticker-style verdict badges and community advisory alerts.
  - Full support for Light and AMOLED Dark modes (`prefers-color-scheme`).
  - Accessible contrast, visible focus states, and XSS-safe DOM rendering.

---

## AI Architecture

```text
 [Uploaded Reel/Screenshots] + [Caption]
                  │
     ┌────────────┴────────────┐
     ▼                         ▼
[FFmpeg Frames]        [faster-whisper]
 (Up to 10 frames)      (Audio Speech-to-Text)
     │                         │
     ▼                         │
[Stage A: Local Vision Model]   │
 (Qwen3-VL-8B-Instruct)        │
 (or Gemini Multimodal Fallback)│
     │                         │
     └────────────┬────────────┘
                  ▼
   [Stage B: Gemini Claim Extraction]
     (Standardized Claim JSON)
                  │
                  ▼
   [Stage C: Gemini Web Verification]
     (Live Google Search Grounding)
                  │
                  ▼
   [Final Verdict & Evidence Report]
```

### Allowed Verdicts & UI Mapping
| Internal Verdict | UI Label | Badge Color | Meaning |
| :--- | :--- | :--- | :--- |
| `verified` | **Verified** | Green | Offer confirmed on official company channels with matching terms. |
| `partial` | **Partly matched** | Amber | Offer exists, but key reel claims are misleading, exaggerated, or expired. |
| `unverified` | **Couldn't verify** | Grey | Insufficient public evidence on official sources to confirm or deny. |
| `suspicious` | **Warning signs** | Red | Mismatched domains, unverified payment demands, or deceptive elements found. |

---

## Prerequisites

- **Python 3.11+**
- **FFmpeg & FFprobe**: Required for video frame extraction and audio demuxing.
- **Google Account & Google Cloud Console Access**: For OAuth 2.0 Client credentials.
- **Google Gemini API Key**: From [Google AI Studio](https://aistudio.google.com/).
- **(Optional) NVIDIA GPU with CUDA & 16GB+ VRAM**: For running local `Qwen3-VL-8B-Instruct`.

> [!NOTE]
> Local vision inference is **entirely optional**. If a GPU is not available, set `ENABLE_LOCAL_VISION=false`. The application will automatically use Gemini's native multimodal capabilities to analyze images and extracted video frames directly.

---

## Simplified Email Authentication Setup

Reel Verifier features passwordless, instant email authentication:
- **Zero OAuth Configuration Required**: No need to create Google Cloud projects, manage OAuth consent screens, or generate Client IDs and Secrets.
- **Instant Access**: Users simply type their email on the landing page or `/login` to sign in. New user accounts are automatically created.
- **Domain Restrictions (Optional)**: If you want to restrict access to a specific organization or company email domain, configure `ALLOWED_EMAIL_DOMAINS` in `.env`:
  ```env
  ALLOWED_EMAIL_DOMAINS=company.com,university.edu
  ```
- **Protected Sessions**: Uses cryptographically signed Flask sessions with `HttpOnly`, `SameSite=Lax`, and `Secure` (in production). Every route except `/`, `/login`, and static assets is strictly protected by `@login_required`.

---

## Gemini API Setup & Search Grounding

1. Go to [Google AI Studio](https://aistudio.google.com/).
2. Click **Get API key** and create a new key.
3. Add the key to your `.env` file:
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   GEMINI_MODEL=gemini-2.5-flash
   ```
4. **Google Search Grounding**: Reel Verifier automatically activates Gemini's native Google Search grounding tool (`types.Tool(google_search=types.GoogleSearch())`). This performs live web searches across official career portals and news sites to retrieve actual source citations.

---

## Local Vision Model Setup (Qwen-VL)

Reel Verifier supports open-source Hugging Face Vision Language Models:
- **Default**: `Qwen/Qwen3-VL-8B-Instruct`
- **Alternative**: `Qwen/Qwen2.5-VL-7B-Instruct`

### Hardware Requirements
- **Standard (bfloat16)**: Requires an NVIDIA GPU with at least **16 GB to 24 GB VRAM**.
- **4-bit Quantization**: Requires an NVIDIA GPU with at least **8 GB to 10 GB VRAM**.
  Set `VISION_QUANTIZATION=4bit` in `.env`.
- **CPU Inference**: Not recommended due to latency (60+ seconds per batch).

### Disabling Local Vision for Lightweight Deployments
If you do not have an NVIDIA GPU, disable local vision in `.env`:
```env
ENABLE_LOCAL_VISION=false
```
When disabled, the app routes video frames directly into Gemini multimodal inputs, requiring zero local GPU resources.

---

## Local Installation

### 1. Clone the repository and enter the directory
```bash
git clone https://github.com/your-username/reel-verifier.git
cd reel-verifier
```

### 2. Create and activate a virtual environment
```bash
python -m venv venv
```
- **Windows (PowerShell)**:
  ```powershell
  .\venv\Scripts\Activate.ps1
  ```
- **macOS / Linux**:
  ```bash
  source venv/bin/activate
  ```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment variables
Copy the example configuration:
```bash
cp .env.example .env
```
Open `.env` in your editor and enter your `SECRET_KEY` and `GEMINI_API_KEY`.

### 5. Run database migrations and launch the app
```bash
python run.py
```
Or using the Flask CLI:
```bash
flask --app run.py run
```
Open your browser and navigate to:
```text
http://localhost:5000
```

---

## Configuration (.env)

| Variable | Default | Description |
| :--- | :--- | :--- |
| `SECRET_KEY` | *required* | Cryptographic secret for signing sessions and CSRF tokens. |
| `GEMINI_API_KEY` | *required* | Google Gemini API key. |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model ID used for claim extraction and web verification. |
| `VISION_MODEL` | `Qwen/Qwen3-VL-8B-Instruct` | Hugging Face model identifier for Stage A vision extraction. |
| `VISION_DEVICE` | `cuda` | Target compute device (`cuda` or `cpu`). |
| `ENABLE_LOCAL_VISION` | `true` | Set to `false` to disable local VLM and use Gemini vision instead. |
| `VISION_QUANTIZATION` | *(empty)* | Optional quantization (`4bit` or `8bit`). |
| `ENABLE_TRANSCRIPTION` | `true` | Set to `false` to disable `faster-whisper` audio transcription. |
| `DAILY_LIMIT_PER_USER` | `10` | Maximum new verifications allowed per user per UTC day. |
| `ALLOWED_EMAIL_DOMAINS` | *(empty)* | Comma-separated list to restrict logins (e.g. `company.com,university.edu`). |
| `DATABASE_URL` | `sqlite:///app.db` | SQLAlchemy database URL. |
| `FLASK_ENV` | `development` | Environment mode (`development` or `production`). |
| `FFMPEG_BINARY` | `ffmpeg` | Path to `ffmpeg` executable. |
| `FFPROBE_BINARY` | `ffprobe` | Path to `ffprobe` executable. |

---

## Production Deployment (Render / Railway)

### 1. Web Process Command
In your Procfile or platform settings:
```bash
gunicorn --bind 0.0.0.0:$PORT "app:create_app()" --workers 2 --timeout 120
```

### 2. Database Persistence
> [!WARNING]
> Render and Railway web containers utilize **ephemeral filesystems**. Any SQLite database stored inside the container will be deleted on redeploy. For production:
> - Provision a managed PostgreSQL instance and set `DATABASE_URL=postgresql://user:password@host/dbname`.
> - Alternatively, mount a persistent volume if using SQLite.

### 3. HTTPS & Cookies
In production, set:
```env
FLASK_ENV=production
```
This enables secure session cookies (`SESSION_COOKIE_SECURE = True`) requiring HTTPS. Ensure your Google OAuth Redirect URI matches your production domain: `https://your-domain.com/auth/callback`.

### 4. GPU Architecture for Cloud
Because open-source 8B vision models require GPU instances, standard low-cost web tiers (e.g., 512MB RAM) cannot host `Qwen3-VL-8B-Instruct`.
For standard cloud tiers:
- Set `ENABLE_LOCAL_VISION=false`.
- Let Gemini handle native multimodal vision.
- If local VLM is strictly required in production, deploy a dedicated GPU worker (e.g., RunPod, Modal, or AWS EC2 g5) exposing a microservice, or run on a dedicated GPU container.

---

## Testing & Verification Scenarios

Run the automated test suite:
```bash
python -m pytest
```

The test suite covers:
- **`tests/test_auth.py`**: Login redirection, unauthenticated API rejection (401), session logout, and open redirect prevention.
- **`tests/test_media.py`**: File magic byte sniffing (JPEG, PNG, GIF, WebP, MP4, WebM), corruption rejection, and deterministic SHA-256 caching.
- **`tests/test_caching_and_limits.py`**: Immediate cache hit retrieval, daily quota enforcement (429), and non-decrementing quota on cached submissions.
- **`tests/test_ownership.py`**: Cross-user report isolation (403 Forbidden) and user history filtering.
- **`tests/test_analysis_schemas.py`**: Pydantic schema validation, category normalization, and safe HTTP link filtering.
- **`tests/test_analysis_pipeline.py`**: End-to-end `/api/analyze` execution and validation.

### Ten Core Manual Verification Scenarios

1. **Legitimate Offer Verification**:
   - Upload a screenshot of an active Microsoft or Google student grant.
   - *Expected*: Verdict is **Verified**, evidence score &gt; 80%, links pointing to `microsoft.com` or `google.com`.
2. **Misleading or Expired Offer**:
   - Upload a reel advertising a scholarship with a deadline from last year.
   - *Expected*: Verdict is **Partly matched** or **Couldn't verify**, with an explicit warning sign highlighting the passed deadline.
3. **Video with Audio Transcription**:
   - Upload an MP4 reel where the creator speaks the details aloud without on-screen text.
   - *Expected*: `faster-whisper` transcribes the voiceover, which Gemini successfully parses into the structured claim.
4. **Unsupported or Fabricated Claim**:
   - Upload a claim that "NASA is giving free laptops to high schoolers".
   - *Expected*: Verdict is **Couldn't verify** (or **Warning signs** if deceptive forms are shown), confidence &lt; 20%, advice warns against sharing personal data.
5. **Google OAuth & Domain Restriction**:
   - Log in with Google. Log out and confirm session revocation. Test with `ALLOWED_EMAIL_DOMAINS` set to verify domain enforcement.
6. **File Size & Type Validation**:
   - Attempt to upload an `.exe` disguised as `.png`, or a 70MB video.
   - *Expected*: Instant client-side and server-side rejection with a friendly error message.
7. **Daily Quota Reached**:
   - Perform 10 distinct checks in one day.
   - *Expected*: The 11th request returns HTTP 429 stating that the daily limit has been reached and resets at 00:00 UTC.
8. **Deterministic Cache Reuse**:
   - Submit the same screenshot and caption twice.
   - *Expected*: The second check returns in &lt; 100ms with a "Cached Result" badge, without counting against your daily quota.
9. **Ownership & Access Control**:
   - Copy a `/result/<id>` URL from User A and paste it into User B's browser session.
   - *Expected*: Returns HTTP 403 Access Denied.
10. **Vision Fallback Resilience**:
    - Disconnect GPU or set `ENABLE_LOCAL_VISION=false`.
    - *Expected*: The pipeline smoothly proceeds with Gemini native multimodal vision with zero downtime.

---

## Three End-to-End Walkthrough Examples

### Example 1: Legitimate Tech Internship Reel
- **Input Media**: Screen recording of a reel showcasing "Google Summer of Code 2026 Stipend & Registration".
- **Caption**: "Applications are now open for GSoC 2026. Comment CODE for the registration link."
- **Visual Evidence Extracted**: Google Summer of Code logo, mentor organization list, deadline dates.
- **Stage B Claim**:
  ```json
  {
    "category": "internship",
    "brand_or_company": "Google",
    "offer": "Google Summer of Code (GSoC) 2026 Open Source Mentorship",
    "eligibility": "Open to post-secondary students and open source newcomers",
    "call_to_action": "Comment CODE for link"
  }
  ```
- **Stage C Verification**: Grounding searches `https://summerofcode.withgoogle.com/`. Matches program terms.
- **Final Result**:
  - **Verdict**: `Verified` (Green badge)
  - **Confidence**: 96%
  - **Summary**: "Google Summer of Code 2026 is an official Google open-source mentorship program confirmed on summerofcode.withgoogle.com."
  - **Official Links**: `https://summerofcode.withgoogle.com/`
  - **Advice**: "Apply directly through the official Google portal. Never pay third parties to apply."

---

### Example 2: Fake / Expired Government Scholarship
- **Input Media**: Screenshot of a reel claiming "$5,000 National STEM Scholarship for all college students - Apply before Friday!".
- **Caption**: "Guaranteed $5000 check from the government, link in bio!"
- **Visual Evidence Extracted**: Fake federal seal, unofficial Bitly link, high-pressure countdown timer.
- **Stage B Claim**:
  ```json
  {
    "category": "scholarship",
    "brand_or_company": "US Government / STEM Foundation",
    "offer": "$5,000 guaranteed student check",
    "urgency_or_pressure_phrases": ["apply before Friday", "guaranteed payment"]
  }
  ```
- **Stage C Verification**: Search finds no matching federal grant; government domains do not guarantee checks via Bitly links.
- **Final Result**:
  - **Verdict**: `Warning signs` (Red badge)
  - **Confidence**: 88%
  - **Summary**: "No legitimate government or accredited STEM foundation offers a guaranteed $5,000 check without an application review. The link in bio redirects to an unauthorized third-party survey site."
  - **Red Flags**:
    - "Mismatched domain: Uses an unverified URL shortener instead of a `.gov` or `.edu` website."
    - "Artificial urgency and guarantee: Federal grants do not guarantee awards without academic review."
  - **Advice**: "Do not enter personal identification, bank numbers, or SSN on external survey links. Look for verified aid on studentaid.gov."

---

### Example 3: Free Certification Course with Concealed Upsell
- **Input Media**: Reel showing "Harvard Free Python Certification with College Credits".
- **Caption**: "Harvard just made their Python degree 100% free with certificates for everyone!"
- **Stage B Claim**:
  ```json
  {
    "category": "free_course",
    "brand_or_company": "Harvard University / edX",
    "offer": "Free CS50 Python Certificate with College Credits",
    "role_or_item": "CS50 Introduction to Programming with Python"
  }
  ```
- **Stage C Verification**: Searches `edx.org` and `pll.harvard.edu`. Course material is free to audit, but certificates and college credits require payment.
- **Final Result**:
  - **Verdict**: `Partly matched` (Amber badge)
  - **Confidence**: 92%
  - **Summary**: "Harvard's CS50 course material is indeed free to audit on edX, but the claim that accredited certificates and college credits are 100% free is inaccurate. A verified certificate requires a paid fee."
  - **Official Links**: `https://pll.harvard.edu/course/cs50s-introduction-programming-with-python`
  - **Advice**: "You can audit the complete course materials for free directly on edX or CS50's portal. Only pay if you specifically require a verified certificate."

---

## Security Architecture

- **CSRF Protection**: Every mutating HTTP request is validated with `Flask-WTF` CSRF tokens. AJAX requests submit the token via the `X-CSRFToken` header.
- **Strict Media Validation**: File signatures (magic bytes) are checked against actual binary headers to prevent MIME confusion or executable uploads.
- **Safe HTML / XSS Defense**: All model-generated responses are rendered exclusively through `textContent` or escaped Jinja2 variables. Model outputs are never rendered with unescaped `innerHTML`.
- **Link Sanitization**: Every link produced by search grounding is validated to ensure it starts with `http://` or `https://`. Malicious protocols (e.g. `javascript:`, `data:`) are rejected.
- **External Link Security**: External hyperlinks strictly employ `rel="noopener noreferrer"` and `target="_blank"`.
- **Zero Media Retention**: Uploaded media and extracted frames are stored only in volatile temporary directories and destroyed in `finally` blocks immediately following processing.
- **Session Security**: Session cookies enforce `HttpOnly`, `SameSite=Lax`, and `Secure` (in production).

---

## License

This project is licensed under the MIT License.

