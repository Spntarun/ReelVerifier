import os
import logging
import threading
from typing import List, Optional

logger = logging.getLogger(__name__)

# System prompt for visual evidence extraction
VISION_SYSTEM_PROMPT = """You are an expert visual evidence extractor analyzing media from social media reels (Instagram reels, TikTok, screenshots).
Your task is to extract factual visual observations from these chronological frames and images.

Strict guidelines:
1. Read and transcribe all visible text in screenshots and video frames (headings, subtitles, banners, URLs, forms).
2. Identify company names, brand logos, platforms, and creator handles.
3. Extract specific promotional claim details (job title, compensation, scholarship amount, course name, discount, coupon, giveaway).
4. Identify banners, registration forms, call-to-action messages (e.g. "link in bio", "comment FREE", "DM to apply"), and any website URLs shown.
5. Note visual context, chronological flow of frames, and any inconsistencies (e.g. mismatched fonts, fake badges, blurred disclaimers).
6. Return concise, objective observations in a structured list.
7. DO NOT make a final authenticity verdict or call anything fake or genuine. You only extract visual evidence."""


class VisionModelManager:
    """
    Reusable Model Manager for open-source Hugging Face Vision Language Models
    (e.g., Qwen/Qwen3-VL-8B-Instruct or Qwen/Qwen2.5-VL-7B-Instruct).
    Loads the model once, manages GPU memory, supports quantization, and handles fallbacks.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(VisionModelManager, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, config=None):
        if self._initialized:
            return
        self.config = config
        self.model = None
        self.processor = None
        self.device = None
        self.is_loaded = False
        self.load_failed = False
        self.load_error_message = ""
        self.inference_lock = threading.Lock()
        self._initialized = True

    def initialize(self, config):
        """Configure or reconfigure model settings."""
        self.config = config

    def _get_config_val(self, key, default):
        if not self.config:
            return default
        if hasattr(self.config, "get"):
            return self.config.get(key, default)
        return getattr(self.config, key, default)

    def load_model(self) -> bool:
        """
        Load the Hugging Face vision model into memory once.
        Supports GPU / CUDA, configurable quantization, and graceful error handling.
        """
        if self.is_loaded:
            return True
        if self.load_failed:
            return False

        if not self._get_config_val("ENABLE_LOCAL_VISION", True):
            logger.info("Local vision model is disabled by configuration.")
            return False

        model_name = self._get_config_val("VISION_MODEL", "Qwen/Qwen3-VL-8B-Instruct")
        requested_device = self._get_config_val("VISION_DEVICE", "cuda")
        quantization = self._get_config_val("VISION_QUANTIZATION", None)

        try:
            import torch
            from transformers import AutoProcessor, AutoModelForVision2Seq

            # Determine device
            if requested_device == "cuda" and torch.cuda.is_available():
                self.device = "cuda"
            else:
                self.device = "cpu"
                logger.info(f"CUDA not available or CPU requested. Running vision model on {self.device}.")

            logger.info(f"Loading vision model '{model_name}' on device '{self.device}' (quantization: {quantization})...")

            # Configure quantization if specified
            model_kwargs = {"trust_remote_code": True}
            if self.device == "cuda":
                if quantization == "4bit":
                    from transformers import BitsAndBytesConfig
                    model_kwargs["quantization_config"] = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_compute_dtype=torch.float16,
                    )
                elif quantization == "8bit":
                    from transformers import BitsAndBytesConfig
                    model_kwargs["quantization_config"] = BitsAndBytesConfig(
                        load_in_8bit=True,
                    )
                else:
                    model_kwargs["torch_dtype"] = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
                    model_kwargs["device_map"] = "auto"
            else:
                model_kwargs["torch_dtype"] = torch.float32

            # Load processor and model
            self.processor = AutoProcessor.from_pretrained(model_name, trust_remote_code=True)
            self.model = AutoModelForVision2Seq.from_pretrained(model_name, **model_kwargs)

            if self.device == "cpu":
                self.model.to("cpu")

            self.model.eval()
            self.is_loaded = True
            logger.info(f"Vision model '{model_name}' successfully loaded.")
            return True

        except Exception as e:
            self.load_failed = True
            self.load_error_message = str(e)
            logger.warning(
                f"Failed to load local vision model '{model_name}': {e}. "
                "The application will automatically fall back to Gemini multimodal analysis."
            )
            # Free any CUDA cache if failed
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
            return False

    def extract_visual_observations(self, image_paths: List[str]) -> Optional[str]:
        """
        Run inference across ordered images or extracted video frames.
        Returns formatted visual observations or None if model is unavailable / failed.
        """
        if not image_paths:
            return None

        if not self.is_loaded:
            if not self.load_model():
                return None

        # Lock inference to keep Flask responsive and avoid concurrent GPU VRAM exhaustion
        with self.inference_lock:
            try:
                import torch
                from PIL import Image

                # Prepare input messages for vision model
                content = []
                for p in image_paths:
                    if os.path.exists(p):
                        content.append({"type": "image", "image": p})

                if not content:
                    return None

                content.append({
                    "type": "text",
                    "text": (
                        "Analyze these media frames in chronological order. "
                        "List all visible on-screen text, brand logos, offer details, "
                        "deadlines, URLs, call to actions, and any visual inconsistencies."
                    )
                })

                messages = [
                    {"role": "system", "content": VISION_SYSTEM_PROMPT},
                    {"role": "user", "content": content},
                ]

                # Format prompt using processor chat template
                text_prompt = self.processor.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True
                )

                # Process images
                images = [Image.open(p).convert("RGB") for p in image_paths if os.path.exists(p)]
                inputs = self.processor(
                    text=[text_prompt],
                    images=images if images else None,
                    padding=True,
                    return_tensors="pt",
                )

                if self.device == "cuda":
                    inputs = {k: v.to(self.device) if isinstance(v, torch.Tensor) else v for k, v in inputs.items()}

                with torch.no_grad():
                    generated_ids = self.model.generate(
                        **inputs,
                        max_new_tokens=768,
                        do_sample=False,
                    )

                # Trim input tokens
                trimmed_ids = [
                    out_ids[len(in_ids):]
                    for in_ids, out_ids in zip(inputs["input_ids"], generated_ids)
                ]
                output_text = self.processor.batch_decode(
                    trimmed_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False
                )[0]

                logger.info(f"Local vision model extracted observations ({len(output_text)} chars).")
                return output_text.strip()

            except Exception as e:
                logger.warning(
                    f"Local vision inference encountered an error: {e}. "
                    "Falling back to Gemini multimodal capabilities."
                )
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except Exception:
                    pass
                return None


# Global singleton instance
vision_manager = VisionModelManager()

