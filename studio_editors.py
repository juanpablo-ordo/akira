"""Native visible selectors and mouse editing for appearance preferences."""
import copy
from pathlib import Path
from PySide6.QtCore import Qt,Signal,QRectF,QPointF,QTimer
from PySide6.QtGui import QColor,QPainter,QPen,QFont,QImage
from PySide6.QtWidgets import QComboBox,QPushButton,QColorDialog,QDialog,QVBoxLayout,QHBoxLayout,QLabel,QFontComboBox,QSpinBox,QCheckBox,QDialogButtonBox,QWidget
class ChoiceBox(QComboBox):
    def wheelEvent(self,event):event.ignore()
    def paintEvent(self,event):
        super().paintEvent(event);p=QPainter(self);p.setPen(QPen(QColor('#00ddff'),2));x=self.width()-14;y=self.height()/2;p.drawPolyline([QPointF(x-4,y-2),QPointF(x,y+2),QPointF(x+4,y-2)])
class ColorButton(QPushButton):
    valueChanged=Signal(str)
    def __init__(self,value='',parent=None):
        super().__init__(parent);self._value=value;self.clicked.connect(self.choose);self.refresh()
    def value(self):return self._value
    def setValue(self,value):
        if self._value!=value:self._value=value;self.refresh();self.valueChanged.emit(value)
    def refresh(self):self.setText('Elegir color' if not self._value else 'Cambiar color');self.setStyleSheet('border-left:22px solid '+(self._value or '#123348')+';padding:6px 12px;')
    def choose(self):
        c=QColorDialog.getColor(QColor(self._value or '#061022'),self,'Elige un tono')
        if c.isValid():self.setValue(c.name())
class FontEditor(QDialog):
    def __init__(self,parent,studio,import_callback=None):
        super().__init__(parent);self.setWindowTitle('Tipografía');self.resize(620,410);box=QVBoxLayout(self);note=QLabel('Selecciona fuente, tamaño y negrita. Puedes importar archivos .ttf o .otf de tu computadora.');note.setWordWrap(True);box.addWidget(note)
        self.family=QFontComboBox();self.family.setCurrentText(studio.get('font','Rajdhani'));box.addWidget(self.family);self.size=QSpinBox();self.size.setRange(60,160);self.size.setSuffix(' %');self.size.setValue(int(studio.get('font_scale',100)));box.addWidget(self.size)
        self.bold=QCheckBox('Negrita');self.bold.setChecked(bool(studio.get('font_bold')));box.addWidget(self.bold);self.preview=QLabel('Akira · Tu espacio de análisis\nBitcoin, oro y conversación.');self.preview.setMinimumHeight(110);box.addWidget(self.preview)
        for signal in (self.family.currentTextChanged,self.size.valueChanged,self.bold.toggled):signal.connect(self.refresh)
        if import_callback:b=QPushButton('Importar fuente TTF / OTF');b.clicked.connect(import_callback);box.addWidget(b)
        footer=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);footer.accepted.connect(self.accept);footer.rejected.connect(self.reject);box.addWidget(footer);self.refresh()
    def refresh(self,*args):f=QFont(self.family.currentText(),round(16*self.size.value()/100));f.setBold(self.bold.isChecked());self.preview.setFont(f)
    def values(self):return {'font':self.family.currentText(),'font_scale':self.size.value(),'font_bold':self.bold.isChecked()}
class CropCanvas(QWidget):
    def __init__(self,config,parent=None):
        super().__init__(parent);self.config=config;self.image=QImage();self.setMinimumSize(460,280);self.setMouseTracking(True);self.drag=None
    def crop_rect(self):
        w,h=self.width(),self.height();c=self.config;return QRectF(w*c.get('crop_left',0)/100,h*c.get('crop_top',0)/100,w*(1-(c.get('crop_left',0)+c.get('crop_right',0))/100),h*(1-(c.get('crop_top',0)+c.get('crop_bottom',0))/100))
    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),QColor('#020c18'));p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if not self.image.isNull():
            c=self.config;r=QRectF(self.rect());p.save();p.translate(r.center()+QPointF(c.get('offset_x',0)*self.width()/200,c.get('offset_y',0)*self.height()/200));p.rotate(float(c.get('rotation',0)));sx=r.width()/self.image.width();sy=r.height()/self.image.height()
            if c.get('fit')!='stretch':sx=sy=(min if c.get('fit')=='contain' else max)(sx,sy)
            z=c.get('zoom',100)/100;p.scale(sx*z,sy*z);p.drawImage(QPointF(-self.image.width()/2,-self.image.height()/2),self.image);p.restore()
        r=self.crop_rect();p.setPen(QPen(QColor('#00ddff'),2));p.drawRect(r)
        for x in (r.left(),r.right()):
            for y in (r.top(),r.bottom()):p.fillRect(QRectF(x-6,y-6,12,12),QColor('#00ddff'))
    def mousePressEvent(self,event):
        pos=event.position();r=self.crop_rect();self.drag='pan';self.previous=pos
        for name,point in [('lt',r.topLeft()),('rt',r.topRight()),('lb',r.bottomLeft()),('rb',r.bottomRight())]:
            if (point-pos).manhattanLength()<22:self.drag=name;break
    def mouseMoveEvent(self,event):
        if not self.drag:return
        delta=event.position()-self.previous;self.previous=event.position();c=self.config
        if self.drag=='pan':c['offset_x']=round(max(-100,min(100,c.get('offset_x',0)+delta.x()*200/self.width())));c['offset_y']=round(max(-100,min(100,c.get('offset_y',0)+delta.y()*200/self.height())))
        else:
            for token,key,amount in [('l','left',delta.x()/self.width()*100),('r','right',-delta.x()/self.width()*100),('t','top',delta.y()/self.height()*100),('b','bottom',-delta.y()/self.height()*100)]:
                if token in self.drag:c['crop_'+key]=max(0,min(45,c.get('crop_'+key,0)+amount))
        self.update()
    def mouseReleaseEvent(self,event):self.drag=None
    def wheelEvent(self,event):
        key='rotation' if event.modifiers()&Qt.KeyboardModifier.ControlModifier else 'zoom';lo,hi=(-360,360) if key=='rotation' else (50,200);self.config[key]=max(lo,min(hi,self.config.get(key,0 if key=='rotation' else 100)+event.angleDelta().y()/120*5));self.update();event.accept()
class WallpaperEditor(QDialog):
    def __init__(self,parent,config):
        super().__init__(parent);self.config=copy.deepcopy(config);self.setWindowTitle('Ajustar fondo con el ratón');self.resize(860,590);box=QVBoxLayout(self);self.worker=None
        note=QLabel('Arrastra para mover; arrastra las esquinas celestes para recortar. Rueda: acercar. Ctrl + rueda: girar. Los ajustes también se aplican a vídeos y GIF.');note.setWordWrap(True);box.addWidget(note);self.canvas=CropCanvas(self.config);box.addWidget(self.canvas,1);row=QHBoxLayout()
        for title,fn in [('Encajar',lambda:self.fit('contain')),('Rellenar',lambda:self.fit('cover')),('Estirar',lambda:self.fit('stretch')),('Girar 90°',self.rotate),('Restablecer',self.reset)]:b=QPushButton(title);b.clicked.connect(fn);row.addWidget(b)
        box.addLayout(row);footer=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);footer.accepted.connect(self.accept);footer.rejected.connect(self.reject);box.addWidget(footer);self.timer=QTimer(self);self.timer.setInterval(80);self.timer.timeout.connect(self.advance)
        if config.get('kind') in ('video','gif') or Path(config.get('file','')).suffix.lower()=='.gif':
            from studio_background import WallpaperWorker
            c={**config,'fps':12,'loop':True,'fit':'contain','rotation':0,'offset_x':0,'offset_y':0,'zoom':100,'quality':70,**{'crop_'+k:0 for k in ('left','right','top','bottom')}};self.worker=WallpaperWorker(c,(640,360));self.worker.start();self.timer.start()
        else:self.canvas.image=QImage(config.get('file',''))
        self.finished.connect(self.stop)
    def fit(self,value):self.config['fit']=value;self.canvas.update()
    def rotate(self):self.config['rotation']=(self.config.get('rotation',0)+90)%360;self.canvas.update()
    def reset(self):self.config.update(rotation=0,offset_x=0,offset_y=0,zoom=100,crop_left=0,crop_right=0,crop_top=0,crop_bottom=0,fit='cover');self.canvas.update()
    def advance(self):
        try:data,w,h=self.worker.frames.pop()
        except IndexError:return
        self.canvas.image=QImage(data,w,h,w*3,QImage.Format.Format_RGB888).copy();self.canvas.update()
    def stop(self,*args):
        self.timer.stop()
        if self.worker:self.worker.close();self.worker=None
