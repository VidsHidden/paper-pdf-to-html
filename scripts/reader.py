# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = [
#   "pymupdf==2.1", "pymupdf4llm==2.1", "pymupdf-layout==2.1",
#   "beautifulsoup4==4.15.0", "markdown-it-py==4.0.0", "playwright==1.65.2"
# ]
# ///
"""Build a portable English or English/Simplified Chinese paper reader."""
import argparse
from hashlib import sha256
from html import escape
from pathlib import Path
import re
import sys

from bs4 import BeautifulSoup, NavigableString, Tag

from translate import MARKER, cache_path, chrome_path, is_valid, read_translations, store, translate
from models import prepare as prepare_models
from api_translate import Config, translate_api

ASSETS=Path(__file__).resolve().parents[1]/'assets'
NODES='header h1,h2,h3,h4,h5,h6,p,figcaption,th,td,li'
TECH=re.compile(r'(?<![A-Za-z0-9])(?:\d+(?:[.,]\d+)*(?:[–-]\d+(?:\.\d+)?)?\s*(?:°C|[μµnmp]?[lLgMsV]|nm|μm|µm|kDa|rpm|mmHg|h|min|%)\b|\d+(?:\.\d+)?\s*%|[⁰¹²³⁴⁵⁶⁷⁸⁹]+[A-Z]|[A-Za-z][A-Za-z0-9_]*(?<=\d)[A-Za-z0-9_]*)(?![A-Za-z0-9\]])')
FIG=re.compile(r'(?:(Extended\s+Data|Supplementary|Supporting|扩展数据|补充)\s*)?(Fig(?:ure)?\.?|Table|图|表)\s*([A-Z]?\d+)([a-z]?)',re.I)
CAPTION_TITLE={
  'abstract':'摘要','introduction':'引言','methods':'方法','materials and methods':'材料与方法',
  'results':'结果','discussion':'讨论','conclusions':'结论','conclusion':'结论',
  'references':'参考文献','acknowledgements':'致谢','acknowledgments':'致谢',
  'data availability':'数据可用性','code availability':'代码可用性',
}
def fig_id(match):
    prefix,kind,number,_panel = match.groups()
    prefixes={'扩展数据':'extended data','补充':'supplementary'}
    prefix=prefixes.get(prefix,prefix)
    kind='table' if kind.casefold() in ('table','表') else 'figure'
    return '-'.join(x.lower().replace(' ','-') for x in (prefix,kind,number) if x)

def link_in_prose(text, ids):
    output=[]
    last=0
    for match in FIG.finditer(text):
        anchor=fig_id(match)
        if anchor not in ids:
            continue
        output.append(escape(text[last:match.start()]))
        output.append(f'<a class="figref" href="#{anchor}">{escape(match.group())}</a>')
        last=match.end()
    return ''.join(output)+escape(text[last:])

def article_dom(work):
    return BeautifulSoup((work/'article.html').read_text(encoding='utf-8'),'html.parser')

def nodes(dom):
    return [n for n in dom.select(NODES) if not n.select(NODES)
            and not n.find_parent(['pre','code'])
            and not n.find_parent('figure', class_='source-page')
            and re.search('[A-Za-z]{2,}',n.get_text())]

def translation_rows(dom):
    result=[]
    in_refs=False
    section=""
    for node in nodes(dom):
        plain=node.get_text(' ',strip=True)
        if re.fullmatch('h[2-6]',node.name):
            section=plain
            in_refs=plain.lower() in ('references','bibliography','literature cited')
        elif in_refs and node.name in ('p','li'):
            continue
        protected=[]
        def save(html):
            protected.append(html)
            return f'[Z{len(protected)}]'
        def flatten(child):
            if isinstance(child,NavigableString):
                return TECH.sub(lambda m:' '+save(escape(m.group()))+' ',str(child))
            if not isinstance(child,Tag):
                return ''
            if child.name in ('a','sup','sub','math','code'):
                return save(str(child))
            if child.name=='br':
                return ' '
            return ''.join(flatten(c) for c in child.children)
        text=re.sub(r'\s+',' ',''.join(flatten(c) for c in node.children)).strip()
        if not text:
            continue
        # Include inline-token contents in the key so corrections and retries cannot reuse stale text.
        identity=sha256((text+'\0'+'\0'.join(protected)).encode()).hexdigest()[:16]
        result.append({'id':identity,'role':node.name,'text':text,'section':section,'protected':protected,'node':node})
    return result

def prepare_job(work):
    rows=translation_rows(article_dom(work))
    data=[{k:v for k,v in row.items() if k!='node'} for row in rows]
    store(work/'translation-input.json',data)
    return data

def split_pair(dom,node,target):
    orig=dom.new_tag('span',attrs={'lang':'en','class':'source-text'})
    zh=dom.new_tag('span',attrs={'lang':'zh-Hans','class':'translation-text'})
    for child in list(node.contents):
        orig.append(child.extract())
    for child in list(BeautifulSoup(target,'html.parser').contents):
        zh.append(child.extract())
    node.append(orig)
    node.append(zh)
    node['class']=(node.get('class') or [])+['parallel']

def target_html(row, text, ids):
    if not is_valid(text,row):
        raise ValueError(f'Missing or invalid translation for {row["id"]}: {row["text"][:80]}')
    result=[]
    last=0
    for mark in MARKER.finditer(text):
        result.append(link_in_prose(text[last:mark.start()],ids))
        result.append(row['protected'][int(mark[1])-1])
        last=mark.end()
    result.append(link_in_prose(text[last:],ids))
    return ''.join(result)

def add_links(dom, ids):
    for n in dom.select('p,li'):
        for node in list(n.find_all(string=True)):
            if node.find_parent(['a','code','sup','sub']):
                continue
            html=link_in_prose(str(node),ids)
            if '<a ' in html:
                node.replace_with(*list(BeautifulSoup(html,'html.parser').contents))

def add_reference_links(dom,numbers):
    if not numbers:
        return
    for sup in dom.select('p sup,figcaption sup'):
        text=sup.get_text()
        following=sup.find_next_sibling(string=True)
        if following and re.match(r'^(?:[CNOHPS]|Cl|Ca|Na)(?:\b|[−-])',str(following).lstrip()):
            continue
        if not re.fullmatch(r'[\d,–\- ]+',text) or sup.find('a'):
            continue
        def link(m):
            target=numbers.get(int(m[0]))
            return f'<a class="cite" href="#{target}">{m[0]}</a>' if target else m[0]
        content=re.sub(r'\d+',link,text)
        sup.clear()
        sup.extend(BeautifulSoup(content,'html.parser').contents)

REF_TITLES={'references','bibliography','literature cited','参考文献'}
REF_START=re.compile(r'(?<=[.;])\s+(?=[A-Z][A-Za-zÀ-ÿ\'’\-]+,\s+[A-Z]\.)')
REF_YEAR=re.compile(r'\((?:19|20)\d{2}[a-z]?\)')
REF_SURNAME=re.compile(r'([A-Z][A-Za-zÀ-ÿ\'’\-]+),\s+[A-Z]\.')
CITE=re.compile(r'([A-Z][A-Za-zÀ-ÿ\'’\-]+(?:\s+(?:et\s+al\.|and\s+[A-Z][A-Za-zÀ-ÿ\'’\-]+|&\s*[A-Z][A-Za-zÀ-ÿ\'’\-]+))?[,，]\s*(?:19|20)\d{2}[a-z]?)')

def structure_references(dom):
    """Split the bibliography into addressable entries keyed by author, year and number."""
    heading=None
    for node in dom.find_all(['h2','h3','h4','h5','h6']):
        label=node.select_one('.source-text') or node
        if label.get_text(' ',strip=True).lower() in REF_TITLES:
            heading=node
            break
    if heading is None:
        return {},{}
    body=[]
    for sibling in heading.find_next_siblings():
        if re.fullmatch(r'h[1-6]',sibling.name or ''):
            break
        body.append(sibling)
    entries=[]
    for node in body:
        if node.name=='ol':
            start=int(node.get('start',1))
            for offset,item in enumerate(node.find_all('li',recursive=False)):
                entries.append((start+offset,item.get_text(' ',strip=True)))
        elif node.name=='ul':
            for item in node.find_all('li',recursive=False):
                entries.append((None,item.get_text(' ',strip=True)))
        elif node.name in ('p','li'):
            for part in REF_START.split(node.get_text(' ',strip=True)):
                if part.strip():
                    entries.append((None,part))
    entries=[(number,re.sub(r'\s+',' ',text).strip()) for number,text in entries if text.strip()]
    if not entries:
        return {},{}
    for node in body:
        node.extract()
    index={}
    numbers={}
    used=set()
    for position,(number,entry) in enumerate(entries,1):
        surnames=REF_SURNAME.findall(entry)
        year=REF_YEAR.search(entry)
        slug='-'.join(x for x in ((surnames[0].lower() if surnames else ''),
                                  (year.group()[1:5] if year else '')) if x) or str(position)
        slug=re.sub(r'[^a-z0-9-]+','-',slug)
        base=slug
        n=1
        while slug in used:
            n+=1
            slug=f'{base}-{n}'
        used.add(slug)
        anchor=f'ref-{slug}'
        node=dom.new_tag('p',attrs={'class':'ref-entry','id':anchor})
        node.string=entry
        heading.insert_before(node)
        if number is not None:
            numbers[number]=anchor
        if surnames:
            index.setdefault(surnames[0].lower(),anchor)
        if year:
            for surname in surnames[:2]:
                index.setdefault(f'{surname.lower()}-{year.group()[1:5]}',anchor)
    return index,numbers

def link_citations(dom,index):
    if not index:
        return
    for node in dom.select('p,li,figcaption'):
        if node.find_parent('p') or node.select_one('.ref-entry'):
            continue
        for text in list(node.find_all(string=True)):
            if text.find_parent(['a','sup','code']) or text.find_parent('p',class_='ref-entry'):
                continue
            value=str(text)
            if not CITE.search(value):
                continue
            pieces=[]; last=0
            for match in CITE.finditer(value):
                phrase=match.group(1)
                surname=re.split(r'[\s,，]',phrase,1)[0].strip()
                year=re.search(r'(?:19|20)\d{2}',phrase)
                target=index.get(f'{surname.lower()}-{year.group()}') if year else None
                target=target or index.get(surname.lower())
                if not target:
                    continue
                pieces.append(escape(value[last:match.start()]))
                pieces.append(f'<a class="cite" href="#{target}">{escape(phrase)}</a>')
                last=match.end()
            if not pieces:
                continue
            pieces.append(escape(value[last:]))
            text.replace_with(*list(BeautifulSoup(''.join(pieces),'html.parser').contents))

def label_captions(dom):
    for figure in dom.select('figure'):
        caption=figure.select_one('figcaption')
        if not caption:
            continue
        first=next((c for c in caption.children if isinstance(c,NavigableString) and str(c).strip()),None)
        if first is None:
            continue
        value=str(first)
        match=re.match(r'\s*(?:Figure|Fig\.?|Table|图|表)\s*[A-Z]?\d+[a-z]?(?:\.|。)?\s*',value,re.I)
        if not match:
            continue
        label=dom.new_tag('span',attrs={'class':'caption-label'})
        label.string=match.group().strip()
        first.replace_with(label, NavigableString(value[match.end():]))

PANEL=re.compile(r'^\s*[（(]\s*[A-Z]\s*(?:[–\-—]\s*[A-Z])?\s*[)）]')
LEGEND=re.compile(r'^(?:[（(]?图例续下页[)）]?|[(（]?legend continued|see also (?:figure|table|fig\.))',re.I)

LEGEND_TEXT=re.compile(r'\s*\(legend continued on next page\)\s*|\s*（图例续下页）\s*')

def strip_legend(node):
    for text in list(node.find_all(string=True)):
        value=str(text)
        cleaned=LEGEND_TEXT.sub(' ',value)
        if cleaned!=value:
            text.replace_with(NavigableString(cleaned))

def gather_captions(dom):
    """Pull the legend paragraphs that trail a figure into that figure."""
    for figure in dom.select('figure'):
        if not figure.select_one('figcaption'):
            continue
        panels=[]
        node=figure
        while True:
            node=node.next_sibling
            if node is None:
                break
            if isinstance(node,Tag):
                if re.fullmatch(r'h[1-6]',node.name or '') or node.name in ('figure','table','details'):
                    break
                text=node.get_text(' ',strip=True) if node.name=='p' else ''
                if text and (PANEL.match(text) or LEGEND.search(text)):
                    panels.append(node)
        # "continued on next page" means the rest of the legend sits after the
        # page break; keep collecting panel paragraphs until the next plate.
        if panels and LEGEND.search(panels[-1].get_text(' ',strip=True)):
            node=panels[-1]
            while True:
                node=node.next_sibling
                if node is None:
                    break
                if not isinstance(node,Tag):
                    continue
                if node.name in ('figure','table','details'):
                    break
                if node.name!='p':
                    continue
                text=node.get_text(' ',strip=True)
                if not PANEL.match(text):
                    break
                panels.append(node)
            # The tail usually sits right above the next plate, after the body text.
            anchor=None
            heading=None
            node=panels[-1]
            while True:
                node=node.next_sibling
                if node is None:
                    break
                if not isinstance(node,Tag):
                    continue
                if node.name in ('figure','table','details'):
                    anchor=node
                    break
                if heading is None and re.fullmatch(r'h[2-6]',node.name or ''):
                    heading=node
            anchor=anchor or heading
            probe=anchor
            tail=[]
            while probe is not None:
                probe=probe.previous_sibling
                if probe is None:
                    break
                if not isinstance(probe,Tag):
                    continue
                if 'page-anchor' in (probe.get('class') or []):
                    continue
                if probe.name=='p' and probe not in panels:
                    text=probe.get_text(' ',strip=True)
                    if PANEL.match(text) or re.match(r'^[a-z(]',text):
                        tail.insert(0,probe)
                        continue
                break
            panels.extend(tail)
        if not panels:
            continue
        for node in panels:
            strip_legend(node)
        body=dom.new_tag('div',attrs={'class':'caption-body'})
        for node in panels:
            node.extract()
            body.append(node)
        figure.append(body)

def place_figures(dom):
    """Leave a slot at the section that first mentions each plate; return the plates."""
    article=dom.select_one('article') or dom
    plates=[tag for tag in article.find_all('figure') if str(tag.get('id','')).startswith(('figure-','table-'))]
    kept=[]
    for plate in plates:
        identifier=plate['id']
        blocks=[child for child in article.children if isinstance(child,Tag)]
        if plate not in blocks:
            continue
        position=None
        for index,block in enumerate(blocks):
            if block is plate or block.name in ('figure','h1'):
                continue
            for match in FIG.finditer(block.get_text(' ',strip=True)):
                if fig_id(match)==identifier:
                    position=index
                    break
            if position is not None:
                break
        if position is None:
            continue
        slot=dom.new_tag('div',attrs={'class':'fig-slot','id':f'slot-{identifier}','data-fig':identifier})
        following=[child for child in article.children if isinstance(child,Tag)][position+1:]
        heading=next((child for child in following if re.fullmatch(r'h[2-6]',child.name or '')),None)
        if heading is None:
            article.append(slot)
        else:
            heading.insert_before(slot)
        plate.extract()
        kept.append(plate)
    return kept

def render(work,output,translation,mode):
    dom=article_dom(work)
    title=dom.h1.get_text(strip=True)
    translations=read_translations(translation) if translation else {}
    bilingual=translation is not None
    if bilingual and mode not in ('en','zh','both'):
        raise ValueError('Unknown reader language mode.')
    anchor_ids={n['id'] for n in dom.select('[id]')}
    primary=[]
    minor=[]
    for i,h in enumerate(dom.select('h2,h3,h4,h5,h6'),1):
        anchor=f'section-{i}'
        h['id']=anchor
        label=h.get_text(' ',strip=True)
        if label.lower() in CAPTION_TITLE:
            h.name='h2'
            primary.append(h)
        else:
            minor.append(h)
    headings=primary if len(primary)>=3 else primary+minor
    headings=headings[:20]
    if bilingual:
        for row in translation_rows(dom):
            if row['role'] in ('h2','h3','h4','h5','h6') and row['text'].lower() in CAPTION_TITLE:
                value=CAPTION_TITLE[row['text'].lower()]
            else:
                value=translations.get(row['id'],'')
            split_pair(dom,row['node'],target_html(row,value,anchor_ids))
    add_links(dom,anchor_ids)
    reference_index,reference_numbers=structure_references(dom)
    add_reference_links(dom,reference_numbers)
    link_citations(dom,reference_index)
    for node in dom.select('p, li'):
        text=node.get_text(' ',strip=True)
        if re.search(r'https?://|[\w.+-]+@[\w-]+\.[\w.]+',text):
            node['class']=(node.get('class') or [])+['plain']
    label_captions(dom)
    gather_captions(dom)
    plates=place_figures(dom)
    rail=''.join(str(plate) for plate in plates)
    labels=[]
    for heading in headings:
        translated=heading.select_one('.translation-text')
        label=heading.select_one('.source-text') or heading
        line=escape(label.get_text(' ',strip=True))
        if translated:
            line='<span class="source-text" lang="en">'+line+'</span><span class="translation-text" lang="zh-Hans">'+escape(translated.get_text(' ',strip=True))+'</span>'
        labels.append(f'<a href="#{heading["id"]}">{line}</a>')
    control=''
    lang='en'
    if bilingual:
        if mode!='en':
            lang='zh-Hans'
        options=''.join(f'<option value="{val}"'+(' selected' if val==mode else '')+f'>{label}</option>'
            for val,label in [('en','English'),('zh','中文'),('both','中英对照')])
        control='<div class="language-control" lang="zh-Hans"><label for="reading-language">阅读语言</label><select id="reading-language">'+options+'</select></div>'
        note=dom.new_tag('p',attrs={'class':'translation-note note-zh','lang':'zh-Hans'})
        note.string='译文供阅读参考。图内文字、公式图和参考文献条目保留原文。'
        dom.header.append(note)
    nav=control+'<a class="brand" href="#top">'+(
        '<span class="source-text" lang="en">Contents</span><span class="translation-text" lang="zh-Hans">目录</span>' if bilingual else 'Contents'
        )+'</a><div class="nav-links">'+''.join(labels)+'</div>'
    css=(ASSETS/'reader.css').read_text()
    js=(ASSETS/'reader.js').read_text()
    result=f'''<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><style>{css}</style></head>
<body id="top" class="no-js" data-mode="{mode if bilingual else 'en'}">
<input class="switch" type="checkbox" id="outline-switch" checked>
<input class="switch" type="checkbox" id="rail-switch" checked>
<input class="switch" type="radio" name="reading-size" id="size-0">
<input class="switch" type="radio" name="reading-size" id="size-1">
<input class="switch" type="radio" name="reading-size" id="size-2">
<input class="switch" type="radio" name="reading-size" id="size-3" checked>
<input class="switch" type="radio" name="reading-size" id="size-4">
<input class="switch" type="radio" name="reading-size" id="size-5">
<input class="switch" type="radio" name="reading-size" id="size-6">
<input class="switch" type="radio" name="rail-width" id="rail-w-0">
<input class="switch" type="radio" name="rail-width" id="rail-w-1" checked>
<input class="switch" type="radio" name="rail-width" id="rail-w-2">
<input class="switch" type="radio" name="rail-size" id="rail-size-0">
<input class="switch" type="radio" name="rail-size" id="rail-size-1" checked>
<input class="switch" type="radio" name="rail-size" id="rail-size-2">
<input class="switch" type="radio" name="rail-size" id="rail-size-3">
<div class="app">
<header class="topbar">
<label class="ctrl" for="outline-switch" title="收起或展开目录"><span aria-hidden="true">☰</span> 目录</label>
<span class="grow"></span>
<div class="fontctl" role="group" aria-label="字号">
<label class="sz sz-0" for="size-0" title="最小字号">A</label>
<label class="sz sz-1" for="size-1" title="很小字号">A</label>
<label class="sz sz-2" for="size-2" title="较小字号">A</label>
<label class="sz sz-3" for="size-3" title="标准字号">A</label>
<label class="sz sz-4" for="size-4" title="稍大字号">A</label>
<label class="sz sz-5" for="size-5" title="大字号">A</label>
<label class="sz sz-6" for="size-6" title="最大字号">A</label>
</div>
<div class="widthctl" role="group" aria-label="图表栏宽度">
<label class="w w-0" for="rail-w-0" title="窄">窄</label>
<label class="w w-1" for="rail-w-1" title="中">中</label>
<label class="w w-2" for="rail-w-2" title="宽">宽</label>
</div>
<label class="ctrl" for="rail-switch" title="收起或展开图表栏"><span aria-hidden="true">◫</span> 图表</label>
</header>
<div class="shell">
<nav id="outline" aria-label="Contents">{nav}</nav>
<main><article>{dom}</article></main>
<div class="rail-resizer" id="rail-resizer" role="separator" aria-orientation="vertical" aria-label="调整图表栏宽度" tabindex="0"></div>
<aside id="rail" aria-label="Figures and tables"><div class="rail-head"><span>图表 · FIGURES</span><div class="rail-size" role="group" aria-label="图表字号"><label class="rs-0" for="rail-size-0" title="图表字号：小">A</label><label class="rs-1" for="rail-size-1" title="图表字号：中">A</label><label class="rs-2" for="rail-size-2" title="图表字号：大">A</label><label class="rs-3" for="rail-size-3" title="图表字号：特大">A</label></div></div>{rail}</aside>
</div>
</div>
<div class="cite-pop" id="cite-pop" role="dialog" aria-label="参考文献" hidden></div>
<dialog aria-label="Enlarged figure"><button class="close" type="button">Close ×</button><div class="enlarged"></div></dialog>
<script>{js}</script></body></html>'''
    verify(result)
    output.parent.mkdir(parents=True,exist_ok=True)
    pending=output.with_suffix(output.suffix+'.tmp')
    pending.write_text(result,encoding='utf-8')
    pending.replace(output)

def verify(html):
    dom=BeautifulSoup(html,'html.parser')
    ids=[n['id'] for n in dom.select('[id]')]
    if len(ids)!=len(set(ids)):
        raise ValueError('Some anchors are duplicated.')
    uniq=set(ids)
    if any(a['href'][1:] not in uniq for a in dom.select('a[href^="#"]')):
        raise ValueError('Some links point to missing anchors.')
    if dom.select('script[src],iframe,link[rel="stylesheet"]') or any(not img.get('src','').startswith('data:image/png;base64,') for img in dom.select('img')):
        raise ValueError('Reader contains external visual or script assets.')
    if any(len(n.select(':scope > .source-text, :scope > .translation-text'))!=2 for n in dom.select('article .parallel')):
        raise ValueError('A bilingual text block is incomplete.')
    return len(dom.select('.page-anchor')),len(dom.select('figure')),len(dom.select('article .translation-text'))

def selected_pages(spec):
    pages=set()
    for selection in spec.split(',') if spec else []:
        points=[int(p) for p in selection.split('-',1)]
        first,last=points[0],points[-1]
        if first<1 or first>last:
            raise ValueError(f'Invalid PDF page range: {selection}')
        pages.update(range(first,last+1))
    return pages

def cli():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    def extraction_options(cmd):
        cmd.add_argument('pdf',type=Path)
        cmd.add_argument('--work',type=Path,required=True)
        cmd.add_argument('--ocr',choices=['auto','off','force'],default='auto')
        cmd.add_argument('--ocr-language',default='eng')
        cmd.add_argument('--facsimile',help='Original page image only, e.g. 33-37')
    def translator_option(cmd):
        cmd.add_argument('--translator',choices=['local','api','deepseek'],default='local',
                         help='Simplified Chinese translation backend (default: local)')
    convert=commands.add_parser('convert')
    extraction_options(convert)
    translator_option(convert)
    convert.add_argument('output',type=Path)
    convert.add_argument('--mode',choices=['en','zh','both'],default='both')
    prep=commands.add_parser('prepare')
    extraction_options(prep)
    mt=commands.add_parser('translate')
    translator_option(mt)
    mt.add_argument('--work',type=Path,required=True)
    build=commands.add_parser('render')
    translator_option(build)
    build.add_argument('--work',type=Path,required=True)
    build.add_argument('output',type=Path)
    build.add_argument('--mode',choices=['en','zh','both'],default='both')
    build.add_argument('--translations',type=Path)
    commands.add_parser('models')
    commands.add_parser('deepseek-setup',help='Save a DeepSeek key using a masked Mac prompt')
    test=commands.add_parser('verify')
    test.add_argument('html',type=Path)
    args=parser.parse_args()
    if args.command=='models':
        prepare_models(cache_path(),chrome_path())
    elif args.command=='deepseek-setup':
        from deepseek_keychain import setup_key
        setup_key()
    elif args.command=='verify':
        print('pages=%d, figures/tables=%d, translated blocks=%d'%verify(args.html.read_text(encoding='utf-8')))
    else:
        needs_translation=args.command=='translate' or (args.command=='convert' and args.mode!='en')
        translator=getattr(args,'translator','local')
        api_config=None
        if needs_translation and translator=='api':
            api_config=Config.from_env()
        elif needs_translation and translator=='deepseek':
            api_config=Config.deepseek()
        translation_name={
            'local':'translations.json',
            'api':'translations-api.json',
            'deepseek':'translations-deepseek.json',
        }[translator]
        if args.command in ('prepare','convert'):
            from extract import extract
            if args.command=='convert' and args.output.resolve()==args.pdf.resolve():
                raise ValueError('The HTML output cannot replace the source PDF.')
            audit=extract(args.pdf,args.work,ocr=args.ocr,language=args.ocr_language,facade=selected_pages(args.facsimile))
            unfinished=[c for c in audit.get('caption_audit',[]) if not c['clean_end']]
            print(f'Parsed {len(audit["pages"])} pages; visuals: {audit["counts"]}; unmatched captions: {len(audit["unmatched_captions"])}',flush=True)
            if audit.get('caption_strategy')=='labels-only':
                print('Caption type sizes unavailable (scanned pages); legends stay label-anchored.',flush=True)
            if unfinished:
                print('Captions without a closing sentence: '+', '.join(c['label'] for c in unfinished),flush=True)
            rows=prepare_job(args.work)
        if needs_translation:
            if args.command=='translate':
                rows=prepare_job(args.work)
            output=args.work/translation_name
            if api_config:
                translate_api(rows,args.work,api_config,output)
            else:
                translate(rows,output,prepare_models)
            print(f'Prepared {len(rows)} aligned blocks using the {translator} translator.',flush=True)
        if args.command in ('render','convert'):
            translation=getattr(args,'translations',None) or (args.work/translation_name if args.mode!='en' else None)
            if args.mode!='en' and (translation is None or not translation.is_file()):
                raise ValueError('Run translate or provide a translation JSON before creating a bilingual reader.')
            render(args.work,args.output,translation,args.mode)
            print(args.output.resolve())

if __name__=='__main__':
    try:
        cli()
    except (OSError,ValueError,RuntimeError) as exc:
        sys.exit(str(exc))
