from datetime import datetime, timedelta

from analytics.analytics_engine import AnalyticsEngine
from analytics.conversation_insights import ConversationInsights


def test_analytics_bilingual_sentiment_and_json_roundtrip(tmp_path):
    data_file = tmp_path / "analytics_data.json"
    engine = AnalyticsEngine(data_file=str(data_file))

    assert engine.analyze_sentiment("cảm ơn bạn rất nhiều, tuyệt vời!") == "positive"
    assert engine.analyze_sentiment("dịch vụ này không tốt và rất tệ") == "negative"
    assert engine.analyze_sentiment("hôm nay thứ mấy") == "neutral"

    engine.record_conversation("Xin chào, code python hay quá", "Chào bạn!", "alice", 1.2)
    engine.record_conversation("Làm sao để học tốt?", "Luyện tập mỗi ngày nhé", "bob", 0.8)
    assert engine.save_data() is True

    # Reload và ghi thêm bản ghi mới (trước đây gây TypeError với set và KeyError sau reload)
    reloaded = AnalyticsEngine(data_file=str(data_file))
    reloaded.record_conversation("Rất tuyệt, cảm ơn!", "Không có chi", "alice", 0.5)
    assert reloaded.save_data() is True

    report = reloaded.generate_report(days=7)
    assert report["summary"]["total_conversations"] == 3
    assert report["summary"]["total_users"] == 2


def test_conversation_insights_pure_python_analytics(tmp_path):
    engine = AnalyticsEngine(data_file=str(tmp_path / "a.json"))
    base_time = datetime.now() - timedelta(hours=2)

    messages = [
        ("hi chào bạn", "hello!", ["personal"]),
        ("học lập trình python sao cho nhanh?", "viết project nhỏ mỗi ngày", ["technology", "education"]),
        ("ăn tối chưa bạn ơi?", "mình ăn cơm rồi", ["food", "personal"]),
        ("công việc dạo này tốt chứ?", "ổn lắm nè", ["work"]),
        ("cảm ơn bạn nhiều nha", "không có gì đâu", ["personal"]),
        ("tệ quá mạng hơi lag", "sorry để mình check lại", ["technology"]),
    ]
    for idx, (u_msg, b_msg, _) in enumerate(messages):
        entry = engine.record_conversation(u_msg, b_msg, "tester", response_time=1.0 + idx * 0.1)
        entry["timestamp"] = (base_time + timedelta(minutes=idx * 45)).isoformat()

    insights = ConversationInsights(engine)
    flow = insights.analyze_conversation_flow("tester", days=7)
    assert flow is not None
    assert len(flow["conversation_sessions"]) >= 2
    assert flow["engagement_patterns"]["avg_message_length"] > 0

    clusters = insights.cluster_conversation_topics(engine.conversation_data, n_clusters=3)
    assert clusters is not None
    assert sum(c["size"] for c in clusters.values()) == len(engine.conversation_data)

    network = insights.build_topic_network(engine.conversation_data)
    assert "most_central_topics" in network
    assert "bridge_topics" in network

    # Đảm bảo không chia cho 0 khi dãy constant
    assert insights.calculate_trend([5.0]) == 0.0
    assert insights.calculate_trend([3.0, 3.0, 3.0]) == 0.0
