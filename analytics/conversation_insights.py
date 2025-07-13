import json
import os
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import re
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
import networkx as nx


class ConversationInsights:
    def __init__(self, analytics_engine=None):
        self.analytics_engine = analytics_engine
        self.conversation_flows = []
        self.user_journeys = defaultdict(list)
        self.topic_networks = {}
        self.response_quality_scores = {}
        
        print("[INSIGHTS] 🔍 Conversation Insights đã khởi tạo")

    def analyze_conversation_flow(self, user_id, days=30):
        """Phân tích luồng cuộc trò chuyện của user"""
        if not self.analytics_engine:
            return None
        
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # Lấy conversations của user
        user_conversations = [
            conv for conv in self.analytics_engine.conversation_data
            if (conv['user_id'] == user_id and 
                datetime.fromisoformat(conv['timestamp']) > cutoff_date)
        ]
        
        if not user_conversations:
            return None
        
        # Sắp xếp theo thời gian
        user_conversations.sort(key=lambda x: x['timestamp'])
        
        # Phân tích patterns
        flow_analysis = {
            'total_conversations': len(user_conversations),
            'conversation_sessions': self.identify_sessions(user_conversations),
            'topic_transitions': self.analyze_topic_transitions(user_conversations),
            'sentiment_journey': self.analyze_sentiment_journey(user_conversations),
            'engagement_patterns': self.analyze_engagement_patterns(user_conversations),
            'response_satisfaction': self.analyze_response_satisfaction(user_conversations)
        }
        
        return flow_analysis

    def identify_sessions(self, conversations):
        """Nhận diện các session chat riêng biệt"""
        sessions = []
        current_session = []
        session_gap_minutes = 30  # 30 phút không hoạt động = session mới
        
        for i, conv in enumerate(conversations):
            if i == 0:
                current_session = [conv]
            else:
                prev_time = datetime.fromisoformat(conversations[i-1]['timestamp'])
                curr_time = datetime.fromisoformat(conv['timestamp'])
                
                if (curr_time - prev_time).total_seconds() / 60 > session_gap_minutes:
                    # Kết thúc session hiện tại
                    sessions.append({
                        'session_id': len(sessions) + 1,
                        'start_time': current_session[0]['timestamp'],
                        'end_time': current_session[-1]['timestamp'],
                        'message_count': len(current_session),
                        'duration_minutes': (
                            datetime.fromisoformat(current_session[-1]['timestamp']) -
                            datetime.fromisoformat(current_session[0]['timestamp'])
                        ).total_seconds() / 60,
                        'topics': list(set(topic for conv in current_session for topic in conv['topics'])),
                        'sentiment_evolution': [conv['sentiment'] for conv in current_session]
                    })
                    
                    # Bắt đầu session mới
                    current_session = [conv]
                else:
                    current_session.append(conv)
        
        # Thêm session cuối cùng
        if current_session:
            sessions.append({
                'session_id': len(sessions) + 1,
                'start_time': current_session[0]['timestamp'],
                'end_time': current_session[-1]['timestamp'],
                'message_count': len(current_session),
                'duration_minutes': (
                    datetime.fromisoformat(current_session[-1]['timestamp']) -
                    datetime.fromisoformat(current_session[0]['timestamp'])
                ).total_seconds() / 60,
                'topics': list(set(topic for conv in current_session for topic in conv['topics'])),
                'sentiment_evolution': [conv['sentiment'] for conv in current_session]
            })
        
        return sessions

    def analyze_topic_transitions(self, conversations):
        """Phân tích chuyển đổi chủ đề"""
        transitions = []
        topic_sequences = []
        
        for conv in conversations:
            topic_sequences.extend(conv['topics'])
        
        # Tạo transition matrix
        transition_counts = defaultdict(lambda: defaultdict(int))
        
        for i in range(len(topic_sequences) - 1):
            current_topic = topic_sequences[i]
            next_topic = topic_sequences[i + 1]
            transition_counts[current_topic][next_topic] += 1
        
        # Tính transition probabilities
        transition_probs = {}
        for from_topic, to_topics in transition_counts.items():
            total = sum(to_topics.values())
            transition_probs[from_topic] = {
                to_topic: count / total
                for to_topic, count in to_topics.items()
            }
        
        return {
            'transition_counts': dict(transition_counts),
            'transition_probabilities': transition_probs,
            'most_common_transitions': self.get_top_transitions(transition_counts),
            'topic_persistence': self.calculate_topic_persistence(topic_sequences)
        }

    def get_top_transitions(self, transition_counts, top_n=5):
        """Lấy top transitions phổ biến nhất"""
        all_transitions = []
        
        for from_topic, to_topics in transition_counts.items():
            for to_topic, count in to_topics.items():
                if from_topic != to_topic:  # Loại bỏ self-transitions
                    all_transitions.append((from_topic, to_topic, count))
        
        return sorted(all_transitions, key=lambda x: x[2], reverse=True)[:top_n]

    def calculate_topic_persistence(self, topic_sequences):
        """Tính độ bền vững của chủ đề"""
        if len(topic_sequences) < 2:
            return 0
        
        same_topic_count = sum(1 for i in range(len(topic_sequences) - 1) 
                              if topic_sequences[i] == topic_sequences[i + 1])
        
        return same_topic_count / (len(topic_sequences) - 1)

    def analyze_sentiment_journey(self, conversations):
        """Phân tích hành trình cảm xúc"""
        sentiments = [conv['sentiment'] for conv in conversations]
        
        # Tính sentiment transitions
        sentiment_transitions = defaultdict(lambda: defaultdict(int))
        for i in range(len(sentiments) - 1):
            current = sentiments[i]
            next_sentiment = sentiments[i + 1]
            sentiment_transitions[current][next_sentiment] += 1
        
        # Tính sentiment stability
        stability_score = sum(1 for i in range(len(sentiments) - 1) 
                             if sentiments[i] == sentiments[i + 1]) / max(1, len(sentiments) - 1)
        
        # Tìm sentiment patterns
        patterns = self.find_sentiment_patterns(sentiments)
        
        return {
            'sentiment_sequence': sentiments,
            'sentiment_transitions': dict(sentiment_transitions),
            'stability_score': stability_score,
            'dominant_sentiment': Counter(sentiments).most_common(1)[0] if sentiments else None,
            'sentiment_patterns': patterns,
            'sentiment_improvement': self.calculate_sentiment_trend(sentiments)
        }

    def find_sentiment_patterns(self, sentiments):
        """Tìm patterns trong sentiment sequence"""
        patterns = []
        
        # Pattern: Negative -> Positive (recovery)
        for i in range(len(sentiments) - 1):
            if sentiments[i] == 'negative' and sentiments[i + 1] == 'positive':
                patterns.append(('recovery', i))
        
        # Pattern: Positive -> Negative (decline)
        for i in range(len(sentiments) - 1):
            if sentiments[i] == 'positive' and sentiments[i + 1] == 'negative':
                patterns.append(('decline', i))
        
        # Pattern: Consistent positive streak
        streak_count = 0
        for sentiment in sentiments:
            if sentiment == 'positive':
                streak_count += 1
            else:
                if streak_count >= 3:
                    patterns.append(('positive_streak', streak_count))
                streak_count = 0
        
        return patterns

    def calculate_sentiment_trend(self, sentiments):
        """Tính xu hướng cảm xúc (cải thiện/xấu đi)"""
        if len(sentiments) < 2:
            return 0
        
        # Chuyển sentiment thành số
        sentiment_values = {'negative': -1, 'neutral': 0, 'positive': 1}
        values = [sentiment_values[s] for s in sentiments]
        
        # Tính trend bằng linear regression đơn giản
        n = len(values)
        x = list(range(n))
        
        # Slope của regression line
        slope = (n * sum(x[i] * values[i] for i in range(n)) - sum(x) * sum(values)) / \
                (n * sum(x[i]**2 for i in range(n)) - sum(x)**2)
        
        return slope

    def analyze_engagement_patterns(self, conversations):
        """Phân tích patterns tương tác"""
        message_lengths = [conv['message_length'] for conv in conversations]
        response_times = [conv['response_time'] for conv in conversations]
        
        # Tính engagement metrics
        avg_message_length = np.mean(message_lengths)
        message_length_trend = self.calculate_trend(message_lengths)
        response_time_trend = self.calculate_trend(response_times)
        
        # Phân tích message frequency
        timestamps = [datetime.fromisoformat(conv['timestamp']) for conv in conversations]
        time_gaps = [(timestamps[i+1] - timestamps[i]).total_seconds() 
                    for i in range(len(timestamps) - 1)]
        
        return {
            'avg_message_length': avg_message_length,
            'message_length_trend': message_length_trend,
            'response_time_trend': response_time_trend,
            'avg_time_between_messages': np.mean(time_gaps) if time_gaps else 0,
            'engagement_consistency': 1 / (1 + np.std(message_lengths)) if message_lengths else 0,
            'conversation_intensity': len(conversations) / max(1, (timestamps[-1] - timestamps[0]).days)
        }

    def calculate_trend(self, values):
        """Tính trend của một chuỗi giá trị"""
        if len(values) < 2:
            return 0
        
        n = len(values)
        x = list(range(n))
        
        slope = (n * sum(x[i] * values[i] for i in range(n)) - sum(x) * sum(values)) / \
                (n * sum(x[i]**2 for i in range(n)) - sum(x)**2)
        
        return slope

    def analyze_response_satisfaction(self, conversations):
        """Phân tích mức độ hài lòng với response"""
        satisfaction_indicators = []
        
        for i, conv in enumerate(conversations):
            # Indicators của satisfaction
            user_msg = conv['user_message'].lower()
            bot_response = conv['bot_response'].lower()
            
            # Positive indicators
            positive_words = ['thanks', 'thank you', 'good', 'great', 'awesome', 'perfect', 
                            'cảm ơn', 'tốt', 'hay', 'được', 'ok', 'oke']
            
            # Negative indicators  
            negative_words = ['wrong', 'bad', 'not good', 'terrible', 'sai', 'tệ', 'không tốt', 
                            'dở', 'không đúng', 'chẳng hiểu']
            
            # Confusion indicators
            confusion_words = ['what', 'huh', 'confused', 'không hiểu', 'gì', 'sao', 'hả']
            
            satisfaction_score = 0
            
            # Kiểm tra next message của user (nếu có)
            if i < len(conversations) - 1:
                next_msg = conversations[i + 1]['user_message'].lower()
                
                if any(word in next_msg for word in positive_words):
                    satisfaction_score += 1
                elif any(word in next_msg for word in negative_words):
                    satisfaction_score -= 1
                elif any(word in next_msg for word in confusion_words):
                    satisfaction_score -= 0.5
            
            # Kiểm tra response time (nhanh = tốt)
            if conv['response_time'] < 2:
                satisfaction_score += 0.3
            elif conv['response_time'] > 10:
                satisfaction_score -= 0.3
            
            # Kiểm tra response length (quá ngắn hoặc quá dài có thể không tốt)
            response_length = len(bot_response)
            if 20 <= response_length <= 200:
                satisfaction_score += 0.2
            elif response_length < 5 or response_length > 500:
                satisfaction_score -= 0.2
            
            satisfaction_indicators.append(satisfaction_score)
        
        return {
            'satisfaction_scores': satisfaction_indicators,
            'avg_satisfaction': np.mean(satisfaction_indicators) if satisfaction_indicators else 0,
            'satisfaction_trend': self.calculate_trend(satisfaction_indicators),
            'highly_satisfied_count': sum(1 for score in satisfaction_indicators if score > 0.5),
            'dissatisfied_count': sum(1 for score in satisfaction_indicators if score < -0.5)
        }

    def cluster_conversation_topics(self, conversations, n_clusters=5):
        """Gom cụm conversations theo chủ đề"""
        if len(conversations) < n_clusters:
            return None
        
        # Tạo text corpus
        texts = [conv['user_message'] for conv in conversations]
        
        # TF-IDF vectorization
        vectorizer = TfidfVectorizer(max_features=100, stop_words='english')
        try:
            tfidf_matrix = vectorizer.fit_transform(texts)
            
            # K-means clustering
            kmeans = KMeans(n_clusters=n_clusters, random_state=42)
            cluster_labels = kmeans.fit_predict(tfidf_matrix)
            
            # Phân tích clusters
            clusters = defaultdict(list)
            for i, label in enumerate(cluster_labels):
                clusters[label].append(conversations[i])
            
            # Tạo cluster summaries
            cluster_summaries = {}
            for cluster_id, cluster_convs in clusters.items():
                topics = [topic for conv in cluster_convs for topic in conv['topics']]
                common_topics = Counter(topics).most_common(3)
                
                cluster_summaries[cluster_id] = {
                    'size': len(cluster_convs),
                    'common_topics': common_topics,
                    'avg_sentiment': self.calculate_avg_sentiment(cluster_convs),
                    'sample_messages': [conv['user_message'] for conv in cluster_convs[:3]]
                }
            
            return cluster_summaries
            
        except Exception as e:
            print(f"[INSIGHTS] ⚠️ Lỗi clustering: {str(e)}")
            return None

    def calculate_avg_sentiment(self, conversations):
        """Tính sentiment trung bình của một nhóm conversations"""
        sentiment_values = {'negative': -1, 'neutral': 0, 'positive': 1}
        values = [sentiment_values[conv['sentiment']] for conv in conversations]
        
        avg_value = np.mean(values)
        
        if avg_value > 0.3:
            return 'positive'
        elif avg_value < -0.3:
            return 'negative'
        else:
            return 'neutral'

    def build_topic_network(self, conversations):
        """Xây dựng mạng lưới chủ đề"""
        G = nx.Graph()
        
        # Thêm edges giữa các topics xuất hiện cùng nhau
        for conv in conversations:
            topics = conv['topics']
            for i in range(len(topics)):
                for j in range(i + 1, len(topics)):
                    if G.has_edge(topics[i], topics[j]):
                        G[topics[i]][topics[j]]['weight'] += 1
                    else:
                        G.add_edge(topics[i], topics[j], weight=1)
        
        # Tính centrality measures
        centrality = nx.degree_centrality(G)
        betweenness = nx.betweenness_centrality(G)
        
        return {
            'graph': G,
            'centrality': centrality,
            'betweenness': betweenness,
            'most_central_topics': sorted(centrality.items(), key=lambda x: x[1], reverse=True)[:5],
            'bridge_topics': sorted(betweenness.items(), key=lambda x: x[1], reverse=True)[:5]
        }

    def generate_insights_report(self, user_id, days=30):
        """Tạo báo cáo insights tổng hợp"""
        flow_analysis = self.analyze_conversation_flow(user_id, days)
        
        if not flow_analysis:
            return None
        
        # Lấy thêm dữ liệu từ analytics engine
        user_insights = self.analytics_engine.get_user_insights(user_id) if self.analytics_engine else {}
        
        report = {
            'user_id': user_id,
            'analysis_period_days': days,
            'generated_at': datetime.now().isoformat(),
            'conversation_flow': flow_analysis,
            'user_profile': user_insights,
            'key_insights': self.extract_key_insights(flow_analysis, user_insights),
            'recommendations': self.generate_recommendations(flow_analysis, user_insights)
        }
        
        return report

    def extract_key_insights(self, flow_analysis, user_insights):
        """Trích xuất insights chính"""
        insights = []
        
        # Session insights
        sessions = flow_analysis.get('conversation_sessions', [])
        if sessions:
            avg_session_duration = np.mean([s['duration_minutes'] for s in sessions])
            insights.append(f"User có {len(sessions)} sessions với thời gian trung bình {avg_session_duration:.1f} phút")
        
        # Sentiment insights
        sentiment_journey = flow_analysis.get('sentiment_journey', {})
        if sentiment_journey:
            trend = sentiment_journey.get('sentiment_improvement', 0)
            if trend > 0.1:
                insights.append("Cảm xúc của user có xu hướng tích cực")
            elif trend < -0.1:
                insights.append("Cảm xúc của user có xu hướng tiêu cực")
        
        # Engagement insights
        engagement = flow_analysis.get('engagement_patterns', {})
        if engagement:
            if engagement.get('message_length_trend', 0) > 0:
                insights.append("User ngày càng viết tin nhắn dài hơn (tăng engagement)")
            
            intensity = engagement.get('conversation_intensity', 0)
            if intensity > 5:
                insights.append("User rất tích cực tương tác (>5 conversations/ngày)")
        
        # Topic insights
        topic_transitions = flow_analysis.get('topic_transitions', {})
        if topic_transitions:
            persistence = topic_transitions.get('topic_persistence', 0)
            if persistence > 0.7:
                insights.append("User có xu hướng tập trung vào một chủ đề")
            elif persistence < 0.3:
                insights.append("User thường chuyển đổi chủ đề")
        
        return insights

    def generate_recommendations(self, flow_analysis, user_insights):
        """Tạo recommendations dựa trên insights"""
        recommendations = []
        
        # Response satisfaction recommendations
        satisfaction = flow_analysis.get('response_satisfaction', {})
        if satisfaction:
            avg_satisfaction = satisfaction.get('avg_satisfaction', 0)
            if avg_satisfaction < 0:
                recommendations.append("Cải thiện chất lượng response - user có vẻ không hài lòng")
            
            dissatisfied_count = satisfaction.get('dissatisfied_count', 0)
            if dissatisfied_count > 3:
                recommendations.append("Cần xem xét lại prompt và response generation")
        
        # Engagement recommendations
        engagement = flow_analysis.get('engagement_patterns', {})
        if engagement:
            if engagement.get('response_time_trend', 0) > 0:
                recommendations.append("Response time đang tăng - cần tối ưu performance")
            
            consistency = engagement.get('engagement_consistency', 0)
            if consistency < 0.5:
                recommendations.append("Tăng consistency trong response để giữ engagement")
        
        # Topic recommendations
        if user_insights:
            favorite_topic = user_insights.get('favorite_topic')
            if favorite_topic and favorite_topic != 'general':
                recommendations.append(f"User quan tâm đến {favorite_topic} - có thể personalize responses")
        
        return recommendations

    def save_insights_report(self, user_id, filename=None):
        """Lưu báo cáo insights"""
        if not filename:
            filename = f"analytics/insights_{user_id}_{datetime.now().strftime('%Y%m%d')}.json"
        
        try:
            report = self.generate_insights_report(user_id)
            if report:
                os.makedirs(os.path.dirname(filename), exist_ok=True)
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(report, f, indent=2, ensure_ascii=False)
                
                print(f"[INSIGHTS] 💾 Insights report saved: {filename}")
                return True
            else:
                print(f"[INSIGHTS] ⚠️ No data available for user {user_id}")
                return False
        except Exception as e:
            print(f"[INSIGHTS] ❌ Error saving report: {str(e)}")
            return False


# Singleton instance
_conversation_insights = None

def get_conversation_insights(analytics_engine=None):
    """Lấy instance singleton của ConversationInsights"""
    global _conversation_insights
    if _conversation_insights is None:
        _conversation_insights = ConversationInsights(analytics_engine)
    return _conversation_insights


if __name__ == "__main__":
    # Test conversation insights
    from analytics_engine import get_analytics_engine
    
    analytics = get_analytics_engine()
    insights = get_conversation_insights(analytics)
    
    # Add some test data
    analytics.record_conversation("Hello", "Hi there!", "test_user", 1.0)
    analytics.record_conversation("How are you?", "I'm good, thanks!", "test_user", 1.5)
    analytics.record_conversation("What's the weather?", "I don't know weather info", "test_user", 2.0)
    
    # Generate insights report
    report = insights.generate_insights_report("test_user", days=1)
    if report:
        print("Insights report generated successfully!")
        print(f"Key insights: {report['key_insights']}")
        print(f"Recommendations: {report['recommendations']}")
    else:
        print("No insights available") 