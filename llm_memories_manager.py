from __activateLocalMemories import ActivateLocalMemories
from __shortContextManager import ShortContextManager
from __writeNewLocalMem import WriteNewLocalMemories
import os


class ActivateLocalMemories(ActivateLocalMemories):
    def __init__(self, limit_mem_storage=4, MEMORIES_DIR = "./memories"):

        if not os.path.exists(MEMORIES_DIR):
            os.mkdir(MEMORIES_DIR)

        super().__init__(limit_mem_storage=limit_mem_storage, MEMORIES_DIR=MEMORIES_DIR)



class ShortContextManager(ShortContextManager):
    def __init__(self, s, t, max_limit_short_mem_contxt=4, TEMP_MEM_BACKUP_DIR = "./temp_memories_backup"):
        
        if not os.path.exists(TEMP_MEM_BACKUP_DIR):
            os.mkdir(TEMP_MEM_BACKUP_DIR)

        super().__init__(s=s, t=t, max_limit_short_mem_contxt=max_limit_short_mem_contxt,
            TEMP_MEM_BACKUP_DIR=TEMP_MEM_BACKUP_DIR)
        


class WriteNewLocalMemories(WriteNewLocalMemories):
    def __init__(self, max_mem_context_towrite=4, s="s object: ", t="t object: ",
            MEMORIES_DIR = "./memories", TEMP_MEM_BACKUP_DIR = "./temp_memories_backup"):
        
        super().__init__(max_mem_context_towrite=max_mem_context_towrite, s=s, t=t,
            MEMORIES_DIR=MEMORIES_DIR, TEMP_MEM_BACKUP_DIR=TEMP_MEM_BACKUP_DIR)