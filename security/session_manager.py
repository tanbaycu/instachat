import json
import os
import time
import hashlib
import base64
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
import pickle


class SessionManager:
    def __init__(self, session_file="security/sessions.json", key_file="security/session.key"):
        self.session_file = session_file
        self.key_file = key_file
        self.sessions = {}
        self.current_session = None
        
        # Tạo thư mục nếu chưa có
        os.makedirs(os.path.dirname(session_file), exist_ok=True)
        
        # Khởi tạo encryption
        self.cipher = self._init_encryption()
        
        # Load sessions
        self.load_sessions()
        
        print("[SESSION] 🔐 Session Manager đã khởi tạo")

    def _init_encryption(self):
        """Khởi tạo encryption cho session data"""
        try:
            if os.path.exists(self.key_file):
                with open(self.key_file, 'rb') as f:
                    key = f.read()
            else:
                key = Fernet.generate_key()
                with open(self.key_file, 'wb') as f:
                    f.write(key)
            
            return Fernet(key)
        except Exception as e:
            print(f"[SESSION] ⚠️ Lỗi khởi tạo encryption: {str(e)}")
            return None

    def encrypt_data(self, data):
        """Mã hóa dữ liệu"""
        if not self.cipher:
            return data
        
        try:
            if isinstance(data, str):
                data = data.encode('utf-8')
            elif not isinstance(data, bytes):
                data = str(data).encode('utf-8')
            
            return self.cipher.encrypt(data).decode('utf-8')
        except Exception as e:
            print(f"[SESSION] ⚠️ Lỗi mã hóa: {str(e)}")
            return data

    def decrypt_data(self, encrypted_data):
        """Giải mã dữ liệu"""
        if not self.cipher:
            return encrypted_data
        
        try:
            if isinstance(encrypted_data, str):
                encrypted_data = encrypted_data.encode('utf-8')
            
            return self.cipher.decrypt(encrypted_data).decode('utf-8')
        except Exception as e:
            print(f"[SESSION] ⚠️ Lỗi giải mã: {str(e)}")
            return encrypted_data

    def create_session(self, username, password, target_username, session_name=None):
        """Tạo session mới"""
        if not session_name:
            session_name = f"session_{username}_{int(time.time())}"
        
        # Mã hóa thông tin nhạy cảm
        encrypted_password = self.encrypt_data(password)
        
        session_data = {
            'session_id': self.generate_session_id(),
            'username': username,
            'password': encrypted_password,  # Encrypted
            'target_username': target_username,
            'created_at': datetime.now().isoformat(),
            'last_used': datetime.now().isoformat(),
            'login_attempts': 0,
            'status': 'created',
            'cookies': None,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'chrome_profile_path': None,
            'last_activity': datetime.now().isoformat()
        }
        
        self.sessions[session_name] = session_data
        self.save_sessions()
        
        print(f"[SESSION] ✅ Session created: {session_name}")
        return session_name, session_data

    def generate_session_id(self):
        """Tạo session ID unique"""
        timestamp = str(int(time.time()))
        random_data = os.urandom(16)
        combined = timestamp + base64.b64encode(random_data).decode('utf-8')
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    def get_session(self, session_name):
        """Lấy session data"""
        if session_name not in self.sessions:
            return None
        
        session = self.sessions[session_name].copy()
        
        # Giải mã password
        if session.get('password'):
            session['password'] = self.decrypt_data(session['password'])
        
        return session

    def update_session(self, session_name, updates):
        """Cập nhật session"""
        if session_name not in self.sessions:
            return False
        
        # Mã hóa password nếu có trong updates
        if 'password' in updates:
            updates['password'] = self.encrypt_data(updates['password'])
        
        # Cập nhật last_used
        updates['last_used'] = datetime.now().isoformat()
        
        self.sessions[session_name].update(updates)
        self.save_sessions()
        
        return True

    def delete_session(self, session_name):
        """Xóa session"""
        if session_name in self.sessions:
            del self.sessions[session_name]
            self.save_sessions()
            print(f"[SESSION] 🗑️ Session deleted: {session_name}")
            return True
        return False

    def list_sessions(self):
        """Liệt kê tất cả sessions"""
        session_list = []
        for name, data in self.sessions.items():
            session_info = {
                'name': name,
                'username': data.get('username'),
                'target_username': data.get('target_username'),
                'created_at': data.get('created_at'),
                'last_used': data.get('last_used'),
                'status': data.get('status'),
                'login_attempts': data.get('login_attempts', 0)
            }
            session_list.append(session_info)
        
        return session_list

    def find_session_by_username(self, username):
        """Tìm session theo username"""
        for name, data in self.sessions.items():
            if data.get('username') == username:
                return name, data
        return None, None

    def is_session_expired(self, session_name, hours=24):
        """Kiểm tra session có hết hạn không"""
        if session_name not in self.sessions:
            return True
        
        session = self.sessions[session_name]
        last_used = datetime.fromisoformat(session.get('last_used', '1970-01-01'))
        expiry_time = last_used + timedelta(hours=hours)
        
        return datetime.now() > expiry_time

    def cleanup_expired_sessions(self, hours=24):
        """Dọn dẹp sessions hết hạn"""
        expired_sessions = []
        
        for name in list(self.sessions.keys()):
            if self.is_session_expired(name, hours):
                expired_sessions.append(name)
                del self.sessions[name]
        
        if expired_sessions:
            self.save_sessions()
            print(f"[SESSION] 🧹 Cleaned up {len(expired_sessions)} expired sessions")
        
        return expired_sessions

    def save_chrome_cookies(self, session_name, cookies):
        """Lưu Chrome cookies cho session"""
        if session_name not in self.sessions:
            return False
        
        try:
            # Serialize cookies
            cookies_data = pickle.dumps(cookies)
            encrypted_cookies = self.encrypt_data(cookies_data)
            
            self.sessions[session_name]['cookies'] = encrypted_cookies
            self.sessions[session_name]['last_activity'] = datetime.now().isoformat()
            
            self.save_sessions()
            return True
        except Exception as e:
            print(f"[SESSION] ⚠️ Lỗi lưu cookies: {str(e)}")
            return False

    def load_chrome_cookies(self, session_name):
        """Load Chrome cookies từ session"""
        if session_name not in self.sessions:
            return None
        
        try:
            encrypted_cookies = self.sessions[session_name].get('cookies')
            if not encrypted_cookies:
                return None
            
            cookies_data = self.decrypt_data(encrypted_cookies)
            cookies = pickle.loads(cookies_data)
            
            return cookies
        except Exception as e:
            print(f"[SESSION] ⚠️ Lỗi load cookies: {str(e)}")
            return None

    def record_login_attempt(self, session_name, success=False):
        """Ghi lại thử đăng nhập"""
        if session_name not in self.sessions:
            return False
        
        session = self.sessions[session_name]
        session['login_attempts'] = session.get('login_attempts', 0) + 1
        
        if success:
            session['status'] = 'active'
            session['last_successful_login'] = datetime.now().isoformat()
            session['login_attempts'] = 0  # Reset attempts on success
        else:
            session['status'] = 'login_failed'
            session['last_failed_login'] = datetime.now().isoformat()
        
        self.save_sessions()
        return True

    def can_attempt_login(self, session_name, max_attempts=3, cooldown_minutes=30):
        """Kiểm tra có thể thử đăng nhập không"""
        if session_name not in self.sessions:
            return False, "Session không tồn tại"
        
        session = self.sessions[session_name]
        attempts = session.get('login_attempts', 0)
        
        if attempts >= max_attempts:
            last_failed = session.get('last_failed_login')
            if last_failed:
                last_failed_time = datetime.fromisoformat(last_failed)
                cooldown_end = last_failed_time + timedelta(minutes=cooldown_minutes)
                
                if datetime.now() < cooldown_end:
                    remaining = cooldown_end - datetime.now()
                    return False, f"Còn {remaining.seconds//60} phút cooldown"
                else:
                    # Reset attempts after cooldown
                    session['login_attempts'] = 0
                    self.save_sessions()
        
        return True, ""

    def save_sessions(self):
        """Lưu sessions vào file"""
        try:
            with open(self.session_file, 'w', encoding='utf-8') as f:
                json.dump(self.sessions, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[SESSION] ⚠️ Lỗi lưu sessions: {str(e)}")

    def load_sessions(self):
        """Load sessions từ file"""
        try:
            if os.path.exists(self.session_file):
                with open(self.session_file, 'r', encoding='utf-8') as f:
                    self.sessions = json.load(f)
                print(f"[SESSION] 📂 Loaded {len(self.sessions)} sessions")
            else:
                self.sessions = {}
        except Exception as e:
            print(f"[SESSION] ⚠️ Lỗi load sessions: {str(e)}")
            self.sessions = {}

    def get_session_stats(self):
        """Lấy thống kê sessions"""
        total_sessions = len(self.sessions)
        active_sessions = sum(1 for s in self.sessions.values() if s.get('status') == 'active')
        failed_sessions = sum(1 for s in self.sessions.values() if s.get('status') == 'login_failed')
        
        return {
            'total_sessions': total_sessions,
            'active_sessions': active_sessions,
            'failed_sessions': failed_sessions,
            'success_rate': (active_sessions / max(1, total_sessions)) * 100
        }

    def print_session_summary(self):
        """In tóm tắt sessions"""
        stats = self.get_session_stats()
        
        print(f"\n[SESSION] 🔐 === SESSION SUMMARY ===")
        print(f"[SESSION] 📊 Total Sessions: {stats['total_sessions']}")
        print(f"[SESSION] ✅ Active Sessions: {stats['active_sessions']}")
        print(f"[SESSION] ❌ Failed Sessions: {stats['failed_sessions']}")
        print(f"[SESSION] 📈 Success Rate: {stats['success_rate']:.1f}%")
        
        if self.sessions:
            print(f"[SESSION] 📋 Recent Sessions:")
            for name, data in list(self.sessions.items())[-5:]:
                status = data.get('status', 'unknown')
                username = data.get('username', 'unknown')
                print(f"[SESSION]   - {name}: {username} ({status})")
        
        print(f"[SESSION] ================================\n")


# Singleton instance
_session_manager = None

def get_session_manager():
    """Lấy instance singleton của SessionManager"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager


if __name__ == "__main__":
    # Test session manager
    session_mgr = get_session_manager()
    
    # Test create session
    session_name, session_data = session_mgr.create_session(
        "test_user", 
        "test_password", 
        "target_user",
        "test_session"
    )
    
    # Test get session
    retrieved_session = session_mgr.get_session(session_name)
    print(f"Retrieved session: {retrieved_session['username']}")
    
    # Test login attempts
    session_mgr.record_login_attempt(session_name, success=True)
    
    # Test session stats
    session_mgr.print_session_summary()
    
    # Cleanup
    session_mgr.cleanup_expired_sessions(hours=0)  # Force cleanup for testing 