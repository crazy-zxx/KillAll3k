import os
import winreg
from typing import List, Dict

from pypinyin import pinyin, Style
from rapidfuzz import fuzz
from pylnk3 import parse


class AppScanner:
    def __init__(self, settings_manager=None):
        self.apps: List[Dict] = []
        self.processed_apps = []
        self.settings_manager = settings_manager
        self.exclude_keywords = [
            'uninstall', '卸载', 'setup', '安装', 'install',
            'unins', 'uninst', 'setup.exe', 'installer'
        ]
        self.scan_all_apps()
    
    def scan_all_apps(self):
        """扫描所有应用程序"""
        self.apps.clear()
        self.processed_apps.clear()
        
        # 扫描桌面和开始菜单
        self.scan_directory_shortcuts()
        
        # 扫描自定义目录
        self.scan_custom_directories()
        
        # 去重
        self.remove_duplicates()
        
        # 过滤卸载、安装类应用
        self.filter_excluded_apps()
        
        # 预处理应用数据，添加拼音
        for app in self.apps:
            app_data = {
                'app': app,
                'name': app['name'].lower(),
                'pinyin': self.get_pinyin(app['name'])
            }
            self.processed_apps.append(app_data)
        
        # 按名称排序
        self.apps.sort(key=lambda x: x['name'].lower())
    
    def scan_custom_directories(self):
        """扫描用户自定义的目录"""
        if self.settings_manager:
            custom_dirs = self.settings_manager.get('custom_scan_dirs')
            for directory in custom_dirs:
                self.scan_directory(directory, recursive=True, max_depth=2)
    
    def get_pinyin(self, text):
        """获取文本的拼音表示"""
        try:
            # 获取拼音，不带声调
            pinyin_list = pinyin(text, style=Style.NORMAL, errors='ignore')
            # 拼接成字符串
            full_pinyin = ''.join([item[0] for item in pinyin_list])
            # 也获取首字母拼音
            initials = ''.join([item[0][0] if item[0] else '' for item in pinyin_list])
            return f"{full_pinyin} {initials}"
        except Exception:
            return ''
    
    def scan_directory_shortcuts(self):
        """扫描常见的快捷方式目录"""
        directories = [
            os.path.join(os.path.expanduser("~"), "Desktop"),
            os.path.join(os.environ.get("PUBLIC", ""), "Desktop"),
            os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Microsoft", "Windows", "Start Menu", "Programs"),
            os.path.join(os.environ.get("PROGRAMDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs")
        ]
        
        for directory in directories:
            self.scan_directory(directory, recursive=True, max_depth=3)
    
    def scan_directory(self, directory, recursive=False, max_depth=3, current_depth=0):
        """扫描目录下的 .lnk 和 .exe 文件，限制递归深度"""
        if not os.path.exists(directory):
            return
        
        if current_depth >= max_depth:
            return
        
        try:
            for item in os.listdir(directory):
                item_path = os.path.join(directory, item)
                
                if os.path.isdir(item_path) and recursive:
                    self.scan_directory(item_path, recursive=True, max_depth=max_depth, current_depth=current_depth + 1)
                elif item.lower().endswith('.lnk'):
                    try:
                        lnk_path, lnk_icon = self.parse_lnk(item_path)
                        if lnk_path:
                            self.apps.append({
                                'name': os.path.splitext(item)[0],
                                'path': lnk_path,
                                'icon': lnk_icon if lnk_icon else lnk_path,
                                'type': 'shortcut'
                            })
                        else:
                            self.apps.append({
                                'name': os.path.splitext(item)[0],
                                'path': item_path,
                                'icon': item_path,
                                'type': 'shortcut'
                            })
                    except Exception:
                        self.apps.append({
                            'name': os.path.splitext(item)[0],
                            'path': item_path,
                            'icon': item_path,
                            'type': 'shortcut'
                        })
                elif item.lower().endswith('.exe'):
                    try:
                        self.apps.append({
                            'name': os.path.splitext(item)[0],
                            'path': item_path,
                            'icon': item_path,
                            'type': 'exe'
                        })
                    except Exception:
                        pass
        except Exception:
            pass
    
    def parse_lnk(self, lnk_path):
        """使用 pylnk3 解析 .lnk 文件，获取目标路径和图标信息"""
        try:
            with open(lnk_path, 'rb') as f:
                lnk = parse(f)
            
            target_path = None
            icon_path = None
            
            # 获取目标路径
            if hasattr(lnk, 'link_target_id_list') and lnk.link_target_id_list:
                # 尝试从 link_target_id_list 获取路径
                if hasattr(lnk.link_target_id_list, 'path'):
                    target_path = lnk.link_target_id_list.path
            
            # 如果上面没有获取到，尝试从相对路径或绝对路径获取
            if not target_path and hasattr(lnk, 'link_info'):
                if hasattr(lnk.link_info, 'local_base_path'):
                    target_path = lnk.link_info.local_base_path
                elif hasattr(lnk.link_info, 'path'):
                    target_path = lnk.link_info.path
            
            # 获取图标信息
            if hasattr(lnk, 'icon_location'):
                icon_location = lnk.icon_location
                if icon_location:
                    # 分离图标路径和索引
                    icon_parts = icon_location.split(',')
                    icon_path = icon_parts[0].strip()
            
            # 验证路径是否存在
            if target_path and not os.path.exists(target_path):
                target_path = None
            if icon_path and not os.path.exists(icon_path):
                icon_path = None
            
            return target_path, icon_path
        except Exception:
            return None, None
    
    
    def extract_exe_path(self, display_icon):
        """从 DisplayIcon 提取 exe 路径"""
        if not display_icon:
            return None
        
        # 处理类似 "C:\app.exe,0" 的格式
        icon_path = display_icon.split(',')[0].strip('"').strip("'")
        if icon_path.lower().endswith('.exe') and os.path.exists(icon_path):
            return icon_path
        
        # 如果只是目录，尝试查找 exe
        if os.path.isdir(icon_path):
            return self.find_exe_in_directory(icon_path)
        
        return None
    
    def find_exe_in_directory(self, directory):
        """在目录中查找 exe 文件"""
        if not os.path.exists(directory):
            return None
        
        try:
            for item in os.listdir(directory):
                item_path = os.path.join(directory, item)
                if item.lower().endswith('.exe') and os.path.isfile(item_path):
                    return item_path
        except Exception:
            pass
        return None
    
    def is_excluded(self, app):
        """检查应用是否应该被排除（卸载、安装程序或用户自定义）"""
        name_lower = app['name'].lower()
        path_lower = app['path'].lower()
        
        # 检查默认排除关键词
        for keyword in self.exclude_keywords:
            if keyword in name_lower or keyword in path_lower:
                return True
        
        # 检查用户自定义排除名称
        if self.settings_manager:
            exclude_names = self.settings_manager.get('exclude_app_names')
            for exclude_name in exclude_names:
                if exclude_name.lower() in name_lower:
                    return True
        
        return False
    
    def remove_duplicates(self):
        """移除重复的应用"""
        seen = set()
        unique_apps = []
        for app in self.apps:
            key = app['name'].lower()
            if key not in seen:
                seen.add(key)
                unique_apps.append(app)
        self.apps = unique_apps
    
    def filter_excluded_apps(self):
        """过滤掉卸载、安装类应用"""
        self.apps = [app for app in self.apps if not self.is_excluded(app)]
    
    def search_apps(self, keyword):
        """模糊搜索应用"""
        keyword = keyword.lower()
        return self.search_with_rapidfuzz(keyword)
    
    def search_with_rapidfuzz(self, keyword):
        """使用 rapidfuzz 进行高级模糊匹配"""
        candidates = []
        keyword_len = len(keyword)
        
        for app_data in self.processed_apps:
            name = app_data['name']
            pinyin = app_data['pinyin']
            base_score = 0
            boost = 0
            
            # === 1. 精确匹配检查 ===
            if name == keyword:
                base_score = 100
                boost = 1000
            elif keyword in name:
                base_score = 95
                boost = 500
            elif pinyin and keyword in pinyin:
                base_score = 90
                boost = 400
            
            # === 2. 前缀匹配 ===
            if boost == 0:
                if name.startswith(keyword):
                    base_score = 98
                    boost = 300
                elif pinyin and pinyin.startswith(keyword):
                    base_score = 95
                    boost = 250
            
            # === 3. 各种模糊匹配分数 ===
            scores = []
            
            # WRatio - 综合匹配
            scores.append(('wratio', fuzz.WRatio(keyword, name)))
            
            # Token Set Ratio - 词集合匹配
            scores.append(('token', fuzz.token_set_ratio(keyword, name)))
            
            # Partial Ratio - 子字符串匹配
            scores.append(('partial', fuzz.partial_ratio(keyword, name)))
            
            # Token Sort Ratio - 词排序匹配
            scores.append(('token_sort', fuzz.token_sort_ratio(keyword, name)))
            
            # 拼音匹配
            if pinyin:
                scores.append(('pinyin_wratio', fuzz.WRatio(keyword, pinyin)))
                scores.append(('pinyin_partial', fuzz.partial_ratio(keyword, pinyin)))
            
            # 取最高的基础分数
            if base_score == 0:
                base_score = max(s[1] for s in scores) if scores else 0
            
            # === 4. 额外加分 ===
            # 如果多个匹配方法都有高分，额外加分
            high_score_count = sum(1 for s in scores if s[1] >= 85)
            boost += high_score_count * 10
            
            # 长度接近加分
            name_len = len(name)
            if keyword_len >= 2 and name_len >= keyword_len:
                length_ratio = keyword_len / name_len
                if length_ratio > 0.5:
                    boost += 20 * length_ratio
            
            # === 5. 计算最终分数 ===
            final_score = base_score + boost
            
            if base_score >= 50:
                candidates.append((app_data['app'], final_score, base_score))
        
        # 排序：先按最终分数，再按基础分数
        candidates.sort(key=lambda x: (-x[1], -x[2]))
        
        # 返回应用列表
        return [app for app, _, _ in candidates]
    
    def launch_app(self, app_path):
        """启动应用程序"""
        try:
            if os.path.exists(app_path):
                os.startfile(app_path)
                return True
        except Exception as e:
            print(f"启动应用失败: {e}")
            return False
        return False
