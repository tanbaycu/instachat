from difflib import SequenceMatcher
import re
from typing import List, Set

_VI_EN_STOPWORDS: Set[str] = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from", "has",
    "have", "he", "in", "is", "it", "of", "on", "or", "that", "the", "to", "was",
    "with", "you", "your", "i", "me", "my",
    "à", "ạ", "bạn", "bị", "bởi", "cả", "các", "cái", "cần", "cũng", "có", "cho",
    "chứ", "chỉ", "của", "cùng", "đã", "đang", "để", "đến", "đó", "được", "em",
    "gì", "hay", "khi", "không", "là", "lại", "làm", "lúc", "mà", "mình", "một",
    "này", "nên", "nếu", "người", "nhé", "nhưng", "như", "những", "nữa", "ở", "ơi",
    "phải", "qua", "rồi", "rằng", "ra", "rất", "sao", "sau", "sẽ", "tại", "theo",
    "thì", "thế", "tôi", "trong", "trên", "từ", "tui", "và", "vào", "vậy", "với",
    "vì", "về", "vừa", "xong", "zạ", "nha",
}

_WINDOWS_RESERVED_NAMES: Set[str] = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


def sanitize_filename(text: str, default_name: str = "memory", max_length: int = 80) -> str:
    """Làm sạch chuỗi thành tên file an toàn trên Windows/Linux, chống path traversal."""
    if not text:
        return default_name

    # Loại bỏ ký tự đường dẫn và ký tự cấm trên Windows (< > : " / \ | ? *)
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", str(text))
    cleaned = cleaned.replace("..", " ")
    cleaned = "_".join(cleaned.split())
    cleaned = cleaned.strip(" ._")

    if not cleaned:
        return default_name

    cleaned = cleaned[:max_length].rstrip(" ._")
    if not cleaned:
        return default_name

    # Chặn tên thiết bị dành riêng của Windows (CON, PRN, AUX, NUL, COM1..LPT9)
    stem = cleaned.split(".")[0].upper()
    if stem in _WINDOWS_RESERVED_NAMES:
        cleaned = f"mem_{cleaned}"

    return cleaned


class NLP:
    """Bộ xử lý ngôn ngữ nhẹ hỗ trợ tiếng Việt và tiếng Anh bằng Python stdlib."""

    def normalize(self, text: str) -> str:
        if not text:
            return ""
        return " ".join(str(text).lower().split())

    def remove_punctuation(self, text: str) -> str:
        """Loại bỏ dấu câu an toàn nhưng vẫn giữ nguyên dấu tiếng Việt và ký tự chữ số."""
        if not text:
            return ""
        cleaned = re.sub(r"[^\w\s]", " ", str(text), flags=re.UNICODE)
        return " ".join(cleaned.split())

    def tokenize_meaningful(self, text: str) -> List[str]:
        """Tách từ có nghĩa bằng cách loại bỏ stopwords cơ bản tiếng Việt/Anh."""
        cleaned = self.remove_punctuation(self.normalize(text))
        tokens = [tok for tok in cleaned.split() if len(tok) > 1 and tok not in _VI_EN_STOPWORDS]
        if not tokens and cleaned:
            return cleaned.split()
        return tokens

    def similarity(self, s: str, t: str) -> float:
        """Tính độ tương đồng kết hợp Jaccard token và SequenceMatcher trong khoảng [0.0, 1.0]."""
        s_norm = self.normalize(s)
        t_norm = self.normalize(t)
        if not s_norm or not t_norm:
            return 0.0
        if s_norm == t_norm:
            return 1.0

        seq_ratio = SequenceMatcher(None, s_norm, t_norm).ratio()
        tokens_s = set(self.tokenize_meaningful(s_norm))
        tokens_t = set(self.tokenize_meaningful(t_norm))
        if tokens_s and tokens_t:
            union = tokens_s | tokens_t
            jaccard = len(tokens_s & tokens_t) / len(union) if union else 0.0
        else:
            jaccard = 0.0

        return round((0.6 * jaccard) + (0.4 * seq_ratio), 4)

    # Giữ alias để tương thích ngược với tên hàm cũ viết sai chính tả
    def similiary(self, s: str, t: str) -> float:
        return self.similarity(s, t)
