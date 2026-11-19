"""Fetch TranslateKit's public Google component packages into a local cache."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
import hashlib
import io
import platform
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
import zipfile

COMPONENTS = {'en-zh': 'boeedobmjjddfgncfnmnehcemjbfpfbk'}
NS='{http://www.google.com/update2/response}'

def fetch(url, byte_range=None):
    if urlparse(url).scheme!='https' or urlparse(url).hostname not in ('update.googleapis.com','www.google.com','dl.google.com','redirector.gvt1.com'):
        raise ValueError('Unexpected Google component URL.')
    req=Request(url, headers={'Range':f'bytes={byte_range[0]}-{byte_range[1]}'} if byte_range else {})
    with urlopen(req, timeout=50) as response:
        return response.read(),response.status

def download(update):
    url=update.get('codebase','').replace('http://','https://',1)
    size=int(update.get('size','0'))
    if not 0<size<160_000_000:
        raise ValueError('Unexpected model package size.')
    parts=[(start,min(start+3_000_000,size)-1) for start in range(0,size,3_000_000)]
    def chunk(span):
        query=urlencode({'part':f'{span[0]}-{span[1]}'})
        data,status=fetch(url+('?' if '?' not in url else '&')+query,span)
        return data if status==206 and len(data)==span[1]-span[0]+1 else None
    first=chunk(parts[0])
    if first is None:
        data,_=fetch(url)
    else:
        with ThreadPoolExecutor(max_workers=16) as pool:
            tail=list(pool.map(chunk,parts[1:]))
        data=b''.join([first]+tail) if all(tail) else fetch(url)[0]
    if hashlib.sha256(data).hexdigest()!=update.get('hash_sha256'):
        raise ValueError('Google component download failed its SHA-256 check.')
    return data

def copy_runtime_from_chrome(cache,chrome):
    from playwright.sync_api import sync_playwright

    dest=cache/'runtime'
    if (dest/'TranslateKitFiles'/'libtranslatekit.so').is_file():
        return
    if dest.exists():
        raise ValueError(f'Incomplete Chrome runtime in {dest}. Use a fresh PAPER_HTML_MODEL_CACHE.')
    print('Preparing the Chrome translation runtime…',flush=True)
    with TemporaryDirectory(dir=cache) as td, sync_playwright() as playwright:
        root=Path(td)
        blank=root/'index.html'
        blank.write_text('<!doctype html><meta charset="utf-8"><title>Set up local translation</title>')
        profile=root/'profile'
        context=playwright.chromium.launch_persistent_context(profile,executable_path=chrome,
            headless=True,ignore_default_args=['--disable-background-networking','--disable-component-update'])
        try:
            page=context.pages[0]
            page.goto(blank.as_uri())
            page.evaluate("""() => {
                if (typeof Translator === 'undefined') throw new Error('This Chrome version does not expose Translator');
                const button = document.createElement('button');
                button.textContent = 'Prepare translation';
                button.onclick = () => Translator.create({sourceLanguage:'en',targetLanguage:'zh'})
                    .catch(error => { window.translationError = String(error); });
                document.body.append(button);
            }""")
            page.get_by_role('button',name='Prepare translation').click()
            end=time.monotonic()+155
            while time.monotonic()<end:
                libraries=list(profile.glob('TranslateKit/lib/*/TranslateKitFiles/libtranslatekit.so'))
                if libraries:
                    stage=root/'runtime'
                    shutil.copytree(libraries[0].parents[1],stage)
                    if not dest.exists():
                        stage.replace(dest)
                    return
                error=page.evaluate('window.translationError || ""')
                if error:
                    raise ValueError(error)
                page.wait_for_timeout(500)
            raise ValueError('Chrome did not finish installing the translation runtime.')
        finally:
            context.close()

def prepare(cache, chrome):
    if (platform.system(),platform.machine())!=('Darwin','arm64'):
        raise ValueError('Automatic model setup currently supports Apple Silicon macOS. Supply a translation JSON on other platforms.')
    if not chrome.is_file():
        raise ValueError('Install Google Chrome or set PAPER_HTML_CHROME to its executable.')
    version=re.search(r'\d+\.\d+\.\d+\.\d+',subprocess.check_output([str(chrome),'--version'],text=True))
    if not version:
        raise ValueError('Cannot determine the installed Chrome version.')
    cache.mkdir(parents=True,exist_ok=True)
    copy_runtime_from_chrome(cache,chrome)
    for folder,appid in COMPONENTS.items():
        required='en_zh_nmt/translation_model.pb'
        dest=cache/folder
        if (dest/required).is_file():
            continue
        query=urlencode({'response':'updatecheck','prodversion':version.group(),'acceptformat':'crx3',
                         'os':'mac','arch':'arm64','os_arch':'arm64','x':f'id={appid}&v=0.0.0.0&uc'})
        xml,_=fetch('https://update.googleapis.com/service/update2/crx?'+query)
        update=ET.fromstring(xml).find(f'.//{NS}updatecheck')
        if update is None or update.get('status')!='ok':
            raise ValueError(f'Google did not return the {folder} component.')
        print(f'Preparing {folder} translation component…',flush=True)
        data=download(update)
        with TemporaryDirectory(dir=cache) as td:
            stage=Path(td)/folder
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for member in archive.namelist():
                    if member.startswith('/') or '..' in Path(member).parts:
                        raise ValueError('Invalid component archive path.')
                archive.extractall(stage)
            if not (stage/required).is_file():
                raise ValueError(f'Google component missing {required}.')
            if not dest.exists():
                stage.replace(dest)
            elif not (dest/required).is_file():
                raise ValueError(f'Incomplete component in {dest}. Use a fresh PAPER_HTML_MODEL_CACHE.')
