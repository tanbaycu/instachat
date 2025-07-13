import os

class ShortContextManager:
    
    def __init__(self, s, t, max_limit_short_mem_contxt=4,
            TEMP_MEM_BACKUP_DIR = "./temp_memories_backup"):
        self.max_limit_short_mem_contxt = max_limit_short_mem_contxt
        self.s = s
        self.t = t
        self.context = []
        self.TEMP_MEM_BACKUP_DIR = TEMP_MEM_BACKUP_DIR
        self.read_backup()


    def read_backup(self):
        # gán lại ngữ cảnh ngắn hạn đã sao lưu nếu có
        if os.path.exists(f"{self.TEMP_MEM_BACKUP_DIR}/short_context_backup.txt"):
            with open(f"{self.TEMP_MEM_BACKUP_DIR}/short_context_backup.txt", "r", encoding="utf-8") as f:
                short_context = f.read().strip().splitlines()
            self.context = short_context



    def backup_short_context_writer(self):
        # sao lưu ngữ cảnh ngắn hạn
        with open(f"{self.TEMP_MEM_BACKUP_DIR}/short_context_backup.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(self.context))



    def save_to_shortContextMem(self, inp, ans):
        # chuẩn hóa inp và ans
        inp, ans = " ".join(inp.split()), " ".join(ans.split())
        
        # thêm inp và ans của bước thời gian hiện tại vào ngữ cảnh
        self.context.append(self.s+inp)
        self.context.append(self.t+ans)

        if len(self.context) > self.max_limit_short_mem_contxt:
            self.context = self.context[ len(self.context)-self.max_limit_short_mem_contxt: ]
        
        # liên tục sao lưu ngữ cảnh
        self.backup_short_context_writer()


    
    def activate_shortContetxMem(self):
        return None if str(self.context) == "[]" else self.context