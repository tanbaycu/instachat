from types import SimpleNamespace

from core import InstaBot
from image_generator import ImageGenerator
from memory.store import SQLiteMemoryStore


class _FakeModels:
    def __init__(self, text_reply="Chào bạn, mình đang nghe đây!", image_bytes=b"\x89PNG\r\n\x1a\nfake"):
        self.text_reply = text_reply
        self.image_bytes = image_bytes
        self.calls = []

    def generate_content(self, model, contents, config=None):
        self.calls.append({"model": model, "contents": contents, "config": config})
        modalities = getattr(config, "response_modalities", None) if config else None
        if modalities and "IMAGE" in modalities:
            part = SimpleNamespace(
                inline_data=SimpleNamespace(data=self.image_bytes, mime_type="image/png")
            )
            return SimpleNamespace(parts=[part], candidates=[])
        return SimpleNamespace(text=self.text_reply)


class _FakeGenAIClient:
    def __init__(self, text_reply="Chào bạn, mình đang nghe đây!"):
        self.models = _FakeModels(text_reply=text_reply)


def test_image_generator_filters_false_positives(tmp_path):
    fake_client = _FakeGenAIClient(text_reply="a cute cat sitting by the window")
    gen = ImageGenerator(genai_client=fake_client, output_dir=str(tmp_path / "imgs"))

    # Các câu bình thường KHÔNG được kích hoạt tạo ảnh
    assert gen.is_image_request("hình như trời sắp mưa rồi đó") is False
    assert gen.is_image_request("ảnh này đẹp quá bạn ơi") is False
    assert gen.is_image_request("that picture looks awesome") is False

    # Các câu yêu cầu rõ ràng PHẢI kích hoạt
    assert gen.is_image_request("tạo ảnh con mèo dễ thương") is True
    assert gen.is_image_request("vẽ cho mình một ngôi nhà bên biển") is True
    assert gen.is_image_request("draw a cyberpunk cat") is True
    assert gen.is_image_request("generate an image of a sunset") is True

    desc = gen.extract_description("tạo ảnh con mèo dễ thương")
    assert "mèo" in desc

    result = gen.generate_image(desc)
    assert result["success"] is True
    assert result["file_path"] is not None
    assert gen.is_processing_image() is False


def test_instabot_generates_vietnamese_response_and_persists_memory(tmp_path):
    fake_client = _FakeGenAIClient(
        text_reply="Chào Tân, rất vui được trò chuyện với bạn ở Hà Nội hôm nay!"
    )
    mem_store = SQLiteMemoryStore(db_path=str(tmp_path / "bot_mem.db"))

    try:
        bot = InstaBot(genai_client=fake_client, memory_store=mem_store)
        reply = bot.generate_response("Mình tên Tân ở Hà Nội", username="tan_user")

        assert "Tân" in reply
        assert "Hà Nội" in reply
        assert len(fake_client.models.calls) == 1
        assert bot.security_manager.get_security_stats()["total_messages"] == 1

        # Tin thứ 2 sẽ tự nạp ngữ cảnh trước đó của tan_user
        bot.generate_response("Bạn nhớ mình tên gì không?", username="tan_user")
        second_prompt = fake_client.models.calls[1]["contents"]
        assert "Tân" in second_prompt
    finally:
        mem_store.close()


def test_instabot_retries_transient_llm_error(tmp_path, monkeypatch):
    class _FlakyModels:
        def __init__(self):
            self.attempts = 0

        def generate_content(self, model, contents, config=None):
            self.attempts += 1
            if self.attempts < 2:
                raise RuntimeError("503 Service Unavailable")
            return SimpleNamespace(text="Đã phản hồi thành công sau khi retry!")

    flaky_client = SimpleNamespace(models=_FlakyModels())
    mem_store = SQLiteMemoryStore(db_path=str(tmp_path / "retry_mem.db"))
    monkeypatch.setattr("core.time.sleep", lambda _s: None)

    try:
        bot = InstaBot(genai_client=flaky_client, memory_store=mem_store)
        reply = bot.generate_response("Alo bạn ơi", username="retry_user")
        assert "thành công" in reply
        assert flaky_client.models.attempts == 2
    finally:
        mem_store.close()
