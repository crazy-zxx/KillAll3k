import os
import sqlite3
import base64
import json
import sys
from datetime import datetime
from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QBuffer, QByteArray, QIODevice, QUrl
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QMimeData


class ClipboardItem:
    TYPE_TEXT = 'text'
    TYPE_IMAGE = 'image'
    TYPE_FILE = 'file'

    def __init__(self, item_type, content, timestamp=None, mime_data=None, item_id=None):
        self.id = item_id or self._generate_id()
        self.type = item_type
        self.content = content
        self.mime_data = mime_data
        self.timestamp = timestamp or datetime.now()
        self.favorite = False
        self.pinned = False

    def _generate_id(self):
        return int(datetime.now().timestamp() * 1000000)

    def to_dict(self):
        content_encoded = self._encode_content()
        mime_encoded = self._encode_mime_data()
        return {
            'id': self.id,
            'type': self.type,
            'content': content_encoded,
            'mime_data': mime_encoded,
            'timestamp': self.timestamp.isoformat(),
            'favorite': self.favorite,
            'pinned': self.pinned
        }

    @classmethod
    def from_dict(cls, data):
        item = cls(
            data['type'], 
            cls._decode_content(data['type'], data['content']), 
            datetime.fromisoformat(data['timestamp']),
            cls._decode_mime_data(data.get('mime_data')),
            data.get('id')
        )
        item.favorite = data.get('favorite', False)
        item.pinned = data.get('pinned', False)
        return item

    def _encode_content(self):
        if self.type == self.TYPE_IMAGE:
            buffer = QImage()
            if isinstance(self.content, QImage):
                buffer = self.content
            elif isinstance(self.content, QPixmap):
                buffer = self.content.toImage()
            byte_array = QByteArray()
            qbuffer = QBuffer(byte_array)
            qbuffer.open(QIODevice.OpenModeFlag.WriteOnly)
            buffer.save(qbuffer, 'PNG')
            qbuffer.close()
            return base64.b64encode(byte_array.data()).decode('utf-8')
        elif self.type == self.TYPE_FILE:
            if isinstance(self.content, list):
                return '\n'.join(self.content)
            return self.content
        return self.content

    @classmethod
    def _decode_content(cls, item_type, encoded_content):
        if item_type == cls.TYPE_IMAGE:
            data = base64.b64decode(encoded_content)
            img = QImage.fromData(data)
            return img
        elif item_type == cls.TYPE_FILE:
            if '\n' in encoded_content:
                return encoded_content.split('\n')
            return encoded_content
        return encoded_content

    def _encode_mime_data(self):
        if not self.mime_data:
            return None
        mime_dict = {}
        formats = self.mime_data.formats()
        for fmt in formats:
            data = self.mime_data.data(fmt)
            mime_dict[fmt] = base64.b64encode(data.data()).decode('utf-8')
        return mime_dict

    @classmethod
    def _decode_mime_data(cls, encoded_mime):
        if not encoded_mime:
            return None

        mime_data = QMimeData()
        for fmt, encoded_data in encoded_mime.items():
            data = QByteArray(base64.b64decode(encoded_data))
            mime_data.setData(fmt, data)
        return mime_data

    def get_preview(self, max_length=100):
        if self.type == self.TYPE_TEXT:
            text = self.content.strip()
            if len(text) > max_length:
                return text[:max_length] + '...'
            return text
        elif self.type == self.TYPE_IMAGE:
            return '[图片]'
        elif self.type == self.TYPE_FILE:
            if isinstance(self.content, list):
                return f'[文件] {len(self.content)} 个文件'
            return f'[文件] {os.path.basename(self.content)}'
        return ''


class ClipboardManager(QObject):
    clipboard_changed = pyqtSignal(object)
    history_updated = pyqtSignal()

    def __init__(self, settings_manager):
        super().__init__()
        self.settings_manager = settings_manager
        self.clipboard = QApplication.clipboard()
        self.history = []
        self.last_content = None
        self.db_file = self.resource_path('clipboard_history.db')
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_clipboard)
        self._suppress_monitoring = False

        self._init_database()
        self.load_history()
        # 根据设置决定是否启动监控
        if self.settings_manager.get('clipboard_enabled', True):
            self.start_monitoring()

    def resource_path(self, relative_path):
        """获取打包后资源文件的绝对路径"""
        if hasattr(sys, '_MEIPASS'):
            # 如果是打包后的环境
            base_path = sys._MEIPASS
        else:
            # 开发环境，直接使用当前路径
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    def _deep_copy_mime_data(self, mime_data):

        if not mime_data:
            return None
        new_mime = QMimeData()
        formats = mime_data.formats()
        for fmt in formats:
            data = mime_data.data(fmt)
            new_mime.setData(fmt, QByteArray(data))
        return new_mime

    def _init_database(self):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clipboard_history 
            (id INTEGER PRIMARY KEY,
             type TEXT NOT NULL,
             content TEXT NOT NULL,
             mime_data TEXT,
             timestamp TEXT NOT NULL,
             favorite INTEGER DEFAULT 0,
             pinned INTEGER DEFAULT 0)
        ''')
        
        conn.commit()
        conn.close()

    def start_monitoring(self):
        self.timer.start(500)

    def stop_monitoring(self):
        self.timer.stop()
    
    def update_monitoring_state(self):
        """根据设置动态更新监控状态"""
        enabled = self.settings_manager.get('clipboard_enabled', True)
        if enabled and not self.timer.isActive():
            self.start_monitoring()
        elif not enabled and self.timer.isActive():
            self.stop_monitoring()

    def check_clipboard(self):
        if self._suppress_monitoring or not self.settings_manager.get('clipboard_enabled', True):
            return
        current_content = self._get_clipboard_content()
        if current_content and current_content != self.last_content:
            self.last_content = current_content
            self.add_to_history(current_content)

    def _get_clipboard_content(self):
        mime_data = self.clipboard.mimeData()
        copied_mime = self._deep_copy_mime_data(mime_data)

        if mime_data.hasUrls():
            urls = mime_data.urls()
            files = []
            for url in urls:
                if url.isLocalFile():
                    files.append(url.toLocalFile())
            if files:
                return {'type': ClipboardItem.TYPE_FILE, 'content': files, 'mime_data': copied_mime}

        if mime_data.hasImage():
            image = self.clipboard.image()
            if not image.isNull():
                return {'type': ClipboardItem.TYPE_IMAGE, 'content': image, 'mime_data': copied_mime}

        if mime_data.hasText():
            text = mime_data.text()
            if text.strip():
                return {'type': ClipboardItem.TYPE_TEXT, 'content': text, 'mime_data': copied_mime}

        return None

    def add_to_history(self, content_dict):
        item = ClipboardItem(
            content_dict['type'], 
            content_dict['content'],
            mime_data=content_dict.get('mime_data')
        )
        
        if not self._is_duplicate(item):
            # 找到第一个非置顶条目的位置，在它前面插入
            insert_pos = 0
            for i, existing_item in enumerate(self.history):
                if not existing_item.pinned:
                    insert_pos = i
                    break
            else:
                insert_pos = len(self.history)
            
            self.history.insert(insert_pos, item)
            self._save_item_to_db(item)
            self._enforce_limit()
            self.history_updated.emit()

    def _is_duplicate(self, new_item):
        for item in self.history[:20]:
            if item.type == new_item.type:
                if item.type == ClipboardItem.TYPE_TEXT:
                    if item.content == new_item.content:
                        return True
                elif item.type == ClipboardItem.TYPE_FILE:
                    content1 = item.content if isinstance(item.content, list) else [item.content]
                    content2 = new_item.content if isinstance(new_item.content, list) else [new_item.content]
                    if sorted(content1) == sorted(content2):
                        return True
                elif item.type == ClipboardItem.TYPE_IMAGE:
                    img1 = item.content
                    img2 = new_item.content
                    if img1.width() == img2.width() and img1.height() == img2.height():
                        return True
        return False

    def _enforce_limit(self):
        limit = self.settings_manager.get('clipboard_history_limit', 0)
        if limit > 0:
            pinned_items = [item for item in self.history if item.pinned]
            other_items = [item for item in self.history if not item.pinned]
            
            kept_others = other_items[:max(0, limit - len(pinned_items))]
            self.history = pinned_items + kept_others
            
            self._save_all_to_db()

    def get_history(self, filter_type=None, search_query=None):
        items = self.history.copy()

        if filter_type == 'favorite':
            items = [item for item in items if item.favorite]
        elif filter_type in ['text', 'image', 'file']:
            items = [item for item in items if item.type == filter_type]

        if search_query:
            query = search_query.lower()
            filtered = []
            for item in items:
                if item.type == ClipboardItem.TYPE_TEXT:
                    if query in item.content.lower():
                        filtered.append(item)
                elif item.type == ClipboardItem.TYPE_FILE:
                    if isinstance(item.content, list):
                        for f in item.content:
                            if query in os.path.basename(f).lower():
                                filtered.append(item)
                                break
                    else:
                        if query in os.path.basename(item.content).lower():
                            filtered.append(item)
            items = filtered

        return items

    def copy_item(self, item):
        try:
            # 对于图像，直接使用 fallback 更可靠
            if item.type == ClipboardItem.TYPE_IMAGE:
                self._fallback_copy(item)
            elif item.mime_data:
                try:
                    copied_mime = self._deep_copy_mime_data(item.mime_data)
                    if copied_mime:
                        self.clipboard.setMimeData(copied_mime)
                    else:
                        self._fallback_copy(item)
                except Exception:
                    self._fallback_copy(item)
            else:
                self._fallback_copy(item)
        except Exception:
            self._fallback_copy(item)
    
    def _fallback_copy(self, item):
        if item.type == ClipboardItem.TYPE_TEXT:
            self.clipboard.setText(item.content)
        elif item.type == ClipboardItem.TYPE_IMAGE:
            self.clipboard.setImage(item.content)
        elif item.type == ClipboardItem.TYPE_FILE:
            urls = []
            if isinstance(item.content, list):
                urls = [QUrl.fromLocalFile(f) for f in item.content]
            else:
                urls = [QUrl.fromLocalFile(item.content)]

            mime_data = QMimeData()
            mime_data.setUrls(urls)
            self.clipboard.setMimeData(mime_data)


    def copy_as_plain_text(self, item):
        if item.type == ClipboardItem.TYPE_TEXT:
            self.clipboard.setText(item.content)

    def copy_multiple_items(self, items):
        text_contents = []
        for item in items:
            if item.type == ClipboardItem.TYPE_TEXT:
                text_contents.append(item.content)
            elif item.type == ClipboardItem.TYPE_FILE:
                if isinstance(item.content, list):
                    text_contents.extend(item.content)
                else:
                    text_contents.append(item.content)
        if text_contents:
            self.clipboard.setText('\n'.join(text_contents))

    def delete_item(self, item):
        if item in self.history:
            self._suppress_monitoring = True
            try:
                self.history.remove(item)
                self._delete_item_from_db(item)
                self.history_updated.emit()
                self.clipboard.clear()
            except Exception as e:
                print(f"删除条目失败: {e}")
            finally:
                self._suppress_monitoring = False

    def delete_multiple_items(self, items):
        if not items:
            return
        
        self._suppress_monitoring = True
        try:
            for item in items:
                if item in self.history:
                    self.history.remove(item)
                    self._delete_item_from_db(item)
            self.history_updated.emit()
            self.clipboard.clear()
        except Exception as e:
            print(f"批量删除条目失败: {e}")
        finally:
            self._suppress_monitoring = False

    def toggle_favorite(self, item):
        item.favorite = not item.favorite
        self._update_item_in_db(item)
        self.history_updated.emit()

    def toggle_pin(self, item):
        item.pinned = not item.pinned
        if item in self.history:
            self.history.remove(item)
        
        if item.pinned:
            # 置顶时插入到最前面
            self.history.insert(0, item)
        else:
            # 取消置顶时插入到所有置顶条目的后面
            pinned_count = sum(1 for i in self.history if i.pinned)
            self.history.insert(pinned_count, item)
        
        self._update_item_in_db(item)
        self.history_updated.emit()

    def reorder_item(self, from_index, to_index):
        if 0 <= from_index < len(self.history) and 0 <= to_index < len(self.history):
            item = self.history[from_index]
            target_item = self.history[to_index]
            
            # 检查拖放是否合法
            if item.pinned:
                # 置顶条目只能拖放到其他置顶条目的位置
                # 找到所有置顶条目的索引范围
                pinned_count = sum(1 for i in self.history if i.pinned)
                if to_index >= pinned_count:
                    # 不能拖放到非置顶区域
                    return
            else:
                # 非置顶条目不能拖放到置顶区域
                pinned_count = sum(1 for i in self.history if i.pinned)
                if to_index < pinned_count:
                    # 不能拖放到置顶区域
                    return
            
            # 执行排序
            item = self.history.pop(from_index)
            self.history.insert(to_index, item)
            self._save_all_to_db()
            self.history_updated.emit()

    def clear_history(self):
        self.history = [item for item in self.history if item.pinned or item.favorite]
        self._save_all_to_db()
        self.history_updated.emit()
        self.clipboard.clear()

    def update_item_text(self, item, new_text):
        if item.type != ClipboardItem.TYPE_TEXT:
            return
        
        self._suppress_monitoring = True
        try:
            item.content = new_text
            item.mime_data = None
            self._save_item_to_db(item)
            self.history_updated.emit()
            self.clipboard.clear()
        except Exception as e:
            print(f"更新条目失败: {e}")
        finally:
            self._suppress_monitoring = False

    def update_item_image(self, item, new_image):
        if item.type != ClipboardItem.TYPE_IMAGE:
            return
        
        self._suppress_monitoring = True
        try:
            item.content = new_image
            item.mime_data = None
            self._save_item_to_db(item)
            self.history_updated.emit()
            self.clipboard.clear()
        except Exception as e:
            print(f"更新图像失败: {e}")
        finally:
            self._suppress_monitoring = False

    def _save_item_to_db(self, item):
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            content_encoded = item._encode_content()
            mime_encoded = item._encode_mime_data()
            
            cursor.execute('''
                INSERT OR REPLACE INTO clipboard_history 
                (id, type, content, mime_data, timestamp, favorite, pinned)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                item.id,
                item.type,
                content_encoded,
                json.dumps(mime_encoded) if mime_encoded else None,
                item.timestamp.isoformat(),
                1 if item.favorite else 0,
                1 if item.pinned else 0
            ))
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"保存项目到数据库失败: {e}")

    def _update_item_in_db(self, item):
        self._save_item_to_db(item)

    def _delete_item_from_db(self, item):
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM clipboard_history WHERE id = ?', (item.id,))
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"从数据库删除项目失败: {e}")

    def _save_all_to_db(self):
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM clipboard_history')
            
            for item in self.history:
                content_encoded = item._encode_content()
                mime_encoded = item._encode_mime_data()
                
                cursor.execute('''
                    INSERT INTO clipboard_history 
                    (id, type, content, mime_data, timestamp, favorite, pinned)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    item.id,
                    item.type,
                    content_encoded,
                    json.dumps(mime_encoded) if mime_encoded else None,
                    item.timestamp.isoformat(),
                    1 if item.favorite else 0,
                    1 if item.pinned else 0
                ))
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"保存所有项目到数据库失败: {e}")

    def save_history(self):
        self._save_all_to_db()

    def load_history(self):
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM clipboard_history ORDER BY timestamp DESC')
            rows = cursor.fetchall()
            
            self.history = []
            for row in rows:
                item_id, item_type, content, mime_data_str, timestamp_str, favorite, pinned = row
                

                mime_dict = None
                if mime_data_str:
                    try:
                        mime_dict = json.loads(mime_data_str)
                    except:
                        pass
                
                data = {
                    'id': item_id,
                    'type': item_type,
                    'content': content,
                    'mime_data': mime_dict,
                    'timestamp': timestamp_str,
                    'favorite': bool(favorite),
                    'pinned': bool(pinned)
                }
                
                item = ClipboardItem.from_dict(data)
                self.history.append(item)
            
            # 将置顶条目排在前面，保持它们的相对顺序
            pinned_items = [item for item in self.history if item.pinned]
            other_items = [item for item in self.history if not item.pinned]
            self.history = pinned_items + other_items
            
            conn.close()
        except Exception as e:
            print(f"从数据库加载剪贴板历史失败: {e}")
            self.history = []

