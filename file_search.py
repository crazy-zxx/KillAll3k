import ctypes
import os
from typing import List, Dict
from rapidfuzz import fuzz


class EverythingSearch:
    def __init__(self, settings_manager=None):
        self.settings_manager = settings_manager
        self.available = False
        self.everything_dll = None
        
        # Everything SDK 常量
        self.EVERYTHING_REQUEST_FILE_NAME = 0x00000001
        self.EVERYTHING_REQUEST_PATH = 0x00000002
        self.EVERYTHING_REQUEST_FULL_PATH_AND_FILE_NAME = 0x00000004
        self.EVERYTHING_REQUEST_SIZE = 0x00000010
        self.EVERYTHING_REQUEST_DATE_MODIFIED = 0x00000020
        self.EVERYTHING_REQUEST_DATE_CREATED = 0x00000040
        self.EVERYTHING_REQUEST_DATE_ACCESSED = 0x00000080
        self.EVERYTHING_REQUEST_ATTRIBUTES = 0x00000100
        
        self.EVERYTHING_SORT_NAME_ASCENDING = 1
        self.EVERYTHING_SORT_NAME_DESCENDING = 2
        self.EVERYTHING_SORT_PATH_ASCENDING = 3
        self.EVERYTHING_SORT_PATH_DESCENDING = 4
        self.EVERYTHING_SORT_SIZE_ASCENDING = 5
        self.EVERYTHING_SORT_SIZE_DESCENDING = 6
        self.EVERYTHING_SORT_DATE_MODIFIED_ASCENDING = 7
        self.EVERYTHING_SORT_DATE_MODIFIED_DESCENDING = 8
        self.EVERYTHING_SORT_DATE_CREATED_ASCENDING = 11
        self.EVERYTHING_SORT_DATE_CREATED_DESCENDING = 12
        self.EVERYTHING_SORT_DATE_ACCESSED_ASCENDING = 13
        self.EVERYTHING_SORT_DATE_ACCESSED_DESCENDING = 14
        self.EVERYTHING_SORT_ATTRIBUTES_ASCENDING = 15
        self.EVERYTHING_SORT_ATTRIBUTES_DESCENDING = 16
        self.EVERYTHING_SORT_RELEVANCE = 1000
        
        # 尝试加载 Everything DLL
        self.load_everything_dll()
    
    def load_everything_dll(self):
        """尝试加载 Everything SDK DLL"""
        dll_paths = []
        
        # 首先尝试配置文件中的自定义路径
        if self.settings_manager:
            custom_dll_path = self.settings_manager.get('everything_dll_path', '')
            if custom_dll_path:
                dll_paths.append(custom_dll_path)
        
        # 然后尝试默认路径
        dll_paths.extend([
            os.path.join(os.environ.get('PROGRAMFILES', ''), 'Everything', 'Everything64.dll'),
            os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), 'Everything', 'Everything64.dll'),
            os.path.join(os.environ.get('PROGRAMFILES', ''), 'Everything', 'Everything32.dll'),
            os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), 'Everything', 'Everything32.dll'),
            'Everything64.dll',
            'Everything32.dll'
        ])
        
        for dll_path in dll_paths:
            if os.path.exists(dll_path):
                try:
                    self.everything_dll = ctypes.windll.LoadLibrary(dll_path)
                    
                    # 设置函数参数类型
                    self.everything_dll.Everything_SetSearchW.argtypes = [ctypes.c_wchar_p]
                    self.everything_dll.Everything_SetMax.argtypes = [ctypes.c_int]
                    self.everything_dll.Everything_SetSort.argtypes = [ctypes.c_int]
                    self.everything_dll.Everything_SetRequestFlags.argtypes = [ctypes.c_uint]
                    self.everything_dll.Everything_QueryW.argtypes = [ctypes.c_bool]
                    self.everything_dll.Everything_GetNumResults.restype = ctypes.c_int
                    self.everything_dll.Everything_IsFolderResult.argtypes = [ctypes.c_int]
                    self.everything_dll.Everything_IsFolderResult.restype = ctypes.c_bool
                    self.everything_dll.Everything_GetResultFullPathNameW.argtypes = [ctypes.c_int, ctypes.c_wchar_p, ctypes.c_int]
                    self.everything_dll.Everything_GetResultFileNameW.argtypes = [ctypes.c_int, ctypes.c_wchar_p, ctypes.c_int]
                    self.everything_dll.Everything_GetResultPathW.argtypes = [ctypes.c_int, ctypes.c_wchar_p, ctypes.c_int]
                    
                    self.available = True
                    # 设置默认请求
                    self.everything_dll.Everything_SetRequestFlags(
                        self.EVERYTHING_REQUEST_FULL_PATH_AND_FILE_NAME |
                        self.EVERYTHING_REQUEST_FILE_NAME |
                        self.EVERYTHING_REQUEST_PATH |
                        self.EVERYTHING_REQUEST_DATE_MODIFIED
                    )
                    return
                except Exception as e:
                    print(f"加载 Everything DLL 失败: {e}")
                    continue
        
        self.available = False
    
    def calculate_score(self, keyword: str, file_name: str) -> int:
        """计算文件搜索结果的相关性分数（与应用评分逻辑完全一致）"""
        name_lower = file_name.lower()
        keyword_lower = keyword.lower()
        keyword_len = len(keyword_lower)
        
        base_score = 0
        boost = 0
        
        # === 1. 精确匹配检查 ===
        if name_lower == keyword_lower:
            base_score = 100
            boost = 1000
        elif keyword_lower in name_lower:
            base_score = 95
            boost = 500
        
        # === 2. 前缀匹配 ===
        if boost == 0:
            if name_lower.startswith(keyword_lower):
                base_score = 98
                boost = 300
        
        # === 3. 各种模糊匹配分数 ===
        scores = []
        
        # WRatio - 综合匹配
        scores.append(('wratio', fuzz.WRatio(keyword_lower, name_lower)))
        
        # Token Set Ratio - 词集合匹配
        scores.append(('token', fuzz.token_set_ratio(keyword_lower, name_lower)))
        
        # Partial Ratio - 子字符串匹配
        scores.append(('partial', fuzz.partial_ratio(keyword_lower, name_lower)))
        
        # Token Sort Ratio - 词排序匹配
        scores.append(('token_sort', fuzz.token_sort_ratio(keyword_lower, name_lower)))
        
        # 取最高的基础分数
        if base_score == 0:
            base_score = max(s[1] for s in scores) if scores else 0
        
        # === 4. 额外加分 ===
        # 如果多个匹配方法都有高分，额外加分
        high_score_count = sum(1 for s in scores if s[1] >= 85)
        boost += high_score_count * 10
        
        # 长度接近加分
        name_len = len(name_lower)
        if keyword_len >= 2 and name_len >= keyword_len:
            length_ratio = keyword_len / name_len
            if length_ratio > 0.5:
                boost += 20 * length_ratio
        
        # === 5. 可执行文件优先 ===
        if name_lower.endswith(('.exe', '.bat', '.cmd', '.py')):
            boost += 50
        
        # === 6. 计算最终分数 ===
        final_score = base_score + boost
        
        return final_score
    
    def search(self, keyword: str, max_results: int = 50) -> List[Dict]:
        """使用 Everything SDK 搜索文件"""
        if not self.available:
            return []
        
        try:
            # 设置搜索关键词
            self.everything_dll.Everything_SetSearchW(keyword)
            
            # 设置最大结果数
            self.everything_dll.Everything_SetMax(max_results)
            
            # 设置排序方式为相关性
            self.everything_dll.Everything_SetSort(self.EVERYTHING_SORT_RELEVANCE)
            
            # 执行搜索
            self.everything_dll.Everything_QueryW(True)
            
            # 获取结果数量
            num_results = self.everything_dll.Everything_GetNumResults()
            
            results = []
            for i in range(num_results):
                # 获取完整路径
                buffer = ctypes.create_unicode_buffer(1024)
                self.everything_dll.Everything_GetResultFullPathNameW(i, buffer, 1024)
                full_path = buffer.value
                
                if not full_path:
                    continue
                
                # 从完整路径中直接提取文件名和目录
                file_name = os.path.basename(full_path)
                file_path = os.path.dirname(full_path)
                
                # 获取是否为文件夹
                is_folder = bool(self.everything_dll.Everything_IsFolderResult(i))
                
                # 计算分数
                score = self.calculate_score(keyword, file_name)
                
                results.append({
                    'name': file_name,
                    'path': full_path,
                    'dir_path': file_path,
                    'type': 'folder' if is_folder else 'file',
                    'icon': full_path,
                    'is_file': True,
                    'score': score
                })
                
                if len(results) >= max_results:
                    break
            
            # 按分数排序
            results.sort(key=lambda x: -x['score'])
            
            return results
        
        except Exception as e:
            print(f"Everything 搜索出错: {e}")
            return []
    
    def search_fallback(self, keyword: str, max_results: int = 50) -> List[Dict]:
        """当 Everything 不可用时的后备搜索方法（简单的本地搜索）"""
        results = []
        
        # 只搜索一些常用目录
        search_dirs = [
            os.path.join(os.path.expanduser("~"), "Desktop"),
            os.path.join(os.path.expanduser("~"), "Documents"),
            os.path.join(os.path.expanduser("~"), "Downloads")
        ]
        
        keyword_lower = keyword.lower()
        
        for directory in search_dirs:
            if not os.path.exists(directory):
                continue
            
            try:
                for item in os.listdir(directory):
                    item_path = os.path.join(directory, item)
                    if keyword_lower in item.lower():
                        
                        is_folder = os.path.isdir(item_path)
                        
                        # 计算分数
                        score = self.calculate_score(keyword, item)
                        
                        results.append({
                            'name': item,
                            'path': item_path,
                            'dir_path': directory,
                            'type': 'folder' if is_folder else 'file',
                            'icon': item_path,
                            'is_file': True,
                            'score': score
                        })
                        
                        if len(results) >= max_results:
                            break
                
                if len(results) >= max_results:
                    break
            
            except Exception:
                continue
        
        # 按分数排序
        results.sort(key=lambda x: -x['score'])
        
        return results
