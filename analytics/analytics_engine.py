from collections import Counter, defaultdict
from datetime import datetime, timedelta
import json
import os
import re
import statistics
import threading
from typing import Any, Dict, List, Optional

from config.config_manager import get_data_dir

_POSITIVE_WORDS = {
    "good", "great", "awesome", "nice", "happy", "love", "thanks", "thank",
    "perfect", "amazing", "cool", "best", "helpful", "excellent", "fun",
    "tốt", "hay", "đẹp", "vui", "tuyệt", "thích", "yêu", "cảm ơn", "cam on",
    "ok", "oke", "okee", "chuẩn", "đỉnh", "xịn", "hài lòng", "ngon", "ổn",
}

_NEGATIVE_WORDS = {
    "bad", "terrible", "awful", "hate", "sad", "angry", "wrong", "broken",
    "slow", "lag", "fail", "error", "worst", "boring", "useless", "annoying",
    "tệ", "dở", "buồn", "giận", "sai", "lỗi", "chán", "kém", "lag", "chậm",
    "ghét", "bực", "hỏng", "thất vọng", "khó chịu", "xấu",
}

_NEGATION_WORDS = {
    "not", "no", "never", "don't", "dont", "doesn't", "didnt", "didn't",
    "không", "chẳng", "chả", "chưa", "đừng", "ko", "k",
}


class AnalyticsEngine:
    """Engine thu thập, phân tích cảm xúc VI/EN và lưu thống kê hội thoại an toàn với JSON."""

    def __init__(self, data_file: Optional[str] = None):
        analytics_dir = get_data_dir("analytics")
        self.data_file = data_file or os.path.join(analytics_dir, "analytics_data.json")
        self.conversation_data: List[Dict[str, Any]] = []
        self.user_profiles: Dict[str, Dict[str, Any]] = {}
        self.daily_stats: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

        os.makedirs(os.path.dirname(self.data_file) or analytics_dir, exist_ok=True)
        self.load_data()

    def load_data(self) -> None:
        with self._lock:
            try:
                if os.path.exists(self.data_file):
                    with open(self.data_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        self.conversation_data = list(data.get("conversations", []))
                        self.user_profiles = dict(data.get("user_profiles", {}))
                        self.daily_stats = dict(data.get("daily_stats", {}))
            except Exception as exc:
                print(f"[ANALYTICS] ⚠️ Lỗi load data: {exc}")

    def save_data(self) -> bool:
        with self._lock:
            try:
                data = {
                    "conversations": self.conversation_data,
                    "user_profiles": self.user_profiles,
                    "daily_stats": self.daily_stats,
                    "last_updated": datetime.now().isoformat(),
                }
                os.makedirs(os.path.dirname(self.data_file) or ".", exist_ok=True)
                with open(self.data_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                return True
            except Exception as exc:
                print(f"[ANALYTICS] ⚠️ Lỗi save data: {exc}")
                return False

    def record_conversation(
        self,
        user_message: str,
        bot_response: str,
        user_id: str,
        response_time: float = 0.0,
    ) -> Dict[str, Any]:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "user_message": user_message,
            "bot_response": bot_response,
            "response_time": float(response_time),
            "message_length": len(user_message),
            "response_length": len(bot_response),
            "sentiment": self.analyze_sentiment(user_message),
            "message_type": self.classify_message_type(user_message),
            "topics": self.extract_topics(user_message),
        }

        with self._lock:
            self.conversation_data.append(entry)
            if len(self.conversation_data) > 10000:
                self.conversation_data = self.conversation_data[-10000:]
            self.update_user_profile(user_id, entry)
            self.update_daily_stats(entry)

        return entry

    def analyze_sentiment(self, text: str) -> str:
        """Phân tích cảm xúc song ngữ Việt/Anh bằng lexicon nhẹ có xử lý từ phủ định."""
        if not text:
            return "neutral"

        normalized = re.sub(r"[^\w\s']", " ", text.lower(), flags=re.UNICODE)
        tokens = normalized.split()
        if not tokens:
            return "neutral"

        score = 0
        for idx, token in enumerate(tokens):
            negated = any(tokens[j] in _NEGATION_WORDS for j in range(max(0, idx - 2), idx))
            if token in _POSITIVE_WORDS:
                score += -1 if negated else 1
            elif token in _NEGATIVE_WORDS:
                score += 1 if negated else -1

        # Kiểm tra cụm từ 2 từ phổ biến (ví dụ: "cảm ơn", "hài lòng", "khó chịu")
        joined = " ".join(tokens)
        for phrase in ("cảm ơn", "cam on", "hài lòng", "rất thích", "rất hay", "thank you"):
            if phrase in joined:
                score += 1
        for phrase in ("khó chịu", "thất vọng", "không ổn", "không tốt", "not good"):
            if phrase in joined:
                score -= 1

        if score > 0:
            return "positive"
        if score < 0:
            return "negative"
        return "neutral"

    def classify_message_type(self, message: str) -> str:
        msg = (message or "").lower().strip()
        question_patterns = (
            r"\?",
            r"^(what|how|when|where|why|who|which|can|could|would|should|is|are|do|does|did)\b",
            r"\b(gì|sao|thế nào|khi nào|ở đâu|tại sao|ai|có thể|được không)\b",
        )
        if any(re.search(p, msg) for p in question_patterns):
            return "question"

        greeting_patterns = (
            r"^(hi|hello|hey|chào|xin chào|good morning|good afternoon|good evening)\b",
        )
        if any(re.search(p, msg) for p in greeting_patterns):
            return "greeting"

        command_patterns = (
            r"^(help|hướng dẫn|giúp|làm|tạo|vẽ|generate|create|draw)\b",
        )
        if any(re.search(p, msg) for p in command_patterns):
            return "command"

        complaint_patterns = (
            r"\b(tệ|dở|lag|lỗi|sai|wrong|bad|terrible|awful|broken)\b",
        )
        if any(re.search(p, msg) for p in complaint_patterns):
            return "complaint"

        return "general"

    def extract_topics(self, message: str) -> List[str]:
        msg = (message or "").lower()
        topic_keywords = {
            "technology": ("ai", "bot", "computer", "internet", "app", "software", "code", "lập trình"),
            "personal": ("tôi", "mình", "bạn", "gia đình", "friend", "family", "life"),
            "work": ("work", "job", "office", "business", "company", "làm việc", "công việc"),
            "entertainment": ("game", "movie", "music", "fun", "phim", "nhạc", "vui"),
            "education": ("học", "study", "school", "university", "learn", "bài tập"),
            "health": ("health", "sick", "doctor", "sức khỏe", "bệnh", "bác sĩ"),
            "food": ("food", "eat", "restaurant", "cooking", "ăn", "món ăn", "nấu ăn"),
            "travel": ("travel", "trip", "vacation", "du lịch", "đi chơi"),
        }
        topics = [
            topic for topic, keywords in topic_keywords.items() if any(kw in msg for kw in keywords)
        ]
        return topics or ["general"]

    def update_user_profile(self, user_id: str, entry: Dict[str, Any]) -> None:
        if user_id not in self.user_profiles:
            self.user_profiles[user_id] = {
                "first_seen": entry["timestamp"],
                "message_count": 0,
                "total_response_time": 0.0,
                "sentiments": {"positive": 0, "negative": 0, "neutral": 0},
                "message_types": {},
                "topics": {},
                "avg_message_length": 0.0,
                "hourly_activity": {},
                "most_active_hour": None,
            }

        profile = self.user_profiles[user_id]
        profile["last_seen"] = entry["timestamp"]
        profile["message_count"] = profile.get("message_count", 0) + 1
        profile["total_response_time"] = profile.get("total_response_time", 0.0) + entry["response_time"]

        sentiments = profile.setdefault("sentiments", {"positive": 0, "negative": 0, "neutral": 0})
        sent = entry["sentiment"]
        sentiments[sent] = sentiments.get(sent, 0) + 1

        msg_types = profile.setdefault("message_types", {})
        mtype = entry["message_type"]
        msg_types[mtype] = msg_types.get(mtype, 0) + 1

        topics = profile.setdefault("topics", {})
        for topic in entry["topics"]:
            topics[topic] = topics.get(topic, 0) + 1

        cnt = profile["message_count"]
        prev_avg = profile.get("avg_message_length", 0.0)
        profile["avg_message_length"] = ((prev_avg * (cnt - 1)) + entry["message_length"]) / cnt

        hour_key = str(datetime.fromisoformat(entry["timestamp"]).hour)
        hourly = profile.setdefault("hourly_activity", {})
        hourly[hour_key] = hourly.get(hour_key, 0) + 1
        profile["most_active_hour"] = int(max(hourly, key=lambda k: hourly[k]))

    def update_daily_stats(self, entry: Dict[str, Any]) -> None:
        date_str = entry["timestamp"][:10]
        if date_str not in self.daily_stats:
            self.daily_stats[date_str] = {
                "total_messages": 0,
                # Dùng list (không dùng set) để đảm bảo luôn serialize được ra JSON.
                "unique_users": [],
                "avg_response_time": 0.0,
                "total_response_time": 0.0,
                "sentiment_distribution": {"positive": 0, "negative": 0, "neutral": 0},
                "message_types": {},
                "topics": {},
            }

        stats = self.daily_stats[date_str]
        stats["total_messages"] = stats.get("total_messages", 0) + 1

        users = stats.setdefault("unique_users", [])
        if isinstance(users, set):
            users = list(users)
            stats["unique_users"] = users
        if entry["user_id"] not in users:
            users.append(entry["user_id"])

        stats["total_response_time"] = stats.get("total_response_time", 0.0) + entry["response_time"]
        stats["avg_response_time"] = stats["total_response_time"] / stats["total_messages"]

        sent_dist = stats.setdefault("sentiment_distribution", {"positive": 0, "negative": 0, "neutral": 0})
        sent = entry["sentiment"]
        sent_dist[sent] = sent_dist.get(sent, 0) + 1

        msg_types = stats.setdefault("message_types", {})
        mtype = entry["message_type"]
        msg_types[mtype] = msg_types.get(mtype, 0) + 1

        topics = stats.setdefault("topics", {})
        for topic in entry["topics"]:
            topics[topic] = topics.get(topic, 0) + 1

    def get_user_insights(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            if user_id not in self.user_profiles:
                return None
            profile = self.user_profiles[user_id]
            cnt = max(1, profile.get("message_count", 0))
            sentiments = profile.get("sentiments", {})
            topics = profile.get("topics", {})
            msg_types = profile.get("message_types", {})

            return {
                "user_id": user_id,
                "message_count": profile.get("message_count", 0),
                "avg_response_time": profile.get("total_response_time", 0.0) / cnt,
                "dominant_sentiment": max(sentiments, key=sentiments.get) if sentiments else "neutral",
                "favorite_topic": max(topics, key=topics.get) if topics else "general",
                "preferred_message_type": max(msg_types, key=msg_types.get) if msg_types else "general",
                "avg_message_length": profile.get("avg_message_length", 0.0),
                "most_active_hour": profile.get("most_active_hour"),
                "engagement_level": self.calculate_engagement_level(profile),
                "user_type": self.classify_user_type(profile),
            }

    def calculate_engagement_level(self, profile: Dict[str, Any]) -> str:
        msg_count = profile.get("message_count", 0)
        avg_length = profile.get("avg_message_length", 0)
        if msg_count >= 100 and avg_length >= 20:
            return "high"
        if msg_count >= 20 and avg_length >= 10:
            return "medium"
        return "low"

    def classify_user_type(self, profile: Dict[str, Any]) -> str:
        msg_types = profile.get("message_types", {})
        if msg_types.get("question", 0) > msg_types.get("general", 0):
            return "inquisitive"
        if msg_types.get("command", 0) > msg_types.get("general", 0):
            return "task_oriented"
        if msg_types.get("complaint", 0) > 5:
            return "critical"
        return "casual"

    def get_conversation_trends(self, days: int = 30) -> Dict[str, Any]:
        cutoff_date = datetime.now() - timedelta(days=days)
        with self._lock:
            recent = [
                conv
                for conv in self.conversation_data
                if datetime.fromisoformat(conv["timestamp"]) > cutoff_date
            ]

        if not recent:
            return {}

        daily_counts: Dict[str, int] = defaultdict(int)
        hourly_dist: Dict[int, int] = defaultdict(int)
        sentiment_trends: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        topic_trends: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for conv in recent:
            date = conv["timestamp"][:10]
            hour = datetime.fromisoformat(conv["timestamp"]).hour
            daily_counts[date] += 1
            hourly_dist[hour] += 1
            sentiment_trends[date][conv["sentiment"]] += 1
            for topic in conv["topics"]:
                topic_trends[date][topic] += 1

        return {
            "daily_message_counts": dict(daily_counts),
            "hourly_distribution": dict(hourly_dist),
            "sentiment_trends": {k: dict(v) for k, v in sentiment_trends.items()},
            "topic_trends": {k: dict(v) for k, v in topic_trends.items()},
            "total_conversations": len(recent),
            "unique_users": len({conv["user_id"] for conv in recent}),
            "avg_response_time": statistics.mean([conv["response_time"] for conv in recent]),
        }

    def generate_report(self, days: int = 30) -> Dict[str, Any]:
        trends = self.get_conversation_trends(days)
        with self._lock:
            total_convs = len(self.conversation_data)
            total_users = len(self.user_profiles)

        return {
            "report_date": datetime.now().isoformat(),
            "period_days": days,
            "summary": {
                "total_conversations": total_convs,
                "total_users": total_users,
                "recent_conversations": trends.get("total_conversations", 0),
                "recent_unique_users": trends.get("unique_users", 0),
                "avg_response_time": trends.get("avg_response_time", 0.0),
            },
            "trends": trends,
            "top_users": self.get_top_users(limit=10),
            "popular_topics": self.get_popular_topics(days),
            "sentiment_analysis": self.get_sentiment_analysis(days),
            "performance_metrics": self.get_performance_metrics(days),
        }

    def get_top_users(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            sorted_users = sorted(
                self.user_profiles.items(),
                key=lambda x: x[1].get("message_count", 0),
                reverse=True,
            )
            return [
                {
                    "user_id": uid,
                    "message_count": prof.get("message_count", 0),
                    "engagement_level": self.calculate_engagement_level(prof),
                }
                for uid, prof in sorted_users[:limit]
            ]

    def get_popular_topics(self, days: int = 30) -> Dict[str, int]:
        cutoff_date = datetime.now() - timedelta(days=days)
        topic_counts: Dict[str, int] = defaultdict(int)
        with self._lock:
            for conv in self.conversation_data:
                if datetime.fromisoformat(conv["timestamp"]) > cutoff_date:
                    for topic in conv.get("topics", []):
                        topic_counts[topic] += 1
        return dict(Counter(topic_counts).most_common(10))

    def get_sentiment_analysis(self, days: int = 30) -> Dict[str, Any]:
        cutoff_date = datetime.now() - timedelta(days=days)
        sentiment_counts: Dict[str, int] = defaultdict(int)
        with self._lock:
            for conv in self.conversation_data:
                if datetime.fromisoformat(conv["timestamp"]) > cutoff_date:
                    sentiment_counts[conv["sentiment"]] += 1

        total = sum(sentiment_counts.values())
        return {
            "counts": dict(sentiment_counts),
            "percentages": {
                k: (v / total) * 100.0 if total > 0 else 0.0 for k, v in sentiment_counts.items()
            },
        }

    def get_performance_metrics(self, days: int = 30) -> Dict[str, Any]:
        cutoff_date = datetime.now() - timedelta(days=days)
        with self._lock:
            recent = [
                conv
                for conv in self.conversation_data
                if datetime.fromisoformat(conv["timestamp"]) > cutoff_date
            ]
        if not recent:
            return {}
        response_times = [conv["response_time"] for conv in recent]
        msg_lengths = [conv["message_length"] for conv in recent]
        return {
            "avg_response_time": statistics.mean(response_times),
            "median_response_time": statistics.median(response_times),
            "max_response_time": max(response_times),
            "min_response_time": min(response_times),
            "avg_message_length": statistics.mean(msg_lengths),
            "conversations_per_day": len(recent) / max(1, days),
        }

    def save_report(self, filename: Optional[str] = None) -> bool:
        target = filename or os.path.join(get_data_dir("analytics"), "analytics_report.json")
        try:
            report = self.generate_report()
            os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            return True
        except Exception as exc:
            print(f"[ANALYTICS] ❌ Lỗi lưu báo cáo: {exc}")
            return False

    def print_summary(self) -> None:
        trends = self.get_conversation_trends(7)
        print("\n[ANALYTICS] 📊 === ANALYTICS SUMMARY ===")
        print(
            f"[ANALYTICS] 💬 Total: {len(self.conversation_data)} | "
            f"Users: {len(self.user_profiles)} | 7d: {trends.get('total_conversations', 0)}"
        )
        print("[ANALYTICS] =====================================\n")


_analytics_engine: Optional[AnalyticsEngine] = None
_analytics_lock = threading.Lock()


def get_analytics_engine(data_file: Optional[str] = None) -> AnalyticsEngine:
    global _analytics_engine
    with _analytics_lock:
        if _analytics_engine is None:
            _analytics_engine = AnalyticsEngine(data_file=data_file)
        return _analytics_engine


def reset_analytics_engine() -> None:
    global _analytics_engine
    with _analytics_lock:
        _analytics_engine = None
