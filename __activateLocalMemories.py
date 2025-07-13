import random
import os
from __naturalLanuageProcessing import NLP


class ActivateLocalMemories:

    def __init__(self, limit_mem_storage=4, MEMORIES_DIR = "./memories"):
        # tạo danh sách tên file đã bỏ đi .txt
        self.limit_mem_storage = limit_mem_storage
        self.MEMORIES_DIR = MEMORIES_DIR
        self.nlp = NLP()

    
    def activate_localMemories(self, inp): # đọc và kích hoạt bộ nhớ dự trên câu văn bản
        list_mem_name = [mem_n.replace(".txt", "") for mem_n in os.listdir(self.MEMORIES_DIR)]
        # tạo một set chứa các tên file bộ nhớ và mức độ tương đồng với text inp dưới dạng key value
        # mục đích là kích hoạt bộ nhớ dựa trên mức độ liên quan
        memories_act_scores = {mem: self.nlp.similiary(inp, mem) for mem in list_mem_name}

        most_mem_n = 0
        most_mem = ""
        
        # lặp qua set và index value score để lấy giá trị lớn nhất (file ký ức liên quan nhất)
        for m in list_mem_name:
            if memories_act_scores[m] > most_mem_n:
                most_mem_n = memories_act_scores[m]
                most_mem = m
        
        # đọc tệp ký ức đã tìm thấy, nếu có lỗi sẽ trả về False
        try:

            with open(f"{self.MEMORIES_DIR}/{most_mem}.txt", "r", encoding="utf-8") as f:
                most_memories = f.read().splitlines()
            
            # giới hạn bộ nhớ ký ức, và lấy phần ký ức ngẫu nhiên
            if len(most_memories) > self.limit_mem_storage * 2:
                sc = random.choice([n for n in range(len(most_memories))]) - self.limit_mem_storage * 2
                most_memories = most_memories[sc : sc+self.limit_mem_storage]

            return None if str(most_memories) == "[]" else most_memories
    
        except:
            print(f"đã có lỗi khi đọc file {self.MEMORIES_DIR}/{most_mem}.txt")
            return None