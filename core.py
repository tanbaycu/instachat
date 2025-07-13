import google.generativeai as genai
import os
import time
import json
from datetime import datetime
from llm_memories_manager import ActivateLocalMemories, ShortContextManager, WriteNewLocalMemories
from image_generator import ImageGenerator

# Import các module mới
from monitoring.performance_monitor import get_performance_monitor, measure_response_time
from monitoring.error_handler import get_error_handler, log_errors, ErrorSeverity
from security.security_manager import get_security_manager, security_check
from analytics.analytics_engine import get_analytics_engine
from utils.cache_manager import get_response_cache, get_image_cache
from utils.notification_system import get_notification_system, notify_info, notify_warning, notify_error
from config.config_manager import get_config_manager


class InstaBot:
    def __init__(self, api_key=None):
        """
        Khởi tạo InstaBot với Gemini AI, Memory Management System và Image Generator
        """
        # Khởi tạo config manager
        self.config_manager = get_config_manager()
        
        # Khởi tạo monitoring
        self.performance_monitor = get_performance_monitor()
        self.error_handler = get_error_handler()
        
        # Khởi tạo security
        self.security_manager = get_security_manager()
        
        # Khởi tạo analytics
        self.analytics_engine = get_analytics_engine()
        
        # Khởi tạo cache
        self.response_cache = get_response_cache()
        self.image_cache = get_image_cache()
        
        # Khởi tạo notification
        self.notification_system = get_notification_system()
        
        # Bắt đầu monitoring
        self.performance_monitor.start_monitoring()
        notify_info("InstaBot khởi tạo thành công", "startup")
        
        if api_key:
            genai.configure(api_key=api_key)
        else:
            # Đọc từ environment variable hoặc config
            api_key = os.getenv('GEMINI_API_KEY') or self.config_manager.get('ai', 'api_key')
            if not api_key:
                raise ValueError("Cần GEMINI_API_KEY trong environment hoặc truyền api_key parameter")
            genai.configure(api_key=api_key)
        
        # Khởi tạo model với config
        model_name = self.config_manager.get('ai', 'model', 'gemini-2.5-flash-lite-preview-06-17')
        self.model = genai.GenerativeModel(model_name)
        
        # Khởi tạo Image Generator
        try:
            self.image_generator = ImageGenerator(gemini_api_key=api_key)
            print("[CORE] ✅ ImageGenerator đã được tích hợp")
        except Exception as e:
            print(f"[CORE] ⚠️ ImageGenerator init failed: {str(e)}")
            self.image_generator = None
        
        # Khởi tạo Memory Management System với config
        memory_config = self.config_manager.get('ai', 'memory_settings', {})
        self.local_memories = ActivateLocalMemories(
            limit_mem_storage=memory_config.get('long_memory_limit', 12)
        )
        self.short_context = ShortContextManager(
            s="user: ", 
            t="bot: ", 
            max_limit_short_mem_contxt=memory_config.get('short_context_limit', 10)
        )
        self.memory_writer = WriteNewLocalMemories(
            max_mem_context_towrite=memory_config.get('memory_write_threshold', 16),
            s="user: ",
            t="bot: "
        )
        
        # Thống kê
        self.stats = {
            'total_messages': 0,
            'start_time': datetime.now(),
            'last_message_time': None,
            'memories_activated': 0,
            'memories_written': 0,
            'images_generated': 0
        }
        
        # Image processing state
        self.is_generating_image = False
        self.last_image_request_time = 0
        
        print("[CORE] ✅ InstaBot với Memory System và ImageGenerator đã khởi tạo thành công")

    def safe_write_memory(self, user_message, ai_response):
        """Safe wrapper cho memory writer để tránh list index out of range"""
        try:
            self.memory_writer.write_newLocalMem(user_message, ai_response)
            return True
        except IndexError as e:
            print(f"[MEMORY] ⚠️ Index error trong memory writer: {str(e)}")
            # Reset context nếu bị lỗi index
            try:
                self.memory_writer.CONTEXT = []
                self.memory_writer.backup_contxt_writer()
                print("[MEMORY] 🔄 Đã reset memory writer context")
            except:
                pass
            return False
        except Exception as e:
            print(f"[MEMORY] ⚠️ Lỗi khác trong memory writer: {str(e)}")
            return False

    def get_system_prompt(self):
        """
        prompt để bot có thể phản hồi theo ý của bạn 
        """
        return """nhập prompt của bạn ở đây."""

    @measure_response_time
    @log_errors(severity=ErrorSeverity.HIGH, context="generate_response")
    def generate_response(self, user_message, username="user"):
        """
        Tạo phản hồi với Memory System, Context Analysis và Image Generation
        """
        try:
            # SECURITY: Validate message trước khi xử lý
            is_valid, error_msg = self.security_manager.validate_message(user_message, username)
            if not is_valid:
                notify_warning(f"Message rejected: {error_msg}", "security")
                return "tin nhắn không hợp lệ, vui lòng thử lại"
            
            # CACHE: Kiểm tra cached response
            cached_response = self.response_cache.get_cached_response(user_message, username)
            if cached_response:
                notify_info("Sử dụng cached response", "cache")
                return cached_response
            
            # Cập nhật stats
            self.stats['total_messages'] += 1
            self.stats['last_message_time'] = datetime.now()
            
            # PRIORITY 1: Kiểm tra xem có đang tạo ảnh không
            current_time = time.time()
            if self.is_generating_image:
                if current_time - self.last_image_request_time < 30:  # 30 giây timeout
                    return "đang tạo ảnh nè, chờ tí :vv"
                else:
                    # Reset state nếu quá lâu
                    self.is_generating_image = False
                    notify_warning("Reset image generation state due to timeout", "image_generation")
            
            # PRIORITY 2: Kiểm tra có phải image request không
            if self.image_generator and self.image_generator.is_image_request(user_message):
                return self.handle_image_request(user_message, username)
            
            # PRIORITY 3: Xử lý tin nhắn thường với memory system
            response = self.handle_normal_message(user_message, username)
            
            # CACHE: Lưu response vào cache
            self.response_cache.cache_response(user_message, response, username)
            
            # ANALYTICS: Ghi lại conversation
            response_time = time.time() - current_time
            self.analytics_engine.record_conversation(user_message, response, username, response_time)
            
            return response
            
        except Exception as e:
            self.error_handler.log_error(e, "generate_response", ErrorSeverity.HIGH, user_message)
            notify_error(f"Lỗi khi tạo phản hồi: {str(e)}", "generate_response")
            
            # Fallback phù hợp với context
            fallback_responses = [
                "uh lag quá",
                "mình không hiểu", 
                "hả",
                "ờ",
                "sao zạ",
                "sorry mình lag"
            ]
            import random
            return random.choice(fallback_responses)

    def handle_image_request(self, user_message, username="user"):
        """
        Xử lý yêu cầu tạo ảnh
        """
        try:
            print(f"[CORE] 🎨 Phát hiện yêu cầu tạo ảnh từ {username}")
            
            # Set image generation state
            self.is_generating_image = True
            self.last_image_request_time = time.time()
            
            # Extract description
            description = self.image_generator.extract_description(user_message)
            
            # Tạo response ngay để user biết đang process
            processing_responses = [
                f"okee {username}, đang tạo ảnh cho bạn nè :))",
                f"roger {username}, tui đang vẽ ảnh :vv",
                f"đang process ảnh cho {username}, chờ tí nha :))",
                f"okk đang tạo ảnh ngay {username} :D"
            ]
            import random
            initial_response = random.choice(processing_responses)
            
            # Lưu vào memory (chỉ initial response)
            try:
                self.short_context.save_to_shortContextMem(user_message, initial_response)
                if self.safe_write_memory(user_message, initial_response):
                    self.stats['memories_written'] += 1
            except Exception as e:
                print(f"[MEMORY] ⚠️ Lỗi khi lưu memory cho image request: {str(e)}")
            
            # Stats
            self.stats['images_generated'] += 1
            
            return initial_response
            
        except Exception as e:
            print(f"[CORE] ❌ Lỗi khi xử lý image request: {str(e)}")
            self.is_generating_image = False
            return f"sorry {username}, có lỗi khi tạo ảnh :(("

    def handle_normal_message(self, user_message, username="user"):
        """
        Xử lý tin nhắn thường với memory system
        """
        # 1. Kích hoạt Local Memories dựa trên similarity - với error handling
        long_term_memories = None
        try:
            long_term_memories = self.local_memories.activate_localMemories(user_message)
            if long_term_memories and len(long_term_memories) > 0:
                self.stats['memories_activated'] += 1
                print(f"[MEMORY] 🧠 Kích hoạt {len(long_term_memories)} ký ức liên quan")
        except Exception as e:
            print(f"[MEMORY] ⚠️ Lỗi khi load ký ức: {str(e)}")
            long_term_memories = None
        
        # 2. Lấy Short Context (ngữ cảnh ngắn hạn) - với error handling
        short_context = None
        try:
            short_context = self.short_context.activate_shortContetxMem()
            if short_context and str(short_context) == "[]":
                short_context = None
        except Exception as e:
            print(f"[MEMORY] ⚠️ Lỗi khi load context: {str(e)}")
            short_context = None
        
        # 3. Xây dựng prompt với nhiều luồng dữ liệu - safe approach
        memory_context = ""
        if long_term_memories and len(long_term_memories) > 0:
            memory_context += "\nký ức từ trước:\n"
            # Safe slicing để tránh lỗi index
            safe_memories = long_term_memories[:min(3, len(long_term_memories))]
            for memory in safe_memories:
                if memory and memory.strip():
                    memory_context += f"- {memory}\n"
        
        conversation_context = ""
        if short_context and len(short_context) > 0:
            conversation_context += "\ncuộc trò chuyện gần đây:\n"
            # Safe slicing để tránh lỗi index
            safe_context = short_context[-min(6, len(short_context)):]
            for context in safe_context:
                if context and context.strip():
                    conversation_context += f"{context}\n"
        
        # 4. Tạo prompt hoàn chỉnh ngắn gọn
        full_prompt = f"""{self.get_system_prompt()}
{memory_context}
{conversation_context}
tin nhắn: {user_message}

trả lời:"""

        print(f"[CORE] 🤔 Đang phân tích tin nhắn: '{user_message[:30]}...'")
        
        # 5. Gọi Gemini AI với config từ config manager
        generation_config = {
            'temperature': self.config_manager.get('ai', 'temperature', 0.7),
            'top_p': self.config_manager.get('ai', 'top_p', 0.8),
            'top_k': self.config_manager.get('ai', 'top_k', 70),
            'max_output_tokens': self.config_manager.get('ai', 'max_tokens', 1024),
        }
        
        response = self.model.generate_content(
            full_prompt,
            generation_config=generation_config
        )
        ai_response = response.text.strip()
        
        # 6. Post-processing để đảm bảo ngắn gọn và tự nhiên
        ai_response = self.post_process_response(ai_response)
        
        # 7. Kiểm tra độ dài - nếu quá dài thì cắt
        words = ai_response.split()
        if len(words) > 25:  # Nếu quá 25 từ
            ai_response = ' '.join(words[:20]) + "..."
        
        # 8. Lưu vào Memory Systems - với safe error handling
        try:
            # Lưu vào short context
            self.short_context.save_to_shortContextMem(user_message, ai_response)
            
            # Lưu vào long term memory với safe wrapper
            if self.safe_write_memory(user_message, ai_response):
                self.stats['memories_written'] += 1
                print(f"[MEMORY] 💾 Đã lưu vào memory systems")
            else:
                print(f"[MEMORY] ⚠️ Lưu memory thất bại nhưng bot vẫn hoạt động")
                
        except Exception as e:
            print(f"[MEMORY] ⚠️ Lỗi khi lưu short context: {str(e)}")
        
        print(f"[CORE] ✅ Phản hồi: '{ai_response}'")
        
        return ai_response

    def process_image_generation(self, description, username="user"):
        """
        Xử lý tạo ảnh trong background (có thể dùng threading)
        Trả về result để main app gửi ảnh
        """
        try:
            print(f"[CORE] 🎨 Bắt đầu tạo ảnh: '{description}'")
            
            # Generate image
            result = self.image_generator.generate_image(description)
            
            # Reset state
            self.is_generating_image = False
            
            # Return result với response text
            if result['success']:
                result['response_text'] = self.image_generator.get_image_response_text(result, username)
                print(f"[CORE] ✅ Tạo ảnh thành công cho {username}")
            else:
                result['response_text'] = self.image_generator.get_image_response_text(result, username)
                print(f"[CORE] ❌ Tạo ảnh thất bại cho {username}")
            
            return result
            
        except Exception as e:
            print(f"[CORE] ❌ Lỗi critical trong image generation: {str(e)}")
            self.is_generating_image = False
            return {
                'success': False,
                'error': str(e),
                'response_text': f"sorry {username}, có lỗi nghiêm trọng khi tạo ảnh :(("
            }

    def post_process_response(self, response):
        """
        Chỉ xử lý cơ bản - loại bỏ emoji và lowercase
        """
        import re
        
        # Chỉ loại bỏ emoji và ký tự đặc biệt
        cleaned_text = re.sub(r'[^\w\s\.\!\?\,\-\'\"]', '', response)
        cleaned_text = ''.join(char for char in cleaned_text if ord(char) < 127 or char.isalpha())
        
        # Chuyển về lowercase
        cleaned_text = cleaned_text.lower()
        
        return cleaned_text.strip()

    def get_memory_stats(self):
        """
        Lấy thống kê về memory system và image generation
        """
        memories_count = 0
        memories_dir = "./memories"
        if os.path.exists(memories_dir):
            memories_count = len([f for f in os.listdir(memories_dir) if f.endswith('.txt')])
        
        # Image stats
        image_stats = {}
        if self.image_generator:
            image_stats = self.image_generator.get_stats()
        
        # Performance stats
        performance_stats = self.performance_monitor.get_current_stats()
        
        # Security stats
        security_stats = self.security_manager.get_security_stats()
        
        # Analytics stats
        analytics_stats = self.analytics_engine.get_conversation_trends(7)
        
        return {
            'total_messages': self.stats['total_messages'],
            'memories_activated': self.stats['memories_activated'],
            'memories_written': self.stats['memories_written'],
            'images_generated': self.stats['images_generated'],
            'total_memory_files': memories_count,
            'short_context_length': len(self.short_context.context) if self.short_context.context else 0,
            'uptime_minutes': (datetime.now() - self.stats['start_time']).total_seconds() / 60,
            'image_generation_stats': image_stats,
            'is_generating_image': self.is_generating_image,
            'performance_stats': performance_stats,
            'security_stats': security_stats,
            'analytics_stats': analytics_stats
        }

    def analyze_conversation_flow(self):
        """
        Phân tích luồng cuộc trò chuyện cho cái nhìn trực quan
        """
        short_context = self.short_context.activate_shortContetxMem()
        if not short_context:
            return "Chưa có cuộc trò chuyện nào"
        
        analysis = {
            'conversation_length': len(short_context),
            'user_messages': [msg for msg in short_context if msg.startswith('user:')],
            'bot_responses': [msg for msg in short_context if msg.startswith('bot:')],
            'topics_flow': []
        }
        
        # Phân tích chủ đề
        for msg in analysis['user_messages']:
            clean_msg = msg.replace('user:', '').strip()
            if len(clean_msg.split()) > 2:
                analysis['topics_flow'].append(clean_msg[:30] + "...")
        
        return analysis

    def clear_short_memory(self):
        """
        Xóa memory ngắn hạn
        """
        self.short_context.context = []
        self.short_context.backup_short_context_writer()
        print("[MEMORY] 🗑️ Đã xóa ngữ cảnh ngắn hạn")

    def get_related_memories(self, query):
        """
        Tìm ký ức liên quan đến query
        """
        return self.local_memories.activate_localMemories(query)


# Factory function
def create_insta_bot(api_key=None):
    """
    Tạo InstaBot instance với Memory Management
    """
    try:
        bot = InstaBot(api_key=api_key)
        notify_info("InstaBot instance created successfully", "factory")
        return bot
    except Exception as e:
        notify_error(f"Failed to create InstaBot: {str(e)}", "factory")
        raise

def cleanup_insta_bot(bot):
    """
    Cleanup function để dọn dẹp InstaBot
    """
    try:
        if hasattr(bot, 'performance_monitor'):
            bot.performance_monitor.stop_monitoring()
            bot.performance_monitor.save_report()
        
        if hasattr(bot, 'analytics_engine'):
            bot.analytics_engine.save_data()
            bot.analytics_engine.save_report()
        
        if hasattr(bot, 'security_manager'):
            bot.security_manager.save_security_report()
        
        if hasattr(bot, 'notification_system'):
            bot.notification_system.stop()
        
        notify_info("InstaBot cleanup completed", "cleanup")
        
    except Exception as e:
        notify_error(f"Error during cleanup: {str(e)}", "cleanup")


# Test function với memory analysis
def test_bot():
    """
    Test bot với memory system
    """
    print("[TEST] 🧪 Testing InstaBot với Memory System...")
    
    try:
        bot = create_insta_bot()
        
        test_messages = [
            "hi tôi tên tân",
            "tôi ở hà nội", 
            "bạn có nhớ tên tôi không?",
            "tôi ở đâu nhỉ?"
        ]
        
        for i, msg in enumerate(test_messages):
            print(f"\n[TEST] Round {i+1}")
            print(f"User: {msg}")
            response = bot.generate_response(msg, "testuser")
            print(f"Bot: {response}")
            
            # Hiển thị memory stats
            if i > 0:
                stats = bot.get_memory_stats()
                print(f"Memory Stats: {stats}")
            
            time.sleep(1)
        
        # Phân tích conversation flow
        print(f"\n[ANALYSIS] 📊 Conversation Flow:")
        flow = bot.analyze_conversation_flow()
        print(flow)
        
    except Exception as e:
        print(f"[TEST] ❌ Cần GEMINI_API_KEY để test: {str(e)}")


if __name__ == "__main__":
    test_bot() 