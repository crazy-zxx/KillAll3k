import ctypes
import json
import os
import subprocess
import sys
import winreg

import requests
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QPalette, QColor, QFont
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QCheckBox, QGroupBox,
    QListWidget, QListWidgetItem, QStackedWidget, QLineEdit, QPushButton, QScrollArea,
    QFormLayout, QMessageBox, QFrame, QFileDialog
)


class SignalHandler(QObject):
    toggle_window = pyqtSignal()
    show_window = pyqtSignal()
    show_settings = pyqtSignal()
    show_clipboard = pyqtSignal()
    take_screenshot = pyqtSignal()
    quit_app = pyqtSignal()
    theme_changed = pyqtSignal(str)
    clipboard_settings_changed = pyqtSignal()
    search_hotkey_changed = pyqtSignal()
    screenshot_hotkey_changed = pyqtSignal()


class SettingsManager:
    @staticmethod
    def get_default_screenshot_path():
        """获取当前用户的默认截图保存目录"""
        try:
            # 获取用户主目录
            user_profile = os.environ.get('USERPROFILE')
            if user_profile:
                # 尝试常见的截图保存路径
                screenshots_path = os.path.join(user_profile, 'Pictures', 'Screenshots')
                if os.path.exists(screenshots_path):
                    return screenshots_path
                # 如果不存在，尝试 Pictures 目录
                pictures_path = os.path.join(user_profile, 'Pictures')
                if os.path.exists(pictures_path):
                    return pictures_path
                # 否则返回用户主目录
                return user_profile
        except Exception:
            pass
        # 如果获取失败，返回一个合理的默认路径
        return 'C:\\Users\\Public\\Pictures'
    
    def __init__(self):
        self.settings_file = self.resource_path('settings.json')
        self.default_settings = {
            'theme': 'auto',
            'auto_start': False,
            'show_notification': False,
            'run_as_admin': False,
            'ai_models': [],
            'proxy_enabled': False,
            'proxy_address': '',
            'proxy_port': '',
            'proxy_username': '',
            'proxy_password': '',
            'custom_scan_dirs': [],
            'exclude_app_names': [],
            'enable_file_search': True,
            'max_file_results': 30,
            'max_app_results': 20,
            'everything_path': '',
            'everything_dll_path': '',
            'clipboard_enabled': True,
            'clipboard_history_limit': 0,
            'clipboard_hotkey': 'win+v',
            'search_hotkey': 'alt+space',
            'screenshot_enabled': True,
            'screenshot_hotkey': 'ctrl+alt+a',
            'screenshot_action': 'annotate',
            'screenshot_save_path': self.get_default_screenshot_path(),
            'screenshot_format': 'png',
            'ocr_api_token': '',
            'ocr_api_url': '',
            'ocr_model': 'pp-ocrv5'
        }
        self.settings = self.load_settings()

    def resource_path(self, relative_path):
        """获取打包后资源文件的绝对路径"""
        if getattr(sys, 'frozen', False):
            # 打包后的 exe：sys.executable 是 exe 的完整路径
            base_path = os.path.dirname(sys.executable)
        else:
            # 开发环境，直接使用当前路径
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    def load_settings(self):
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    return {**self.default_settings, **json.load(f)}
            except:
                return self.default_settings.copy()
        return self.default_settings.copy()
    
    def save_settings(self):
        with open(self.settings_file, 'w', encoding='utf-8') as f:
            json.dump(self.settings, f, ensure_ascii=False, indent=2)
    
    def get(self, key, default=None):
        return self.settings.get(key, self.default_settings.get(key, default))
    
    def set(self, key, value):
        self.settings[key] = value
        self.save_settings()


class ThemeManager:
    def __init__(self, signal_handler):
        self.signal_handler = signal_handler
        self.current_theme = 'auto'
    
    def is_system_dark(self):
        try:

            registry = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
            key = winreg.OpenKey(registry, r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize')
            value, _ = winreg.QueryValueEx(key, 'AppsUseLightTheme')
            return value == 0
        except:
            return False
    
    def get_effective_theme(self):
        if self.current_theme == 'auto':
            return 'dark' if self.is_system_dark() else 'light'
        return self.current_theme
    
    def apply_theme(self, theme):
        self.current_theme = theme

        app = QApplication.instance()
        if not app:
            return
        
        if theme == 'auto':
            theme = 'dark' if self.is_system_dark() else 'light'
        
        palette = QPalette()
        if theme == 'dark':
            palette.setColor(QPalette.ColorRole.Window, QColor(30, 41, 59))
            palette.setColor(QPalette.ColorRole.WindowText, QColor(226, 232, 240))
            palette.setColor(QPalette.ColorRole.Base, QColor(45, 55, 72))
            palette.setColor(QPalette.ColorRole.AlternateBase, QColor(51, 65, 85))
            palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(226, 232, 240))
            palette.setColor(QPalette.ColorRole.ToolTipText, QColor(15, 23, 42))
            palette.setColor(QPalette.ColorRole.Text, QColor(226, 232, 240))
            palette.setColor(QPalette.ColorRole.Button, QColor(51, 65, 85))
            palette.setColor(QPalette.ColorRole.ButtonText, QColor(226, 232, 240))
            palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 255, 255))
            palette.setColor(QPalette.ColorRole.Link, QColor(96, 165, 250))
            palette.setColor(QPalette.ColorRole.Highlight, QColor(96, 165, 250))
            palette.setColor(QPalette.ColorRole.HighlightedText, QColor(15, 23, 42))
        else:
            palette.setColor(QPalette.ColorRole.Window, QColor(248, 250, 252))
            palette.setColor(QPalette.ColorRole.WindowText, QColor(15, 23, 42))
            palette.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
            palette.setColor(QPalette.ColorRole.AlternateBase, QColor(241, 245, 249))
            palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(15, 23, 42))
            palette.setColor(QPalette.ColorRole.ToolTipText, QColor(248, 250, 252))
            palette.setColor(QPalette.ColorRole.Text, QColor(15, 23, 42))
            palette.setColor(QPalette.ColorRole.Button, QColor(241, 245, 249))
            palette.setColor(QPalette.ColorRole.ButtonText, QColor(15, 23, 42))
            palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
            palette.setColor(QPalette.ColorRole.Link, QColor(59, 130, 246))
            palette.setColor(QPalette.ColorRole.Highlight, QColor(59, 130, 246))
            palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
        
        app.setPalette(palette)
    
    def get_colors(self):
        theme = self.get_effective_theme()
        if theme == 'dark':
            return {
                'window': '#1e293b',
                'window_text': '#e2e8f0',
                'base': '#2d3748',
                'base_text': '#e2e8f0',
                'button': '#334155',
                'button_text': '#e2e8f0',
                'border': '#475569',
                'highlight': '#516F9C',
                'highlight_text': '#ffffff',
                'hover': '#3b4a60',
                'surface': '#2d3748',
                'text_secondary': '#94a3b8',
                'success': '#10b981',
                'warning': '#f59e0b',
                'error': '#ef4444',
                'info': '#60a5fa'
            }
        else:
            return {
                'window': '#f8fafc',
                'window_text': '#0f172a',
                'base': '#ffffff',
                'base_text': '#0f172a',
                'button': '#f1f5f9',
                'button_text': '#0f172a',
                'border': '#e2e8f0',
                'highlight': '#3b82f6',
                'highlight_text': '#000000',
                'hover': '#e2e8f0',
                'surface': '#ffffff',
                'text_secondary': '#64748b',
                'success': '#10b981',
                'warning': '#f59e0b',
                'error': '#ef4444',
                'info': '#3b82f6'
            }
    
    def get_line_edit_style(self):
        colors = self.get_colors()
        return f"""
            QLineEdit {{
                background-color: {colors['base']};
                color: {colors['base_text']};
                border: 1px solid {colors['border']};
                border-radius: 6px;
                padding: 8px 12px;
            }}
            QLineEdit:focus {{
                border: 1px solid {colors['highlight']};
            }}
        """
    
    def get_push_button_style(self, btn_type='default'):
        colors = self.get_colors()
        if btn_type == 'icon':
            # 图标按钮专用样式，无padding
            return f"""
                QPushButton {{
                    background-color: {colors['button']};
                    color: {colors['button_text']};
                    border: 1px solid {colors['border']};
                    border-radius: 6px;
                    padding: 0px;
                    font-size: 18px;
                }}
                QPushButton:hover {{
                    background-color: {colors['hover']};
                }}
            """
        elif btn_type == 'primary':
            return f"""
                QPushButton {{
                    background-color: {colors['highlight']};
                    color: {colors['highlight_text']};
                    border: none;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: #3b82f6;
                }}
                QPushButton:pressed {{
                    background-color: #2563eb;
                }}
            """
        elif btn_type == 'success':
            return f"""
                QPushButton {{
                    background-color: {colors['success']};
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: #059669;
                }}
            """
        elif btn_type == 'danger':
            return f"""
                QPushButton {{
                    background-color: {colors['error']};
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: #dc2626;
                }}
            """
        else:
            return f"""
                QPushButton {{
                    background-color: {colors['button']};
                    color: {colors['button_text']};
                    border: 1px solid {colors['border']};
                    border-radius: 6px;
                    padding: 8px 16px;
                }}
                QPushButton:hover {{
                    background-color: {colors['hover']};
                }}
            """
    
    def get_combobox_style(self):
        colors = self.get_colors()
        return f"""
            QComboBox {{
                background-color: {colors['base']};
                color: {colors['base_text']};
                border: 1px solid {colors['border']};
                border-radius: 6px;
                padding: 8px 32px 8px 12px;
                min-height: 30px;
            }}
            QComboBox:hover {{
                border: 1px solid {colors['highlight']};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 30px;
                background-color: transparent;
            }}
            QComboBox::down-arrow {{
                width: 0;
                height: 0;
                border-left: 4px solid  {colors['base']};
                border-right: 4px solid  {colors['base']};
                border-top: 6px solid {colors['text_secondary']};
                subcontrol-origin: padding;
                subcontrol-position: right center;
                right: 8px;
            }}
            QComboBox::down-arrow:hover {{
                border-top-color: {colors['highlight']};
            }}
            QComboBox::down-arrow:on {{
                border-top-color: {colors['highlight']};
            }}
            QComboBox QAbstractItemView {{
                background-color: {colors['window']};
                color: {colors['window_text']};
                border: 1px solid {colors['border']};
                border-radius: 6px;
                selection-background-color: {colors['highlight']};
                selection-color: {colors['highlight_text']};
                padding: 4px;
                outline: none;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 8px 12px;
                border-radius: 4px;
                margin: 2px;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: {colors['hover']};
            }}
        """
    
    def get_list_widget_style(self):
        colors = self.get_colors()
        return f"""
            QListWidget {{
                background-color: {colors['base']};
                color: {colors['base_text']};
                border: 1px solid {colors['border']};
                border-radius: 8px;
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 8px;
                border-radius: 4px;
                margin: 2px 0;
            }}
            QListWidget::item:selected {{
                background-color: {colors['highlight']};
                color: {colors['highlight_text']};
            }}
            QListWidget::item:hover:!selected {{
                background-color: {colors['hover']};
            }}
        """
    
    def get_checkbox_style(self):
        colors = self.get_colors()
        return f"""
            QCheckBox {{
                color: {colors['window_text']};
                padding: 5px;
                font-size: 14px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 2px solid {colors['border']};
                border-radius: 4px;
                background-color: {colors['base']};
            }}
            QCheckBox::indicator:checked {{
                background-color: {colors['highlight']};
                border-color: {colors['highlight']};
            }}
            QCheckBox::indicator:hover {{
                border-color: {colors['highlight']};
            }}
        """
    
    def get_groupbox_style(self):
        colors = self.get_colors()
        return f"""
            QGroupBox {{
                color: {colors['window_text']};
                border: 1px solid {colors['border']};
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 15px;
                font-weight: bold;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }}
        """
    
    def get_textedit_style(self):
        colors = self.get_colors()
        return f"""
            QTextEdit {{
                background-color: {colors['base']};
                color: {colors['base_text']};
                border: 1px solid {colors['border']};
                border-radius: 8px;
                padding: 12px;
            }}
            QTextEdit:focus {{
                border: 1px solid {colors['highlight']};
            }}
        """
    
    def get_scrollbar_style(self):
        colors = self.get_colors()
        return f"""
            QScrollBar:vertical {{
                width: 10px;
                background-color: {colors['window']};
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {colors['border']};
                border-radius: 5px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {colors['text_secondary']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar:horizontal {{
                height: 10px;
                background-color: {colors['window']};
                border-radius: 5px;
            }}
            QScrollBar::handle:horizontal {{
                background-color: {colors['border']};
                border-radius: 5px;
                min-width: 30px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background-color: {colors['text_secondary']};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
        """
    
    def get_sidebar_style(self):
        colors = self.get_colors()
        return f"""
            QListWidget {{
                outline: none; 
                background-color: {colors['surface']};
                border-right: 1px solid {colors['border']};
                font-size: 14px;
            }}
            QListWidget::item {{
                padding: 12px 20px;
                color: {colors['text_secondary']};
                border: none;
            }}
            QListWidget::item:selected {{
                background-color: {colors['hover']};
                color: {colors['highlight']};
                font-weight: bold;
            }}
            QListWidget::item:hover {{
                background-color: {colors['hover']};
            }}
        """


class AutoStartManager:
    def __init__(self):
        self.app_name = "KillAll3k (要你命三千)"
        self.registry_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    
    def is_admin(self):
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False
    
    def get_auto_start(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.registry_path, 0, winreg.KEY_READ)
            winreg.QueryValueEx(key, self.app_name)
            winreg.CloseKey(key)
            return True
        except:
            return False
    
    def get_executable_path(self):
        """获取可执行文件的真实路径，支持py和打包后的exe"""
        if getattr(sys, 'frozen', False):
            # PyInstaller打包后的exe
            return sys.executable
        else:
            # 开发环境下的py文件
            return os.path.abspath(sys.argv[0])
    
    def set_auto_start(self, enable):
        try:

            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.registry_path, 0, winreg.KEY_WRITE)
            if enable:
                exe_path = self.get_executable_path()
                if exe_path.endswith('.py'):
                    python_path = sys.executable
                    winreg.SetValueEx(key, self.app_name, 0, winreg.REG_SZ, f'"{python_path}" "{exe_path}"')
                else:
                    winreg.SetValueEx(key, self.app_name, 0, winreg.REG_SZ, f'"{exe_path}"')
            else:
                try:
                    winreg.DeleteValue(key, self.app_name)
                except:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            print(f"设置开机自启动失败: {e}")
    
    def run_as_admin(self):
        """以管理员权限重新启动程序"""
        try:
            exe_path = self.get_executable_path()
            if exe_path.endswith('.py'):
                python_path = sys.executable
                ctypes.windll.shell32.ShellExecuteW(None, "runas", python_path, f'"{exe_path}"', None, 1)
            else:
                ctypes.windll.shell32.ShellExecuteW(None, "runas", exe_path, None, None, 1)
            sys.exit(0)
        except Exception as e:
            print(f"提权失败: {e}")


class CollapsibleGroup(QWidget):
    def __init__(self, title, parent_widget, index, theme_manager=None):
        super().__init__()
        self.is_expanded = False
        self.index = index
        self.parent_widget = parent_widget
        self.theme_manager = theme_manager
        self.init_ui(title)
    
    def init_ui(self, title):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 标题栏
        header = QPushButton()
        self.header_btn = header
        header.clicked.connect(self.toggle)
        
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        self.arrow_label = QLabel("▼")
        self.title_label = QLabel(title)
        self.enabled_label = QLabel("")
        
        header_layout.addWidget(self.arrow_label)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.enabled_label)
        
        header.setLayout(header_layout)
        layout.addWidget(header)
        
        # 内容区
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(15, 10, 15, 15)
        self.content_widget.setLayout(self.content_layout)
        layout.addWidget(self.content_widget)
        
        self.setLayout(layout)
        
        # 设置初始状态
        self.content_widget.setVisible(self.is_expanded)
        self.arrow_label.setText("▼" if self.is_expanded else "▶")
        
        # 应用主题样式
        self.apply_theme()
    
    def apply_theme(self):
        if not self.theme_manager:
            return
        
        colors = self.theme_manager.get_colors()
        
        self.header_btn.setStyleSheet(f"""
            QPushButton {{
                text-align: left;
                padding: 12px 15px;
                background-color: {colors['surface']};
                border: 1px solid {colors['border']};
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
                color: {colors['window_text']};
            }}
            QPushButton:hover {{
                background-color: {colors['hover']};
            }}
        """)
        
        self.arrow_label.setStyleSheet(f"font-size: 12px; color: {colors['window_text']};")
        self.title_label.setStyleSheet(f"color: {colors['window_text']};")
        
        self.set_enabled_status(self.enabled_label.text() == "(已启用)")
    
    def toggle(self):
        self.is_expanded = not self.is_expanded
        self.content_widget.setVisible(self.is_expanded)
        self.arrow_label.setText("▼" if self.is_expanded else "▶")
    
    def set_enabled_status(self, enabled):
        self.enabled_label.setText("(已启用)" if enabled else "(已禁用)")
        colors = self.theme_manager.get_colors() if self.theme_manager else None
        success_color = colors['success'] if colors else '#10b981'
        secondary_color = colors['text_secondary'] if colors else '#94a3b8'
        self.enabled_label.setStyleSheet(f"color: {success_color};" if enabled else f"color: {secondary_color};")
    
    def update_title(self, title):
        self.title_label.setText(title)


class SettingsWindow(QWidget):
    def __init__(self, settings_manager, theme_manager, auto_start_manager, signal_handler):
        super().__init__()
        self.settings_manager = settings_manager
        self.theme_manager = theme_manager
        self.auto_start_manager = auto_start_manager
        self.signal_handler = signal_handler
        self.ai_model_inputs = []
        self.ai_collapsible_groups = []
        self.scan_dirs_list = None
        self.widgets_to_style = []  # 保存需要应用主题的控件
        self.providers = {
            'OpenAI': {'api_url': 'https://api.openai.com/v1/chat/completions', 'model': 'gpt-3.5-turbo'},
            'DeepSeek': {'api_url': 'https://api.deepseek.com/v1/chat/completions', 'model': 'deepseek-chat'},
            '硅基流动': {'api_url': 'https://api.siliconflow.cn/v1/chat/completions', 'model': 'Qwen/Qwen2.5-7B-Instruct'},
            '魔搭': {'api_url': 'https://api-inference.modelscope.cn/v1/chat/completions', 'model': 'Qwen/Qwen2.5-7B-Instruct'},
            'OpenRouter': {'api_url': 'https://openrouter.ai/api/v1/chat/completions', 'model': 'openai/gpt-3.5-turbo'},
            'Ollama': {'api_url': 'http://localhost:11434/api/chat', 'model': 'llama2'}
        }
        self.init_ui()
        self.load_settings()
        # 连接主题变化信号
        self.signal_handler.theme_changed.connect(self.on_theme_changed_external)
    
    def init_ui(self):
        self.setWindowTitle("设置")
        self.setFixedSize(800, 600)
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 侧边栏
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(200)
        self.sidebar.setFrameShape(QFrame.Shape.NoFrame)
        self.widgets_to_style.append(('sidebar', self.sidebar))
        
        item1 = QListWidgetItem("⚙️ 系统功能设置")
        item2 = QListWidgetItem("🔌 系统代理设置")
        item3 = QListWidgetItem("🤖 AI 模型配置")
        item4 = QListWidgetItem("🚀 启动程序扫描")
        item5 = QListWidgetItem("📁 文件搜索设置")
        item6 = QListWidgetItem("📋 剪贴板设置")
        item7 = QListWidgetItem("📷 截图设置")
        self.sidebar.addItem(item1)
        self.sidebar.addItem(item2)
        self.sidebar.addItem(item3)
        self.sidebar.addItem(item4)
        self.sidebar.addItem(item5)
        self.sidebar.addItem(item6)
        self.sidebar.addItem(item7)
        self.sidebar.setCurrentRow(0)
        self.sidebar.currentRowChanged.connect(self.switch_page)
        
        # 主内容区
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.addWidget(self.create_system_settings_page())
        self.stacked_widget.addWidget(self.create_proxy_settings_page())
        self.stacked_widget.addWidget(self.create_ai_settings_page())
        self.stacked_widget.addWidget(self.create_scan_settings_page())
        self.stacked_widget.addWidget(self.create_file_search_settings_page())
        self.stacked_widget.addWidget(self.create_clipboard_settings_page())
        self.stacked_widget.addWidget(self.create_screenshot_settings_page())
        
        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(self.stacked_widget, 1)
        
        self.setLayout(main_layout)
        
        # 应用主题样式
        self.apply_theme()
    
    def create_system_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        title = QLabel("系统功能设置")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Weight.Bold))
        # 设置标题颜色
        self.widgets_to_style.append(('title', title))
        layout.addWidget(title)
        
        # 主题设置
        theme_group = QGroupBox("主题设置")
        self.widgets_to_style.append(('groupbox', theme_group))
        theme_layout = QVBoxLayout()
        theme_layout.setSpacing(15)
        
        theme_label = QLabel("主题模式：")
        self.widgets_to_style.append(('label', theme_label))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["自动跟随系统", "浅色主题", "深色主题"])
        self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)
        self.widgets_to_style.append(('combobox', self.theme_combo))
        
        theme_layout.addWidget(theme_label)
        theme_layout.addWidget(self.theme_combo)
        theme_group.setLayout(theme_layout)
        layout.addWidget(theme_group)
        
        # 系统设置
        system_group = QGroupBox("系统设置")
        self.widgets_to_style.append(('groupbox', system_group))
        system_layout = QVBoxLayout()
        system_layout.setSpacing(15)
        
        self.auto_start_check = QCheckBox("开机自启动")
        self.auto_start_check.toggled.connect(self.on_auto_start_changed)
        self.widgets_to_style.append(('checkbox', self.auto_start_check))
        
        self.notification_check = QCheckBox("启动通知")
        self.notification_check.toggled.connect(self.on_notification_changed)
        self.widgets_to_style.append(('checkbox', self.notification_check))
        
        self.admin_check = QCheckBox("管理员权限运行")
        self.admin_check.toggled.connect(self.on_admin_changed)
        self.widgets_to_style.append(('checkbox', self.admin_check))
        
        system_layout.addWidget(self.auto_start_check)
        system_layout.addWidget(self.notification_check)
        system_layout.addWidget(self.admin_check)
        system_group.setLayout(system_layout)
        layout.addWidget(system_group)
        
        # 快捷键设置
        hotkey_group = QGroupBox("快捷键设置")
        self.widgets_to_style.append(('groupbox', hotkey_group))
        hotkey_layout = QFormLayout()
        hotkey_layout.setSpacing(15)
        
        self.search_hotkey_input = QLineEdit()
        self.search_hotkey_input.setPlaceholderText("例如：alt+space")
        self.widgets_to_style.append(('lineedit', self.search_hotkey_input))
        
        hotkey_layout.addRow("唤醒搜索框快捷键：", self.search_hotkey_input)
        hotkey_group.setLayout(hotkey_layout)
        layout.addWidget(hotkey_group)
        
        # 保存按钮
        save_system_btn = QPushButton("💾 保存系统设置")
        save_system_btn.clicked.connect(self.save_system_settings)
        self.widgets_to_style.append(('pushbutton_primary', save_system_btn))
        layout.addWidget(save_system_btn)
        
        layout.addStretch()
        page.setLayout(layout)
        return page
    
    def create_proxy_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        title = QLabel("系统代理设置")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Weight.Bold))
        self.widgets_to_style.append(('title', title))
        layout.addWidget(title)
        
        # 代理设置
        proxy_group = QGroupBox("代理配置")
        self.widgets_to_style.append(('groupbox', proxy_group))
        proxy_layout = QVBoxLayout()
        proxy_layout.setSpacing(15)
        
        self.proxy_enabled_check = QCheckBox("启用代理")
        self.proxy_enabled_check.toggled.connect(self.on_proxy_enabled_changed)
        self.widgets_to_style.append(('checkbox', self.proxy_enabled_check))
        
        # 代理表单
        proxy_form = QFormLayout()
        proxy_form.setSpacing(12)
        
        self.proxy_address_input = QLineEdit()
        self.proxy_address_input.setPlaceholderText("例如：127.0.0.1")
        self.widgets_to_style.append(('lineedit', self.proxy_address_input))
        proxy_form.addRow("代理地址:", self.proxy_address_input)
        
        self.proxy_port_input = QLineEdit()
        self.proxy_port_input.setPlaceholderText("例如：7890")
        self.widgets_to_style.append(('lineedit', self.proxy_port_input))
        proxy_form.addRow("代理端口:", self.proxy_port_input)
        
        self.proxy_username_input = QLineEdit()
        self.proxy_username_input.setPlaceholderText("可选")
        self.widgets_to_style.append(('lineedit', self.proxy_username_input))
        proxy_form.addRow("用户名:", self.proxy_username_input)
        
        self.proxy_password_input = QLineEdit()
        self.proxy_password_input.setPlaceholderText("可选")
        self.proxy_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.widgets_to_style.append(('lineedit', self.proxy_password_input))
        proxy_form.addRow("密码:", self.proxy_password_input)
        
        # 测试和保存按钮
        proxy_btn_layout = QHBoxLayout()
        proxy_btn_layout.addStretch()
        
        test_proxy_btn = QPushButton("🔌 测试连通性")
        test_proxy_btn.clicked.connect(self.test_proxy_connection)
        self.widgets_to_style.append(('pushbutton_success', test_proxy_btn))
        proxy_btn_layout.addWidget(test_proxy_btn)
        
        save_proxy_btn = QPushButton("💾 保存代理配置")
        save_proxy_btn.clicked.connect(self.save_proxy_settings)
        self.widgets_to_style.append(('pushbutton_primary', save_proxy_btn))
        proxy_btn_layout.addWidget(save_proxy_btn)
        
        proxy_layout.addWidget(self.proxy_enabled_check)
        proxy_layout.addLayout(proxy_form)
        proxy_layout.addLayout(proxy_btn_layout)
        proxy_group.setLayout(proxy_layout)
        layout.addWidget(proxy_group)
        
        layout.addStretch()
        page.setLayout(layout)
        return page
    
    def create_ai_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        title = QLabel("AI 模型配置")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Weight.Bold))
        self.widgets_to_style.append(('title', title))
        layout.addWidget(title)
        
        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        scroll_content = QWidget()
        self.ai_settings_layout = QVBoxLayout()
        self.ai_settings_layout.setSpacing(15)
        
        # 已添加的模型区域（容器）
        self.models_container = QWidget()
        self.models_layout = QVBoxLayout()
        self.models_layout.setContentsMargins(0, 0, 0, 0)
        self.models_layout.setSpacing(10)
        self.models_container.setLayout(self.models_layout)
        self.ai_settings_layout.addWidget(self.models_container)
        
        # 添加模型区域
        add_group = QGroupBox("➕ 添加新模型")
        self.widgets_to_style.append(('groupbox', add_group))
        
        add_layout = QFormLayout()
        add_layout.setSpacing(12)
        add_layout.setContentsMargins(15, 20, 15, 15)
        
        # 提供商选择
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(self.providers.keys())
        self.widgets_to_style.append(('combobox', self.provider_combo))
        self.provider_combo.currentTextChanged.connect(self.on_provider_changed)
        add_layout.addRow("选择提供商:", self.provider_combo)
        
        # 自定义名称
        self.custom_name_input = QLineEdit()
        self.custom_name_input.setPlaceholderText("留空则使用提供商名称")
        self.widgets_to_style.append(('lineedit', self.custom_name_input))
        add_layout.addRow("自定义名称:", self.custom_name_input)
        
        # API URL
        self.new_api_url_input = QLineEdit(self.providers['OpenAI']['api_url'])
        self.widgets_to_style.append(('lineedit', self.new_api_url_input))
        add_layout.addRow("API 地址:", self.new_api_url_input)
        
        # API Key
        self.new_api_key_input = QLineEdit()
        self.new_api_key_input.setPlaceholderText("请输入 API Key")
        self.new_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.widgets_to_style.append(('lineedit', self.new_api_key_input))
        add_layout.addRow("API Key:", self.new_api_key_input)
        
        # Model
        self.new_model_input = QLineEdit(self.providers['OpenAI']['model'])
        self.widgets_to_style.append(('lineedit', self.new_model_input))
        add_layout.addRow("模型名称:", self.new_model_input)
        
        # 添加按钮和测试按钮
        add_btn_layout = QHBoxLayout()
        add_btn_layout.addStretch()
        
        test_new_btn = QPushButton("🔌 测试连通性")
        test_new_btn.clicked.connect(self.test_new_model)
        self.widgets_to_style.append(('pushbutton_success', test_new_btn))
        add_btn_layout.addWidget(test_new_btn)
        
        add_btn = QPushButton("添加模型")
        add_btn.clicked.connect(self.add_new_model)
        self.widgets_to_style.append(('pushbutton_primary', add_btn))
        add_btn_layout.addWidget(add_btn)
        add_layout.addRow("", add_btn_layout)
        
        add_group.setLayout(add_layout)
        self.ai_settings_layout.addWidget(add_group)
        
        self.ai_settings_layout.addStretch()
        
        scroll_content.setLayout(self.ai_settings_layout)
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)
        
        # 保存按钮 - 固定在窗口底部
        save_btn = QPushButton("💾 保存AI模型配置")
        save_btn.clicked.connect(self.save_ai_settings)
        self.widgets_to_style.append(('pushbutton_primary', save_btn))
        layout.addWidget(save_btn)
        
        page.setLayout(layout)
        return page
    
    def on_provider_changed(self, provider):
        if provider in self.providers:
            self.new_api_url_input.setText(self.providers[provider]['api_url'])
            self.new_model_input.setText(self.providers[provider]['model'])
    
    def add_new_model(self):
        provider = self.provider_combo.currentText()
        custom_name = self.custom_name_input.text().strip()
        name = custom_name if custom_name else provider
        api_url = self.new_api_url_input.text()
        api_key = self.new_api_key_input.text()
        model = self.new_model_input.text()
        
        if not api_url:
            QMessageBox.warning(self, "警告", "请填写 API 地址！")
            return
        
        # 创建新模型数据
        new_model = {
            'name': name,
            'api_url': api_url,
            'api_key': api_key,
            'model': model,
            'enabled': True
        }
        
        # 添加到界面
        index = len(self.ai_model_inputs)
        widget = self.create_ai_model_widget(new_model, index)
        self.models_layout.addWidget(widget)
        
        # 清空添加表单
        self.custom_name_input.clear()
        self.new_api_key_input.clear()
        
        QMessageBox.information(self, "成功", f"已添加模型：{name}")
    
    def create_ai_model_widget(self, model_data, index):
        collapsible = CollapsibleGroup(model_data['name'], self, index, self.theme_manager)
        collapsible.set_enabled_status(model_data['enabled'])
        
        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        
        # API URL
        api_url_input = QLineEdit(model_data['api_url'])
        api_url_input.textChanged.connect(lambda: collapsible.update_title(api_url_input.text() if not self.custom_name_input.text() else self.custom_name_input.text()))
        form_layout.addRow("API 地址:", api_url_input)
        
        # API Key
        api_key_input = QLineEdit(model_data['api_key'])
        api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addRow("API Key:", api_key_input)
        
        # Model
        model_input = QLineEdit(model_data['model'])
        form_layout.addRow("模型名称:", model_input)
        
        # Enabled
        enabled_check = QCheckBox("启用")
        enabled_check.setChecked(model_data['enabled'])
        enabled_check.toggled.connect(lambda checked: collapsible.set_enabled_status(checked))
        
        # Test button and Delete button
        test_btn = QPushButton("🔌 测试")
        test_btn.clicked.connect(lambda: self.test_api_connection(index))
        
        delete_btn = QPushButton("🗑️ 删除")
        delete_btn.clicked.connect(lambda: self.delete_model(index))
        
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(enabled_check)
        btn_layout.addStretch()
        btn_layout.addWidget(test_btn)
        btn_layout.addWidget(delete_btn)
        form_layout.addRow("", btn_layout)
        
        collapsible.content_layout.addLayout(form_layout)
        
        # 添加到样式列表
        self.widgets_to_style.append(('lineedit', api_url_input))
        self.widgets_to_style.append(('lineedit', api_key_input))
        self.widgets_to_style.append(('lineedit', model_input))
        self.widgets_to_style.append(('checkbox', enabled_check))
        self.widgets_to_style.append(('pushbutton_success', test_btn))
        self.widgets_to_style.append(('pushbutton_danger', delete_btn))
        
        self.ai_model_inputs.append({
            'name': model_data['name'],
            'api_url': api_url_input,
            'api_key': api_key_input,
            'model': model_input,
            'enabled': enabled_check,
            'widget': collapsible
        })
        self.ai_collapsible_groups.append(collapsible)
        
        return collapsible
    
    def delete_model(self, index):
        reply = QMessageBox.question(self, "确认", "确定要删除这个模型吗？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            widget = self.ai_model_inputs[index]['widget']
            widget.deleteLater()
            self.ai_model_inputs.pop(index)
            self.ai_collapsible_groups.pop(index)
            # 更新剩余模型的索引
            for i in range(index, len(self.ai_model_inputs)):
                self.ai_collapsible_groups[i].index = i
    
    def test_api_connection(self, index_or_url, api_key=None, model=None):
        # 支持两种调用方式：传入 index 或直接传入 url, api_key, model
        if isinstance(index_or_url, int):
            # 通过索引调用（已添加的模型）
            model_input = self.ai_model_inputs[index_or_url]
            api_url = model_input['api_url'].text()
            api_key = model_input['api_key'].text()
            model = model_input['model'].text()
        else:
            # 直接传参调用（新添加模型测试）
            api_url = index_or_url
        
        if not api_url:
            QMessageBox.warning(self, "警告", "请填写 API 地址！")
            return
        
        if not api_key:
            QMessageBox.warning(self, "警告", "请填写 API Key！")
            return
        
        try:
            # 获取代理配置
            proxies = self.get_proxy_config()
            
            # 测试连接
            if 'openai' in api_url.lower() or 'deepseek' in api_url.lower() or 'siliconflow' in api_url.lower() or 'modelscope' in api_url.lower() or 'openrouter' in api_url.lower():
                headers = {
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json'
                }
                test_url = api_url.replace('/chat/completions', '/models')
                response = requests.get(test_url, headers=headers, proxies=proxies, timeout=10)
            elif 'ollama' in api_url.lower() or 'localhost' in api_url.lower():
                # Ollama 简单测试
                response = requests.get(api_url.replace('/api/chat', '/api/tags'), proxies=proxies, timeout=10)
            else:
                response = requests.get(api_url, proxies=proxies, timeout=10)
            
            if response.status_code in (200, 201, 401):
                if response.status_code == 401:
                    QMessageBox.warning(self, "测试结果", f"连接成功，但 API Key 无效 (状态码: 401)")
                else:
                    QMessageBox.information(self, "测试结果", "✅ 连接成功！API 配置正确。")
            else:
                QMessageBox.warning(self, "测试结果", f"连接失败 (状态码: {response.status_code})")
        
        except Exception as e:
            QMessageBox.critical(self, "错误", f"连接测试失败：{str(e)}")
    
    def test_new_model(self):
        # 直接调用合并后的函数
        self.test_api_connection(
            self.new_api_url_input.text(),
            self.new_api_key_input.text(),
            self.new_model_input.text()
        )
    
    def load_settings(self):
        theme = self.settings_manager.get('theme')
        theme_index = {'auto': 0, 'light': 1, 'dark': 2}.get(theme, 0)
        self.theme_combo.setCurrentIndex(theme_index)
        
        self.auto_start_check.blockSignals(True)
        self.auto_start_check.setChecked(self.auto_start_manager.get_auto_start())
        self.auto_start_check.blockSignals(False)
        
        self.notification_check.blockSignals(True)
        self.notification_check.setChecked(self.settings_manager.get('show_notification'))
        self.notification_check.blockSignals(False)
        
        self.admin_check.blockSignals(True)
        self.admin_check.setChecked(self.settings_manager.get('run_as_admin'))
        self.admin_check.blockSignals(False)
        
        # 加载搜索框快捷键
        self.search_hotkey_input.setText(self.settings_manager.get('search_hotkey', 'alt+space'))
        
        # 加载代理配置
        self.load_proxy_settings()
        
        # 加载 AI 模型配置
        self.load_ai_settings()
        
        # 加载扫描配置
        self.load_scan_settings()
    
    def save_system_settings(self):
        """保存系统设置（包括快捷键）"""
        new_hotkey = self.search_hotkey_input.text().strip()
        if not new_hotkey:
            new_hotkey = 'alt+space'
        
        old_hotkey = self.settings_manager.get('search_hotkey', 'alt+space')
        if new_hotkey != old_hotkey:
            self.settings_manager.set('search_hotkey', new_hotkey)
            self.signal_handler.search_hotkey_changed.emit()
        
        QMessageBox.information(self, "成功", "系统设置已保存！")
    
    def load_proxy_settings(self):
        """从配置文件重新加载代理设置"""
        self.proxy_enabled_check.blockSignals(True)
        self.proxy_enabled_check.setChecked(self.settings_manager.get('proxy_enabled'))
        self.proxy_enabled_check.blockSignals(False)
        
        self.proxy_address_input.setText(self.settings_manager.get('proxy_address'))
        self.proxy_port_input.setText(self.settings_manager.get('proxy_port'))
        self.proxy_username_input.setText(self.settings_manager.get('proxy_username'))
        self.proxy_password_input.setText(self.settings_manager.get('proxy_password'))
        
        # 初始设置输入框状态
        self.on_proxy_enabled_changed(self.proxy_enabled_check.isChecked())
    
    def load_ai_settings(self):
        # 清空现有 AI 模型输入
        for i in reversed(range(self.models_layout.count())):
            item = self.models_layout.itemAt(i)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.ai_model_inputs.clear()
        self.ai_collapsible_groups.clear()
        
        ai_models = self.settings_manager.get('ai_models')
        for idx, model in enumerate(ai_models):
            widget = self.create_ai_model_widget(model, idx)
            self.models_layout.addWidget(widget)
    
    def save_ai_settings(self):
        ai_models = []
        for model_input in self.ai_model_inputs:
            ai_models.append({
                'name': model_input['name'],
                'api_url': model_input['api_url'].text(),
                'api_key': model_input['api_key'].text(),
                'model': model_input['model'].text(),
                'enabled': model_input['enabled'].isChecked()
            })
        self.settings_manager.set('ai_models', ai_models)
        QMessageBox.information(self, "成功", "AI 模型配置已保存！")
    

    
    def switch_page(self, index):
        self.stacked_widget.setCurrentIndex(index)
        # 当切换到代理设置页面时（索引为1），重新从配置文件加载
        if index == 1:
            self.load_proxy_settings()
        # 当切换到AI模型配置页面时（索引为2），重新从配置文件加载
        elif index == 2:
            self.load_ai_settings()
        # 当切换到启动程序扫描页面时（索引为3），重新从配置文件加载
        elif index == 3:
            self.load_scan_settings()
        # 当切换到文件搜索设置页面时（索引为4），重新从配置文件加载
        elif index == 4:
            self.load_file_search_settings()
        elif index == 5:
            self.load_clipboard_settings()
        elif index == 6:
            self.load_screenshot_settings()
    
    def on_theme_changed(self, index):
        theme = ['auto', 'light', 'dark'][index]
        self.settings_manager.set('theme', theme)
        self.theme_manager.apply_theme(theme)
        self.signal_handler.theme_changed.emit(theme)
    
    def apply_theme(self):
        colors = self.theme_manager.get_colors()
        
        # 设置窗口背景色
        self.setStyleSheet(f"QWidget {{ background-color: {colors['window']}; }}")
        
        # 应用侧边栏样式
        try:
            self.sidebar.setStyleSheet(self.theme_manager.get_sidebar_style())
        except RuntimeError:
            pass
        
        # 应用其他控件样式
        valid_widgets = []
        for widget_type, widget in self.widgets_to_style:
            try:
                if widget_type == 'lineedit':
                    widget.setStyleSheet(self.theme_manager.get_line_edit_style())
                    valid_widgets.append((widget_type, widget))
                elif widget_type == 'combobox':
                    widget.setStyleSheet(self.theme_manager.get_combobox_style())
                    valid_widgets.append((widget_type, widget))
                elif widget_type == 'checkbox':
                    widget.setStyleSheet(self.theme_manager.get_checkbox_style())
                    valid_widgets.append((widget_type, widget))
                elif widget_type == 'groupbox':
                    widget.setStyleSheet(self.theme_manager.get_groupbox_style())
                    valid_widgets.append((widget_type, widget))
                elif widget_type == 'listwidget':
                    widget.setStyleSheet(self.theme_manager.get_list_widget_style())
                    valid_widgets.append((widget_type, widget))
                elif widget_type == 'pushbutton_primary':
                    widget.setStyleSheet(self.theme_manager.get_push_button_style('primary'))
                    valid_widgets.append((widget_type, widget))
                elif widget_type == 'pushbutton_success':
                    widget.setStyleSheet(self.theme_manager.get_push_button_style('success'))
                    valid_widgets.append((widget_type, widget))
                elif widget_type == 'pushbutton_danger':
                    widget.setStyleSheet(self.theme_manager.get_push_button_style('danger'))
                    valid_widgets.append((widget_type, widget))
                elif widget_type == 'textedit':
                    widget.setStyleSheet(self.theme_manager.get_textedit_style())
                    valid_widgets.append((widget_type, widget))
                elif widget_type == 'title' or widget_type == 'label':
                    widget.setStyleSheet(f"color: {colors['window_text']};")
                    valid_widgets.append((widget_type, widget))
            except RuntimeError:
                pass
        
        # 更新有效的widget列表
        self.widgets_to_style = valid_widgets
        
        # 更新可折叠组件样式
        for group in self.ai_collapsible_groups:
            try:
                if hasattr(group, 'apply_theme'):
                    group.apply_theme()
            except RuntimeError:
                pass
    
    def on_theme_changed_external(self, theme):
        self.apply_theme()
    
    def on_auto_start_changed(self, checked):
        self.auto_start_manager.set_auto_start(checked)
    
    def on_notification_changed(self, checked):
        self.settings_manager.set('show_notification', checked)
    
    def on_admin_changed(self, checked):
        self.settings_manager.set('run_as_admin', checked)
        if checked and not self.auto_start_manager.is_admin():
            reply = QMessageBox.question(
                self, 
                "需要管理员权限", 
                "是否现在就以管理员权限重新启动程序？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.auto_start_manager.run_as_admin()
            else:
                self.admin_check.setChecked(False)
    
    def on_proxy_enabled_changed(self, checked):
        self.proxy_address_input.setEnabled(checked)
        self.proxy_port_input.setEnabled(checked)
        self.proxy_username_input.setEnabled(checked)
        self.proxy_password_input.setEnabled(checked)
    
    def test_proxy_connection(self):
        proxy_address = self.proxy_address_input.text().strip()
        proxy_port = self.proxy_port_input.text().strip()
        proxy_username = self.proxy_username_input.text().strip()
        proxy_password = self.proxy_password_input.text().strip()
        
        if not proxy_address or not proxy_port:
            QMessageBox.warning(self, "警告", "请填写代理地址和端口！")
            return
        
        try:
            # 构建代理URL
            proxy_url = f"{proxy_address}:{proxy_port}"
            proxies = {}
            
            if proxy_username and proxy_password:
                proxies = {
                    'http': f'http://{proxy_username}:{proxy_password}@{proxy_url}',
                    'https': f'http://{proxy_username}:{proxy_password}@{proxy_url}'
                }
            else:
                proxies = {
                    'http': f'http://{proxy_url}',
                    'https': f'http://{proxy_url}'
                }
            
            # 使用 Google 测试连通性
            response = requests.get('https://www.google.com', proxies=proxies, timeout=10)
            
            if response.status_code == 200:
                QMessageBox.information(self, "测试结果", "✅ 代理连通成功！")
            else:
                QMessageBox.warning(self, "测试结果", f"代理连通失败 (状态码: {response.status_code})")
        
        except Exception as e:
            QMessageBox.critical(self, "错误", f"代理连通测试失败：{str(e)}")
    
    def save_proxy_settings(self):
        self.settings_manager.set('proxy_enabled', self.proxy_enabled_check.isChecked())
        self.settings_manager.set('proxy_address', self.proxy_address_input.text().strip())
        self.settings_manager.set('proxy_port', self.proxy_port_input.text().strip())
        self.settings_manager.set('proxy_username', self.proxy_username_input.text().strip())
        self.settings_manager.set('proxy_password', self.proxy_password_input.text().strip())
        QMessageBox.information(self, "成功", "代理配置已保存！")
    
    def get_proxy_config(self):
        """获取代理配置，供其他模块使用"""
        if not self.settings_manager.get('proxy_enabled'):
            return None
        
        proxy_address = self.settings_manager.get('proxy_address')
        proxy_port = self.settings_manager.get('proxy_port')
        proxy_username = self.settings_manager.get('proxy_username')
        proxy_password = self.settings_manager.get('proxy_password')
        
        if not proxy_address or not proxy_port:
            return None
        
        proxy_url = f"{proxy_address}:{proxy_port}"
        
        if proxy_username and proxy_password:
            return {
                'http': f'http://{proxy_username}:{proxy_password}@{proxy_url}',
                'https': f'http://{proxy_username}:{proxy_password}@{proxy_url}'
            }
        else:
            return {
                'http': f'http://{proxy_url}',
                'https': f'http://{proxy_url}'
            }
    
    def create_scan_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        title = QLabel("启动程序扫描")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Weight.Bold))
        self.widgets_to_style.append(('title', title))
        layout.addWidget(title)
                        
        # 目录列表
        dir_group = QGroupBox("自定义扫描目录")
        self.widgets_to_style.append(('groupbox', dir_group))
        dir_layout = QVBoxLayout()
        dir_layout.setSpacing(15)

        # 说明
        desc = QLabel("添加自定义目录来扫描快捷方式（.lnk）和可执行程序（.exe）：\n为了避免卡顿，最多扫描两层子目录！！！")
        self.widgets_to_style.append(('label', desc))
        dir_layout.addWidget(desc)
        
        self.scan_dirs_list = QListWidget()
        self.widgets_to_style.append(('listwidget', self.scan_dirs_list))
        dir_layout.addWidget(self.scan_dirs_list, 1)
        
        # 按钮区
        btn_layout = QHBoxLayout()
        
        add_btn = QPushButton("➕ 添加目录")
        add_btn.clicked.connect(self.add_scan_dir)
        self.widgets_to_style.append(('pushbutton_success', add_btn))
        
        delete_btn = QPushButton("🗑️ 删除选中")
        delete_btn.clicked.connect(self.delete_scan_dir)
        self.widgets_to_style.append(('pushbutton_danger', delete_btn))
        
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(delete_btn)
        btn_layout.addStretch()
        dir_layout.addLayout(btn_layout)
        
        dir_group.setLayout(dir_layout)
        layout.addWidget(dir_group, 1)
        
        # 排除列表
        exclude_group = QGroupBox("自定义排除应用")
        self.widgets_to_style.append(('groupbox', exclude_group))
        exclude_layout = QVBoxLayout()
        exclude_layout.setSpacing(15)
        
        exclude_desc = QLabel("添加应用名称关键词，包含这些关键词的应用将不会显示在搜索结果中：")
        self.widgets_to_style.append(('label', exclude_desc))
        exclude_layout.addWidget(exclude_desc)
        
        self.exclude_names_list = QListWidget()
        self.widgets_to_style.append(('listwidget', self.exclude_names_list))
        exclude_layout.addWidget(self.exclude_names_list, 1)
        
        # 排除列表按钮区
        exclude_btn_layout = QHBoxLayout()
        
        # 添加排除名称输入框
        self.exclude_name_input = QLineEdit()
        self.exclude_name_input.setPlaceholderText("输入要排除的应用名称关键词...")
        self.widgets_to_style.append(('lineedit', self.exclude_name_input))
        self.exclude_name_input.returnPressed.connect(self.add_exclude_name)
        
        add_exclude_btn = QPushButton("➕ 添加排除")
        add_exclude_btn.clicked.connect(self.add_exclude_name)
        self.widgets_to_style.append(('pushbutton_primary', add_exclude_btn))
        
        delete_exclude_btn = QPushButton("🗑️ 删除选中")
        delete_exclude_btn.clicked.connect(self.delete_exclude_name)
        self.widgets_to_style.append(('pushbutton_danger', delete_exclude_btn))
        
        exclude_btn_layout.addWidget(self.exclude_name_input, 1)
        exclude_btn_layout.addWidget(add_exclude_btn)
        exclude_btn_layout.addWidget(delete_exclude_btn)
        exclude_layout.addLayout(exclude_btn_layout)
        
        exclude_group.setLayout(exclude_layout)
        layout.addWidget(exclude_group, 1)
        
        # 保存按钮
        save_btn = QPushButton("💾 保存扫描配置")
        save_btn.clicked.connect(self.save_scan_settings)
        self.widgets_to_style.append(('pushbutton_primary', save_btn))
        layout.addWidget(save_btn)
        
        layout.addStretch()
        page.setLayout(layout)
        return page
    
    def add_scan_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择扫描目录")
        if dir_path:
            # 检查是否已存在
            exists = False
            for i in range(self.scan_dirs_list.count()):
                if self.scan_dirs_list.item(i).text() == dir_path:
                    exists = True
                    break
            if not exists:
                self.scan_dirs_list.addItem(dir_path)
            else:
                QMessageBox.information(self, "提示", "该目录已存在！")
    
    def delete_scan_dir(self):
        current_row = self.scan_dirs_list.currentRow()
        if current_row >= 0:
            self.scan_dirs_list.takeItem(current_row)
        else:
            QMessageBox.warning(self, "警告", "请先选择要删除的目录！")
    
    def add_exclude_name(self):
        exclude_name = self.exclude_name_input.text().strip()
        if exclude_name:
            # 检查是否已存在
            exists = False
            for i in range(self.exclude_names_list.count()):
                if self.exclude_names_list.item(i).text().lower() == exclude_name.lower():
                    exists = True
                    break
            if not exists:
                self.exclude_names_list.addItem(exclude_name)
                self.exclude_name_input.clear()
            else:
                QMessageBox.information(self, "提示", "该排除关键词已存在！")
        else:
            QMessageBox.warning(self, "警告", "请输入要排除的应用名称关键词！")
    
    def delete_exclude_name(self):
        current_row = self.exclude_names_list.currentRow()
        if current_row >= 0:
            self.exclude_names_list.takeItem(current_row)
        else:
            QMessageBox.warning(self, "警告", "请先选择要删除的排除关键词！")
    
    def load_scan_settings(self):
        # 加载扫描目录
        self.scan_dirs_list.clear()
        scan_dirs = self.settings_manager.get('custom_scan_dirs')
        for dir_path in scan_dirs:
            self.scan_dirs_list.addItem(dir_path)
        
        # 加载排除应用列表
        self.exclude_names_list.clear()
        exclude_names = self.settings_manager.get('exclude_app_names')
        for name in exclude_names:
            self.exclude_names_list.addItem(name)
    
    def save_scan_settings(self):
        # 保存扫描目录
        scan_dirs = []
        for i in range(self.scan_dirs_list.count()):
            scan_dirs.append(self.scan_dirs_list.item(i).text())
        self.settings_manager.set('custom_scan_dirs', scan_dirs)
        
        # 保存排除应用列表
        exclude_names = []
        for i in range(self.exclude_names_list.count()):
            exclude_names.append(self.exclude_names_list.item(i).text())
        self.settings_manager.set('exclude_app_names', exclude_names)
        
        QMessageBox.information(self, "成功", "扫描配置已保存！")
    
    def create_file_search_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        title = QLabel("文件搜索设置")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Weight.Bold))
        self.widgets_to_style.append(('title', title))
        layout.addWidget(title)
        
        # 文件搜索启用开关
        enable_group = QGroupBox("文件搜索功能")
        self.widgets_to_style.append(('groupbox', enable_group))
        enable_layout = QVBoxLayout()
        
        self.enable_file_search_check = QCheckBox("启用文件搜索（需要 Everything 软件）")
        self.widgets_to_style.append(('checkbox', self.enable_file_search_check))
        enable_layout.addWidget(self.enable_file_search_check)
        
        enable_group.setLayout(enable_layout)
        layout.addWidget(enable_group)
        
        # Everything 配置
        everything_group = QGroupBox("Everything 配置")
        self.widgets_to_style.append(('groupbox', everything_group))
        everything_layout = QFormLayout()
        everything_layout.setSpacing(15)
        
        # Everything 主程序路径
        self.everything_path_input = QLineEdit()
        self.everything_path_input.setPlaceholderText("Everything.exe 的路径")
        self.widgets_to_style.append(('lineedit', self.everything_path_input))
        
        browse_everything_btn = QPushButton("📁 浏览")
        browse_everything_btn.clicked.connect(self.browse_everything_path)
        self.widgets_to_style.append(('pushbutton_default', browse_everything_btn))
        
        everything_path_layout = QHBoxLayout()
        everything_path_layout.addWidget(self.everything_path_input)
        everything_path_layout.addWidget(browse_everything_btn)
        
        # Everything DLL 路径
        self.everything_dll_input = QLineEdit()
        self.everything_dll_input.setPlaceholderText("Everything64.dll 或 Everything32.dll 的路径")
        self.widgets_to_style.append(('lineedit', self.everything_dll_input))
        
        browse_dll_btn = QPushButton("📁 浏览")
        browse_dll_btn.clicked.connect(self.browse_everything_dll)
        self.widgets_to_style.append(('pushbutton_default', browse_dll_btn))
        
        everything_dll_layout = QHBoxLayout()
        everything_dll_layout.addWidget(self.everything_dll_input)
        everything_dll_layout.addWidget(browse_dll_btn)
        
        # 启动 Everything 按钮
        start_everything_btn = QPushButton("🚀 启动 Everything")
        start_everything_btn.clicked.connect(self.start_everything)
        self.widgets_to_style.append(('pushbutton_success', start_everything_btn))
        
        everything_layout.addRow("Everything 主程序：", everything_path_layout)
        everything_layout.addRow("Everything DLL：", everything_dll_layout)
        everything_layout.addRow("", start_everything_btn)
        
        everything_group.setLayout(everything_layout)
        layout.addWidget(everything_group)
        
        # 结果数量设置
        result_group = QGroupBox("搜索结果数量")
        self.widgets_to_style.append(('groupbox', result_group))
        result_layout = QFormLayout()
        result_layout.setSpacing(15)
        
        self.max_app_results_input = QLineEdit()
        self.max_app_results_input.setPlaceholderText("应用搜索最大结果数")
        self.widgets_to_style.append(('lineedit', self.max_app_results_input))
        
        self.max_file_results_input = QLineEdit()
        self.max_file_results_input.setPlaceholderText("文件搜索最大结果数")
        self.widgets_to_style.append(('lineedit', self.max_file_results_input))
        
        result_layout.addRow("应用搜索最大结果数：", self.max_app_results_input)
        result_layout.addRow("文件搜索最大结果数：", self.max_file_results_input)
        
        result_group.setLayout(result_layout)
        layout.addWidget(result_group)
        
        # 保存按钮
        save_btn = QPushButton("💾 保存文件搜索配置")
        save_btn.clicked.connect(self.save_file_search_settings)
        self.widgets_to_style.append(('pushbutton_primary', save_btn))
        layout.addWidget(save_btn)
        
        layout.addStretch()
        page.setLayout(layout)
        return page
    
    def browse_everything_path(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "选择 Everything 主程序", 
            "", 
            "可执行文件 (*.exe)"
        )
        if file_path:
            self.everything_path_input.setText(file_path)
    
    def browse_everything_dll(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "选择 Everything DLL 文件", 
            "", 
            "DLL 文件 (*.dll)"
        )
        if file_path:
            self.everything_dll_input.setText(file_path)
    
    def start_everything(self):
        
        everything_path = self.everything_path_input.text().strip()
        
        if not everything_path:
            # 尝试自动查找
            program_files = os.environ.get('PROGRAMFILES', '')
            program_files_x86 = os.environ.get('PROGRAMFILES(X86)', '')
            
            potential_paths = [
                os.path.join(program_files, 'Everything', 'Everything.exe'),
                os.path.join(program_files_x86, 'Everything', 'Everything.exe'),
                r'C:\Program Files\Everything\Everything.exe',
                r'C:\Program Files (x86)\Everything\Everything.exe'
            ]
            
            for path in potential_paths:
                if os.path.exists(path):
                    everything_path = path
                    break
        
        if everything_path and os.path.exists(everything_path):
            try:
                subprocess.Popen(everything_path)
                QMessageBox.information(self, "成功", "Everything 已启动！")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"启动 Everything 失败：{str(e)}")
        else:
            QMessageBox.warning(self, "警告", "请先设置 Everything 的路径！")
    
    def load_file_search_settings(self):
        self.enable_file_search_check.setChecked(self.settings_manager.get('enable_file_search', True))
        self.max_app_results_input.setText(str(self.settings_manager.get('max_app_results', 20)))
        self.max_file_results_input.setText(str(self.settings_manager.get('max_file_results', 30)))
        self.everything_path_input.setText(self.settings_manager.get('everything_path', ''))
        self.everything_dll_input.setText(self.settings_manager.get('everything_dll_path', ''))
    
    def save_file_search_settings(self):
        self.settings_manager.set('enable_file_search', self.enable_file_search_check.isChecked())
        self.settings_manager.set('everything_path', self.everything_path_input.text().strip())
        self.settings_manager.set('everything_dll_path', self.everything_dll_input.text().strip())
        
        try:
            max_app = int(self.max_app_results_input.text())
            self.settings_manager.set('max_app_results', max_app)
        except ValueError:
            self.settings_manager.set('max_app_results', 20)
        
        try:
            max_file = int(self.max_file_results_input.text())
            self.settings_manager.set('max_file_results', max_file)
        except ValueError:
            self.settings_manager.set('max_file_results', 30)
        
        QMessageBox.information(self, "成功", "文件搜索配置已保存！")
    
    def create_clipboard_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        title = QLabel("剪贴板设置")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Weight.Bold))
        self.widgets_to_style.append(('title', title))
        layout.addWidget(title)
        
        # 启用剪贴板功能
        enable_group = QGroupBox("功能设置")
        self.widgets_to_style.append(('groupbox', enable_group))
        enable_layout = QVBoxLayout()
        enable_layout.setSpacing(15)
        
        self.clipboard_enabled_check = QCheckBox("启用剪贴板历史记录")
        self.widgets_to_style.append(('checkbox', self.clipboard_enabled_check))
        enable_layout.addWidget(self.clipboard_enabled_check)
        
        enable_group.setLayout(enable_layout)
        layout.addWidget(enable_group)
        
        # 快捷键设置
        hotkey_group = QGroupBox("快捷键设置")
        self.widgets_to_style.append(('groupbox', hotkey_group))
        hotkey_layout = QFormLayout()
        hotkey_layout.setSpacing(15)
        
        self.clipboard_hotkey_input = QLineEdit()
        self.clipboard_hotkey_input.setPlaceholderText("例如：win+v, alt+v")
        self.widgets_to_style.append(('lineedit', self.clipboard_hotkey_input))
        
        hotkey_layout.addRow("显示剪贴板历史：", self.clipboard_hotkey_input)
        
        hotkey_group.setLayout(hotkey_layout)
        layout.addWidget(hotkey_group)
        
        # 历史记录数量限制
        limit_group = QGroupBox("历史记录设置")
        self.widgets_to_style.append(('groupbox', limit_group))
        limit_layout = QFormLayout()
        limit_layout.setSpacing(15)
        
        self.clipboard_history_limit_combo = QComboBox()
        self.clipboard_history_limit_combo.addItems([
            "无限制",
            "100 条",
            "500 条",
            "1000 条"
        ])
        self.widgets_to_style.append(('combobox', self.clipboard_history_limit_combo))
        
        limit_layout.addRow("最大历史记录数：", self.clipboard_history_limit_combo)
        
        limit_group.setLayout(limit_layout)
        layout.addWidget(limit_group)
        
        # 保存按钮
        save_btn = QPushButton("💾 保存剪贴板设置")
        save_btn.clicked.connect(self.save_clipboard_settings)
        self.widgets_to_style.append(('pushbutton_primary', save_btn))
        layout.addWidget(save_btn)
        
        layout.addStretch()
        page.setLayout(layout)
        return page
    
    def load_clipboard_settings(self):
        self.clipboard_enabled_check.setChecked(self.settings_manager.get('clipboard_enabled', True))
        self.clipboard_hotkey_input.setText(self.settings_manager.get('clipboard_hotkey', 'win+v'))
        
        limit = self.settings_manager.get('clipboard_history_limit', 0)
        if limit == 0:
            self.clipboard_history_limit_combo.setCurrentIndex(0)
        elif limit == 100:
            self.clipboard_history_limit_combo.setCurrentIndex(1)
        elif limit == 500:
            self.clipboard_history_limit_combo.setCurrentIndex(2)
        elif limit == 1000:
            self.clipboard_history_limit_combo.setCurrentIndex(3)
    
    def save_clipboard_settings(self):
        self.settings_manager.set('clipboard_enabled', self.clipboard_enabled_check.isChecked())
        self.settings_manager.set('clipboard_hotkey', self.clipboard_hotkey_input.text().strip())
        
        limit_index = self.clipboard_history_limit_combo.currentIndex()
        limits = [0, 100, 500, 1000]
        self.settings_manager.set('clipboard_history_limit', limits[limit_index])
        
        # 发送剪贴板设置变更信号
        self.signal_handler.clipboard_settings_changed.emit()
        
        QMessageBox.information(self, "成功", "剪贴板设置已保存！")
    
    def create_screenshot_settings_page(self):
        page = QWidget()
        
        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        scroll_content = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        title = QLabel("截图设置")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Weight.Bold))
        self.widgets_to_style.append(('title', title))
        layout.addWidget(title)
        
        # 功能启用设置
        enable_group = QGroupBox("功能启用")
        self.widgets_to_style.append(('groupbox', enable_group))
        enable_layout = QVBoxLayout()
        enable_layout.setSpacing(15)
        
        self.screenshot_enabled_check = QCheckBox("启用截图功能")
        self.widgets_to_style.append(('checkbox', self.screenshot_enabled_check))
        self.screenshot_enabled_check.toggled.connect(self.on_screenshot_enabled_toggled)
        
        enable_layout.addWidget(self.screenshot_enabled_check)
        enable_group.setLayout(enable_layout)
        layout.addWidget(enable_group)
        
        # 快捷键设置
        hotkey_group = QGroupBox("快捷键设置")
        self.widgets_to_style.append(('groupbox', hotkey_group))
        hotkey_layout = QFormLayout()
        hotkey_layout.setSpacing(15)
        
        self.screenshot_hotkey_input = QLineEdit()
        self.screenshot_hotkey_input.setPlaceholderText("例如：ctrl+alt+a")
        self.widgets_to_style.append(('lineedit', self.screenshot_hotkey_input))
        
        hotkey_layout.addRow("截图快捷键：", self.screenshot_hotkey_input)
        hotkey_group.setLayout(hotkey_layout)
        layout.addWidget(hotkey_group)
        
        # 截图后操作（下拉菜单）
        action_group = QGroupBox("截图后操作")
        self.widgets_to_style.append(('groupbox', action_group))
        action_layout = QFormLayout()
        action_layout.setSpacing(15)
        
        self.screenshot_action_combo = QComboBox()
        self.screenshot_action_combo.addItems([
            "进行标注操作", 
            "直接复制到剪贴板", 
            "直接保存到文件"
        ])
        self.widgets_to_style.append(('combobox', self.screenshot_action_combo))
        self.screenshot_action_combo.currentIndexChanged.connect(self.on_screenshot_action_changed)
        
        action_layout.addRow("默认操作：", self.screenshot_action_combo)
        action_group.setLayout(action_layout)
        layout.addWidget(action_group)
        
        # 保存路径和格式
        save_group = QGroupBox("保存设置")
        self.widgets_to_style.append(('groupbox', save_group))
        save_layout = QFormLayout()
        save_layout.setSpacing(15)
        
        self.screenshot_save_path_input = QLineEdit()
        self.screenshot_save_path_input.setPlaceholderText("选择截图保存目录")
        self.widgets_to_style.append(('lineedit', self.screenshot_save_path_input))
        
        browse_save_path_btn = QPushButton("📁 浏览")
        browse_save_path_btn.clicked.connect(self.browse_screenshot_save_path)
        self.widgets_to_style.append(('pushbutton_default', browse_save_path_btn))
        
        save_path_layout = QHBoxLayout()
        save_path_layout.addWidget(self.screenshot_save_path_input)
        save_path_layout.addWidget(browse_save_path_btn)
        
        self.screenshot_format_combo = QComboBox()
        self.screenshot_format_combo.addItems(["PNG", "JPG", "BMP"])
        self.widgets_to_style.append(('combobox', self.screenshot_format_combo))
        
        save_layout.addRow("保存目录：", save_path_layout)
        save_layout.addRow("保存格式：", self.screenshot_format_combo)
        save_group.setLayout(save_layout)
        layout.addWidget(save_group)
        
        # OCR 模型配置（在线 API）
        ocr_group = QGroupBox("OCR 模型配置（在线 API）")
        self.widgets_to_style.append(('groupbox', ocr_group))
        ocr_layout = QFormLayout()
        ocr_layout.setSpacing(15)
        
        # API Token
        self.ocr_api_token_input = QLineEdit()
        self.ocr_api_token_input.setPlaceholderText("请输入 PaddleOCR API Token")
        self.ocr_api_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.widgets_to_style.append(('lineedit', self.ocr_api_token_input))
        
        # API URL
        self.ocr_api_url_input = QLineEdit()
        self.ocr_api_url_input.setPlaceholderText("请输入 PaddleOCR API URL，留空使用默认")
        self.widgets_to_style.append(('lineedit', self.ocr_api_url_input))
        
        # 模型选择
        self.ocr_model_combo = QComboBox()
        self.ocr_model_combo.addItems([
            "PP-OCRv5",
            "PaddleOCR-VL-1.5",
            "PaddleOCR-VL"
        ])
        self.widgets_to_style.append(('combobox', self.ocr_model_combo))
        
        ocr_desc = QLabel("使用 PaddleOCR 在线 API 进行文字识别，请配置 API Token：")
        self.widgets_to_style.append(('label', ocr_desc))
        ocr_layout.addRow(ocr_desc)
        ocr_layout.addRow("API Token：", self.ocr_api_token_input)
        ocr_layout.addRow("API URL：", self.ocr_api_url_input)
        ocr_layout.addRow("模型选择：", self.ocr_model_combo)
        
        ocr_group.setLayout(ocr_layout)
        layout.addWidget(ocr_group)
        
        # 保存按钮
        save_btn = QPushButton("💾 保存截图设置")
        save_btn.clicked.connect(self.save_screenshot_settings)
        self.widgets_to_style.append(('pushbutton_primary', save_btn))
        layout.addWidget(save_btn)
        
        layout.addStretch()
        scroll_content.setLayout(layout)
        scroll.setWidget(scroll_content)
        
        main_page_layout = QVBoxLayout()
        main_page_layout.setContentsMargins(0, 0, 0, 0)
        main_page_layout.addWidget(scroll)
        page.setLayout(main_page_layout)
        
        return page
    
    def on_screenshot_enabled_toggled(self, checked):
        """当启用/禁用截图功能时，切换相关控件状态"""
        self.screenshot_hotkey_input.setEnabled(checked)
        self.screenshot_action_combo.setEnabled(checked)
        self.screenshot_format_combo.setEnabled(checked)
        # 如果选择了保存到文件，路径输入才启用
        self.screenshot_save_path_input.setEnabled(
            checked and self.screenshot_action_combo.currentIndex() == 2
        )
    
    def on_screenshot_action_changed(self, index):
        """当操作选项变化时，更新保存路径输入框的启用状态"""
        if self.screenshot_enabled_check.isChecked():
            self.screenshot_save_path_input.setEnabled(index == 2)
    
    def browse_screenshot_save_path(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择截图保存目录")
        if dir_path:
            self.screenshot_save_path_input.setText(dir_path)
    
    def browse_ocr_det_model(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择检测模型文件", "", "模型文件 (*.pdmodel *.pdiparams)")
        if file_path:
            # 如果用户选择的是模型文件，我们需要取目录路径
            self.ocr_det_model_input.setText(os.path.dirname(file_path))
    
    def browse_ocr_rec_model(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择识别模型文件", "", "模型文件 (*.pdmodel *.pdiparams)")
        if file_path:
            self.ocr_rec_model_input.setText(os.path.dirname(file_path))
    
    def load_screenshot_settings(self):
        self.screenshot_enabled_check.setChecked(self.settings_manager.get('screenshot_enabled', True))
        self.screenshot_hotkey_input.setText(self.settings_manager.get('screenshot_hotkey', 'ctrl+alt+a'))
        
        action_map = {'annotate': 0, 'clipboard': 1, 'save': 2}
        action = self.settings_manager.get('screenshot_action', 'annotate')
        self.screenshot_action_combo.setCurrentIndex(action_map.get(action, 0))
        
        # 获取保存路径，如果为空则使用默认值
        save_path = self.settings_manager.get('screenshot_save_path', '')
        if not save_path:
            save_path = SettingsManager.get_default_screenshot_path()
        self.screenshot_save_path_input.setText(save_path)
        
        format_map = {'png': 0, 'jpg': 1, 'bmp': 2}
        screenshot_format = self.settings_manager.get('screenshot_format', 'png').lower()
        self.screenshot_format_combo.setCurrentIndex(format_map.get(screenshot_format, 0))
        
        # 加载 OCR API 配置
        self.ocr_api_token_input.setText(self.settings_manager.get('ocr_api_token', ''))
        self.ocr_api_url_input.setText(self.settings_manager.get('ocr_api_url', ''))
        
        # 加载模型选择
        model_map = {'pp-ocrv5': 0, 'paddleocr-vl-1.5': 1, 'paddleocr-vl': 2}
        ocr_model = self.settings_manager.get('ocr_model', 'pp-ocrv5').lower()
        self.ocr_model_combo.setCurrentIndex(model_map.get(ocr_model, 0))
        
        # 初始状态设置
        self.on_screenshot_enabled_toggled(self.screenshot_enabled_check.isChecked())
    
    def save_screenshot_settings(self):
        old_hotkey = self.settings_manager.get('screenshot_hotkey', 'ctrl+alt+a')
        new_hotkey = self.screenshot_hotkey_input.text().strip()
        if not new_hotkey:
            new_hotkey = 'ctrl+alt+a'
        
        self.settings_manager.set('screenshot_enabled', self.screenshot_enabled_check.isChecked())
        self.settings_manager.set('screenshot_hotkey', new_hotkey)
        
        action_map = {0: 'annotate', 1: 'clipboard', 2: 'save'}
        action = action_map.get(self.screenshot_action_combo.currentIndex(), 'annotate')
        self.settings_manager.set('screenshot_action', action)
        
        # 确保保存路径不为空
        save_path = self.screenshot_save_path_input.text().strip()
        if not save_path:
            save_path = SettingsManager.get_default_screenshot_path()
        self.settings_manager.set('screenshot_save_path', save_path)
        
        formats = ['png', 'jpg', 'bmp']
        self.settings_manager.set('screenshot_format', formats[self.screenshot_format_combo.currentIndex()])
        
        # 保存 OCR API 配置
        self.settings_manager.set('ocr_api_token', self.ocr_api_token_input.text().strip())
        self.settings_manager.set('ocr_api_url', self.ocr_api_url_input.text().strip())
        
        # 保存模型选择
        model_map = {0: 'pp-ocrv5', 1: 'paddleocr-vl-1.5', 2: 'paddleocr-vl'}
        self.settings_manager.set('ocr_model', model_map.get(self.ocr_model_combo.currentIndex(), 'pp-ocrv5'))
        
        # 无论是否热键变化，只要设置变更就更新热键状态
        self.signal_handler.screenshot_hotkey_changed.emit()
        
        QMessageBox.information(self, "成功", "截图设置已保存！")
