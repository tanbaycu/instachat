from datetime import datetime
import os
import random
import re
import time
from typing import Any, Dict, Optional

from google import genai
from google.genai import types

from config.config_manager import ConfigManager, get_config_manager, get_data_dir
from utils.cache_manager import get_image_cache

# Chỉ match các cụm từ mang ý định YÊU CẦU tạo/vẽ ảnh, tránh false-positive với "hình như", "ảnh này đẹp"...
_IMAGE_REQUEST_PATTERNS = (
    re.compile(
        r"\b(?:tạo|vẽ|sinh|làm)\s+(?:ra\s+)?(?:một\s+|cho\s+(?:mình|tui|tôi|em|anh|chị|bạn)\s+)?"
        r"(?:bức\s+|tấm\s+)?(?:ảnh|hình(?:\s+ảnh)?|tranh)\b",
        re.IGNORECASE | re.UNICODE,
    ),
    re.compile(
        r"\bvẽ\s+(?:giúp|cho|hộ|một|1|con|cái|ngôi|cô|anh|phong\s+cảnh|chân\s+dung)\b",
        re.IGNORECASE | re.UNICODE,
    ),
    re.compile(
        r"\b(?:generate|create|draw|sketch|paint|render|make)\s+(?:me\s+|us\s+)?"
        r"(?:an?\s+)?(?:image|picture|photo|pic|drawing|illustration|artwork|art)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:draw|sketch)\s+(?:a|an|me)\b", re.IGNORECASE),
)

_DESCRIPTION_EXTRACT_PATTERNS = (
    re.compile(
        r"(?:tạo|vẽ|sinh|làm)\s+(?:ra\s+)?(?:một\s+|cho\s+(?:mình|tui|tôi|em|anh|chị|bạn)\s+)?"
        r"(?:bức\s+|tấm\s+)?(?:ảnh|hình(?:\s+ảnh)?|tranh)\s*(?:về|của|là)?\s+(.+)",
        re.IGNORECASE | re.UNICODE,
    ),
    re.compile(r"vẽ\s+(?:giúp|cho|hộ)?\s*(.+)", re.IGNORECASE | re.UNICODE),
    re.compile(
        r"(?:generate|create|draw|sketch|paint|render|make)\s+(?:me\s+|us\s+)?(?:an?\s+)?"
        r"(?:image|picture|photo|pic|drawing|illustration|artwork|art)?\s*(?:of|about)?\s*(.+)",
        re.IGNORECASE,
    ),
)


class ImageGenerator:
    """Sinh ảnh bằng Google Gemini Image Generation (google-genai) với cache đĩa và phát hiện ý định chính xác."""

    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        genai_client: Any = None,
        output_dir: Optional[str] = None,
        config_manager: Optional[ConfigManager] = None,
    ):
        self.config_manager = config_manager or get_config_manager()
        self.output_dir = output_dir or get_data_dir("generated_images")
        os.makedirs(self.output_dir, exist_ok=True)

        self.text_model = self.config_manager.get("ai", "model", "gemini-flash-latest")
        self.image_model = self.config_manager.get(
            "ai", "image_model", "gemini-2.5-flash-image"
        )
        self.image_provider = self.config_manager.get("ai", "image_provider", "gemini")
        self.ai_intent_detection = bool(
            self.config_manager.get("ai", "image_generation.ai_intent_detection", False)
        )

        if genai_client is not None:
            self.genai_client = genai_client
        else:
            api_key = gemini_api_key or os.getenv("GEMINI_API_KEY") or self.config_manager.get("ai", "api_key")
            self.genai_client = genai.Client(api_key=api_key) if api_key else None

        self.image_cache = get_image_cache()
        self._processing = False
        self.stats: Dict[str, Any] = {
            "total_requests": 0,
            "successful_generations": 0,
            "failed_generations": 0,
            "start_time": datetime.now(),
        }

    def is_image_request(self, message: str) -> bool:
        """Kiểm tra chính xác tin nhắn có phải lệnh yêu cầu vẽ/tạo ảnh hay không."""
        if not message or not message.strip():
            return False

        msg_clean = message.strip()
        for pattern in _IMAGE_REQUEST_PATTERNS:
            if pattern.search(msg_clean):
                return True

        # Chỉ gọi LLM phân loại ý định khi bật rõ trong config để tránh tốn quota cho mọi tin nhắn.
        if self.ai_intent_detection and self.genai_client and len(msg_clean) > 10:
            try:
                intent_prompt = (
                    "Phân tích tin nhắn sau xem người dùng có đang yêu cầu bot tạo/vẽ một bức ảnh mới hay không.\n"
                    f'Tin nhắn: "{msg_clean}"\nChỉ trả lời đúng 1 từ: YES hoặc NO.'
                )
                resp = self.genai_client.models.generate_content(
                    model=self.text_model,
                    contents=intent_prompt,
                    config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=8),
                )
                return "YES" in (getattr(resp, "text", "") or "").upper()
            except Exception as exc:
                print(f"[IMAGE] ⚠️ AI intent detection failed: {exc}")

        return False

    def extract_description(self, message: str) -> str:
        msg_clean = (message or "").strip()
        for pattern in _DESCRIPTION_EXTRACT_PATTERNS:
            match = pattern.search(msg_clean)
            if match and match.group(1):
                extracted = re.sub(r"^(của|cho|về|một|cái|chiếc)\s+", "", match.group(1).strip(), flags=re.I)
                if extracted:
                    return extracted
        return msg_clean

    def enhance_prompt(self, description: str) -> str:
        try:
            if self.genai_client:
                prompt = (
                    "Translate to English if needed and rewrite as a concise, vivid image generation prompt "
                    "(lighting, style, composition). Return ONLY the prompt text.\n"
                    f'Input: "{description}"'
                )
                resp = self.genai_client.models.generate_content(
                    model=self.text_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=0.6, max_output_tokens=160),
                )
                enhanced = (getattr(resp, "text", "") or "").strip()
                enhanced = re.sub(r"^[\"'`]+|[\"'`]+$", "", enhanced).replace("\n", " ").strip()
                if enhanced:
                    return enhanced
        except Exception as exc:
            print(f"[IMAGE] ⚠️ Prompt enhancement fallback: {exc}")

        return self.basic_enhance(description)

    def basic_enhance(self, description: str) -> str:
        vi_to_en = {
            "mèo": "cat",
            "chó": "dog",
            "cô gái": "girl",
            "chàng trai": "boy",
            "người": "person",
            "phong cảnh": "landscape",
            "thành phố": "city",
            "biển": "ocean",
            "núi": "mountain",
            "hoa": "flower",
            "cây": "tree",
            "ô tô": "car",
            "nhà": "house",
            "đẹp": "beautiful",
            "xinh": "pretty",
            "đỏ": "red",
            "xanh": "blue",
            "vàng": "yellow",
            "trắng": "white",
            "đen": "black",
        }
        enhanced = (description or "").lower()
        for vi, en in vi_to_en.items():
            enhanced = re.sub(rf"\b{re.escape(vi)}\b", en, enhanced)
        if "high quality" not in enhanced and "4k" not in enhanced:
            enhanced = f"{enhanced}, high quality, detailed lighting"
        return enhanced.strip(", ")

    def _save_image_bytes(self, image_bytes: bytes, mime_type: str) -> str:
        ext = "png"
        if "jpeg" in mime_type or "jpg" in mime_type:
            ext = "jpg"
        elif "webp" in mime_type:
            ext = "webp"
        filename = f"img_{int(time.time() * 1000)}.{ext}"
        file_path = os.path.join(self.output_dir, filename)
        with open(file_path, "wb") as f:
            f.write(image_bytes)
        return file_path

    def generate_image(self, description: str) -> Dict[str, Any]:
        """Tạo ảnh và lưu file local (hoặc URL nếu dùng provider mở rộng)."""
        self._processing = True
        self.stats["total_requests"] += 1

        try:
            cached = self.image_cache.get_cached_image(description)
            if cached:
                self.stats["successful_generations"] += 1
                return {
                    "success": True,
                    "file_path": cached.get("file_path"),
                    "url": cached.get("url"),
                    "original_prompt": description,
                    "enhanced_prompt": description,
                    "cached": True,
                }

            enhanced_prompt = self.enhance_prompt(description)

            if self.image_provider == "g4f":
                from g4f.client import Client as G4FClient

                g4f_client = G4FClient()
                resp = g4f_client.images.generate(
                    model="flux", prompt=enhanced_prompt, response_format="url"
                )
                if resp and getattr(resp, "data", None):
                    image_url = resp.data[0].url
                    self.image_cache.cache_image(description, image_url, is_file=False)
                    self.stats["successful_generations"] += 1
                    return {
                        "success": True,
                        "file_path": None,
                        "url": image_url,
                        "original_prompt": description,
                        "enhanced_prompt": enhanced_prompt,
                    }
                raise RuntimeError("g4f không trả về URL ảnh")

            if not self.genai_client:
                raise RuntimeError("Thiếu GEMINI_API_KEY để tạo ảnh với Gemini")

            response = self.genai_client.models.generate_content(
                model=self.image_model,
                contents=enhanced_prompt,
                config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
            )

            parts = list(getattr(response, "parts", None) or [])
            if not parts and getattr(response, "candidates", None):
                candidate = response.candidates[0]
                if getattr(candidate, "content", None) and getattr(candidate.content, "parts", None):
                    parts = list(candidate.content.parts)

            for part in parts:
                inline = getattr(part, "inline_data", None)
                if inline and getattr(inline, "data", None):
                    raw_bytes = inline.data
                    if isinstance(raw_bytes, str):
                        import base64

                        raw_bytes = base64.b64decode(raw_bytes)
                    mime = getattr(inline, "mime_type", None) or "image/png"
                    saved_path = self._save_image_bytes(raw_bytes, mime)
                    self.image_cache.cache_image(description, saved_path, is_file=True)
                    self.stats["successful_generations"] += 1
                    return {
                        "success": True,
                        "file_path": saved_path,
                        "url": None,
                        "original_prompt": description,
                        "enhanced_prompt": enhanced_prompt,
                    }

            raise RuntimeError("Model không trả về dữ liệu ảnh (inline_data trống)")

        except Exception as exc:
            self.stats["failed_generations"] += 1
            return {
                "success": False,
                "error": str(exc),
                "original_prompt": description,
            }
        finally:
            self._processing = False

    def get_image_response_text(self, result: Dict[str, Any], user_name: str = "bạn") -> str:
        if result.get("success"):
            responses = [
                f"đây nè {user_name}, mình vừa tạo ảnh xong :)",
                f"ảnh của {user_name} đây, xem thử nha",
                f"tạo xong rồi nè {user_name}, hy vọng bạn thích :)",
            ]
            return random.choice(responses)

        error_responses = [
            f"sorry {user_name}, tạo ảnh bị lỗi rồi :(",
            f"tạo ảnh chưa được {user_name} ơi, thử lại sau nhé :(",
        ]
        return random.choice(error_responses)

    def get_stats(self) -> Dict[str, Any]:
        uptime = (datetime.now() - self.stats["start_time"]).total_seconds() / 60.0
        total = self.stats["total_requests"]
        success = self.stats["successful_generations"]
        return {
            "total_requests": total,
            "successful_generations": success,
            "failed_generations": self.stats["failed_generations"],
            "success_rate": (success / max(1, total)) * 100.0,
            "uptime_minutes": uptime,
        }

    def is_processing_image(self) -> bool:
        return self._processing
