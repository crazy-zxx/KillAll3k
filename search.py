import sys
import os
import threading
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLineEdit, QHBoxLayout, QMessageBox, QVBoxLayout, QListWidget, QListWidgetItem, QLabel
)
from PyQt6.QtCore import Qt, QPoint, QTimer, QSize
from PyQt6.QtGui import QPainter, QBrush, QColor, QIcon
import pystray
from PIL import Image, ImageDraw
import keyboard
from settings import (
    SignalHandler, SettingsManager, ThemeManager, AutoStartManager, SettingsWindow
)
from app_scanner import AppScanner


class SearchWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.drag_pos = None
        self.tray_icon = None
        self.settings_window = None
        self.settings_manager = SettingsManager()
        self.theme_manager = ThemeManager(None)
        self.auto_start_manager = AutoStartManager()
        self.signal_handler = SignalHandler()
        self.theme_manager.signal_handler = self.signal_handler
        self.app_scanner = AppScanner(self.settings_manager)
        self.search_results = []
        self.selected_index = 0
        
        # 检查是否需要以管理员权限运行
        self.check_admin_privilege()
        
        self.signal_handler.toggle_window.connect(self.toggle_window)
        self.signal_handler.show_window.connect(self.show_window)
        self.signal_handler.show_settings.connect(self.show_settings)
        self.signal_handler.quit_app.connect(self.safe_quit)
        self.signal_handler.theme_changed.connect(self.on_theme_changed)
        
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
        self.app_list.setMaximumHeight(400)
        self.app_list.hide()
        self.app_list.itemClicked.connect(self.on_item_clicked)
        self.app_list.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.update_app_list_style()
        
        main_layout.addWidget(self.app_list)
        
        self.setLayout(main_layout)
    
    def update_search_input_style(self):
        theme = self.theme_manager.current_theme
        if theme == 'auto':
            theme = 'dark' if self.theme_manager.is_system_dark() else 'light'
        
        if theme == 'dark':
            self.search_input.setStyleSheet("""
                QLineEdit {
                    background-color: #2b3548;
                    color: #e2e8f0;
                    border: 1px solid #38455a;
                    border-radius: 12px;
                    padding-left: 22px;
                    padding-right: 22px;
                    font-size: 20px;
                }
                QLineEdit:focus {
                    border: 1px solid #60a5fa;
                    outline: none;
                }
            """)
        else:
            self.search_input.setStyleSheet("""
                QLineEdit {
                    background-color: #ffffff;
                    color: #0f172a;
                    border: 1px solid #e2e8f0;
                    border-radius: 12px;
                    padding-left: 22px;
                    padding-right: 22px;
                    font-size: 20px;
                }
                QLineEdit:focus {
                    border: 1px solid #3b82f6;
                    outline: none;
                }
            """)
    
    def update_app_list_style(self):
        theme = self.theme_manager.current_theme
        if theme == 'auto':
            theme = 'dark' if self.theme_manager.is_system_dark() else 'light'
        
        if theme == 'dark':
            self.app_list.setStyleSheet("""
                QListWidget {
                    background-color: #1E293B;
                    color: #e2e8f0;
                    border: 1px solid #38455a;
                    border-radius: 12px;
                    padding: 8px;
                    font-size: 16px;
                }
                QListWidget::item {
                    padding: 12px;
                    border-radius: 8px;
                    margin: 4px 0;
                }
                QListWidget::item:selected {
                    background-color: #3B82F6;
                    color: white;
                }
                QListWidget::item:hover:!selected {
                    background-color: #334155;
                }
            """)
        else:
            self.app_list.setStyleSheet("""
                QListWidget {
                    background-color: #F8FAFC;
                    color: #0f172a;
                    border: 1px solid #e2e8f0;
                    border-radius: 12px;
                    padding: 8px;
                    font-size: 16px;
                }
                QListWidget::item {
                    padding: 12px;
                    border-radius: 8px;
                    margin: 4px 0;
                }
                QListWidget::item:selected {
                    background-color: #3B82F6;
                    color: white;
                }
                QListWidget::item:hover:!selected {
                    background-color: #E2E8F0;
                }
            """)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        theme = self.theme_manager.current_theme
        if theme == 'auto':
            theme = 'dark' if self.theme_manager.is_system_dark() else 'light'
        
        if theme == 'dark':
            painter.setBrush(QBrush(QColor("#1E293B")))
        else:
            painter.setBrush(QBrush(QColor("#F8FAFC")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 14, 14)
    
    def real_time_search(self, keyword):
        keyword = keyword.strip()
        
        if keyword:
            self.search_results = self.app_scanner.search_apps(keyword)
            self.update_app_list()
        else:
            self.search_results = []
            self.app_list.clear()
            self.app_list.hide()
            self.adjust_window_size()
    
    def update_app_list(self):
        self.app_list.clear()
        
        if not self.search_results:
            self.app_list.hide()
            self.adjust_window_size()
            return
        
        for idx, app in enumerate(self.search_results):
            item = QListWidgetItem(app['name'])
            item.setData(Qt.ItemDataRole.UserRole, app)
            self.app_list.addItem(item)
        
        self.selected_index = 0
        if self.app_list.count() > 0:
            self.app_list.setCurrentRow(self.selected_index)
        
        self.app_list.show()
        self.adjust_window_size()
    
    def adjust_window_size(self):
        if self.app_list.isVisible() and self.app_list.count() > 0:
            count = self.app_list.count()
            item_height = self.app_list.sizeHintForRow(0) or 50
            
            if count <= 6:
                list_height = item_height * count + 20
                self.app_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            else:
                list_height = min(item_height * 6 + 20, 300)
                self.app_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            
            total_height = 60 + list_height
            current_pos = self.pos()
            self.setFixedSize(600, total_height)
            self.app_list.setMaximumHeight(list_height)
            self.move(current_pos)
        else:
            current_pos = self.pos()
            self.setFixedSize(600, 60)
            self.move(current_pos)
    
    def on_item_clicked(self, item):
        self.selected_index = self.app_list.row(item)
    
    def on_item_double_clicked(self, item):
        app = item.data(Qt.ItemDataRole.UserRole)
        if app:
            self.app_scanner.launch_app(app['path'])
            self.hide_window()
    
    def launch_selected_app(self):
        if self.search_results and 0 <= self.selected_index < len(self.search_results):
            app = self.search_results[self.selected_index]
            self.app_scanner.launch_app(app['path'])
            self.hide_window()
    
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
    
    def on_theme_changed(self, theme):
        self.update_search_input_style()
        self.update_app_list_style()
        self.update()
    
    def show_notification(self):
        """显示启动通知"""
        if self.tray_icon is not None:
            self.tray_icon.notify(
                title="KillAll3k",
                message="程序已启动！按 Alt+Space 打开搜索框"
            )
    
    def setup_tray(self):
        icon_image = self.create_tray_icon()
        menu = pystray.Menu(
            pystray.MenuItem('显示窗口', self.on_tray_show, default=True),
            pystray.MenuItem('设置', self.on_tray_settings),
            pystray.MenuItem('退出', self.on_tray_quit)
        )
        self.tray_icon = pystray.Icon("KillAll3k", icon_image, "KillAll3k", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()
    
    def create_tray_icon(self):
        width, height = 64, 64
        image = Image.new('RGBA', (width, height), (30, 41, 59, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle([8, 8, 56, 56], radius=12, fill=(30, 41, 59, 255))
        draw.text((32, 32), 'K', fill=(226, 232, 240, 255), anchor='mm', font=None)
        return image
    
    def setup_hotkey(self):
        keyboard.add_hotkey('alt+space', lambda: self.signal_handler.toggle_window.emit(), suppress=True)
    
    def on_tray_show(self, icon, item):
        self.signal_handler.show_window.emit()
    
    def on_tray_settings(self, icon, item):
        self.signal_handler.show_settings.emit()
    
    def on_tray_quit(self, icon, item):
        self.signal_handler.quit_app.emit()
    
    def safe_quit(self):
        def stop_tray():
            if self.tray_icon:
                self.tray_icon.stop()
        threading.Thread(target=stop_tray, daemon=True).start()
        QTimer.singleShot(100, QApplication.quit)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SearchWindow()
    sys.exit(app.exec())
