from collections import Counter, defaultdict, deque
from datetime import datetime, timedelta
import json
import math
import os
import re
import statistics
import threading
from typing import Any, Dict, List, Optional

from config.config_manager import get_data_dir


class ConversationInsights:
    """Phân tích luồng hội thoại, cụm chủ đề và mạng chủ đề bằng Python thuần (không cần numpy/sklearn)."""

    def __init__(self, analytics_engine=None):
        self.analytics_engine = analytics_engine
        self.conversation_flows: List[Dict[str, Any]] = []
        self.user_journeys: Dict[str, List[Any]] = defaultdict(list)
        self.topic_networks: Dict[str, Any] = {}

    def analyze_conversation_flow(self, user_id: str, days: int = 30) -> Optional[Dict[str, Any]]:
        if not self.analytics_engine:
            return None

        cutoff_date = datetime.now() - timedelta(days=days)
        user_conversations = [
            conv
            for conv in self.analytics_engine.conversation_data
            if conv.get("user_id") == user_id
            and datetime.fromisoformat(conv["timestamp"]) > cutoff_date
        ]
        if not user_conversations:
            return None

        user_conversations.sort(key=lambda x: x["timestamp"])
        return {
            "total_conversations": len(user_conversations),
            "conversation_sessions": self.identify_sessions(user_conversations),
            "topic_transitions": self.analyze_topic_transitions(user_conversations),
            "sentiment_journey": self.analyze_sentiment_journey(user_conversations),
            "engagement_patterns": self.analyze_engagement_patterns(user_conversations),
            "response_satisfaction": self.analyze_response_satisfaction(user_conversations),
        }

    def identify_sessions(self, conversations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        sessions: List[Dict[str, Any]] = []
        current_session: List[Dict[str, Any]] = []
        session_gap_minutes = 30

        for idx, conv in enumerate(conversations):
            if idx == 0:
                current_session = [conv]
                continue

            prev_time = datetime.fromisoformat(conversations[idx - 1]["timestamp"])
            curr_time = datetime.fromisoformat(conv["timestamp"])
            if (curr_time - prev_time).total_seconds() / 60.0 > session_gap_minutes:
                sessions.append(self._summarize_session(len(sessions) + 1, current_session))
                current_session = [conv]
            else:
                current_session.append(conv)

        if current_session:
            sessions.append(self._summarize_session(len(sessions) + 1, current_session))
        return sessions

    @staticmethod
    def _summarize_session(session_id: int, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        start = datetime.fromisoformat(items[0]["timestamp"])
        end = datetime.fromisoformat(items[-1]["timestamp"])
        return {
            "session_id": session_id,
            "start_time": items[0]["timestamp"],
            "end_time": items[-1]["timestamp"],
            "message_count": len(items),
            "duration_minutes": (end - start).total_seconds() / 60.0,
            "topics": list({t for c in items for t in c.get("topics", [])}),
            "sentiment_evolution": [c.get("sentiment", "neutral") for c in items],
        }

    def analyze_topic_transitions(self, conversations: List[Dict[str, Any]]) -> Dict[str, Any]:
        topic_sequences: List[str] = []
        for conv in conversations:
            topic_sequences.extend(conv.get("topics", []))

        transition_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for idx in range(len(topic_sequences) - 1):
            transition_counts[topic_sequences[idx]][topic_sequences[idx + 1]] += 1

        transition_probs: Dict[str, Dict[str, float]] = {}
        for from_topic, to_topics in transition_counts.items():
            total = sum(to_topics.values())
            transition_probs[from_topic] = {
                to_topic: count / total for to_topic, count in to_topics.items()
            }

        return {
            "transition_counts": {k: dict(v) for k, v in transition_counts.items()},
            "transition_probabilities": transition_probs,
            "most_common_transitions": self.get_top_transitions(transition_counts),
            "topic_persistence": self.calculate_topic_persistence(topic_sequences),
        }

    def get_top_transitions(
        self, transition_counts: Dict[str, Dict[str, int]], top_n: int = 5
    ) -> List[tuple]:
        all_transitions = []
        for from_topic, to_topics in transition_counts.items():
            for to_topic, count in to_topics.items():
                if from_topic != to_topic:
                    all_transitions.append((from_topic, to_topic, count))
        return sorted(all_transitions, key=lambda x: x[2], reverse=True)[:top_n]

    def calculate_topic_persistence(self, topic_sequences: List[str]) -> float:
        if len(topic_sequences) < 2:
            return 0.0
        same_count = sum(
            1 for idx in range(len(topic_sequences) - 1) if topic_sequences[idx] == topic_sequences[idx + 1]
        )
        return same_count / (len(topic_sequences) - 1)

    def analyze_sentiment_journey(self, conversations: List[Dict[str, Any]]) -> Dict[str, Any]:
        sentiments = [conv.get("sentiment", "neutral") for conv in conversations]
        sentiment_transitions: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for idx in range(len(sentiments) - 1):
            sentiment_transitions[sentiments[idx]][sentiments[idx + 1]] += 1

        stability = sum(
            1 for idx in range(len(sentiments) - 1) if sentiments[idx] == sentiments[idx + 1]
        ) / max(1, len(sentiments) - 1)

        return {
            "sentiment_sequence": sentiments,
            "sentiment_transitions": {k: dict(v) for k, v in sentiment_transitions.items()},
            "stability_score": stability,
            "dominant_sentiment": Counter(sentiments).most_common(1)[0] if sentiments else None,
            "sentiment_patterns": self.find_sentiment_patterns(sentiments),
            "sentiment_improvement": self.calculate_sentiment_trend(sentiments),
        }

    def find_sentiment_patterns(self, sentiments: List[str]) -> List[tuple]:
        patterns: List[tuple] = []
        for idx in range(len(sentiments) - 1):
            if sentiments[idx] == "negative" and sentiments[idx + 1] == "positive":
                patterns.append(("recovery", idx))
            elif sentiments[idx] == "positive" and sentiments[idx + 1] == "negative":
                patterns.append(("decline", idx))

        streak = 0
        for sentiment in sentiments:
            if sentiment == "positive":
                streak += 1
            else:
                if streak >= 3:
                    patterns.append(("positive_streak", streak))
                streak = 0
        if streak >= 3:
            patterns.append(("positive_streak", streak))
        return patterns

    def calculate_sentiment_trend(self, sentiments: List[str]) -> float:
        sentiment_values = {"negative": -1.0, "neutral": 0.0, "positive": 1.0}
        values = [sentiment_values.get(s, 0.0) for s in sentiments]
        return self.calculate_trend(values)

    def analyze_engagement_patterns(self, conversations: List[Dict[str, Any]]) -> Dict[str, Any]:
        message_lengths = [float(conv["message_length"]) for conv in conversations]
        response_times = [float(conv["response_time"]) for conv in conversations]

        timestamps = [datetime.fromisoformat(conv["timestamp"]) for conv in conversations]
        time_gaps = [
            (timestamps[idx + 1] - timestamps[idx]).total_seconds()
            for idx in range(len(timestamps) - 1)
        ]

        std_len = statistics.pstdev(message_lengths) if len(message_lengths) > 1 else 0.0
        span_days = max(1, (timestamps[-1] - timestamps[0]).days) if timestamps else 1

        return {
            "avg_message_length": statistics.mean(message_lengths) if message_lengths else 0.0,
            "message_length_trend": self.calculate_trend(message_lengths),
            "response_time_trend": self.calculate_trend(response_times),
            "avg_time_between_messages": statistics.mean(time_gaps) if time_gaps else 0.0,
            "engagement_consistency": 1.0 / (1.0 + std_len),
            "conversation_intensity": len(conversations) / span_days,
        }

    def calculate_trend(self, values: List[float]) -> float:
        """Tính hệ số góc hồi quy tuyến tính; bảo vệ mẫu số 0 để không bao giờ chia cho 0."""
        n = len(values)
        if n < 2:
            return 0.0
        sum_x = (n - 1) * n / 2.0
        sum_x2 = (n - 1) * n * (2 * n - 1) / 6.0
        denom = (n * sum_x2) - (sum_x**2)
        if denom == 0:
            return 0.0
        sum_y = sum(values)
        sum_xy = sum(idx * val for idx, val in enumerate(values))
        return ((n * sum_xy) - (sum_x * sum_y)) / denom

    def analyze_response_satisfaction(self, conversations: List[Dict[str, Any]]) -> Dict[str, Any]:
        positive_words = (
            "thanks", "thank you", "good", "great", "awesome", "perfect",
            "cảm ơn", "tốt", "hay", "được", "ok", "oke",
        )
        negative_words = (
            "wrong", "bad", "not good", "terrible", "sai", "tệ", "không tốt",
            "dở", "không đúng", "chẳng hiểu",
        )
        confusion_words = ("what", "huh", "confused", "không hiểu", "gì", "sao", "hả")

        scores: List[float] = []
        for idx, conv in enumerate(conversations):
            bot_resp = conv.get("bot_response", "").lower()
            score = 0.0

            if idx < len(conversations) - 1:
                next_msg = conversations[idx + 1].get("user_message", "").lower()
                if any(w in next_msg for w in positive_words):
                    score += 1.0
                elif any(w in next_msg for w in negative_words):
                    score -= 1.0
                elif any(w in next_msg for w in confusion_words):
                    score -= 0.5

            resp_time = conv.get("response_time", 0.0)
            if resp_time < 2.0:
                score += 0.3
            elif resp_time > 10.0:
                score -= 0.3

            resp_len = len(bot_resp)
            if 15 <= resp_len <= 250:
                score += 0.2
            elif resp_len < 3 or resp_len > 500:
                score -= 0.2

            scores.append(score)

        return {
            "satisfaction_scores": scores,
            "avg_satisfaction": statistics.mean(scores) if scores else 0.0,
            "satisfaction_trend": self.calculate_trend(scores),
            "highly_satisfied_count": sum(1 for s in scores if s > 0.5),
            "dissatisfied_count": sum(1 for s in scores if s < -0.5),
        }

    def cluster_conversation_topics(
        self, conversations: List[Dict[str, Any]], n_clusters: int = 5
    ) -> Optional[Dict[int, Dict[str, Any]]]:
        """Gom cụm hội thoại bằng TF-IDF vector thưa + K-means thuần Python (ổn định, không dependency nặng)."""
        if len(conversations) < max(1, n_clusters):
            return None

        docs_tokens: List[List[str]] = []
        df: Counter = Counter()
        for conv in conversations:
            tokens = re.findall(r"\w{2,}", conv.get("user_message", "").lower())
            docs_tokens.append(tokens)
            for tok in set(tokens):
                df[tok] += 1

        n_docs = len(conversations)
        vectors: List[Dict[str, float]] = []
        for tokens in docs_tokens:
            tf = Counter(tokens)
            vec: Dict[str, float] = {}
            norm_sq = 0.0
            for tok, freq in tf.items():
                idf = math.log((n_docs + 1) / (df[tok] + 1)) + 1.0
                w = (freq / max(1, len(tokens))) * idf
                vec[tok] = w
                norm_sq += w * w
            norm = math.sqrt(norm_sq) or 1.0
            vectors.append({k: v / norm for k, v in vec.items()})

        # Khởi tạo tâm cụm từ k mẫu phân bố đều để kết quả xác định (deterministic).
        step = max(1, n_docs // n_clusters)
        centroids = [dict(vectors[min(i * step, n_docs - 1)]) for i in range(n_clusters)]
        labels = [0] * n_docs

        for _ in range(8):
            changed = False
            for idx, vec in enumerate(vectors):
                best_c = 0
                best_sim = -1.0
                for c_idx, cent in enumerate(centroids):
                    sim = sum(val * cent.get(k, 0.0) for k, val in vec.items())
                    if sim > best_sim:
                        best_sim = sim
                        best_c = c_idx
                if labels[idx] != best_c:
                    labels[idx] = best_c
                    changed = True

            if not changed:
                break

            for c_idx in range(n_clusters):
                member_indices = [i for i, lbl in enumerate(labels) if lbl == c_idx]
                if not member_indices:
                    continue
                accum: Dict[str, float] = defaultdict(float)
                for m_idx in member_indices:
                    for k, v in vectors[m_idx].items():
                        accum[k] += v
                norm = math.sqrt(sum(v * v for v in accum.values())) or 1.0
                centroids[c_idx] = {k: v / norm for k, v in accum.items()}

        clusters: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for idx, lbl in enumerate(labels):
            clusters[lbl].append(conversations[idx])

        return {
            cid: {
                "size": len(items),
                "common_topics": Counter(
                    t for c in items for t in c.get("topics", [])
                ).most_common(3),
                "avg_sentiment": self.calculate_avg_sentiment(items),
                "sample_messages": [c.get("user_message", "") for c in items[:3]],
            }
            for cid, items in clusters.items()
        }

    def calculate_avg_sentiment(self, conversations: List[Dict[str, Any]]) -> str:
        if not conversations:
            return "neutral"
        sentiment_values = {"negative": -1.0, "neutral": 0.0, "positive": 1.0}
        avg = statistics.mean(
            [sentiment_values.get(c.get("sentiment", "neutral"), 0.0) for c in conversations]
        )
        if avg > 0.3:
            return "positive"
        if avg < -0.3:
            return "negative"
        return "neutral"

    def build_topic_network(self, conversations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Xây dựng đồ thị đồng xuất hiện chủ đề và tính degree / betweenness centrality thuần Python."""
        adjacency: Dict[str, Dict[str, int]] = defaultdict(dict)
        nodes = set()

        for conv in conversations:
            topics = list(dict.fromkeys(conv.get("topics", [])))
            for topic in topics:
                nodes.add(topic)
            for i in range(len(topics)):
                for j in range(i + 1, len(topics)):
                    u, v = topics[i], topics[j]
                    adjacency[u][v] = adjacency[u].get(v, 0) + 1
                    adjacency[v][u] = adjacency[v].get(u, 0) + 1

        node_count = len(nodes)
        centrality: Dict[str, float] = {}
        for node in nodes:
            centrality[node] = (
                len(adjacency.get(node, {})) / (node_count - 1) if node_count > 1 else 0.0
            )

        # Betweenness centrality bằng thuật toán Brandes rút gọn cho đồ thị vô hướng không trọng số
        betweenness: Dict[str, float] = {n: 0.0 for n in nodes}
        for s in nodes:
            stack: List[str] = []
            pred: Dict[str, List[str]] = {w: [] for w in nodes}
            sigma: Dict[str, float] = {w: 0.0 for w in nodes}
            sigma[s] = 1.0
            dist: Dict[str, int] = {w: -1 for w in nodes}
            dist[s] = 0
            queue: deque = deque([s])

            while queue:
                v = queue.popleft()
                stack.append(v)
                for w in adjacency.get(v, {}):
                    if dist[w] < 0:
                        queue.append(w)
                        dist[w] = dist[v] + 1
                    if dist[w] == dist[v] + 1:
                        sigma[w] += sigma[v]
                        pred[w].append(v)

            delta: Dict[str, float] = {w: 0.0 for w in nodes}
            while stack:
                w = stack.pop()
                for v in pred[w]:
                    if sigma[w] > 0:
                        delta[v] += (sigma[v] / sigma[w]) * (1.0 + delta[w])
                if w != s:
                    betweenness[w] += delta[w]

        norm = (node_count - 1) * (node_count - 2) if node_count > 2 else 1.0
        betweenness = {k: v / norm for k, v in betweenness.items()}

        return {
            "nodes": sorted(nodes),
            "edges": {u: dict(nbrs) for u, nbrs in adjacency.items()},
            "centrality": centrality,
            "betweenness": betweenness,
            "most_central_topics": sorted(centrality.items(), key=lambda x: x[1], reverse=True)[:5],
            "bridge_topics": sorted(betweenness.items(), key=lambda x: x[1], reverse=True)[:5],
        }

    def generate_insights_report(self, user_id: str, days: int = 30) -> Optional[Dict[str, Any]]:
        flow_analysis = self.analyze_conversation_flow(user_id, days)
        if not flow_analysis:
            return None

        user_insights = (
            self.analytics_engine.get_user_insights(user_id) if self.analytics_engine else {}
        ) or {}
        return {
            "user_id": user_id,
            "analysis_period_days": days,
            "generated_at": datetime.now().isoformat(),
            "conversation_flow": flow_analysis,
            "user_profile": user_insights,
            "key_insights": self.extract_key_insights(flow_analysis, user_insights),
            "recommendations": self.generate_recommendations(flow_analysis, user_insights),
        }

    def extract_key_insights(
        self, flow_analysis: Dict[str, Any], user_insights: Dict[str, Any]
    ) -> List[str]:
        insights: List[str] = []
        sessions = flow_analysis.get("conversation_sessions", [])
        if sessions:
            avg_dur = statistics.mean([s["duration_minutes"] for s in sessions])
            insights.append(f"User có {len(sessions)} sessions với thời gian trung bình {avg_dur:.1f} phút")

        sentiment_trend = flow_analysis.get("sentiment_journey", {}).get("sentiment_improvement", 0.0)
        if sentiment_trend > 0.1:
            insights.append("Cảm xúc của user có xu hướng tích cực")
        elif sentiment_trend < -0.1:
            insights.append("Cảm xúc của user có xu hướng tiêu cực")

        engagement = flow_analysis.get("engagement_patterns", {})
        if engagement.get("message_length_trend", 0.0) > 0:
            insights.append("User ngày càng viết tin nhắn dài hơn (tăng engagement)")
        if engagement.get("conversation_intensity", 0.0) > 5:
            insights.append("User rất tích cực tương tác (>5 conversations/ngày)")

        persistence = flow_analysis.get("topic_transitions", {}).get("topic_persistence", 0.0)
        if persistence > 0.7:
            insights.append("User có xu hướng tập trung vào một chủ đề")
        elif persistence < 0.3:
            insights.append("User thường xuyên chuyển đổi chủ đề")

        return insights

    def generate_recommendations(
        self, flow_analysis: Dict[str, Any], user_insights: Dict[str, Any]
    ) -> List[str]:
        recommendations: List[str] = []
        satisfaction = flow_analysis.get("response_satisfaction", {})
        if satisfaction.get("avg_satisfaction", 0.0) < 0:
            recommendations.append("Cải thiện chất lượng phản hồi — user có dấu hiệu chưa hài lòng")
        if satisfaction.get("dissatisfied_count", 0) > 3:
            recommendations.append("Cần xem xét lại system prompt và ngữ cảnh bộ nhớ")

        engagement = flow_analysis.get("engagement_patterns", {})
        if engagement.get("response_time_trend", 0.0) > 0:
            recommendations.append("Response time đang tăng — cần tối ưu tốc độ xử lý")
        if engagement.get("engagement_consistency", 1.0) < 0.5:
            recommendations.append("Giữ văn phong phản hồi ổn định hơn để tăng mức độ gắn kết")

        fav_topic = user_insights.get("favorite_topic") if user_insights else None
        if fav_topic and fav_topic != "general":
            recommendations.append(f"User quan tâm đến {fav_topic} — có thể cá nhân hóa câu trả lời")
        return recommendations

    def save_insights_report(self, user_id: str, filename: Optional[str] = None) -> bool:
        if not filename:
            filename = os.path.join(
                get_data_dir("analytics"),
                f"insights_{user_id}_{datetime.now().strftime('%Y%m%d')}.json",
            )
        try:
            report = self.generate_insights_report(user_id)
            if not report:
                return False
            os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            return True
        except Exception as exc:
            print(f"[INSIGHTS] ❌ Lỗi lưu report: {exc}")
            return False


_conversation_insights: Optional[ConversationInsights] = None
_insights_lock = threading.Lock()


def get_conversation_insights(analytics_engine=None) -> ConversationInsights:
    global _conversation_insights
    with _insights_lock:
        if _conversation_insights is None:
            _conversation_insights = ConversationInsights(analytics_engine)
        elif analytics_engine is not None and _conversation_insights.analytics_engine is None:
            _conversation_insights.analytics_engine = analytics_engine
        return _conversation_insights


def reset_conversation_insights() -> None:
    global _conversation_insights
    with _insights_lock:
        _conversation_insights = None
