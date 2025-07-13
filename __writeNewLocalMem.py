import os
from __naturalLanuageProcessing import NLP

class WriteNewLocalMemories:
    
    def __init__(self, max_mem_context_towrite=10, s="s object: ", t="t object: ",
            MEMORIES_DIR = "./memories", TEMP_MEM_BACKUP_DIR = "./temp_memories_backup"):
        # tạo danh sách tên file đã bỏ đi .txt
        self.max_mem_context_towrite = max_mem_context_towrite
        self.s = s
        self.t = t
        self.CONTEXT = []
        self.MEMORIES_DIR = MEMORIES_DIR
        self.TEMP_MEM_BACKUP_DIR = TEMP_MEM_BACKUP_DIR
        self.nlp = NLP()
        self.read_context_backup()


    
    def read_context_backup(self):
        if os.path.exists(f"{self.TEMP_MEM_BACKUP_DIR}/backup_contxt_writer.txt"):
            with open(f"{self.TEMP_MEM_BACKUP_DIR}/backup_contxt_writer.txt", "r", encoding="utf-8") as file:
                context_backup = file.read().splitlines()
            self.CONTEXT = context_backup



    def backup_contxt_writer(self):
        # backup lại ngữ cảnh đang duy trùy ở hiện tại, để phòng tránh trường hợp tắt bất ngờ và mất
        # thông tin đang duy trì
        with open(f"{self.TEMP_MEM_BACKUP_DIR}/backup_contxt_writer.txt", "w", encoding="utf-8") as file:
            context_text = "\n".join(self.CONTEXT)
            file.write(context_text)



    def w(self, inp, ans, filename: str): # ghi bộ nhớ mới vào folder memories
        inp, ans = " ".join(inp.split()), " ".join(ans.split())
        list_mem_name = [mem_n.replace(".txt", "") for mem_n in os.listdir(self.MEMORIES_DIR)]
        # tạo một set chứa các tên file bộ nhớ và mức độ tương đồng với text inp dưới dạng key value
        # mục đích là kích hoạt bộ nhớ dựa trên mức độ liên quan
        memories_act_scores = {mem: self.nlp.similiary(" ".join(inp.split()[:10]), mem) for mem in list_mem_name}
        
        most_mem_n = 0
        most_mem = ""
        
        # lặp qua set và index value score để lấy giá trị lớn nhất (file ký ức liên quan nhất)
        for m in list_mem_name:
            if memories_act_scores[m] > most_mem_n:
                most_mem_n = memories_act_scores[m]
                most_mem = m
        
        """
        lưu đầu vào và đầu ra vào file đã tồn tại nếu file đã tồn tại có độ tương đồng cao 0.5 (50%)
        so với input
        """
        if most_mem_n > 0.5:
            with open(f"{self.MEMORIES_DIR}/{most_mem}.txt", "a", encoding="utf-8") as f:
                f.write(f"{inp}\n{ans}\n")
        
        # nếu độ tương đồng không cao hơn 50% sẽ tajo file ký ức mới và lưu các ký ức mới vào
        else:
            with open(f"{self.MEMORIES_DIR}/{filename}.txt", "a", encoding="utf-8") as f:
                f.write(f"{inp}\n{ans}\n")



    def write_newLocalMem(self, inp, ans):
        """
        hàm đặc biệt này sẽ giới hạn số lượng ngữ cảnh tối đa trước khi ghi, để ký ức không chỉ là
        những gì đã diễn ra trong một lần, mà nó còn bao gồm ngữ cảnh
        """
        inp, ans = " ".join(inp.split()), " ".join(ans.split())
        # thêm input và ans vào ngữ cảnh sau mỗi bước thời gian
        self.CONTEXT.append(self.s+inp)
        self.CONTEXT.append(self.t+ans)
        
        # tiến hành lưu nếu số lượng ngữ cảnh đạt chỉ tiêu
        if len(self.CONTEXT) > self.max_mem_context_towrite:
            # lấy vị trí index đầu tiên trong ngữ cảnh làm tên file ký ức
            # xử lý trước tên file
            filename = self.CONTEXT[0].replace(self.s, "").replace(self.t, "")
            filename = " ".join(self.nlp.remove_punctuation(filename).split()[:10])
            filename = filename.strip()

            # lưu vào bộ nhớ, bao gồm cả ngữ cảnh
            n=0
            for _ in range(self.max_mem_context_towrite-1):
                self.w(self.CONTEXT[n], self.CONTEXT[n+1], filename)
                n = (n+1)+1

            # cập nhật cắt bớt ngữ cảnh lại
            self.CONTEXT = self.CONTEXT[ len(self.CONTEXT)-self.max_mem_context_towrite: ]
    
        self.backup_contxt_writer()