import json
import os
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import re
import statistics
from textblob import TextBlob
import matplotlib.pyplot as plt
import seaborn as sns


class AnalyticsEngine:
    def __init__(self, data_file="analytics/analytics_data.json"):
        self.data_file = data_file
        self.conversation_data = []
        self.user_profiles = defaultdict(dict)
        self.daily_stats = defaultdict(dict)
        
        # Tạo thư mục nếu chưa có
        os.makedirs(os.path.dirname(data_file), exist_ok=True)
        
        # Load existing data
        self.load_data()
        
        print("[ANALYTICS] 📊 Analytics Engine đã khởi tạo")

    def load_data(self):
        """Load dữ liệu analytics từ file"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.conversation_data = data.get('conversations', [])
                    self.user_profiles = defaultdict(dict, data.get('user_profiles', {}))
                    self.daily_stats = defaultdict(dict, data.get('daily_stats', {}))
                print(f"[ANALYTICS] 📂 Loaded {len(self.conversation_data)} conversations")
        except Exception as e:
            print(f"[ANALYTICS] ⚠️ Lỗi load data: {str(e)}")

    def save_data(self):
        """Lưu dữ liệu analytics"""
        try:
            data = {
                'conversations': self.conversation_data,
                'user_profiles': dict(self.user_profiles),
                'daily_stats': dict(self.daily_stats),
                'last_updated': datetime.now().isoformat()
            }
            
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            print(f"[ANALYTICS] 💾 Saved analytics data")
        except Exception as e:
            print(f"[ANALYTICS] ⚠️ Lỗi save data: {str(e)}")

    def record_conversation(self, user_message, bot_response, user_id, response_time=0):
        """Ghi lại cuộc trò chuyện"""
        conversation_entry = {
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'user_message': user_message,
            'bot_response': bot_response,
            'response_time': response_time,
            'message_length': len(user_message),
            'response_length': len(bot_response),
            'sentiment': self.analyze_sentiment(user_message),
            'message_type': self.classify_message_type(user_message),
            'topics': self.extract_topics(user_message)
        }
        
        self.conversation_data.append(conversation_entry)
        self.update_user_profile(user_id, conversation_entry)
        self.update_daily_stats(conversation_entry)
        
        # Giữ chỉ 10000 conversations gần nhất
        if len(self.conversation_data) > 10000:
            self.conversation_data = self.conversation_data[-10000:]

    def analyze_sentiment(self, text):
        """Phân tích cảm xúc của tin nhắn"""
        try:
            blob = TextBlob(text)
            polarity = blob.sentiment.polarity
            
            if polarity > 0.1:
                return 'positive'
            elif polarity < -0.1:
                return 'negative'
            else:
                return 'neutral'
        except:
            return 'neutral'

    def classify_message_type(self, message):
        """Phân loại loại tin nhắn"""
        message_lower = message.lower()
        
        # Question patterns
        question_patterns = [
            r'\?', r'^(what|how|when|where|why|who|which|can|could|would|should|is|are|do|does|did)',
            r'(gì|sao|thế nào|khi nào|ở đâu|tại sao|ai|có thể|được không)'
        ]
        
        if any(re.search(pattern, message_lower) for pattern in question_patterns):
            return 'question'
        
        # Greeting patterns
        greeting_patterns = [
            r'^(hi|hello|hey|chào|xin chào|good morning|good afternoon|good evening)',
            r'(chào bạn|hello|hi there)'
        ]
        
        if any(re.search(pattern, message_lower) for pattern in greeting_patterns):
            return 'greeting'
        
        # Command patterns
        command_patterns = [
            r'^(help|hướng dẫn|giúp|làm|tạo|generate|create)',
            r'(làm giúp|tạo cho|generate|create)'
        ]
        
        if any(re.search(pattern, message_lower) for pattern in command_patterns):
            return 'command'
        
        # Complaint patterns
        complaint_patterns = [
            r'(không|chẳng|tệ|dở|lag|lỗi|sai|wrong|bad|terrible|awful)',
            r'(không hoạt động|not working|broken)'
        ]
        
        if any(re.search(pattern, message_lower) for pattern in complaint_patterns):
            return 'complaint'
        
        return 'general'

    def extract_topics(self, message):
        """Trích xuất chủ đề từ tin nhắn"""
        topics = []
        message_lower = message.lower()
        
        # Định nghĩa các chủ đề
        topic_keywords = {
            'technology': ['ai', 'bot', 'computer', 'internet', 'app', 'software', 'code', 'programming'],
            'personal': ['tôi', 'mình', 'bạn', 'gia đình', 'friend', 'family', 'personal', 'life'],
            'work': ['work', 'job', 'office', 'business', 'company', 'career', 'làm việc', 'công việc'],
            'entertainment': ['game', 'movie', 'music', 'fun', 'entertainment', 'phim', 'nhạc', 'vui'],
            'education': ['học', 'study', 'school', 'university', 'education', 'learn', 'knowledge'],
            'health': ['health', 'sick', 'doctor', 'medicine', 'sức khỏe', 'bệnh', 'bác sĩ'],
            'food': ['food', 'eat', 'restaurant', 'cooking', 'ăn', 'thức ăn', 'món ăn', 'nấu ăn'],
            'travel': ['travel', 'trip', 'vacation', 'du lịch', 'đi chơi', 'nghỉ mát']
        }
        
        for topic, keywords in topic_keywords.items():
            if any(keyword in message_lower for keyword in keywords):
                topics.append(topic)
        
        return topics if topics else ['general']

    def update_user_profile(self, user_id, conversation_entry):
        """Cập nhật profile người dùng"""
        if user_id not in self.user_profiles:
            self.user_profiles[user_id] = {
                'first_seen': conversation_entry['timestamp'],
                'message_count': 0,
                'total_response_time': 0,
                'sentiments': {'positive': 0, 'negative': 0, 'neutral': 0},
                'message_types': defaultdict(int),
                'topics': defaultdict(int),
                'avg_message_length': 0,
                'most_active_hour': None,
                'conversation_patterns': []
            }
        
        profile = self.user_profiles[user_id]
        profile['last_seen'] = conversation_entry['timestamp']
        profile['message_count'] += 1
        profile['total_response_time'] += conversation_entry['response_time']
        
        # Update sentiment
        sentiment = conversation_entry['sentiment']
        profile['sentiments'][sentiment] += 1
        
        # Update message type
        msg_type = conversation_entry['message_type']
        profile['message_types'][msg_type] += 1
        
        # Update topics
        for topic in conversation_entry['topics']:
            profile['topics'][topic] += 1
        
        # Update average message length
        total_length = profile['avg_message_length'] * (profile['message_count'] - 1) + conversation_entry['message_length']
        profile['avg_message_length'] = total_length / profile['message_count']
        
        # Update most active hour
        hour = datetime.fromisoformat(conversation_entry['timestamp']).hour
        if 'hourly_activity' not in profile:
            profile['hourly_activity'] = defaultdict(int)
        profile['hourly_activity'][hour] += 1
        profile['most_active_hour'] = max(profile['hourly_activity'], key=profile['hourly_activity'].get)

    def update_daily_stats(self, conversation_entry):
        """Cập nhật thống kê hàng ngày"""
        date_str = conversation_entry['timestamp'][:10]  # YYYY-MM-DD
        
        if date_str not in self.daily_stats:
            self.daily_stats[date_str] = {
                'total_messages': 0,
                'unique_users': set(),
                'avg_response_time': 0,
                'total_response_time': 0,
                'sentiment_distribution': {'positive': 0, 'negative': 0, 'neutral': 0},
                'message_types': defaultdict(int),
                'topics': defaultdict(int)
            }
        
        stats = self.daily_stats[date_str]
        stats['total_messages'] += 1
        stats['unique_users'].add(conversation_entry['user_id'])
        stats['total_response_time'] += conversation_entry['response_time']
        stats['avg_response_time'] = stats['total_response_time'] / stats['total_messages']
        
        # Update sentiment distribution
        sentiment = conversation_entry['sentiment']
        stats['sentiment_distribution'][sentiment] += 1
        
        # Update message types
        msg_type = conversation_entry['message_type']
        stats['message_types'][msg_type] += 1
        
        # Update topics
        for topic in conversation_entry['topics']:
            stats['topics'][topic] += 1

    def get_user_insights(self, user_id):
        """Lấy insights về user cụ thể"""
        if user_id not in self.user_profiles:
            return None
        
        profile = self.user_profiles[user_id]
        
        # Tính toán các metrics
        avg_response_time = profile['total_response_time'] / max(1, profile['message_count'])
        dominant_sentiment = max(profile['sentiments'], key=profile['sentiments'].get)
        favorite_topic = max(profile['topics'], key=profile['topics'].get) if profile['topics'] else 'general'
        preferred_message_type = max(profile['message_types'], key=profile['message_types'].get)
        
        return {
            'user_id': user_id,
            'message_count': profile['message_count'],
            'avg_response_time': avg_response_time,
            'dominant_sentiment': dominant_sentiment,
            'favorite_topic': favorite_topic,
            'preferred_message_type': preferred_message_type,
            'avg_message_length': profile['avg_message_length'],
            'most_active_hour': profile.get('most_active_hour'),
            'engagement_level': self.calculate_engagement_level(profile),
            'user_type': self.classify_user_type(profile)
        }

    def calculate_engagement_level(self, profile):
        """Tính mức độ tương tác của user"""
        msg_count = profile['message_count']
        avg_length = profile['avg_message_length']
        
        if msg_count >= 100 and avg_length >= 20:
            return 'high'
        elif msg_count >= 20 and avg_length >= 10:
            return 'medium'
        else:
            return 'low'

    def classify_user_type(self, profile):
        """Phân loại loại user"""
        msg_types = profile['message_types']
        
        if msg_types.get('question', 0) > msg_types.get('general', 0):
            return 'inquisitive'
        elif msg_types.get('command', 0) > msg_types.get('general', 0):
            return 'task_oriented'
        elif msg_types.get('complaint', 0) > 5:
            return 'critical'
        else:
            return 'casual'

    def get_conversation_trends(self, days=30):
        """Lấy xu hướng cuộc trò chuyện"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        recent_conversations = [
            conv for conv in self.conversation_data
            if datetime.fromisoformat(conv['timestamp']) > cutoff_date
        ]
        
        if not recent_conversations:
            return {}
        
        # Tính toán trends
        daily_message_counts = defaultdict(int)
        hourly_distribution = defaultdict(int)
        sentiment_trends = defaultdict(lambda: defaultdict(int))
        topic_trends = defaultdict(lambda: defaultdict(int))
        
        for conv in recent_conversations:
            date = conv['timestamp'][:10]
            hour = datetime.fromisoformat(conv['timestamp']).hour
            
            daily_message_counts[date] += 1
            hourly_distribution[hour] += 1
            sentiment_trends[date][conv['sentiment']] += 1
            
            for topic in conv['topics']:
                topic_trends[date][topic] += 1
        
        return {
            'daily_message_counts': dict(daily_message_counts),
            'hourly_distribution': dict(hourly_distribution),
            'sentiment_trends': dict(sentiment_trends),
            'topic_trends': dict(topic_trends),
            'total_conversations': len(recent_conversations),
            'unique_users': len(set(conv['user_id'] for conv in recent_conversations)),
            'avg_response_time': statistics.mean([conv['response_time'] for conv in recent_conversations])
        }

    def generate_report(self, days=30):
        """Tạo báo cáo tổng hợp"""
        trends = self.get_conversation_trends(days)
        
        report = {
            'report_date': datetime.now().isoformat(),
            'period_days': days,
            'summary': {
                'total_conversations': len(self.conversation_data),
                'total_users': len(self.user_profiles),
                'recent_conversations': trends.get('total_conversations', 0),
                'recent_unique_users': trends.get('unique_users', 0),
                'avg_response_time': trends.get('avg_response_time', 0)
            },
            'trends': trends,
            'top_users': self.get_top_users(limit=10),
            'popular_topics': self.get_popular_topics(days),
            'sentiment_analysis': self.get_sentiment_analysis(days),
            'performance_metrics': self.get_performance_metrics(days)
        }
        
        return report

    def get_top_users(self, limit=10):
        """Lấy top users theo message count"""
        sorted_users = sorted(
            self.user_profiles.items(),
            key=lambda x: x[1]['message_count'],
            reverse=True
        )
        
        return [
            {
                'user_id': user_id,
                'message_count': profile['message_count'],
                'engagement_level': self.calculate_engagement_level(profile)
            }
            for user_id, profile in sorted_users[:limit]
        ]

    def get_popular_topics(self, days=30):
        """Lấy chủ đề phổ biến"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        topic_counts = defaultdict(int)
        for conv in self.conversation_data:
            if datetime.fromisoformat(conv['timestamp']) > cutoff_date:
                for topic in conv['topics']:
                    topic_counts[topic] += 1
        
        return dict(Counter(topic_counts).most_common(10))

    def get_sentiment_analysis(self, days=30):
        """Phân tích cảm xúc tổng thể"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        sentiment_counts = defaultdict(int)
        for conv in self.conversation_data:
            if datetime.fromisoformat(conv['timestamp']) > cutoff_date:
                sentiment_counts[conv['sentiment']] += 1
        
        total = sum(sentiment_counts.values())
        
        return {
            'counts': dict(sentiment_counts),
            'percentages': {
                sentiment: (count / total) * 100 if total > 0 else 0
                for sentiment, count in sentiment_counts.items()
            }
        }

    def get_performance_metrics(self, days=30):
        """Lấy metrics hiệu suất"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        recent_conversations = [
            conv for conv in self.conversation_data
            if datetime.fromisoformat(conv['timestamp']) > cutoff_date
        ]
        
        if not recent_conversations:
            return {}
        
        response_times = [conv['response_time'] for conv in recent_conversations]
        message_lengths = [conv['message_length'] for conv in recent_conversations]
        
        return {
            'avg_response_time': statistics.mean(response_times),
            'median_response_time': statistics.median(response_times),
            'max_response_time': max(response_times),
            'min_response_time': min(response_times),
            'avg_message_length': statistics.mean(message_lengths),
            'conversations_per_day': len(recent_conversations) / days
        }

    def save_report(self, filename="analytics/analytics_report.json"):
        """Lưu báo cáo"""
        try:
            report = self.generate_report()
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            print(f"[ANALYTICS] 💾 Báo cáo đã lưu: {filename}")
            return True
        except Exception as e:
            print(f"[ANALYTICS] ❌ Lỗi lưu báo cáo: {str(e)}")
            return False

    def print_summary(self):
        """In tóm tắt analytics"""
        trends = self.get_conversation_trends(7)  # 7 ngày gần nhất
        
        print(f"\n[ANALYTICS] 📊 === ANALYTICS SUMMARY ===")
        print(f"[ANALYTICS] 💬 Total Conversations: {len(self.conversation_data)}")
        print(f"[ANALYTICS] 👥 Total Users: {len(self.user_profiles)}")
        print(f"[ANALYTICS] 📅 Recent (7 days): {trends.get('total_conversations', 0)} conversations")
        print(f"[ANALYTICS] ⏱️ Avg Response Time: {trends.get('avg_response_time', 0):.2f}s")
        
        # Top topics
        popular_topics = self.get_popular_topics(7)
        if popular_topics:
            top_topic = max(popular_topics, key=popular_topics.get)
            print(f"[ANALYTICS] 🔥 Top Topic: {top_topic} ({popular_topics[top_topic]} mentions)")
        
        # Sentiment
        sentiment = self.get_sentiment_analysis(7)
        if sentiment['counts']:
            dominant_sentiment = max(sentiment['counts'], key=sentiment['counts'].get)
            print(f"[ANALYTICS] 😊 Dominant Sentiment: {dominant_sentiment} ({sentiment['percentages'][dominant_sentiment]:.1f}%)")
        
        print(f"[ANALYTICS] =====================================\n")


# Singleton instance
_analytics_engine = None

def get_analytics_engine():
    """Lấy instance singleton của AnalyticsEngine"""
    global _analytics_engine
    if _analytics_engine is None:
        _analytics_engine = AnalyticsEngine()
    return _analytics_engine


if __name__ == "__main__":
    # Test analytics engine
    analytics = get_analytics_engine()
    
    # Test record conversation
    analytics.record_conversation(
        "Hello, how are you?",
        "Hi there! I'm doing well, thanks for asking!",
        "test_user_1",
        response_time=1.5
    )
    
    analytics.record_conversation(
        "What's the weather like?",
        "I don't have access to weather data, but I hope it's nice!",
        "test_user_1",
        response_time=2.1
    )
    
    # Print summary
    analytics.print_summary()
    
    # Save report
    analytics.save_report()
    
    # Save data
    analytics.save_data() 