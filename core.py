from datetime import datetime
import os
import random
import re
import time
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

from analytics.analytics_engine import get_analytics_engine
from config.config_manager import get_config_manager
from image_generator import ImageGenerator
from llm_memories_manager import ActivateLocalMemories, ShortContextManager, WriteNewLocalMemories
from memory.store import SQLiteMemoryStore
from monitoring.error_handler import ErrorSeverity, get_error_handler, log_errors
from monitoring.performance_monitor import get_performance_monitor, measure_response_time
from security.security_manager import get_security_manager
from utils.cache_manager import get_image_cache, get_response_cache
from utils.notification_system import (
    get_notification_system,
    notify_error,
    notify_info,
    notify_warning,
)


class InstaBot:
    """AI Engine trung tâm sử dụng google-genai, SQLiteMemoryStore và bộ lọc an toàn."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        genai_client: Any = None,
        memory_store: Optional[SQLiteMemoryStore] = None,
    ):
        self.config_manager = get_config_manager()
        self.performance_monitor = get_performance_monitor()
        self.error_handler = get_error_handler()
        self.security_manager = get_security_manager()
        self.analytics_engine = get_analytics_engine()
        self.response_cache = get_response_cache()
        self.image_cache = get_image_cache()
        self.notification_system = get_notification_system()

        self.model_name = self.config_manager.get("ai", "model", "gemini-flash-latest")

        if genai_client is not None:
            self.genai_client = genai_client
            resolved_key = api_key or os.getenv("GEMINI_API_KEY") or self.config_manager.get("ai", "api_key")
        else:
            resolved_key = api_key or os.getenv("GEMINI_API_KEY") or self.config_manager.get("ai", "api_key")
            if not resolved_key:
                raise ValueError(
                    "Cần GEMINI_API_KEY trong biến môi trường hoặc truyền tham số api_key"
                )
            self.genai_client = genai.Client(api_key=resolved_key)

        self.image_generator: Optional[ImageGenerator]
        try:
            self.image_generator = ImageGenerator(
                gemini_api_key=resolved_key,
                genai_client=self.genai_client,
                config_manager=self.config_manager,
            )
        except Exception as exc:
            print(f"[CORE] ⚠️ Không thể khởi tạo ImageGenerator: {exc}")
            self.image_generator = None

        memory_config = self.config_manager.get("ai", "memory_settings", {}) or {}
        self.short_context_limit = int(memory_config.get("short_context_limit", 12))
        self.long_memory_limit = int(memory_config.get("long_memory_limit", 10))

        self.memory_store = memory_store or SQLiteMemoryStore()
        # Giữ các wrapper tương thích ngược để không phá vỡ caller cũ
        self.local_memories = ActivateLocalMemories(limit_mem_storage=self.long_memory_limit)
        self.short_context = ShortContextManager(
            s="user: ", t="bot: ", max_limit_short_mem_contxt=self.short_context_limit
        )
        self.memory_writer = WriteNewLocalMemories(
            max_mem_context_towrite=int(memory_config.get("memory_write_threshold", 16)),
            s="user: ",
            t="bot: ",
        )

        self.stats: Dict[str, Any] = {
            "total_messages": 0,
            "start_time": datetime.now(),
            "last_message_time": None,
            "memories_activated": 0,
            "memories_written": 0,
            "images_generated": 0,
        }

        self.is_generating_image = False
        self.last_image_request_time = 0.0

        mon_interval = float(
            self.config_manager.get("monitoring", "performance.monitoring_interval", 10) or 10
        )
        if self.config_manager.get("monitoring", "performance.enabled", True):
            self.performance_monitor.start_monitoring(interval=mon_interval)

        notify_info("InstaBot khởi tạo thành công", "startup")

    def get_system_prompt(self) -> str:
        prompt = self.config_manager.get("ai", "system_prompt")
        if prompt and str(prompt).strip():
            return str(prompt).strip()
        return (
            "Bạn là trợ lý chat Instagram thân thiện, nói chuyện tự nhiên, lịch sự và ngắn gọn. "
            "Trả lời bằng ngôn ngữ mà người dùng sử dụng."
        )

    def safe_write_memory(self, user_message: str, ai_response: str) -> bool:
        try:
            self.memory_writer.write_newLocalMem(user_message, ai_response)
            return True
        except Exception as exc:
            print(f"[MEMORY] ⚠️ Lỗi khi lưu file memory: {exc}")
            return False

    def _generate_content_with_retry(
        self,
        contents: str,
        config: types.GenerateContentConfig,
        max_attempts: int = 3,
        base_delay: float = 0.5,
    ) -> Any:
        """Gọi Gemini API kèm exponential backoff cho lỗi mạng/429/503 tạm thời."""
        last_exc: Optional[Exception] = None
        for attempt in range(max(1, max_attempts)):
            try:
                return self.genai_client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=config,
                )
            except Exception as exc:
                last_exc = exc
                msg_lower = str(exc).lower()
                non_retryable = isinstance(exc, ValueError) or any(
                    token in msg_lower
                    for token in ("api_key", "api key", "invalid argument", "permission denied")
                )
                if non_retryable or attempt >= max_attempts - 1:
                    raise
                delay = (base_delay * (2**attempt)) + random.uniform(0.0, 0.25)
                time.sleep(delay)
        if last_exc is not None:
            raise last_exc

    @measure_response_time
    @log_errors(severity=ErrorSeverity.HIGH, context="generate_response")
    def generate_response(self, user_message: str, username: str = "user") -> str:
        start_ts = time.time()
        try:
            is_valid, error_msg = self.security_manager.validate_message(user_message, username)
            if not is_valid:
                self.security_manager.log_message(user_message, username, "", f"rejected: {error_msg}")
                notify_warning(f"Message rejected ({username}): {error_msg}", "security")
                return "tin nhắn không hợp lệ hoặc vượt giới hạn, vui lòng thử lại sau nhé"

            # Chỉ dùng ResponseCache cho chat nếu được bật rõ ràng; mặc định tắt để bot không lặp máy móc.
            if self.config_manager.get("cache", "cache_chat_responses", False):
                cached = self.response_cache.get_cached_response(user_message, username)
                if cached:
                    self.security_manager.log_message(user_message, username, cached[:100], "cached")
                    return cached

            self.stats["total_messages"] += 1
            self.stats["last_message_time"] = datetime.now()

            current_time = time.time()
            if self.is_generating_image:
                if (current_time - self.last_image_request_time) < 60:
                    return "mình đang tạo ảnh nè, bạn chờ chút xíu nhé"
                self.is_generating_image = False
                notify_warning("Reset trạng thái tạo ảnh do quá thời gian chờ", "image_generation")

            if self.image_generator and self.image_generator.is_image_request(user_message):
                response = self.handle_image_request(user_message, username)
                self.security_manager.log_message(user_message, username, response[:100], "image_request")
                return response

            response = self.handle_normal_message(user_message, username)

            if self.config_manager.get("cache", "cache_chat_responses", False):
                self.response_cache.cache_response(user_message, response, username)

            self.security_manager.log_message(user_message, username, response[:100], "processed")
            self.analytics_engine.record_conversation(
                user_message, response, username, time.time() - start_ts
            )
            return response

        except Exception as exc:
            self.error_handler.log_error(exc, "generate_response", ErrorSeverity.HIGH, user_message)
            notify_error(f"Lỗi khi tạo phản hồi: {exc}", "generate_response")
            fallback_responses = [
                "uh mạng bên mình hơi lag chút, bạn nhắn lại giúp mình nha",
                "mình chưa kịp hiểu ý bạn, nói rõ hơn giúp mình được không",
                "sorry mình bị khựng nhịp tí, bạn nhắc lại giúp mình nha",
            ]
            return random.choice(fallback_responses)

    def handle_image_request(self, user_message: str, username: str = "user") -> str:
        try:
            self.is_generating_image = True
            self.last_image_request_time = time.time()
            processing_responses = [
                f"okee {username}, đang vẽ ảnh cho bạn nè, đợi tí nha",
                f"đã nhận yêu cầu, mình đang tạo ảnh cho {username} đây",
                f"đang xử lý ảnh cho {username}, chờ mình vài giây nhé",
            ]
            initial_response = random.choice(processing_responses)
            self.memory_store.save_turn(
                username, user_message, initial_response, short_limit=self.short_context_limit, save_long_term=False
            )
            self.stats["images_generated"] += 1
            return initial_response
        except Exception as exc:
            self.is_generating_image = False
            print(f"[CORE] ❌ Lỗi image request: {exc}")
            return f"sorry {username}, có lỗi khi khởi tạo yêu cầu tạo ảnh :("

    def handle_normal_message(self, user_message: str, username: str = "user") -> str:
        long_term_memories: List[str] = []
        try:
            long_term_memories = self.memory_store.search_memories(
                username, user_message, limit=min(5, self.long_memory_limit)
            )
            if long_term_memories:
                self.stats["memories_activated"] += 1
        except Exception as exc:
            print(f"[MEMORY] ⚠️ Lỗi truy xuất ký ức dài hạn: {exc}")

        short_lines: List[str] = []
        try:
            short_lines = self.memory_store.get_short_context_lines(
                username, limit=self.short_context_limit
            )
        except Exception as exc:
            print(f"[MEMORY] ⚠️ Lỗi truy xuất ngữ cảnh ngắn hạn: {exc}")

        prompt_sections: List[str] = []
        if long_term_memories:
            mem_block = "\n".join(f"- {item}" for item in long_term_memories[:3])
            prompt_sections.append(f"Ký ức liên quan trước đây với {username}:\n{mem_block}")
        if short_lines:
            hist_block = "\n".join(short_lines[-8:])
            prompt_sections.append(f"Cuộc trò chuyện gần đây:\n{hist_block}")

        prompt_sections.append(f"Tin nhắn mới từ {username}: {user_message}\nHãy trả lời tự nhiên:")
        contents = "\n\n".join(prompt_sections)

        gen_config = types.GenerateContentConfig(
            system_instruction=self.get_system_prompt(),
            temperature=float(self.config_manager.get("ai", "temperature", 0.7)),
            top_p=float(self.config_manager.get("ai", "top_p", 0.85)),
            top_k=int(self.config_manager.get("ai", "top_k", 40)),
            max_output_tokens=int(self.config_manager.get("ai", "max_tokens", 512)),
        )

        response = self._generate_content_with_retry(contents=contents, config=gen_config)
        raw_text = (getattr(response, "text", None) or "").strip()
        if not raw_text:
            raw_text = "mình nghe nè, bạn nói tiếp đi"

        ai_response = self.post_process_response(raw_text)

        try:
            self.memory_store.save_turn(
                username,
                user_message,
                ai_response,
                short_limit=self.short_context_limit,
                save_long_term=True,
            )
            self.short_context.save_to_shortContextMem(user_message, ai_response)
            self.stats["memories_written"] += 1
        except Exception as exc:
            print(f"[MEMORY] ⚠️ Lỗi lưu memory: {exc}")

        return ai_response

    def process_image_generation(self, description: str, username: str = "user") -> Dict[str, Any]:
        if not self.image_generator:
            self.is_generating_image = False
            return {
                "success": False,
                "error": "ImageGenerator chưa sẵn sàng",
                "response_text": f"sorry {username}, tính năng tạo ảnh đang tạm tắt",
            }
        try:
            result = self.image_generator.generate_image(description)
            result["response_text"] = self.image_generator.get_image_response_text(result, username)
            return result
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "response_text": f"sorry {username}, tạo ảnh gặp lỗi rồi :(",
            }
        finally:
            self.is_generating_image = False

    def post_process_response(self, response: str) -> str:
        """Chuẩn hóa câu trả lời: giữ nguyên dấu tiếng Việt, cắt gọn theo số từ và ranh giới câu."""
        if not response:
            return ""

        prompt_cfg = self.config_manager.get("ai", "prompt_settings", {}) or {}
        cleaned = " ".join(response.split()).strip()

        if prompt_cfg.get("strip_emoji", False):
            # Loại bỏ các ký tự ngoài BMP (emoji) nhưng bảo toàn toàn bộ chữ cái Unicode/tiếng Việt.
            cleaned = "".join(ch for ch in cleaned if ord(ch) <= 0xFFFF)
            cleaned = " ".join(cleaned.split())

        if prompt_cfg.get("lowercase", False):
            cleaned = cleaned.lower()

        max_words = int(prompt_cfg.get("max_response_words", 40) or 40)
        words = cleaned.split()
        if max_words > 0 and len(words) > max_words:
            truncated = " ".join(words[:max_words])
            # Ưu tiên ngắt ở dấu kết thúc câu gần cuối nếu đủ dài
            last_punct = max(
                truncated.rfind("."), truncated.rfind("!"), truncated.rfind("?")
            )
            if last_punct > len(truncated) // 2:
                cleaned = truncated[: last_punct + 1]
            else:
                cleaned = truncated.rstrip(" ,;:-") + "..."

        return cleaned

    def get_memory_stats(self, username: Optional[str] = None) -> Dict[str, Any]:
        sqlite_stats = self.memory_store.get_stats(user_id=username)
        image_stats = self.image_generator.get_stats() if self.image_generator else {}
        return {
            "total_messages": self.stats["total_messages"],
            "memories_activated": self.stats["memories_activated"],
            "memories_written": self.stats["memories_written"],
            "images_generated": self.stats["images_generated"],
            "short_context_length": sqlite_stats["short_context_count"],
            "long_memories_count": sqlite_stats["long_memories_count"],
            "uptime_minutes": (datetime.now() - self.stats["start_time"]).total_seconds() / 60.0,
            "image_generation_stats": image_stats,
            "is_generating_image": self.is_generating_image,
            "performance_stats": self.performance_monitor.get_current_stats(),
            "security_stats": self.security_manager.get_security_stats(),
            "analytics_stats": self.analytics_engine.get_conversation_trends(7),
        }

    def analyze_conversation_flow(self, username: str = "user") -> Any:
        lines = self.memory_store.get_short_context_lines(username, limit=20)
        if not lines:
            return "Chưa có cuộc trò chuyện nào"
        user_msgs = [m for m in lines if m.startswith("user:")]
        bot_msgs = [m for m in lines if m.startswith("bot:")]
        topics = [re.sub(r"^user:\s*", "", m)[:40] for m in user_msgs if len(m.split()) > 2]
        return {
            "conversation_length": len(lines),
            "user_messages": user_msgs,
            "bot_responses": bot_msgs,
            "topics_flow": topics,
        }

    def clear_short_memory(self, username: Optional[str] = None) -> None:
        self.memory_store.clear_short_context(user_id=username)
        self.short_context.context = []
        self.short_context.backup_short_context_writer()

    def get_related_memories(self, query: str, username: str = "user") -> List[str]:
        return self.memory_store.search_memories(username, query)


def create_insta_bot(
    api_key: Optional[str] = None,
    genai_client: Any = None,
    memory_store: Optional[SQLiteMemoryStore] = None,
) -> InstaBot:
    try:
        bot = InstaBot(api_key=api_key, genai_client=genai_client, memory_store=memory_store)
        notify_info("InstaBot instance created successfully", "factory")
        return bot
    except Exception as exc:
        notify_error(f"Failed to create InstaBot: {exc}", "factory")
        raise


def cleanup_insta_bot(bot: Optional[InstaBot]) -> None:
    if bot is None:
        return
    try:
        if hasattr(bot, "performance_monitor") and bot.performance_monitor:
            bot.performance_monitor.stop_monitoring()
            bot.performance_monitor.save_report()
        if hasattr(bot, "analytics_engine") and bot.analytics_engine:
            bot.analytics_engine.save_data()
            bot.analytics_engine.save_report()
        if hasattr(bot, "security_manager") and bot.security_manager:
            bot.security_manager.save_security_report()
        if hasattr(bot, "memory_store") and bot.memory_store:
            bot.memory_store.close()
        if hasattr(bot, "notification_system") and bot.notification_system:
            bot.notification_system.stop()
        notify_info("InstaBot cleanup completed", "cleanup")
    except Exception as exc:
        notify_error(f"Error during cleanup: {exc}", "cleanup")
