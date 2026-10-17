"""Localize the persistent shell without translating live financial values.

The original Spanish UI remains the default. Source-reported technical errors,
prices, tickets and human-authored text are never machine-translated implicitly.
"""
HEADINGS={
 'en':('TRADING','PENDING ORDERS','ACCOUNT & OPERATIONS','ANALYSIS','RESEARCH & SOURCES','CHAT WITH AKIRA','SETTINGS','TERMINAL & REPORTS'),
 'pt':('NEGOCIAÇÃO','ORDENS PENDENTES','CONTA E OPERAÇÕES','ANÁLISE','FONTES E PESQUISA','CHAT COM AKIRA','CONFIGURAÇÕES','TERMINAL E RELATÓRIOS'),
 'fr':('TRADING','ORDRES EN ATTENTE','COMPTE ET OPÉRATIONS','ANALYSE','SOURCES ET RECHERCHE','DISCUSSION AVEC AKIRA','PARAMÈTRES','TERMINAL ET RAPPORTS'),
 'de':('HANDEL','PENDING-ORDERS','KONTO UND TRANSAKTIONEN','ANALYSE','QUELLEN UND RECHERCHE','CHAT MIT AKIRA','EINSTELLUNGEN','TERMINAL UND BERICHTE'),
 'it':('TRADING','ORDINI PENDENTI','CONTO E OPERAZIONI','ANALISI','FONTI E RICERCA','CHAT CON AKIRA','IMPOSTAZIONI','TERMINALE E REPORT'),
 'ja':('取引','指値・逆指値注文','口座と取引','分析','情報源と調査','AKIRAとのチャット','設定','ターミナルとレポート'),
 'zh':('交易','挂单','账户与交易','分析','来源与研究','与AKIRA聊天','设置','终端与报告'),
 'ko':('거래','예약 주문','계정과 거래','분석','자료와 조사','AKIRA 채팅','설정','터미널과 보고서'),
 'ar':('التداول','الأوامر المعلقة','الحساب والعمليات','التحليل','المصادر والبحث','المحادثة مع أكيرا','الإعدادات','الطرفية والتقارير'),
}
SUBTITLES={
 'en':('Control, context and BTC/gold charts','Ideas, broker-confirmed orders and validity','Orders, positions and owners','Structure, indicators and decision evidence','Status and freshness of sources actually read','Conversation, memory, files and voice','Settings applied safely without editing files','Logs, diagnostics and PDF/Excel reports'),
 'pt':('Controle, contexto e gráficos de BTC e ouro','Ideias, ordens confirmadas e validade','Ordens, posições e responsáveis','Estrutura, indicadores e motivos','Estado e atualização das fontes lidas','Conversas, memória, arquivos e voz','Preferências aplicadas com segurança','Registros e relatórios PDF/Excel'),
 'fr':('Contrôle, contexte et graphiques BTC/or','Idées, ordres confirmés et validité','Ordres, positions et propriétaires','Structure, indicateurs et justifications','État et fraîcheur des sources consultées','Conversation, mémoire, fichiers et voix','Paramètres appliqués en toute sécurité','Journaux et rapports PDF/Excel'),
 'de':('Kontrolle, Kontext und BTC-/Gold-Charts','Ideen, bestätigte Aufträge und Gültigkeit','Aufträge, Positionen und Eigentümer','Struktur, Indikatoren und Belege','Status und Aktualität gelesener Quellen','Chat, Gedächtnis, Dateien und Stimme','Einstellungen sicher übernehmen','Protokolle und PDF-/Excel-Berichte'),
 'it':('Controllo, contesto e grafici BTC/oro','Idee, ordini confermati e validità','Ordini, posizioni e proprietari','Struttura, indicatori e motivazioni','Stato e aggiornamento delle fonti lette','Conversazione, memoria, file e voce','Impostazioni applicate in sicurezza','Registri e report PDF/Excel'),
 'ja':('BTCと金の状況とチャート','候補、確認済み注文、有効期限','注文、ポジション、所有者','市場構造、指標、判断根拠','取得した情報の状態と鮮度','会話、記憶、ファイル、音声','安全に適用する設定','ログとPDF/Excelレポート'),
 'zh':('BTC与黄金的控制、背景和图表','候选方案、已确认订单及有效期','订单、持仓和所有者','结构、指标和决策依据','已读取来源的状态与时效','对话、记忆、文件与语音','安全应用设置','日志与PDF/Excel报告'),
 'ko':('BTC 및 금 시황과 차트','후보, 확인된 주문 및 유효기간','주문, 포지션 및 소유자','구조, 지표 및 결정 근거','수집한 자료의 상태와 최신성','대화, 기억, 파일 및 음성','안전하게 적용하는 설정','로그 및 PDF/Excel 보고서'),
 'ar':('السياق والرسوم البيانية للبيتكوين والذهب','الأفكار والأوامر المؤكدة وصلاحيتها','الأوامر والمراكز والملكية','البنية والمؤشرات وأسباب القرار','حالة المصادر المقروءة وحداثتها','المحادثة والذاكرة والملفات والصوت','تطبيق الإعدادات بأمان','السجلات وتقارير PDF وExcel'),
}

def heading(locale,index,spanish):
    return HEADINGS.get(locale,())[index] if locale in HEADINGS and 0<=index<8 else spanish[index]

def subtitle(locale,index,spanish):
    return SUBTITLES.get(locale,())[index] if locale in SUBTITLES and 0<=index<8 else spanish[index]
