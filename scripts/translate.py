"""Run paragraph translation with the locally installed Chrome TranslateKit."""
import json
import os
from pathlib import Path
import re
import shutil
from tempfile import NamedTemporaryFile, TemporaryDirectory

MARKER = re.compile(r'[\[［【]\s*[zZｚＺ]\s*([0-9０-９]+)\s*[\]］】]')
CHINESE = re.compile(r'[\u3400-\u9fff]')
CHROME_MAC = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

def chrome_path():
    value=os.environ.get('PAPER_HTML_CHROME')
    if value:
        return Path(value)
    if Path(CHROME_MAC).exists():
        return Path(CHROME_MAC)
    return Path(shutil.which('google-chrome') or shutil.which('chromium') or CHROME_MAC)

def cache_path():
    return Path(os.environ.get('PAPER_HTML_MODEL_CACHE', str(Path.home()/'.cache'/'codex-paper-pdf-to-html'))).expanduser()

def read_translations(path):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}

def store(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    file=NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,delete=False)
    pending=Path(file.name)
    try:
        with file:
            json.dump(data,file,ensure_ascii=False,indent=2)
        pending.replace(path)
    finally:
        pending.unlink(missing_ok=True)

def markers(value):
    return sorted(int(m.group(1)) for m in MARKER.finditer(value))

def is_valid(value, row):
    return isinstance(value,str) and value.strip() and markers(value)==list(range(1,len(row['protected'])+1))

def translate(rows, output, prepare=None):
    from playwright.sync_api import sync_playwright
    cache=cache_path()
    pack=cache/'en-zh'
    library=cache/'runtime'/'TranslateKitFiles'/'libtranslatekit.so'
    if not (pack/'en_zh_nmt'/'translation_model.pb').is_file() or not library.is_file():
        if prepare is None:
            raise ValueError(f'Translation models missing in {cache}.')
        prepare(cache,chrome_path())
    translations=read_translations(output)
    with TemporaryDirectory(prefix='paper-html-') as temp, sync_playwright() as playwright:
        placeholder=Path(temp)/'index.html'
        placeholder.write_text('<!doctype html><meta charset="utf-8"><title>Local translation</title>')
        browser=playwright.chromium.launch(executable_path=chrome_path(),headless=True,
            args=['--disable-background-networking',f'--translate-kit-packages=en,zh,{pack.resolve()}',
                  f'--translate-kit-binary-path={library.resolve()}'])
        page=browser.new_page(offline=True)
        page.set_default_timeout(40_000)
        page.goto(placeholder.as_uri())
        page.evaluate("""async () => {
            const options = {sourceLanguage:'en',targetLanguage:'zh'};
            const startup = async () => {
                if (typeof Translator === 'undefined' || await Translator.availability(options) !== 'available') {
                    throw new Error('Google Chrome could not load the local en/zh translation models');
                }
                return Translator.create(options);
            };
            window.engine = await Promise.race([startup(),new Promise((_, reject) =>
                setTimeout(() => reject(new Error('Local Translator startup timed out')),20_000))]);
        }""")
        for index,row in enumerate(rows,1):
            if is_valid(translations.get(row['id']),row):
                continue
            text=row['text']
            def infer(value):
                return page.evaluate("""text => Promise.race([engine.translate(text),new Promise((_, reject) =>
                    setTimeout(() => reject(new Error('Local translation timed out')),25_000))])""",value)
            value=infer(text)
            if not is_valid(value,row):
                tokens=re.split(r'(\[Z\d+\])',text)
                value=''.join(infer(part) if i%2==0 and re.search('[A-Za-z]{2,}',part) else part
                    for i,part in enumerate(tokens))
            if not is_valid(value,row):
                raise ValueError(f'Translation has missing or duplicated protected tokens in {row["id"]}.')
            translations[row['id']]=value
            if index%10==0:
                store(output,translations)
        store(output,translations)
        browser.close()
    return translations
