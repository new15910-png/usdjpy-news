from __future__ import annotations

import html
import json
import os
import socket
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from main import Item, OUT, run_pipeline

JST = timezone(timedelta(hours=9))


def load_cached() -> list[Item]:
    path = OUT / "usdjpy_items.json"
    if not path.exists():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
        return [Item(**r) for r in rows]
    except Exception:
        return []


def load_errors() -> list[str]:
    path = OUT / "last_errors.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def updated_text() -> str:
    path = OUT / "usdjpy_items.json"
    if not path.exists():
        return "未取得"
    dt = datetime.fromtimestamp(path.stat().st_mtime, tz=JST)
    return dt.strftime("%Y-%m-%d %H:%M JST")


def summarize(items: list[Item]) -> tuple[dict[str, int], str]:
    counts = {"円高材料": 0, "円安材料": 0, "中立/要確認": 0}
    for i in items:
        counts[i.direction] = counts.get(i.direction, 0) + 1
    if not items:
        return counts, "未取得"
    if counts["円高材料"] > counts["円安材料"] + 1:
        verdict = "円高材料がやや優勢"
    elif counts["円安材料"] > counts["円高材料"] + 1:
        verdict = "円安材料がやや優勢"
    else:
        verdict = "材料は拮抗"
    return counts, verdict


def direction_class(direction: str) -> str:
    if direction == "円高材料":
        return "yenstrong"
    if direction == "円安材料":
        return "yenweak"
    return "neutral"


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def ensure_initial_data() -> None:
    """Render free instances have ephemeral storage, so fetch once after a cold start."""
    if load_cached():
        return
    try:
        _, errors = run_pipeline()
        (OUT / "last_errors.json").write_text(
            json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        (OUT / "last_errors.json").write_text(
            json.dumps([f"初回取得失敗: {type(e).__name__}: {e}"], ensure_ascii=False),
            encoding="utf-8",
        )


def render_page() -> str:
    ensure_initial_data()
    items = load_cached()
    errors = load_errors()
    counts, verdict = summarize(items)

    cards = []
    for i in items[:12]:
        reasons = "・".join(i.reasons or ["方向を自動確定できず"])
        pub = f'<div class="meta">{esc(i.published)}</div>' if i.published else ""
        cards.append(f'''<a class="card" href="{esc(i.url)}" target="_blank" rel="noopener noreferrer">
          <div class="row"><span class="badge">{esc(i.source)}</span><span class="badge {direction_class(i.direction)}">{esc(i.direction)}</span><span class="badge">関連度 {i.relevance}</span></div>
          <div class="headline">{esc(i.title)}</div><div class="reason">{esc(reasons)}</div>{pub}</a>''')
    cards_html = "\n".join(cards) if cards else '<div class="empty">まだニュースを取得していません。<br>上の「更新」を押してください。</div>'

    errors_html = ""
    if errors:
        errors_html = '<div class="section">取得エラー</div>' + "".join(f'<div class="error">{esc(e)}</div>' for e in errors)

    return f'''<!doctype html><html lang="ja"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"><meta name="theme-color" content="#0f172a">
<title>USD/JPY News</title><style>
:root{{color-scheme:light dark;--bg:#f4f6f8;--card:#fff;--text:#18212f;--muted:#677386;--line:#dde3ea;--accent:#155eef;--strong:#0b7a53;--weak:#b54708;--neutral:#667085}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0d1117;--card:#161b22;--text:#eef2f6;--muted:#9aa6b2;--line:#30363d;--accent:#79a7ff;--strong:#56d6a2;--weak:#ffb86b;--neutral:#a7b0bb}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,"Noto Sans JP",sans-serif}}main{{max-width:760px;margin:auto;padding:16px 14px 40px}}
.top{{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:4px 0 16px}}.title{{font-size:25px;font-weight:800;letter-spacing:-.02em}}.sub{{font-size:12px;color:var(--muted);margin-top:4px}}
button{{border:0;border-radius:12px;background:var(--accent);color:white;font-size:16px;font-weight:700;padding:12px 18px;min-height:46px;cursor:pointer}}button:disabled{{opacity:.65}}
.status{{border:1px solid var(--line);background:var(--card);border-radius:16px;padding:16px;margin-bottom:12px}}.verdict{{font-size:22px;font-weight:800;margin-top:4px}}.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:14px}}.metric{{padding:10px;border-radius:12px;border:1px solid var(--line);text-align:center}}.num{{font-size:22px;font-weight:800}}.lab{{font-size:12px;color:var(--muted)}}
.section{{margin:18px 0 9px;font-size:16px;font-weight:800}}.card{{display:block;text-decoration:none;color:inherit;border:1px solid var(--line);background:var(--card);border-radius:14px;padding:14px;margin:9px 0}}.row{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}}.badge{{font-size:12px;font-weight:800;padding:4px 8px;border-radius:999px;border:1px solid var(--line)}}.yenstrong{{color:var(--strong)}}.yenweak{{color:var(--weak)}}.neutral{{color:var(--neutral)}}
.headline{{font-size:15px;line-height:1.45;font-weight:700;margin:9px 0 7px}}.reason{{font-size:13px;color:var(--muted);line-height:1.45}}.meta{{font-size:11px;color:var(--muted);margin-top:8px}}.error{{border:1px solid #f0b8b8;border-radius:12px;padding:12px;font-size:12px;margin:8px 0;overflow-wrap:anywhere}}.empty{{text-align:center;color:var(--muted);padding:34px 12px;border:1px dashed var(--line);border-radius:14px;background:var(--card)}}.footer{{color:var(--muted);font-size:11px;line-height:1.5;margin-top:22px}}
@media(max-width:430px){{main{{padding:12px 10px 30px}}.title{{font-size:22px}}.grid{{gap:6px}}.metric{{padding:9px 4px}}.num{{font-size:20px}}}}
</style></head><body><main>
<div class="top"><div><div class="title">USD/JPY News</div><div class="sub">Reuters・日銀・財務省・FRB・BLS</div></div><form method="post" action="/refresh" id="rf"><button id="rb" type="submit">更新</button></form></div>
<section class="status"><div class="sub">ニュース材料の総合判定</div><div class="verdict">{esc(verdict)}</div><div class="grid"><div class="metric"><div class="num yenstrong">{counts['円高材料']}</div><div class="lab">円高材料</div></div><div class="metric"><div class="num yenweak">{counts['円安材料']}</div><div class="lab">円安材料</div></div><div class="metric"><div class="num neutral">{counts['中立/要確認']}</div><div class="lab">要確認</div></div></div><div class="meta">最終更新: {esc(updated_text())}</div></section>
<div class="section">重要ニュース</div>{cards_html}{errors_html}<div class="footer">これはニュース整理用の試作です。売買推奨ではありません。判定は現在ルールベースで、今後AI要約へ置き換え可能です。</div>
</main><script>const f=document.getElementById('rf'),b=document.getElementById('rb');f.addEventListener('submit',()=>{{b.disabled=true;b.textContent='取得中…';}});</script></body></html>'''


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path != "/":
            self.send_error(404)
            return
        body = render_page().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/refresh":
            self.send_error(404)
            return
        try:
            _, errors = run_pipeline()
            (OUT / "last_errors.json").write_text(json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            (OUT / "last_errors.json").write_text(json.dumps([f"更新失敗: {type(e).__name__}: {e}"], ensure_ascii=False), encoding="utf-8")
        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()

    def log_message(self, fmt: str, *args) -> None:
        print(f"[web] {self.address_string()} - {fmt % args}")


def local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "<PCのIPアドレス>"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    ip = local_ip()
    print("\nUSD/JPY News prototype")
    print(f"Local:   http://127.0.0.1:{port}")
    print(f"LAN:     http://{ip}:{port}")
    print(f"Cloud:   listening on 0.0.0.0:{port}\n")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
