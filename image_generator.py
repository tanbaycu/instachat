import re
import time
from g4f.client import Client
import google.generativeai as genai
from datetime import datetime


class ImageGenerator:
    def __init__(self, gemini_api_key=None):
        """
        Khởi tạo ImageGenerator với AI phân tích và enhance prompt
        """
        self.client = Client()
        
        # Khởi tạo Gemini để enhance prompt
        if gemini_api_key:
            genai.configure(api_key=gemini_api_key)
            self.gemini_model = genai.GenerativeModel('gemini-2.0-flash')
        else:
            self.gemini_model = None
            
        # Từ khóa trigger tạo ảnh (tiếng Việt)
        self.image_triggers_vi = [
            'tạo ảnh', 'tạo hình', 'vẽ', 'vẽ cho', 'làm ảnh', 'sinh ảnh',
            'tạo ra ảnh', 'generate image', 'make image', 'create image',
            'draw', 'sketch', 'paint', 'design', 'tạo hình ảnh',
            'ảnh', 'hình', 'picture', 'image', 'photo', 'pic'
        ]
        
        # Từ khóa mô tả cần tạo ảnh
        self.description_patterns = [
            r'tạo ảnh (.+)',
            r'vẽ (.+)',
            r'làm ảnh (.+)',
            r'ảnh (.+)',
            r'hình (.+)',
            r'generate (.+)',
            r'create (.+)',
            r'draw (.+)',
            r'make (.+)',
        ]
        
        # Statistics
        self.stats = {
            'total_requests': 0,
            'successful_generations': 0,
            'failed_generations': 0,
            'start_time': datetime.now()
        }
        
        print("[IMAGE] ✅ ImageGenerator đã khởi tạo thành công")

    def is_image_request(self, message):
        """
        Phân tích tin nhắn xem có phải yêu cầu tạo ảnh không
        Logic cực kỳ mạnh với multiple checks
        """
        message_lower = message.lower().strip()
        
        # Check 1: Chứa từ khóa trigger trực tiếp
        for trigger in self.image_triggers_vi:
            if trigger in message_lower:
                print(f"[IMAGE] 🔍 Trigger detected: '{trigger}'")
                return True
        
        # Check 2: Pattern matching với regex
        for pattern in self.description_patterns:
            if re.search(pattern, message_lower):
                print(f"[IMAGE] 🔍 Pattern matched: '{pattern}'")
                return True
        
        # Check 3: AI-powered intent detection (nếu có Gemini)
        if self.gemini_model and len(message) > 10:
            try:
                intent_prompt = f"""
                Phân tích tin nhắn này xem người dùng có muốn tạo ảnh/hình không?
                Tin nhắn: "{message}"
                
                Trả lời chỉ: YES hoặc NO
                """
                response = self.gemini_model.generate_content(intent_prompt)
                ai_decision = response.text.strip().upper()
                
                if "YES" in ai_decision:
                    print(f"[IMAGE] 🤖 AI detected image intent")
                    return True
                    
            except Exception as e:
                print(f"[IMAGE] ⚠️ AI intent detection failed: {str(e)}")
        
        # Check 4: Context-based detection (câu hỏi về hình ảnh)
        context_keywords = ['như thế nào', 'trông ra sao', 'hình dáng', 'màu sắc', 'thiết kế']
        if any(keyword in message_lower for keyword in context_keywords):
            if any(visual in message_lower for visual in ['ảnh', 'hình', 'nhìn', 'thấy']):
                print(f"[IMAGE] 🔍 Context-based detection")
                return True
        
        return False

    def extract_description(self, message):
        """
        Trích xuất mô tả từ tin nhắn để tạo ảnh
        """
        message_clean = message.strip()
        
        # Thử extract bằng pattern matching
        for pattern in self.description_patterns:
            match = re.search(pattern, message.lower())
            if match:
                description = match.group(1).strip()
                if description:
                    print(f"[IMAGE] 📝 Extracted: '{description}'")
                    return description
        
        # Nếu không match pattern, loại bỏ trigger words và lấy phần còn lại
        message_lower = message.lower()
        for trigger in self.image_triggers_vi:
            if trigger in message_lower:
                # Tìm vị trí trigger và lấy phần sau
                start_idx = message_lower.find(trigger)
                if start_idx != -1:
                    description = message[start_idx + len(trigger):].strip()
                    # Loại bỏ các từ liên kết
                    description = re.sub(r'^(của|cho|về|một|cái|chiếc)\s+', '', description)
                    if description:
                        print(f"[IMAGE] 📝 Extracted after trigger: '{description}'")
                        return description
        
        # Fallback: trả về toàn bộ tin nhắn
        print(f"[IMAGE] 📝 Using full message: '{message}'")
        return message

    def enhance_prompt(self, description):
        """
        Enhance prompt để tạo ảnh chất lượng cao
        Chuyển tiếng Việt sang tiếng Anh và thêm detail
        """
        try:
            if self.gemini_model:
                enhance_prompt = f"""
                Enhance prompt này để tạo ảnh AI chất lượng cao:
                Input: "{description}"
                
                Yêu cầu:
                1. Chuyển sang tiếng Anh nếu là tiếng Việt
                2. Thêm chi tiết về style, lighting, quality
                3. Tối ưu cho AI art generation
                4. Ngắn gọn nhưng đầy đủ thông tin
                5. Professional prompt format
                
                Chỉ trả về enhanced prompt, không giải thích:
                """
                
                response = self.gemini_model.generate_content(enhance_prompt)
                enhanced = response.text.strip()
                
                # Clean up response
                enhanced = re.sub(r'^["\'`]|["\'`]$', '', enhanced)  # Remove quotes
                enhanced = enhanced.replace('\n', ' ').strip()
                
                print(f"[IMAGE] ✨ Enhanced: '{enhanced}'")
                return enhanced
                
            else:
                # Fallback enhancement without AI
                enhanced = self.basic_enhance(description)
                print(f"[IMAGE] ✨ Basic enhanced: '{enhanced}'")
                return enhanced
                
        except Exception as e:
            print(f"[IMAGE] ⚠️ Enhancement failed: {str(e)}")
            return self.basic_enhance(description)

    def basic_enhance(self, description):
        """
        Basic prompt enhancement without AI
        """
        # Translate common Vietnamese terms
        vi_to_en = {
            'mèo': 'cat', 'chó': 'dog', 'người': 'person', 'cô gái': 'girl',
            'chàng trai': 'boy', 'phong cảnh': 'landscape', 'thành phố': 'city',
            'biển': 'ocean', 'núi': 'mountain', 'hoa': 'flower', 'cây': 'tree',
            'ô tô': 'car', 'nhà': 'house', 'đẹp': 'beautiful', 'xinh': 'pretty',
            'lớn': 'big', 'nhỏ': 'small', 'đỏ': 'red', 'xanh': 'blue',
            'vàng': 'yellow', 'trắng': 'white', 'đen': 'black'
        }
        
        enhanced = description.lower()
        for vi, en in vi_to_en.items():
            enhanced = enhanced.replace(vi, en)
        
        # Add quality modifiers
        if 'high quality' not in enhanced and '4k' not in enhanced:
            enhanced += ', high quality, detailed, professional'
            
        return enhanced

    def generate_image(self, description):
        """
        Generate image từ description với error handling
        """
        try:
            self.stats['total_requests'] += 1
            print(f"[IMAGE] 🎨 Đang tạo ảnh với prompt: '{description}'")
            
            # Enhance prompt trước khi tạo
            enhanced_prompt = self.enhance_prompt(description)
            
            # Generate image với g4f
            response = self.client.images.generate(
                model="flux",
                prompt=enhanced_prompt,
                response_format="url"
            )
            
            if response and response.data and len(response.data) > 0:
                image_url = response.data[0].url
                self.stats['successful_generations'] += 1
                print(f"[IMAGE] ✅ Tạo ảnh thành công: {image_url}")
                return {
                    'success': True,
                    'url': image_url,
                    'original_prompt': description,
                    'enhanced_prompt': enhanced_prompt
                }
            else:
                raise Exception("No image data returned")
                
        except Exception as e:
            self.stats['failed_generations'] += 1
            print(f"[IMAGE] ❌ Lỗi tạo ảnh: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'original_prompt': description
            }

    def get_image_response_text(self, result, user_name="bạn"):
        """
        Tạo text response phù hợp với kết quả tạo ảnh
        """
        if result['success']:
            responses = [
                f"đây nè {user_name}, tui vừa tạo ảnh xong :))",
                f"ảnh của {user_name} đây, check thử nhé :vv",
                f"tạo xong rồi {user_name}, hy vọng {user_name} thích :))",
                f"done ảnh rồi nè, {user_name} xem sao :D",
                f"fresh ảnh mới toanh cho {user_name} :))"
            ]
            import random
            return random.choice(responses)
        else:
            error_responses = [
                f"sorry {user_name}, tạo ảnh bị lỗi rồi :(((",
                f"ôi không, tạo ảnh failed rồi {user_name} :((", 
                f"hụt, lỗi tạo ảnh rồi {user_name} :vv",
                f"tạo ảnh không được {user_name} ơi, thử lại nhé :(("
            ]
            import random
            return random.choice(error_responses)

    def get_stats(self):
        """
        Lấy thống kê image generation
        """
        uptime = (datetime.now() - self.stats['start_time']).total_seconds() / 60
        return {
            'total_requests': self.stats['total_requests'],
            'successful_generations': self.stats['successful_generations'],
            'failed_generations': self.stats['failed_generations'],
            'success_rate': (self.stats['successful_generations'] / max(1, self.stats['total_requests'])) * 100,
            'uptime_minutes': uptime
        }

    def is_processing_image(self):
        """
        Kiểm tra xem có đang process image không
        Để block tin nhắn khác trong lúc tạo ảnh
        """
        # Có thể implement logic phức tạp hơn nếu cần
        return False


# Test function
def test_image_generator():
    """
    Test ImageGenerator functionality
    """
    print("[TEST] 🧪 Testing ImageGenerator...")
    
    try:
        # Khởi tạo generator (cần API key thật để test enhancement)
        generator = ImageGenerator()
        
        test_messages = [
            "tạo ảnh con mèo",
            "vẽ phong cảnh đẹp",
            "làm ảnh một cô gái xinh",
            "generate a beautiful sunset",
            "hello how are you",  # Không phải image request
            "ảnh của một chiếc ô tô đỏ"
        ]
        
        for msg in test_messages:
            print(f"\n[TEST] Testing: '{msg}'")
            is_request = generator.is_image_request(msg)
            print(f"[TEST] Is image request: {is_request}")
            
            if is_request:
                description = generator.extract_description(msg)
                print(f"[TEST] Description: '{description}'")
                
                enhanced = generator.basic_enhance(description)
                print(f"[TEST] Enhanced: '{enhanced}'")
        
        # Stats
        stats = generator.get_stats()
        print(f"\n[TEST] Stats: {stats}")
        
    except Exception as e:
        print(f"[TEST] ❌ Error: {str(e)}")


if __name__ == "__main__":
    test_image_generator() 