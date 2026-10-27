"""Wrapping controls and wheel routing for the native desktop."""
from PySide6.QtCore import QCoreApplication,QEvent,QObject,QPointF,QRect,QSize,Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QAbstractScrollArea,QAbstractSpinBox,QComboBox,QLayout,QScrollArea,QSlider,QWidget


class FlowLayout(QLayout):
    def __init__(self,spacing=8):
        super().__init__();self.items=[];self.setContentsMargins(0,0,0,0);self.setSpacing(spacing)
    def addItem(self,item):self.items.append(item)
    def count(self):return len(self.items)
    def itemAt(self,index):return self.items[index] if 0<=index<len(self.items) else None
    def takeAt(self,index):return self.items.pop(index) if 0<=index<len(self.items) else None
    def expandingDirections(self):return Qt.Orientation(0)
    def hasHeightForWidth(self):return True
    def heightForWidth(self,width):return self.arrange(QRect(0,0,width,0),True)
    def sizeHint(self):return self.minimumSize()
    def minimumSize(self):
        size=QSize()
        for item in self.items:
            if not item.isEmpty():size=size.expandedTo(item.minimumSize())
        left,top,right,bottom=self.getContentsMargins();return size+QSize(left+right,top+bottom)
    def setGeometry(self,rect):super().setGeometry(rect);self.arrange(rect)
    def arrange(self,rect,measure=False):
        left,top,right,bottom=self.getContentsMargins();area=rect.adjusted(left,top,-right,-bottom)
        x=area.x();y=area.y();height=0;spacing=self.spacing()
        for item in self.items:
            if item.isEmpty():continue
            size=item.sizeHint();width=min(size.width(),max(0,area.width()))
            if x>area.x() and x+width>area.right()+1:x=area.x();y+=height+spacing;height=0
            if not measure:item.setGeometry(QRect(x,y,width,size.height()))
            x+=width+spacing;height=max(height,size.height())
        return y+height-rect.y()+bottom


class WheelGuard(QObject):
    """Scroll the page over controls; retain inner scrolling until its boundary."""
    def __init__(self,window):super().__init__(window);self.window=window;self.forwarding=False
    def watch(self,root):
        for widget in root.findChildren(QWidget):
            if isinstance(widget,(QAbstractSpinBox,QComboBox,QSlider)):widget.installEventFilter(self)
            elif isinstance(widget,QAbstractScrollArea):widget.viewport().installEventFilter(self)
    @staticmethod
    def can_scroll(area,event):
        delta=event.pixelDelta() if not event.pixelDelta().isNull() else event.angleDelta()
        horizontal=bool(delta.x()) and not delta.y();amount=delta.x() if horizontal else delta.y()
        bar=area.horizontalScrollBar() if horizontal else area.verticalScrollBar()
        return bool(amount and bar.maximum()>bar.minimum() and (bar.value()>bar.minimum() if amount>0 else bar.value()<bar.maximum()))
    def send(self,area,event):
        if self.forwarding or not self.can_scroll(area,event):return False
        if isinstance(area,QScrollArea) and not event.pixelDelta().isNull():
            delta=event.pixelDelta();horizontal=bool(delta.x()) and not delta.y()
            bar=area.horizontalScrollBar() if horizontal else area.verticalScrollBar()
            bar.setValue(bar.value()-(delta.x() if horizontal else delta.y()));event.accept();return True
        viewport=area.viewport();position=QPointF(viewport.mapFromGlobal(event.globalPosition().toPoint()))
        forwarded=QWheelEvent(position,event.globalPosition(),event.pixelDelta(),event.angleDelta(),event.buttons(),event.modifiers(),event.phase(),event.inverted())
        self.forwarding=True
        try:QCoreApplication.sendEvent(viewport,forwarded)
        finally:self.forwarding=False
        event.accept();return True
    def eventFilter(self,watched,event):
        if event.type()!=QEvent.Type.Wheel or self.forwarding or not isinstance(watched,QWidget):return False
        if watched.window()!=self.window:return False
        control=isinstance(watched,(QAbstractSpinBox,QComboBox,QSlider));node=watched;first=True
        while node is not None:
            if isinstance(node,QAbstractScrollArea):
                if self.can_scroll(node,event):
                    if first and not control and not (isinstance(node,QScrollArea) and not event.pixelDelta().isNull()):return False
                    return self.send(node,event)
                first=False
            node=node.parentWidget()
        if control:event.accept();return True
        return False
