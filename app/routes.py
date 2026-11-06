import os
import json
import logging
from datetime import datetime, timezone
from flask import (
    Blueprint,
    render_template,
    request,
    jsonify,
    redirect,
    url_for,
    current_app,
    abort,
)
from app.models import db, User, Check
from app.auth import login_required, get_current_user
from app.media import (
    MediaProcessor,
    MediaValidationError,
    compute_deterministic_hash,
    TemporaryMediaManager,
)
from app.vision import vision_manager
from app.analysis import ReelAnalysisPipeline

logger = logging.getLogger(__name__)

routes_bp = Blueprint("routes", __name__)


@routes_bp.route("/")
def landing():
    """Landing page. Redirects authenticated users directly to /check."""
    user = get_current_user()
    if user:
        return redirect(url_for("routes.check_view"))
    return render_template("landing.html")


@routes_bp.route("/check")
@login_required
def check_view():
    """Upload and verification workspace page."""
    user = get_current_user()
    return render_template("check.html", user=user)


@routes_bp.route("/history")
@login_required
def history():
    """Display verification history for the current user."""
    user = get_current_user()
    checks = (
        Check.query.filter_by(user_id=user.id)
        .order_by(Check.created_at.desc())
        .all()
    )
    return render_template("history.html", user=user, checks=checks)


@routes_bp.route("/result/<int:check_id>")
@login_required
def result_detail(check_id: int):
    """View stored detailed verification report (owner-only)."""
    user = get_current_user()
    check = db.session.get(Check, check_id)
    if not check:
        abort(404)

    # Enforce strict ownership
    if check.user_id != user.id:
        abort(403)

    return render_template(
        "result.html",
        user=user,
        check=check,
        claim=check.get_claim(),
        verdict_data=check.get_verdict(),
    )


@routes_bp.route("/api/analyze", methods=["POST"])
@login_required
def analyze_endpoint():
    """
    Asynchronous analysis endpoint for social media reels and promotional claims.
    Accepts multipart form-data with files and caption.
    Returns structured verification results.
    """
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required."}), 401

    # Extract inputs
    caption = (request.form.get("caption") or "").strip()
    if len(caption) > current_app.config.get("MAX_CAPTION_LENGTH", 2000):
        return jsonify({
            "success": False,
            "error": f"Caption is too long (maximum {current_app.config.get('MAX_CAPTION_LENGTH', 2000)} characters)."
        }), 400

    uploaded_files = request.files.getlist("files") or request.files.getlist("files[]")
    # Filter empty file handles
    valid_file_handles = [f for f in uploaded_files if f and f.filename and f.filename.strip()]

    # Validate overall input presence
    if not valid_file_handles and not caption:
        return jsonify({
            "success": False,
            "error": "Please provide at least one screenshot/video or a caption describing the offer."
        }), 400

    max_files = current_app.config.get("MAX_FILES_PER_REQUEST", 4)
    if len(valid_file_handles) > max_files:
        return jsonify({
            "success": False,
            "error": f"You can upload at most {max_files} files per check."
        }), 400

    # Initialize media processor
    media_processor = MediaProcessor(current_app.config)
    max_img_size = current_app.config.get("MAX_IMAGE_SIZE_BYTES", 5 * 1024 * 1024)
    max_vid_size = current_app.config.get("MAX_VIDEO_SIZE_BYTES", 60 * 1024 * 1024)

    # Validate file contents and magic bytes
    validated_files = []
    for f in valid_file_handles:
        try:
            processed_file = media_processor.validate_file_content(f, max_img_size, max_vid_size)
            validated_files.append(processed_file)
        except MediaValidationError as e:
            return jsonify({"success": False, "error": str(e)}), 400
        except Exception as e:
            logger.error(f"File validation error: {e}")
            return jsonify({"success": False, "error": f"Error reading file '{f.filename}'."}), 400

    # 1. Deterministic hashing for caching
    input_hash = compute_deterministic_hash([f.content_bytes for f in validated_files], caption)

    # 2. Check for cached result for this user
    cached_check = Check.query.filter_by(user_id=user.id, input_hash=input_hash).first()
    if cached_check:
        logger.info(f"Returning cached verification result for check {cached_check.id} (user {user.id})")
        response_data = cached_check.to_dict(include_details=True)
        response_data["success"] = True
        response_data["cached"] = True
        return jsonify(response_data), 200

    # 3. Check daily limits for this user
    now_utc = datetime.now(timezone.utc)
    start_of_day_utc = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)
    today_checks_count = (
        Check.query.filter(Check.user_id == user.id, Check.created_at >= start_of_day_utc)
        .count()
    )
    daily_limit = current_app.config.get("DAILY_LIMIT_PER_USER", 10)
    if today_checks_count >= daily_limit:
        return jsonify({
            "success": False,
            "limit_reached": True,
            "error": (
                f"You have reached your daily limit of {daily_limit} verifications. "
                "Your limit will reset tomorrow at 00:00 UTC."
            ),
        }), 429

    # 4. Execute media processing and AI pipeline
    # Temporary files are stored in an isolated temporary directory and automatically deleted in finally block
    temp_dir_base = current_app.config.get("TEMP_MEDIA_DIR")

    with TemporaryMediaManager(base_dir=temp_dir_base) as temp_dir:
        all_image_paths = []
        frames_bytes_for_gemini = []
        all_transcripts = []

        try:
            for idx, pfile in enumerate(validated_files):
                if pfile.file_type == "image":
                    ext = ".jpg" if pfile.mime_type == "image/jpeg" else ".png"
                    img_path = os.path.join(temp_dir, f"input_{idx}{ext}")
                    with open(img_path, "wb") as out_f:
                        out_f.write(pfile.content_bytes)
                    all_image_paths.append(img_path)
                    frames_bytes_for_gemini.append((pfile.content_bytes, pfile.mime_type))

                elif pfile.file_type == "video":
                    ext = ".webm" if "webm" in pfile.mime_type else ".mp4"
                    vid_path = os.path.join(temp_dir, f"video_{idx}{ext}")
                    with open(vid_path, "wb") as out_f:
                        out_f.write(pfile.content_bytes)

                    # Probe video duration and stream validity
                    duration = media_processor.probe_video_duration(vid_path)
                    max_duration = current_app.config.get("MAX_VIDEO_DURATION_SECONDS", 120)
                    if duration > max_duration:
                        return jsonify({
                            "success": False,
                            "error": f"Video '{pfile.original_filename}' is {duration:.0f}s long (maximum allowed duration is {max_duration}s)."
                        }), 400

                    # Extract up to 10 chronological frames
                    frames = media_processor.extract_video_frames(vid_path, duration, temp_dir)
                    all_image_paths.extend(frames)

                    # Read frame bytes for multimodal fallback
                    for frame_p in frames:
                        try:
                            with open(frame_p, "rb") as fr_f:
                                frames_bytes_for_gemini.append((fr_f.read(), "image/jpeg"))
                        except Exception:
                            pass

                    # Extract and transcribe audio
                    if current_app.config.get("ENABLE_TRANSCRIPTION", True):
                        transcript = media_processor.transcribe_video_audio(vid_path, temp_dir)
                        if transcript:
                            all_transcripts.append(transcript)

            combined_transcript = " ".join(all_transcripts).strip()

            # --- Stage A: Local Vision Inference ---
            visual_observations = None
            if current_app.config.get("ENABLE_LOCAL_VISION", True) and all_image_paths:
                try:
                    visual_observations = vision_manager.extract_visual_observations(all_image_paths)
                except Exception as e:
                    logger.warning(f"Stage A vision model failed: {e}. Falling back to Gemini vision.")
                    visual_observations = None

            # --- Stage B: Gemini Claim Extraction ---
            analysis_pipeline = ReelAnalysisPipeline(current_app.config)
            claim = analysis_pipeline.extract_claim(
                visual_observations=visual_observations,
                frames_bytes=frames_bytes_for_gemini,
                transcript=combined_transcript,
                caption=caption,
            )

            # --- Stage C: Gemini Web Verification with Google Search ---
            verdict = analysis_pipeline.verify_claim(claim)

            # 5. Persist result in database
            check_record = Check(
                user_id=user.id,
                input_hash=input_hash,
                claim_json=json.dumps(claim.model_dump()),
                verdict_json=json.dumps(verdict.model_dump()),
                verdict=verdict.verdict,
                confidence=verdict.confidence,
            )
            db.session.add(check_record)
            db.session.commit()

            logger.info(f"Created check #{check_record.id} for user #{user.id}: {verdict.verdict} ({verdict.confidence}%)")

            # Prepare successful response
            response_data = check_record.to_dict(include_details=True)
            response_data["success"] = True
            response_data["cached"] = False
            return jsonify(response_data), 200

        except MediaValidationError as e:
            return jsonify({"success": False, "error": str(e)}), 400
        except RuntimeError as e:
            logger.error(f"Pipeline runtime error: {e}")
            return jsonify({"success": False, "error": str(e)}), 503
        except Exception as e:
            db.session.rollback()
            logger.exception(f"Unexpected error in /api/analyze: {e}")
            return jsonify({
                "success": False,
                "error": "A service error occurred while verifying the claim. Please try again shortly."
            }), 500
