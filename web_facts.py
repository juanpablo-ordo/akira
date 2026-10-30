"""Akira web research: multi-source search + current-fact verification.

The local assistant must not treat Wikipedia as its search engine.  Search is
performed across public web indexes first, diversified by domain, and Wikipedia
is only a secondary fallback/reference.  Current political/public-office facts
prefer official primary sources plus an independent corroborating source.
"""
from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
from network_tls import https_context
from network_diagnostics import guarded_open
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from language_normalization import understood

UA = "Akira/7.3 (+local research; multi-source factual verification)"
_WEB_POOL=ThreadPoolExecutor(max_workers=8,thread_name_prefix='AkiraFactSearch')


def _collect_searches(jobs,timeout,direct_fast=False):
    futures={_WEB_POOL.submit(fn,query,timeout):name for name,fn,query in jobs}
    rows=[];errors=[]
    try:
        for future in as_completed(futures,timeout=max(.05,min(10,float(timeout)+.3))):
            try:
                received=future.result();rows.extend(received)
                if direct_fast and any(row.get('engine')=='official-direct' and row.get('text') for row in received):break
            except Exception as error:errors.append(futures[future]+':'+type(error).__name__)
    except TimeoutError:errors.append('search:total_time_budget')
    finally:
        for future in futures:
            if not future.done():future.cancel()
    return rows,errors

_CURRENT_PATTERNS = (
    r"\bactual(?:es|mente)?\b", r"\bhoy\b", r"\bahora\b", r"\búltim[oa]s?\b", r"\bultimo?s?\b",
    r"\bpresidente\b", r"\bprimer ministro\b", r"\bministro\b", r"\bceo\b", r"\bgobernador\b",
    r"\bquién es\b", r"\bquien es\b", r"\bprecio\b", r"\bcotiza\b", r"\bnoticias?\b",
    r"\belecciones?\b", r"\b202[5-9]\b", r"\besta semana\b", r"\beste mes\b",
    r"\b(lanz[oó]|lanzar|lanzaron|lanzado|lanzamiento|estren[oó]|taquillera|recaudaci[oó]n|acaba|reci[eé]n|reciente|nuev[oa]s?|anunci[oó])\b",
)

_STOP = {
    "que","qué","quien","quién","cual","cuál","como","cómo","donde","dónde","cuando","cuándo",
    "el","la","los","las","un","una","unos","unas","de","del","en","a","al","por","para","con",
    "es","son","fue","era","actual","actualmente","hoy","este","esta","estos","estas","me","dame",
    "puedes","podrias","podrías","otras","otros","fuentes","informacion","información"
}

_OFFICIAL_SUFFIXES = (
    ".gob.gt", ".gov.gt", ".gov", ".gov.uk", ".gc.ca", ".gouv.fr", ".bund.de",
    ".europa.eu", ".un.org", ".who.int", ".worldbank.org", ".imf.org"
)
_OFFICIAL_HOSTS = {
    "agn.gt",
    "hbo.com", "max.com", "press.wbd.com", "wbd.com", "warnerbros.com", "dc.com", "dcstudios.com",
    "netflix.com", "about.netflix.com", "thewaltdisneycompany.com", "marvel.com", "news.xbox.com",
    "playstation.com", "blog.playstation.com", "apple.com", "google.com", "blog.google", "openai.com",
    "nvidia.com", "investor.nvidia.com", "coinglass.com"
}
_REPUTABLE_HOSTS = {
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "cnn.com", "nytimes.com", "washingtonpost.com",
    "theguardian.com", "bloomberg.com", "ft.com", "forbes.com", "cnbc.com", "npr.org",
    "the-numbers.com", "boxofficemojo.com", "variety.com", "deadline.com", "hollywoodreporter.com",
    "ign.com", "theverge.com", "gamespot.com", "polygon.com",
}


def needs_web_verification(message: str) -> bool:
    m = understood(message).lower()
    return any(re.search(p, m, flags=re.I) for p in _CURRENT_PATTERNS)


def _get_json(url: str, timeout: float = 7.0):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with guarded_open(urllib.request.urlopen,req, timeout=timeout, context=https_context()) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _host(url: str) -> str:
    try:
        return (urllib.parse.urlparse(str(url)).hostname or "").lower().removeprefix("www.")
    except Exception:
        return ""


def _is_official(url: str) -> bool:
    host = _host(url)
    return bool(host and (host in _OFFICIAL_HOSTS or any(host.endswith('.'+h) for h in _OFFICIAL_HOSTS)
                          or any(host == s.lstrip(".") or host.endswith(s) for s in _OFFICIAL_SUFFIXES)))


def _is_wikipedia(url: str) -> bool:
    return "wikipedia.org" in _host(url)


def _terms(query: str):
    return [x for x in re.findall(r"[^\W_]{3,}", str(query).lower(), flags=re.UNICODE) if x not in _STOP]


def _relevance(query: str, row: dict) -> float:
    text=(str(row.get("title") or "")+" "+str(row.get("text") or "")).lower()
    ts=_terms(understood(query))
    if not ts:return 0.5
    hit=sum(1 for t in set(ts) if t in text)
    return hit/max(1,len(set(ts)))


def _wiki(query: str, lang: str = "es", timeout: float = 7.0):
    base = f"https://{lang}.wikipedia.org/w/api.php"
    qs = urllib.parse.urlencode({
        "action": "query", "list": "search", "srsearch": query,
        "format": "json", "utf8": 1, "srlimit": 3,
    })
    data = _get_json(base + "?" + qs, timeout)
    out = []
    for row in ((data.get("query") or {}).get("search") or [])[:3]:
        title = str(row.get("title") or "").strip()
        if not title:continue
        qs2 = urllib.parse.urlencode({
            "action": "query", "prop": "extracts|info", "titles": title,
            "exintro": 1, "explaintext": 1, "inprop": "url", "format": "json", "utf8": 1,
        })
        detail = _get_json(base + "?" + qs2, timeout)
        pages = ((detail.get("query") or {}).get("pages") or {})
        for p in pages.values():
            extract = re.sub(r"\s+", " ", str(p.get("extract") or "")).strip()
            if extract:
                out.append({"title":str(p.get("title") or title),
                            "url":str(p.get("fullurl") or f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"),
                            "text":extract[:1800],"engine":"wikipedia","source_class":"encyclopedia"})
                break
    return out


def _duck(query: str, timeout: float = 7.0):
    url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode({
        "q": query, "format": "json", "no_html": 1, "skip_disambig": 1, "no_redirect": 1,
    })
    data = _get_json(url, timeout)
    rows=[]
    if data.get("AbstractText"):
        rows.append({"title":data.get("Heading") or "DuckDuckGo","url":data.get("AbstractURL") or "",
                     "text":data.get("AbstractText"),"engine":"duck-instant"})
    return rows


def _duck_html(query: str, timeout: float = 7.0):
    """DuckDuckGo HTML result snippets."""
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with guarded_open(urllib.request.urlopen,req, timeout=timeout, context=https_context()) as r:
        raw = r.read(1_200_000).decode("utf-8", "replace")
    links = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', raw, flags=re.I|re.S)
    snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</(?:a|div)>', raw, flags=re.I|re.S)
    rows=[]
    for i,(href,title) in enumerate(links[:10]):
        href=html.unescape(href)
        m=re.search(r'uddg=([^&]+)',href)
        if m:href=urllib.parse.unquote(m.group(1))
        title=re.sub(r'<[^>]+>',' ',html.unescape(title)); title=re.sub(r'\s+',' ',title).strip()
        snippet=snippets[i] if i<len(snippets) else ''
        snippet=re.sub(r'<[^>]+>',' ',html.unescape(snippet)); snippet=re.sub(r'\s+',' ',snippet).strip()
        if title and href.startswith(('http://','https://')):
            rows.append({"title":title,"url":href,"text":snippet[:1600],"engine":"duck-html"})
    return rows


def _bing_rss(query: str, timeout: float = 7.0):
    """Public Bing RSS endpoint; no key required.  Used as a second index."""
    url="https://www.bing.com/search?"+urllib.parse.urlencode({"q":query,"format":"rss","setlang":"es"})
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/rss+xml,application/xml,text/xml"})
    with guarded_open(urllib.request.urlopen,req,timeout=timeout, context=https_context()) as r:
        raw=r.read(1_200_000)
    root=ET.fromstring(raw)
    rows=[]
    for item in root.findall('.//item')[:10]:
        title=(item.findtext('title') or '').strip(); link=(item.findtext('link') or '').strip()
        desc=re.sub(r'<[^>]+>',' ',html.unescape(item.findtext('description') or ''))
        desc=re.sub(r'\s+',' ',desc).strip()
        pub=(item.findtext('pubDate') or '').strip()
        if title and link.startswith(('http://','https://')):
            rows.append({"title":title,"url":link,"text":desc[:1600],"published":pub,"engine":"bing-rss"})
    return rows


def _google_news_rss(query: str, timeout: float = 7.0):
    """Google News RSS as an additional fresh index; no API key required."""
    params={"q":query,"hl":"es-419","gl":"US","ceid":"US:es-419"}
    url="https://news.google.com/rss/search?"+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/rss+xml,application/xml,text/xml"})
    with guarded_open(urllib.request.urlopen,req,timeout=timeout, context=https_context()) as r:
        raw=r.read(1_200_000)
    root=ET.fromstring(raw);rows=[]
    for item in root.findall('.//item')[:12]:
        title=(item.findtext('title') or '').strip();link=(item.findtext('link') or '').strip()
        desc=re.sub(r'<[^>]+>',' ',html.unescape(item.findtext('description') or ''))
        desc=re.sub(r'\s+',' ',desc).strip();pub=(item.findtext('pubDate') or '').strip()
        if title and link.startswith(('http://','https://')):
            rows.append({"title":title,"url":link,"text":desc[:1600],"published":pub,"publisher":(item.findtext("source") or "").strip(),"publisher_url":item.find("source").get("url", "") if item.find("source") is not None else "","read_status":"rss_excerpt","engine":"google-news-rss"})
    return rows


def _expanded_queries(query: str):
    q=' '.join(understood(query).split()).strip(); low=q.lower(); out=[q]
    year=str(datetime.now(timezone.utc).year)
    if re.search(r'president\w*',low) and 'guatemala' in low:
        out += [f'site:presidencia.gob.gt presidente Guatemala {year}', f'site:agn.gt presidente Guatemala {year}', f'presidente Guatemala {year} Reuters AP']
    elif 'xbox' in low:
        out += [f'site:news.xbox.com {q} {year}', f'site:gearsofwar.com {q} {year}' if 'gears' in low else f'{q} {year} Microsoft Xbox Wire']
    elif re.search(r'pel[ií]cula',low) and re.search(r'(exitosa|taquillera|recaud|box office)',low):
        out += [f'{year} worldwide box office highest grossing The Numbers Box Office Mojo', f'películas más taquilleras {year} Variety Deadline']
    elif re.search(r'(walter white|breaking bad|tuco)',low):
        out += [q+' Breaking Bad wiki fandom AMC scene', q+' chemistry compound scene']
    # Current queries get date-aware and verification-oriented variants.
    if needs_web_verification(q) and year not in q:
        out.append(q+' '+year)
        out.append(q+' '+year+' official announcement')
    if re.search(r'\b(?:dc|dc studios|hbo|max|warner)\b',low) and re.search(r'\b(?:serie|series|estren|lanz|show)\w*',low):
        out += [f'{q} {year} DC Studios Warner Bros official', f'{q} {year} Variety Deadline Hollywood Reporter']
    clean=[]
    for x in out:
        if x and x not in clean:clean.append(x)
    return clean[:5]


def _official_presidency(query,timeout):
    """Read the stable government root; the current holder is never hardcoded."""
    question=understood(query).lower()
    if 'guatemala' not in question or not re.search(r'\bpresidente\b',question):return []
    url='https://presidencia.gob.gt/'
    request=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'text/html'})
    with guarded_open(urllib.request.urlopen,request,timeout=timeout, context=https_context()) as response:
        final=response.geturl();host=_host(final)
        if host!='presidencia.gob.gt' and not host.endswith('.presidencia.gob.gt'):
            raise ValueError('La Presidencia redirigió fuera de su dominio oficial')
        raw=response.read(1_200_000).decode('utf-8','replace')
    raw=re.sub(r'<(?:script|style)\b[^>]*>[\s\S]*?</(?:script|style)>',' ',raw,flags=re.I)
    clean=lambda text:' '.join(re.sub(r'<[^>]*>',' ',html.unescape(text)).split())
    title=re.search(r'<title[^>]*>(.*?)</title>',raw,re.I|re.S)
    title=clean(title.group(1))[:220] if title else 'Presidencia de Guatemala'
    paragraphs=[clean(text) for text in re.findall(r'<(?:p|h[1-3])\b[^>]*>(.*?)</(?:p|h[1-3])>',raw,re.I|re.S)]
    paragraphs=[text for text in paragraphs if re.search(r'\b(?:presidente|presidencia|mandatario)\b',text,re.I)]
    text='\n'.join(paragraphs)[:4500]
    if not text or not re.search(r'\bpresidente\b',text,re.I):return []
    return [{'title':title,'url':final,'text':text,'engine':'official-direct',
             'source_class':'official','read_status':'official_page_excerpt','retrieved_at':datetime.now(timezone.utc).isoformat()}]


def _classify(row):
    url=str(row.get('url') or '')
    host=_host(url)
    if _is_official(url):return 'official'
    if _is_wikipedia(url):return 'encyclopedia'
    if any(host==h or host.endswith('.'+h) for h in _REPUTABLE_HOSTS):return 'reputable'
    return 'web'


def _rank(query,row,strict=False):
    rel=_relevance(query,row)
    cls=_classify(row)
    score=rel*100
    if cls=='official':score+=50
    elif cls=='reputable':score+=25
    elif cls=='encyclopedia':score-=20
    if str(row.get('published') or ''):score+=4
    if strict and cls=='official':score+=25
    return score


def _dedupe_diverse(query,rows,limit=8,strict=False):
    query=understood(query)
    office=bool(re.search(r'\b(?:presidente|ministro|gobernador|alcalde|primer ministro)\b',query,re.I))
    merged=[]; seen=set(); per_host={}
    for r in rows:
        url=str(r.get('url') or '').strip(); title=str(r.get('title') or '').strip()
        if not url or not title:continue
        key=url.split('#',1)[0].rstrip('/')
        if key in seen:continue
        seen.add(key)
        rr=dict(r); rr['source_class']=_classify(rr); rr['relevance']=round(_relevance(query,rr),3)
        # A country match alone does not answer who holds a public office.
        body=(title+' '+str(r.get('text') or '')).lower()
        if re.search(r'\bgears\b',query,re.I) and 'gears' not in body:continue
        if office and not re.search(r'\b(?:president\w*|mandatari\w*|ministro\w*|gobernador\w*|alcalde\w*)\b',body):continue
        if rr['relevance'] < (.35 if office or strict else .18) and len(_terms(query))>=2:continue
        merged.append(rr)
    merged.sort(key=lambda r:_rank(query,r,strict),reverse=True)
    out=[]
    # Domain diversity: no single publication should dominate the answer.
    for r in merged:
        h=_host(r.get('url'))
        max_per=2 if r.get('source_class')=='official' else 1
        if per_host.get(h,0)>=max_per:continue
        if r.get('source_class')=='encyclopedia' and any(x.get('source_class')!='encyclopedia' for x in out):
            if len(out)>=max(2,limit-1):continue
        per_host[h]=per_host.get(h,0)+1; out.append(r)
        if len(out)>=limit:break
    return out


def lookup_current_fact(query: str, timeout: float = 7.0, limit: int = 6):
    """Multi-index public search. Fresh questions never fall back to stale Wikipedia alone."""
    query=understood(query);queries=_expanded_queries(query)
    jobs=[]
    for q in queries:
        jobs.extend((('duckhtml',_duck_html,q),('bing',_bing_rss,q),('gnews',_google_news_rss,q)))
    jobs.append(('duckduckgo',_duck,query))
    rows,errors=_collect_searches(jobs,timeout)
    nonwiki=_dedupe_diverse(query,rows,max(limit,4),strict=False)
    # A question asking for the latest/current fact must fail closed rather than
    # confidently answering from an old encyclopedia page.
    if not nonwiki and not needs_web_verification(query):
        for lang in ('es','en'):
            try: rows.extend(_wiki(query,lang,timeout))
            except Exception as exc: errors.append(f'wikipedia-{lang}:{type(exc).__name__}')
            if len(rows)>=limit*3:break
    clean=_dedupe_diverse(query,rows,limit,strict=False)
    return {"query":query,"results":clean,"errors":errors,"source_count":len(clean),"fresh_required":needs_web_verification(query)}


def lookup_verified_current_fact(query: str, timeout: float = 6.5, limit: int = 4):
    """Stronger current-fact verification.

    Prefer a current-year official result plus an independent corroborator.  If a
    search engine omits the year in its snippet, allow a relevant official source
    rather than falsely claiming the fact is unverifiable. Wikipedia is excluded.
    """
    year=str(datetime.now(timezone.utc).year)
    query=understood(query);jobs=[('official-direct',_official_presidency,query)]
    for q in _expanded_queries(query):
        jobs.extend((('duckhtml',_duck_html,q if year in q else q+' '+year),('bing',_bing_rss,q)))
    rows,errors=_collect_searches(jobs,timeout,direct_fast=True)
    ranked=_dedupe_diverse(query,[r for r in rows if not _is_wikipedia(r.get('url',''))],max(10,limit*2),strict=True)
    official=[r for r in ranked if r.get('source_class')=='official']
    fresh_official=[r for r in official if year in (str(r.get('title',''))+' '+str(r.get('text',''))+' '+str(r.get('published','')))]
    independent=[r for r in ranked if r.get('source_class') in ('reputable','web') and r.get('relevance',0)>=0.22]
    selected=[]
    primary=(fresh_official or official)
    if primary:selected.append(primary[0])
    for r in independent:
        if _host(r.get('url')) not in {_host(x.get('url')) for x in selected}:
            selected.append(r)
        if len(selected)>=limit:break
    # If no independent corroborator was found, a second distinct official page is useful.
    if len(selected)<2:
        for r in primary[1:]:
            if r.get('url') not in {x.get('url') for x in selected}:selected.append(r)
            if len(selected)>=limit:break
    # No official result: accept multiple reputable independent sources, not one random page.
    if not selected and len([r for r in ranked if r.get('source_class')=='reputable'])>=2:
        selected=[r for r in ranked if r.get('source_class')=='reputable'][:limit]
    return {"query":query,"results":selected[:limit],"errors":errors,"verified":bool(selected),"source_count":len(selected)}


def format_context(result: dict) -> str:
    rows=result.get('results') or []
    if not rows:return ''
    parts=['VERIFICACIÓN WEB MULTIFUENTE (usa estos datos; si discrepan, dilo explícitamente):']
    for i,r in enumerate(rows,1):
        parts.append(f"[{i}] {r.get('title','Fuente')} ({r.get('source_class','web')})\n{r.get('text','')}\nURL: {r.get('url','')}")
    return '\n\n'.join(parts)
