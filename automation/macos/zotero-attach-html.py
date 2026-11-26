#!/usr/bin/env python3
"""List pending PDFs and import a reviewed PDF2html reader as a Zotero child file."""
import argparse
from http.client import HTTPException
import fcntl
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlencode, urlsplit
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

BASE = "http://127.0.0.1:23119"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(opener, path, *, data, headers, timeout):
    req = Request(BASE + path, data=data, headers=headers)
    try:
        response = opener.open(req, timeout=timeout)
    except HTTPError as error:
        response = error
    with response:
        return response.code, response.headers, response.read()

LIBRARY = "/api/users/0"
ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config.json"
SERVICE = "PDF2html macOS Zotero attachment"


def load_config():
    if not CONFIG.is_file():
        raise RuntimeError(f"请创建 {CONFIG.name}，参见自动化安装说明。")
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or not isinstance(config.get("collection_key"), str):
        raise RuntimeError("config.json 必须包含 collection_key 字符串。")
    try:
        item_key(config["collection_key"])
    except argparse.ArgumentTypeError as exc:
        raise RuntimeError("config.json 的 collection_key 无效。") from exc
    return config
STORED = {"imported_file", "imported_url"}


def item_key(value):
    if not re.fullmatch(r"[A-Z0-9]{8}", value):
        raise argparse.ArgumentTypeError("Zotero 条目标识必须是 8 位字母或数字。")
    return value


class ZoteroError(RuntimeError):
    def __init__(self, path, code, expected):
        self.code = code
        label = "附件数据上传" if path.startswith("/api/local/uploads/") else path
        super().__init__(f"Zotero 请求 {label} 返回 HTTP {code}，预期 {expected}。")


class Zotero:
    def __init__(self):
        self.opener = build_opener(ProxyHandler({}), NoRedirect())
        self.server_id = None
        self.key = None

    def send(self, path, *, payload=None, form=None, raw=None, headers=None, write=False, expected=200):
        headers = dict(headers or {})
        if write:
            headers.update({"Zotero-Server-ID": self.server_id, "Zotero-API-Key": self.key})
        data = None
        if payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        elif form is not None:
            data = urlencode(form).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif raw is not None:
            data = raw
        try:
            code, returned, body = request(self.opener, path, data=data, headers=headers, timeout=120 if data is not None else 15)
        except (OSError, HTTPException) as exc:
            raise RuntimeError(f"本机 Zotero 接口不可用：{exc}") from None
        if code != expected:
            raise ZoteroError(path, code, expected)
        server_id = returned.get("Zotero-Server-ID")
        if self.server_id and server_id and self.server_id != server_id:
            raise RuntimeError("本机 Zotero 数据库已切换，请重新运行。")
        self.server_id = self.server_id or server_id
        return body

    def get_json(self, path):
        return json.loads(self.send(path))

    def members(self):
        collection = load_config()["collection_key"]
        path = f"{LIBRARY}/collections/{collection}/items/top"
        return {item["key"]: item["data"] for item in self.get_json(path)}

    def children(self, parent):
        return [entry["data"] for entry in self.get_json(f"{LIBRARY}/items/{parent}/children")]

    def file(self, child):
        try:
            url = self.send(f'{LIBRARY}/items/{child["key"]}/file/view/url').decode().strip()
        except ZoteroError as exc:
            if exc.code == 404:
                return None
            raise
        parsed = urlsplit(url)
        if not url:
            return None
        if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
            raise RuntimeError("Zotero 返回的附件位置不是本机文件。")
        path = Path(unquote(parsed.path))
        return path if path.is_file() else None

    def saved_grant(self):
        if not self.server_id or not re.fullmatch(r"[A-Za-z0-9]+", self.server_id):
            raise RuntimeError("未获得有效的 Zotero 服务标识。")
        account = self.server_id
        result = subprocess.run(
            ["/usr/bin/security", "find-generic-password", "-s", SERVICE, "-a", account, "-w"],
            capture_output=True, text=True, timeout=15,
        )
        existing = result.stdout.strip()
        if result.returncode == 0 and re.fullmatch(r"[A-Za-z0-9]{32}", existing):
            return existing
        return None

    def authorize(self, *, renew=False):
        existing = self.saved_grant()
        if existing and not renew:
            self.key = existing
            return
        account = self.server_id
        print("请在 Zotero 弹窗选择「始终允许」，以便分步上传并让本机任务复用授权。", flush=True)
        authorization = json.loads(self.send(
            "/api/local/authorize",
            payload={"appName": "PDF2html 本机附件上传"},
            headers={"Zotero-Server-ID": account},
        ))
        if not authorization.get("remember"):
            raise RuntimeError("本次未授予可重复使用的权限，未开始上传。")
        key = authorization.get("key") or ""
        if not re.fullmatch(r"[A-Za-z0-9]{32}", key):
            raise RuntimeError("Zotero 返回了无效授权。")
        # security -i accepts commands on stdin. The key is never a process argument.
        command = f'add-generic-password -U -s "{SERVICE}" -a {account} -w {key}\n'
        subprocess.run(["/usr/bin/security", "-i"], input=command, text=True,
                       capture_output=True, timeout=15)
        if self.saved_grant() != key:
            raise RuntimeError("无法将授权保存到 Mac 钥匙串，未开始上传。")
        self.key = key


def reader_file(path):
    if not path or path.suffix.lower() != ".html":
        return False
    with path.open("rb") as source:
        start = source.read(65536)
        source.seek(max(path.stat().st_size - 131072, 0))
        end = source.read()
    return b'id="reading-language"' in start and b'data-mode=' in start and b'</html>' in end


def inspect_children(zotero, parent):
    children = zotero.children(parent)
    pdfs = [item for item in children if item.get("contentType") == "application/pdf"]
    converted = [
        item for item in children
        if item.get("contentType") == "text/html" and item.get("linkMode") in STORED
        and reader_file(zotero.file(item))
    ]
    return children, pdfs, converted


def covers_pdf(converted, pdf, pdf_count):
    for item in converted:
        tags = {tag.get("tag", "") for tag in item.get("tags", [])}
        if f"PDF2html:source:{pdf['key']}" in tags:
            return True
        if pdf_count == 1 and not any(tag.startswith("PDF2html:source:") for tag in tags):
            return True
    return False


def check(zotero, members):
    pending = 0
    for parent, record in members.items():
        _, pdfs, converted = inspect_children(zotero, parent)
        for pdf in pdfs:
            if covers_pdf(converted, pdf, len(pdfs)):
                continue
            pending += 1
            print(f"待处理：{record.get('title', parent)}｜文献 {parent}｜PDF {pdf['key']}")
    print(f"扫描 {len(members)} 个条目，待处理 PDF 共 {pending} 份。")


def attach(zotero, parent, pdf_key, html):
    children, pdfs, converted = inspect_children(zotero, parent)
    pdf = next((item for item in pdfs if item["key"] == pdf_key), None)
    if pdf is None:
        raise RuntimeError("指定 PDF 不属于这个条目。")
    if covers_pdf(converted, pdf, len(pdfs)):
        print("跳过：该 PDF 已有 Zotero 存储的阅读版 HTML。")
        return
    if not html.is_file() or not reader_file(html):
        raise RuntimeError("请选择已验收并嵌入语言切换的 PDF2html 文件。")
    content = html.read_bytes()
    digest = hashlib.md5(content).hexdigest()
    filename = html.name
    filename = f"{html.stem}-{pdf_key}.html" if len(pdfs) > 1 else filename
    marker = f"PDF2html:source:{pdf_key}"
    matching = [item for item in children if marker in {tag.get("tag") for tag in item.get("tags", [])}]
    if len(matching) > 1:
        raise RuntimeError("此 PDF 已有多个同源附件，需要核对后再继续。")
    if matching:
        if (matching[0].get("linkMode") != "imported_file"
            or matching[0].get("contentType") != "text/html"
            or matching[0].get("md5")
            or zotero.file(matching[0])):
            raise RuntimeError("同源附件已有内容或不是本次程序创建的存储文件，需要核对。")
        child_key = matching[0]["key"]
    if not zotero.key:
        zotero.authorize()
    if not matching:
        token = hashlib.sha256(f"{parent}:{pdf_key}".encode()).hexdigest()[:32]
        created = json.loads(zotero.send(f"{LIBRARY}/items", payload=[{
            "itemType": "attachment", "parentItem": parent, "linkMode": "imported_file",
            "title": "中文版 HTML", "contentType": "text/html", "charset": "utf-8",
            "filename": filename, "tags": [{"tag": marker}],
        }], headers={"Zotero-Write-Token": token}, write=True))
        created_item = created.get("successful", {}).get("0") or created.get("unchanged", {}).get("0")
        if not created_item:
            failure = created.get("failed", {}).get("0", {})
            raise RuntimeError(f"Zotero 未创建子附件，返回代码 {failure.get('code', '未知')}。")
        child_key = created_item.get("key") if isinstance(created_item, dict) else created_item
    child_key = item_key(child_key)
    file_endpoint = f"{LIBRARY}/items/{child_key}/file"
    precondition = {"If-None-Match": "*"}
    ready = json.loads(zotero.send(file_endpoint, form={
        "md5": digest, "filename": filename, "filesize": len(content),
        "mtime": html.stat().st_mtime_ns // 1_000_000, "contentType": "text/html",
    }, headers=precondition, write=True))
    if ready.get("exists") != 1:
        upload_url = urlsplit(ready["url"])
        upload_key = ready["uploadKey"]
        if (not re.fullmatch(r"[A-Za-z0-9_-]+", upload_key)
            or upload_url.scheme != "http" or upload_url.port != 23119
            or upload_url.hostname not in ("127.0.0.1", "localhost", "::1")
            or upload_url.path != f"/api/local/uploads/{upload_key}"
            or upload_url.query or upload_url.fragment):
            raise RuntimeError("Zotero 返回了异常上传地址，已停止。")
        if ready.get("prefix") or ready.get("suffix"):
            raise RuntimeError("Zotero 返回了意外的上传包装格式，已停止。")
        zotero.send(upload_url.path, raw=content, headers={"Content-Type": ready["contentType"]}, expected=201)
        zotero.send(file_endpoint, form={"upload": upload_key}, headers=precondition, write=True, expected=204)
    stored = zotero.get_json(f"{LIBRARY}/items/{child_key}")["data"]
    copied = zotero.file(stored)
    if (stored.get("parentItem") != parent or stored.get("linkMode") != "imported_file"
        or not copied or copied.read_bytes() != content):
        raise RuntimeError("写入后未能验证父条目、存储类型和文件内容。")
    print(f"已确认 Zotero 存储副本：{copied.name}")


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    subcommands = cli.add_subparsers(dest="command", required=True)
    subcommands.add_parser("check")
    subcommands.add_parser("collections")
    authorize = subcommands.add_parser("authorize")
    authorize.add_argument("--renew", action="store_true")
    upload = subcommands.add_parser("attach")
    upload.add_argument("parent", type=item_key)
    upload.add_argument("pdf", type=item_key)
    upload.add_argument("html", type=Path)
    args = cli.parse_args()
    try:
        with (ROOT / ".zotero-attach.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            zotero = Zotero()
            if args.command == "collections":
                entries = zotero.get_json(f"{LIBRARY}/collections")
                for entry in entries:
                    data = entry["data"]
                    print(f'{entry["key"]}\t{data["name"]}\t父分类：{data.get("parentCollection") or "-"}')
                return 0
            members = zotero.members()
            if args.command == "authorize":
                zotero.authorize(renew=args.renew)
                print("Zotero 附件写入授权已保存在登录钥匙串。")
            elif args.command == "check":
                check(zotero, members)
            elif args.parent not in members:
                raise RuntimeError("指定文献不在已配置的 Zotero 分类。")
            else:
                attach(zotero, args.parent, args.pdf, args.html)
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, AttributeError,
            argparse.ArgumentTypeError, subprocess.TimeoutExpired) as exc:
        print(f"未完成：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
