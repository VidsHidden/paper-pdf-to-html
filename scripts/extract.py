"""Extract ordered reading blocks and clipped visuals from an academic PDF."""
from dataclasses import dataclass
from html import escape
from pathlib import Path
import base64
import json
import re
import statistics

from bs4 import BeautifulSoup
from markdown_it import MarkdownIt
import pymupdf
import pymupdf4llm

MD = MarkdownIt('commonmark', {'html': True}).enable('table')
ALLOWED = set('a p strong em b i sup sub s del u mark br h1 h2 h3 h4 h5 h6 ul ol li blockquote pre code table thead tbody tfoot tr th td hr'.split())
VISUAL = {'picture', 'formula'}
LABEL = re.compile(r'^(?:(extended\s+data|supplementary|supporting)\s+)?(fig(?:ure)?\.?|table)\s*([A-Z]?\d+[A-Z]?)(?=\s*(?:[.｜|:]|$)|\s)', re.I)

@dataclass
class Box:
    page: int
    kind: str
    rect: pymupdf.Rect
    html: str
    text: str
    label: str = ''
    used: bool = False
    size: float = 0.0

def clean_html(value):
    dom = BeautifulSoup(MD.render(value), 'html.parser')
    for tag in list(dom.find_all(True)):
        if tag.name is None:
            continue
        if tag.name in ('script','style','iframe','object','embed','svg','img','video','audio','form'):
            tag.decompose()
        elif tag.name not in ALLOWED:
            tag.unwrap()
        else:
            keep = {}
            if tag.name == 'a' and tag.get('href'):
                uri = tag.get('href').strip()
                if re.match(r'^(?:https?://|mailto:)', uri,re.I):
                    keep['href']=uri
            for attr in ('colspan','rowspan','start'):
                if str(tag.get(attr,'')).isdigit():
                    keep[attr]=tag[attr]
            tag.attrs = keep
    return str(dom).strip(), dom.get_text(' ', strip=True)

def key_for(match):
    prefix,kind,number = match.groups()
    return ' '.join(x.casefold() for x in (prefix,'table' if kind.lower()=='table' else 'figure',number) if x)

def by_columns(boxes, width):
    if len(boxes)<4:
        return sorted(boxes,key=lambda b:(b.rect.y0,b.rect.x0))
    prose=[b for b in boxes if b.kind in ('text','section-header','list-item','caption')]
    if not prose:
        return sorted(boxes,key=lambda b:(b.rect.y0,b.rect.x0))
    x = max(range(int(width*.4),int(width*.61)),key=lambda x:
        min(sum(b.rect.x1 <= x for b in prose),sum(b.rect.x0 >= x for b in prose))
        - 1.5*sum(b.rect.x0+12 < x < b.rect.x1-12 for b in prose) -.0001*abs(x-width/2))
    left=[b for b in prose if b.rect.x1 <= x+3]
    right=[b for b in prose if b.rect.x0 >= x-3]
    def height(values):
        return sum(min(b.rect.height,140) for b in values)
    if not left or not right or min(height(left),height(right))<24:
        return sorted(boxes,key=lambda b:(b.rect.y0,b.rect.x0))
    if min(max(b.rect.y1 for b in left),max(b.rect.y1 for b in right)) <= max(min(b.rect.y0 for b in left),min(b.rect.y0 for b in right)):
        return sorted(boxes,key=lambda b:(b.rect.y0,b.rect.x0))
    full=[b for b in boxes if b.rect.x0 < x-7 and b.rect.x1 > x+7]
    pending=[b for b in boxes if b not in full]
    result=[]
    def column_sort(group):
        return sorted(group,key=lambda b:(b.rect.x0 >= x-3,b.rect.y0,b.rect.x0))
    for divider in sorted(full,key=lambda b:b.rect.y0):
        band=[b for b in pending if (b.rect.y0+b.rect.y1)/2 < divider.rect.y0]
        result.extend(column_sort(band))
        result.append(divider)
        pending=[b for b in pending if b not in band]
    return result+column_sort(pending)

def block_font_size(page, rect):
    """Median text size of the spans that fill this block."""
    sizes=[]
    for block in page.get_text('dict')['blocks']:
        if block.get('type')!=0:
            continue
        for line in block['lines']:
            for span in line['spans']:
                box=pymupdf.Rect(span['bbox'])
                if box.is_empty:
                    continue
                overlap=box&rect
                if overlap.is_empty or overlap.get_area()<.4*box.get_area():
                    continue
                sizes.append(round(span['size'],1))
    return statistics.median(sizes) if sizes else 0.0

def body_font_size(page_boxes):
    """Most common size among long prose blocks; legends are set smaller."""
    sizes=[]
    for group in page_boxes.values():
        for box in group:
            if box.kind in ('text','list-item') and box.size and len(box.text)>200:
                sizes.extend([box.size]*min(len(box.text),1200))
    return statistics.median(sizes) if sizes else 0.0

def parse_pages(doc, pages, ocr, language):
    chunks=pymupdf4llm.to_markdown(doc,pages=pages,page_chunks=True, header=False, footer=False,
        use_ocr=ocr!='off',force_ocr=ocr=='force',ocr_language=language,table_output='html',force_text=False)
    result={}
    for number,chunk in zip(pages,chunks,strict=True):
        result[number]=[]
        for info in chunk['page_boxes']:
            kind=info['class']
            if kind in ('page-header','page-footer','folio'):
                continue
            start,end=info['pos']
            md=chunk['text'][start:end].strip()
            html,text=clean_html(md) if kind not in VISUAL else ('','')
            if kind not in VISUAL and not text:
                continue
            m=LABEL.match(text)
            rect=pymupdf.Rect(info['bbox'])
            result[number].append(Box(number,kind,rect,html,text,key_for(m) if m else '',
                                      False,block_font_size(doc[number],rect)))
        # Some title pages have authors and editorial dates aligned as a faux table.
        for box in result[number]:
            if number==0 and box.kind=='table' and re.search(r'\breceived\b.*\baccepted\b',box.text,re.I|re.S):
                cells=BeautifulSoup(box.html,'html.parser').select('td,th')
                if len(cells)>1:
                    box.kind='text'
                    box.html=''.join('<p>'+escape(c.get_text(' ',strip=True))+'</p>' for c in cells if c.get_text(strip=True))
    return result

def caption_text(group):
    """Join caption blocks and drop the publisher's page-break marker."""
    text=' '.join(simple_inline(box.html) for box in group)
    text=LEGEND_MARK.sub(' ',text)
    return re.sub(r'\s+',' ',text).strip()

def simple_inline(html):
    return re.sub(r'^<(?:p|h[1-6])>|</(?:p|h[1-6])>$','',html.strip()).strip()

def caption_groups(page_boxes):
    captions={}
    for index,boxes in page_boxes.items():
        for row in boxes:
            if not row.label or row.used or row.kind in VISUAL:
                continue
            before=list(captions.get(row.label,[]))
            if len(row.text)>90 and re.search(r'^.{0,80}\b(?:demonstrates|shows|illustrates|presents|summarizes)\b',row.text,re.I) and row.kind=='text':
                continue
            related=[b for b in boxes if b is not row and not b.label and not b.used and b.kind in ('text','caption')
                and b.rect.x0 >= row.rect.x1+4 and abs(b.rect.y0-row.rect.y0)<3
                and min(b.rect.height,row.rect.height)>.5*max(b.rect.height,row.rect.height)]
            continuation=[]
            if row.kind=='section-header':
                continuation=[b for b in boxes if b.kind=='text' and not b.label and not b.used
                    and abs(b.rect.x0-row.rect.x0)<8 and -1 <= b.rect.y0-row.rect.y1 < 7][:1]
                if continuation and not related:
                    base=continuation[0]
                    related=[b for b in boxes if b.kind=='text' and not b.label and not b.used and b.rect.x0>=base.rect.x1+4
                        and abs(b.rect.y0-row.rect.y0)<6 and abs(b.rect.y1-base.rect.y1)<15]
            for box in continuation+related:
                box.used=True
            row.used=True
            if re.search(r'\bsee (?:the )?next page\b',row.text,re.I):
                if not before:
                    captions[row.label]=[row]
            else:
                if not before or any('see next page' in b.text.lower() for b in before):
                    captions[row.label]=[row]+continuation+related
                else:
                    # Keep repeated caption labels as ordinary blocks when their role is uncertain.
                    row.used=False
                    for b in continuation+related:
                        b.used=False
    return captions

PANEL_LIKE=re.compile(r'^\s*[（(]\s*[A-Z]\s*(?:[–\-—]\s*[A-Z])?\s*[)）]')
TERMINAL=re.compile(r'[.!?。！？]\s*$')
HEADING_LIKE=re.compile(r'^(?:[A-Z][A-Z0-9 ,.&/–-]{3,}|(?:RESULTS|DISCUSSION|METHODS|CONCLUSION)\b)')
LEGEND_MARK=re.compile(r'\(legend continued on next page\)|（图例续下页）|\(continued on next page\)|\(continued\)',re.I)
TERMINAL=re.compile(r'[.!?。！？]\s*$')

def attach_legend(captions, page_boxes, body):
    """Grow each caption with the smaller-set type that belongs to it.

    Legend type is set below body size, which separates multi-paragraph and
    page-break tails from ordinary prose far more reliably than adjacency.
    """
    if not captions or not body:
        return
    for boxes in page_boxes.values():
        for index,box in enumerate(boxes):
            group=captions.get(box.label) if box.label else None
            if not group or group[0] is not box:
                continue
            for follower in boxes[index+1:]:
                if follower.used or follower.label or follower.kind in VISUAL or follower.kind=='table':
                    break
                if follower.kind=='section-header' or HEADING_LIKE.match(follower.text.strip()):
                    break
                if not follower.size or follower.size>body-.25:
                    break
                follower.used=True
                group.append(follower)
    open_labels={label for label,group in captions.items()
                 if group and LEGEND_MARK.search(group[-1].text)}
    if not open_labels:
        return
    orphans=[box for group in page_boxes.values() for box in group
             if not box.used and not box.label and box.size and box.size<body-.25
             and box.kind in ('text','caption','list-item')]
    taken={}
    for orphan in sorted(orphans,key=lambda b:(b.page,b.rect.y0,b.rect.x0)):
        candidates=[(label,group) for label,group in captions.items()
                    if label in open_labels and group[0].page<=orphan.page<=group[0].page+2]
        if not candidates:
            continue
        label,group=max(candidates,key=lambda item:(item[1][0].page,item[1][0].rect.y0))
        if any(item is orphan for item in group):
            continue
        # The first tail may continue a sentence; anything after it must open a
        # new panel. That keeps method notes and reference lists out.
        pattern=r'^\s*[(（]' if taken.get(label,0) else r'^\s*[a-z(（]'
        if not re.match(pattern,orphan.text):
            continue
        orphan.used=True
        group.append(orphan)
        taken[label]=taken.get(label,0)+1

def distances(caption, visual):
    pages=visual.page-caption.page
    if pages:
        return 190 + abs(pages)*40 + (0 if pages==1 else 15)
    a,b=caption.rect,visual.rect
    xgap=max(0,a.x0-b.x1,b.x0-a.x1)
    ygap=max(0,a.y0-b.y1,b.y0-a.y1)
    return ygap + 1.3*xgap

def png(doc,page,rect=None,dpi=180):
    p=doc[page]
    clip=p.rect if rect is None else pymupdf.Rect(rect.x0-4,rect.y0-3,rect.x1+4,rect.y1+3)&p.rect
    pix=p.get_pixmap(dpi=dpi,clip=clip,alpha=False)
    data=base64.b64encode(pix.tobytes('png')).decode('ascii')
    return f'<img src="data:image/png;base64,{data}" width="{pix.width}" height="{pix.height}" loading="lazy">'

def zoom(image,alt):
    return (f'<button class="zoom" type="button" aria-label="Enlarge {escape(alt,quote=True)}">'
        +image.replace('<img ',f'<img alt="{escape(alt,quote=True)}" ',1)+'</button>')

def ink_area(page, area):
    """Tighten a plate region to the drawn content, ignoring a corner watermark."""
    width,height=page.rect.width,page.rect.height
    scan=pymupdf.Rect(area.x0,area.y0,area.x1,min(page.rect.y1,area.y1+24))
    rects=[]
    for item in page.get_drawings():
        rect=pymupdf.Rect(item['rect'])&page.rect
        if not rect.is_empty and rect.intersects(scan):
            rects.append(rect)
    for info in page.get_image_info():
        rect=pymupdf.Rect(info['bbox'])&page.rect
        if not rect.is_empty and rect.intersects(scan):
            rects.append(rect)
    if not rects:
        return area
    # Publisher watermarks and logos sit alone in a top corner and must not enlarge the plate.
    corner=[r for r in rects if r.y1<.1*height and (r.x1<.15*width or r.x0>.85*width)]
    rest=[r for r in rects if not any(r==c for c in corner)]
    if corner and rest and min(r.y0 for r in rest)>max(r.y1 for r in corner):
        rects=rest
    box=pymupdf.Rect(min(r.x0 for r in rects),min(r.y0 for r in rects),
                     max(r.x1 for r in rects),max(r.y1 for r in rects))
    box.x0=max(box.x0,area.x0); box.x1=min(box.x1,area.x1); box.y0=max(box.y0,area.y0)
    # Panel art can sit a hair below the caption line; keep it when it is close.
    if box.y1-area.y1>18:
        box.y1=area.y1
    if box.is_empty or box.width<.25*width or box.height<.08*height:
        return area
    return (box+(-3,-3,3,3))&page.rect

def crop_large_figures(doc, page_boxes):
    for page, boxes in page_boxes.items():
        labels=[b for b in boxes if b.label and 'figure' in b.label]
        if len(labels)!=1:
            continue
        label=labels[0]
        surface=doc[page].rect
        caption_column=[]
        if label.rect.y0 >= .58*surface.height:
            area=pymupdf.Rect(surface.x0,.05*surface.height,surface.x1,label.rect.y0-4)
        else:
            # A caption at the top of the page still anchors a plate that fills the page.
            caption_column=[b for b in boxes if b is not label
                            and abs(b.rect.x0-label.rect.x0)<10
                            and b.rect.y0 >= label.rect.y1-2 and b.rect.y1 <= label.rect.y1+420]
            floor=max([label.rect.y1]+[b.rect.y1 for b in caption_column])
            prose=[b for b in boxes if b.kind in ('text','list-item','section-header') and not b.label
                   and len(b.text)>140 and len(re.findall(r'[a-z]+',b.text))>=16
                   and b.rect.y0 > floor+8]
            if not prose:
                continue
            area=pymupdf.Rect(surface.x0,.04*surface.height,surface.x1,min(b.rect.y0 for b in prose)-4)
            if label.rect.x0 > .4*surface.width and label.rect.y1 <= area.y1+20:
                # The caption occupies its own column; keep it out of the plate.
                area.x1=min(area.x1,label.rect.x0-3)
        before=[b for b in boxes if b.rect.y0 < area.y1 and b.rect.y1 <= area.y1+18]
        skip={id(label)}|{id(b) for b in caption_column}
        prose=[b for b in before if id(b) not in skip
               and b.kind in ('text','list-item','section-header') and not b.label
               and len(b.text)>140 and len(re.findall(r'[a-z]+',b.text))>=16]
        if prose or not any(b.kind in ('picture','table') for b in before):
            continue
        # Recover the whole plate when a caption identifies a figure-only region.
        # A layout model may report only some image panels or misclassify plots as tables.
        area=ink_area(doc[page],area)
        for b in before:
            if id(b) not in skip:
                b.used=True
        boxes.append(Box(page,'picture',area,'','',label.label))

def extract(pdf, out, *, ocr='auto', language='eng', facade=()):
    with pymupdf.open(pdf) as doc:
        if not doc.is_pdf or doc.needs_pass:
            raise ValueError('Supply an unlocked PDF.')
        title=(doc.metadata.get('title') or '').strip() or Path(pdf).stem
        if set(facade)-set(range(1,len(doc)+1)):
            raise ValueError('A facsimile page number is outside the PDF.')
        pages=[i for i in range(len(doc)) if i+1 not in facade]
        boxes=parse_pages(doc,pages,ocr,language) if pages else {}
        crop_large_figures(doc,boxes)
        body=body_font_size(boxes)
        captions=caption_groups(boxes)
        attach_legend(captions,boxes,body)
        pictures=[b for group in boxes.values() for b in group if b.kind=='picture' and not b.used]
        tables=[b for group in boxes.values() for b in group if b.kind=='table' and not b.used]
        assigned={}
        for max_distance in (0,1):
            paired_labels={item[0] for item in assigned.values()}
            for label,caption in captions.items():
                if label in paired_labels:
                    continue
                options=tables if 'table' in label else pictures
                candidates=[b for b in options if id(b) not in assigned and b.label==label]
                if not candidates:
                    candidates=[b for b in options if id(b) not in assigned and not b.label
                                and abs(b.page-caption[0].page)==max_distance]
                if candidates:
                    found=min(candidates,key=lambda b:distances(caption[0],b))
                    if found.label or distances(caption[0],found)<270:
                        assigned[id(found)]=(label,caption)
        # Vector plates leave caption-less slivers behind: an unpaired picture smaller
        # than a readable panel is a fragment of a figure, not a figure.
        for b in pictures:
            if id(b) in assigned:
                continue
            surface=doc[b.page].rect
            if b.rect.width < .18*surface.width or b.rect.height < .10*surface.height:
                b.used=True
        html=[]
        report={'title':title,'source':str(Path(pdf).resolve()),'pages':[],'unmatched_captions':[]}
        counts={'picture':0,'formula':0,'table':0}
        title_norm=lambda s:re.sub(r'\W+','',s.casefold())
        for group in boxes.values():
            for b in group:
                if b.kind=='section-header' and b.page==0 and title_norm(b.text)==title_norm(title):
                    b.used=True
        for page in range(len(doc)):
            number=page+1
            content=[]
            html.append(f'<div class="page-anchor" id="page-{number}" aria-label="PDF page {number}"></div>')
            group=boxes.get(page,[])
            for b in by_columns([b for b in group if not b.used],doc[page].rect.width):
                paired=assigned.get(id(b))
                caption=''
                identifier=''
                if paired:
                    label, cap=paired
                    identifier=re.sub(r'[^a-z0-9]+','-',label.strip().casefold())
                    caption='<figcaption data-pdf-page="'+str(cap[0].page+1)+'">'+caption_text(cap)+'</figcaption>'
                if b.kind in VISUAL:
                    counts[b.kind]+=1
                    alt=paired[0].title() if paired else f'{b.kind.title()} on PDF page {number}'
                    tag=f'<figure data-pdf-page="{number}"'+(f' id="{identifier}"' if identifier else '')+'>'
                    image=png(doc,page,b.rect,dpi=215 if b.kind=='formula' else 180)
                    content.append(tag+(zoom(image,alt) if b.kind=='picture' else image.replace('<img ',f'<img alt="{escape(alt)}" ',1))+caption+'</figure>')
                elif b.kind=='table':
                    counts['table']+=1
                    content.append(f'<figure class="table-wrap"'+(f' id="{identifier}"' if identifier else '')+'>'+caption+b.html+'</figure>')
                else:
                    fragment=b.html
                    if fragment.startswith('<h1>'):
                        fragment=fragment.replace('<h1>','<h2>',1).replace('</h1>','</h2>',1)
                    content.append(fragment)
            for label, cap in captions.items():
                if cap[0].page==page and label not in {a[0] for a in assigned.values()}:
                    report['unmatched_captions'].append({'label':label,'page':number})
                    content.append('<figure id="'+re.sub(r'[^a-z0-9]+','-',label.strip().casefold())+'"><figcaption>'
                                   +' '.join(simple_inline(x.html) for x in cap)+'</figcaption></figure>')
            preserved=number in facade or not (content or group)
            if preserved:
                content.append(f'<details class="source-page"><summary>Original PDF page {number}</summary>'
                    +zoom(png(doc,page,dpi=150),f'PDF page {number}')+'</details>')
            html.extend(content)
            report['pages'].append({'page':number,'extracted_blocks':len(group),'facsimile':preserved})
        report['counts']=counts
        report['body_font_size']=body
        report['caption_strategy']='font-size' if body else 'labels-only'
        report['caption_audit']=[{'label':label,'page':cap[0].page+1,'chars':len(clean),
                                  'clean_end':bool(TERMINAL.search(clean))}
                                 for label,cap in captions.items()
                                 for clean in [BeautifulSoup(caption_text(cap),'html.parser').get_text(' ',strip=True)]]
        report['paired_captions']=[{'label':label,'caption_page':cap[0].page+1,'asset_page':b.page+1}
            for b in pictures+tables if (pair:=assigned.get(id(b))) for label,cap in [pair]]
    out.mkdir(parents=True,exist_ok=True)
    (out/'article.html').write_text('<header><h1>'+escape(title)+'</h1></header>\n'+'\n'.join(html),encoding='utf-8')
    (out/'extraction.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report
