import ctypes
import json
import math
import os
import sys
import time
from ctypes import wintypes
from datetime import datetime
from io import BytesIO

import numpy as np
import requests
import win32gui
from PIL import Image
from PyQt6.QtCore import QBuffer
from PyQt6.QtCore import (
    Qt, QRect, QPoint, QPointF, pyqtSignal, QRectF, QThread
)
from PyQt6.QtGui import QAction, QFontMetrics
from PyQt6.QtGui import QCursor
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QBrush, QPixmap, QImage,
    QFont, QPolygonF, QPainterPath,
)
from PyQt6.QtWidgets import QMenu, QSlider, QWidgetAction
from PyQt6.QtWidgets import (
    QWidget, QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QToolBar, QColorDialog, QSpinBox, QComboBox, QTextEdit, QLineEdit, QScrollArea
)


class ClickableLabel(QLabel):
    """可点击的标签"""
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class ScreenshotWindow(QWidget):
    """主截图窗口"""

    screenshot_taken = pyqtSignal(QImage)
    cancelled = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # 获取全屏尺寸
        self.screen_geometry = QApplication.primaryScreen().geometry()
        self.setGeometry(self.screen_geometry)

        # 状态
        self.is_drawing = False
        self.is_moving = False
        self.is_resizing = False
        self.resize_handle = None  # 8个调整手柄之一
        self.start_pos = QPoint()
        self.current_pos = QPoint()

        # 选区
        self.selection = QRect()
        self.previous_selection = QRect()

        # 捕获的屏幕图像
        self.screen_pixmap = None

        # 窗口识别
        self.detected_windows = []
        self.highlighted_window = None

        # 8个调整手柄的位置
        self.handles = []

        # 调整手柄的大小
        self.handle_size = 10

        self.init_ui()
        self.capture_screen()
        self.setFocus()
        self.activateWindow()

    def init_ui(self):
        """初始化UI"""
        pass  # 绘制在paintEvent中完成

    def showEvent(self, event):
        """窗口显示时确保获得焦点"""
        super().showEvent(event)
        self.setFocus()
        self.activateWindow()

    def capture_screen(self):
        """捕获屏幕"""
        screen = QApplication.primaryScreen()
        self.screen_pixmap = screen.grabWindow(0)
        self.dpi_scale = self.get_dpi_scale()

        # 检测窗口
        self.detect_windows()

        self.update()

    def get_dpi_scale(self):
        """获取准确的 DPI 缩放比例"""
        try:

            # 尝试使用 Windows API 获取 DPI
            user32 = ctypes.windll.user32
            user32.SetProcessDPIAware()

            hdc = user32.GetDC(0)
            LOGPIXELSX = 88
            LOGPIXELSY = 90

            dpi_x = ctypes.windll.gdi32.GetDeviceCaps(hdc, LOGPIXELSX)
            dpi_y = ctypes.windll.gdi32.GetDeviceCaps(hdc, LOGPIXELSY)

            user32.ReleaseDC(0, hdc)

            # 使用较高的 DPI 值（考虑 x 和 y）
            dpi = max(dpi_x, dpi_y)
            return dpi / 96.0
        except Exception:
            # 如果 Windows API 调用失败，回退到 Qt 的方法
            screen = QApplication.primaryScreen()
            return screen.devicePixelRatio()

    def detect_windows(self):
        """检测所有可见窗口"""
        self.detected_windows = []

        dpi_scale = self.dpi_scale

        def callback(hwnd, extra):
            if win32gui.IsWindowVisible(hwnd):
                try:
                    # 尝试使用 DwmGetWindowAttribute 获取更准确的窗口边界（排除阴影）
                    dwmapi = ctypes.windll.dwmapi
                    DWMWA_EXTENDED_FRAME_BOUNDS = 9

                    rect = wintypes.RECT()
                    hr = dwmapi.DwmGetWindowAttribute(
                        hwnd, DWMWA_EXTENDED_FRAME_BOUNDS,
                        ctypes.byref(rect), ctypes.sizeof(rect)
                    )

                    if hr == 0:
                        left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
                    else:
                        # 如果 DwmGetWindowAttribute 失败，回退到 GetWindowRect
                        rect = win32gui.GetWindowRect(hwnd)
                        left, top, right, bottom = rect[0], rect[1], rect[2], rect[3]
                except Exception:
                    # 如果导入或调用失败，回退到 GetWindowRect
                    rect = win32gui.GetWindowRect(hwnd)
                    left, top, right, bottom = rect[0], rect[1], rect[2], rect[3]

                # 将物理像素转换为逻辑像素（使用更精确的计算）
                x = round(left / dpi_scale)
                y = round(top / dpi_scale)
                w = round((right - left) / dpi_scale)
                h = round((bottom - top) / dpi_scale)

                if w > 10 and h > 10:
                    self.detected_windows.append({
                        'hwnd': hwnd,
                        'title': win32gui.GetWindowText(hwnd),
                        'rect': QRect(x, y, w, h)
                    })
            return True

        win32gui.EnumWindows(callback, None)

    def get_window_at_pos(self, pos):
        """获取鼠标位置下的窗口"""
        if not self.detected_windows:
            return None

        # 优先选择小窗口（更精确）
        matching = []
        for win in self.detected_windows:
            if win['rect'].contains(pos):
                matching.append(win)

        if matching:
            # 按面积排序，选择最小的
            matching.sort(key=lambda x: x['rect'].width() * x['rect'].height())
            return matching[0]
        return None

    def get_resize_handle_at_pos(self, pos):
        """获取鼠标位置下的调整手柄"""
        for i, handle in enumerate(self.handles):
            if handle.contains(pos):
                return i
        return None

    def update_handles(self):
        """更新调整手柄位置"""
        if self.selection.isValid():
            s = self.handle_size
            x, y, w, h = self.selection.x(), self.selection.y(), self.selection.width(), self.selection.height()
            self.handles = [
                QRect(x - s // 2, y - s // 2, s, s),  # 左上
                QRect(x + w // 2 - s // 2, y - s // 2, s, s),  # 上中
                QRect(x + w - s // 2, y - s // 2, s, s),  # 右上
                QRect(x + w - s // 2, y + h // 2 - s // 2, s, s),  # 右中
                QRect(x + w - s // 2, y + h - s // 2, s, s),  # 右下
                QRect(x + w // 2 - s // 2, y + h - s // 2, s, s),  # 下中
                QRect(x - s // 2, y + h - s // 2, s, s),  # 左下
                QRect(x - s // 2, y + h // 2 - s // 2, s, s),  # 左中
            ]
        else:
            self.handles = []

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()

            # 检查是否点击调整手柄
            handle_idx = self.get_resize_handle_at_pos(pos)
            if handle_idx is not None and self.selection.isValid():
                self.is_resizing = True
                self.resize_handle = handle_idx
                self.start_pos = pos
                self.previous_selection = QRect(self.selection)
                return

            # 检查是否点击选区内部（移动）
            if self.selection.isValid() and self.selection.contains(pos):
                self.is_moving = True
                self.start_pos = pos
                return

            # 开始新选区
            self.is_drawing = True
            self.start_pos = pos
            self.current_pos = pos
            self.selection = QRect()

            # 窗口识别始终开启
            window = self.get_window_at_pos(pos)
            if window:
                self.highlighted_window = window
                self.selection = window['rect']
            self.update()

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()

        # 更新光标
        self.update_cursor(pos)

        if self.is_drawing:
            self.current_pos = pos
            # 绘制矩形选区
            self.selection = QRect(self.start_pos, self.current_pos).normalized()
            self.highlighted_window = None
            self.update()
        elif self.is_moving:
            # 移动选区
            dx = pos.x() - self.start_pos.x()
            dy = pos.y() - self.start_pos.y()
            self.selection.translate(dx, dy)
            self.start_pos = pos
            self.update()
        elif self.is_resizing:
            # 调整选区大小
            self.resize_selection(pos)
            self.update()
        else:
            # 窗口检测始终开启
            if not self.selection.isValid():
                window = self.get_window_at_pos(pos)
                self.highlighted_window = window
                self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.is_drawing:
                self.is_drawing = False
                if not self.selection.isValid():
                    # 如果没有有效选区，检查是否有高亮窗口
                    if self.highlighted_window:
                        self.selection = self.highlighted_window['rect']
            elif self.is_moving:
                self.is_moving = False
            elif self.is_resizing:
                self.is_resizing = False
                self.resize_handle = None

            self.update_handles()
            self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            self.close()
        elif event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self.confirm_screenshot()

    def update_cursor(self, pos):
        """更新光标形状"""
        if not self.selection.isValid():
            self.setCursor(Qt.CursorShape.CrossCursor)
            return

        handle_idx = self.get_resize_handle_at_pos(pos)
        if handle_idx is not None:
            # 根据手柄位置设置光标
            cursors = [
                Qt.CursorShape.SizeFDiagCursor,  # 左上
                Qt.CursorShape.SizeVerCursor,  # 上中
                Qt.CursorShape.SizeBDiagCursor,  # 右上
                Qt.CursorShape.SizeHorCursor,  # 右中
                Qt.CursorShape.SizeFDiagCursor,  # 右下
                Qt.CursorShape.SizeVerCursor,  # 下中
                Qt.CursorShape.SizeBDiagCursor,  # 左下
                Qt.CursorShape.SizeHorCursor,  # 左中
            ]
            self.setCursor(cursors[handle_idx])
        elif self.selection.contains(pos):
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)

    def resize_selection(self, pos):
        """根据手柄调整选区"""
        dx = pos.x() - self.start_pos.x()
        dy = pos.y() - self.start_pos.y()
        x, y, w, h = self.previous_selection.getRect()

        # 根据不同手柄调整
        if self.resize_handle == 0:  # 左上
            new_x = x + dx
            new_y = y + dy
            new_w = w - dx
            new_h = h - dy
            if new_w > 10 and new_h > 10:
                self.selection.setRect(new_x, new_y, new_w, new_h)
        elif self.resize_handle == 1:  # 上中
            new_y = y + dy
            new_h = h - dy
            if new_h > 10:
                self.selection.setY(new_y)
                self.selection.setHeight(new_h)
        elif self.resize_handle == 2:  # 右上
            new_y = y + dy
            new_w = w + dx
            new_h = h - dy
            if new_w > 10 and new_h > 10:
                self.selection.setY(new_y)
                self.selection.setWidth(new_w)
                self.selection.setHeight(new_h)
        elif self.resize_handle == 3:  # 右中
            new_w = w + dx
            if new_w > 10:
                self.selection.setWidth(new_w)
        elif self.resize_handle == 4:  # 右下
            new_w = w + dx
            new_h = h + dy
            if new_w > 10 and new_h > 10:
                self.selection.setWidth(new_w)
                self.selection.setHeight(new_h)
        elif self.resize_handle == 5:  # 下中
            new_h = h + dy
            if new_h > 10:
                self.selection.setHeight(new_h)
        elif self.resize_handle == 6:  # 左下
            new_x = x + dx
            new_w = w - dx
            new_h = h + dy
            if new_w > 10 and new_h > 10:
                self.selection.setX(new_x)
                self.selection.setWidth(new_w)
                self.selection.setHeight(new_h)
        elif self.resize_handle == 7:  # 左中
            new_x = x + dx
            new_w = w - dx
            if new_w > 10:
                self.selection.setX(new_x)
                self.selection.setWidth(new_w)

    def confirm_screenshot(self):
        """确认截图"""
        if self.selection.isValid() and self.screen_pixmap:
            # 将逻辑像素选区转换为物理像素选区（使用四舍五入提高精度）
            physical_rect = QRect(
                round(self.selection.x() * self.dpi_scale),
                round(self.selection.y() * self.dpi_scale),
                round(self.selection.width() * self.dpi_scale),
                round(self.selection.height() * self.dpi_scale)
            )
            # 裁剪选区
            screenshot = self.screen_pixmap.copy(physical_rect).toImage()
            self.screenshot_taken.emit(screenshot)
            self.close()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 绘制屏幕背景
        if self.screen_pixmap:
            painter.drawPixmap(0, 0, self.screen_pixmap)

        # 绘制半透明遮罩
        mask_color = QColor(0, 0, 0, 100)
        if self.selection.isValid():
            # 创建选区以外的区域
            path = QPainterPath()
            path.addRect(QRectF(self.rect()))
            path.addRect(QRectF(self.selection))
            painter.setBrush(QBrush(mask_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPath(path)
        elif self.highlighted_window:
            # 创建高亮窗口以外的区域（镂空遮罩）
            path = QPainterPath()
            path.addRect(QRectF(self.rect()))
            path.addRect(QRectF(self.highlighted_window['rect']))
            painter.setBrush(QBrush(mask_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPath(path)
        else:
            # 全屏遮罩
            painter.fillRect(self.rect(), mask_color)

        # 绘制高亮窗口的矩形框提示
        if self.highlighted_window and not self.selection.isValid():
            pen = QPen(QColor(59, 130, 246), 3)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.highlighted_window['rect'])

        # 绘制选区边框
        if self.selection.isValid():
            pen = QPen(QColor(59, 130, 246), 2)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.selection)

            # 绘制调整手柄
            self.update_handles()
            painter.setBrush(QBrush(QColor(59, 130, 246)))
            painter.setPen(QPen(QColor(255, 255, 255), 1))
            for handle in self.handles:
                painter.drawEllipse(QPointF(handle.center()), self.handle_size // 2, self.handle_size // 2)

            # 显示尺寸信息（考虑 DPI 缩放的真实物理像素）
            real_width = round(self.selection.width() * self.dpi_scale)
            real_height = round(self.selection.height() * self.dpi_scale)
            size_text = f"{real_width} x {real_height}"
            info_width = 120
            info_height = 28

            # 计算信息框的位置
            x = self.selection.x()
            y = self.selection.y() - info_height - 5  # 默认显示在选区上方

            # 检查是否超出顶部边界，如果是则显示在选区下方
            if y < 0:
                y = self.selection.y() + self.selection.height() + 5

            # 检查是否超出左边界
            if x < 0:
                x = 0

            # 检查是否超出右边界
            if x + info_width > self.screen_geometry.width():
                x = self.screen_geometry.width() - info_width

            info_rect = QRect(x, y, info_width, info_height)
            painter.setBrush(QBrush(QColor(0, 0, 0, 180)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(info_rect, 4, 4)

            painter.setPen(QColor(255, 255, 255))
            font = QFont("Microsoft YaHei", 10)
            painter.setFont(font)
            painter.drawText(info_rect, Qt.AlignmentFlag.AlignCenter, size_text)

        # 绘制操作提示
        self.draw_operation_tips(painter)

    def draw_operation_tips(self, painter):
        """绘制操作提示"""

        tips = "点击活动窗口自动识别 | 鼠标框选截图区域" + '\n' + "Enter键: 确认截图 | Esc键: 退出截图"

        # 计算水平居中的矩形
        text_width = 600  # 设置一个合适的宽度
        x = (self.screen_geometry.width() - text_width) // 2
        rect = QRect(x, 80, text_width, 80)
        painter.setBrush(QBrush(QColor(0, 0, 0, 150)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 6, 6)

        painter.setPen(QColor(255, 255, 255))
        font = QFont("Microsoft YaHei", 14)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, tips)


class AnnotationItem:
    """标注项基类"""
    SELECT = 'select'
    PEN = 'pen'
    LINE = 'line'
    RECT = 'rect'
    ELLIPSE = 'ellipse'
    ARROW = 'arrow'
    TEXT = 'text'
    NUMBER = 'number'
    MOSAIC = 'mosaic'

    def __init__(self, item_type):
        self.type = item_type
        self.color = QColor(255, 0, 0)
        self.line_width = 3
        self.points = []
        self.text = ''
        self.number = 0
        self.font = QFont("Microsoft YaHei", 14)
        self.opacity = 1.0
        self.is_selected = False
        # 手柄大小
        self.handle_size = 12

    def get_bounding_rect(self):
        """获取标注的边界矩形"""
        if len(self.points) >= 2:
            x_coords = [p.x() for p in self.points]
            y_coords = [p.y() for p in self.points]
            min_x, max_x = min(x_coords), max(x_coords)
            min_y, max_y = min(y_coords), max(y_coords)
            return QRect(int(min_x) - 5, int(min_y) - 5, int(max_x - min_x) + 10, int(max_y - min_y) + 10)
        elif len(self.points) == 1:
            # 对于只有一个点的情况
            size = 40
            return QRect(self.points[0].x() - size // 2, self.points[0].y() - size // 2, size, size)
        return QRect()

    def contains_point(self, point):
        """判断点是否在元素内"""
        rect = self.get_bounding_rect()
        return rect.contains(point)

    def move_by(self, dx, dy):
        """移动标注"""
        for i in range(len(self.points)):
            self.points[i] = QPoint(self.points[i].x() + dx, self.points[i].y() + dy)

    def get_handle_rect(self, handle_index):
        """获取指定索引的手柄矩形（不再使用，但保持兼容性）"""
        handles = self.get_all_handles()
        if 0 <= handle_index < len(handles):
            point = handles[handle_index]
            half = self.handle_size // 2
            return QRect(point.x() - half, point.y() - half, half * 2, half * 2)
        return QRect()

    def get_all_handles(self):
        """获取所有手柄中心点"""
        rect = self.get_bounding_rect()
        return [
            QPoint(rect.left(), rect.top()),  # 0: 左上
            QPoint(rect.center().x(), rect.top()),  # 1: 上中
            QPoint(rect.right(), rect.top()),  # 2: 右上
            QPoint(rect.right(), rect.center().y()),  # 3: 右中
            QPoint(rect.right(), rect.bottom()),  # 4: 右下
            QPoint(rect.center().x(), rect.bottom()),  # 5: 下中
            QPoint(rect.left(), rect.bottom()),  # 6: 左下
            QPoint(rect.left(), rect.center().y())  # 7: 左中
        ]

    def get_handle_at_point(self, point):
        """获取鼠标位置下的手柄索引"""
        if not self.is_selected:
            return None
        tolerance = self.handle_size
        for i, handle_point in enumerate(self.get_all_handles()):
            # 使用距离检测，更容易点击
            dx = point.x() - handle_point.x()
            dy = point.y() - handle_point.y()
            if (dx * dx + dy * dy) <= (tolerance * tolerance):
                return i
        return None

    def draw_selection(self, painter):
        """绘制选中状态和手柄"""
        if not self.is_selected:
            return
        rect = self.get_bounding_rect()

        # 绘制选择框
        pen = QPen(QColor(59, 130, 246), 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)

        # 绘制手柄
        painter.setBrush(QBrush(QColor(59, 130, 246)))
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        radius = self.handle_size // 2
        for handle_point in self.get_all_handles():
            painter.drawEllipse(QPointF(handle_point), radius, radius)

    def draw(self, painter):
        """绘制标注"""
        pass


class PenAnnotation(AnnotationItem):
    """画笔标注"""

    def __init__(self):
        super().__init__(self.PEN)

    def draw(self, painter):
        if len(self.points) < 2:
            return
        pen = QPen(self.color, self.line_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                   Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setOpacity(self.opacity)

        path = QPainterPath(QPointF(self.points[0]))
        for p in self.points[1:]:
            path.lineTo(QPointF(p))
        painter.drawPath(path)


class RectAnnotation(AnnotationItem):
    """矩形标注"""

    def __init__(self):
        super().__init__(self.RECT)

    def draw(self, painter):
        if len(self.points) < 2:
            return
        pen = QPen(self.color, self.line_width)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setOpacity(self.opacity)
        rect = QRect(self.points[0], self.points[-1]).normalized()
        painter.drawRect(rect)


class EllipseAnnotation(AnnotationItem):
    """椭圆标注"""

    def __init__(self):
        super().__init__(self.ELLIPSE)

    def draw(self, painter):
        if len(self.points) < 2:
            return
        pen = QPen(self.color, self.line_width)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setOpacity(self.opacity)
        rect = QRect(self.points[0], self.points[-1]).normalized()
        painter.drawEllipse(rect)


class LineAnnotation(AnnotationItem):
    """直线标注"""

    def __init__(self):
        super().__init__(self.LINE)

    def draw(self, painter):
        if len(self.points) < 2:
            return
        pen = QPen(self.color, self.line_width)
        painter.setPen(pen)
        painter.setOpacity(self.opacity)
        painter.drawLine(self.points[0], self.points[-1])


class ArrowAnnotation(AnnotationItem):
    """箭头标注"""

    def __init__(self):
        super().__init__(self.ARROW)

    def draw(self, painter):
        if len(self.points) < 2:
            return
        pen = QPen(self.color, self.line_width)
        painter.setPen(pen)
        painter.setBrush(QBrush(self.color))
        painter.setOpacity(self.opacity)

        p1 = self.points[0]
        p2 = self.points[-1]

        # 绘制箭身
        painter.drawLine(p1, p2)

        # 绘制箭头
        angle = math.atan2(p2.y() - p1.y(), p2.x() - p1.x())
        arrow_length = 15
        arrow_angle = math.pi / 6

        arrow_p1 = QPointF(
            p2.x() - arrow_length * math.cos(angle - arrow_angle),
            p2.y() - arrow_length * math.sin(angle - arrow_angle)
        )
        arrow_p2 = QPointF(
            p2.x() - arrow_length * math.cos(angle + arrow_angle),
            p2.y() - arrow_length * math.sin(angle + arrow_angle)
        )

        arrow = QPolygonF([QPointF(p2), arrow_p1, arrow_p2])
        painter.drawPolygon(arrow)


class TextAnnotation(AnnotationItem):
    """文字标注"""

    def __init__(self):
        super().__init__(self.TEXT)

    def get_bounding_rect(self):
        """获取文字标注的边界"""
        if len(self.points) >= 2:
            # 使用两个点定义的边界
            return QRect(self.points[0], self.points[1]).normalized()
        elif len(self.points) == 1:
            # 兼容旧的格式
            metrics = QFontMetrics(self.font)
            text_width = metrics.horizontalAdvance(self.text) if self.text else 100
            text_height = metrics.height()
            x = self.points[0].x()
            y = self.points[0].y() - text_height
            return QRect(int(x) - 10, int(y) - 10, int(text_width) + 20, int(text_height) + 20)
        return QRect()

    def contains_point(self, point):
        return self.get_bounding_rect().contains(point)

    def draw(self, painter):
        if len(self.points) < 1 or not self.text:
            return
        pen = QPen(self.color)
        painter.setPen(pen)
        painter.setFont(self.font)
        painter.setOpacity(self.opacity)

        if len(self.points) >= 2:
            # 使用边界的中心绘制文字
            rect = QRect(self.points[0], self.points[1]).normalized()
            # 垂直居中
            metrics = QFontMetrics(self.font)
            text_height = metrics.height()
            center_y = rect.center().y() + text_height // 3
            painter.drawText(QPoint(rect.left(), center_y), self.text)
        else:
            painter.drawText(self.points[0], self.text)


class NumberAnnotation(AnnotationItem):
    """序号标注"""

    def __init__(self):
        super().__init__(self.NUMBER)
        self.radius = 16

    def get_bounding_rect(self):
        """获取序号标注的边界"""
        if len(self.points) >= 2:
            # 使用两个点定义的边界
            return QRect(self.points[0], self.points[1]).normalized()
        elif len(self.points) == 1:
            # 兼容旧的格式
            x = self.points[0].x() - self.radius - 10
            y = self.points[0].y() - self.radius - 10
            return QRect(int(x), int(y), int(self.radius * 2 + 20), int(self.radius * 2 + 20))
        return QRect()

    def draw(self, painter):
        if len(self.points) < 1:
            return

        # 获取中心点
        center = QPoint()
        if len(self.points) >= 2:
            rect = QRect(self.points[0], self.points[1]).normalized()
            center = rect.center()
            # 根据边界计算半径，确保圆能完整显示
            self.radius = min(rect.width(), rect.height()) // 2 - 2
            self.radius = max(8, min(80, self.radius))
        else:
            center = self.points[0]

        # 绘制圆形背景
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self.color))
        painter.setOpacity(self.opacity)
        painter.drawEllipse(QPointF(center), self.radius, self.radius)

        # 绘制序号
        painter.setPen(QColor(255, 255, 255))
        # 根据radius调整字体大小
        font_size = max(10, int(self.radius))
        font = QFont("Microsoft YaHei", font_size, QFont.Weight.Bold)
        painter.setFont(font)
        text = str(self.number)
        rect = QRect(center.x() - self.radius, center.y() - self.radius,
                     int(self.radius * 2), int(self.radius * 2))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)


class MosaicAnnotation(AnnotationItem):
    """马赛克标注"""

    def __init__(self):
        super().__init__(self.MOSAIC)
        self.mosaic_size = 12  # 像素块大小
        self.original_image = None

    def draw(self, painter):
        if len(self.points) < 2:
            return

        rect = QRect(self.points[0], self.points[-1]).normalized()

        # 如果我们有原始图像引用，使用它来创建真正的马赛克
        if self.original_image and not self.original_image.isNull():
            # 确保矩形在图像范围内
            image_rect = self.original_image.rect()
            intersect_rect = rect.intersected(image_rect)
            if not intersect_rect.isNull():
                # 复制指定区域的图像
                mosaic_region = self.original_image.copy(intersect_rect)

                # 使用缩放方式，但是确保完全匹配
                if mosaic_region.width() > 0 and mosaic_region.height() > 0:
                    # 先缩小
                    small_w = max(1, mosaic_region.width() // self.mosaic_size)
                    small_h = max(1, mosaic_region.height() // self.mosaic_size)

                    small_img = mosaic_region.scaled(
                        small_w, small_h,
                        Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.FastTransformation
                    )

                    # 再放大
                    result_img = small_img.scaled(
                        mosaic_region.width(), mosaic_region.height(),
                        Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.FastTransformation
                    )

                    # 直接绘制到正确位置
                    painter.drawImage(intersect_rect, result_img)
                    return

        # 如果没有原始图像，使用简单填充
        painter.fillRect(rect, QColor(128, 128, 128, 255))


class AnnotationEditor(QMainWindow):
    """标注编辑器"""

    save_clicked = pyqtSignal(QImage)
    copy_clicked = pyqtSignal(QImage)
    ocr_clicked = pyqtSignal(QImage)
    ai_clicked = pyqtSignal(QImage)
    sticker_clicked = pyqtSignal(QImage)
    closed = pyqtSignal()

    def __init__(self, image, theme_manager=None):
        super().__init__()
        self.original_image = image
        self.current_image = QImage(image)
        self.annotations = []
        self.current_tool = AnnotationItem.PEN
        self.current_annotation = None
        self.is_drawing = False
        self.color = QColor(255, 0, 0)
        self.line_width = 3
        self.number_counter = 1
        self.dpi_scale = self.get_dpi_scale()
        self.theme_manager = theme_manager

        self.setWindowTitle("截图编辑")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )

        self.init_ui()
        self.apply_theme()

        self.setFixedSize(int(1700 / self.dpi_scale), int(1100 / self.dpi_scale))

    def get_dpi_scale(self):
        """获取准确的 DPI 缩放比例"""
        try:
            # 尝试使用 Windows API 获取 DPI
            user32 = ctypes.windll.user32
            user32.SetProcessDPIAware()

            hdc = user32.GetDC(0)
            LOGPIXELSX = 88
            LOGPIXELSY = 90

            dpi_x = ctypes.windll.gdi32.GetDeviceCaps(hdc, LOGPIXELSX)
            dpi_y = ctypes.windll.gdi32.GetDeviceCaps(hdc, LOGPIXELSY)

            user32.ReleaseDC(0, hdc)

            # 使用较高的 DPI 值（考虑 x 和 y）
            dpi = max(dpi_x, dpi_y)
            return dpi / 96.0
        except Exception:
            # 如果 Windows API 调用失败，回退到 Qt 的方法
            screen = QApplication.primaryScreen()
            return screen.devicePixelRatio()

    def init_ui(self):
        """初始化UI"""
        # 工具栏
        toolbar = QToolBar("工具")
        self.addToolBar(toolbar)

        # 工具按钮
        self.tool_buttons = []
        tools = [
            ("选择", AnnotationItem.SELECT),
            ("画笔", AnnotationItem.PEN),
            ("直线", AnnotationItem.LINE),
            ("矩形", AnnotationItem.RECT),
            ("椭圆", AnnotationItem.ELLIPSE),
            ("箭头", AnnotationItem.ARROW),
            ("文字", AnnotationItem.TEXT),
            ("序号", AnnotationItem.NUMBER),
            ("马赛克", AnnotationItem.MOSAIC),
        ]

        for name, tool_type in tools:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setFixedWidth(60)
            if tool_type == self.current_tool:
                btn.setChecked(True)
            btn.clicked.connect(lambda checked, t=tool_type, b=btn: self.set_tool(t, b))
            toolbar.addWidget(btn)
            self.tool_buttons.append(btn)

        tmp = QLabel('')
        tmp.setFixedWidth(20)
        toolbar.addWidget(tmp)

        # 颜色块显示（可点击）
        self.color_label = ClickableLabel()
        self.color_label.setFixedSize(24, 24)
        self.color_label.clicked.connect(self.choose_color)
        toolbar.addWidget(self.color_label)

        tmp = QLabel('')
        tmp.setFixedWidth(10)
        toolbar.addWidget(tmp)

        # 线宽
        self.line_spin = QSpinBox()
        self.line_spin.setRange(1, 100)
        self.line_spin.setValue(self.line_width)
        self.line_spin.valueChanged.connect(self.set_line_width)
        self.line_width_label = QLabel("线宽:")
        toolbar.addWidget(self.line_width_label)
        toolbar.addWidget(self.line_spin)

        tmp = QLabel('')
        tmp.setFixedWidth(20)
        toolbar.addWidget(tmp)

        # 操作按钮
        self.ocr_btn = QPushButton("OCR识别")
        self.ocr_btn.clicked.connect(self.do_ocr)
        toolbar.addWidget(self.ocr_btn)

        self.ai_btn = QPushButton("问AI")
        self.ai_btn.clicked.connect(self.do_ai)
        toolbar.addWidget(self.ai_btn)

        tmp = QLabel('')
        tmp.setFixedWidth(60)
        toolbar.addWidget(tmp)

        self.sticker_btn = QPushButton("贴图")
        self.sticker_btn.clicked.connect(self.do_sticker)
        toolbar.addWidget(self.sticker_btn)

        self.copy_btn = QPushButton("复制")
        self.copy_btn.clicked.connect(self.do_copy)
        toolbar.addWidget(self.copy_btn)

        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self.do_save)
        toolbar.addWidget(self.save_btn)

        # 滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(False)  # 保持画布固定大小

        # 先计算画布大小
        scaled_canvas_width = int(self.original_image.width() / self.dpi_scale)
        scaled_canvas_height = int(self.original_image.height() / self.dpi_scale)

        # 画布
        self.canvas = AnnotationCanvas(self)
        self.canvas.setFixedSize(scaled_canvas_width, scaled_canvas_height)

        scroll_area.setWidget(self.canvas)
        # 设置滚动区域对齐方式居中
        scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCentralWidget(scroll_area)

    def apply_theme(self):
        """应用主题"""
        if not self.theme_manager:
            return
        colors = self.theme_manager.get_colors()

        # 设置工具栏和窗口背景
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {colors['window']};
            }}
            QToolBar {{
                background-color: {colors['window']};
                border: none;
                spacing: 4px;
            }}
            QToolBar::separator {{
                background-color: {colors['border']};
                width: 1px;
                margin: 4px 8px;
            }}
        """)

        # 设置工具按钮样式
        for btn in self.tool_buttons:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {colors['base']};
                    color: {colors['base_text']};
                    border: 1px solid {colors['border']};
                    border-radius: 4px;
                    padding: 6px 12px;
                }}
                QPushButton:hover {{
                    background-color: {colors['hover']};
                    border-color: {colors['highlight']};
                }}
                QPushButton:checked {{
                    background-color: {colors['highlight']};
                    color: {colors['highlight_text']};
                    border-color: {colors['highlight']};
                }}
            """)

        # 设置颜色标签
        self.color_label.setStyleSheet(f"""
            ClickableLabel {{
                background-color: {self.color.name()};
                border: 1px solid {colors['border']};
                border-radius: 2px;
            }}
            ClickableLabel:hover {{
                border-color: {colors['highlight']};
                cursor: pointer;
            }}
        """)

        # 设置线宽标签和输入框
        self.line_width_label.setStyleSheet(f"color: {colors['window_text']};")
        self.line_spin.setStyleSheet(f"""
            QSpinBox {{
                background-color: {colors['base']};
                color: {colors['base_text']};
                border: 1px solid {colors['border']};
                border-radius: 4px;
                padding: 4px;
            }}
            QSpinBox:hover {{
                border-color: {colors['highlight']};
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                background-color: {colors['button']};
                border-left: 1px solid {colors['border']};
                width: 20px;
            }}
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
                background-color: {colors['hover']};
            }}
            QSpinBox::up-arrow {{
                border-left: 5px solid {colors['base']};
                border-right: 5px solid {colors['base']};
                border-bottom: 6px solid {colors['base_text']};
                width: 0;
                height: 0;
            }}
            QSpinBox::down-arrow {{
                border-left: 5px solid {colors['base']};
                border-right: 5px solid {colors['base']};
                border-top: 6px solid {colors['base_text']};
                width: 0;
                height: 0;
            }}
        """)

        # 设置操作按钮样式
        for btn in [self.ocr_btn, self.ai_btn, self.sticker_btn, self.copy_btn, self.save_btn]:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {colors['base']};
                    color: {colors['base_text']};
                    border: 1px solid {colors['border']};
                    border-radius: 4px;
                    padding: 6px 12px;
                }}
                QPushButton:hover {{
                    background-color: {colors['hover']};
                    border-color: {colors['highlight']};
                }}
                QPushButton:checked {{
                    background-color: {colors['highlight']};
                    color: {colors['highlight_text']};
                    border-color: {colors['highlight']};
                }}
            """)

        # 更新画布文字编辑框样式
        if hasattr(self.canvas, 'text_edit'):
            self.canvas.text_edit.setStyleSheet(f"""
                QLineEdit {{
                    background-color: {colors['base']};
                    border: 2px solid {colors['highlight']};
                    border-radius: 4px;
                    padding: 4px;
                    font-size: 14px;
                    color: {colors['base_text']};
                }}
            """)

    def set_tool(self, tool_type, button):
        """设置当前工具"""
        self.current_tool = tool_type
        # 取消其他按钮的选中状态
        for tb in self.findChildren(QPushButton):
            if tb.isCheckable():
                tb.setChecked(False)
        button.setChecked(True)

        # 如果不是选择工具，清除所有选中状态
        if tool_type != AnnotationItem.SELECT:
            for ann in self.annotations:
                ann.is_selected = False
            # 清除 canvas 中的状态
            self.canvas.selected_annotation = None
            self.canvas.is_moving = False
            self.canvas.is_resizing = False

        # 更新画布显示
        self.canvas.update()

        if tool_type == AnnotationItem.NUMBER:
            self.number_counter = self.get_next_number()

    def get_next_number(self):
        """获取下一个序号"""
        numbers = [a.number for a in self.annotations if a.type == AnnotationItem.NUMBER]
        if not numbers:
            return 1
        return max(numbers) + 1

    def choose_color(self):
        """选择颜色"""
        color = QColorDialog.getColor(self.color, self, "选择颜色")
        if color.isValid():
            self.color = color
            # 更新颜色块显示
            self.apply_theme()

    def set_line_width(self, width):
        """设置线宽"""
        self.line_width = width

    def do_ocr(self):
        """OCR识别"""
        final_image = self.get_final_image()
        self.ocr_clicked.emit(final_image)

    def do_ai(self):
        """问AI"""
        final_image = self.get_final_image()
        self.ai_clicked.emit(final_image)

    def do_sticker(self):
        """贴图"""
        final_image = self.get_final_image()
        self.sticker_clicked.emit(final_image)
        self.close()

    def do_copy(self):
        """复制到剪贴板"""
        final_image = self.get_final_image()
        self.copy_clicked.emit(final_image)
        self.close()

    def do_save(self):
        """保存到文件"""
        final_image = self.get_final_image()
        self.save_clicked.emit(final_image)

    def get_final_image(self):
        """获取最终图像（包含所有标注）"""
        image = QImage(self.original_image)
        painter = QPainter(image)
        for ann in self.annotations:
            ann.draw(painter)
        painter.end()
        return image

    def add_annotation(self, annotation):
        """添加标注"""
        self.annotations.append(annotation)
        self.canvas.update()

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)


class AnnotationCanvas(QWidget):
    """标注画布"""

    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self.setMouseTracking(True)
        self.is_moving = False
        self.is_resizing = False
        self.resize_handle = None
        self.selected_annotation = None
        self.drag_start_pos = QPoint()
        self.original_points = []

        # 内联文字编辑框
        self.text_edit = QLineEdit(self)
        self.text_edit.setStyleSheet("""
            QLineEdit {
                background-color: rgba(255,255,255,0);
                border: 2px solid #3b82f6;
                border-radius: 4px;
                padding: 4px;
                font-size: 14px;
                color: #ffffff;
            }
        """)
        self.text_edit.hide()
        self.text_edit_position = QPoint()
        self.text_edit_font = None
        self.is_finishing_text = False
        self.editing_annotation = None  # 正在编辑的文字标注

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # 绘制原始图像
        painter.drawImage(0, 0, self.editor.original_image)
        # 绘制所有标注
        for ann in self.editor.annotations:
            ann.draw(painter)
        # 绘制选中状态和手柄
        for ann in self.editor.annotations:
            ann.draw_selection(painter)
        # 绘制当前正在绘制的标注
        if self.editor.current_annotation:
            self.editor.current_annotation.draw(painter)

    def start_text_edit(self, pos, existing_annotation=None):
        """开始内联文字编辑"""
        if existing_annotation:
            # 编辑现有文字标注
            self.editing_annotation = existing_annotation
            # 获取边界矩形
            rect = existing_annotation.get_bounding_rect()
            self.text_edit_position = QPoint(rect.left(), rect.top())
            self.text_edit_font = QFont(existing_annotation.font)

            # 设置编辑框
            self.text_edit.setFont(self.text_edit_font)
            self.text_edit.setText(existing_annotation.text)
            self.text_edit.setGeometry(rect.left(), rect.top(), rect.width() + 50, 35)
        else:
            # 创建新文字标注
            self.editing_annotation = None
            self.text_edit_position = pos
            self.text_edit_font = QFont("Microsoft YaHei", 14)

            # 设置编辑框
            self.text_edit.setFont(self.text_edit_font)
            self.text_edit.setText("")
            self.text_edit.setGeometry(pos.x(), pos.y() - 30, 300, 35)

        self.text_edit.show()
        self.text_edit.setFocus()
        self.text_edit.selectAll()  # 全选文字以便编辑
        self.is_finishing_text = False

        # 连接编辑完成信号（只连接一次）
        try:
            self.text_edit.editingFinished.disconnect()
        except:
            pass
        self.text_edit.editingFinished.connect(self.finish_text_edit)

    def finish_text_edit(self):
        """完成文字编辑"""
        if self.is_finishing_text:
            return

        self.is_finishing_text = True
        text = self.text_edit.text().strip()

        if text:
            if self.editing_annotation:
                # 更新现有文字标注
                self.editing_annotation.text = text
            else:
                # 创建文字标注
                ann = TextAnnotation()
                ann.text = text
                ann.color = self.editor.color
                ann.font = self.text_edit_font

                # 添加两个点形成边界
                pos = self.text_edit_position
                default_size = 50
                ann.points = [
                    QPoint(pos.x(), pos.y() - default_size),
                    QPoint(pos.x() + default_size * 2, pos.y())
                ]

                self.editor.add_annotation(ann)

        self.editing_annotation = None
        self.text_edit.hide()
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()

            # 确保画布获得焦点，这样键盘事件能正常工作
            self.setFocus()

            if self.editor.current_tool == AnnotationItem.SELECT:
                # 选择模式
                self.is_moving = False
                self.is_resizing = False
                self.selected_annotation = None
                self.orig_font = None
                self.orig_radius = None

                # 先检查是否有手柄被点击（在清除选中之前）
                for ann in reversed(self.editor.annotations):
                    if ann.is_selected:  # 只检查已选中的元素的手柄
                        handle = ann.get_handle_at_point(pos)
                        if handle is not None:
                            self.selected_annotation = ann
                            self.is_resizing = True
                            self.resize_handle = handle
                            self.drag_start_pos = pos
                            self.original_points = [QPoint(p) for p in ann.points]
                            # 保存原始参数
                            if ann.type == AnnotationItem.TEXT:
                                self.orig_font = QFont(ann.font)
                            elif ann.type == AnnotationItem.NUMBER:
                                self.orig_radius = ann.radius
                            break

                # 如果没有点击手柄
                if not self.is_resizing:
                    # 先清除所有选择
                    for ann in self.editor.annotations:
                        ann.is_selected = False

                    # 检查是否有标注被点击
                    for ann in reversed(self.editor.annotations):
                        if ann.contains_point(pos):
                            ann.is_selected = True
                            self.selected_annotation = ann
                            self.is_moving = True
                            self.drag_start_pos = pos
                            self.original_points = [QPoint(p) for p in ann.points]
                            break
            else:
                if self.editor.current_tool == AnnotationItem.TEXT:
                    # 文字工具：显示内联编辑框
                    self.start_text_edit(pos)
                else:
                    # 其他标注：正常创建
                    self.editor.is_drawing = True

                    if self.editor.current_tool == AnnotationItem.PEN:
                        ann = PenAnnotation()
                    elif self.editor.current_tool == AnnotationItem.LINE:
                        ann = LineAnnotation()
                    elif self.editor.current_tool == AnnotationItem.RECT:
                        ann = RectAnnotation()
                    elif self.editor.current_tool == AnnotationItem.ELLIPSE:
                        ann = EllipseAnnotation()
                    elif self.editor.current_tool == AnnotationItem.ARROW:
                        ann = ArrowAnnotation()
                    elif self.editor.current_tool == AnnotationItem.NUMBER:
                        ann = NumberAnnotation()
                        ann.number = self.editor.number_counter
                        self.editor.number_counter += 1
                    elif self.editor.current_tool == AnnotationItem.MOSAIC:
                        ann = MosaicAnnotation()
                        # 保存原始图像引用
                        ann.original_image = self.editor.original_image

                    ann.color = self.editor.color
                    ann.line_width = self.editor.line_width
                    ann.points.append(pos)

                    # 对于序号，添加第二个默认点，形成边界，并且立即完成添加
                    if self.editor.current_tool == AnnotationItem.NUMBER:
                        default_size = 50
                        ann.points.append(QPoint(pos.x() + default_size, pos.y() + default_size))
                        # 序号标注：立即添加并结束绘制，不支持拖动调整大小
                        self.editor.add_annotation(ann)
                        self.editor.is_drawing = False
                        return

                    self.editor.current_annotation = ann

            self.update()

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()

        if self.editor.current_tool == AnnotationItem.SELECT:
            if self.is_moving and self.selected_annotation:
                # 移动标注
                dx = pos.x() - self.drag_start_pos.x()
                dy = pos.y() - self.drag_start_pos.y()
                # 恢复原始位置然后移动
                self.selected_annotation.points = [QPoint(p) for p in self.original_points]
                self.selected_annotation.move_by(dx, dy)
                self.update()
            elif self.is_resizing and self.selected_annotation:
                # 缩放标注
                dx = pos.x() - self.drag_start_pos.x()
                dy = pos.y() - self.drag_start_pos.y()
                self.resize_annotation(self.selected_annotation, dx, dy, pos)
                self.update()
            else:
                # 更新光标
                self.update_cursor(pos)
        else:
            # 正常绘制逻辑
            if self.editor.is_drawing and self.editor.current_annotation:
                if self.editor.current_tool == AnnotationItem.PEN:
                    self.editor.current_annotation.points.append(pos)
                else:
                    if len(self.editor.current_annotation.points) == 1:
                        self.editor.current_annotation.points.append(pos)
                    else:
                        self.editor.current_annotation.points[-1] = pos
                self.update()

    def resize_annotation(self, ann, dx, dy, pos):
        """根据手柄缩放标注 - 支持所有类型"""
        if len(self.original_points) == 0:
            return

        # 计算缩放因子
        orig_rect = QRect(self.original_points[0], self.original_points[-1]).normalized()

        # 根据不同的手柄计算新的边界
        new_rect = QRect(orig_rect)

        if self.resize_handle == 0:  # 左上
            new_rect.setLeft(orig_rect.left() + dx)
            new_rect.setTop(orig_rect.top() + dy)
        elif self.resize_handle == 1:  # 上中
            new_rect.setTop(orig_rect.top() + dy)
        elif self.resize_handle == 2:  # 右上
            new_rect.setRight(orig_rect.right() + dx)
            new_rect.setTop(orig_rect.top() + dy)
        elif self.resize_handle == 3:  # 右中
            new_rect.setRight(orig_rect.right() + dx)
        elif self.resize_handle == 4:  # 右下
            new_rect.setRight(orig_rect.right() + dx)
            new_rect.setBottom(orig_rect.bottom() + dy)
        elif self.resize_handle == 5:  # 下中
            new_rect.setBottom(orig_rect.bottom() + dy)
        elif self.resize_handle == 6:  # 左下
            new_rect.setLeft(orig_rect.left() + dx)
            new_rect.setBottom(orig_rect.bottom() + dy)
        elif self.resize_handle == 7:  # 左中
            new_rect.setLeft(orig_rect.left() + dx)

        # 确保最小尺寸
        if new_rect.width() < 10:
            new_rect.setWidth(10)
        if new_rect.height() < 10:
            new_rect.setHeight(10)

        # 根据标注类型处理不同的缩放逻辑
        if ann.type == AnnotationItem.PEN:
            # 画笔使用比例缩放
            scale_x = new_rect.width() / max(orig_rect.width(), 1)
            scale_y = new_rect.height() / max(orig_rect.height(), 1)
            center = orig_rect.center()
            new_points = []
            for p in self.original_points:
                # 先相对于中心点平移，然后缩放，最后再平移回来
                rel_x = (p.x() - center.x()) * scale_x
                rel_y = (p.y() - center.y()) * scale_y
                new_x = center.x() + rel_x + (new_rect.center().x() - center.x())
                new_y = center.y() + rel_y + (new_rect.center().y() - center.y())
                new_points.append(QPoint(int(new_x), int(new_y)))
            ann.points = new_points
        elif ann.type in [AnnotationItem.RECT, AnnotationItem.ELLIPSE,
                          AnnotationItem.MOSAIC]:
            # 矩形类使用新的边界点
            ann.points = [new_rect.topLeft(), new_rect.bottomRight()]
        elif ann.type in [AnnotationItem.ARROW, AnnotationItem.LINE]:
            # 箭头和直线根据手柄移动起点或终点
            if len(self.original_points) >= 2:
                if self.resize_handle in [0, 6, 7]:  # 左边手柄
                    ann.points = [new_rect.topLeft(), self.original_points[-1]]
                elif self.resize_handle in [2, 3, 4]:  # 右边手柄
                    ann.points = [self.original_points[0], new_rect.bottomRight()]
                elif self.resize_handle == 1:  # 上边手柄
                    ann.points = [QPoint(self.original_points[0].x(), new_rect.top()), self.original_points[-1]]
                elif self.resize_handle == 5:  # 下边手柄
                    ann.points = [self.original_points[0], QPoint(self.original_points[-1].x(), new_rect.bottom())]
        elif ann.type == AnnotationItem.TEXT:
            # 文字标注缩放：保持两个边界点，同时更新字体
            ann.points = [new_rect.topLeft(), new_rect.bottomRight()]
            if self.orig_font:
                orig_font = self.orig_font
            else:
                orig_font = ann.font
            # 根据高度变化计算字体缩放比例
            scale = new_rect.height() / max(orig_rect.height(), 1)
            # 确保字体在合理范围内
            new_size = max(8, min(100, int(orig_font.pointSize() * scale)))
            ann.font.setPointSize(new_size)
        elif ann.type == AnnotationItem.NUMBER:
            # 序号标注缩放：只需要保持两个边界点，半径在 draw 中计算
            ann.points = [new_rect.topLeft(), new_rect.bottomRight()]

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.editor.current_tool == AnnotationItem.SELECT:
                self.is_moving = False
                self.is_resizing = False
                self.resize_handle = None
            elif self.editor.current_tool != AnnotationItem.TEXT:
                # 除了文字工具外，其他工具正常处理
                if self.editor.is_drawing and self.editor.current_annotation:
                    self.editor.is_drawing = False
                    self.editor.add_annotation(self.editor.current_annotation)
                    self.editor.current_annotation = None

            self.update()

    def update_cursor(self, pos):
        """更新光标形状"""
        cursor = Qt.CursorShape.CrossCursor

        # 检查是否有手柄在鼠标下
        for ann in reversed(self.editor.annotations):
            if ann.is_selected:
                handle = ann.get_handle_at_point(pos)
                if handle is not None:
                    # 根据手柄设置光标
                    cursors = [
                        Qt.CursorShape.SizeFDiagCursor,
                        Qt.CursorShape.SizeVerCursor,
                        Qt.CursorShape.SizeBDiagCursor,
                        Qt.CursorShape.SizeHorCursor,
                        Qt.CursorShape.SizeFDiagCursor,
                        Qt.CursorShape.SizeVerCursor,
                        Qt.CursorShape.SizeBDiagCursor,
                        Qt.CursorShape.SizeHorCursor,
                    ]
                    cursor = cursors[handle]
                    break
                elif ann.contains_point(pos):
                    cursor = Qt.CursorShape.SizeAllCursor
                    break

        self.setCursor(cursor)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            # 如果正在编辑文字，取消编辑
            if self.text_edit.isVisible():
                self.text_edit.hide()
                self.update()
            else:
                # 取消选择
                for ann in self.editor.annotations:
                    ann.is_selected = False
                self.selected_annotation = None
                self.is_moving = False
                self.is_resizing = False
                self.update()
        elif event.key() == Qt.Key.Key_Delete or event.key() == Qt.Key.Key_Backspace:
            # 删除选中的标注
            self.editor.annotations = [a for a in self.editor.annotations if not a.is_selected]
            self.selected_annotation = None
            self.is_moving = False
            self.is_resizing = False
            self.update()

    def mouseDoubleClickEvent(self, event):
        """双击事件处理"""
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()

            # 检查是否双击了文字标注
            for ann in reversed(self.editor.annotations):
                if ann.type == AnnotationItem.TEXT and ann.contains_point(pos):
                    # 选中标注
                    for a in self.editor.annotations:
                        a.is_selected = False
                    ann.is_selected = True
                    self.selected_annotation = ann

                    # 开始编辑文字
                    self.start_text_edit(pos, ann)
                    return


class StickerWindow(QWidget):
    """贴图窗口"""

    def __init__(self, image):
        super().__init__()
        self.image = image
        self.scale = 1.0
        self.opacity = 0.9
        self.is_pinned = True  # 默认置顶
        self.drag_pos = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.init_ui()
        self.resize(int(image.width() * self.scale), int(image.height() * self.scale))

    def init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 图像显示
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.update_image()
        layout.addWidget(self.image_label)

        self.setLayout(layout)

    def update_image(self):
        """更新显示的图像"""
        scaled = self.image.scaled(
            int(self.image.width() * self.scale),
            int(self.image.height() * self.scale),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.image_label.setPixmap(QPixmap.fromImage(scaled))
        self.resize(scaled.width(), scaled.height())
        self.setWindowOpacity(self.opacity)

    def toggle_pin(self):
        """切换置顶状态"""
        self.is_pinned = not self.is_pinned
        if self.is_pinned:
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.Tool
            )
        else:
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.Tool
            )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.show()

    def contextMenuEvent(self, event):
        """右键菜单"""

        menu = QMenu(self)

        # 透明度子菜单
        opacity_menu = menu.addMenu("透明度")

        # 创建一个带滑块的动作
        opacity_widget = QWidget()
        opacity_layout = QVBoxLayout()
        opacity_layout.setContentsMargins(10, 5, 10, 5)

        opacity_label = QLabel(f"{int(self.opacity * 100)}%")
        opacity_layout.addWidget(opacity_label)

        opacity_slider = QSlider(Qt.Orientation.Horizontal)
        opacity_slider.setRange(10, 100)
        opacity_slider.setValue(int(self.opacity * 100))

        def update_opacity(value):
            opacity_label.setText(f"{value}%")

        opacity_slider.valueChanged.connect(update_opacity)
        opacity_layout.addWidget(opacity_slider)

        opacity_widget.setLayout(opacity_layout)

        opacity_action = QWidgetAction(self)
        opacity_action.setDefaultWidget(opacity_widget)
        opacity_menu.addAction(opacity_action)

        # 应用透明度按钮
        apply_opacity = QAction("应用透明度", self)

        def apply_op():
            self.opacity = opacity_slider.value() / 100.0
            self.setWindowOpacity(self.opacity)

        apply_opacity.triggered.connect(apply_op)
        opacity_menu.addAction(apply_opacity)

        menu.addSeparator()

        # 置顶/取消置顶
        pin_text = "取消置顶" if self.is_pinned else "置顶"
        pin_action = QAction(pin_text, self)
        pin_action.triggered.connect(self.toggle_pin)
        menu.addAction(pin_action)

        menu.addSeparator()

        # 关闭
        close_action = QAction("关闭", self)
        close_action.triggered.connect(self.close)
        menu.addAction(close_action)

        menu.exec(QCursor.pos())

    def wheelEvent(self, event):
        """鼠标滚轮缩放"""
        delta = event.angleDelta().y()
        # 根据滚轮步数计算缩放因子，更自然
        num_steps = abs(delta) / 120.0  # 标准滚轮一步是120
        base_factor = 1.08
        if delta > 0:
            scale_factor = base_factor ** num_steps
        else:
            scale_factor = 1.0 / (base_factor ** num_steps)

        new_scale = self.scale * scale_factor
        # 限制缩放范围
        if 0.2 <= new_scale <= 3.0:
            # 获取鼠标在屏幕上的位置
            mouse_pos_screen = event.globalPosition().toPoint()
            # 获取鼠标在窗口内的位置（相对于窗口）
            mouse_pos_window = event.position().toPoint()

            old_size = self.size()
            old_pos = self.pos()

            # 计算缩放前鼠标相对于图片的位置比例
            relative_x = mouse_pos_window.x() / old_size.width()
            relative_y = mouse_pos_window.y() / old_size.height()

            # 更新缩放
            self.scale = new_scale
            self.update_image()

            # 计算新大小
            new_size = self.size()

            # 计算新位置，使缩放以鼠标位置为中心
            # 鼠标应该指向图片上的同一个位置
            new_x = int(mouse_pos_screen.x() - new_size.width() * relative_x)
            new_y = int(mouse_pos_screen.y() - new_size.height() * relative_y)

            self.move(new_x, new_y)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_pos:
            self.move(event.globalPosition().toPoint() - self.drag_pos)


class ScreenshotManager:
    """截图管理器"""

    def __init__(self, settings_manager, theme_manager=None):
        self.settings_manager = settings_manager
        self.theme_manager = theme_manager
        self.screenshot_window = None
        self.annotation_editor = None
        self.sticker_windows = []
        self.ocr_engine = OCREngine(settings_manager)
        self.ocr_window = None

    def take_screenshot(self):
        """开始截图"""
        self.screenshot_window = ScreenshotWindow()
        self.screenshot_window.screenshot_taken.connect(self.on_screenshot_taken)
        self.screenshot_window.cancelled.connect(self.on_cancelled)
        self.screenshot_window.show()

    def on_screenshot_taken(self, image):
        """截图完成"""
        action = self.settings_manager.get('screenshot_action', 'annotate')

        if action == 'annotate':
            # 打开标注编辑器
            self.show_annotation_editor(image)
        elif action == 'copy':
            # 直接复制
            self.copy_to_clipboard(image)
        elif action == 'save':
            # 直接保存
            self.save_image(image)

    def on_cancelled(self):
        """取消截图"""
        pass

    def show_annotation_editor(self, image):
        """显示标注编辑器"""
        self.annotation_editor = AnnotationEditor(image, self.theme_manager)
        self.annotation_editor.save_clicked.connect(self.save_image)
        self.annotation_editor.copy_clicked.connect(self.copy_to_clipboard)
        self.annotation_editor.ocr_clicked.connect(self.do_ocr)
        self.annotation_editor.ai_clicked.connect(self.do_ai)
        self.annotation_editor.sticker_clicked.connect(self.create_sticker)
        self.annotation_editor.show()

    def copy_to_clipboard(self, image):
        """复制到剪贴板"""
        clipboard = QApplication.clipboard()
        clipboard.setImage(image)

    def save_image(self, image):
        """保存图像 - 静默保存到默认位置，然后关闭编辑窗口"""
        save_path = self.settings_manager.get('screenshot_save_path', '')
        if not save_path or not os.path.exists(save_path):
            save_path = os.path.expanduser('~')

        file_path = os.path.join(save_path, f"screenshot_{self.get_timestamp()}.png")
        image.save(file_path)

        # 保存完成后关闭编辑窗口
        if hasattr(self, 'annotation_editor') and self.annotation_editor:
            self.annotation_editor.close()
            self.annotation_editor = None

    def get_timestamp(self):
        """获取时间戳"""
        return datetime.now().strftime('%Y%m%d_%H%M%S')

    def do_ocr(self, image):
        """OCR识别"""
        # 创建OCR结果窗口，设置为模态对话框
        self.ocr_window = OCRResultWindow(image, self.ocr_engine, self.theme_manager, parent=self.annotation_editor)
        self.ocr_window.setWindowModality(Qt.WindowModality.WindowModal)
        self.ocr_window.show()

    def do_ai(self, image):
        """问AI"""
        # 创建AI对话框，设置为模态对话框
        self.ai_window = AIDialog(image, self.settings_manager, self.theme_manager, parent=self.annotation_editor)
        self.ai_window.setWindowModality(Qt.WindowModality.WindowModal)
        self.ai_window.show()

    def create_sticker(self, image):
        """创建贴图"""
        sticker = StickerWindow(image)
        self.sticker_windows.append(sticker)
        sticker.show()


class OCRWorker(QThread):
    """OCR 工作线程
    在后台线程中处理 OCR 识别"""
    finished = pyqtSignal(str)

    def __init__(self, ocr_engine, image_arr):
        super().__init__()
        self.ocr_engine = ocr_engine
        self.image_arr = image_arr

    def run(self):
        """执行 OCR 识别"""
        result = self.ocr_engine.recognize_from_array(self.image_arr)
        self.finished.emit(result)


class OCRResultWindow(QMainWindow):
    """OCR结果显示窗口"""

    def __init__(self, image, ocr_engine, theme_manager=None, parent=None):
        super().__init__(parent)
        self.image = image
        self.ocr_engine = ocr_engine
        self.theme_manager = theme_manager
        self.result_text = ""
        self.ocr_worker = None
        self.init_ui()
        self.apply_theme()
        self.process_image()

    def init_ui(self):
        self.setWindowTitle("OCR 文字识别")
        self.setFixedSize(700, 500)
        self.setWindowFlags(Qt.WindowType.Tool)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 标题
        title_label = QLabel("识别结果")
        title_label.setFont(QFont("Microsoft YaHei", 14, QFont.Weight.Bold))
        layout.addWidget(title_label)

        # 文本区域
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setPlaceholderText("正在识别中...")
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                padding: 12px;
                font-size: 14px;
                line-height: 1.6;
            }
        """)
        layout.addWidget(self.text_edit)

        # 按钮区域
        btn_layout = QHBoxLayout()

        self.reocr_btn = QPushButton("🔄 重新识别")
        self.reocr_btn.clicked.connect(self.reocr)
        self.reocr_btn.setStyleSheet("""
            QPushButton {
                background-color: #6366f1;
                color: white;
                padding: 10px 20px;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4f46e5;
            }
            QPushButton:disabled {
                background-color: #a5b4fc;
            }
        """)

        self.copy_btn = QPushButton("📋 复制")
        self.copy_btn.clicked.connect(self.copy_text)
        self.copy_btn.setStyleSheet("""
            QPushButton {
                background-color: #64748b;
                color: white;
                padding: 10px 20px;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #475569;
            }
        """)

        btn_layout.addWidget(self.reocr_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.copy_btn)
        layout.addLayout(btn_layout)

        # 初始禁用按钮
        self.set_buttons_enabled(False)

    def set_buttons_enabled(self, enabled):
        """设置按钮状态"""
        self.copy_btn.setEnabled(enabled)
        self.reocr_btn.setEnabled(enabled)

    def process_image(self):
        """处理图像并显示结果 - 使用后台线程"""
        self.text_edit.clear()
        self.text_edit.setPlaceholderText("正在识别文字，请稍候...")
        self.set_buttons_enabled(False)

        # 在主线程完成 QImage 转换（安全的 UI 操作）
        image_arr = OCREngine.convert_qimage_to_array(self.image)

        # 创建并启动后台线程（只传递 numpy 数组，不涉及 UI 对象）
        self.ocr_worker = OCRWorker(self.ocr_engine, image_arr)
        self.ocr_worker.finished.connect(self.on_ocr_finished)
        self.ocr_worker.start()

    def on_ocr_finished(self, result):
        """OCR 完成回调"""
        self.result_text = result
        # 尝试使用 Markdown 渲染
        try:
            self.text_edit.setMarkdown(result)
        except:
            # 如果 Markdown 渲染失败，回退到纯文本
            self.text_edit.setText(result)
        self.set_buttons_enabled(True)

        # 清理线程
        if self.ocr_worker:
            self.ocr_worker.deleteLater()
            self.ocr_worker = None

    def reocr(self):
        """重新识别"""
        self.process_image()

    def copy_text(self):
        """复制文本到剪贴板"""
        text = self.text_edit.toPlainText()
        if text:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            # QMessageBox.information(self, "成功", "已复制到剪贴板！")

    def apply_theme(self):
        """应用主题"""
        if not self.theme_manager:
            return
        colors = self.theme_manager.get_colors()

        # 设置窗口背景
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {colors['window']};
            }}
        """)

        # 设置标题标签
        self.findChild(QLabel).setStyleSheet(f"color: {colors['window_text']};")

        # 设置文本区域
        self.text_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: {colors['base']};
                color: {colors['base_text']};
                border: 1px solid {colors['border']};
                border-radius: 6px;
                padding: 12px;
                font-size: 14px;
                line-height: 1.6;
            }}
        """)

        # 设置重新识别按钮
        self.reocr_btn.setStyleSheet(f"""
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
                background-color: {colors['hover']};
            }}
            QPushButton:disabled {{
                background-color: {colors['border']};
                color: {colors['text_secondary']};
            }}
        """)

        # 设置复制按钮
        self.copy_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {colors['button']};
                color: {colors['button_text']};
                padding: 10px 20px;
                border: 1px solid {colors['border']};
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {colors['hover']};
                border-color: {colors['highlight']};
            }}
        """)

    def closeEvent(self, event):
        """窗口关闭时确保线程被清理"""
        if self.ocr_worker and self.ocr_worker.isRunning():
            self.ocr_worker.quit()
            self.ocr_worker.wait()
        event.accept()


class AIDialog(QMainWindow):
    """AI对话框"""

    def __init__(self, image, settings_manager, theme_manager=None, parent=None):
        super().__init__(parent)
        self.image = image
        self.settings_manager = settings_manager
        self.theme_manager = theme_manager
        self.current_task = None
        self.worker = None
        self.recognized_text = None
        self.init_ui()
        self.apply_theme()

    def init_ui(self):
        self.setWindowTitle("问AI")
        self.setFixedSize(700, 600)
        self.setWindowFlags(Qt.WindowType.Tool)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 标题
        title_label = QLabel("问AI")
        title_label.setFont(QFont("Microsoft YaHei", 14, QFont.Weight.Bold))
        layout.addWidget(title_label)

        # 模型选择
        model_layout = QHBoxLayout()
        model_label = QLabel("选择模型：")
        model_label.setStyleSheet("font-size: 13px; color: #64748b;")
        self.model_combo = QComboBox()
        self.model_combo.setStyleSheet("""
            QComboBox {
                padding: 8px 12px;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                background-color: white;
                min-width: 200px;
            }
        """)
        self.load_models()
        model_layout.addWidget(model_label)
        model_layout.addWidget(self.model_combo)
        model_layout.addStretch()
        layout.addLayout(model_layout)

        # 结果区域
        result_label = QLabel("结果：")
        result_label.setStyleSheet("font-size: 13px; font-weight: 600; color: #1e293b; margin-top: 10px;")
        layout.addWidget(result_label)

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setPlaceholderText("请选择下方操作开始...")
        self.result_text.setStyleSheet("""
            QTextEdit {
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                padding: 12px;
                font-size: 14px;
                line-height: 1.6;
            }
        """)
        layout.addWidget(self.result_text)

        # 底部按钮
        bottom_layout = QHBoxLayout()

        # 操作按钮（左）
        self.explain_btn = QPushButton("🔍 解释图像")
        self.explain_btn.clicked.connect(lambda: self.start_task("explain"))
        self.explain_btn.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: white;
                padding: 10px 16px;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:disabled {
                background-color: #6ee7b7;
            }
        """)

        self.ocr_btn = QPushButton("📝 识别文字")
        self.ocr_btn.clicked.connect(lambda: self.start_task("ocr"))
        self.ocr_btn.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                color: white;
                padding: 10px 16px;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
            QPushButton:disabled {
                background-color: #93c5fd;
            }
        """)

        self.translate_btn = QPushButton("🌐 翻译文字")
        self.translate_btn.clicked.connect(lambda: self.start_task("translate"))
        self.translate_btn.setStyleSheet("""
            QPushButton {
                background-color: #8b5cf6;
                color: white;
                padding: 10px 16px;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7c3aed;
            }
            QPushButton:disabled {
                background-color: #c4b5fd;
            }
        """)

        bottom_layout.addWidget(self.explain_btn)
        bottom_layout.addWidget(self.ocr_btn)
        bottom_layout.addWidget(self.translate_btn)
        bottom_layout.addStretch()

        # 操作按钮（右）
        copy_btn = QPushButton("📋 复制")
        copy_btn.clicked.connect(self.copy_result)
        copy_btn.setStyleSheet("""
            QPushButton {
                background-color: #64748b;
                color: white;
                padding: 10px 20px;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #475569;
            }
        """)

        bottom_layout.addWidget(copy_btn)
        layout.addLayout(bottom_layout)

    def load_models(self):
        self.model_combo.clear()
        ai_models = self.settings_manager.get('ai_models', [])
        enabled_models = [model for model in ai_models if model.get('enabled', True)]
        if not enabled_models:
            self.model_combo.addItem("没有配置模型")
            self.model_combo.setEnabled(False)
            return

        for model in enabled_models:
            self.model_combo.addItem(model['name'], model)

    def set_buttons_enabled(self, enabled):
        self.explain_btn.setEnabled(enabled)
        self.ocr_btn.setEnabled(enabled)
        self.translate_btn.setEnabled(enabled)
        self.model_combo.setEnabled(enabled)

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

    def start_task(self, task_type):
        self.current_task = task_type
        self.set_buttons_enabled(False)

        if task_type == "translate" and not self.recognized_text:
            self.result_text.setPlainText("请先使用 \"识别文字\" 功能识别图中文字！")
            self.set_buttons_enabled(True)
            return

        model_data = self.model_combo.currentData()
        if not model_data:
            self.result_text.setPlainText("未配置可用的AI模型，请在设置中添加模型！")
            self.set_buttons_enabled(True)
            return

        self.result_text.setPlainText("正在处理中...")

        proxy_config = self.get_proxy_config()

        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()

        self.worker = AIWorker(
            model_data,
            self.image,
            self.recognized_text,
            task_type,
            proxy_config
        )
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.error.connect(self.on_worker_error)
        self.worker.start()

    def on_worker_finished(self, result):
        if self.current_task == "ocr":
            self.recognized_text = result
            # 尝试使用 Markdown 渲染
            try:
                self.result_text.setMarkdown(result)
            except:
                self.result_text.setPlainText(result)
        else:
            try:
                self.result_text.setMarkdown(result)
            except:
                self.result_text.setPlainText(result)
        self.set_buttons_enabled(True)

    def on_worker_error(self, error):
        self.result_text.setPlainText(f"错误：{error}")
        self.set_buttons_enabled(True)

    def apply_theme(self):
        """应用主题"""
        if not self.theme_manager:
            return
        colors = self.theme_manager.get_colors()

        # 设置窗口背景
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {colors['window']};
            }}
        """)

        # 设置所有标签
        for label in self.findChildren(QLabel):
            label.setStyleSheet(f"color: {colors['window_text']};")

        # 设置模型下拉框
        self.model_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {colors['base']};
                color: {colors['base_text']};
                border: 1px solid {colors['border']};
                border-radius: 6px;
                padding: 8px 12px;
                min-width: 200px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 30px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid {colors['base']};
                border-right: 5px solid {colors['base']};
                border-top: 6px solid {colors['base_text']};
                width: 0;
                height: 0;
            }}
            QComboBox QAbstractItemView {{
                background-color: {colors['base']};
                color: {colors['base_text']};
                border: 1px solid {colors['border']};
                selection-background-color: {colors['highlight']};
                selection-color: {colors['highlight_text']};
            }}
        """)

        # 设置结果文本区域
        self.result_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {colors['base']};
                color: {colors['base_text']};
                border: 1px solid {colors['border']};
                border-radius: 6px;
                padding: 12px;
                font-size: 14px;
                line-height: 1.6;
            }}
        """)

        # 设置解释图像按钮
        self.explain_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {colors['success']};
                color: white;
                padding: 10px 16px;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #059669;
            }}
            QPushButton:disabled {{
                background-color: {colors['border']};
                color: {colors['text_secondary']};
            }}
        """)

        # 设置识别文字按钮
        self.ocr_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {colors['info']};
                color: white;
                padding: 10px 16px;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #2563eb;
            }}
            QPushButton:disabled {{
                background-color: {colors['border']};
                color: {colors['text_secondary']};
            }}
        """)

        # 设置翻译文字按钮
        self.translate_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #8b5cf6;
                color: white;
                padding: 10px 16px;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #7c3aed;
            }}
            QPushButton:disabled {{
                background-color: {colors['border']};
                color: {colors['text_secondary']};
            }}
        """)

        # 设置复制按钮
        for btn in self.findChildren(QPushButton):
            if btn.text() == "📋 复制":
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {colors['button']};
                        color: {colors['button_text']};
                        padding: 10px 20px;
                        border: 1px solid {colors['border']};
                        border-radius: 6px;
                        font-size: 14px;
                        font-weight: bold;
                    }}
                    QPushButton:hover {{
                        background-color: {colors['hover']};
                        border-color: {colors['highlight']};
                    }}
                """)

    def copy_result(self):
        text = self.result_text.toPlainText()
        if text:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            # QMessageBox.information(self, "成功", "已复制到剪贴板！")

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait()
        event.accept()


class AIWorker(QThread):
    """AI工作线程"""
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, model_data, image, recognized_text, task_type, proxy_config):
        super().__init__()
        self.model_data = model_data
        self.image = image
        self.recognized_text = recognized_text
        self.task_type = task_type
        self.proxy_config = proxy_config

    def encode_image_to_base64(self):

        buffer = QBuffer()
        buffer.open(QBuffer.OpenModeFlag.WriteOnly)
        self.image.save(buffer, "PNG")
        image_data = buffer.data().toBase64()
        return image_data.data().decode('utf-8')

    def run(self):
        try:
            api_url = self.model_data['api_url']
            api_key = self.model_data['api_key']
            model = self.model_data['model']

            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }

            user_content = None

            if self.task_type == "explain":
                base64_image = self.encode_image_to_base64()
                user_content = [
                    {
                        "type": "text",
                        "text": "请详细描述这张图片的内容，包括场景、物体、文字等信息。"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}"
                        }
                    }
                ]
            elif self.task_type == "ocr":
                base64_image = self.encode_image_to_base64()
                user_content = [
                    {
                        "type": "text",
                        "text": "请识别这张图片中的所有文字，准确提取出来。"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}"
                        }
                    }
                ]
            elif self.task_type == "translate":
                user_content = f"请将以下文字翻译成中文，保持原意不变：\n\n{self.recognized_text}"

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


class OCREngine:
    """OCR引擎"""

    def __init__(self, settings_manager=None):
        self.settings_manager = settings_manager

    def recognize(self, image):
        """识别文字（兼容旧方法）"""
        # 将 QImage 转换为图片字节流
        byte_stream = BytesIO()
        image.save(byte_stream, format="PNG")
        return self.recognize_from_bytes(byte_stream.getvalue())

    def recognize_from_bytes(self, image_bytes):
        """从图片字节流识别文字"""

        if not self.settings_manager:
            return "未设置配置管理器"

        # 获取配置
        api_token = self.settings_manager.get('ocr_api_token', '')
        api_url = self.settings_manager.get('ocr_api_url', '')
        model = self.settings_manager.get('ocr_model', 'pp-ocrv5')

        if not api_token:
            return "请先在设置中配置PaddleOCR API Token"

        # 默认API URL
        if not api_url:
            api_url = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"

        # 模型名称映射（保持与下拉框对应）
        model_map = {
            'pp-ocrv5': 'PP-OCRv5',
            'paddleocr-vl-1.5': 'PaddleOCR-VL-1.5',
            'paddleocr-vl': 'PaddleOCR-VL'
        }
        model = model_map.get(model, 'PP-OCRv5')

        # 构建可选参数
        if model == 'PP-OCRv5':
            optional_payload = {
                "markdownIgnoreLabels": [],
                "useDocOrientationClassify": False,
                "useDocUnwarping": False,
                "useTextlineOrientation": False,
                "textDetLimitType": "min",
                "textDetLimitSideLen": 64,
                "textDetThresh": 0.3,
                "textDetBoxThresh": 0.6,
                "textDetUnclipRatio": 1.5,
                "textRecScoreThresh": 0,
                "parseLanguage": "default"
            }
        else:
            optional_payload = {
                "markdownIgnoreLabels": [
                    "header",
                    "header_image",
                    "footer",
                    "footer_image",
                    "number",
                    "footnote",
                    "aside_text"
                ],
                "useDocOrientationClassify": False,
                "useDocUnwarping": False,
                "useLayoutDetection": True,
                "useChartRecognition": False,
                "useSealRecognition": False,
                "useOcrForImageBlock": False,
                "mergeTables": True,
                "relevelTitles": True,
                "layoutShapeMode": "auto",
                "promptLabel": "ocr",
                "repetitionPenalty": 1,
                "temperature": 0,
                "topP": 1,
                "minPixels": 147384,
                "maxPixels": 2822400,
                "layoutNms": True,
                "restructurePages": True
            }

        headers = {
            "Authorization": f"bearer {api_token}",
        }

        # 准备请求数据
        data = {
            "model": model,
            "optionalPayload": json.dumps(optional_payload)
        }

        # 准备文件
        files = {"file": ("image.png", BytesIO(image_bytes), "image/png")}

        try:
            # 1. 提交任务
            job_response = requests.post(api_url, headers=headers, data=data, files=files, timeout=30)

            if job_response.status_code != 200:
                return f"API请求失败: {job_response.status_code} - {job_response.text}"

            job_data = job_response.json()
            job_id = job_data["data"]["jobId"]

            # 2. 轮询任务状态
            jsonl_url = ""
            while True:
                job_result_response = requests.get(f"{api_url}/{job_id}", headers=headers, timeout=30)
                if job_result_response.status_code != 200:
                    return f"获取任务状态失败: {job_result_response.status_code}"

                result_data = job_result_response.json()
                state = result_data["data"]["state"]

                if state == 'pending':
                    time.sleep(2)
                    continue
                elif state == 'running':
                    time.sleep(2)
                    continue
                elif state == 'done':
                    jsonl_url = result_data["data"]["resultUrl"]["jsonUrl"]
                    break
                elif state == "failed":
                    error_msg = result_data["data"].get("errorMsg", "未知错误")
                    return f"任务失败: {error_msg}"

            # 3. 获取结果
            jsonl_response = requests.get(jsonl_url, timeout=30)
            jsonl_response.raise_for_status()

            # 解析JSONL
            lines = jsonl_response.text.strip().split('\n')
            all_texts = []

            for line in lines:
                line = line.strip()
                if not line:
                    continue
                result = json.loads(line)["result"]

                if model == 'PP-OCRv5':
                    # PP-OCRv5 使用 ocrResults
                    if "ocrResults" in result:
                        for res in result["ocrResults"]:
                            if "prunedResult" in res:
                                # 从 prunedResult 中提取文本
                                pruned = res["prunedResult"]
                                if "rec_texts" in pruned:
                                    # 格式 1: rec_texts 数组
                                    all_texts.extend(pruned["rec_texts"])
                                elif isinstance(pruned, list):
                                    # 格式 2: prunedResult 直接是结果数组
                                    for item in pruned:
                                        if "text" in item:
                                            all_texts.append(item["text"])
                                        elif "rec_text" in item:
                                            all_texts.append(item["rec_text"])
                else:
                    # VL 模型使用 layoutParsingResults
                    if "layoutParsingResults" in result:
                        for res in result["layoutParsingResults"]:
                            if "markdown" in res and "text" in res["markdown"]:
                                all_texts.append(res["markdown"]["text"])

            if all_texts:
                return '\n'.join(all_texts)

            return "未识别到文字"

        except requests.exceptions.Timeout:
            return "请求超时，请检查网络连接"
        except requests.exceptions.RequestException as e:
            return f"网络请求错误: {str(e)}"
        except Exception as e:
            print(e)
            return f"OCR识别出错: {str(e)}"

    # 保留兼容性方法
    @staticmethod
    def convert_qimage_to_array(image):
        """PyQt6 最安全 QImage → numpy 数组（永无扭曲/报错）"""

        # 强制转成标准格式
        image = image.convertToFormat(QImage.Format.Format_RGB888)

        h = image.height()
        w = image.width()
        stride = image.bytesPerLine()

        # 🚀 唯一 100% 安全的取数据方式（解决 size=1 所有报错）
        ptr = image.bits()
        ptr.setsize(sys.maxsize)  # 关键！强制解锁内存限制

        # 构造数组
        arr = np.ndarray((h, stride // 3, 3), np.uint8, buffer=ptr)
        arr = arr[:, :w, :].copy()  # 裁剪 + 复制，避免内存失效

        return arr

    def recognize_from_array(self, image_arr):
        """从 numpy 数组识别文字（保留兼容性）"""
        # 将 numpy 数组转换为图片字节流

        image = Image.fromarray(np.uint8(image_arr))
        byte_stream = BytesIO()
        image.save(byte_stream, format="PNG")
        return self.recognize_from_bytes(byte_stream.getvalue())
