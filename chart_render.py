"""Native rendering of real closed bars, indicators and recorded order levels."""
from cyber_ui import PANEL,LINE,MUTED,TEXT,CYAN,PINK,GREEN,AMBER,BLUE,MONO,FONT
from chart_indicators import indicator_chart,finite_series

def render(canvas):
    data=canvas.data;canvas.delete('all');width=canvas.winfo_width();height=canvas.winfo_height()
    if width<100 or height<70:return
    if data.get('market_closed'):
        canvas.create_text(width/2,height/2-8,text='MERCADO CERRADO',fill=AMBER,font=(FONT,13,'bold'))
        canvas.create_text(width/2,height/2+17,text='Se reanuda con una cotización nueva de MT5',fill=MUTED,font=(FONT,9));return
    bars=data.get('bars') or []
    if not bars:
        canvas.create_text(width/2,height/2,text='ESPERANDO VELAS MT5',fill=MUTED,font=(FONT,11));return
    mode=data.get('indicator','Precio');tf=data.get('timeframe','M15')
    signature=(tf,len(bars),tuple((b['time'],b['close'],b['high'],b['low'],b.get('volume',0)) for b in bars))
    if signature!=getattr(canvas,'_indicator_signature',None):
        computed=indicator_chart(bars,tf)
        canvas._indicator_data=computed;canvas._indicator_signature=signature
    indicators=canvas._indicator_data;osc=mode in ('RSI','MACD','ADX','Volumen y estructura')
    left,right,top=10,max(50,width-85),32;bottom=max(top+15,height-16-(max(38,int(height*.27)) if osc else 0))
    low=min(b['low'] for b in bars);high=max(b['high'] for b in bars);span=max(.001,high-low);low-=span*.09;high+=span*.09
    def y(value):return bottom-(value-low)/(high-low)*(bottom-top)
    dx=(right-left)/len(bars)
    def x(i):return left+(i+.5)*dx
    for n in range(4):
        price=low+(high-low)*n/3;yy=y(price);canvas.create_line(left,yy,right,yy,fill=LINE,dash=(2,4));canvas.create_text(right+5,yy,text=f'{price:,.2f}',anchor='w',fill=MUTED,font=(MONO,8))
    for i,b in enumerate(bars):
        color=GREEN if b['close']>=b['open'] else PINK;canvas.create_line(x(i),y(b['high']),x(i),y(b['low']),fill=color)
        a,z=sorted((y(b['open']),y(b['close'])));canvas.create_rectangle(x(i)-max(1,dx*.25),a,x(i)+max(1,dx*.25),max(a+1,z),fill=color,outline='')
    def line(values,color,converter=y):
        points=[]
        for i,value in enumerate(values):
            if value is not None:points.extend((x(i),converter(value)))
        if len(points)>=4:canvas.create_line(*points,fill=color,width=1)
    if mode=='Medias y Bollinger':
        for key,color in [('EMA 9',CYAN),('EMA 21',AMBER),('EMA 50',BLUE),('EMA 200',PINK),('Bollinger inferior',MUTED),('Bollinger superior',MUTED)]:
            values=indicators.get('series',{}).get(key,[]);line([v if v is not None and low<=v<=high else None for v in values],color)
    if mode=='Volumen y estructura':
        for group,color in [('lows',GREEN),('highs',PINK)]:
            for value,stamp in indicators.get(group,[])[-3:]:
                if low<=value<=high:canvas.create_line(left,y(value),right,y(value),fill=color,dash=(3,5))
        f=data.get('engine_frame') or {}
        for group,color in [('lows',GREEN),('highs',PINK)]:
            for value,stamp in indicators.get(group,[])[-2:]:
                zone=indicators.get('atr',0)*.12
                if low<=value<=high:canvas.create_rectangle(left,y(min(high,value+zone)),right,y(max(low,value-zone)),outline=color,fill='',dash=(2,5))
        for key,color in [('fib382',AMBER),('fib50',CYAN),('fib618',AMBER)]:
            value=f.get(key)
            if isinstance(value,(int,float)) and low<=value<=high:canvas.create_line(left,y(value),right,y(value),fill=color,dash=(1,5))
        structural=[]
        for key in ('bos','sweep'):
            if f.get(key) in (-1,1):structural.append(key.upper()+(' ↑' if f[key]==1 else ' ↓'))
        if structural:canvas.create_text(left+4,top+8,text=' · '.join(structural)+' · última vela cerrada',anchor='w',fill=AMBER,font=(FONT,8))
    if osc:
        start=bottom+15;end=height-15
        values=[b.get('volume',0) for b in bars] if mode=='Volumen y estructura' else indicators.get('series',{}).get(mode,[])
        usable=finite_series(values)
        lo,hi=(0,100) if mode in ('RSI','ADX') else (min(usable or [0]),max(usable or [1]));hi=max(hi,lo+1e-8)
        convert=lambda v:end-(v-lo)/(hi-lo)*max(1,end-start)
        canvas.create_line(left,start-7,right,start-7,fill=LINE)
        if mode=='Volumen y estructura':
            for i,value in enumerate(values):canvas.create_line(x(i),end,x(i),convert(value),fill=GREEN if bars[i]['close']>=bars[i]['open'] else PINK,width=max(1,dx*.45))
        else:line(values,CYAN,convert)
        for level in ((30,70) if mode=='RSI' else (25,) if mode=='ADX' else (0,) if mode=='MACD' and lo<=0<=hi else ()):
            canvas.create_line(left,convert(level),right,convert(level),fill=LINE,dash=(3,4))
        canvas.create_text(right+5,(start+end)/2,text=mode.replace('Volumen y estructura','Volumen'),anchor='w',fill=CYAN,font=(FONT,8))
    levels=[p for p in data.get('pending_book',[]) if p.get('confirmed')]
    proposals=[p for p in data.get('scenario_book',[]) if not p.get('confirmed')]
    selected=data.get('selected_key');proposals=sorted(proposals,key=lambda p:p.get('key')!=selected)[:1]
    for row in levels+proposals+data.get('runner_levels',[]):
        confirmed=row.get('confirmed') or row.get('kind')=='position';color=AMBER if confirmed else GREEN if row.get('side') in (1,'BUY') else PINK
        for key in ('entry','sl','tp'):
            value=row.get(key)
            if not isinstance(value,(int,float)) or not low<=value<=high:continue
            yy=y(value);canvas.create_line(left,yy,right,yy,fill=color,dash=(4,3) if key=='entry' else (2,5))
            canvas.create_text(left+3,yy-5,text=('#'+str(row.get('ticket')) if confirmed else 'PROPUESTA')+' '+key.upper(),anchor='w',fill=color,font=(MONO,8))
        if row.get('kind')=='position' and isinstance(row.get('entry'),(int,float)) and low<=row['entry']<=high:
            current=data.get('bid') or bars[-1]['close']
            if low<=current<=high:canvas.create_line(x(max(0,len(bars)-15)),y(row['entry']),x(len(bars)-1),y(current),fill=AMBER,width=2,dash=(3,3))
    quote=data.get('bid') or bars[-1]['close']
    if low<=quote<=high:canvas.create_line(left,y(quote),right,y(quote),fill=CYAN,dash=(4,4))
    frame=data.get('engine_frame') or {};title=tf+' · MT5 · '+mode
    if mode in ('RSI','MACD','ADX'):
        key={'RSI':'rsi','MACD':'macd','ADX':'adx'}[mode];value=frame.get(key)
        title+=' · motor '+(f'{value:.2f}' if isinstance(value,(int,float)) else 'sin dato')
    from datetime import datetime,timezone
    last=frame.get('last_bar') or bars[-1]['time']
    title+=' · '+datetime.fromtimestamp(last,timezone.utc).strftime('%H:%M UTC')
    canvas.create_text(left,12,text=title,anchor='w',fill=TEXT,font=(FONT,9))
    canvas.create_text(right,bottom+8,text='Curva: ventana de velas visible',anchor='e',fill=MUTED,font=(FONT,7))
