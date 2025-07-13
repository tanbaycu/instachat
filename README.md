# 🤖 InstaChat - Bot Instagram AI Thông Minh Tự Động

[![GitHub Stars](https://img.shields.io/github/stars/tanbaycu/instachat?style=social)](https://github.com/tanbaycu/instachat)
[![GitHub Forks](https://img.shields.io/github/forks/tanbaycu/instachat?style=social)](https://github.com/tanbaycu/instachat)
[![GitHub Issues](https://img.shields.io/github/issues/tanbaycu/instachat)](https://github.com/tanbaycu/instachat/issues)
[![GitHub License](https://img.shields.io/github/license/tanbaycu/instachat)](https://github.com/tanbaycu/instachat)

Bot chat Instagram thông minh sử dụng Google Gemini AI với hệ thống monitoring, bảo mật, và phân tích nâng cao. Được thiết kế để hoạt động 24/7 với khả năng tự động phục hồi, quản lý bộ nhớ, và tạo hình ảnh AI.

> 🔗 **Repository:** [https://github.com/tanbaycu/instachat](https://github.com/tanbaycu/instachat)

## 🌟 Tính năng nổi bật

### 🤖 AI & Tự động hóa
- **Gemini AI**: Sử dụng Google Gemini AI để tạo phản hồi thông minh và tự nhiên
- **Memory System**: Hệ thống nhớ thông minh với LLM Memory Manager
- **Image Generation**: Tạo hình ảnh AI tự động khi được yêu cầu
- **Context Awareness**: Nhớ ngữ cảnh cuộc trò chuyện và cá nhân hóa phản hồi
- **Auto Response**: Trả lời tự động với độ trễ có thể tùy chỉnh

### 🛡️ Bảo mật & An toàn
- **Rate Limiting**: Giới hạn tần suất tin nhắn để tránh spam
- **Spam Detection**: Phát hiện spam bằng AI với machine learning
- **Content Filtering**: Lọc nội dung không phù hợp tự động
- **Session Encryption**: Mã hóa thông tin phiên làm việc
- **Auto Blocking**: Tự động chặn người dùng vi phạm

### 📊 Monitoring & Phân tích
- **Performance Monitor**: Theo dõi CPU, RAM, thời gian phản hồi
- **Error Handling**: Xử lý lỗi tự động với retry logic
- **Analytics Engine**: Phân tích hành vi người dùng và sentiment
- **Conversation Insights**: Phân tích sâu về flow cuộc trò chuyện
- **Real-time Alerts**: Cảnh báo real-time qua nhiều kênh

### 🚀 Hiệu suất & Tối ưu
- **Smart Caching**: Cache thông minh với LRU và disk persistence
- **Background Processing**: Xử lý background cho image generation
- **Auto Cleanup**: Tự động dọn dẹp tài nguyên
- **Resource Management**: Quản lý tài nguyên hệ thống thông minh
- **Config Management**: Quản lý cấu hình tập trung với hot reload

## 📁 Cấu trúc Project

```
instachat/
├── 📄 app.py                    # Main Instagram automation
├── 🧠 core.py                   # AI engine với Gemini & Memory
├── 🎨 image_generator.py        # AI image generation
├── 🧠 llm_memories_manager.py   # LLM memory management
├── 🚀 start_bot.py              # Startup script với validation
├── 🔧 requirements.txt          # Dependencies
├── 📖 README.md                 # Hướng dẫn này
│
├── 📊 monitoring/
│   ├── performance_monitor.py   # Theo dõi hiệu suất hệ thống
│   └── error_handler.py         # Xử lý lỗi tự động
│
├── 🛡️ security/
│   ├── security_manager.py      # Quản lý bảo mật
│   └── session_manager.py       # Quản lý phiên làm việc
│
├── 📈 analytics/
│   ├── analytics_engine.py      # Engine phân tích
│   └── conversation_insights.py # Phân tích cuộc trò chuyện
│
├── 🛠️ utils/
│   ├── cache_manager.py         # Quản lý cache
│   └── notification_system.py   # Hệ thống thông báo
│
├── ⚙️ config/
│   └── config_manager.py        # Quản lý cấu hình
│
├── 💾 memories/                 # Thư mục lưu memory
├── 🗂️ temp_memories_backup/     # Backup memories
└── 🔧 chromium_temp_data_dir/   # Temp browser data
```

## 🚀 Cài đặt nhanh

### 1. Clone repository
```bash
git clone https://github.com/tanbaycu/instachat.git
cd instachat
```

### 2. Cài đặt dependencies
```bash
pip install -r requirements.txt
```

### 3. Lấy Gemini API Key
1. Truy cập [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Tạo API key mới
3. Copy API key

### 4. Setup Environment Variables

**Cách 1: Sử dụng file .env (Khuyến nghị)**
```bash
# Copy file env_example thành .env
cp env_example .env

# Chỉnh sửa file .env với thông tin thực tế
GEMINI_API_KEY=your_gemini_api_key_here
INSTAGRAM_USERNAME=your_instagram_username
INSTAGRAM_PASSWORD=your_instagram_password
TARGET_USERNAME=target_username_to_chat
```

**Cách 2: Environment Variables**
**Windows:**
```cmd
set GEMINI_API_KEY=your_gemini_api_key_here
set INSTAGRAM_USERNAME=your_username
set INSTAGRAM_PASSWORD=your_password
set TARGET_USERNAME=target_user
```

**Linux/Mac:**
```bash
export GEMINI_API_KEY=your_gemini_api_key_here
export INSTAGRAM_USERNAME=your_username
export INSTAGRAM_PASSWORD=your_password
export TARGET_USERNAME=target_user
```

### 5. Chạy bot
```bash
# Sử dụng startup script (khuyến nghị)
python start_bot.py

# Hoặc chạy trực tiếp
python app.py

# Hoặc sử dụng batch file (Windows)
run_bot.bat

# Hoặc shell script (Linux/Mac)
./run_bot.sh
```

## ⚙️ Cấu hình chi tiết

### Cấu hình trong config_manager.py

```python
# Cấu hình Instagram
app:
  instagram_username: "your_username"
  instagram_password: "your_password"
  target_username: "target_user"
  message_delay: 3
  idle_threshold: 20
  
# Cấu hình Chrome
chrome_options:
  headless: true
  no_sandbox: true
  window_size: "1920,1080"
  
# Cấu hình AI
ai:
  api_key: "your_gemini_key"
  model: "gemini-pro"
  temperature: 0.7
  max_tokens: 100
  
# Cấu hình Security
security:
  rate_limit_messages: 10
  rate_limit_window: 60
  spam_threshold: 0.8
  max_login_attempts: 3
  
# Cấu hình Monitoring
monitoring:
  performance_check_interval: 30
  health_score_threshold: 0.7
  alert_thresholds:
    cpu: 80
    memory: 85
    response_time: 5.0
```

## 🤖 Hệ thống AI nâng cao

### Memory System
Bot sử dụng hệ thống nhớ thông minh:
- **Short-term Memory**: Nhớ 10-15 tin nhắn gần nhất
- **Long-term Memory**: Lưu trữ thông tin quan trọng lâu dài
- **Context Memory**: Nhớ ngữ cảnh cuộc trò chuyện
- **User Profiling**: Tạo profile người dùng từ lịch sử chat

### Image Generation
Tích hợp AI tạo ảnh:
- **Automatic Detection**: Tự động phát hiện yêu cầu tạo ảnh
- **Background Processing**: Xử lý tạo ảnh trong background
- **Smart Caching**: Cache ảnh đã tạo để tái sử dụng
- **Error Handling**: Xử lý lỗi tạo ảnh một cách graceful

### Prompt Engineering
```python
# Prompt được tối ưu cho:
- Trả lời ngắn gọn (10-15 từ)
- Thân thiện và tự nhiên
- Phù hợp với ngữ cảnh Việt Nam
- Tránh spam emoji
- Cá nhân hóa theo user
```

## 🛡️ Hệ thống bảo mật

### Security Manager
- **Rate Limiting**: Giới hạn 10 tin nhắn/phút
- **Spam Detection**: AI phát hiện spam với độ chính xác 85%
- **Content Filtering**: Lọc nội dung không phù hợp
- **Auto Blocking**: Tự động block user vi phạm
- **Message Validation**: Kiểm tra tính hợp lệ của tin nhắn

### Session Management
- **Encrypted Storage**: Mã hóa thông tin đăng nhập
- **Auto Login**: Tự động đăng nhập lại khi session hết hạn
- **Credential Protection**: Bảo vệ thông tin đăng nhập
- **Session Persistence**: Lưu trữ session giữa các lần chạy

## 📊 Monitoring & Analytics

### Performance Monitor
```python
# Theo dõi real-time:
- CPU Usage: 45%
- Memory Usage: 67%
- Response Time: 1.2s
- Health Score: 0.85
- Active Sessions: 1
```

### Error Handler
- **Automatic Retry**: Tự động thử lại với exponential backoff
- **Error Classification**: Phân loại lỗi theo mức độ nghiêm trọng
- **Smart Recovery**: Phục hồi thông minh từ lỗi
- **Error Logging**: Ghi log chi tiết để debug

### Analytics Engine
- **User Behavior**: Phân tích hành vi người dùng
- **Sentiment Analysis**: Phân tích cảm xúc tin nhắn
- **Conversation Flow**: Theo dõi luồng cuộc trò chuyện
- **Topic Extraction**: Trích xuất chủ đề chính

### Conversation Insights
- **Session Analysis**: Phân tích phiên chat
- **Topic Transitions**: Theo dõi chuyển đổi chủ đề
- **Sentiment Journey**: Hành trình cảm xúc trong chat
- **User Clustering**: Nhóm người dùng theo hành vi

## 🛠️ Utilities

### Cache Manager
- **LRU Cache**: Cache thông minh với Least Recently Used
- **Disk Persistence**: Lưu cache xuống disk
- **Response Cache**: Cache phản hồi AI
- **Image Cache**: Cache hình ảnh đã tạo

### Notification System
- **Multi-channel**: Thông báo qua console, file, email, webhook
- **Background Worker**: Xử lý thông báo trong background
- **Rate Limiting**: Giới hạn tần suất thông báo
- **Priority System**: Ưu tiên thông báo theo mức độ

## 🔧 Customization

### Tùy chỉnh Prompt
```python
# Trong core.py
def get_system_prompt(self):
    return """
    Bạn là một AI assistant thông minh...
    - Trả lời ngắn gọn, tối đa 15 từ
    - Thân thiện và tự nhiên
    - Phù hợp với văn hóa Việt Nam
    """
```

### Thêm Custom Analytics
```python
# Trong analytics_engine.py
def custom_analysis(self, messages):
    # Thêm logic phân tích tùy chỉnh
    return analysis_result
```

### Tùy chỉnh Security Rules
```python
# Trong security_manager.py
def custom_security_check(self, message):
    # Thêm rule bảo mật tùy chỉnh
    return is_safe
```

## 🚀 Tính năng nâng cao

### Auto Startup
```bash
# Windows Task Scheduler
schtasks /create /tn "InstaBot" /tr "C:\path\to\start_bot.py" /sc onstart

# Linux Cron
@reboot cd /path/to/instachat && python start_bot.py

# Systemd Service
sudo systemctl enable instachat.service
```

### Multi-Instance
```python
# Chạy nhiều bot cùng lúc
instances = [
    {"username": "bot1", "target": "user1"},
    {"username": "bot2", "target": "user2"}
]
```

### API Integration
```python
# Webhook integration
def webhook_handler(message):
    # Gửi tin nhắn đến external API
    requests.post(webhook_url, json=message)
```

## 📈 Performance Optimization

### Memory Management
- **Garbage Collection**: Tự động dọn dẹp memory
- **Memory Monitoring**: Theo dõi memory usage
- **Smart Cleanup**: Dọn dẹp thông minh khi cần thiết

### CPU Optimization
- **Async Processing**: Xử lý bất đồng bộ
- **Background Tasks**: Chạy task nặng trong background
- **Resource Pooling**: Tái sử dụng tài nguyên

### Network Optimization
- **Connection Pooling**: Tái sử dụng kết nối
- **Request Caching**: Cache request để giảm latency
- **Retry Logic**: Logic retry thông minh

## 🐛 Troubleshooting

### Lỗi thường gặp

#### Bot không khởi động
```bash
# Kiểm tra dependencies
pip install -r requirements.txt

# Kiểm tra Python version
python --version  # Cần >= 3.8

# Kiểm tra Chrome
google-chrome --version
```

#### Không tìm thấy element
```python
# Instagram thay đổi UI → Bot có backup selectors
# Kiểm tra logs để xem selector nào đang fail
```

#### AI không hoạt động
```bash
# Kiểm tra API key
echo $GEMINI_API_KEY

# Kiểm tra quota
curl -H "Authorization: Bearer $GEMINI_API_KEY" https://generativelanguage.googleapis.com/v1/models
```

#### Memory leak
```python
# Kiểm tra memory usage
python -m memory_profiler app.py

# Bật garbage collection
import gc
gc.collect()
```

### Debug Mode
```bash
# Chạy với debug mode
DEBUG=true python app.py

# Xem logs chi tiết
tail -f logs/instachat.log
```

## 📊 Monitoring Dashboard

### Real-time Stats
```
┌─────────────────────────────────────────────────────────────┐
│                    InstaChat Bot Status                     │
├─────────────────────────────────────────────────────────────┤
│ Status: ✅ Running                                          │
│ Uptime: 2h 34m 12s                                         │
│ Messages Processed: 156                                     │
│ Response Time: 1.2s avg                                     │
│ Memory Usage: 67% (512MB/768MB)                            │
│ CPU Usage: 23%                                             │
│ Cache Hit Rate: 89%                                        │
│ Error Rate: 0.01%                                          │
└─────────────────────────────────────────────────────────────┘
```

### Health Check
```python
# Health check endpoint
def health_check():
    return {
        "status": "healthy",
        "uptime": get_uptime(),
        "memory_usage": get_memory_usage(),
        "cpu_usage": get_cpu_usage(),
        "last_message": get_last_message_time(),
        "error_rate": get_error_rate()
    }
```

## 🔐 Security Best Practices

### Credential Management
```bash
# Sử dụng file .env (Khuyến nghị)
cp env_example .env
# Chỉnh sửa file .env với thông tin thực tế

# Hoặc sử dụng environment variables
export INSTAGRAM_USERNAME="your_username"
export INSTAGRAM_PASSWORD="your_password"
export GEMINI_API_KEY="your_api_key"

# Đã tích hợp python-dotenv
pip install python-dotenv
```

### Network Security
```python
# Sử dụng proxy nếu cần
chrome_options.add_argument("--proxy-server=http://proxy:port")

# Rotate User-Agent
user_agents = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
]
```

### Data Protection
```python
# Mã hóa sensitive data
from cryptography.fernet import Fernet
key = Fernet.generate_key()
cipher = Fernet(key)
encrypted_data = cipher.encrypt(data.encode())
```

## 🚀 Deployment

### Docker Deployment
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
CMD ["python", "start_bot.py"]
```

### Cloud Deployment
```yaml
# docker-compose.yml
version: '3.8'
services:
  instachat:
    build: .
    environment:
      - GEMINI_API_KEY=${GEMINI_API_KEY}
      - INSTAGRAM_USERNAME=${INSTAGRAM_USERNAME}
      - INSTAGRAM_PASSWORD=${INSTAGRAM_PASSWORD}
    volumes:
      - ./memories:/app/memories
      - ./logs:/app/logs
    restart: unless-stopped
```

### Production Setup
```bash
# Sử dụng supervisor cho production
sudo apt-get install supervisor

# Tạo config file
sudo nano /etc/supervisor/conf.d/instachat.conf

[program:instachat]
command=python /path/to/instachat/start_bot.py
directory=/path/to/instachat
user=instachat
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/instachat.log
```

## 📚 API Documentation

### Core API
```python
# Khởi tạo bot
bot = create_insta_bot(api_key)

# Tạo phản hồi
response = bot.generate_response(message, username)

# Lấy memory stats
stats = bot.get_memory_stats()

# Phân tích conversation
flow = bot.analyze_conversation_flow()
```

### Monitoring API
```python
# Performance monitor
monitor = get_performance_monitor()
health_score = monitor.get_health_score()

# Error handler
handler = get_error_handler()
handler.log_error(exception, context, severity)
```

### Analytics API
```python
# Analytics engine
analytics = get_analytics_engine()
insights = analytics.analyze_conversation(messages)

# Conversation insights
insights = get_conversation_insights()
flow = insights.analyze_conversation_flow(messages)
```

## 🤝 Contributing

### Development Setup
```bash
# Clone repo
git clone https://github.com/tanbaycu/instachat.git
cd instachat

# Tạo virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Install dev dependencies
pip install -r requirements-dev.txt

# Pre-commit hooks
pre-commit install
```

### Code Style
```python
# Sử dụng black formatter
black .

# Sử dụng flake8 linter
flake8 .

# Type checking với mypy
mypy .
```

### Testing
```bash
# Chạy unit tests
pytest tests/

# Coverage report
pytest --cov=. tests/

# Integration tests
pytest tests/integration/
```


## ⚖️ Disclaimer

- Bot chỉ dùng cho mục đích học tập và cá nhân
- Tuân thủ Terms of Service của Instagram
- Không sử dụng để spam hoặc làm phiền người khác
- Sử dụng có trách nhiệm và đạo đức
- Tác giả không chịu trách nhiệm về việc sử dụng sai mục đích

## 🆘 Hỗ trợ

### Liên hệ
- 🌐 Website: [tanbaycu.is-a.dev](https://tanbaycu.is-a.dev)
- 🔗 Linktree: [linktr.ee/tanbaycu](https://linktr.ee/tanbaycu)
- 🐛 Issues: [GitHub Issues](https://github.com/tanbaycu/instachat/issues)

### FAQ
**Q: Bot có thể chạy 24/7 không?**
A: Có, bot được thiết kế để chạy 24/7 với auto-recovery và monitoring.

**Q: Có thể chạy nhiều bot cùng lúc không?**
A: Có, nhưng cần cẩn thận về rate limiting và resource usage.

**Q: Bot có bị phát hiện bởi Instagram không?**
A: Bot sử dụng các kỹ thuật anti-detection nhưng vẫn có rủi ro.

### Roadmap
- [ ] Support multiple AI models (GPT-4, Claude)
- [ ] Web dashboard cho monitoring
- [ ] Mobile app companion
- [ ] Voice message support
- [ ] Advanced analytics dashboard
- [ ] Multi-language support
- [ ] Plugin system
- [ ] Cloud deployment templates

---

**Made with ❤️ và ☕ by [tanbaycu](https://tanbaycu.is-a.dev)**

*"Tự động hóa thông minh, kết nối con người"* 🤖✨

### Star History
⭐ Nếu project này hữu ích, hãy cho chúng tôi một star trên [GitHub](https://github.com/tanbaycu/instachat)!

### Contributors
**Tác giả chính:** [tanbaycu](https://linktr.ee/tanbaycu) - *Creator & Lead Developer*

Cảm ơn tất cả những người đã đóng góp cho dự án này! 🙏

---

**Version:** 2.0.0 | **Last Updated:** 2024 | **Status:** ✅ Active Development 