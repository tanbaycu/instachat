from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
import time
import os
import shutil
import threading
import random
import uuid
from core import create_insta_bot, cleanup_insta_bot

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv not installed, skip loading .env file
    pass

# Import các module mới
from monitoring.performance_monitor import get_performance_monitor
from monitoring.error_handler import get_error_handler, retry_on_error, ErrorSeverity
from security.security_manager import get_security_manager
from security.session_manager import get_session_manager
from analytics.analytics_engine import get_analytics_engine
from analytics.conversation_insights import get_conversation_insights
from utils.notification_system import notify_info, notify_warning, notify_error, notify_critical
from config.config_manager import get_config_manager


class LoginCreateSession:
    def __init__(self, username=None, password=None, target_username=None, user_temp_dir_path=None):
        self.username = username
        self.password = password
        self.user_temp_dir_path = user_temp_dir_path
        self.target_username = target_username
        
        # Khởi tạo các managers
        self.config_manager = get_config_manager()
        self.session_manager = get_session_manager()
        self.error_handler = get_error_handler()
        
        # Tạo hoặc load session
        self.session_name = f"session_{username}_{target_username}"
        self.setup_session()
        
        # Khởi tạo driver và login
        self.driver = self.driver_init()
        self.login()
        self.go_to_chat()

    def setup_session(self):
        """Setup session management"""
        try:
            # Tạo hoặc load session
            session_data = self.session_manager.get_session(self.session_name)
            if not session_data:
                self.session_manager.create_session(
                    self.username, 
                    self.password, 
                    self.target_username,
                    self.session_name
                )
                notify_info(f"Created new session: {self.session_name}", "session")
            else:
                notify_info(f"Loaded existing session: {self.session_name}", "session")
        except Exception as e:
            self.error_handler.log_error(e, "setup_session", ErrorSeverity.MEDIUM)
            notify_warning(f"Session setup error: {str(e)}", "session")

    @retry_on_error(max_attempts=3, exceptions=(Exception,))
    def driver_init(self):
        notify_info("Đang khởi tạo trình duyệt ảo...", "driver_init")

        # Tạo Chrome options từ config
        chrome_options = Options()
        chrome_config = self.config_manager.get('app', 'chrome_options', {})
        
        # Headless mode từ config
        if chrome_config.get('headless', True):
            chrome_options.add_argument("--headless=new")
        
        # Tạo unique temp directory cho profile
        import tempfile
        temp_dir = tempfile.mkdtemp(prefix="chrome_selenium_")
        chrome_options.add_argument(f"--user-data-dir={temp_dir}")
        
        # Lưu để cleanup sau
        self.temp_profile_dir = temp_dir
        
        # Thêm random port để tránh conflict khi chạy nhiều instance
        random_port = random.randint(9000, 9999)
        chrome_options.add_argument(f"--remote-debugging-port={random_port}")
        
        # Thêm các option từ config
        if chrome_config.get('no_sandbox', True):
            chrome_options.add_argument("--no-sandbox")
        if chrome_config.get('disable_dev_shm_usage', True):
            chrome_options.add_argument("--disable-dev-shm-usage")
        
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-software-rasterizer")
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-features=TranslateUI,VizDisplayCompositor")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-plugins")
        
        # Window size từ config
        window_size = chrome_config.get('window_size', '1920,1080')
        chrome_options.add_argument(f"--window-size={window_size}")
        
        # Các options khác
        chrome_options.add_argument("--no-first-run")
        chrome_options.add_argument("--no-default-browser-check")
        chrome_options.add_argument("--disable-default-apps")
        chrome_options.add_argument("--disable-sync")
        chrome_options.add_argument("--disable-translate")
        chrome_options.add_argument("--mute-audio")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        
        # User agent
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Prefs
        prefs = {
            "profile.default_content_setting_values": {
                "notifications": 2,
                "geolocation": 2,
                "media_stream": 2,
            }
        }
        chrome_options.add_experimental_option("prefs", prefs)

        print(f"[*] Đang tạo trình duyệt HEADLESS với debug port: {random_port}")
        print(f"[*] Temp profile: {temp_dir}")
        
        try:
            driver = webdriver.Chrome(options=chrome_options)
            notify_info("Trình duyệt đã khởi tạo thành công!", "driver_init")
            
            # Lưu thông tin driver vào session
            self.session_manager.update_session(self.session_name, {
                'chrome_profile_path': temp_dir,
                'status': 'driver_ready'
            })
            
            return driver
        except Exception as e:
            self.error_handler.log_error(e, "driver_init", ErrorSeverity.CRITICAL)
            notify_critical(f"Lỗi khi khởi tạo Chrome: {str(e)}", "driver_init")
            
            # Cleanup temp directory nếu failed
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
                
            notify_error("Thử các giải pháp sau:", "driver_init")
            notify_error("  1. Cài đặt Chrome browser mới nhất", "driver_init")
            notify_error("  2. Cập nhật Chrome driver", "driver_init")
            notify_error("  3. Restart máy tính", "driver_init")
            notify_error("  4. Chạy với quyền Administrator", "driver_init")
            raise
    
    
    @retry_on_error(max_attempts=3, exceptions=(Exception,))
    def login(self):
        notify_info("Đang đăng nhập...", "login")
        
        # Kiểm tra có thể đăng nhập không
        can_login, msg = self.session_manager.can_attempt_login(self.session_name)
        if not can_login:
            notify_error(f"Không thể đăng nhập: {msg}", "login")
            raise Exception(f"Login blocked: {msg}")
        
        notify_info("Đang truy cập Instagram...", "login")
        self.driver.get("https://www.instagram.com/")
        
        # Chờ page load với config timeout
        login_timeout = self.config_manager.get('app', 'instagram.login_timeout', 30)
        time.sleep(3)
        
        # Tìm username input
        try:
            username_input = WebDriverWait(self.driver, login_timeout).until(
                EC.presence_of_element_located((By.NAME, "username"))
            )
            username_input.clear()
            username_input.send_keys(self.username)
            notify_info("Đã nhập username", "login")
        except Exception as e:
            self.error_handler.log_error(e, "login_username", ErrorSeverity.HIGH)
            notify_error(f"Lỗi khi nhập username: {str(e)}", "login")
            self.session_manager.record_login_attempt(self.session_name, success=False)
            raise
        
        # Tìm password input  
        try:
            password_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, "password"))
            )
            password_input.clear()
            password_input.send_keys(self.password)
            notify_info("Đã nhập password", "login")
        except Exception as e:
            self.error_handler.log_error(e, "login_password", ErrorSeverity.HIGH)
            notify_error(f"Lỗi khi nhập password: {str(e)}", "login")
            self.session_manager.record_login_attempt(self.session_name, success=False)
            raise
        
        # Submit form
        try:
            password_input.send_keys(Keys.ENTER)
            notify_info("Đã submit form đăng nhập", "login")
        except Exception as e:
            self.error_handler.log_error(e, "login_submit", ErrorSeverity.HIGH)
            notify_error(f"Lỗi khi submit: {str(e)}", "login")
            self.session_manager.record_login_attempt(self.session_name, success=False)
            raise

        notify_info("Đang chờ kết quả đăng nhập...", "login")
        
        # Chờ một trong các element sau login xuất hiện
        login_success = False
        wait_time = login_timeout
        
        try:
            # Thử nhiều selector để detect login thành công
            success_indicators = [
                "//button[contains(text(), 'Save info') or contains(text(), 'Save Info')]",
                "//button[contains(text(), 'Not Now')]", 
                "//div[contains(@aria-label, 'Home')]",
                "//a[contains(@href, '/direct/')]",
                "//span[text()='Home']"
            ]
            
            for i, selector in enumerate(success_indicators):
                try:
                    print(f"[*] Kiểm tra indicator {i+1}: {selector[:30]}...")
                    element = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.XPATH, selector))
                    )
                    print(f"[*] Tìm thấy login indicator {i+1}!")
                    login_success = True
                    
                    # Nếu là Save Info button, click Not Now nếu có
                    if "Save info" in selector or "Save Info" in selector:
                        try:
                            not_now_btn = self.driver.find_element(By.XPATH, "//button[contains(text(), 'Not Now')]")
                            not_now_btn.click()
                            print("[*] Đã click 'Not Now' cho Save Info")
                        except:
                            pass
                    break
                except:
                    print(f"[!] Indicator {i+1} không tìm thấy")
                    continue
                    
            if login_success:
                notify_info('Đăng nhập thành công!', "login")
                self.session_manager.record_login_attempt(self.session_name, success=True)
            else:
                notify_error("Không thể xác nhận đăng nhập thành công", "login")
                self.session_manager.record_login_attempt(self.session_name, success=False)
                raise Exception("Login verification failed")
                
        except Exception as e:
            self.error_handler.log_error(e, "login_verification", ErrorSeverity.HIGH)
            notify_error(f"Timeout hoặc lỗi khi chờ login: {str(e)}", "login")
            
            # Kiểm tra có phải đang ở trang home không
            current_url = self.driver.current_url
            if "instagram.com" in current_url and ("feed" in current_url or current_url.endswith("instagram.com/")):
                notify_info("Có vẻ như đã đăng nhập thành công dựa trên URL", "login")
                login_success = True
                self.session_manager.record_login_attempt(self.session_name, success=True)
            else:
                self.session_manager.record_login_attempt(self.session_name, success=False)
                raise Exception(f"Login failed. Current URL: {current_url}")
        
        if not login_success:
            self.session_manager.record_login_attempt(self.session_name, success=False)
            raise Exception("Could not verify login success")
    

    def go_to_chat(self):
        print('[*] Đang chuyển đến trang chat...')
        print(f"[*] Đang truy cập trang của {self.target_username}...")
        self.driver.get(f"https://www.instagram.com/{self.target_username}")
        
        # Chờ trang load
        time.sleep(3)
        print("[*] Đang tìm nút Message...")
        
        # Thử nhiều cách tìm nút Message
        click_message_btn = None
        message_selectors = [
            "//div[contains(text(), 'Message')]",
            "//button[contains(text(), 'Message')]", 
            "//a[contains(text(), 'Message')]",
            "//div[@role='button' and contains(text(), 'Message')]",
            "//div[contains(@class, '_acan') and contains(text(), 'Message')]",
            "//div[contains(@class, '_ap30')]//div[contains(text(), 'Message')]",
            "//button[contains(@class, '_acan')]",
            "//div[@class='x1i10hfl xjqpnuy xa49m3k xqeqjp1 x2hbi6w x972fbf xcfux6l x1qhh985 xm0m39n xdl72j9 x2lah0s xe8uvvx xdj266r x11i5rnm xat24cr x1mh8g0r x2lwn1j xeuugli xexx8yu x18d9i69 x1hl2dhg xggy1nq x1ja2u2z x1t137rt x1q0g3np x1lku1pv x1a2a7pz x6s0dn4 xjyslct x1lq5wgf xgqcy7u x30kzoy x9jhf4c x1ejq31n xd10rxx x1sy0etr x17r0tee x9f619 x1ypdohk x78zum5 x1f6kntn xwhw2v2 x10w6t97 xl56j7k x17ydfre x1swvt13 x1pi30zi x1n2onr6 x2b8uid xlyipyv x87ps6o x14atkfc xcdnw81 x1i0vuye x1gjpkn9 x5n08af xsz8vos']"
        ]
        
        for i, selector in enumerate(message_selectors):
            try:
                print(f"[*] Thử selector {i+1}...")
                click_message_btn = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, selector))
                )
                print(f"[*] Tìm thấy nút Message với selector {i+1}!")
                break
            except:
                print(f"[!] Selector {i+1} không hoạt động")
                continue
        
        if click_message_btn:
            print("[*] Đang click nút Message...")
            try:
                click_message_btn.click()
                print("[*] Đã click nút Message thành công!")
            except:
                # Thử click bằng JavaScript
                print("[*] Thử click bằng JavaScript...")
                self.driver.execute_script("arguments[0].click();", click_message_btn)
                print("[*] Đã click nút Message bằng JavaScript!")
        else:
            print("[!] Không tìm thấy nút Message với tất cả selector!")
            # In ra source để debug
            print("[*] Đang in page source để debug...")
            page_source = self.driver.page_source
            if "Message" in page_source:
                print("[*] Từ 'Message' có trong page source")
            else:
                print("[!] Từ 'Message' KHÔNG có trong page source")
            return

        try:
            click_abandone_notify = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//button[contains(@class, '_a9--') and contains(@class, ' _ap36') and text()='Not Now']"))
            )
            click_abandone_notify.click()
            print("[*] Đã click bỏ qua notification")
        except:
            print("[!] Không có notification để bỏ qua")



class Listener(LoginCreateSession):
    def __init__(self, username=None, password=None, target_username=None, user_temp_dir_path=None):
        super().__init__(username, password, target_username, user_temp_dir_path)
        self.hist_message_input = ""
        self.current_message_input = ""
        self.message_inited = False
        
        # Hệ thống tracking tin nhắn mạnh mẽ
        self.processed_messages = set()  # Lưu message hash đã xử lý
        self.last_user_message = ""  # Tin nhắn cuối từ user
        self.last_user_message_time = 0  # Thời gian tin nhắn cuối từ user
        self.last_sent_message = ""  # Tin nhắn cuối bot gửi
        self.last_sent_time = 0  # Thời gian bot gửi cuối
        
        # Statistics
        self.total_messages_processed = 0
        self.duplicate_detections = 0
        
        self.listener_thread = threading.Thread(target=self.listener)
        self.listener_thread.start()

    def create_message_hash(self, message, window_minutes=2):
        """Tạo hash unique cho tin nhắn trong time window"""
        import hashlib
        # Sử dụng time window để tạo hash
        time_window = int(time.time() // (window_minutes * 60))
        hash_input = f"{message.strip()}_{time_window}"
        return hashlib.md5(hash_input.encode()).hexdigest()[:12]

    def is_bot_message(self, message):
        """Kiểm tra có phải tin nhắn của bot không - nhiều điều kiện"""
        current_time = time.time()
        
        # Check 1: Exact match với tin nhắn vừa gửi
        if (self.last_sent_message and message == self.last_sent_message and
            current_time - self.last_sent_time < 30):
            return True
            
        # Check 2: Partial match cho tin nhắn dài bị cắt
        if (self.last_sent_message and len(self.last_sent_message) > 30 and
            message in self.last_sent_message and 
            current_time - self.last_sent_time < 30):
            return True
            
        # Check 3: Reverse check - bot message có trong current message
        if (self.last_sent_message and len(message) > 30 and
            self.last_sent_message in message and 
            current_time - self.last_sent_time < 30):
            return True
            
        return False

    def is_duplicate_message(self, message):
        """Kiểm tra tin nhắn trùng lặp với multiple checks"""
        current_time = time.time()
        
        # Check 1: Message hash
        msg_hash = self.create_message_hash(message)
        if msg_hash in self.processed_messages:
            self.duplicate_detections += 1
            return True
            
        # Check 2: Same as last user message trong 60 giây
        if (message == self.last_user_message and 
            current_time - self.last_user_message_time < 60):
            self.duplicate_detections += 1
            return True
            
        # Check 3: Very similar message (typo protection)
        if (self.last_user_message and len(message) > 5 and
            abs(len(message) - len(self.last_user_message)) <= 2 and
            current_time - self.last_user_message_time < 30):
            # Simple similarity check
            common_chars = sum(1 for a, b in zip(message.lower(), self.last_user_message.lower()) if a == b)
            similarity = common_chars / max(len(message), len(self.last_user_message))
            if similarity > 0.85:
                self.duplicate_detections += 1
                return True
                
        return False

    def mark_message_processed(self, message):
        """Đánh dấu tin nhắn đã xử lý"""
        current_time = time.time()
        
        # Add hash to processed
        msg_hash = self.create_message_hash(message)
        self.processed_messages.add(msg_hash)
        
        # Update last user message
        self.last_user_message = message
        self.last_user_message_time = current_time
        
        # Clean old hashes (keep only last 100)
        if len(self.processed_messages) > 100:
            # Convert to list, remove first 20, convert back
            temp_list = list(self.processed_messages)
            self.processed_messages = set(temp_list[-80:])
            
        self.total_messages_processed += 1
        print(f"[TRACKER] 📝 Đã xử lý {self.total_messages_processed} tin nhắn, {self.duplicate_detections} duplicate")

    
    def init_first_message(self):
        print("[*] Đang khởi tạo để đọc tin nhắn...")
        messages = None
        
        # Chờ chat interface load
        time.sleep(2)
        
        # Thử nhiều selector để tìm tin nhắn
        message_selectors = [
            "//div[@role='none']//div[contains(@class, 'x126k92a')]",
            "//div[contains(@class, 'x1n2onr6')]//span",
            "//div[@data-scope='messages']//div",
            "//div[contains(@class, 'html-div')]",
            "//div[@class='html-div xexx8yu x4uap5 x18d9i69 xkhd6sd x1gslohp x11i5rnm x12nagc x1mh8g0r x1yc453h x126k92a x18lvrbx']",
            "//span[contains(@class, 'x1lliihq')]",
            "//div[contains(text(), 'hi') or contains(text(), 'Hi') or contains(text(), 'hello')]"
        ]
        
        for i, selector in enumerate(message_selectors):
            try:
                print(f"[*] Thử đọc tin nhắn với selector {i+1}...")
                messages = WebDriverWait(self.driver, 3).until(
                    EC.presence_of_all_elements_located((By.XPATH, selector))
                )
                if messages and len(messages) > 0:
                    initial_message = messages[-1].text
                    self.hist_message_input = initial_message
                    self.current_message_input = initial_message
                    
                    # Khởi tạo tracking cho tin nhắn đầu tiên
                    if initial_message.strip():
                        self.mark_message_processed(initial_message)
                        print(f"[*] Đã khởi tạo tin nhắn: '{initial_message[:50]}...'")
                    
                    self.message_inited = True
                    return
            except:
                print(f"[!] Selector {i+1} không hoạt động")
                continue
        
        print('[!] Không thể khởi tạo đọc tin nhắn với tất cả selector!')
        # Khởi tạo rỗng để không bị lỗi
        self.hist_message_input = ""
        self.current_message_input = ""
        self.message_inited = True


    def listener(self):
        self.init_first_message()
        print("[*] Bắt đầu lắng nghe tin nhắn...")
        
        message_selectors = [
            "//div[@role='none']//div[contains(@class, 'x126k92a')]",
            "//div[contains(@class, 'x1n2onr6')]//span",
            "//div[@data-scope='messages']//div",
            "//div[contains(@class, 'html-div')]",
            "//div[@class='html-div xexx8yu x4uap5 x18d9i69 xkhd6sd x1gslohp x11i5rnm x12nagc x1mh8g0r x1yc453h x126k92a x18lvrbx']",
            "//span[contains(@class, 'x1lliihq')]",
            "//div[contains(text(), 'hi') or contains(text(), 'Hi') or contains(text(), 'hello')]"
        ]
        
        retry_count = 0
        max_retries = 3
        
        while True:
            try:
                messages = None
                
                # Thử từng selector cho đến khi tìm được
                for i, selector in enumerate(message_selectors):
                    try:
                        messages = WebDriverWait(self.driver, 2).until(
                            EC.presence_of_all_elements_located((By.XPATH, selector))
                        )
                        if messages and len(messages) > 0:
                            break
                    except:
                        continue
                
                if not messages:
                    print('[!] Không thể đọc tin nhắn, thử lại...')
                    time.sleep(3)
                    retry_count += 1
                    if retry_count > max_retries:
                        print("[!] Quá nhiều lần thử, reset listener...")
                        retry_count = 0
                        time.sleep(10)
                    continue

                # Reset retry count khi thành công
                retry_count = 0
                
                # Kiểm tra tin nhắn mới với xử lý stale element
                latest_message = ""
                try:
                    # Lấy text từ element cuối cùng
                    if messages and len(messages) > 0:
                        latest_element = messages[-1]
                        latest_message = latest_element.text.strip() if latest_element.text else ""
                except Exception as e:
                    print(f"[DEBUG] Stale element hoặc lỗi đọc: {str(e)[:50]}")
                    time.sleep(1)
                    continue  # Bỏ qua và thử lại
                
                # LOGIC MỚI: Kiểm tra tin nhắn với comprehensive checks
                if latest_message and latest_message != self.hist_message_input:
                    
                    # Check 1: Có phải tin nhắn của bot không?
                    if self.is_bot_message(latest_message):
                        print(f"[DEBUG] Bot message detected: '{latest_message[:30]}...'")
                        self.hist_message_input = latest_message  # Update để không check lại
                        time.sleep(1)
                        continue
                    
                    # Check 2: Có phải duplicate không?
                    if self.is_duplicate_message(latest_message):
                        print(f"[DEBUG] Duplicate message: '{latest_message[:30]}...'")
                        self.hist_message_input = latest_message  # Update để không check lại
                        time.sleep(1)
                        continue
                    
                    # Tin nhắn mới hợp lệ
                    print(f"[DEBUG] Valid new message: '{latest_message[:50]}...'")
                    self.current_message_input = latest_message
                    self.hist_message_input = latest_message
                    time.sleep(1)
                
                time.sleep(1.5)  # Delay cho mỗi lần check
                
            except Exception as e:
                print(f"[!] Lỗi trong listener: {str(e)[:100]}")
                print("[*] Đang thử khôi phục listener...")
                time.sleep(5)
                continue


    def listen_new_message(self):
        """Simplified new message detection"""
        if (self.current_message_input != self.last_user_message and 
            self.message_inited and 
            self.current_message_input.strip()):
            
            new_message = self.current_message_input.strip()
            
            # Final safety check
            if self.is_duplicate_message(new_message):
                print(f"[DEBUG] Final duplicate check failed: '{new_message[:30]}...'")
                return None
            
            # Mark as processed
            self.mark_message_processed(new_message)
            
            print(f"[DEBUG] Confirmed new message: '{new_message[:50]}...'")
            return new_message
        else:
            return None
        



class Sender(Listener):
    def __init__(self, username=None, password=None, target_username=None, user_temp_dir_path=None):
        super().__init__(username, password, target_username, user_temp_dir_path)
    

    def send_message(self, text=None):
        text = text.replace("\n", " ")
        
        # Thử nhiều selector để tìm input box
        input_selectors = [
            "//div[@contenteditable='true' and @aria-label='Message']",
            "//div[@contenteditable='true']",
            "//div[@role='textbox']",
            "//textarea[@placeholder='Message...']",
            "//div[contains(@aria-label, 'Message')]"
        ]
        
        aria_input = None
        for i, selector in enumerate(input_selectors):
            try:
                print(f"[*] Thử tìm input box với selector {i+1}...")
                aria_input = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, selector))
                )
                print(f"[*] Tìm thấy input box với selector {i+1}!")
                break
            except:
                print(f"[!] Input selector {i+1} không hoạt động")
                continue
        
        if aria_input:
            try:
                aria_input.clear()
                aria_input.send_keys(text)
                aria_input.send_keys(Keys.ENTER)
                
                # Cập nhật tracking system cho tin nhắn bot
                self.last_sent_message = text
                self.last_sent_time = time.time()
                
                print(f"[*] Đã gửi tin nhắn: '{text}'")
                print(f"[TRACKER] 🤖 Bot sent: '{text[:30]}...' at {int(self.last_sent_time)}")
                
            except Exception as e:
                print(f"[!] Lỗi khi gửi tin nhắn: {str(e)}")
        else:
            print("[!] Không tìm thấy input box để gửi tin nhắn!")



class InstaChat(Sender):
    def __init__(self, username=None, password=None, target_username=None, user_temp_dir_path=None, gemini_api_key=None):
        super().__init__(username, password, target_username, user_temp_dir_path)
        
        # Khởi tạo các managers bổ sung
        self.performance_monitor = get_performance_monitor()
        self.analytics_engine = get_analytics_engine()
        self.conversation_insights = get_conversation_insights(self.analytics_engine)
        
        # Khởi tạo AI Bot với Memory System
        try:
            self.ai_bot = create_insta_bot(gemini_api_key)
            notify_info("🤖 AI Bot với Memory System đã sẵn sàng!", "ai_bot")
        except Exception as e:
            self.error_handler.log_error(e, "ai_bot_init", ErrorSeverity.CRITICAL)
            notify_critical(f"⚠️ Không thể khởi tạo AI Bot: {str(e)}", "ai_bot")
            notify_warning("🔄 Bot sẽ không hoạt động mà không có AI", "ai_bot")
            self.ai_bot = None
    
    def get_ai_response(self, message):
        """Lấy phản hồi từ AI và xử lý image generation"""
        if self.ai_bot:
            try:
                # Kiểm tra xem có phải image request không
                if (self.ai_bot.image_generator and 
                    self.ai_bot.image_generator.is_image_request(message)):
                    
                    print("[*] 🎨 Phát hiện yêu cầu tạo ảnh")
                    
                    # Gửi response ngay để user biết đang process
                    initial_response = self.ai_bot.generate_response(message, self.target_username)
                    
                    # Trigger background image generation
                    description = self.ai_bot.image_generator.extract_description(message)
                    
                    # Store image request để xử lý sau
                    self.pending_image_request = {
                        'description': description,
                        'username': self.target_username,
                        'timestamp': time.time()
                    }
                    
                    return initial_response
                else:
                    # Xử lý tin nhắn thường
                    return self.ai_bot.generate_response(message, self.target_username)
                    
            except Exception as e:
                print(f"[!] ❌ Lỗi AI: {str(e)}")
                return "uh sorry mình không hiểu"
        else:
            return "ai chưa sẵn sàng"

    def check_and_send_pending_image(self):
        """Kiểm tra và gửi ảnh đang pending"""
        if (hasattr(self, 'pending_image_request') and 
            self.pending_image_request and 
            not self.ai_bot.is_generating_image):
            
            try:
                print("[*] 🎨 Đang xử lý image generation...")
                
                # Process image generation
                result = self.ai_bot.process_image_generation(
                    self.pending_image_request['description'],
                    self.pending_image_request['username']
                )
                
                if result['success']:
                    print(f"[*] ✅ Image URL: {result['url']}")
                    
                    # Gửi URL thay vì upload file (đơn giản hơn)
                    image_message = f"{result['response_text']}\n{result['url']}"
                    self.send_message(image_message)
                    
                else:
                    print(f"[*] ❌ Image generation failed: {result.get('error', 'Unknown error')}")
                    self.send_message(result['response_text'])
                
                # Clear pending request
                self.pending_image_request = None
                
            except Exception as e:
                print(f"[!] ❌ Lỗi khi xử lý image: {str(e)}")
                self.send_message("sorry, tạo ảnh bị lỗi rồi :((")
                self.pending_image_request = None
    
    def cleanup(self):
        """Dọn dẹp trình duyệt và hiển thị memory stats"""
        try:
            notify_info("Đang dọn dẹp...", "cleanup")
            
            # Hiển thị tracking statistics
            notify_info("📊 Final Statistics:", "cleanup")
            notify_info(f"  - Total messages processed: {self.total_messages_processed}", "cleanup")
            notify_info(f"  - Duplicates blocked: {self.duplicate_detections}", "cleanup")
            notify_info(f"  - Processed hashes: {len(self.processed_messages)}", "cleanup")
            notify_info(f"  - Last user message: '{self.last_user_message[:30]}...' if self.last_user_message else 'None'", "cleanup")
            notify_info(f"  - Last bot message: '{self.last_sent_message[:30]}...' if self.last_sent_message else 'None'", "cleanup")
            
            # Hiển thị comprehensive statistics
            if self.ai_bot:
                stats = self.ai_bot.get_memory_stats()
                notify_info(f"📊 Comprehensive Stats: {stats}", "cleanup")
                
                # Phân tích conversation flow
                flow = self.ai_bot.analyze_conversation_flow()
                if flow != "Chưa có cuộc trò chuyện nào":
                    notify_info(f"🔄 Conversation Flow: {len(flow['topics_flow'])} chủ đề", "cleanup")
                
                # Cleanup AI bot
                cleanup_insta_bot(self.ai_bot)
            
            # Print summaries từ các systems
            self.performance_monitor.print_summary()
            self.error_handler.print_error_summary()
            self.security_manager.print_security_summary()
            
            # Đóng trình duyệt
            if hasattr(self, 'driver'):
                self.driver.quit()
                notify_info("Đã đóng trình duyệt", "cleanup")
                
            # Cleanup temp directory
            if hasattr(self, 'temp_profile_dir'):
                try:
                    shutil.rmtree(self.temp_profile_dir)
                    notify_info("Đã dọn dẹp temp directory", "cleanup")
                except:
                    pass
                
        except Exception as e:
            self.error_handler.log_error(e, "cleanup", ErrorSeverity.MEDIUM)
            notify_error(f"Lỗi khi dọn dẹp: {str(e)}", "cleanup")
    
    def debug_tracking_status(self):
        """Debug method to show current tracking status"""
        print(f"\n[DEBUG] 🔍 Tracking Status:")
        print(f"  - Messages processed: {self.total_messages_processed}")
        print(f"  - Duplicates detected: {self.duplicate_detections}")
        print(f"  - Hash cache size: {len(self.processed_messages)}")
        print(f"  - Last user msg: '{self.last_user_message[:40]}...' if self.last_user_message else 'None'")
        print(f"  - Last bot msg: '{self.last_sent_message[:40]}...' if self.last_sent_message else 'None'")
        current_time = time.time()
        if self.last_user_message_time > 0:
            print(f"  - User msg age: {current_time - self.last_user_message_time:.1f}s")
        if self.last_sent_time > 0:
            print(f"  - Bot msg age: {current_time - self.last_sent_time:.1f}s")
        print(f"  - Current input: '{self.current_message_input[:40]}...' if self.current_message_input else 'None'")
        print(f"  - Hist input: '{self.hist_message_input[:40]}...' if self.hist_message_input else 'None'")
        print()  # Blank line for readability




if __name__ == "__main__":
    instagram = None
    try:
        notify_info("Bắt đầu chương trình InstaChat...", "main")
        
        # Khởi tạo config manager
        config_manager = get_config_manager()
        
        # Lấy Gemini API key từ environment hoặc config
        gemini_api_key = os.getenv('GEMINI_API_KEY') or config_manager.get('ai', 'api_key')
        if not gemini_api_key:
            notify_error("⚠️ GEMINI_API_KEY không được tìm thấy!", "main")
            notify_info("💡 Hướng dẫn setup:", "main")
            notify_info("   1. Tạo file .env từ .env.example", "main")
            notify_info("   2. Hoặc set environment: set GEMINI_API_KEY=your_key", "main")
            notify_info("   3. Hoặc cấu hình trong config_manager.py", "main")
            raise Exception("Missing GEMINI_API_KEY")
            
        if not gemini_api_key:
            notify_warning("⚠️ Không tìm thấy GEMINI_API_KEY trong environment", "main")
            notify_info("💡 Bạn có thể:", "main")
            notify_info("   1. Set environment: set GEMINI_API_KEY=your_key", "main")
            notify_info("   2. Hoặc bot sẽ chạy ở chế độ cơ bản", "main")
        
        # Lấy thông tin login từ environment hoặc config
        app_config = config_manager.get('app', {})
        username = (os.getenv('INSTAGRAM_USERNAME') or 
                   app_config.get('instagram_username'))
        password = (os.getenv('INSTAGRAM_PASSWORD') or 
                   app_config.get('instagram_password'))
        target_username = (os.getenv('TARGET_USERNAME') or 
                          app_config.get('target_username'))
        
        # Kiểm tra thông tin bắt buộc
        if not username or not password or not target_username:
            notify_error("⚠️ Thiếu thông tin đăng nhập Instagram!", "main")
            notify_info("💡 Hướng dẫn setup:", "main")
            notify_info("   1. Tạo file .env từ .env.example", "main")
            notify_info("   2. Hoặc set environment variables:", "main")
            notify_info("      set INSTAGRAM_USERNAME=your_username", "main")
            notify_info("      set INSTAGRAM_PASSWORD=your_password", "main")
            notify_info("      set TARGET_USERNAME=target_user", "main")
            notify_info("   3. Hoặc cấu hình trong config_manager.py", "main")
            raise Exception("Missing Instagram credentials")
        
        instagram = InstaChat(
            username=username,
            password=password,
            target_username=target_username,
            user_temp_dir_path="./chromium_temp_data_dir",
            gemini_api_key=gemini_api_key
        )
        
        notify_info("Khởi tạo thành công! Bắt đầu lắng nghe tin nhắn...", "main")
        notify_info("Nhấn Ctrl+C để dừng chương trình", "main")
        
        consecutive_empty_count = 0  # Đếm số lần liên tiếp không có tin nhắn mới
        
        while True:
            new_message = instagram.listen_new_message()
            if new_message is not None:
                consecutive_empty_count = 0  # Reset counter
                notify_info(f"Tin nhắn mới từ {instagram.target_username}: '{new_message[:50]}...'", "main")
                
                # Sử dụng AI để tạo phản hồi
                notify_info("🤖 Đang tạo phản hồi bằng AI...", "main")
                ai_response = instagram.get_ai_response(new_message)
                
                notify_info(f"💬 Đang gửi: '{ai_response[:50]}...'", "main")
                instagram.send_message(ai_response)
                
                # Delay từ config
                message_delay = config_manager.get('app', 'message_delay', 3)
                time.sleep(message_delay)
                
                # Kiểm tra và xử lý pending image request
                if hasattr(instagram, 'pending_image_request') and instagram.pending_image_request:
                    notify_info("🎨 Có pending image request, đang xử lý...", "main")
                    time.sleep(2)  # Thêm delay trước khi process image
                    instagram.check_and_send_pending_image()
                    
            else:
                consecutive_empty_count += 1
                
                # Kiểm tra pending image request ngay cả khi không có tin nhắn mới
                if (hasattr(instagram, 'pending_image_request') and 
                    instagram.pending_image_request and 
                    instagram.ai_bot and
                    not instagram.ai_bot.is_generating_image):
                    notify_info("🎨 Processing pending image trong idle time...", "main")
                    instagram.check_and_send_pending_image()
                
                # Nếu không có tin nhắn mới trong thời gian dài, delay ít hơn
                idle_threshold = config_manager.get('app', 'idle_threshold', 20)
                if consecutive_empty_count > idle_threshold:
                    time.sleep(5)  # Delay lớn hơn khi không có hoạt động
                else:
                    time.sleep(3)  # Delay bình thường
            
    except KeyboardInterrupt:
        notify_info("\nNgười dùng dừng chương trình...", "main")
    except Exception as e:
        error_handler = get_error_handler()
        error_handler.log_error(e, "main", ErrorSeverity.CRITICAL)
        notify_critical(f"\nLỗi critical: {str(e)}", "main")
    finally:
        if instagram:
            instagram.cleanup()
        notify_info("Chương trình đã kết thúc!", "main")