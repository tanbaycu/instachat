from difflib import SequenceMatcher

class NLP:

    def __init__(self) -> None:
        pass

    # kiểm tra độ tương đồng
    def similiary(self, s, t):
        return SequenceMatcher(None, s, t).ratio()
    
    # xóa dấu câu
    def remove_punctuation(self, text):
        punct = """<>?"'}{|+_)(*&^%$#@!)/.,;'][\\=-`~]:"""
        for c in list(punct):
            text = text.replace(c, "")
        return text