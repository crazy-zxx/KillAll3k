import os
import sys

import keyboard
from PyQt6.QtCore import QFileInfo, QSize
from PyQt6.QtCore import Qt, QPoint, QTimer
from PyQt6.QtGui import QPainter, QBrush, QColor, QIcon, QAction, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLineEdit, QMessageBox, QVBoxLayout, QListWidget, QListWidgetItem,
    QFileIconProvider, QSystemTrayIcon, QMenu
)

from app_scanner import AppScanner
from clipboard_manager import ClipboardManager
from clipboard_window import ClipboardWindow
from file_search import EverythingSearch
from screenshot import ScreenshotManager
from settings import (
    SignalHandler, SettingsManager, ThemeManager, AutoStartManager, SettingsWindow
)


class SearchWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.drag_pos = None
        self.tray_icon = None
        self.settings_window = None
        self.clipboard_window = None
        self.settings_manager = SettingsManager()
        self.theme_manager = ThemeManager(None)
        self.auto_start_manager = AutoStartManager()
        self.signal_handler = SignalHandler()
        self.theme_manager.signal_handler = self.signal_handler
        self.app_scanner = AppScanner(self.settings_manager)
        self.file_searcher = EverythingSearch(self.settings_manager)
        self.search_results = []
        self.selected_index = 0
        # 在 SearchWindow 中也创建 ClipboardManager 实例，确保设置变更能即时生效

        self.clipboard_manager = ClipboardManager(self.settings_manager)
        # 创建截图管理器

        self.screenshot_manager = ScreenshotManager(self.settings_manager, self.theme_manager)
        # 用于跟踪当前注册的热键
        self.current_search_hotkey = None
        self.current_clipboard_hotkey = None
        self.current_screenshot_hotkey = None
        
        # 检查是否需要以管理员权限运行
        self.check_admin_privilege()
        
        self.signal_handler.toggle_window.connect(self.toggle_window)
        self.signal_handler.show_window.connect(self.show_window)
        self.signal_handler.show_settings.connect(self.show_settings)
        self.signal_handler.show_clipboard.connect(self.show_clipboard)
        self.signal_handler.take_screenshot.connect(self.take_screenshot)
        self.signal_handler.quit_app.connect(self.safe_quit)
        self.signal_handler.theme_changed.connect(self.on_theme_changed)
        # 连接剪贴板设置变更信号
        self.signal_handler.clipboard_settings_changed.connect(self.clipboard_manager.update_monitoring_state)
        self.signal_handler.clipboard_settings_changed.connect(self.update_clipboard_hotkey)
        # 连接搜索框快捷键变更信号
        self.signal_handler.search_hotkey_changed.connect(self.update_search_hotkey)
        # 连接截图快捷键变更信号
        self.signal_handler.screenshot_hotkey_changed.connect(self.update_screenshot_hotkey)
        
        self.theme_manager.apply_theme(self.settings_manager.get('theme'))
        self.init_ui()
        self.setup_tray()
        self.setup_hotkey()
        
        # 显示启动通知
        if self.settings_manager.get('show_notification'):
            QTimer.singleShot(500, self.show_notification)
    
    def check_admin_privilege(self):
        """检查并处理管理员权限需求"""
        need_admin = self.settings_manager.get('run_as_admin')
        is_admin = self.auto_start_manager.is_admin()
        
        if need_admin and not is_admin:
            # 询问用户是否以管理员权限启动
            reply = QMessageBox.question(
                None, 
                "需要管理员权限", 
                "设置中要求以管理员权限运行，是否现在重新启动？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.auto_start_manager.run_as_admin()
    
    def init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(600, 60)  # 初始固定大小
        
        # 设置窗口图标
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logo.ico')
        self.setWindowIcon(QIcon(icon_path))
        
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)
        
        # 搜索输入框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("在此处输入以搜索应用")
        self.search_input.setFixedHeight(50)
        self.update_search_input_style()
        self.search_input.textChanged.connect(self.real_time_search)
        self.search_input.returnPressed.connect(self.launch_selected_app)
        
        main_layout.addWidget(self.search_input)
        
        # 应用列表
        self.app_list = QListWidget()
        # self.app_list.setMaximumHeight(400)
        # 设置列表属性，确保滚动时不会出现空白
        self.app_list.setUniformItemSizes(True)
        self.app_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerItem)
        self.app_list.hide()
        self.app_list.itemClicked.connect(self.on_item_clicked)
        self.app_list.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.app_list.setIconSize(QSize(32, 32))  # 设置适中的图标尺寸
        self.update_app_list_style()
        
        main_layout.addWidget(self.app_list)
        
        self.setLayout(main_layout)
    
    def update_search_input_style(self):
        # 使用ThemeManager的样式
        colors = self.theme_manager.get_colors()
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {colors['base']};
                color: {colors['window_text']};
                border: 1px solid {colors['border']};
                border-radius: 12px;
                padding-left: 22px;
                padding-right: 22px;
                font-size: 20px;
            }}
            QLineEdit:focus {{
                border: 1px solid {colors['highlight']};
                outline: none;
            }}
        """)
    
    def update_app_list_style(self):
        # 使用ThemeManager的颜色
        colors = self.theme_manager.get_colors()
        self.app_list.setStyleSheet(f"""
            QListWidget {{
                outline: none; 
                background-color: {colors['window']};
                color: {colors['window_text']};
                border: 1px solid {colors['border']};
                border-radius: 12px;
                padding: 8px;
                font-size: 16px;
            }}
            QListWidget::item {{
                padding: 8px;
                border-radius: 8px;
                margin: 2px 0;
            }}
            QListWidget::item:selected {{
                background-color: {colors['highlight']};
                color: {colors['highlight_text']};
            }}
            QListWidget::item:hover:!selected {{
                background-color: {colors['hover']};
            }}
            QListWidget QScrollArea {{
                background-color: transparent;
                border: none;
            }}
            QListWidget QScrollBar:vertical {{
                width: 8px;
                background-color: {colors['base']};
                border-radius: 4px;
            }}
        """)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # 使用ThemeManager的颜色
        colors = self.theme_manager.get_colors()
        painter.setBrush(QBrush(QColor(colors['window'])))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 14, 14)
    
    def real_time_search(self, keyword):
        keyword = keyword.strip()
        
        if keyword:
            # 搜索应用（带分数）
            max_app_results = self.settings_manager.get('max_app_results', 20)
            app_results_with_scores = self.app_scanner.search_apps(keyword, with_scores=True)
            app_results_with_scores = app_results_with_scores[:max_app_results]
            
            # 搜索文件
            file_results = []
            if self.settings_manager.get('enable_file_search', True):
                max_file_results = self.settings_manager.get('max_file_results', 30)
                file_results = self.file_searcher.search(keyword, max_file_results)
                if not file_results:
                    file_results = self.file_searcher.search_fallback(keyword, max_file_results)

            # 合并并智能排序
            self.search_results = self.merge_and_sort_results(keyword, app_results_with_scores, file_results)
            self.update_app_list()
        else:
            self.search_results = []
            self.app_list.clear()
            self.app_list.hide()
            self.adjust_window_size()
    
    def merge_and_sort_results(self, keyword, app_results_with_scores, file_results):
        """合并应用和文件搜索结果，并智能排序"""
        combined = []
        
        # 应用结果：使用从 app_scanner 获得的原始分数
        for item in app_results_with_scores:
            app = item['app']
            app['type'] = 'app'
            app['result_name'] = app['name']
            app['score'] = item['score']
            combined.append(app)
        
        # 文件结果：直接使用从 file_searcher 获得的分数
        for file in file_results:
            file['type'] = 'file'
            file['result_name'] = file['name']
            # 文件的分数已经在 file_search.py 中计算好了，直接使用
            # 注意：应用有 +100 的优先加分，我们需要给应用加回来
            # 但文件不需要这个加分，保持原样即可
            combined.append(file)
        
        # 排序：首先按分数降序，同样分数时应用（0）排在文件（1）前面
        combined.sort(key=lambda x: (-x['score'], 0 if x['type'] == 'app' else 1))
        
        return combined
    
    def update_app_list(self):
        self.app_list.clear()
        
        if not self.search_results:
            self.app_list.hide()
            self.adjust_window_size()
            return
        
        for idx, item_data in enumerate(self.search_results):
            # 构建显示文本
            display_text = item_data['name']
            if item_data.get('type') == 'file':
                # 对于文件，添加路径提示
                dir_path = item_data.get('dir_path', '')
                if dir_path:
                    # 只显示路径的最后部分
                    short_dir = os.path.basename(dir_path)
                    if short_dir:
                        display_text = f"{display_text}  ({short_dir})"
            
            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, item_data)
            item.setSizeHint(QSize(0, 50))
            
            # 获取并设置图标
            icon = self.get_item_icon(item_data)
            if icon:
                item.setIcon(icon)
            
            self.app_list.addItem(item)
        
        self.selected_index = 0
        if self.app_list.count() > 0:
            self.app_list.setCurrentRow(self.selected_index)
        
        self.app_list.show()
        self.adjust_window_size()
    
    def get_item_icon(self, item_data):
        """获取项目图标（应用或文件）"""
        file_path = item_data.get('path', '')
        icon_path = item_data.get('icon', '')
        
        # 优先使用 icon 属性
        if icon_path and os.path.exists(icon_path):
            return self.load_icon_from_file(icon_path)
        elif file_path and os.path.exists(file_path):
            return self.load_icon_from_file(file_path)
        
        return None
    
    def load_icon_from_file(self, file_path):
        """从文件加载图标"""
        if not os.path.exists(file_path):
            return None
        
        try:

            provider = QFileIconProvider()
            file_info = QFileInfo(file_path)
            icon = provider.icon(file_info)
            if not icon.isNull():
                return icon
        except Exception:
            pass
        
        return None
    
    def adjust_window_size(self):
        if self.app_list.isVisible() and self.app_list.count() > 0:
            count = self.app_list.count()
            item_height = self.app_list.sizeHintForRow(0) 
            max_item = 5
            if count <= max_item:
                # 给每个项目留足够的空间，确保不出现滚动条
                list_height = item_height * count + 20
                self.app_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            else:
                list_height = min(item_height * max_item + 20, 250 + 20)
                self.app_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            
            total_height = 60 + list_height
            current_pos = self.pos()
            self.setFixedSize(600, total_height)
            self.app_list.setMaximumHeight(list_height)
            self.app_list.setMinimumHeight(list_height)  # 确保最小高度足够
            self.move(current_pos)
        else:
            current_pos = self.pos()
            self.setFixedSize(600, 60)
            self.move(current_pos)
    
    def on_item_clicked(self, item):
        self.selected_index = self.app_list.row(item)
    
    def on_item_double_clicked(self, item):
        item_data = item.data(Qt.ItemDataRole.UserRole)
        if item_data:
            self.launch_item(item_data)
            self.hide_window()
    
    def launch_selected_app(self):
        if self.search_results and 0 <= self.selected_index < len(self.search_results):
            item_data = self.search_results[self.selected_index]
            self.launch_item(item_data)
            self.hide_window()
    
    def launch_item(self, item_data):
        """启动应用或打开文件"""
        path = item_data.get('path', '')
        if path and os.path.exists(path):
            try:
                os.startfile(path)
            except Exception as e:
                print(f"启动失败: {e}")
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide_window()
        elif event.key() == Qt.Key.Key_Down:
            self.navigate_down()
        elif event.key() == Qt.Key.Key_Up:
            self.navigate_up()
        else:
            super().keyPressEvent(event)
    
    def navigate_down(self):
        if self.search_results:
            self.selected_index = (self.selected_index + 1) % len(self.search_results)
            self.app_list.setCurrentRow(self.selected_index)
    
    def navigate_up(self):
        if self.search_results:
            self.selected_index = (self.selected_index - 1) % len(self.search_results)
            self.app_list.setCurrentRow(self.selected_index)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self.drag_pos)
            event.accept()
    
    def mouseReleaseEvent(self, event):
        self.drag_pos = None
    
    def event(self, event):
        if event.type() == event.Type.WindowDeactivate:
            QTimer.singleShot(100, self.hide_window)
        return super().event(event)
    
    def toggle_window(self):
        if self.isVisible():
            self.hide_window()
        else:
            self.show_window()
    
    def show_window(self):
        # 重新扫描应用（包括自定义目录）
        self.app_scanner.scan_all_apps()
        self.search_input.clear()
        self.search_results = []
        self.app_list.clear()
        self.app_list.hide()
        self.setFixedSize(600, 60)
        
        # 计算并设置位置
        screen_center = self.screen().geometry().center()
        window_rect = self.rect()
        self.move(screen_center - window_rect.center() + QPoint(0, -200))
        
        self.show()
        QTimer.singleShot(50, self.activate_window)
    
    def activate_window(self):
        self.activateWindow()
        self.raise_()
        QTimer.singleShot(50, self.set_focus)
    
    def set_focus(self):
        self.search_input.setFocus()
        self.search_input.selectAll()
    
    def hide_window(self):
        self.hide()
    
    def show_settings(self):
        if not self.settings_window:
            self.settings_window = SettingsWindow(
                self.settings_manager,
                self.theme_manager,
                self.auto_start_manager,
                self.signal_handler
            )
        self.settings_window.show()
        self.settings_window.activateWindow()
    
    def show_clipboard(self):
        if not self.clipboard_window:
            self.clipboard_window = ClipboardWindow(
                self.settings_manager,
                self.theme_manager,
                self.signal_handler,
                self.clipboard_manager  # 传递已有的 ClipboardManager 实例
            )
        self.clipboard_window.show()
        self.clipboard_window.activateWindow()
        self.clipboard_window.raise_()
        # 聚焦搜索框
        self.clipboard_window.search_input.setFocus()
    
    def on_theme_changed(self, theme):
        self.update_search_input_style()
        self.update_app_list_style()
        self.apply_tray_theme()
        self.update()
    
    def show_notification(self):
        """显示启动通知"""
        if self.tray_icon is not None:
            self.tray_icon.showMessage(
                "KillAll3k",
                "程序已启动！按 Alt+Space 打开搜索框",
                QSystemTrayIcon.MessageIcon.Information,
                3000
            )
    
    def setup_tray(self):
        """设置系统托盘图标"""
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logo.ico')
        try:
            icon = QIcon(icon_path)
        except Exception:
            # 如果加载失败，使用默认图标
            icon = self.create_tray_icon()
        
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(icon)
        self.tray_icon.setToolTip("KillAll3k")
        
        # 创建托盘菜单
        self.tray_menu = QMenu()
        
        self.action_show = QAction("显示搜索窗口", self)
        self.action_show.triggered.connect(self.on_tray_show)
        self.tray_menu.addAction(self.action_show)
        
        self.action_clipboard = QAction("剪贴板历史", self)
        self.action_clipboard.triggered.connect(self.on_tray_clipboard)
        self.tray_menu.addAction(self.action_clipboard)
        
        self.action_settings = QAction("设置", self)
        self.action_settings.triggered.connect(self.on_tray_settings)
        self.tray_menu.addAction(self.action_settings)
        
        self.tray_menu.addSeparator()
        
        self.action_quit = QAction("退出", self)
        self.action_quit.triggered.connect(self.on_tray_quit)
        self.tray_menu.addAction(self.action_quit)
        
        self.tray_icon.setContextMenu(self.tray_menu)
        
        # 托盘图标双击事件
        self.tray_icon.activated.connect(self.on_tray_activated)
        
        self.tray_icon.show()
        
        # 应用主题
        self.apply_tray_theme()
    
    def create_tray_icon(self):
        """创建默认托盘图标"""
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 绘制蓝色圆形
        painter.setBrush(QColor(59, 130, 246))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(8, 8, 48, 48)
        
        # 绘制白色 K 字
        painter.setPen(QColor(255, 255, 255))
        font = painter.font()
        font.setPixelSize(40)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "K")
        
        painter.end()
        
        return QIcon(pixmap)
    
    def apply_tray_theme(self):
        """应用托盘菜单主题"""
        if not self.theme_manager:
            return
        colors = self.theme_manager.get_colors()
        
        # 设置菜单样式
        self.tray_menu.setStyleSheet(f"""
            QMenu {{
                background-color: {colors['base']};
                border: 1px solid {colors['border']};
                padding: 4px;
            }}
            QMenu::item {{
                background-color: transparent;
                padding: 6px 24px 6px 24px;
                color: {colors['base_text']};
            }}
            QMenu::item:selected {{
                background-color: {colors['highlight']};
                color: {colors['highlight_text']};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {colors['border']};
                margin: 4px 8px 4px 8px;
            }}
        """)
    
    def on_tray_activated(self, reason):
        """托盘图标激活事件"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.on_tray_show()
    
    def setup_hotkey(self):
        # 初始化搜索框热键
        self.update_search_hotkey()
        # 初始化剪贴板热键
        self.update_clipboard_hotkey()
        # 初始化截图热键
        self.update_screenshot_hotkey()
    
    def update_search_hotkey(self):
        """动态更新搜索框热键状态"""
        # 先注销旧的热键
        if self.current_search_hotkey:
            try:
                keyboard.remove_hotkey(self.current_search_hotkey)
            except Exception as e:
                print(f"Failed to remove old search hotkey: {e}")
            self.current_search_hotkey = None
        
        # 注册新的热键
        search_hotkey = self.settings_manager.get('search_hotkey', 'alt+space')
        if search_hotkey:
            try:
                keyboard.add_hotkey(search_hotkey, lambda: self.signal_handler.toggle_window.emit(), suppress=True)
                self.current_search_hotkey = search_hotkey
            except Exception as e:
                print(f"Failed to add search hotkey: {e}")
    
    def update_clipboard_hotkey(self):
        """动态更新剪贴板热键状态"""
        # 先注销旧的热键
        if self.current_clipboard_hotkey:
            try:
                keyboard.remove_hotkey(self.current_clipboard_hotkey)
            except Exception as e:
                print(f"Failed to remove old clipboard hotkey: {e}")
            self.current_clipboard_hotkey = None
        
        # 检查剪贴板是否启用
        clipboard_enabled = self.settings_manager.get('clipboard_enabled', True)
        if not clipboard_enabled:
            return
        
        # 注册新的热键
        clipboard_hotkey = self.settings_manager.get('clipboard_hotkey', 'win+v')
        if clipboard_hotkey:
            try:
                keyboard.add_hotkey(clipboard_hotkey, lambda: self.signal_handler.show_clipboard.emit(), suppress=True)
                self.current_clipboard_hotkey = clipboard_hotkey
            except Exception as e:
                print(f"Failed to add clipboard hotkey: {e}")
    
    def update_screenshot_hotkey(self):
        """动态更新截图热键状态"""
        # 先注销旧的热键
        if self.current_screenshot_hotkey:
            try:
                keyboard.remove_hotkey(self.current_screenshot_hotkey)
            except Exception as e:
                print(f"Failed to remove old screenshot hotkey: {e}")
            self.current_screenshot_hotkey = None
        
        # 检查截图是否启用
        screenshot_enabled = self.settings_manager.get('screenshot_enabled', True)
        if not screenshot_enabled:
            return
        
        # 注册新的热键
        screenshot_hotkey = self.settings_manager.get('screenshot_hotkey', 'ctrl+alt+a')
        if screenshot_hotkey:
            try:
                keyboard.add_hotkey(screenshot_hotkey, lambda: self.signal_handler.take_screenshot.emit(), suppress=True)
                self.current_screenshot_hotkey = screenshot_hotkey
            except Exception as e:
                print(f"Failed to add screenshot hotkey: {e}")
    
    def take_screenshot(self):
        """执行截图操作"""
        self.hide_window()
        QTimer.singleShot(100, self.screenshot_manager.take_screenshot)
    
    def on_tray_show(self):
        self.signal_handler.show_window.emit()
    
    def on_tray_clipboard(self):
        self.signal_handler.show_clipboard.emit()
    
    def on_tray_settings(self):
        self.signal_handler.show_settings.emit()
    
    def on_tray_quit(self):
        self.signal_handler.quit_app.emit()
    
    def safe_quit(self):
        if self.tray_icon:
            self.tray_icon.hide()
        QTimer.singleShot(100, QApplication.quit)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SearchWindow()
    sys.exit(app.exec())
