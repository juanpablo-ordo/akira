"""Native, high-DPI Studio components. Painting never enters the broker actor."""
from __future__ import annotations
import math,time
from functools import lru_cache
from collections import OrderedDict
from pathlib import Path
from PySide6.QtCore import Qt,QRectF,QPointF,QTimer,QSize,QVariantAnimation
from PySide6.QtGui import QColor,QPainter,QPen,QLinearGradient,QPainterPath,QPixmap,QImage,QFont,QIcon
from PySide6.QtWidgets import QWidget,QFrame,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QSizePolicy,QCheckBox,QStyledItemDelegate

INK={'bg':'#020c18','panel':'#041426','line':'#164762','cyan':'#00ddff','pink':'#ff2585','green':'#00e8b5','amber':'#ffc548','text':'#e8f3ff','muted':'#80acc9'}

@lru_cache(maxsize=160)
def icon(name,color='#00ddff',size=22):
    pix=QPixmap(size*2,size*2);pix.fill(Qt.GlobalColor.transparent)
    p=QPainter(pix);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.scale(size/24*2,size/24*2)
    p.setPen(QPen(QColor(color),1.6,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin));p.setBrush(Qt.BrushStyle.NoBrush)
    if name=='bitcoin':
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#f7931a'));p.drawEllipse(QRectF(1,1,22,22));p.setPen(QPen(QColor('#fff4d9'),1.5));p.setFont(QFont('Rajdhani',17,QFont.Weight.Bold));p.drawText(QRectF(1,-1,22,25),Qt.AlignmentFlag.AlignCenter,'B');p.drawLine(10,3,10,6);p.drawLine(13,3,13,6);p.drawLine(10,18,10,21);p.drawLine(13,18,13,21)
    elif name=='gold':
        p.setPen(QPen(QColor('#f6c34c'),1));p.setBrush(QColor('#e6a624'))
        for x,y in ((8,2),(2,12),(13,12)):p.drawPolygon([QPointF(x+2,y),QPointF(x+8,y),QPointF(x+10,y+8),QPointF(x,y+8)])
        p.setPen(QPen(QColor('#fff2ad'),1));p.drawLine(11,4,15,4);p.drawLine(5,14,9,14);p.drawLine(16,14,20,14)
    elif name in ('chart','trading','analysis'):
        for x,h in ((5,8),(11,15),(17,11)):p.drawRoundedRect(QRectF(x,21-h,3,h),.7,.7)
    elif name in ('wallet','account'):
        p.drawRoundedRect(QRectF(3,6,18,15),2,2);p.drawPolyline([QPointF(4,6),QPointF(15,2),QPointF(17,6)])
        p.drawRoundedRect(QRectF(15,11,7,5),1,1);p.drawPoint(18,13)
    elif name in ('pending','report','file'):
        p.drawPolyline([QPointF(6,2),QPointF(15,2),QPointF(20,7),QPointF(20,22),QPointF(5,22),QPointF(5,2)])
        p.drawPolyline([QPointF(15,2),QPointF(15,8),QPointF(20,8)])
        for y in (12,16,19):p.drawLine(8,y,16,y)
    elif name=='eye':
        p.drawEllipse(QRectF(2,6,20,12));p.drawEllipse(QRectF(9,9,6,6))
    elif name=='phone':
        p.drawPolyline([QPointF(4,3),QPointF(8,2),QPointF(10,7),QPointF(7,10),QPointF(14,17),QPointF(17,14),QPointF(22,17),QPointF(21,21),QPointF(17,22),QPointF(9,17),QPointF(3,9),QPointF(4,3)])
    elif name=='chat':
        p.drawRoundedRect(QRectF(2,3,20,15),5,5);p.drawPolyline([QPointF(7,18),QPointF(5,22),QPointF(13,18)])
    elif name=='sources':
        p.drawEllipse(QRectF(10,8,4,4));p.drawLine(12,12,7,22);p.drawLine(12,12,17,22)
        p.drawArc(QRectF(6,4,12,12),-65*16,310*16);p.drawArc(QRectF(2,0,20,20),-65*16,310*16)
    elif name=='terminal':
        p.drawRoundedRect(QRectF(2,3,20,16),2,2);p.drawLine(8,22,16,22);p.drawLine(12,19,12,22)
        p.drawPolyline([QPointF(5,7),QPointF(8,10),QPointF(5,13)]);p.drawLine(11,13,16,13)
    elif name=='bell':
        p.drawArc(QRectF(6,3,12,15),0,180*16);p.drawPolyline([QPointF(6,10),QPointF(5,17),QPointF(3,19),QPointF(21,19),QPointF(19,17),QPointF(18,10)])
        p.drawArc(QRectF(10,19,4,4),180*16,180*16)
    elif name=='shield':
        p.drawPolygon([QPointF(12,2),QPointF(21,6),QPointF(19,16),QPointF(12,22),QPointF(5,16),QPointF(3,6)])
        p.drawPolyline([QPointF(8,12),QPointF(11,15),QPointF(16,9)])
    elif name=='bolt':p.drawPolygon([QPointF(13,1),QPointF(4,13),QPointF(11,13),QPointF(9,23),QPointF(21,9),QPointF(13,9)])
    elif name=='layers':
        for y in (3,8,13):p.drawPolyline([QPointF(2,y+5),QPointF(12,y),QPointF(22,y+5),QPointF(12,y+10),QPointF(2,y+5)])
    elif name=='refresh':
        p.drawArc(QRectF(3,3,18,18),35*16,285*16);p.drawPolyline([QPointF(21,2),QPointF(21,8),QPointF(15,8)])
    elif name=='clock':p.drawEllipse(QRectF(2,2,20,20));p.drawLine(12,5,12,12);p.drawLine(12,12,17,15)
    elif name=='send':p.drawPolygon([QPointF(2,3),QPointF(22,12),QPointF(2,21),QPointF(6,12)]);p.drawLine(6,12,22,12)
    elif name=='settings':
        p.drawEllipse(QRectF(7,7,10,10));p.drawEllipse(QRectF(10,10,4,4))
        for a in range(0,360,45):
            r=math.radians(a);p.drawLine(QPointF(12+8*math.cos(r),12+8*math.sin(r)),QPointF(12+11*math.cos(r),12+11*math.sin(r)))
    else:p.drawEllipse(QRectF(3,3,18,18));p.drawLine(12,7,12,13);p.drawPoint(12,17)
    p.end();pix.setDevicePixelRatio(2);return QIcon(pix)

def label(text='',role='body',color=None):
    w=QLabel(str(text));w.setProperty('role',role);w.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    if color:w.setStyleSheet('color:'+color+';background:transparent;border:0;')
    return w

def button(text,callback=None,kind='',glyph=None):
    w=QPushButton(str(text));w.setProperty('kind',kind);w.setCursor(Qt.CursorShape.PointingHandCursor)
    w.setMinimumHeight(35)
    if callback:w.clicked.connect(callback)
    if glyph:w.setIcon(icon(glyph,'#e8f3ff' if kind=='primary' else INK['cyan']));w.setIconSize(QSize(20,20))
    return w

class Toggle(QCheckBox):
    """Native accessible checkbox with an unambiguous moving switch thumb."""
    def sizeHint(self):return QSize(48,26)
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r=QRectF(self.width()-44,3,42,21);p.setPen(QPen(QColor(INK['cyan'] if self.isChecked() else '#29627c'),1));p.setBrush(QColor(INK['cyan'] if self.isChecked() else '#102c40'));p.drawRoundedRect(r,10,10)
        p.setBrush(QColor('#ffffff' if self.isEnabled() else '#71828b'));p.setPen(Qt.PenStyle.NoPen);p.drawEllipse(QRectF(r.left()+(23 if self.isChecked() else 3),r.top()+3,15,15))
        if self.hasFocus():p.setPen(QPen(QColor(INK['cyan']),1,Qt.PenStyle.DotLine));p.setBrush(Qt.BrushStyle.NoBrush);p.drawRoundedRect(r.adjusted(-2,-2,2,2),11,11)
    def hitButton(self,pos):return self.rect().contains(pos)

class Card(QFrame):
    def __init__(self,title='',glyph='',accent='',parent=None):
        super().__init__(parent);self.setObjectName('card');self.setProperty('accent',accent)
        self.setMinimumWidth(0);self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        self.body=QVBoxLayout(self);self.body.setContentsMargins(13,11,13,12);self.body.setSpacing(9)
        self.heading=QHBoxLayout();self.heading.setSpacing(9)
        if glyph:
            self.symbol=QLabel();self.symbol.setPixmap(icon(glyph,accent or INK['cyan']).pixmap(24,24));self.heading.addWidget(self.symbol)
        self.title=label(title,'cardTitle');self.heading.addWidget(self.title,1);self.body.addLayout(self.heading)
    def paintEvent(self,event):
        super().paintEvent(event);p=QPainter(self);p.setPen(QPen(QColor(self.property('accent') or INK['cyan']),1));p.drawLine(10,0,36,0)

class Metric(Card):
    def __init__(self,title,glyph,color=INK['cyan']):
        super().__init__('',accent=color);self.body.setSpacing(1);self.body.setContentsMargins(13,10,13,10)
        self.title.hide();self.body.removeItem(self.heading)
        line=QHBoxLayout();line.setSpacing(12);self.body.addLayout(line)
        self.metric_color=color;self.symbol=QLabel();self.symbol.setFixedWidth(40);self.symbol.setAlignment(Qt.AlignmentFlag.AlignCenter);self.symbol.setPixmap(icon(glyph,color,32).pixmap(32,32));line.addWidget(self.symbol)
        values=QVBoxLayout();values.setSpacing(1);self.name_label=label(title,'metricName');self.name_row=QHBoxLayout();self.name_row.addWidget(self.name_label,1);values.addLayout(self.name_row)
        self.value=label('—','metric',color);values.addWidget(self.value)
        self.caption=label('','muted');values.addWidget(self.caption);line.addLayout(values,1)
        self.value.setWordWrap(True);self.caption.setWordWrap(True)
        self.setMinimumHeight(90);self.setMaximumHeight(115)
    def set_action(self,title,callback):
        action=QPushButton(title);action.setMinimumHeight(20);action.setMaximumHeight(22);action.setCursor(Qt.CursorShape.PointingHandCursor)
        action.setStyleSheet('font-size:11px;padding:1px 5px;');action.clicked.connect(callback);self.name_row.addWidget(action);return action
    def paintEvent(self,event):
        super().paintEvent(event);p=QPainter(self);color=QColor(self.metric_color);color.setAlpha(24);gradient=QLinearGradient(0,0,65,self.height());gradient.setColorAt(0,color);color.setAlpha(1);gradient.setColorAt(1,color);p.fillRect(QRectF(1,1,62,max(1,self.height()-2)),gradient);p.setPen(QPen(QColor('#15415d'),.7));p.drawLine(64,1,64,self.height()-1)

class DataTable(QTableWidget):
    """Stable keys; changing ages must not reorder rows or lose the selection."""
    def __init__(self,columns):
        super().__init__(0,len(columns));self.columns=columns;self.rows={};self.keys=[]
        self.setHorizontalHeaderLabels(columns);self.verticalHeader().hide();self.verticalHeader().setDefaultSectionSize(38)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.setShowGrid(False)
        self.setAlternatingRowColors(True);self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel);self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        for index in range(len(columns)):self.setColumnWidth(index,110 if index else 130)

    def selected_key(self):
        row=self.currentRow();return self.keys[row] if 0<=row<len(self.keys) else None

    def update_rows(self,rows):
        # rows = (stable id, displayed cells, original data). No reset/model rebuild.
        rows=list(rows)
        signature=tuple((str(key),tuple(str(v if v is not None else '—') for v in values[:len(self.columns)])) for key,values,_ in rows)
        # Refresh the underlying facts even if their displayed text is the same.
        # Toggling updates off/on unconditionally repainted entire transparent
        # tables on Windows, including tables without any changed cell.
        if signature==getattr(self,'_display_signature',None):
            self.rows={str(key):data for key,_,data in rows};return
        self._display_signature=signature
        selected=self.selected_key();scroll=self.verticalScrollBar().value();top=self.rowAt(0);anchor=self.keys[top] if 0<=top<len(self.keys) else None;offset=self.rowViewportPosition(top) if top>=0 else 0;self.blockSignals(True)
        desired=[str(k) for k,_,_ in rows]
        structural=desired!=self.keys
        if structural:self.setUpdatesEnabled(False)
        try:
            if desired!=self.keys:
                self.setRowCount(len(rows));self.keys=desired
            self.rows={str(key):data for key,_,data in rows}
            for row,(_,values,_) in enumerate(rows):
                for col,value in enumerate(values[:len(self.columns)]):
                    text=str(value if value is not None else '—');item=self.item(row,col)
                    if item is None:item=QTableWidgetItem();self.setItem(row,col,item)
                    if item.text()!=text:
                        item.setText(text);item.setToolTip(text)
                        color=INK['green'] if text.startswith(('BUY','DISPONIBLE','CONFIRMAD','ACTIVO')) else INK['pink'] if text.startswith(('SELL','ERROR','RECHAZ','DESCART')) else INK['amber'] if text.startswith(('ESPER','EN REVIS','SOLO','NO DISPON')) else INK['text']
                        if item.foreground().color()!=QColor(color):item.setForeground(QColor(color))
            if selected in self.keys and self.currentRow()!=self.keys.index(selected):self.selectRow(self.keys.index(selected))
            if anchor in self.keys:
                scroll=self.verticalScrollBar().value()+self.rowViewportPosition(self.keys.index(anchor))-offset
            self.verticalScrollBar().setValue(scroll)
        finally:
            if structural:self.setUpdatesEnabled(True)
            self.blockSignals(False)

class ActivityDelegate(QStyledItemDelegate):
    def paint(self,painter,option,index):
        painter.save();rect=QRectF(option.rect);text=str(index.data() or '')
        colors={'SISTEMA':INK['green'],'TRADING':INK['cyan'],'ANÁLISIS':INK['cyan'],'AVISO':INK['amber'],'ERROR':INK['pink']}
        category=str(index.siblingAtColumn(1).data() or 'SISTEMA');color=QColor(colors.get(category,INK['cyan']))
        if index.row()%2:painter.fillRect(rect,QColor(0,26,44,120))
        if self.parent().currentRow()==index.row():painter.fillRect(rect,QColor(0,90,130,80))
        painter.setPen(QPen(QColor('#12364e'),.7));painter.drawLine(rect.bottomLeft(),rect.bottomRight());painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if index.column()==0:
            painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(color);painter.drawEllipse(QPointF(rect.left()+13,rect.center().y()),5,5);painter.setPen(QColor(INK['muted']));painter.drawText(rect.adjusted(28,0,0,0),Qt.AlignmentFlag.AlignVCenter,text)
        elif index.column()==1:
            badge=rect.adjusted(5,20,-7,-20);painter.setPen(QPen(color,1));painter.setBrush(QColor(color.red(),color.green(),color.blue(),30));painter.drawRoundedRect(badge,4,4);painter.drawText(badge,Qt.AlignmentFlag.AlignCenter,text)
        else:
            title,_,body=text.partition('\n');painter.setPen(QColor(INK['text']));font=QFont(option.font);font.setBold(True);painter.setFont(font);painter.drawText(rect.adjusted(8,9,-12,-30),Qt.AlignmentFlag.AlignVCenter,painter.fontMetrics().elidedText(title,Qt.TextElideMode.ElideRight,max(10,int(rect.width()-22))))
            font.setBold(False);painter.setFont(font);painter.setPen(QColor(INK['muted']));painter.drawText(rect.adjusted(8,32,-12,-7),Qt.AlignmentFlag.AlignVCenter,painter.fontMetrics().elidedText(body,Qt.TextElideMode.ElideRight,max(10,int(rect.width()-22))))
        painter.restore()


class ActivityFeed(DataTable):
    """Two readable lines per event, sharing the stable-scroll table contract."""
    def __init__(self):
        super().__init__(['Hora','Tipo','Actividad']);self.horizontalHeader().hide();self.verticalHeader().setDefaultSectionSize(68);self.setColumnWidth(0,102);self.setColumnWidth(1,110);self.setItemDelegate(ActivityDelegate(self))
    def update_rows(self,rows):
        presented=[]
        for key,values,data in rows:
            stamp,module,state,detail=values
            words=(module+' '+state).upper()
            kind='ERROR' if any(w in words for w in ('ERROR','FALLO')) else 'AVISO' if any(w in words for w in ('AVISO','RECHAZ','BLOQUE')) else 'ANÁLISIS' if any(w in words for w in ('ANÁLISIS','REVISION','REVISIÓN','MAPA','DATOS')) else 'TRADING' if any(w in words for w in ('PENDIENT','RUNNER','ORDEN','BTC','XAU','MT5')) else 'SISTEMA'
            presented.append((key,[stamp,kind,state+'\n'+detail],data))
        super().update_rows(presented)


class CandleChart(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.bars=[];self.levels={};self._signature=None;self._valid_bars=[]
        self._chart_cache=None;self._cache_geometry=None;self._raster_count=0
        self._resize_plot=QTimer(self);self._resize_plot.setSingleShot(True);self._resize_plot.setInterval(120);self._resize_plot.timeout.connect(self.finish_resize)
        self.setMinimumHeight(95);self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
    def set_data(self,bars,levels=None):
        bars=list(bars or [])[-95:];valid=[]
        for row in bars:
            try:
                values=tuple(float(row.get(key,0)) for key in ('open','high','low','close'))
                if all(math.isfinite(v) for v in values) and values[1]>=values[2]:valid.append(values)
            except (AttributeError,ValueError,TypeError):continue
        levels=dict(levels or {});signature=(tuple(valid),tuple(sorted(levels.items())))
        self.bars=bars
        if signature!=self._signature:
            self._valid_bars=valid;self.levels=levels;self._signature=signature;self._chart_cache=None;self.update()
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'_resize_plot') and self._chart_cache is not None:self._resize_plot.start()
    def finish_resize(self):
        self._cache_geometry=None;self.update()
    def paintEvent(self,event):
        ratio=self.devicePixelRatioF();geometry=(self.width(),self.height(),ratio)
        if self._chart_cache is None or (geometry!=self._cache_geometry and not self._resize_plot.isActive()):
            image=QPixmap(max(1,math.ceil(self.width()*ratio)),max(1,math.ceil(self.height()*ratio)))
            image.setDevicePixelRatio(ratio);image.fill(Qt.GlobalColor.transparent)
            painter=QPainter(image);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._draw_plot(painter);painter.end();self._chart_cache=image;self._cache_geometry=geometry;self._raster_count+=1
        painter=QPainter(self)
        if self._cache_geometry==geometry:painter.drawPixmap(0,0,self._chart_cache)
        else:painter.drawPixmap(QRectF(self.rect()),self._chart_cache,QRectF(self._chart_cache.rect()))
    def _draw_plot(self,p):
        rect=QRectF(self.rect()).adjusted(3,3,-64,-18);p.setPen(QPen(QColor('#10334b'),.6))
        for n in range(1,5):p.drawLine(QPointF(rect.left(),rect.top()+n*rect.height()/5),QPointF(rect.right(),rect.top()+n*rect.height()/5))
        valid=self._valid_bars
        if not valid:p.setPen(QColor(INK['muted']));p.drawText(rect,Qt.AlignmentFlag.AlignCenter,'—');return
        low=min(b[2] for b in valid);high=max(b[1] for b in valid);span=max(1e-8,high-low);low-=span*.08;span*=1.16
        y=lambda value:rect.bottom()-(value-low)/span*rect.height();step=rect.width()/max(1,len(valid))
        for index,(op,hi,lo,cl) in enumerate(valid):
            x=rect.left()+(index+.5)*step;color=QColor(INK['green'] if cl>=op else INK['pink']);p.setPen(QPen(color,1));p.setBrush(color)
            p.drawLine(QPointF(x,y(lo)),QPointF(x,y(hi)));p.drawRect(QRectF(x-step*.29,min(y(op),y(cl)),max(1,step*.58),max(1,abs(y(op)-y(cl)))))
        p.setFont(QFont('Rajdhani',10));p.setPen(QColor(INK['muted']))
        for index in range(5):
            value=low+span*index/4;p.drawText(QRectF(rect.right()+6,y(value)-8,58,18),f'{value:,.2f}')
        for name,value in self.levels.items():
            if isinstance(value,(int,float)) and low<=value<=low+span:
                color=INK['pink'] if name=='SL' else INK['green'] if name=='TP' else INK['cyan'];p.setPen(QPen(QColor(color),1,Qt.PenStyle.DashLine))
                p.drawLine(QPointF(rect.left(),y(value)),QPointF(rect.right(),y(value)))

class AvatarWidget(QWidget):
    def __init__(self,director,asset_root,reduce_motion=False,parent=None):
        super().__init__(parent);self.director=director;self.asset_root=Path(asset_root);self.reduce_motion=reduce_motion
        self.cache=OrderedDict();self.offset=QPointF();self.setMouseTracking(True);self.setMinimumSize(140,100)
        self._previous=None;self._current=None;self._fade_value=1.;self._fade=QVariantAnimation(self);self._fade.setStartValue(0.);self._fade.setEndValue(1.);self._fade.setDuration(140);self._fade.valueChanged.connect(self.fade_changed)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        from avatar_animation import MotionSprites
        self.states=MotionSprites(self.asset_root);self._stable_dimensions=None
        self._rescale=QTimer(self);self._rescale.setSingleShot(True);self._rescale.setInterval(120);self._rescale.timeout.connect(self.finish_resize);director.subscribe(self)
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'_rescale') and self._current is not None:self._rescale.start()
    def finish_resize(self):
        self._stable_dimensions=None;self.update()
    def winfo_ismapped(self):return self.isVisible()
    def fade_changed(self,value):self._fade_value=float(value);self.update()
    def _receive(self,name,entry,animate=False):
        # A crossfade superimposes two differently shaped faces. Swap cleanly;
        # blink and speaking use their own short sequences instead.
        self._fade.stop();self._previous=None
        self.name=name;self.selected=entry;self._fade_value=1.
        if self._previous is not None:self._fade.start()
        self.update()
    def _draw(self):self.update()
    def _loading_ring(self):self.update()
    def mouseMoveEvent(self,event):
        if not self.reduce_motion:
            self.offset=QPointF(max(-4,min(4,(event.position().x()-self.width()/2)/18)),max(-3,min(3,(event.position().y()-self.height()/2)/20)));self.update()
    def leaveEvent(self,event):self.offset=QPointF();self.update()
    def paintEvent(self,event):
        if not hasattr(self,'selected'):return
        available=(max(1,self.width()-10),max(1,self.height()-10))
        # Dragging a window scales the cached pixmap in Qt. Decode/resample once
        # after the final resize, rather than running PIL for every resize event.
        if self._stable_dimensions is None:self._stable_dimensions=available
        width,height=self._stable_dimensions;director=self.director
        state=None;entry=self.selected
        if hasattr(entry,'path') and director.blink_frame is not None:
            blink=next((item for item in director.catalog.entries if item.state=='blink'),None)
            if blink:entry=blink
        if not hasattr(self.selected,'path'):
            state=15 if not director.online and not director.interacting else 14 if self.name=='waking' else int(time.monotonic()*8)%8 if director.loading else 10 if director.blink_frame==2 else 9 if director.blink_frame is not None else 12 if self.name=='listening' else (13 if director.mouth_level>.035 else 8) if director.playing else 8 if self.name in ('idle','waiting') else None
        key=(entry.id if state is None else 'motion',state,width,height)
        if key not in self.cache:
            image=self.states.image(state,width,height) if state is not None else director.catalog.image(entry,width,height)
            image=image.convert('RGBA')
            qimage=QImage(image.tobytes(),image.width,image.height,image.width*4,QImage.Format.Format_RGBA8888).copy()
            self.cache[key]=QPixmap.fromImage(qimage)
            while len(self.cache)>12:self.cache.popitem(last=False)
        self._current=self.cache[key];p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._previous is not None and self._fade.state()==QVariantAnimation.State.Running:
            p.setOpacity(1-self._fade_value);p.drawPixmap(QPointF(5,5)+self.offset,self._previous);p.setOpacity(self._fade_value)
        ratio=min(available[0]/self._current.width(),available[1]/self._current.height());width=self._current.width()*ratio;height=self._current.height()*ratio
        target=QRectF((self.width()-width)/2+self.offset.x(),(self.height()-height)/2+self.offset.y(),width,height)
        p.drawPixmap(target,self._current,QRectF(self._current.rect()));p.setOpacity(1)


class SignalWave(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.setFixedHeight(32);self.saving=False;self.timer=QTimer(self);self.timer.setInterval(125);self.timer.timeout.connect(self.tick)
    def set_saving(self,saving):
        self.saving=bool(saving)
        if self.saving or not self.isVisible():self.timer.stop()
        else:self.timer.start()
        self.update()
    def showEvent(self,event):
        super().showEvent(event);self.set_saving(self.saving)
    def hideEvent(self,event):
        self.timer.stop();super().hideEvent(event)
    def tick(self):
        if not self.isVisible() or self.window().isMinimized():return
        if getattr(self.window(),'_visual_studio',{}).get('reduce_motion') or getattr(self.window(),'_render_interval',.4)>=.9:return
        self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);t=0 if self.saving else time.monotonic();style=getattr(self.window(),'_visual_studio',{})
        for j,color in enumerate((style.get('accent','#00ddff'),style.get('secondary','#ff2585'))):
            p.setPen(QPen(QColor(color),1));path=QPainterPath()
            for x in range(0,self.width()+4,4):
                y=16+math.sin(x/24+t*(1 if j else -1)+j)*7*math.sin(x/max(1,self.width())*math.pi)
                if x==0:path.moveTo(x,y)
                else:path.lineTo(x,y)
            p.drawPath(path)
