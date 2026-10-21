"""Application-wide wallpaper. One owned decoder, one pending frame, no broker IO."""
from __future__ import annotations
import math,os,subprocess,sys,threading,time,tempfile
from collections import deque
from pathlib import Path
from PySide6.QtCore import Qt,QRectF,QPointF,QTimer,QSize
from PySide6.QtGui import QPainter,QColor,QLinearGradient,QPen,QPainterPath,QImage,QPixmap,QImageReader
from PySide6.QtWidgets import QWidget


class DecoderLimits:
    """Windows job limits apply exclusively to our FFmpeg child, never MT5/LLM."""
    def __init__(self,process,cpu,memory):
        self.handle=None;self.status={'cpu_hard_limit':False,'decoder_memory_hard_limit':False,'scope':'owned wallpaper decoder'}
        if os.name!='nt':return
        try:
            import ctypes as c
            from ctypes import wintypes as w
            class Basic(c.Structure):
                _fields_=[('PerProcessUserTimeLimit',c.c_longlong),('PerJobUserTimeLimit',c.c_longlong),('LimitFlags',w.DWORD),('MinimumWorkingSetSize',c.c_size_t),('MaximumWorkingSetSize',c.c_size_t),('ActiveProcessLimit',w.DWORD),('Affinity',c.c_size_t),('PriorityClass',w.DWORD),('SchedulingClass',w.DWORD)]
            class IO(c.Structure):_fields_=[(name,c.c_ulonglong) for name in ('ReadOperationCount','WriteOperationCount','OtherOperationCount','ReadTransferCount','WriteTransferCount','OtherTransferCount')]
            class Extended(c.Structure):_fields_=[('BasicLimitInformation',Basic),('IoInfo',IO),('ProcessMemoryLimit',c.c_size_t),('JobMemoryLimit',c.c_size_t),('PeakProcessMemoryUsed',c.c_size_t),('PeakJobMemoryUsed',c.c_size_t)]
            class Cpu(c.Structure):_fields_=[('ControlFlags',w.DWORD),('CpuRate',w.DWORD)]
            kernel=c.WinDLL('kernel32',use_last_error=True)
            kernel.CreateJobObjectW.argtypes=[c.c_void_p,w.LPCWSTR];kernel.CreateJobObjectW.restype=w.HANDLE
            kernel.SetInformationJobObject.argtypes=[w.HANDLE,c.c_int,c.c_void_p,w.DWORD];kernel.SetInformationJobObject.restype=w.BOOL
            kernel.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE];kernel.AssignProcessToJobObject.restype=w.BOOL
            kernel.CloseHandle.argtypes=[w.HANDLE];kernel.CloseHandle.restype=w.BOOL
            handle=kernel.CreateJobObjectW(None,None)
            if not handle:raise OSError(c.get_last_error(),'CreateJobObjectW')
            self.kernel=kernel;self.handle=handle
            info=Extended();info.BasicLimitInformation.LimitFlags=0x100|0x2000
            info.ProcessMemoryLimit=max(32,int(memory))*1024*1024
            memory_ok=bool(kernel.SetInformationJobObject(handle,9,c.byref(info),c.sizeof(info)))
            rate=Cpu(0x1|0x4,max(100,min(10000,int(cpu)*100)))
            cpu_ok=bool(kernel.SetInformationJobObject(handle,15,c.byref(rate),c.sizeof(rate)))
            if not kernel.AssignProcessToJobObject(handle,int(process._handle)):raise OSError(c.get_last_error(),'AssignProcessToJobObject')
            self.status.update(cpu_hard_limit=cpu_ok,decoder_memory_hard_limit=memory_ok,cpu_percent=int(cpu),decoder_memory_mb=int(memory))
        except (AttributeError,OSError,ValueError,TypeError) as error:
            self.status['limit_error']=str(error);self.close()
    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle);self.handle=None


def wait_decoder_exit(process,timeout):
    """Wait for the native exit even if Popen cached an exit code during stop.

    TerminateProcess is asynchronous. Only the owned process handle is waited
    on; no process-name lookup, taskkill or access to another application's IO.
    """
    if sys.platform=='win32':
        import ctypes as c
        from ctypes import wintypes as w
        kernel=c.WinDLL('kernel32',use_last_error=True)
        kernel.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD]
        kernel.WaitForSingleObject.restype=w.DWORD
        result=kernel.WaitForSingleObject(int(process._handle),max(0,int(timeout*1000)))
        if result==0x102:raise subprocess.TimeoutExpired(process.args,timeout)
        if result!=0:raise OSError(c.get_last_error(),'WaitForSingleObject for wallpaper decoder')
    return process.wait(timeout=timeout)


def release_decoder(process,timeout=3):
    """Reap our child and close its pipe/Windows handle before releasing media."""
    # The reader owns this call and has left its read loop. Release the pipe
    # first so a paused FFmpeg cannot remain blocked writing buffered frames.
    if process.stdout:process.stdout.close()
    if process.poll() is None:
        try:process.terminate()
        except ProcessLookupError:pass
    try:
        wait_decoder_exit(process,timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        wait_decoder_exit(process,timeout)
    # Keep the native handle valid until the real exit has been confirmed.
    handle=getattr(process,'_handle',None)
    if handle is not None:handle.Close()


def frame_geometry(size,config):
    quality=max(.2,min(1,int(config.get('quality',70))/100))
    width=max(160,int(size[0]*quality));height=max(90,int(size[1]*quality))
    # Three RGB/RGBA buffers have an enforceable allocation budget, separate
    # from FFmpeg's process memory. Never buffer the entire video.
    budget=max(8,int(config.get('max_memory_mb',128)))*1024*1024
    factor=min(1,math.sqrt(budget*.5/max(1,width*height*12)))
    width=max(2,int(width*factor)//2*2);height=max(2,int(height*factor)//2*2)
    return width,height


def video_filter(size,config):
    width,height=size;filters=[]
    crop=[max(0,min(45,float(config.get('crop_'+k,0)))) for k in ('left','top','right','bottom')]
    left,top,right,bottom=crop
    if any(crop):filters.append(f'crop=iw*{1-(left+right)/100:.4f}:ih*{1-(top+bottom)/100:.4f}:iw*{left/100:.4f}:ih*{top/100:.4f}')
    rotation=float(config.get('rotation',0))%360
    if rotation==90:filters.append('transpose=1')
    elif rotation==180:filters.extend(('hflip','vflip'))
    elif rotation==270:filters.append('transpose=2')
    elif rotation:filters.append(f'rotate={math.radians(rotation):.7f}:ow=rotw({math.radians(rotation):.7f}):oh=roth({math.radians(rotation):.7f}):c=0x020c18')
    fps=max(1,min(144,int(config.get('fps',24))))
    filters.append('fps='+str(fps))
    fit=config.get('fit','cover')
    if fit=='cover':
        fx=(100-max(-100,min(100,int(config.get('offset_x',0)))))/200
        fy=(100-max(-100,min(100,int(config.get('offset_y',0)))))/200
        filters.extend((f'scale={width}:{height}:force_original_aspect_ratio=increase',f'crop={width}:{height}:(iw-ow)*{fx:.4f}:(ih-oh)*{fy:.4f}'))
    elif fit=='contain':
        fx=(max(-100,min(100,int(config.get('offset_x',0))))+100)/200;fy=(max(-100,min(100,int(config.get('offset_y',0))))+100)/200
        filters.extend((f'scale={width}:{height}:force_original_aspect_ratio=decrease',f'pad={width}:{height}:(ow-iw)*{fx:.4f}:(oh-ih)*{fy:.4f}:color=0x020c18'))
    else:filters.append(f'scale={width}:{height}')
    zoom=max(.5,min(2,float(config.get('zoom',100))/100))
    if zoom>1:filters.extend((f'scale={round(width*zoom)//2*2}:{round(height*zoom)//2*2}',f'crop={width}:{height}'))
    elif zoom<1:filters.extend((f'scale={max(2,round(width*zoom)//2*2)}:{max(2,round(height*zoom)//2*2)}',f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x020c18'))
    return ','.join(filters)


class WallpaperWorker:
    def __init__(self,config,size):
        self.config=dict(config);self.size=frame_geometry(size,config)
        self.frames=deque(maxlen=1);self.stop_event=threading.Event();self.visible=threading.Event();self.visible.set()
        self.finished=threading.Event();self.shutdown_error=None
        self.process=None;self.lock=threading.Lock();self.status={'state':'STARTING','frames_buffered':0,'gpu_decode':False}
        self.thread=threading.Thread(target=self.run,name='AkiraWallpaper',daemon=True)
    def start(self):self.thread.start()
    def stop(self):
        self.stop_event.set();self.visible.set()
        with self.lock:process=self.process
        if process and process.poll() is None:
            try:process.terminate()
            except OSError:pass
    def close(self,timeout=7):
        """Final shutdown barrier; stop() alone stays nonblocking for resizing."""
        self.stop()
        if self.thread.ident is not None:self.thread.join(timeout)
        if self.thread.is_alive():raise TimeoutError('El decodificador del fondo no terminó de cerrar.')
        if self.shutdown_error:raise RuntimeError('No se pudo liberar el fondo: '+self.shutdown_error)
    def run(self):
        limits=None;process=None;errors=None
        try:
            import imageio_ffmpeg
            width,height=self.size;fps=max(1,min(144,int(self.config.get('fps',24))))
            flags=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'BELOW_NORMAL_PRIORITY_CLASS',0)
            command=[imageio_ffmpeg.get_ffmpeg_exe(),'-nostdin','-v','error','-threads','1',*(['-stream_loop','-1'] if self.config.get('loop',True) else []),*(['-ignore_loop','1'] if Path(self.config['file']).suffix.lower()=='.gif' else []),'-i',str(self.config['file']),'-an','-sn','-vf',video_filter(self.size,self.config),'-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1']
            errors=tempfile.TemporaryFile()
            if not self.stop_event.is_set():
                process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=errors,creationflags=flags,close_fds=True)
                with self.lock:self.process=process
                limits=DecoderLimits(process,self.config.get('max_cpu_percent',10),self.config.get('max_memory_mb',128))
                self.status.update(pid=process.pid,**limits.status,frame_size=list(self.size),frame_bytes=width*height*3)
                if self.stop_event.is_set():return
                try:
                    import psutil
                    meter=psutil.Process(process.pid);meter.cpu_percent()
                except Exception:meter=None
                count=width*height*3;next_frame=time.monotonic();last_meter=0;delay=1/fps
                while not self.stop_event.is_set():
                    if not self.visible.wait(.25):continue
                    data=bytearray()
                    while len(data)<count and not self.stop_event.is_set():
                        chunk=process.stdout.read(count-len(data))
                        if not chunk:break
                        data.extend(chunk)
                    if len(data)!=count:
                        if not self.stop_event.is_set():
                            errors.seek(0);detail=errors.read(2000).decode('utf-8','replace')
                            if not detail and not self.config.get('loop',True):self.status['state']='ENDED';break
                            raise RuntimeError(detail or 'No se pudo decodificar el fondo')
                        break
                    self.frames.append((bytes(data),width,height));now=time.monotonic()
                    self.status.update(state='PLAYING',frames_buffered=len(self.frames),last_frame=now,effective_fps=round(1/delay,1))
                    if meter and now-last_meter>=1:
                        last_meter=now
                        try:
                            cpu=meter.cpu_percent()/max(1,os.cpu_count() or 1);rss=meter.memory_info().rss/1048576
                            self.status.update(cpu_percent_measured=round(cpu,2),decoder_ram_mb=round(rss,1))
                            # Outside Windows, allocation is hard-bounded and
                            # decoder CPU is adapted, explicitly labelled soft.
                            if not self.status['cpu_hard_limit']:
                                delay=min(1,max(1/fps,delay*1.25)) if cpu>self.config.get('max_cpu_percent',10) else max(1/fps,delay*.98)
                            if not self.status['decoder_memory_hard_limit'] and rss>self.config.get('max_memory_mb',128):
                                raise MemoryError('El decodificador superó el presupuesto. Reduce calidad o amplía su memoria.')
                        except (ProcessLookupError,OSError):pass
                    next_frame=max(next_frame+delay,now)
                    if self.stop_event.wait(max(0,next_frame-time.monotonic())):break
        except Exception as error:
            if not self.stop_event.is_set():self.status.update(state='ERROR',error=str(error)[:500])
        finally:
            try:
                if process:release_decoder(process)
            except Exception as error:
                self.shutdown_error=type(error).__name__+': '+str(error)
                self.status.update(state='ERROR',error=self.shutdown_error)
            finally:
                if limits:limits.close()
                if errors:errors.close()
                if self.stop_event.is_set():self.frames.clear()
                if self.stop_event.is_set() and self.shutdown_error is None:self.status['state']='STOPPED'
                self.finished.set()


class BackgroundSurface(QWidget):
    """Every main page is a transparent child of this one compositor."""
    def __init__(self,parent=None):
        super().__init__(parent);self.config={};self.worker=None;self.frame=QImage();self.image=QImage();self._default=QPixmap()
        self.accent='#00ddff';self.secondary='#ff2585';self._cache_size=None
        self._generation=0;self._ready_image=None;self.media_status={};self.style={};self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self._tick=QTimer(self);self._tick.setInterval(33);self._tick.timeout.connect(self.advance)
        self._resize=QTimer(self);self._resize.setSingleShot(True);self._resize.setInterval(180);self._resize.timeout.connect(self.restart)
    def configure(self,config,accent='#00ddff',secondary='#ff2585',style=None):
        changed=dict(config)!=self.config
        self.config=dict(config);self.accent=accent;self.secondary=secondary;self.style=dict(style or {});self._cache_size=None
        if changed:self.restart()
        else:self.update()
    def restart(self):
        if self.worker:
            self.worker.stop()
            # Retain ownership until the old reader and its native child have
            # finished; rapid resizes must not start overlapping decoders.
            if self.worker.thread.is_alive():self._resize.start(16);return
            if self.worker.shutdown_error:
                self.media_status=dict(self.worker.status);self._tick.stop();return
            self.worker=None
        self._resize.stop()
        self._generation+=1;generation=self._generation;self._ready_image=None
        self.frame=QImage();self.image=QImage();self._tick.stop();self.media_status={}
        if self.config.get('enabled') and (self.config.get('kind') in ('video','gif') or Path(self.config.get('file','')).suffix.lower()=='.gif') and Path(self.config.get('file','')).is_file():
            config=dict(self.config);hz=max(1,round(self.screen().refreshRate() or 60));config['fps']=min(hz,int(config.get('fps',30))) if config.get('vsync',True) else int(config.get('fps',30))
            self.worker=WallpaperWorker(config,(max(320,round(self.width()*self.devicePixelRatioF())),max(240,round(self.height()*self.devicePixelRatioF()))));self.worker.start();self._tick.setInterval(max(7,round(1000/config['fps'])));self._tick.start()
        elif self.config.get('enabled') and self.config.get('kind')=='image':
            config=dict(self.config);size=frame_geometry((max(320,round(self.width()*self.devicePixelRatioF())),max(240,round(self.height()*self.devicePixelRatioF()))),config)
            def load():
                reader=QImageReader(config.get('file',''));reader.setAutoTransform(True)
                original=reader.size()
                if original.isValid():reader.setScaledSize(original.scaled(QSize(*size),Qt.AspectRatioMode.KeepAspectRatio))
                image=reader.read()
                if generation==self._generation:self._ready_image=(generation,image,reader.errorString() if image.isNull() else '')
            threading.Thread(target=load,name='AkiraWallpaperImage',daemon=True).start();self._tick.start()
        self.update()
    def advance(self):
        if self._ready_image is not None:
            generation,image,error=self._ready_image;self._ready_image=None
            if generation==self._generation:
                self.image=image;self.media_status={'state':'ERROR','error':error} if error else {'state':'IMAGE','buffer_bytes':image.sizeInBytes()};self.update()
            if not self.worker:self._tick.stop()
        if not self.worker:return
        if self.worker.status.get('state')=='ERROR':self._tick.stop();self.update();return
        if self.isVisible() and not self.window().isMinimized():
            self.worker.visible.set()
            try:pending=self.worker.frames.pop()
            except IndexError:pending=None
            if pending:
                data,width,height=pending;self.frame=QImage(data,width,height,width*3,QImage.Format.Format_RGB888).copy();self.update()
        else:self.worker.visible.clear()
        if self.worker.status.get('state')=='ENDED' and not self.worker.frames:self._tick.stop()
    def resizeEvent(self,event):
        self._cache_size=None
        if self.worker or self.config.get('enabled') and self.config.get('kind')=='image':self._resize.start()
        super().resizeEvent(event)
    def paintEvent(self,event):
        from studio_theme import palette_for
        colors=palette_for(self.style);background=QColor(colors['BG']);panel=QColor(colors['PANEL']);glow=max(0,min(100,int(self.style.get('glow',65))))
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);rect=QRectF(self.rect());p.fillRect(rect,background)
        if self._cache_size!=self.size():
            self._cache_size=self.size();self._default=QPixmap(self.size());self._default.fill(background);g=QPainter(self._default)
            gradient=QLinearGradient(0,0,self.width(),self.height());gradient.setColorAt(0,background.darker(170));gradient.setColorAt(.6,panel.darker(140));gradient.setColorAt(1,background);g.fillRect(self.rect(),gradient)
            for index,color in enumerate((self.accent,self.secondary)):
                pen=QColor(color);pen.setAlpha(round(glow*1.5));g.setPen(QPen(pen,.7+glow/150));path=QPainterPath()
                for x in range(0,self.width()+8,8):
                    y=self.height()*.94+math.sin(x/90+index*1.5)*20+math.sin(x/210)*18
                    if x==0:path.moveTo(x,y)
                    else:path.lineTo(x,y)
                g.drawPath(path)
            texture=self.style.get('panel_texture','Neon grid');line=QColor(colors['LINE']);line.setAlpha(60);g.setPen(QPen(line,.5))
            if texture=='Neon grid':
                for x in range(-self.height(),self.width(),100):g.drawLine(x,0,x+self.height(),self.height())
            elif texture=='Carbon':
                line.setAlpha(20);g.setPen(QPen(line,2))
                for y in range(0,self.height(),7):g.drawLine(0,y,self.width(),y)
            g.end()
        p.drawPixmap(0,0,self._default)
        image=self.frame if not self.frame.isNull() else self.image
        if not image.isNull():
            p.save();p.setOpacity(max(0,min(1,self.config.get('opacity',30)/100)))
            if not self.frame.isNull():p.drawImage(rect,image)
            else:
                # QImage is decoded/scaled by a worker; painting only transforms
                # the existing image in C++, without reopening or PIL-resizing it.
                w,h=image.width(),image.height();left,top,right,bottom=[self.config.get('crop_'+k,0)/100 for k in ('left','top','right','bottom')]
                source=QRectF(w*left,h*top,w*(1-left-right),h*(1-top-bottom));rotation=float(self.config.get('rotation',0))%360
                angle=math.radians(rotation);sw=abs(source.width()*math.cos(angle))+abs(source.height()*math.sin(angle));sh=abs(source.height()*math.cos(angle))+abs(source.width()*math.sin(angle))
                fit=self.config.get('fit','cover')
                if fit=='stretch':sx,sy=rect.width()/max(1,sw),rect.height()/max(1,sh)
                else:sx=sy=(max if fit=='cover' else min)(rect.width()/max(1,sw),rect.height()/max(1,sh))
                zoom=float(self.config.get('zoom',100))/100;sx*=zoom;sy*=zoom
                dx=abs(sw*sx-rect.width())*self.config.get('offset_x',0)/200;dy=abs(sh*sy-rect.height())*self.config.get('offset_y',0)/200
                p.setClipRect(rect);p.translate(rect.center()+QPointF(dx,dy));p.rotate(rotation)
                target=QRectF(-source.width()*sx/2,-source.height()*sy/2,source.width()*sx,source.height()*sy)
                p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform,self.config.get('quality',70)>=60);p.drawImage(target,image,source)
            p.restore()
    def stop(self):
        self._generation+=1;self._tick.stop();self._resize.stop()
        if self.worker:self.worker.close();self.worker=None
