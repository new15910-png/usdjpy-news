from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import quote_plus, urljoin
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
OUT = ROOT / "output"
OUT.mkdir(exist_ok=True)

UA = "USDJPYNewsPrototype/0.1 (+personal research; polite polling)"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept-Language": "ja,en-US;q=0.8,en;q=0.7"})
TIMEOUT = int(CONFIG.get("request_timeout_seconds", 15))


@dataclass
class Item:
    source: str
    title: str
    url: str
    published: str | None = None
    summary: str = ""
    text: str = ""
    relevance: int = 0
    direction: str = "中立"
    reasons: list[str] | None = None

    def searchable(self) -> str:
        return " ".join([self.title, self.summary, self.text]).lower()


KEYWORDS = {
    # direct FX terms
    "usd/jpy": 5, "dollar/yen": 5, "ドル円": 5, "円相場": 4,
    "yen": 3, "円安": 4, "円高": 4, "jpy": 3,
    # central banks / policy
    "bank of japan": 3, "boj": 3, "日本銀行": 3, "日銀": 3,
    "federal reserve": 3, "fed": 2, "frb": 3, "fomc": 3,
    "interest rate": 2, "rate hike": 3, "rate cut": 3,
    "政策金利": 3, "利上げ": 3, "利下げ": 3,
    # macro catalysts
    "cpi": 2, "inflation": 2, "インフレ": 2, "consumer price": 2,
    "employment": 2, "nonfarm": 3, "payroll": 3, "unemployment": 2,
    "雇用統計": 3, "失業率": 2, "treasury yield": 2, "米国債": 2,
    # intervention
    "intervention": 4, "currency intervention": 5, "為替介入": 5,
}

# USD/JPY rises = yen weakens. These are intentionally transparent prototype rules.
YEN_WEAK = [
    (r"rate hike|利上げ", "FRB", "FRB利上げ・タカ派材料"),
    (r"hawkish|タカ派", "", "タカ派材料"),
    (r"treasury yield.*(?:rise|higher)|米国債.*(?:上昇|高)", "", "米金利上昇"),
    (r"strong(?:er)? dollar|ドル高", "", "ドル高"),
    (r"yen weak|weak yen|円安", "", "円安"),
]
YEN_STRONG = [
    (r"rate cut|利下げ", "FRB", "FRB利下げ・ハト派材料"),
    (r"dovish|ハト派", "", "ハト派材料"),
    (r"rate hike|利上げ", "BOJ", "日銀利上げ材料"),
    (r"intervention|為替介入", "", "為替介入・介入警戒"),
    (r"yen strengthen|strong yen|円高", "", "円高"),
    (r"weak(?:er)? employment|雇用.*弱|payroll.*(?:miss|weak|fall)", "", "米雇用の弱さ"),
]


def clean_html(value: str) -> str:
    if not value:
        return ""
    return " ".join(BeautifulSoup(value, "html.parser").stripped_strings)


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = dateparser.parse(value)
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def recent_enough(value: str | None) -> bool:
    dt = parse_date(value)
    if dt is None:
        return True
    cutoff = datetime.now(timezone.utc) - timedelta(hours=int(CONFIG["lookback_hours"]))
    return dt >= cutoff


def get(url: str) -> requests.Response:
    r = SESSION.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(node: ET.Element, names: set[str]) -> str:
    for child in list(node):
        if _local_name(child.tag) in names:
            return "".join(child.itertext()).strip()
    return ""


def rss_items(source: str, url: str) -> list[Item]:
    # Standard-library parser for RSS 2.0 / RDF RSS / Atom. No extra dependency.
    r = get(url)
    root = ET.fromstring(r.content)
    candidates = [n for n in root.iter() if _local_name(n.tag) in {"item", "entry"}]
    out: list[Item] = []
    for e in candidates[: int(CONFIG["max_items_per_source"])]:
        title = clean_html(_child_text(e, {"title"}))
        summary = clean_html(_child_text(e, {"description", "summary", "content", "encoded"}))
        published = _child_text(e, {"pubdate", "published", "updated", "date"}) or None

        link = _child_text(e, {"link"})
        if not link:
            for child in list(e):
                if _local_name(child.tag) == "link":
                    href = child.attrib.get("href")
                    rel = child.attrib.get("rel", "alternate")
                    if href and rel in {"alternate", ""}:
                        link = href
                        break
        if title and link and recent_enough(published):
            out.append(Item(source=source, title=title, url=link, published=published, summary=summary))
    return out


def collect_reuters() -> list[Item]:
    # Prototype adapter: Google News RSS restricted to reuters.com.
    # This avoids pretending Reuters has a stable public general-purpose RSS endpoint.
    q = 'site:reuters.com (USD JPY OR yen OR "Bank of Japan" OR dollar OR Federal Reserve)'
    url = "https://news.google.com/rss/search?q=" + quote_plus(q) + "&hl=en-US&gl=US&ceid=US:en"
    items = rss_items("Reuters", url)
    # Keep only Reuters-labelled items when Google includes publisher in source metadata/title.
    return [i for i in items if "Reuters" in i.title or "reuters" in i.summary.lower() or "reuters" in i.url.lower()]


def collect_boj() -> list[Item]:
    url = "https://www.boj.or.jp/whatsnew/index.htm"
    r = get(url)
    soup = BeautifulSoup(r.text, "html.parser")
    out: list[Item] = []
    # The page structure changes occasionally, so select anchors and filter by useful text.
    for a in soup.select("a[href]"):
        title = " ".join(a.stripped_strings)
        href = a.get("href", "")
        if not title or len(title) < 8:
            continue
        if href.startswith("#") or "rss" in href.lower():
            continue
        full = urljoin(url, href)
        parent_text = " ".join(a.parent.stripped_strings) if a.parent else title
        if any(k in (title + " " + parent_text) for k in ["金融政策", "総裁", "物価", "短観", "国債", "金利", "市場", "経済"]):
            out.append(Item(source="日銀", title=title, url=full, summary=parent_text[:500]))
        if len(out) >= int(CONFIG["max_items_per_source"]):
            break
    return out


def collect_mof() -> list[Item]:
    return rss_items("財務省", "https://www.mof.go.jp/news.rss")


def collect_fed() -> list[Item]:
    return rss_items("FRB", "https://www.federalreserve.gov/feeds/press_monetary.xml")


def collect_bls() -> list[Item]:
    """Collect key BLS indicators with one batched API request.

    The previous prototype made one request per series. This version batches
    all three series into a single POST request and caches successful results
    for six hours. If the API is temporarily unavailable or the daily quota
    is exhausted, the last successful cache is reused when available.
    Set optional environment variable BLS_API_KEY to use a registered key.
    """
    series_meta = {
        "CES0000000001": ("米国・非農業部門雇用者数", "千人", "https://www.bls.gov/news.release/empsit.nr0.htm"),
        "LNS14000000": ("米国・失業率", "%", "https://www.bls.gov/news.release/empsit.nr0.htm"),
        "CUUR0000SA0": ("米国・消費者物価指数（CPI-U）", "指数", "https://www.bls.gov/news.release/cpi.nr0.htm"),
    }
    cache_path = OUT / "bls_cache.json"
    cache_ttl = timedelta(hours=6)

    def load_bls_cache(allow_stale: bool = False) -> list[Item]:
        if not cache_path.exists():
            return []
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            fetched_at = datetime.fromisoformat(payload["fetched_at"])
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=timezone.utc)
            if not allow_stale and datetime.now(timezone.utc) - fetched_at > cache_ttl:
                return []
            return [Item(**row) for row in payload.get("items", [])]
        except Exception:
            return []

    cached = load_bls_cache()
    if cached:
        return cached

    request_body: dict[str, object] = {"seriesid": list(series_meta.keys())}
    registration_key = os.environ.get("BLS_API_KEY", "").strip()
    if registration_key:
        request_body["registrationKey"] = registration_key

    api_url = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
    try:
        r = SESSION.post(api_url, json=request_body, timeout=TIMEOUT)
        r.raise_for_status()
        payload = r.json()
        if payload.get("status") != "REQUEST_SUCCEEDED":
            messages = payload.get("message", [])
            stale = load_bls_cache(allow_stale=True)
            if stale:
                return stale
            raise RuntimeError(f"BLS API request failed: {messages}")

        out: list[Item] = []
        for row in payload.get("Results", {}).get("series", []):
            series_id = row.get("seriesID")
            if series_id not in series_meta:
                continue
            label, unit, human_url = series_meta[series_id]
            data = row.get("data", [])
            monthly = [d for d in data if str(d.get("period", "")).startswith("M") and d.get("period") != "M13"]
            if not monthly:
                continue

            latest = monthly[0]
            previous = monthly[1] if len(monthly) > 1 else None
            value = str(latest.get("value", "")).strip()
            period_name = latest.get("periodName") or latest.get("period") or ""
            year = latest.get("year", "")

            change_text = ""
            if previous is not None:
                try:
                    delta = float(value.replace(",", "")) - float(str(previous.get("value", "")).replace(",", ""))
                    sign = "+" if delta > 0 else ""
                    change_text = f"、前月比 {sign}{delta:g} {unit}"
                except (TypeError, ValueError):
                    pass

            title = f"{label}: {period_name} {year} = {value} {unit}"
            summary = (
                f"BLS公式Public Data API。{label}の最新値は {value} {unit}{change_text}。"
                "市場予想との比較を含まないため、この数値だけではドル円の方向は自動確定しません。"
            )
            out.append(Item(source="BLS", title=title, url=human_url, summary=summary))

        if out:
            cache_path.write_text(
                json.dumps({
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "items": [asdict(i) for i in out],
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return out
    except Exception:
        stale = load_bls_cache(allow_stale=True)
        if stale:
            return stale
        raise

def fetch_article_text(item: Item) -> None:
    if not CONFIG.get("fetch_article_text", True):
        return
    # Reuters: leave article body alone in the prototype; headline/summary are enough for filtering.
    if item.source == "Reuters":
        return
    try:
        r = get(item.url)
        if "text/html" not in r.headers.get("content-type", ""):
            return
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()
        # Prefer main/article, fall back to body.
        node = soup.find("main") or soup.find("article") or soup.body
        if node:
            text = " ".join(node.stripped_strings)
            item.text = text[:12000]
    except Exception:
        pass


def relevance_score(item: Item) -> int:
    s = item.searchable()
    score = 0
    for k, w in KEYWORDS.items():
        if k.lower() in s:
            score += w
    # Official source priors: these releases can matter even when USDJPY isn't named.
    if item.source == "FRB" and any(k in s for k in ["fomc", "monetary policy", "interest rate", "federal funds"]):
        score += 3
    if item.source == "BLS" and any(k in s for k in ["employment", "payroll", "consumer price", "cpi", "inflation"]):
        score += 3
    if item.source == "日銀" and any(k in s for k in ["金融政策", "物価", "金利", "総裁"]):
        score += 3
    if item.source == "財務省" and any(k in s for k in ["為替", "外国為替", "介入", "国際政策"]):
        score += 4
    return score


def classify(item: Item) -> tuple[str, list[str]]:
    s = item.searchable()
    up, down = 0, 0
    reasons: list[str] = []

    # Context-aware simple rules.
    for pattern, context, reason in YEN_WEAK:
        if re.search(pattern, s, re.I) and (not context or context.lower() in s or item.source.lower() == context.lower()):
            up += 1
            reasons.append(reason)
    for pattern, context, reason in YEN_STRONG:
        if re.search(pattern, s, re.I) and (not context or context.lower() in s or item.source.lower() == context.lower()):
            down += 1
            reasons.append(reason)

    if down > up:
        return "円高材料", reasons[:3]
    if up > down:
        return "円安材料", reasons[:3]
    return "中立/要確認", reasons[:3]


def normalize_title(title: str) -> set[str]:
    text = re.sub(r"[^a-zA-Z0-9一-龥ぁ-んァ-ヶ]+", " ", title.lower())
    return {t for t in text.split() if len(t) >= 2 and t not in {"reuters", "update", "news"}}


def dedupe(items: list[Item]) -> list[Item]:
    kept: list[Item] = []
    for item in sorted(items, key=lambda x: x.relevance, reverse=True):
        words = normalize_title(item.title)
        duplicate = False
        for k in kept:
            other = normalize_title(k.title)
            if not words or not other:
                continue
            sim = len(words & other) / max(1, len(words | other))
            if sim >= 0.62:
                duplicate = True
                break
        if not duplicate:
            kept.append(item)
    return kept


def collect_all() -> tuple[list[Item], list[str]]:
    collectors = [collect_reuters, collect_boj, collect_mof, collect_fed, collect_bls]
    all_items: list[Item] = []
    errors: list[str] = []
    for fn in collectors:
        try:
            chunk = fn()
            all_items.extend(chunk)
        except Exception as e:
            errors.append(f"{fn.__name__}: {type(e).__name__}: {e}")
        time.sleep(0.5)
    return all_items, errors


def render_report(items: list[Item], errors: list[str]) -> str:
    now_jst = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M JST")
    counts = {"円高材料": 0, "円安材料": 0, "中立/要確認": 0}
    for i in items:
        counts[i.direction] = counts.get(i.direction, 0) + 1

    if counts["円高材料"] > counts["円安材料"] + 1:
        balance = "円高材料がやや優勢"
    elif counts["円安材料"] > counts["円高材料"] + 1:
        balance = "円安材料がやや優勢"
    else:
        balance = "材料は拮抗"

    lines = [
        "# USD/JPY ニュース・プロトタイプレポート",
        "",
        f"生成: {now_jst}",
        f"判定: **{balance}**",
        "",
        "> 注意: これはニュース整理用の試作で、売買推奨ではありません。方向判定は透明なルールベースです。",
        "",
        "## サマリー",
        "",
        f"- 円高材料: {counts['円高材料']}件",
        f"- 円安材料: {counts['円安材料']}件",
        f"- 中立/要確認: {counts['中立/要確認']}件",
        "",
        "## 抽出ニュース",
        "",
    ]

    for idx, i in enumerate(items[:20], 1):
        why = "、".join(i.reasons or []) or "方向を自動確定できず"
        lines += [
            f"### {idx}. [{i.source}] {i.title}",
            f"- 判定: **{i.direction}** / 関連度: {i.relevance}",
            f"- 根拠: {why}",
            f"- URL: {i.url}",
        ]
        if i.published:
            lines.append(f"- 公開日時: {i.published}")
        if i.summary:
            lines.append(f"- 概要: {i.summary[:350]}")
        lines.append("")

    if errors:
        lines += ["## 取得エラー", ""] + [f"- {e}" for e in errors] + [""]

    lines += [
        "## 次段階",
        "",
        "このプロトタイプでは取得・関連抽出・重複整理・方向分類まで実装。次はLLMを使い、",
        "1) 同一イベントのクラスタリング、2) 重要度、3) 3行要約、4) 根拠引用、5) 時系列保存を追加する。",
    ]
    return "\n".join(lines)


def run_pipeline() -> tuple[list[Item], list[str]]:
    """Collect, classify, dedupe and persist the latest USD/JPY news set."""
    raw, errors = collect_all()

    for item in raw:
        # First cheap pass on headline/summary. Fetch body only if potentially relevant or official source.
        item.relevance = relevance_score(item)
        if item.relevance >= 1 or item.source != "Reuters":
            fetch_article_text(item)
            item.relevance = relevance_score(item)
        item.direction, item.reasons = classify(item)

    selected = [i for i in raw if i.relevance >= int(CONFIG["relevance_threshold"])]
    selected = dedupe(selected)
    selected.sort(key=lambda x: x.relevance, reverse=True)

    (OUT / "usdjpy_items.json").write_text(
        json.dumps([asdict(i) for i in selected], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report = render_report(selected, errors)
    (OUT / "usdjpy_report.md").write_text(report, encoding="utf-8")
    return selected, errors


def main() -> None:
    items, errors = run_pipeline()
    print(render_report(items, errors))


if __name__ == "__main__":
    main()
