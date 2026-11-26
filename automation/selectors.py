import re

"""Tập hợp XPath/CSS selectors đa ngôn ngữ (EN/VI), bộ lọc noise và dấu hiệu an toàn Instagram."""

DIRECT_INBOX_URL = "https://www.instagram.com/direct/inbox/"

COOKIE_CONSENT_XPATHS = (
    "//button[contains(text(), 'Allow all cookies')]",
    "//button[contains(text(), 'Allow essential and optional cookies')]",
    "//button[contains(text(), 'Accept All')]",
    "//button[contains(text(), 'Cho phép tất cả cookie')]",
)

LOGIN_USERNAME_SELECTORS = (
    ("name", "username"),
    ("css", "input[name='username']"),
    ("css", "input[autocomplete='username']"),
)

LOGIN_PASSWORD_SELECTORS = (
    ("name", "password"),
    ("css", "input[name='password']"),
    ("css", "input[type='password']"),
)

LOGIN_SUCCESS_INDICATORS = (
    "//button[contains(text(), 'Save info') or contains(text(), 'Save Info') or contains(text(), 'Lưu thông tin')]",
    "//button[contains(text(), 'Not Now') or contains(text(), 'Not now') or contains(text(), 'Lúc khác')]",
    "//div[contains(@aria-label, 'Home') or contains(@aria-label, 'Trang chủ')]",
    "//a[contains(@href, '/direct/')]",
    "//span[text()='Home' or text()='Trang chủ']",
    "//svg[@aria-label='Home' or @aria-label='Trang chủ']",
)

DISMISS_POPUP_XPATHS = (
    "//button[contains(text(), 'Not Now') or contains(text(), 'Not now')]",
    "//button[contains(text(), 'Lúc khác')]",
    "//button[contains(@class, '_a9--') and (text()='Not Now' or text()='Lúc khác')]",
)

PROFILE_MESSAGE_BUTTON_XPATHS = (
    "//div[@role='button' and (contains(., 'Message') or contains(., 'Nhắn tin'))]",
    "//button[contains(., 'Message') or contains(., 'Nhắn tin')]",
    "//a[contains(., 'Message') or contains(., 'Nhắn tin')]",
    "//div[contains(text(), 'Message') or contains(text(), 'Nhắn tin')]",
)

DIRECT_THREAD_SEARCH_XPATHS = (
    "//input[@name='queryBox' or @placeholder='Search' or @placeholder='Tìm kiếm']",
    "//input[contains(@aria-label, 'Search') or contains(@aria-label, 'Tìm kiếm')]",
)

MESSAGE_TEXT_XPATHS = (
    "//div[@role='none']//div[contains(@class, 'x126k92a')]",
    "//div[@data-scope='messages_table']//div[@dir='auto']",
    "//div[@data-scope='messages']//div[@dir='auto']",
    "//div[contains(@class, 'html-div') and @dir='auto']",
    "//div[contains(@class, 'x1n2onr6')]//span[@dir='auto']",
    "//span[contains(@class, 'x1lliihq')]",
)

COMPOSER_INPUT_XPATHS = (
    "//div[@contenteditable='true' and @aria-label='Message']",
    "//div[@contenteditable='true' and @aria-label='Tin nhắn']",
    "//div[@contenteditable='true' and @role='textbox']",
    "//div[@contenteditable='true']",
    "//textarea[@placeholder='Message...']",
    "//textarea[@placeholder='Nhắn tin...']",
    "//div[contains(@aria-label, 'Message') or contains(@aria-label, 'Tin nhắn')]",
)

FILE_UPLOAD_INPUT_XPATHS = (
    "//input[@type='file' and contains(@accept, 'image')]",
    "//input[@type='file']",
)

# Nhãn trạng thái hệ thống của Instagram Direct không phải tin nhắn người dùng thật
SYSTEM_NOISE_PATTERNS = (
    re.compile(r"^seen(?:\s+.*)?$", re.IGNORECASE),
    re.compile(r"^đã xem(?:\s+.*)?$", re.IGNORECASE | re.UNICODE),
    re.compile(r"^sent(?:\s+\d+[smhdw]\s+ago)?$", re.IGNORECASE),
    re.compile(r"^đã gửi(?:\s+.*)?$", re.IGNORECASE | re.UNICODE),
    re.compile(r"^active\s+(?:now|\d+[smhdw]\s+ago)$", re.IGNORECASE),
    re.compile(r"^đang hoạt động$", re.IGNORECASE | re.UNICODE),
    re.compile(r"^hoạt động\s+\d+\s*(?:phút|giờ|ngày)\s+trước$", re.IGNORECASE | re.UNICODE),
    re.compile(r"^typing\.{0,3}$", re.IGNORECASE),
    re.compile(r"^đang nhập\.{0,3}$", re.IGNORECASE | re.UNICODE),
    re.compile(r"^you sent(?:\s+an?\s+attachment)?$", re.IGNORECASE),
    re.compile(r"^bạn đã gửi(?:\s+một\s+tệp\s+đính\s+kèm)?$", re.IGNORECASE | re.UNICODE),
    re.compile(r"^reacted\s+.*?\s+to\s+your\s+message$", re.IGNORECASE),
    re.compile(r"^đã bày tỏ cảm xúc.*$", re.IGNORECASE | re.UNICODE),
)

# Các dấu hiệu URL/nội dung cảnh báo Instagram đang khóa, checkpoint hoặc rate-limit
SAFETY_URL_RULES = {
    "suspended": ("/accounts/suspended", "disabled"),
    "challenge": ("/challenge/", "/consent/"),
    "two_factor": ("/two_factor",),
    "logged_out": ("/accounts/login",),
}

SAFETY_TEXT_RULES = {
    "suspended": (
        "your account has been suspended",
        "we suspended your account",
        "tài khoản của bạn đã bị đình chỉ",
        "tài khoản bị tạm khóa",
    ),
    "challenge": (
        "we detected unusual activity",
        "confirm your identity",
        "help us confirm it's you",
        "we suspect automated behavior",
        "hoạt động bất thường",
        "xác nhận danh tính",
    ),
    "rate_limited": (
        "please wait a few minutes",
        "try again later",
        "action blocked",
        "try again in a few minutes",
        "vui lòng đợi vài phút",
        "hành động bị chặn",
        "thử lại sau",
    ),
}
