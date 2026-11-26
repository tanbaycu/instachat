import os

from memory.nlp import NLP, sanitize_filename
from memory.store import (
    ActivateLocalMemories,
    ShortContextManager,
    SQLiteMemoryStore,
    WriteNewLocalMemories,
)


def test_sanitize_filename_blocks_traversal_and_reserved_names():
    assert ".." not in sanitize_filename("../../etc/passwd")
    assert "/" not in sanitize_filename("foo/bar\\baz")
    assert sanitize_filename("CON").startswith("mem_")
    assert sanitize_filename("nul.txt").startswith("mem_")
    assert sanitize_filename("") == "memory"


def test_nlp_vietnamese_similarity_and_punctuation():
    nlp = NLP()
    cleaned = nlp.remove_punctuation("Xin chào, bạn tên là gì?!")
    assert "chào" in cleaned
    assert "?" not in cleaned
    assert nlp.similarity("tôi thích cà phê sữa", "mình rất thích uống cà phê sữa") > 0.3
    assert nlp.similiary("abc", "abc") == 1.0


def test_sqlite_memory_store_isolates_users_and_retrieves_memories(tmp_path):
    store = SQLiteMemoryStore(db_path=str(tmp_path / "mem.db"))
    try:
        store.save_turn("alice", "Mình thích ăn bún chả Hà Nội", "Ngon quá, bún chả rất tuyệt!")
        store.save_turn("bob", "Tôi thích chơi bóng đá cuối tuần", "Chơi thể thao rất khỏe!")

        alice_ctx = store.get_short_context("alice")
        bob_ctx = store.get_short_context("bob")
        assert len(alice_ctx) == 2
        assert all("bún chả" in item["message"] or "Ngon" in item["message"] for item in alice_ctx)
        assert len(bob_ctx) == 2
        assert not any("bún chả" in item["message"] for item in bob_ctx)

        hits = store.search_memories("alice", "bún chả Hà Nội")
        assert hits
        assert "bún chả" in hits[0]
        assert store.search_memories("bob", "bún chả Hà Nội") == []
    finally:
        store.close()


def test_legacy_memory_wrappers_no_index_error_or_negative_slice(tmp_path):
    mem_dir = tmp_path / "memories"
    backup_dir = tmp_path / "backup"

    activator = ActivateLocalMemories(limit_mem_storage=4, MEMORIES_DIR=str(mem_dir))
    # Thư mục rỗng trả về None thay vì crash đọc ".txt"
    assert activator.activate_localMemories("xin chào") is None

    writer = WriteNewLocalMemories(
        max_mem_context_towrite=5,
        s="user: ",
        t="bot: ",
        MEMORIES_DIR=str(mem_dir),
        TEMP_MEM_BACKUP_DIR=str(backup_dir),
    )
    # Ghi vượt ngưỡng lẻ trước đây gây IndexError
    for idx in range(6):
        writer.write_newLocalMem(f"CON? câu hỏi số {idx}", f"trả lời {idx}")

    files = os.listdir(mem_dir)
    assert any(name.endswith(".txt") for name in files)

    result = activator.activate_localMemories("câu hỏi số 0")
    assert result is not None
    assert 1 <= len(result) <= 4

    short_mgr = ShortContextManager(
        s="user: ", t="bot: ", max_limit_short_mem_contxt=4, TEMP_MEM_BACKUP_DIR=str(backup_dir)
    )
    short_mgr.save_to_shortContextMem("hi", "hello")
    assert short_mgr.activate_shortContetxMem() == ["user: hi", "bot: hello"]
