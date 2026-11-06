/**
 * Reel Verifier — Client-side Application Logic
 * Pure Vanilla JavaScript (No React, Vue, or build tools)
 * Handles drag-and-drop, client validation, CSRF headers, Fetch API requests,
 * and safe textContent DOM rendering (XSS prevention).
 */

document.addEventListener("DOMContentLoaded", () => {
    // --- Elements ---
    const dropzone = document.getElementById("dropzone");
    const fileInput = document.getElementById("file-input");
    const browseBtn = document.getElementById("browse-btn");
    const previewsContainer = document.getElementById("file-previews");
    const captionInput = document.getElementById("caption-input");
    const charCounter = document.getElementById("char-counter");
    const verifyForm = document.getElementById("verify-form");
    const submitBtn = document.getElementById("submit-btn");
    const formError = document.getElementById("form-error");

    const loadingSection = document.getElementById("loading-section");
    const loadingStatusText = document.getElementById("loading-status-text");
    const step1 = document.getElementById("step-1");
    const step2 = document.getElementById("step-2");
    const step3 = document.getElementById("step-3");

    const resultSection = document.getElementById("result-section");
    const resultCacheBadge = document.getElementById("result-cache-badge");
    const verdictBanner = document.getElementById("verdict-banner");
    const verdictLabel = document.getElementById("verdict-label");
    const confidenceVal = document.getElementById("confidence-val");
    const confidenceBar = document.getElementById("confidence-bar");
    const resultSummary = document.getElementById("result-summary");
    const redFlagsBlock = document.getElementById("red-flags-block");
    const redFlagsList = document.getElementById("red-flags-list");
    const resultAdvice = document.getElementById("result-advice");
    const linksContainer = document.getElementById("links-container");
    const noLinksMsg = document.getElementById("no-links-msg");

    const claimCategory = document.getElementById("claim-category");
    const claimBrand = document.getElementById("claim-brand");
    const claimOffer = document.getElementById("claim-offer");
    const claimRole = document.getElementById("claim-role");
    const claimLocation = document.getElementById("claim-location");
    const claimEligibility = document.getElementById("claim-eligibility");
    const claimDeadline = document.getElementById("claim-deadline");
    const claimCreator = document.getElementById("claim-creator");
    const claimCta = document.getElementById("claim-cta");
    const claimLinkShown = document.getElementById("claim-link-shown");
    const claimUrgencyWrapper = document.getElementById("claim-urgency-wrapper");
    const claimUrgencyTags = document.getElementById("claim-urgency-tags");

    const viewSavedLink = document.getElementById("view-saved-link");
    const checkAnotherBtn = document.getElementById("check-another-btn");

    // Only run upload logic if dropzone exists (on /check page)
    if (!dropzone || !fileInput) {
        return;
    }

    // Selected files buffer
    let selectedFiles = [];

    const MAX_FILES = 4;
    const MAX_IMAGE_BYTES = 5 * 1024 * 1024;   // 5 MB
    const MAX_VIDEO_BYTES = 60 * 1024 * 1024;  // 60 MB

    const ALLOWED_MIME_PREFIXES = [
        "image/jpeg", "image/png", "image/webp", "image/gif",
        "video/mp4", "video/quicktime", "video/webm"
    ];

    // Helper: Retrieve CSRF Token from meta tag
    function getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute("content") : "";
    }

    // --- Caption Character Counter ---
    if (captionInput && charCounter) {
        captionInput.addEventListener("input", () => {
            const len = captionInput.value.length;
            charCounter.textContent = `${len} / 2000`;
            if (len >= 1950) {
                charCounter.style.color = "var(--verdict-suspicious-text)";
            } else {
                charCounter.style.color = "var(--text-muted)";
            }
        });
    }

    // --- Dropzone & File Input Handlers ---
    if (browseBtn) {
        browseBtn.addEventListener("click", (e) => {
            e.preventDefault();
            fileInput.click();
        });
    }

    dropzone.addEventListener("click", (e) => {
        // Prevent clicking child buttons from double-triggering
        if (e.target !== browseBtn) {
            fileInput.click();
        }
    });

    dropzone.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            fileInput.click();
        }
    });

    // Drag-over styling
    ["dragenter", "dragover"].forEach((eventName) => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.add("dragover");
        });
    });

    ["dragleave", "drop"].forEach((eventName) => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.remove("dragover");
        });
    });

    dropzone.addEventListener("drop", (e) => {
        const dt = e.dataTransfer;
        if (dt && dt.files && dt.files.length > 0) {
            handleIncomingFiles(Array.from(dt.files));
        }
    });

    fileInput.addEventListener("change", () => {
        if (fileInput.files && fileInput.files.length > 0) {
            handleIncomingFiles(Array.from(fileInput.files));
        }
    });

    // --- Validation and File Buffer Management ---
    function showError(msg) {
        if (formError) {
            formError.textContent = msg;
            formError.classList.remove("hidden");
        }
    }

    function clearError() {
        if (formError) {
            formError.textContent = "";
            formError.classList.add("hidden");
        }
    }

    function handleIncomingFiles(newFiles) {
        clearError();

        if (selectedFiles.length + newFiles.length > MAX_FILES) {
            showError(`You can upload at most ${MAX_FILES} files in total.`);
            return;
        }

        for (const file of newFiles) {
            // Validate MIME type
            const isSupported = ALLOWED_MIME_PREFIXES.some(prefix => file.type.startsWith(prefix)) ||
                file.name.match(/\.(jpe?g|png|webp|gif|mp4|mov|webm)$/i);

            if (!isSupported) {
                showError(`File '${file.name}' is not a supported format. Please upload JPEG, PNG, WebP, GIF, MP4, MOV, or WebM.`);
                return;
            }

            // Validate Size
            const isVideo = file.type.startsWith("video") || file.name.match(/\.(mp4|mov|webm)$/i);
            if (isVideo && file.size > MAX_VIDEO_BYTES) {
                showError(`Video '${file.name}' (${(file.size / (1024*1024)).toFixed(1)}MB) exceeds the 60MB limit.`);
                return;
            }
            if (!isVideo && file.size > MAX_IMAGE_BYTES) {
                showError(`Image '${file.name}' (${(file.size / (1024*1024)).toFixed(1)}MB) exceeds the 5MB limit.`);
                return;
            }

            selectedFiles.push(file);
        }

        renderPreviews();
    }

    function removeFile(index) {
        selectedFiles.splice(index, 1);
        renderPreviews();
    }

    function renderPreviews() {
        previewsContainer.innerHTML = "";
        if (selectedFiles.length === 0) {
            previewsContainer.classList.add("hidden");
            return;
        }

        previewsContainer.classList.remove("hidden");

        selectedFiles.forEach((file, idx) => {
            const previewCard = document.createElement("div");
            previewCard.className = "preview-item";

            const removeBtn = document.createElement("button");
            removeBtn.type = "button";
            removeBtn.className = "preview-remove-btn";
            removeBtn.setAttribute("aria-label", `Remove ${file.name}`);
            removeBtn.textContent = "×";
            removeBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                removeFile(idx);
            });

            const metaBar = document.createElement("div");
            metaBar.className = "preview-meta";
            metaBar.textContent = `${file.name} (${(file.size / (1024*1024)).toFixed(1)}M)`;

            if (file.type.startsWith("image/")) {
                const img = document.createElement("img");
                img.className = "preview-thumb";
                img.alt = file.name;
                img.src = URL.createObjectURL(file);
                previewCard.appendChild(img);
            } else {
                const vidPlaceholder = document.createElement("div");
                vidPlaceholder.className = "preview-video-placeholder";
                const icon = document.createElement("span");
                icon.textContent = "🎬";
                const label = document.createElement("span");
                label.style.fontSize = "0.75rem";
                label.textContent = "Video";
                vidPlaceholder.appendChild(icon);
                vidPlaceholder.appendChild(label);
                previewCard.appendChild(vidPlaceholder);
            }

            previewCard.appendChild(removeBtn);
            previewCard.appendChild(metaBar);
            previewsContainer.appendChild(previewCard);
        });
    }

    // --- Loading State Simulation Steps ---
    let stepInterval = null;

    function startLoadingAnimation() {
        loadingSection.classList.remove("hidden");
        resultSection.classList.add("hidden");
        submitBtn.disabled = true;
        const spinner = submitBtn.querySelector(".btn-spinner");
        if (spinner) spinner.classList.remove("hidden");

        step1.className = "loading-step active";
        step2.className = "loading-step";
        step3.className = "loading-step";
        loadingStatusText.textContent = "Processing media and video frames...";

        let currentStep = 1;
        stepInterval = setInterval(() => {
            currentStep++;
            if (currentStep === 2) {
                step1.className = "loading-step";
                step2.className = "loading-step active";
                loadingStatusText.textContent = "Extracting promotional claims and details...";
            } else if (currentStep === 3) {
                step2.className = "loading-step";
                step3.className = "loading-step active";
                loadingStatusText.textContent = "Cross-referencing official sites with Google Search...";
            }
        }, 3500);
    }

    function stopLoadingAnimation() {
        if (stepInterval) clearInterval(stepInterval);
        loadingSection.classList.add("hidden");
        submitBtn.disabled = false;
        const spinner = submitBtn.querySelector(".btn-spinner");
        if (spinner) spinner.classList.add("hidden");
    }

    // --- Form Submission via Fetch API ---
    verifyForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        clearError();

        const caption = captionInput ? captionInput.value.trim() : "";
        if (selectedFiles.length === 0 && !caption) {
            showError("Please upload at least one image or video, or provide a caption to check.");
            return;
        }

        const formData = new FormData();
        selectedFiles.forEach((file) => {
            formData.append("files", file);
        });
        if (caption) {
            formData.append("caption", caption);
        }

        startLoadingAnimation();

        try {
            const response = await fetch("/api/analyze", {
                method: "POST",
                headers: {
                    "X-CSRFToken": getCsrfToken(),
                },
                body: formData,
            });

            const data = await response.json();
            stopLoadingAnimation();

            if (!response.ok || !data.success) {
                const msg = data.error || "Verification failed. Please try again.";
                showError(msg);
                return;
            }

            renderVerificationResult(data);

        } catch (err) {
            stopLoadingAnimation();
            showError("A network error occurred. Please check your connection and try again.");
            console.error("Fetch error:", err);
        }
    });

    // --- Safe DOM Rendering of Results (XSS Prevention) ---
    function renderVerificationResult(data) {
        // Cached badge
        if (data.cached) {
            resultCacheBadge.classList.remove("hidden");
        } else {
            resultCacheBadge.classList.add("hidden");
        }

        // Verdict Badge & Styling
        const verdict = data.verdict || "unverified";
        const label = data.verdict_label || "Couldn't verify";

        verdictLabel.textContent = label;
        verdictLabel.className = `verdict-badge-large badge-${verdict}`;

        // Confidence Bar
        const conf = data.confidence !== undefined ? data.confidence : 0;
        confidenceVal.textContent = `${conf}%`;
        confidenceBar.style.width = `${conf}%`;

        // Bar color based on verdict
        if (verdict === "verified") {
            confidenceBar.style.backgroundColor = "var(--verdict-verified-bar)";
        } else if (verdict === "partial") {
            confidenceBar.style.backgroundColor = "var(--verdict-partial-bar)";
        } else if (verdict === "suspicious") {
            confidenceBar.style.backgroundColor = "var(--verdict-suspicious-bar)";
        } else {
            confidenceBar.style.backgroundColor = "var(--verdict-unverified-bar)";
        }

        // Summary
        resultSummary.textContent = data.summary || "No summary provided.";

        // Red Flags
        redFlagsList.innerHTML = "";
        const flags = data.red_flags || [];
        if (flags.length > 0) {
            redFlagsBlock.classList.remove("hidden");
            flags.forEach((flagText) => {
                const li = document.createElement("li");
                li.textContent = flagText;
                redFlagsList.appendChild(li);
            });
        } else {
            redFlagsBlock.classList.add("hidden");
        }

        // Advice
        resultAdvice.textContent = data.advice || "Always apply through the official website and never pay application fees.";

        // Official Links
        linksContainer.innerHTML = "";
        const links = data.official_links || [];
        const validLinks = links.filter(l => l.url && (l.url.startsWith("http://") || l.url.startsWith("https://")));

        if (validLinks.length > 0) {
            noLinksMsg.classList.add("hidden");
            validLinks.forEach((link) => {
                const linkCard = document.createElement("a");
                linkCard.href = link.url;
                linkCard.target = "_blank";
                linkCard.rel = "noopener noreferrer";
                linkCard.className = "official-link-card";

                const infoDiv = document.createElement("div");
                infoDiv.className = "link-info";

                const titleSpan = document.createElement("span");
                titleSpan.className = "link-title";
                titleSpan.textContent = link.title || link.url;

                const urlSpan = document.createElement("span");
                urlSpan.className = "link-url";
                urlSpan.textContent = link.url;

                infoDiv.appendChild(titleSpan);
                infoDiv.appendChild(urlSpan);

                const iconSpan = document.createElement("span");
                iconSpan.className = "external-icon";
                iconSpan.textContent = "↗";

                linkCard.appendChild(infoDiv);
                linkCard.appendChild(iconSpan);
                linksContainer.appendChild(linkCard);
            });
        } else {
            noLinksMsg.classList.remove("hidden");
        }

        // Extracted Claim Fields
        const claim = data.claim || {};
        claimCategory.textContent = claim.category ? claim.category.replace(/_/g, " ").toUpperCase() : "—";
        claimBrand.textContent = claim.brand_or_company || "—";
        claimOffer.textContent = claim.offer || "—";
        claimRole.textContent = claim.role_or_item || "—";
        claimLocation.textContent = claim.location || "—";
        claimEligibility.textContent = claim.eligibility || "—";
        claimDeadline.textContent = claim.deadline || "—";
        claimCreator.textContent = claim.creator_handle || "—";
        claimCta.textContent = claim.call_to_action || "—";
        claimLinkShown.textContent = claim.link_shown || "—";

        // Urgency tags
        claimUrgencyTags.innerHTML = "";
        const urgencyPhrases = claim.urgency_or_pressure_phrases || [];
        if (urgencyPhrases.length > 0) {
            claimUrgencyWrapper.classList.remove("hidden");
            urgencyPhrases.forEach((phrase) => {
                const tag = document.createElement("span");
                tag.className = "tag tag-warning";
                tag.textContent = phrase;
                claimUrgencyTags.appendChild(tag);
            });
        } else {
            claimUrgencyWrapper.classList.add("hidden");
        }

        // View Saved Report link
        if (data.id || data.check_id) {
            const id = data.id || data.check_id;
            viewSavedLink.href = `/result/${id}`;
            viewSavedLink.classList.remove("hidden");
        } else {
            viewSavedLink.classList.add("hidden");
        }

        // Display results section smoothly
        resultSection.classList.remove("hidden");
        resultSection.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    // --- Reset for Another Verification ---
    if (checkAnotherBtn) {
        checkAnotherBtn.addEventListener("click", () => {
            selectedFiles = [];
            renderPreviews();
            if (captionInput) {
                captionInput.value = "";
                if (charCounter) charCounter.textContent = "0 / 2000";
            }
            clearError();
            resultSection.classList.add("hidden");
            window.scrollTo({ top: 0, behavior: "smooth" });
        });
    }
});

