import sys
import os
import webbrowser
import time
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QScrollArea, QFrame, QLabel, QCheckBox, QMenu,
    QApplication, QDialog, QTextEdit, QComboBox, QMessageBox
)
from PyQt6.QtCore import Qt, QSize, QPoint, pyqtSignal, QMimeData, QTimer, QThread
from PyQt6.QtGui import QPainter, QBrush, QColor, QPixmap, QDrag, QPen, QCursor, QIcon
from clipboard_manager import ClipboardManager, ClipboardItem
from screenshot import AnnotationEditor


class TextEditDialog(QDialog):
    def __init__(self, initial_text, parent=None, theme_manager=None):
        super().__init__(parent)
        self.initial_text = initial_text
        self.theme_manager = theme_manager
        self.setWindowTitle("编辑文本")
        self.setFixedSize(450, 350)
        self.init_ui()
        self.apply_theme()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.title_label = QLabel("编辑内容：")
        self.title_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(self.title_label)

        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(self.initial_text)
        layout.addWidget(self.text_edit)

        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(self.cancel_btn)

        self.ok_btn = QPushButton("保存")
        self.ok_btn.clicked.connect(self.accept)
        buttons_layout.addWidget(self.ok_btn)

        layout.addLayout(buttons_layout)
        self.setLayout(layout)

    def apply_theme(self):
        if not self.theme_manager:
            return
        colors = self.theme_manager.get_colors()
        self.title_label.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {colors['window_text']};")
        self.text_edit.setStyleSheet(f"""
            QTextEdit {{
                border: 1px solid {colors['border']};
                border-radius: 8px;
                padding: 12px;
                font-size: 14px;
                line-height: 1.6;
                background-color: {colors['base']};
                color: {colors['base_text']};
            }}
            QTextEdit:focus {{
                border: 1px solid {colors['highlight']};
            }}
        """)
        self.cancel_btn.setStyleSheet(f"""
            QPushButton {{
                padding: 10px 24px;
                border: 1px solid {colors['border']};
                border-radius: 6px;
                background-color: {colors['base']};
                color: {colors['text_secondary']};
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {colors['hover']};
            }}
        """)
        self.ok_btn.setStyleSheet(f"""
            QPushButton {{
                padding: 10px 24px;
                border: none;
                border-radius: 6px;
                background-color: {colors['highlight']};
                color: {colors['highlight_text']};
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {colors['highlight']};
                opacity: 0.9;
            }}
        """)
        self.setStyleSheet(f"background-color: {colors['window']};")

    def get_text(self):
        return self.text_edit.toPlainText()


class AIWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, model_data, content, content_type, task_type, proxy_config):
        super().__init__()
        self.model_data = model_data
        self.content = content
        self.content_type = content_type
        self.task_type = task_type
        self.proxy_config = proxy_config

    def encode_image_to_base64(self, pixmap):
        from PyQt6.QtCore import QBuffer
        import base64

        buffer = QBuffer()
        buffer.open(QBuffer.OpenModeFlag.WriteOnly)
        pixmap.save(buffer, "PNG")
        image_data = buffer.data().toBase64()
        return image_data.data().decode('utf-8')

    def run(self):
        try:
            import requests

            api_url = self.model_data['api_url']
            api_key = self.model_data['api_key']
            model = self.model_data['model']

            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }

            user_content = None

            if self.task_type == "explain":
                if self.content_type == "text":
                    user_content = f"请详细解释以下文本内容，用简洁清晰的语言阐述其含义。全程只输出无格式纯文本，严禁使用 Markdown、代码块、序号列表、项目符号、加粗、表格、引用等任何排版语法，只用普通文字自然换行。\n\n{self.content}"
                elif self.content_type == "image":
                    base64_image = self.encode_image_to_base64(self.content)
                    user_content = [
                        {
                            "type": "text",
                            "text": "请描述一下这个图片的内容和场景。全程只输出无格式纯文本，严禁使用 Markdown、代码块、序号列表、项目符号、加粗、表格、引用等任何排版语法，只用普通文字自然换行。"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}"
                            }
                        }
                    ]
            elif self.task_type == "translate":
                user_content = f"请将以下文本翻译成中文，保持原意不变。全程只输出无格式纯文本，严禁使用 Markdown、代码块、序号列表、项目符号、加粗、表格、引用等任何排版语法，只用普通文字自然换行。\n\n{self.content}"

            data = {
                'model': model,
                'messages': [
                    {'role': 'user', 'content': user_content}
                ],
                'temperature': 0.7,
                'stream': False
            }

            if 'ollama' in api_url.lower() or 'localhost' in api_url.lower():
                response = requests.post(api_url, json=data, proxies=self.proxy_config, timeout=60)
            else:
                response = requests.post(api_url, headers=headers, json=data, proxies=self.proxy_config, timeout=60)

            if response.status_code == 200:
                result = response.json()

                if 'choices' in result and len(result['choices']) > 0:
                    ai_response = result['choices'][0]['message']['content']
                    self.finished.emit(ai_response.strip())
                elif 'message' in result:
                    ai_response = result['message']['content']
                    self.finished.emit(ai_response.strip())
                else:
                    self.error.emit(f"无法解析AI响应：\n{str(result)}")
            else:
                self.error.emit(f"请求失败，状态码：{response.status_code}\n{response.text}")

        except Exception as e:
            self.error.emit(f"发生错误：\n{str(e)}")


class AIChatDialog(QDialog):
    def __init__(self, content, content_type, task_type, settings_manager, theme_manager=None, parent=None):
        super().__init__(parent)
        self.content = content
        self.content_type = content_type
        self.task_type = task_type
        self.settings_manager = settings_manager
        self.theme_manager = theme_manager
        self.setWindowTitle("AI 处理")
        self.setFixedSize(600, 500)
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.current_model_index = 0
        self.worker = None
        self.init_ui()
        self.apply_theme()
        self.generate_response()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        self.title_label = QLabel("AI 翻译" if self.task_type == "translate" else "AI 解释")
        layout.addWidget(self.title_label)

        model_layout = QHBoxLayout()
        self.model_label = QLabel("选择模型：")
        self.model_combo = QComboBox()
        self.load_models()
        model_layout.addWidget(self.model_label)
        model_layout.addWidget(self.model_combo)
        model_layout.addStretch()
        layout.addLayout(model_layout)

        self.result_label = QLabel("AI 回复：")
        layout.addWidget(self.result_label)

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setPlaceholderText("正在生成...")
        layout.addWidget(self.result_text)

        buttons_layout = QHBoxLayout()

        self.regenerate_btn = QPushButton("🔄 重新生成")
        self.regenerate_btn.clicked.connect(self.generate_response)
        buttons_layout.addWidget(self.regenerate_btn)
        buttons_layout.addStretch()

        self.copy_btn = QPushButton("📋 复制")
        self.copy_btn.clicked.connect(self.copy_result)
        buttons_layout.addWidget(self.copy_btn)

        layout.addLayout(buttons_layout)
        self.setLayout(layout)

    def apply_theme(self):
        if not self.theme_manager:
            return
        colors = self.theme_manager.get_colors()
        self.title_label.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {colors['window_text']};")
        self.model_label.setStyleSheet(f"font-size: 13px; color: {colors['text_secondary']};")
        self.model_combo.setStyleSheet(self.theme_manager.get_combobox_style())
        self.result_label.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {colors['window_text']}; margin-top: 10px;")
        self.result_text.setStyleSheet(f"""
            QTextEdit {{
                border: 1px solid {colors['border']};
                border-radius: 8px;
                padding: 15px;
                font-size: 14px;
                line-height: 1.8;
                background-color: {colors['base']};
                color: {colors['base_text']};
            }}
        """)
        self.regenerate_btn.setStyleSheet(f"""
            QPushButton {{
                padding: 10px 20px;
                border: 1px solid {colors['highlight']};
                border-radius: 6px;
                background-color: {colors['base']};
                color: {colors['highlight']};
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {colors['highlight']};
                color: {colors['highlight_text']};
            }}
            QPushButton:disabled {{
                background-color: {colors['hover']};
                border-color: {colors['border']};
                color: {colors['text_secondary']};
            }}
        """)
        self.copy_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {colors['highlight']};
                color: {colors['highlight_text']};
                padding: 10px 20px;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
        """)
        self.setStyleSheet(f"background-color: {colors['window']};")

    def load_models(self):
        self.model_combo.clear()
        ai_models = self.settings_manager.get('ai_models', [])
        enabled_models = [model for model in ai_models if model.get('enabled', True)]
        if not enabled_models:
            self.model_combo.addItem("没有配置模型")
            self.model_combo.setEnabled(False)
            return

        for idx, model in enumerate(enabled_models):
            self.model_combo.addItem(model['name'], model)

        if self.current_model_index < self.model_combo.count():
            self.model_combo.setCurrentIndex(self.current_model_index)

    def get_proxy_config(self):
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

    def generate_response(self):
        self.result_text.setPlaceholderText("正在生成...")
        self.result_text.clear()
        self.regenerate_btn.setEnabled(False)

        model_data = self.model_combo.currentData()
        if not model_data:
            self.result_text.setPlainText("未配置可用的AI模型，请在设置中添加模型。")
            self.regenerate_btn.setEnabled(True)
            return

        proxy_config = self.get_proxy_config()

        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()

        self.worker = AIWorker(model_data, self.content, self.content_type, self.task_type, proxy_config)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.error.connect(self.on_worker_error)
        self.worker.start()

    def on_worker_finished(self, result):
        self.result_text.setPlainText(result)
        self.regenerate_btn.setEnabled(True)

    def on_worker_error(self, error_message):
        self.result_text.setPlainText(error_message)
        self.regenerate_btn.setEnabled(True)

    def copy_result(self):
        text = self.result_text.toPlainText()
        if text:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            QMessageBox.information(self, "提示", "复制成功！")

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()
        super().closeEvent(event)


class ClipboardCardWidget(QWidget):
    clicked = pyqtSignal(object)
    drag_started = pyqtSignal(object, int)
    favorite_toggled = pyqtSignal(object)
    pin_toggled = pyqtSignal(object)
    item_deleted = pyqtSignal(object)

    def __init__(self, item, parent=None, index=0, is_selected=False, theme_manager=None):
        super().__init__(parent)
        self.item = item
        self.index = index
        self.setObjectName("clipboard_card")
        self._is_hovered = False
        self._is_selected = is_selected
        self.drag_start_pos = None
        self.action_buttons = None
        self.theme_manager = theme_manager
        self.labels = []  # 保存所有标签引用
        self.init_ui()
        self.apply_theme()
        self.update_label_colors()  # 确保初始状态颜色正确

    def set_selected(self, selected):
        self._is_selected = selected
        self.update_label_colors()
        self.update()

    def update_label_colors(self):
        """根据当前状态动态更新标签文字颜色"""
        if not self.theme_manager:
            return
        colors = self.theme_manager.get_colors()
        
        # 确定当前应该使用的文字颜色
        if self._is_selected:
            text_color = colors['highlight_text']
        else:
            text_color = colors['base_text']
        
        for label_type, label in self.labels:
            try:
                if label_type == 'time':
                    if self._is_selected:
                        label.setStyleSheet(f"color: {colors['highlight_text']}; font-size: 10px; font-weight: 500;")
                    else:
                        label.setStyleSheet(f"color: {colors['text_secondary']}; font-size: 10px; font-weight: 500;")
                elif label_type == 'info':
                    if self._is_selected:
                        label.setStyleSheet(f"color: {colors['highlight_text']}; font-size: 10px; padding-left: 8px;")
                    else:
                        label.setStyleSheet(f"color: {colors['text_secondary']}; font-size: 10px; padding-left: 8px;")
                elif label_type == 'content':
                    label.setStyleSheet(f"color: {text_color}; font-size: 12px; line-height: 1.6;")
                elif label_type == 'desc':
                    if self._is_selected:
                        label.setStyleSheet(f"color: {colors['highlight_text']}; font-size: 12px;")
                    else:
                        label.setStyleSheet(f"color: {colors['text_secondary']}; font-size: 12px;")
            except RuntimeError:
                pass

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 获取当前主题颜色
        colors = self.theme_manager.get_colors() if self.theme_manager else None
        
        # 根据状态确定背景色
        if self._is_selected and self._is_hovered:
            if colors:
                bg_color = QColor(colors['highlight'])  # 使用主题高亮色
            else:
                bg_color = QColor(147, 197, 253)  # 默认浅蓝色
        elif self._is_selected:
            if colors:
                # 创建一个稍微浅一点的高亮色作为选中背景
                base_color = QColor(colors['highlight'])
                h, s, v, a = base_color.getHsv()
                bg_color = QColor.fromHsv(h, max(s - 30, 100), min(v + 30, 255), 50)
            else:
                bg_color = QColor(219, 234, 254)  # 默认浅蓝色
        elif self._is_hovered:
            if colors:
                bg_color = QColor(colors['hover'])  # 使用主题悬停色
            else:
                bg_color = QColor(226, 232, 240)  # 默认浅灰色
        else:
            if colors:
                bg_color = QColor(colors['base'])  # 使用主题背景色
            else:
                bg_color = QColor(255, 255, 255)  # 默认白色

        # 绘制背景
        painter.setBrush(QBrush(bg_color))

        # 根据是否选中确定边框
        if self._is_selected:
            if colors:
                painter.setPen(QPen(QColor(colors['highlight']), 2))  # 使用主题高亮色
            else:
                painter.setPen(QPen(QColor(59, 130, 246), 2))  # 默认蓝色边框
        else:
            if colors:
                painter.setPen(QPen(QColor(colors['border']), 1))  # 使用主题边框色
            else:
                painter.setPen(QPen(QColor(226, 232, 240), 1))  # 默认浅灰色边框

        # 绘制圆角矩形
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 12, 12)

    def enterEvent(self, event):
        self._is_hovered = True
        if self.action_buttons:
            self.action_buttons.setVisible(True)
        self.update()  # 触发重绘
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        if self.action_buttons:
            self.action_buttons.setVisible(False)
        self.update()  # 触发重绘
        super().leaveEvent(event)

    def init_ui(self):
        self.setMaximumWidth(450)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        top_layout = QHBoxLayout()
        left_layout = QHBoxLayout()

        timestamp = self.item.timestamp.strftime("今天 %H:%M")
        time_label = QLabel(timestamp)
        time_label.setStyleSheet("font-size: 10px; font-weight: 500;")
        self.labels.append(('time', time_label))
        left_layout.addWidget(time_label)

        if self.item.type == ClipboardItem.TYPE_TEXT:
            info_text = f"{len(self.item.content.strip())} 字符"
            info_label = QLabel(info_text)
            info_label.setStyleSheet("font-size: 10px; padding-left: 8px;")
            self.labels.append(('info', info_label))
            left_layout.addWidget(info_label)
        elif self.item.type == ClipboardItem.TYPE_IMAGE:
            pixmap = QPixmap.fromImage(self.item.content)
            if not pixmap.isNull():
                info_text = f"{pixmap.width()}×{pixmap.height()}"
                info_label = QLabel(info_text)
                info_label.setStyleSheet("font-size: 10px; padding-left: 8px;")
                self.labels.append(('info', info_label))
                left_layout.addWidget(info_label)
        elif self.item.type == ClipboardItem.TYPE_FILE:
            if isinstance(self.item.content, list):
                info_text = f"{len(self.item.content)} 个文件"
            else:
                info_text = "1 个文件"
            info_label = QLabel(info_text)
            info_label.setStyleSheet("font-size: 10px; padding-left: 8px;")
            self.labels.append(('info', info_label))
            left_layout.addWidget(info_label)

        left_layout.addStretch()

        # Action buttons container - hidden by default
        self.action_buttons = QWidget()
        action_layout = QHBoxLayout(self.action_buttons)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(4)

        # Favorite button
        fav_btn = QPushButton("⭐" if self.item.favorite else "☆")
        fav_btn.setFixedSize(24, 24)
        fav_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        fav_btn.setStyleSheet("""
            QPushButton {
                border: none;
                background-color: transparent;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: rgba(0, 0, 0, 0.1);
                border-radius: 4px;
            }
        """)
        fav_btn.clicked.connect(lambda: self.favorite_toggled.emit(self.item))
        action_layout.addWidget(fav_btn)

        # Pin button
        pin_btn = QPushButton("📌" if self.item.pinned else "📍")
        pin_btn.setFixedSize(24, 24)
        pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        pin_btn.setStyleSheet("""
            QPushButton {
                border: none;
                background-color: transparent;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: rgba(0, 0, 0, 0.1);
                border-radius: 4px;
            }
        """)
        pin_btn.clicked.connect(lambda: self.pin_toggled.emit(self.item))
        action_layout.addWidget(pin_btn)

        # Delete button
        delete_btn = QPushButton("🗑️")
        delete_btn.setFixedSize(24, 24)
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.setStyleSheet("""
            QPushButton {
                border: none;
                background-color: transparent;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: rgba(255, 0, 0, 0.2);
                border-radius: 4px;
            }
        """)
        delete_btn.clicked.connect(lambda: self.item_deleted.emit(self.item))
        action_layout.addWidget(delete_btn)

        self.action_buttons.setVisible(False)

        right_layout = QHBoxLayout()
        right_layout.setSpacing(6)

        # Add action buttons
        right_layout.addWidget(self.action_buttons)

        # Smaller index label
        index_label = QLabel(str(self.index + 1))
        index_label.setFixedHeight(20)
        index_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        index_label.setStyleSheet("""
            background-color: #3b82f6;
            color: white;
            font-size: 10px;
            font-weight: 600;
            border-radius: 5px;
            padding: 4px;
        """)
        right_layout.addWidget(index_label)

        top_layout.addLayout(left_layout)
        top_layout.addLayout(right_layout)
        layout.addLayout(top_layout)

        if self.item.type == ClipboardItem.TYPE_TEXT:
            text = self.item.content.strip()
            lines = text.split('\n')
            if len(lines) > 3:
                display_text = '\n'.join(lines[:3]) + '...'
            else:
                display_text = text
                if len(display_text) > 200:
                    display_text = display_text[:200] + '...'

            content_label = QLabel(display_text)
            content_label.setWordWrap(True)
            content_label.setStyleSheet("""
                font-size: 12px;
                line-height: 1.6;
            """)
            self.labels.append(('content', content_label))
            layout.addWidget(content_label)

        elif self.item.type == ClipboardItem.TYPE_IMAGE:
            content_layout = QHBoxLayout()
            pixmap = QPixmap.fromImage(self.item.content)
            if not pixmap.isNull():
                thumb_label = QLabel()
                scaled_pixmap = pixmap.scaled(
                    80, 60,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                thumb_label.setPixmap(scaled_pixmap)
                thumb_label.setStyleSheet("border-radius: 6px;")
                content_layout.addWidget(thumb_label)
                content_layout.addSpacing(12)

            desc_label = QLabel("[图片]")
            desc_label.setStyleSheet("font-size: 12px;")
            self.labels.append(('desc', desc_label))
            content_layout.addWidget(desc_label)
            content_layout.addStretch()
            layout.addLayout(content_layout)

        elif self.item.type == ClipboardItem.TYPE_FILE:
            if isinstance(self.item.content, list):
                file_list = self.item.content[:3]
                for file_path in file_list:
                    file_layout = QHBoxLayout()
                    file_icon = QLabel("📄")
                    file_icon.setStyleSheet("font-size: 12px;")
                    file_layout.addWidget(file_icon)
                    file_name = QLabel(os.path.basename(file_path))
                    file_name.setStyleSheet("font-size: 12px;")
                    self.labels.append(('content', file_name))
                    file_layout.addWidget(file_name)
                    file_layout.addStretch()
                    layout.addLayout(file_layout)

                if len(self.item.content) > 3:
                    more_label = QLabel(f"... 还有 {len(self.item.content) - 3} 个文件")
                    more_label.setStyleSheet("font-size: 12px;")
                    self.labels.append(('desc', more_label))
                    layout.addWidget(more_label)
            else:
                file_layout = QHBoxLayout()
                file_icon = QLabel("📄")
                file_icon.setStyleSheet("font-size: 12px;")
                file_layout.addWidget(file_icon)
                file_name = QLabel(os.path.basename(self.item.content))
                file_name.setStyleSheet("font-size: 12px;")
                self.labels.append(('content', file_name))
                file_layout.addWidget(file_name)
                file_layout.addStretch()
                layout.addLayout(file_layout)

        self.setLayout(layout)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_start_pos:
            distance = (event.pos() - self.drag_start_pos).manhattanLength()
            if distance > QApplication.startDragDistance():
                self.drag_started.emit(self.item, self.index)
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.drag_start_pos:
                distance = (event.pos() - self.drag_start_pos).manhattanLength()
                if distance <= QApplication.startDragDistance():
                    self.clicked.emit(self.item)
        super().mouseReleaseEvent(event)

    def apply_theme(self):
        if not self.theme_manager:
            return
        # 调用 update_label_colors 来根据当前状态更新颜色
        self.update_label_colors()


class ClipboardWindow(QWidget):
    def __init__(self, settings_manager, theme_manager, signal_handler, clipboard_manager=None):
        super().__init__()
        self.settings_manager = settings_manager
        self.theme_manager = theme_manager
        self.signal_handler = signal_handler
        # 使用提供的 clipboard_manager 或创建新的
        if clipboard_manager is not None:
            self.clipboard_manager = clipboard_manager
        else:
            self.clipboard_manager = ClipboardManager(settings_manager)
        self.current_filter = "all"
        self.search_query = ""
        self.selected_items = []
        self.is_pinned = False
        self.is_multi_select = False
        self.drag_item = None
        self.drag_from_index = -1
        self.top_bar_widget = None
        self.current_selected_index = 0  # 当前选中项的索引
        self.card_widgets = []  # 保存所有卡片组件的引用

        self.clipboard_manager.history_updated.connect(self.refresh_history)
        self.signal_handler.theme_changed.connect(self.apply_theme)
        self.widgets_to_style = []  # 保存需要应用主题的控件
        self.init_ui()

    def init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(500, 600)
        self.setAcceptDrops(True)

        # 设置窗口图标
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logo.ico')
        self.setWindowIcon(QIcon(icon_path))

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        container = QWidget()
        container.setObjectName("clipboard_container")
        self.container = container
        self.widgets_to_style.append(('container', container))
        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(12, 12, 12, 12)
        container_layout.setSpacing(12)

        top_bar_widget = QWidget()
        top_bar_widget.setObjectName("top_bar_widget")
        self.top_bar_widget = top_bar_widget

        top_bar = QHBoxLayout(top_bar_widget)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索剪贴板历史...")
        self.search_input.textChanged.connect(self.on_search_changed)
        self.widgets_to_style.append(('lineedit', self.search_input))
        top_bar.addWidget(self.search_input, stretch=1)

        self.multi_select_btn = QPushButton("☑️")
        self.multi_select_btn.setCheckable(True)
        self.multi_select_btn.setFixedSize(36, 36)
        self.widgets_to_style.append(('pushbutton_icon', self.multi_select_btn))
        self.multi_select_btn.clicked.connect(self.toggle_multi_select)
        top_bar.addWidget(self.multi_select_btn)

        self.pin_btn = QPushButton("📌")
        self.pin_btn.setCheckable(True)
        self.pin_btn.setFixedSize(36, 36)
        self.widgets_to_style.append(('pushbutton_icon', self.pin_btn))
        self.pin_btn.clicked.connect(self.toggle_pin_window)
        top_bar.addWidget(self.pin_btn)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(36, 36)
        self.widgets_to_style.append(('pushbutton_icon', close_btn))
        close_btn.clicked.connect(self.hide)
        top_bar.addWidget(close_btn)

        container_layout.addWidget(top_bar_widget)

        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(4)

        self.filter_buttons = {}
        filters = [
            ("all", "全部", "#3b82f6"),
            ("favorite", "⭐ 收藏", "#f59e0b"),
            ("text", "📝 文本", "#6366f1"),
            ("image", "🖼️ 图片", "#10b981"),
            ("file", "📁 文件", "#8b5cf6")
        ]

        for filter_id, filter_text, color in filters:
            btn = QPushButton(filter_text)
            btn.setCheckable(True)
            btn.setProperty("filter_id", filter_id)
            btn.setProperty("color", color)
            if filter_id == "all":
                btn.setChecked(True)
            btn.clicked.connect(lambda checked, fid=filter_id: self.on_filter_changed(fid))
            self.update_filter_button_style(btn, filter_id == "all")
            filter_bar.addWidget(btn)
            self.filter_buttons[filter_id] = btn
            self.widgets_to_style.append(('filter_button', btn))

        filter_bar.addStretch()
        container_layout.addLayout(filter_bar)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                width: 8px;
                background-color: #f1f5f9;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background-color: #cbd5e1;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #94a3b8;
            }
        """)

        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout()
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(12)
        self.scroll_layout.addStretch()
        self.scroll_content.setLayout(self.scroll_layout)
        self.scroll_area.setWidget(self.scroll_content)

        container_layout.addWidget(self.scroll_area)

        self.bottom_bar = QHBoxLayout()
        self.bottom_bar.setSpacing(8)

        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.clicked.connect(self.toggle_select_all)
        self.select_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #6366f1;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4f46e5;
            }
        """)

        self.merge_copy_btn = QPushButton("复制合并")
        self.merge_copy_btn.clicked.connect(self.merge_copy_items)
        self.merge_copy_btn.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
        """)

        self.merge_paste_plain_btn = QPushButton("合并粘贴")
        self.merge_paste_plain_btn.clicked.connect(self.merge_paste_plain_items)
        self.merge_paste_plain_btn.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)

        self.batch_favorite_btn = QPushButton("批量收藏")
        self.batch_favorite_btn.clicked.connect(self.batch_favorite_items)
        self.batch_favorite_btn.setStyleSheet("""
            QPushButton {
                background-color: #f59e0b;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #d97706;
            }
        """)

        self.batch_delete_btn = QPushButton("批量删除")
        self.batch_delete_btn.clicked.connect(self.batch_delete_items)
        self.batch_delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #ef4444;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #dc2626;
            }
        """)

        self.bottom_bar.addWidget(self.select_all_btn)
        self.bottom_bar.addWidget(self.merge_copy_btn)
        self.bottom_bar.addWidget(self.merge_paste_plain_btn)
        self.bottom_bar.addWidget(self.batch_favorite_btn)
        self.bottom_bar.addWidget(self.batch_delete_btn)
        self.bottom_bar.addStretch()

        self.bottom_bar_widget = QWidget()
        self.bottom_bar_widget.setLayout(self.bottom_bar)
        self.bottom_bar_widget.setVisible(False)
        container_layout.addWidget(self.bottom_bar_widget)
        
        # 保存底部按钮引用
        self.widgets_to_style.append(('pushbutton_action', self.select_all_btn))
        self.widgets_to_style.append(('pushbutton_action', self.merge_copy_btn))
        self.widgets_to_style.append(('pushbutton_action', self.merge_paste_plain_btn))
        self.widgets_to_style.append(('pushbutton_action', self.batch_favorite_btn))
        self.widgets_to_style.append(('pushbutton_action', self.batch_delete_btn))

        container.setLayout(container_layout)
        main_layout.addWidget(container)

        self.setLayout(main_layout)
        self.apply_theme()
        self.refresh_history()

    def update_filter_button_style(self, btn, is_active):
        filter_id = btn.property("filter_id")
        color = btn.property("color")
        
        if not self.theme_manager:
            # 如果没有主题管理器，使用默认样式
            if is_active:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {color};
                        color: white;
                        padding: 6px 12px;
                        border: none;
                        border-radius: 4px;
                        font-size: 12px;
                        font-weight: bold;
                    }}
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #f1f5f9;
                        color: #64748b;
                        padding: 6px 12px;
                        border: none;
                        border-radius: 4px;
                        font-size: 12px;
                    }
                    QPushButton:hover {
                        background-color: #e2e8f0;
                        color: #1e293b;
                    }
                """)
            return
        
        # 使用主题颜色
        colors = self.theme_manager.get_colors()
        
        if is_active:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    color: white;
                    padding: 6px 12px;
                    border: none;
                    border-radius: 4px;
                    font-size: 12px;
                    font-weight: bold;
                }}
            """)
        else:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {colors['base']};
                    color: {colors['text_secondary']};
                    padding: 6px 12px;
                    border: 1px solid {colors['border']};
                    border-radius: 4px;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background-color: {colors['hover']};
                    color: {colors['base_text']};
                }}
            """)

    def on_filter_changed(self, filter_id):
        self.current_filter = filter_id
        for fid, btn in self.filter_buttons.items():
            btn.setChecked(fid == filter_id)
            self.update_filter_button_style(btn, fid == filter_id)
        self.refresh_history()

    def on_search_changed(self, text):
        self.search_query = text.strip()
        self.refresh_history()

    def toggle_multi_select(self):
        self.is_multi_select = self.multi_select_btn.isChecked()
        self.bottom_bar_widget.setVisible(self.is_multi_select)
        self.selected_items = []
        if hasattr(self, 'select_all_btn'):
            self.select_all_btn.setText("全选")
        self.refresh_history()

    def toggle_pin_window(self):
        # 保存当前窗口位置
        current_geometry = self.geometry()
        self.is_pinned = self.pin_btn.isChecked()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )

        self.show()
        # 恢复窗口位置
        self.setGeometry(current_geometry)
        # 聚焦搜索框
        self.focus_search_input()

    def focus_search_input(self):
        """聚焦搜索框并清空内容"""
        self.search_input.clear()
        self.search_input.setFocus()
        self.search_query = ""
        self.refresh_history()

    def refresh_history(self):
        while self.scroll_layout.count() > 1:
            item = self.scroll_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self.card_widgets = []  # 清空卡片引用列表
        # 只保留持久化的widget（搜索框、按钮等），清空临时添加的widget
        if hasattr(self, 'widgets_to_style'):
            # 筛选出仍然有效的widget
            valid_widgets = []
            for widget_type, widget in self.widgets_to_style:
                try:
                    # 检查widget是否仍然有效
                    if widget and widget.isVisible() is not None:
                        valid_widgets.append((widget_type, widget))
                except RuntimeError:
                    # widget已被删除，跳过
                    pass
            self.widgets_to_style = valid_widgets
        
        history = self.clipboard_manager.get_history(self.current_filter, self.search_query)

        # 确保选中索引在有效范围内
        if len(history) == 0:
            self.current_selected_index = 0
        elif self.current_selected_index >= len(history):
            self.current_selected_index = len(history) - 1

        # 更新全选按钮文本
        if hasattr(self, 'select_all_btn') and self.is_multi_select:
            if len(self.selected_items) == len(history) and len(history) > 0:
                self.select_all_btn.setText("取消全选")
            else:
                self.select_all_btn.setText("全选")

        if not history:
            empty_label = QLabel("暂无剪贴板历史")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if self.theme_manager:
                colors = self.theme_manager.get_colors()
                empty_label.setStyleSheet(f"color: {colors['text_secondary']}; font-size: 14px; padding: 40px;")
            else:
                empty_label.setStyleSheet("color: #94a3b8; font-size: 14px; padding: 40px;")
            self.scroll_layout.insertWidget(0, empty_label)
            return

        for index, item in enumerate(reversed(history)):
            is_selected = (index == self.current_selected_index)
            card = ClipboardCardWidget(item, index=index, is_selected=is_selected, theme_manager=self.theme_manager)
            card.clicked.connect(lambda i=item, idx=index: self.on_card_clicked(i, idx))
            card.drag_started.connect(lambda i, idx=index: self.on_card_drag_started(i, idx))
            card.favorite_toggled.connect(lambda i=item: self.toggle_item_favorite(i))
            card.pin_toggled.connect(lambda i=item: self.toggle_item_pin(i))
            card.item_deleted.connect(lambda i=item: self.delete_item(i))

            # 保存卡片引用（插入到前面，这样 card_widgets 的顺序与显示一致）
            self.card_widgets.insert(0, card)

            if self.is_multi_select:
                card.setMaximumWidth(400)
                card_layout = QHBoxLayout()
                card_layout.setContentsMargins(0, 0, 0, 0)

                checkbox = QCheckBox()
                checkbox.setChecked(item in self.selected_items)
                if self.theme_manager:
                    checkbox.setStyleSheet(self.theme_manager.get_checkbox_style())
                else:
                    checkbox.setStyleSheet("""
                        QCheckBox::indicator {
                            width: 20px;
                            height: 20px;
                            border: 2px solid #cbd5e1;
                            border-radius: 4px;
                            background-color: white;
                        }
                        QCheckBox::indicator:checked {
                            background-color: #3b82f6;
                            border-color: #3b82f6;
                        }
                    """)
                checkbox.stateChanged.connect(lambda state, i=item, cb=checkbox: self.on_item_check_changed(i, cb))

                card_layout.addWidget(checkbox)
                card_layout.addWidget(card)

                container = QWidget()
                container.setLayout(card_layout)
                container.setProperty("card_item", item)
                self.scroll_layout.insertWidget(0, container)
            else:
                card.setProperty("card_item", item)
                self.scroll_layout.insertWidget(0, card)

        # 确保选中状态正确
        self.update_selection()

    def on_card_clicked(self, item, index=None):
        if index is not None:
            self.current_selected_index = index
            self.update_selection()
        if self.is_multi_select:
            if item in self.selected_items:
                self.selected_items.remove(item)
            else:
                self.selected_items.append(item)
            self.refresh_history()
        else:
            self.paste_as_plain_text(item)

    def update_selection(self):
        """更新所有卡片的选中状态"""
        for i, card in enumerate(self.card_widgets):
            card.set_selected(i == self.current_selected_index)

    def scroll_to_selected(self):
        """滚动到当前选中项"""
        if self.card_widgets and 0 <= self.current_selected_index < len(self.card_widgets):
            card = self.card_widgets[self.current_selected_index]
            self.scroll_area.ensureWidgetVisible(card)

    def on_card_drag_started(self, item, index):
        self.drag_item = item
        self.drag_from_index = index

        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(str(index))
        drag.setMimeData(mime_data)

        for i in range(self.scroll_layout.count()):
            widget = self.scroll_layout.itemAt(i).widget()
            if widget and hasattr(widget, 'property'):
                card_item = widget.property('card_item')
                if card_item == item:
                    pixmap = QPixmap(widget.size())
                    widget.render(pixmap)
                    drag.setPixmap(pixmap)
                    break

        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        try:
            from_index = int(event.mimeData().text())
            pos = event.position() if hasattr(event, 'position') else event.pos()

            widget = self.childAt(pos.toPoint() if hasattr(pos, 'toPoint') else pos)
            target_item = None

            while widget:
                if hasattr(widget, 'property') and widget.property('card_item'):
                    target_item = widget.property('card_item')
                    break
                widget = widget.parent()

            if target_item and self.drag_item:
                # 检查拖放是否合法
                pinned_count = sum(1 for i in self.clipboard_manager.history if i.pinned)
                from_idx_orig = self.clipboard_manager.history.index(self.drag_item)
                to_idx_orig = self.clipboard_manager.history.index(target_item)

                valid_drop = True
                if self.drag_item.pinned:
                    # 置顶条目只能拖放到其他置顶条目的位置
                    if to_idx_orig >= pinned_count:
                        valid_drop = False
                else:
                    # 非置顶条目不能拖放到置顶区域
                    if to_idx_orig < pinned_count:
                        valid_drop = False

                if valid_drop:
                    history = self.clipboard_manager.get_history(self.current_filter, self.search_query)
                    history_reversed = list(reversed(history))

                    if 0 <= from_index < len(history_reversed):
                        try:
                            self.clipboard_manager.reorder_item(from_idx_orig, to_idx_orig)
                        except ValueError:
                            pass
                else:
                    # 无效拖放，忽略
                    pass

            self.drag_item = None
            self.drag_from_index = -1
            event.acceptProposedAction()
        except Exception as e:
            print(f"Drop error: {e}")
            pass

    def on_item_check_changed(self, item, checkbox):
        if checkbox.isChecked():
            if item not in self.selected_items:
                self.selected_items.append(item)
        else:
            if item in self.selected_items:
                self.selected_items.remove(item)

        # 更新全选按钮文本
        if hasattr(self, 'select_all_btn'):
            history = self.clipboard_manager.get_history(self.current_filter, self.search_query)
            if len(self.selected_items) == len(history) and len(history) > 0:
                self.select_all_btn.setText("取消全选")
            else:
                self.select_all_btn.setText("全选")

    def contextMenuEvent(self, event):
        child = self.childAt(event.pos())
        while child and not isinstance(child, ClipboardCardWidget):
            child = child.parent()

        if isinstance(child, ClipboardCardWidget):
            item = child.item
            menu = QMenu(self)

            copy_action = menu.addAction("复制")
            copy_action.triggered.connect(lambda: self.clipboard_manager.copy_item(item))

            menu.addSeparator()

            paste_plain_action = menu.addAction("无格式粘贴")
            paste_plain_action.triggered.connect(lambda: self.paste_as_plain_text(item))

            paste_format_action = menu.addAction("带格式粘贴")
            paste_format_action.triggered.connect(lambda: self.paste_with_format(item))

            menu.addSeparator()

            if item.type == ClipboardItem.TYPE_TEXT:
                edit_action = menu.addAction("编辑")
                edit_action.triggered.connect(lambda: self.edit_item_text(item))
                menu.addSeparator()
            elif item.type == ClipboardItem.TYPE_IMAGE:
                edit_action = menu.addAction("编辑")
                edit_action.triggered.connect(lambda: self.edit_item_image(item))
                menu.addSeparator()

            if item.type in [ClipboardItem.TYPE_TEXT, ClipboardItem.TYPE_IMAGE]:
                explain_action = menu.addAction("AI 解释")
                explain_action.triggered.connect(lambda: self.ai_explain(item))

                if item.type == ClipboardItem.TYPE_TEXT:
                    translate_action = menu.addAction("AI 翻译")
                    translate_action.triggered.connect(lambda: self.ai_translate(item))

                menu.addSeparator()

            fav_text = "取消收藏" if item.favorite else "收藏"
            fav_action = menu.addAction(fav_text)
            fav_action.triggered.connect(lambda: self.toggle_item_favorite(item))

            pin_text = "取消置顶" if item.pinned else "置顶"
            pin_action = menu.addAction(pin_text)
            pin_action.triggered.connect(lambda: self.toggle_item_pin(item))

            menu.addSeparator()

            if item.type == ClipboardItem.TYPE_TEXT:
                search_menu = menu.addMenu("在线搜索")
                baidu_action = search_menu.addAction("百度搜索")
                baidu_action.triggered.connect(lambda: self.search_online(item, "baidu"))
                bing_action = search_menu.addAction("必应搜索")
                bing_action.triggered.connect(lambda: self.search_online(item, "bing"))
                google_action = search_menu.addAction("Google搜索")
                google_action.triggered.connect(lambda: self.search_online(item, "google"))

                menu.addSeparator()

            delete_action = menu.addAction("删除")
            delete_action.triggered.connect(lambda: self.delete_item(item))

            menu.exec(event.globalPos())

    def paste_as_plain_text(self, item):
        self.hide()

        if item.type == ClipboardItem.TYPE_TEXT:
            self.clipboard_manager.copy_as_plain_text(item)
        else:
            self.clipboard_manager.copy_item(item)

        # 如果是固定窗口，粘贴完成后重新显示
        if self.is_pinned:
            QTimer.singleShot(200, self.show)

        self.simulate_ctrl_v()

    def paste_with_format(self, item):
        self.hide()
        self.clipboard_manager.copy_item(item)

        # 如果是固定窗口，粘贴完成后重新显示
        if self.is_pinned:
            QTimer.singleShot(200, self.show)

        self.simulate_ctrl_v()

    def simulate_ctrl_v(self):
        QTimer.singleShot(100, self._do_paste)

    def _do_paste(self):
        try:
            import ctypes
            VK_CONTROL = 0x11
            VK_V = 0x56
            KEYEVENTF_KEYUP = 0x0002

            keybd_event = ctypes.windll.user32.keybd_event
            keybd_event(VK_CONTROL, 0, 0, 0)
            keybd_event(VK_V, 0, 0, 0)
            time.sleep(0.05)
            keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
            keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
        except:
            pass

    def toggle_item_favorite(self, item):
        self.clipboard_manager.toggle_favorite(item)

    def toggle_item_pin(self, item):
        self.clipboard_manager.toggle_pin(item)

    def edit_item_text(self, item):
        if item.type != ClipboardItem.TYPE_TEXT:
            return

        dialog = TextEditDialog(item.content, self, self.theme_manager)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_text = dialog.get_text()
            if new_text:
                self.clipboard_manager.update_item_text(item, new_text)

    def edit_item_image(self, item):
        if item.type != ClipboardItem.TYPE_IMAGE:
            return

        editor = AnnotationEditor(item.content, self.theme_manager)
        editor.save_clicked.connect(lambda img: self.on_image_edited(item, img))
        editor.copy_clicked.connect(lambda img: self.on_image_edited(item, img))
        editor.show()

    def on_image_edited(self, item, image):
        if image and not image.isNull():
            self.clipboard_manager.update_item_image(item, image)

    def ai_explain(self, item):
        if item.type not in [ClipboardItem.TYPE_TEXT, ClipboardItem.TYPE_IMAGE]:
            return

        content = item.content
        content_type = "text" if item.type == ClipboardItem.TYPE_TEXT else "image"
        dialog = AIChatDialog(content, content_type, "explain", self.settings_manager, self.theme_manager, self)
        dialog.exec()

    def ai_translate(self, item):
        if item.type != ClipboardItem.TYPE_TEXT:
            return

        dialog = AIChatDialog(item.content, "text", "translate", self.settings_manager, self.theme_manager, self)
        dialog.exec()

    def delete_item(self, item):
        self.clipboard_manager.delete_item(item)

    def merge_copy_items(self):
        if self.selected_items:
            self.clipboard_manager.copy_multiple_items(self.selected_items)
            self.is_multi_select = False
            self.multi_select_btn.setChecked(False)
            self.bottom_bar_widget.setVisible(False)
            self.selected_items = []

    def merge_paste_plain_items(self):
        if self.selected_items:
            self.is_multi_select = False
            self.multi_select_btn.setChecked(False)
            self.bottom_bar_widget.setVisible(False)
            items_to_paste = self.selected_items.copy()
            self.selected_items = []

            self.hide()

            # 合并所有内容为纯文本
            text_contents = []
            for item in items_to_paste:
                if item.type == ClipboardItem.TYPE_TEXT:
                    text_contents.append(item.content)
                elif item.type == ClipboardItem.TYPE_FILE:
                    if isinstance(item.content, list):
                        text_contents.extend(item.content)
                    else:
                        text_contents.append(item.content)

            if text_contents:
                self.clipboard_manager.clipboard.setText('\n'.join(text_contents))

            # 如果是固定窗口，粘贴完成后重新显示
            if self.is_pinned:
                QTimer.singleShot(200, self.show)

            self.simulate_ctrl_v()

    def batch_favorite_items(self):
        for item in self.selected_items:
            if not item.favorite:
                self.clipboard_manager.toggle_favorite(item)
        self.selected_items = []
        self.refresh_history()

    def batch_delete_items(self):
        self.clipboard_manager.delete_multiple_items(self.selected_items)
        self.selected_items = []
        self.is_multi_select = False
        self.multi_select_btn.setChecked(False)
        self.bottom_bar_widget.setVisible(False)

    def toggle_select_all(self):
        current_history = self.clipboard_manager.get_history(self.current_filter, self.search_query)

        if len(self.selected_items) == len(current_history):
            # 如果已经全选，则取消全选
            self.selected_items = []
            self.select_all_btn.setText("全选")
        else:
            # 否则全选
            self.selected_items = current_history.copy()
            self.select_all_btn.setText("取消全选")

        self.refresh_history()

    def search_online(self, item, engine):
        if item.type != ClipboardItem.TYPE_TEXT:
            return

        query = item.content.strip()
        if not query:
            return

        urls = {
            "baidu": f"https://www.baidu.com/s?wd={query}",
            "bing": f"https://www.bing.com/search?q={query}",
            "google": f"https://www.google.com/search?q={query}"
        }

        webbrowser.open(urls.get(engine, urls["baidu"]))

    def event(self, event):
        if event.type() == event.Type.WindowDeactivate and not self.is_pinned:
            self.hide()
        return super().event(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # 检查点击是否在不可拖动的区域内
            click_pos = event.globalPosition().toPoint()

            # 检查是否点击了搜索框
            if hasattr(self, 'search_edit'):
                search_local = self.search_edit.mapFromGlobal(click_pos)
                if self.search_edit.rect().contains(search_local):
                    event.accept()
                    return

            # 检查是否点击了按钮区域
            if hasattr(self, 'top_bar_buttons'):
                buttons_local = self.top_bar_buttons.mapFromGlobal(click_pos)
                if self.top_bar_buttons.rect().contains(buttons_local):
                    event.accept()
                    return

            # 检查是否点击了滚动列表区域
            if hasattr(self, 'scroll_area'):
                scroll_local = self.scroll_area.mapFromGlobal(click_pos)
                if self.scroll_area.rect().contains(scroll_local):
                    event.accept()
                    return

            # 检查是否点击了底部多选栏
            if hasattr(self, 'bottom_bar_widget') and self.bottom_bar_widget.isVisible():
                bottom_local = self.bottom_bar_widget.mapFromGlobal(click_pos)
                if self.bottom_bar_widget.rect().contains(bottom_local):
                    event.accept()
                    return

            # 如果不在以上区域，则允许拖动窗口
            if self.windowHandle():
                self.windowHandle().startSystemMove()

            event.accept()

    def showEvent(self, event):
        try:
            # 获取鼠标当前位置
            cursor_pos = QCursor.pos()

            # 获取鼠标所在屏幕
            screen = QApplication.screenAt(cursor_pos)
            if not screen:
                screen = self.screen()

            screen_geometry = screen.availableGeometry()
            window_width = self.width()
            window_height = self.height()

            # 默认让窗口中心对准鼠标X坐标，显示在鼠标下方
            x = cursor_pos.x() - window_width // 2
            y = cursor_pos.y() + 10

            # 确保窗口不会超出屏幕右边界
            if x + window_width > screen_geometry.right():
                x = screen_geometry.right() - window_width

            # 确保窗口不会超出屏幕左边界
            if x < screen_geometry.left():
                x = screen_geometry.left()

            # 如果鼠标下方空间不够，显示在鼠标上方
            if y + window_height > screen_geometry.bottom():
                y = cursor_pos.y() - window_height - 10

            # 确保窗口不会超出屏幕上边界
            if y < screen_geometry.top():
                y = screen_geometry.top()

            self.move(x, y)
        except Exception as e:
            print(f"Show event error: {e}")

        # 清空搜索框并重置选中项
        self.search_input.clear()
        self.search_query = ""
        self.current_selected_index = 0
        self.refresh_history()
        # 确保选中状态被更新并滚动到选中项
        QTimer.singleShot(50, lambda: self.ensure_selection_visible())

        super().showEvent(event)

    def ensure_selection_visible(self):
        """确保选中项可见并正确显示选中状态"""
        self.update_selection()
        self.scroll_to_selected()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        elif event.key() == Qt.Key.Key_Down:
            self.navigate_down()
        elif event.key() == Qt.Key.Key_Up:
            self.navigate_up()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.enter_pressed()
        else:
            super().keyPressEvent(event)

    def apply_theme(self):
        colors = self.theme_manager.get_colors()
        
        # 应用容器样式
        try:
            self.container.setStyleSheet(f"""
                QWidget#clipboard_container {{
                    background-color: {colors['window']};
                    border-radius: 12px;
                    border: 2px solid {colors['highlight']};
                }}
            """)
        except RuntimeError:
            pass
        
        # 应用滚动条样式
        try:
            self.scroll_area.setStyleSheet(f"""
                QScrollArea {{
                    background-color: transparent;
                    border: none;
                }}
                QScrollBar:vertical {{
                    width: 8px;
                    background-color: {colors['base']};
                    border-radius: 4px;
                }}
                QScrollBar::handle:vertical {{
                    background-color: {colors['border']};
                    border-radius: 4px;
                }}
                QScrollBar::handle:vertical:hover {{
                    background-color: {colors['hover']};
                }}
            """)
        except RuntimeError:
            pass
        
        # 应用其他控件样式
        valid_widgets = []
        for widget_type, widget in self.widgets_to_style:
            try:
                if widget_type == 'lineedit':
                    widget.setStyleSheet(self.theme_manager.get_line_edit_style())
                    valid_widgets.append((widget_type, widget))
                elif widget_type == 'checkbox':
                    widget.setStyleSheet(self.theme_manager.get_checkbox_style())
                    valid_widgets.append((widget_type, widget))
                elif widget_type == 'pushbutton_default':
                    widget.setStyleSheet(self.theme_manager.get_push_button_style('default'))
                    valid_widgets.append((widget_type, widget))
                elif widget_type == 'pushbutton_danger':
                    widget.setStyleSheet(self.theme_manager.get_push_button_style('danger'))
                    valid_widgets.append((widget_type, widget))
                elif widget_type == 'pushbutton_icon':
                    widget.setStyleSheet(self.theme_manager.get_push_button_style('icon'))
                    valid_widgets.append((widget_type, widget))
                elif widget_type == 'filter_button':
                    is_active = widget.isChecked()
                    self.update_filter_button_style(widget, is_active)
                    valid_widgets.append((widget_type, widget))
                elif widget_type == 'pushbutton_action':
                    # 更新动作按钮样式
                    btn_text = widget.text()
                    if '全选' in btn_text or '取消全选' in btn_text:
                        widget.setStyleSheet(f"""
                            QPushButton {{
                                background-color: #6366f1;
                                color: white;
                                padding: 8px 16px;
                                border: none;
                                border-radius: 6px;
                                font-size: 13px;
                                font-weight: bold;
                            }}
                            QPushButton:hover {{
                                background-color: #4f46e5;
                            }}
                        """)
                    elif '复制合并' in btn_text:
                        widget.setStyleSheet(f"""
                            QPushButton {{
                                background-color: #3b82f6;
                                color: white;
                                padding: 8px 16px;
                                border: none;
                                border-radius: 6px;
                                font-size: 13px;
                                font-weight: bold;
                            }}
                            QPushButton:hover {{
                                background-color: #2563eb;
                            }}
                        """)
                    elif '合并粘贴' in btn_text:
                        widget.setStyleSheet(f"""
                            QPushButton {{
                                background-color: #10b981;
                                color: white;
                                padding: 8px 16px;
                                border: none;
                                border-radius: 6px;
                                font-size: 13px;
                                font-weight: bold;
                            }}
                            QPushButton:hover {{
                                background-color: #059669;
                            }}
                        """)
                    elif '批量收藏' in btn_text:
                        widget.setStyleSheet(f"""
                            QPushButton {{
                                background-color: #f59e0b;
                                color: white;
                                padding: 8px 16px;
                                border: none;
                                border-radius: 6px;
                                font-size: 13px;
                                font-weight: bold;
                            }}
                            QPushButton:hover {{
                                background-color: #d97706;
                            }}
                        """)
                    elif '批量删除' in btn_text:
                        widget.setStyleSheet(f"""
                            QPushButton {{
                                background-color: #ef4444;
                                color: white;
                                padding: 8px 16px;
                                border: none;
                                border-radius: 6px;
                                font-size: 13px;
                                font-weight: bold;
                            }}
                            QPushButton:hover {{
                                background-color: #dc2626;
                            }}
                        """)
                    valid_widgets.append((widget_type, widget))
                elif widget_type == 'label':
                    widget.setStyleSheet(f"color: {colors['text_secondary']}; font-size: 14px; padding: 40px;")
                    valid_widgets.append((widget_type, widget))
            except RuntimeError:
                # widget已被删除，跳过
                pass
        
        # 更新有效的widget列表
        self.widgets_to_style = valid_widgets
        
        # 更新现有卡片
        for card in self.card_widgets:
            try:
                if hasattr(card, 'apply_theme'):
                    card.apply_theme()
                if hasattr(card, 'update'):
                    card.update()
            except RuntimeError:
                pass

    def navigate_down(self):
        if not self.card_widgets:
            return
        self.current_selected_index = (self.current_selected_index + 1) % len(self.card_widgets)
        self.update_selection()
        self.scroll_to_selected()

    def navigate_up(self):
        if not self.card_widgets:
            return
        self.current_selected_index = (self.current_selected_index - 1) % len(self.card_widgets)
        self.update_selection()
        self.scroll_to_selected()

    def enter_pressed(self):
        if not self.card_widgets or self.is_multi_select:
            return
        # 直接从当前选中的卡片中获取项目
        if 0 <= self.current_selected_index < len(self.card_widgets):
            card = self.card_widgets[self.current_selected_index]
            item = card.item
            self.paste_as_plain_text(item)

