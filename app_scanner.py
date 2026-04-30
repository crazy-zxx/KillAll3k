import os
import sys
import winreg
import subprocess
from typing import List, Dict

try:
    from pypinyin import pinyin, Style
    from rapidfuzz import fuzz, process
    HAS_LIBS = True
except ImportError:
    HAS_LIBS = False


class AppScanner:
    def __init__(self, settings_manager=None):
        self.apps: List[Dict] = []
        self.processed_apps = []
        self.settings_manager = settings_manager
        self.scan_all_apps()
    
    def scan_all_apps(self):
        """扫描所有应用程序"""
        self.apps.clear()
        self.processed_apps.clear()
        
        # 扫描注册表中的应用
        self.scan_registry_apps()
        
        # 扫描桌面和开始菜单
        self.scan_directory_shortcuts()
        
        # 扫描自定义目录
        self.scan_custom_directories()
        
        # 去重
        self.remove_duplicates()
        
        # 预处理应用数据，添加拼音
        for app in self.apps:
            app_data = {
                'app': app,
                'name': app['name'].lower(),
                'pinyin': self.get_pinyin(app['name']) if HAS_LIBS else ''
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
        if not HAS_LIBS:
            return ''
        
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
                        app_path = self.resolve_lnk(item_path)
                        if app_path and os.path.exists(app_path):
                            self.apps.append({
                                'name': os.path.splitext(item)[0],
                                'path': app_path,
                                'icon': item_path,
                                'type': 'shortcut'
                            })
                    except Exception:
                        pass
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
    
    def resolve_lnk(self, shortcut_path):
        """解析快捷方式"""
        try:
            import pythoncom
            from win32com.shell import shell
            link = pythoncom.CoCreateInstance(
                shell.CLSID_ShellLink,
                None,
                pythoncom.CLSCTX_INPROC_SERVER,
                shell.IID_IShellLink
            )
            link.QueryInterface(pythoncom.IID_IPersistFile).Load(shortcut_path)
            target, _ = link.GetPath(0)
            return target
        except ImportError:
            try:
                # 备用方法：使用 wscript
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', suffix='.vbs', delete=False, encoding='utf-8') as f:
                    f.write(f'''
Set WshShell = CreateObject("WScript.Shell")
Set shortcut = WshShell.CreateShortcut("{shortcut_path}")
WScript.Echo shortcut.TargetPath
''')
                    temp_file = f.name
                result = subprocess.run(
                    ['cscript', '//NoLogo', temp_file],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                os.unlink(temp_file)
                if result.returncode == 0:
                    return result.stdout.strip()
            except Exception:
                pass
        except Exception:
            pass
        return None
    
    def scan_registry_apps(self):
        """从注册表扫描已安装的应用"""
        registry_paths = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall")
        ]
        
        for root, subkey_path in registry_paths:
            try:
                key = winreg.OpenKey(root, subkey_path)
                index = 0
                while True:
                    try:
                        app_key_name = winreg.EnumKey(key, index)
                        index += 1
                        
                        try:
                            app_key = winreg.OpenKey(key, app_key_name)
                            try:
                                display_name = winreg.QueryValueEx(app_key, "DisplayName")[0]
                                
                                display_icon = None
                                try:
                                    display_icon = winreg.QueryValueEx(app_key, "DisplayIcon")[0]
                                except Exception:
                                    pass
                                
                                install_location = None
                                try:
                                    install_location = winreg.QueryValueEx(app_key, "InstallLocation")[0]
                                except Exception:
                                    pass
                                
                                app_path = None
                                if display_icon:
                                    app_path = self.extract_exe_path(display_icon)
                                
                                if not app_path and install_location:
                                    app_path = self.find_exe_in_directory(install_location)
                                
                                if display_name and app_path and os.path.exists(app_path):
                                    self.apps.append({
                                        'name': display_name,
                                        'path': app_path,
                                        'icon': display_icon if display_icon else '',
                                        'type': 'registry'
                                    })
                            except Exception:
                                pass
                        except Exception:
                            pass
                    except OSError:
                        break
            except Exception:
                pass
    
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
    
    def remove_duplicates(self):
        """移除重复的应用"""
        seen = set()
        unique_apps = []
        for app in self.apps:
            key = (app['name'].lower(), app['path'].lower())
            if key not in seen:
                seen.add(key)
                unique_apps.append(app)
        self.apps = unique_apps
    
    def search_apps(self, keyword):
        """模糊搜索应用"""
        keyword = keyword.lower()
        
        if HAS_LIBS:
            return self.search_with_rapidfuzz(keyword)
        else:
            return self.search_simple(keyword)
    
    def search_simple(self, keyword):
        """简单匹配（备用）"""
        results = []
        for app in self.apps:
            app_name = app['name'].lower()
            if keyword in app_name:
                results.append(app)
        return results
    
    def search_with_rapidfuzz(self, keyword):
        """使用 rapidfuzz 进行高级模糊匹配"""
        candidates = []
        
        for app_data in self.processed_apps:
            score = 0
            
            # 1. 原始名称匹配
            name_score = fuzz.partial_ratio(keyword, app_data['name'])
            score = max(score, name_score)
            
            # 2. 拼音匹配
            if app_data['pinyin']:
                pinyin_score = fuzz.partial_ratio(keyword, app_data['pinyin'])
                score = max(score, pinyin_score)
            
            # 3. token 匹配
            token_score = fuzz.token_set_ratio(keyword, app_data['name'])
            score = max(score, token_score)
            
            if score > 50:  # 阈值，只保留匹配度较高的
                candidates.append((app_data['app'], score))
        
        # 按分数排序，降序
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        # 返回应用列表
        return [app for app, score in candidates]
    
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
