#!/usr/bin/env python3
"""
VECTOR 84 — Pipeline automático de noticias y papers científicos.

Recopila noticias RSS y papers open-access (arXiv + OpenAlex con PDF directo)
sobre IA, Impresión 3D / extrusión de filamento (FDM/FFF) y Emprendimiento.
Usa Gemini API (GEMINI_API_KEY) para traducir al español, curar relevancia,
detectar cruces entre áreas, resumir cada pieza y redactar el Parte Diario.

Sin dependencias externas: funciona con la biblioteca estándar de Python 3.
"""

from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
SOURCES_PATH = ROOT_DIR / "scripts" / "sources.json"
FEED_JSON_PATH = ROOT_DIR / "data" / "feed.json"
RSS_XML_PATH = ROOT_DIR / "feed.xml"

USER_AGENT = "Vector84Radar/1.0 (+https://github.com/; Automated Personal Tech Digest)"
DEFAULT_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")
FALLBACK_GEMINI_MODELS = (
    "gemini-flash-lite-latest",
    "gemini-3-flash-preview",
    "gemini-flash-latest",
    "gemini-3.1-flash-lite",
)


def load_local_dotenv() -> None:
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v

FDM_KEYWORDS = (
    "fdm", "fff", "filament", "filamento", "extrusion", "extrusión", "extruder",
    "nozzle", "boquilla", "slicer", "orcaslicer", "prusaslicer", "klipper",
    "bambu", "prusa", "voron", "creality", "pla", "petg", "abs", "asa", "tpu",
    "peek", "nylon", "pa-cf", "g-code", "gcode", "3d print", "impresión 3d",
    "additive manufacturing", "fabricación aditiva", "layer adhesion", "infill",
    "corexy", "hotend", "bed leveling", "multi-material", "toolchanger",
)
AI_KEYWORDS = (
    "ai", "artificial intelligence", "llm", "gpt", "gemini", "claude", "llama",
    "agent", "agente", "multimodal", "reasoning", "neural", "diffusion",
    "transformer", "fine-tuning", "inference", "open-weight", "open source ai",
    "machine learning", "deep learning", "computer vision", "vision model",
    "robotics", "benchmark", "vlm", "mcp",
)
BIZ_KEYWORDS = (
    "startup", "founder", "funding", "seed", "series a", "venture", "yc",
    "y combinator", "bootstrapped", "indie", "saas", "hardware startup",
    "entrepreneur", "emprendimiento", "revenue", "business model", "go-to-market",
    "acquisition", "ipo", "product-market", "monetiz", "solo founder",
)


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def make_id(prefix: str, key: str) -> str:
    digest = hashlib.sha1(key.encode("utf-8", errors="ignore")).hexdigest()[:10]
    return f"{prefix}-{digest}"


def strip_html(raw: str | None) -> str:
    if not raw:
        return ""
    text = html.unescape(raw)
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def http_get(url: str, timeout: int = 12, max_bytes: int | None = None, headers: dict[str, str] | None = None) -> bytes:
    req_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, application/json, text/html;q=0.9, */*;q=0.8",
    }
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        if max_bytes is not None:
            return resp.read(max_bytes)
        return resp.read()


def parse_date(value: str | None) -> str:
    if not value:
        return now_utc().isoformat()
    v = value.strip()
    try:
        parsed = email.utils.parsedate_to_datetime(v)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc).isoformat()
    except Exception:
        pass
    try:
        iso = v.replace("Z", "+00:00")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", iso):
            iso = f"{iso}T12:00:00+00:00"
        parsed = dt.datetime.fromisoformat(iso)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc).isoformat()
    except Exception:
        return now_utc().isoformat()


def local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower() if "}" in tag else tag.lower()


def extract_image_from_html(html_text: str, base_url: str) -> str:
    if not html_text:
        return ""
    patterns = [
        r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image(?::secure_url)?["\']',
        r'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image(?::src)?["\']',
        r'<img[^>]+src=["\']([^"\']+)["\']',
    ]
    for pat in patterns:
        match = re.search(pat, html_text, flags=re.I)
        if match:
            candidate = html.unescape(match.group(1).strip())
            if candidate.startswith("data:") or any(bad in candidate.lower() for bad in ("gravatar", "avatar", "pixel", "1x1", "spacer", "icon", ".svg")):
                continue
            return urllib.parse.urljoin(base_url, candidate)
    return ""


def fetch_og_image(article_url: str) -> str:
    try:
        raw = http_get(article_url, timeout=6, max_bytes=65536)
        snippet = raw.decode("utf-8", errors="ignore")
        return extract_image_from_html(snippet, article_url)
    except Exception:
        return ""


def _contains_keyword(lower_text: str, keywords: tuple[str, ...]) -> bool:
    for kw in keywords:
        if re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", lower_text):
            return True
    return False


def infer_categories(text: str, default_category: str) -> list[str]:
    lower = text.lower()
    cats: list[str] = []
    if _contains_keyword(lower, FDM_KEYWORDS):
        cats.append("fdm")
    if _contains_keyword(lower, AI_KEYWORDS):
        cats.append("ia")
    if _contains_keyword(lower, BIZ_KEYWORDS):
        cats.append("emprendimiento")
    if default_category and default_category not in cats:
        cats.insert(0, default_category)
    return cats or [default_category or "ia"]


def heuristic_score(title: str, snippet: str, categories: list[str], priority: int) -> float:
    lower = f"{title} {snippet}".lower()
    score = float(priority)
    # Prioridad explícita del usuario: extrusión de filamento FDM y IA
    if "fdm" in categories:
        score += 2.2
    if "ia" in categories:
        score += 1.8
    if len(categories) >= 2:
        score += 2.0  # Cruce de áreas
    for kw in ("filament", "extrusion", "fdm", "fff", "klipper", "orcaslicer", "prusa", "bambu", "nozzle", "peek", "agent", "reasoning", "open-weight"):
        if re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", lower):
            score += 0.7
    return round(min(score, 15.0), 2)


def fetch_rss_feed(feed_cfg: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    url = feed_cfg["url"]
    source_name = feed_cfg["name"]
    default_cat = feed_cfg.get("default_category", "ia")
    priority = int(feed_cfg.get("priority", 8))

    try:
        data = http_get(url, timeout=12)
        root = ET.fromstring(data)
    except Exception as exc:
        print(f"[WARN] RSS falló ({source_name}): {exc}", file=sys.stderr)
        return []

    items: list[dict[str, Any]] = []
    root_name = local_tag(root.tag)

    entries: list[ET.Element] = []
    if root_name == "rss":
        channel = root.find("channel")
        if channel is not None:
            entries = list(channel.findall("item"))
    elif root_name == "feed":
        entries = [el for el in root if local_tag(el.tag) == "entry"]
    else:
        entries = [el for el in root.iter() if local_tag(el.tag) in ("item", "entry")]

    for entry in entries[:limit]:
        title = ""
        link = ""
        pub_date = ""
        summary_html = ""
        image = ""

        for child in entry:
            tag = local_tag(child.tag)
            if tag == "title" and not title:
                title = strip_html(child.text)
            elif tag == "link":
                href = child.attrib.get("href")
                rel = child.attrib.get("rel", "alternate")
                if href and rel in ("alternate", ""):
                    link = href.strip()
                elif child.text and not link:
                    link = child.text.strip()
            elif tag in ("pubdate", "published", "updated", "date") and not pub_date:
                pub_date = (child.text or "").strip()
            elif tag in ("description", "summary", "encoded", "content"):
                candidate_html = child.text or ""
                if len(candidate_html) > len(summary_html):
                    summary_html = candidate_html
            elif tag in ("content", "thumbnail") and "media" in child.tag.lower():
                cand = child.attrib.get("url", "")
                if cand and not image:
                    image = cand
            elif tag == "enclosure":
                mtype = child.attrib.get("type", "")
                cand = child.attrib.get("url", "")
                if cand and ("image" in mtype or cand.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))) and not image:
                    image = cand

        if not title or not link:
            continue

        if not image and summary_html:
            image = extract_image_from_html(summary_html, link)

        snippet = strip_html(summary_html)[:600]
        categories = infer_categories(f"{title} {snippet}", default_cat)
        published_at = parse_date(pub_date)

        items.append({
            "id": make_id("news", link),
            "original_title": title,
            "snippet": snippet,
            "url": link,
            "source": source_name,
            "published_at": published_at,
            "image": image,
            "categories": categories,
            "priority": priority,
            "heuristic_score": heuristic_score(title, snippet, categories, priority),
        })

    return items


def fetch_arxiv_papers(query_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    query = query_cfg["query"]
    default_cat = query_cfg.get("default_category", "ia")
    max_results = int(query_cfg.get("max_results", 8))

    params = urllib.parse.urlencode({
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    })
    url = f"https://export.arxiv.org/api/query?{params}"

    data = None
    for attempt in range(2):
        try:
            data = http_get(url, timeout=30)
            break
        except Exception as exc:
            if attempt == 0:
                time.sleep(3)
            else:
                print(f"[WARN] arXiv falló ({query_cfg.get('label')}): {exc}", file=sys.stderr)
                return []
    try:
        root = ET.fromstring(data)
    except Exception as exc:
        print(f"[WARN] arXiv XML inválido ({query_cfg.get('label')}): {exc}", file=sys.stderr)
        return []

    papers: list[dict[str, Any]] = []
    for entry in [el for el in root if local_tag(el.tag) == "entry"]:
        raw_id = ""
        title = ""
        abstract = ""
        published = ""
        authors: list[str] = []
        pdf_url = ""
        abs_url = ""

        for child in entry:
            tag = local_tag(child.tag)
            if tag == "id":
                raw_id = (child.text or "").strip()
            elif tag == "title":
                title = re.sub(r"\s+", " ", (child.text or "").strip())
            elif tag == "summary":
                abstract = re.sub(r"\s+", " ", (child.text or "").strip())
            elif tag == "published":
                published = (child.text or "").strip()
            elif tag == "author":
                for sub in child:
                    if local_tag(sub.tag) == "name" and sub.text:
                        authors.append(sub.text.strip())
            elif tag == "link":
                href = child.attrib.get("href", "")
                if child.attrib.get("title") == "pdf" or child.attrib.get("type") == "application/pdf":
                    pdf_url = href
                elif child.attrib.get("rel") == "alternate":
                    abs_url = href

        if not title or not raw_id:
            continue

        arxiv_code = raw_id.rstrip("/").rsplit("/", 1)[-1]
        if not pdf_url:
            pdf_url = f"https://arxiv.org/pdf/{arxiv_code}.pdf"
        elif not pdf_url.endswith(".pdf"):
            pdf_url = f"{pdf_url}.pdf"
        if not abs_url:
            abs_url = raw_id

        categories = infer_categories(f"{title} {abstract}", default_cat)
        papers.append({
            "id": make_id("paper", raw_id),
            "original_title": title,
            "abstract": abstract[:1500],
            "url": abs_url,
            "pdf_url": pdf_url,
            "source": "arXiv",
            "paper_code": f"arXiv:{arxiv_code}",
            "authors": authors[:4],
            "published_at": parse_date(published),
            "categories": categories,
            "heuristic_score": heuristic_score(title, abstract, categories, 10),
        })

    return papers


def reconstruct_openalex_abstract(inv_index: dict[str, list[int]] | None) -> str:
    if not inv_index or not isinstance(inv_index, dict):
        return ""
    pairs: list[tuple[int, str]] = []
    for word, positions in inv_index.items():
        for pos in positions:
            pairs.append((pos, word))
    pairs.sort(key=lambda x: x[0])
    return " ".join(word for _, word in pairs)[:1500]


def fetch_openalex_papers(query_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    search = query_cfg["search"]
    default_cat = query_cfg.get("default_category", "fdm")
    per_page = int(query_cfg.get("per_page", 8))

    cutoff_year = now_utc().year - 1
    today_str = now_utc().strftime("%Y-%m-%d")
    params = urllib.parse.urlencode({
        "search": search,
        "filter": f"is_oa:true,from_publication_date:{cutoff_year}-01-01,to_publication_date:{today_str}",
        "sort": "publication_date:desc",
        "per-page": per_page,
        "mailto": "vector84-radar@example.org",
    })
    url = f"https://api.openalex.org/works?{params}"

    try:
        raw = http_get(url, timeout=15)
        payload = json.loads(raw.decode("utf-8", errors="ignore"))
    except Exception as exc:
        print(f"[WARN] OpenAlex falló ({query_cfg.get('label')}): {exc}", file=sys.stderr)
        return []

    papers: list[dict[str, Any]] = []
    for work in payload.get("results", []):
        title = (work.get("display_name") or "").strip()
        best_oa = work.get("best_oa_location") or {}
        pdf_url = best_oa.get("pdf_url") or ""
        landing = best_oa.get("landing_page_url") or work.get("doi") or work.get("id") or ""
        if not pdf_url:
            oa_url = (work.get("open_access") or {}).get("oa_url") or ""
            if oa_url.lower().endswith(".pdf"):
                pdf_url = oa_url
        if not title or not pdf_url:
            # Solo incluimos papers con enlace directo real al PDF
            continue

        abstract = reconstruct_openalex_abstract(work.get("abstract_inverted_index"))
        if not abstract:
            abstract = f"Open-access research paper published in {(best_oa.get('source') or {}).get('display_name', 'scientific journal')}."

        authors = [
            (a.get("author") or {}).get("display_name", "")
            for a in (work.get("authorships") or [])[:4]
        ]
        authors = [a for a in authors if a]
        pub_date = work.get("publication_date") or f"{work.get('publication_year', now_utc().year)}-01-01"
        venue = (best_oa.get("source") or {}).get("display_name") or "OpenAlex OA"
        doi = (work.get("doi") or "").replace("https://doi.org/", "")

        categories = infer_categories(f"{title} {abstract}", default_cat)
        papers.append({
            "id": make_id("paper", work.get("id") or pdf_url),
            "original_title": title,
            "abstract": abstract,
            "url": landing or pdf_url,
            "pdf_url": pdf_url,
            "source": venue[:40],
            "paper_code": f"DOI:{doi}" if doi else "OpenAccess",
            "authors": authors,
            "published_at": parse_date(pub_date),
            "categories": categories,
            "heuristic_score": heuristic_score(title, abstract, categories, 10),
        })

    return papers


def call_gemini_json(prompt: str, api_key: str, model: str = DEFAULT_GEMINI_MODEL) -> Any:
    models_to_try = [model] + [m for m in FALLBACK_GEMINI_MODELS if m != model]
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "responseMimeType": "application/json",
        },
    }
    encoded_body = json.dumps(body).encode("utf-8")
    ctx = ssl.create_default_context()
    last_err: Exception | None = None
    retry_delays = (0, 12, 30)

    for round_idx, delay in enumerate(retry_delays, start=1):
        if delay > 0:
            print(f"[INFO] Reintentando Gemini (ronda {round_idx}/{len(retry_delays)}) tras esperar {delay}s...", file=sys.stderr)
            time.sleep(delay)

        for candidate_model in models_to_try:
            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(candidate_model)}:generateContent?key={urllib.parse.quote(api_key)}"
            req = urllib.request.Request(
                endpoint,
                data=encoded_body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=120, context=ctx) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                candidates = data.get("candidates") or []
                if not candidates:
                    raise RuntimeError(f"Gemini no devolvió candidatos: {data}")
                parts = (candidates[0].get("content") or {}).get("parts") or []
                text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
                if not text:
                    text = "".join(p.get("text", "") for p in parts).strip()
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)
                return json.loads(text)
            except urllib.error.HTTPError as exc:
                err_body = exc.read().decode("utf-8", errors="ignore")[:300]
                print(f"[WARN] Ronda {round_idx} · {candidate_model} devolvió HTTP {exc.code}: {err_body}", file=sys.stderr)
                last_err = exc
                if exc.code in (400, 401, 403):
                    raise
                time.sleep(2)
            except Exception as exc:
                print(f"[WARN] Ronda {round_idx} · {candidate_model} falló: {exc}", file=sys.stderr)
                last_err = exc
                time.sleep(2)

    raise RuntimeError(f"Ningún modelo Gemini respondió correctamente tras {len(retry_delays)} rondas: {last_err}")


def curate_news_with_gemini(candidates: list[dict[str, Any]], max_items: int, api_key: str) -> list[dict[str, Any]]:
    compact = [
        {
            "id": item["id"],
            "title": item["original_title"],
            "snippet": item["snippet"][:420],
            "source": item["source"],
            "hint_categories": item["categories"],
            "published_at": item["published_at"][:10],
        }
        for item in candidates
    ]

    prompt = f"""Eres el editor técnico de VECTOR 84, un radar en español especializado en:
1) Inteligencia Artificial (prioridad alta)
2) Impresión 3D / Fabricación aditiva, con foco especial en extrusión de filamento FDM/FFF, materiales, slicers y hardware (prioridad alta)
3) Emprendimiento tecnológico, startups de hardware/software e indie makers.

Recibes {len(compact)} artículos candidatos (muchos en inglés). Selecciona los {max_items} más relevantes, variados y útiles (asegurando fuerte presencia de IA y extrusión de filamento/FDM, además de emprendimiento y cruces entre áreas).

Devuelve un JSON con exactamente esta forma:
{{
  "items": [
    {{
      "id": "el id exacto de entrada",
      "title_es": "Titular natural, claro y fiel en español (sin clickbait)",
      "summary_es": "Resumen conciso de 2-3 frases en español explicando qué ha pasado y por qué importa",
      "deep_summary_es": "Análisis breve adicional de 2-3 frases en español con contexto técnico o impacto práctico",
      "categories": ["ia", "fdm", "emprendimiento"],
      "primary_category": "ia | fdm | emprendimiento",
      "is_crossover": true,
      "importance": 8,
      "tags": ["FDM", "Klipper", "Filamento"]
    }}
  ]
}}

Reglas:
- Traduce SIEMPRE todo al español natural y técnico correcto (mantén siglas como FDM, FFF, PLA, PETG, PEEK, LLM, G-code).
- `categories` solo puede usar valores de ["ia", "fdm", "emprendimiento"].
- `is_crossover` es true si el artículo conecta 2 o más áreas (por ejemplo IA + FDM, o startup de impresión 3D).
- `importance` es un entero de 1 a 10.
- `tags`: entre 2 y 4 etiquetas cortas.

Candidatos:
{json.dumps(compact, ensure_ascii=False)}
"""
    res = call_gemini_json(prompt, api_key)
    by_id = {c["id"]: c for c in candidates}
    curated: list[dict[str, Any]] = []

    for entry in res.get("items", []):
        orig = by_id.get(entry.get("id"))
        if not orig:
            continue
        cats = [c for c in (entry.get("categories") or orig["categories"]) if c in ("ia", "fdm", "emprendimiento")]
        if not cats:
            cats = orig["categories"]
        primary = entry.get("primary_category")
        if primary not in ("ia", "fdm", "emprendimiento"):
            primary = cats[0]

        curated.append({
            "id": orig["id"],
            "type": "news",
            "title_es": (entry.get("title_es") or orig["original_title"]).strip(),
            "original_title": orig["original_title"],
            "summary_es": (entry.get("summary_es") or orig["snippet"][:260]).strip(),
            "deep_summary_es": (entry.get("deep_summary_es") or "").strip(),
            "url": orig["url"],
            "source": orig["source"],
            "published_at": orig["published_at"],
            "image": orig.get("image", ""),
            "categories": cats,
            "primary_category": primary,
            "is_crossover": bool(entry.get("is_crossover") or len(cats) >= 2),
            "importance": max(1, min(10, int(entry.get("importance") or 7))),
            "tags": [str(t)[:24] for t in (entry.get("tags") or [])[:4]],
        })

    curated.sort(key=lambda x: (x["importance"], x["published_at"]), reverse=True)
    return curated[:max_items]


def curate_papers_with_gemini(candidates: list[dict[str, Any]], max_items: int, api_key: str) -> list[dict[str, Any]]:
    compact = [
        {
            "id": p["id"],
            "title": p["original_title"],
            "abstract": p["abstract"][:950],
            "source": p["source"],
            "paper_code": p["paper_code"],
            "hint_categories": p["categories"],
            "published_at": p["published_at"][:10],
        }
        for p in candidates
    ]

    prompt = f"""Eres un curador científico en español para VECTOR 84, enfocado en:
1) Fabricación aditiva y extrusión de filamento (FDM/FFF, polímeros, parámetros, boquillas, defectos, G-code, optimización)
2) Inteligencia Artificial (modelos, agentes, visión artificial, razonamiento, eficiencia)
3) Emprendimiento tecnológico e innovación.

De los {len(compact)} papers candidatos (todos con PDF descargable), selecciona los {max_items} mejores y más interesantes (dando alta prioridad a extrusión de filamento/FDM y a IA, y destacando si cruzan IA + FDM).

Devuelve un JSON con exactamente esta estructura:
{{
  "papers": [
    {{
      "id": "el id exacto de entrada",
      "title_es": "Título traducido al español de forma clara y rigurosa",
      "summary_es": "Resumen claro de 2-3 frases en español comprensible para un perfil técnico",
      "problem_es": "1 frase: qué problema o limitación aborda el paper",
      "method_es": "1 frase: qué método, material o arquitectura proponen",
      "takeaway_es": "1 frase: por qué importa o qué aplicación práctica tiene",
      "categories": ["fdm", "ia"],
      "primary_category": "fdm | ia | emprendimiento",
      "is_crossover": true,
      "importance": 9,
      "tags": ["FDM", "Visión Artificial", "Control de Calidad"]
    }}
  ]
}}

Candidatos:
{json.dumps(compact, ensure_ascii=False)}
"""
    res = call_gemini_json(prompt, api_key)
    by_id = {c["id"]: c for c in candidates}
    curated: list[dict[str, Any]] = []

    for entry in res.get("papers", []):
        orig = by_id.get(entry.get("id"))
        if not orig:
            continue
        cats = [c for c in (entry.get("categories") or orig["categories"]) if c in ("ia", "fdm", "emprendimiento")]
        if not cats:
            cats = orig["categories"]
        primary = entry.get("primary_category")
        if primary not in ("ia", "fdm", "emprendimiento"):
            primary = cats[0]

        curated.append({
            "id": orig["id"],
            "type": "paper",
            "title_es": (entry.get("title_es") or orig["original_title"]).strip(),
            "original_title": orig["original_title"],
            "summary_es": (entry.get("summary_es") or orig["abstract"][:320]).strip(),
            "problem_es": (entry.get("problem_es") or "").strip(),
            "method_es": (entry.get("method_es") or "").strip(),
            "takeaway_es": (entry.get("takeaway_es") or "").strip(),
            "url": orig["url"],
            "pdf_url": orig["pdf_url"],
            "source": orig["source"],
            "paper_code": orig["paper_code"],
            "authors": orig["authors"],
            "published_at": orig["published_at"],
            "categories": cats,
            "primary_category": primary,
            "is_crossover": bool(entry.get("is_crossover") or len(cats) >= 2),
            "importance": max(1, min(10, int(entry.get("importance") or 8))),
            "tags": [str(t)[:24] for t in (entry.get("tags") or [])[:4]],
        })

    curated.sort(key=lambda x: (x["importance"], x["published_at"]), reverse=True)
    return curated[:max_items]


def generate_daily_briefing(news: list[dict[str, Any]], papers: list[dict[str, Any]], api_key: str) -> dict[str, Any]:
    top_news = [{"id": n["id"], "title": n["title_es"], "summary": n["summary_es"], "cat": n["primary_category"]} for n in news[:10]]
    top_papers = [{"id": p["id"], "title": p["title_es"], "takeaway": p.get("takeaway_es") or p["summary_es"], "cat": p["primary_category"]} for p in papers[:6]]

    prompt = f"""Redacta el "Parte Diario" (Daily Briefing) en español para VECTOR 84, un lector apasionado por IA, impresión 3D por extrusión de filamento (FDM) y emprendimiento.

A partir de las noticias y papers de hoy, genera un resumen ejecutivo para ponerse al día en 30 segundos.
Devuelve JSON exacto:
{{
  "headline": "Titular editorial breve del día (máx 90 caracteres)",
  "intro": "1-2 frases sintetizando el pulso de hoy entre IA, FDM y emprendimiento.",
  "bullets": [
    {{
      "category": "ia | fdm | emprendimiento | cruce",
      "label": "Etiqueta corta (ej. EXTRUSIÓN FDM, AGENTES IA, PAPER DESTACADO, CRUCE IA×FDM)",
      "text": "Punto clave accionable de 1-2 frases en español",
      "ref_id": "id del artículo o paper relacionado"
    }}
  ]
}}

Incluye entre 4 y 5 bullets cubriendo obligatoriamente IA, FDM/impresión 3D, emprendimiento y al menos un paper científico destacable.

Noticias:
{json.dumps(top_news, ensure_ascii=False)}

Papers:
{json.dumps(top_papers, ensure_ascii=False)}
"""
    data = call_gemini_json(prompt, api_key)
    return {
        "date": now_utc().strftime("%Y-%m-%d"),
        "headline": (data.get("headline") or "Pulso diario de IA, FDM y emprendimiento").strip(),
        "intro": (data.get("intro") or "").strip(),
        "bullets": (data.get("bullets") or [])[:5],
    }


def write_rss(feed_data: dict[str, Any], site_cfg: dict[str, Any]) -> None:
    items_xml = []
    combined = list(feed_data.get("news", []))[:15] + list(feed_data.get("papers", []))[:10]
    combined.sort(key=lambda x: x.get("published_at", ""), reverse=True)

    for item in combined[:20]:
        title = html.escape(item.get("title_es", ""))
        link = html.escape(item.get("pdf_url") or item.get("url", ""))
        desc = html.escape(item.get("summary_es", ""))
        guid = html.escape(item.get("id", link))
        cat = html.escape(item.get("primary_category", "ia").upper())
        items_xml.append(
            f"    <item>\n"
            f"      <title>[{cat}] {title}</title>\n"
            f"      <link>{link}</link>\n"
            f"      <guid isPermaLink=\"false\">{guid}</guid>\n"
            f"      <description>{desc}</description>\n"
            f"    </item>"
        )

    rss = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0">\n'
        "  <channel>\n"
        f"    <title>{html.escape(site_cfg.get('title', 'VECTOR 84'))}</title>\n"
        f"    <link>{html.escape(site_cfg.get('base_url') or 'https://github.com')}</link>\n"
        f"    <description>{html.escape(site_cfg.get('description', ''))}</description>\n"
        "    <language>es</language>\n"
        f"    <lastBuildDate>{email.utils.format_datetime(now_utc())}</lastBuildDate>\n"
        + "\n".join(items_xml)
        + "\n  </channel>\n</rss>\n"
    )
    RSS_XML_PATH.write_text(rss, encoding="utf-8")


def deduplicate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        url_key = item["url"].split("?")[0].rstrip("/").lower()
        title_key = re.sub(r"[^a-z0-9]+", "", item["original_title"].lower())[:60]
        if url_key in seen_urls or (title_key and title_key in seen_titles):
            continue
        seen_urls.add(url_key)
        if title_key:
            seen_titles.add(title_key)
        unique.append(item)
    return unique


def enrich_images(news_items: list[dict[str, Any]]) -> None:
    for item in news_items:
        if not item.get("image"):
            img = fetch_og_image(item["url"])
            if img:
                item["image"] = img


def main() -> int:
    parser = argparse.ArgumentParser(description="Actualiza data/feed.json y feed.xml para VECTOR 84.")
    parser.add_argument("--dry-run", action="store_true", help="Recopila fuentes pero no sobreescribe data/feed.json")
    parser.add_argument("--force-without-llm", action="store_true", help="Guarda resultados sin traducir si falta GEMINI_API_KEY")
    args = parser.parse_args()

    load_local_dotenv()
    cfg = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    limits = cfg["limits"]
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    active_model = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip() or DEFAULT_GEMINI_MODEL

    print("==> 1/4 Recopilando noticias RSS...")
    raw_news: list[dict[str, Any]] = []
    for feed_cfg in cfg["news_feeds"]:
        fetched = fetch_rss_feed(feed_cfg, limit=int(limits["per_feed_items"]))
        print(f"    {feed_cfg['name']}: {len(fetched)} items")
        raw_news.extend(fetched)

    raw_news = deduplicate(raw_news)
    raw_news.sort(key=lambda x: (x["heuristic_score"], x["published_at"]), reverse=True)
    candidate_news = raw_news[: int(limits["candidate_news_for_llm"])]
    print(f"    Total candidatos noticias: {len(candidate_news)}")

    print("==> 2/4 Recopilando papers open-access (arXiv + OpenAlex)...")
    raw_papers: list[dict[str, Any]] = []
    for q in cfg["arxiv_queries"]:
        found = fetch_arxiv_papers(q)
        print(f"    arXiv [{q['label']}]: {len(found)} papers")
        raw_papers.extend(found)
    for q in cfg["openalex_queries"]:
        found = fetch_openalex_papers(q)
        print(f"    OpenAlex [{q['label']}]: {len(found)} papers con PDF")
        raw_papers.extend(found)

    raw_papers = deduplicate(raw_papers)
    raw_papers.sort(key=lambda x: (x["heuristic_score"], x["published_at"]), reverse=True)
    candidate_papers = raw_papers[: int(limits["candidate_papers_for_llm"])]
    print(f"    Total candidatos papers con PDF directo: {len(candidate_papers)}")

    if args.dry_run:
        print("[DRY-RUN] Recolección finalizada sin escribir archivos.")
        return 0

    if not api_key:
        if not args.force_without_llm and FEED_JSON_PATH.exists():
            print(
                "[INFO] GEMINI_API_KEY no está configurada. Se conserva data/feed.json actual "
                "para no perder las traducciones al español. Añade GEMINI_API_KEY en GitHub Secrets.",
                file=sys.stderr,
            )
            return 0
        print("[WARN] Ejecutando sin GEMINI_API_KEY (--force-without-llm): textos sin traducir.", file=sys.stderr)
        curated_news = [
            {
                "id": n["id"],
                "type": "news",
                "title_es": n["original_title"],
                "original_title": n["original_title"],
                "summary_es": n["snippet"][:260],
                "deep_summary_es": "",
                "url": n["url"],
                "source": n["source"],
                "published_at": n["published_at"],
                "image": n.get("image", ""),
                "categories": n["categories"],
                "primary_category": n["categories"][0],
                "is_crossover": len(n["categories"]) >= 2,
                "importance": min(10, max(5, int(round(n["heuristic_score"] / 1.4)))),
                "tags": [c.upper() for c in n["categories"]],
            }
            for n in candidate_news[: int(limits["max_news"])]
        ]
        curated_papers = [
            {
                "id": p["id"],
                "type": "paper",
                "title_es": p["original_title"],
                "original_title": p["original_title"],
                "summary_es": p["abstract"][:320],
                "problem_es": "",
                "method_es": "",
                "takeaway_es": "",
                "url": p["url"],
                "pdf_url": p["pdf_url"],
                "source": p["source"],
                "paper_code": p["paper_code"],
                "authors": p["authors"],
                "published_at": p["published_at"],
                "categories": p["categories"],
                "primary_category": p["categories"][0],
                "is_crossover": len(p["categories"]) >= 2,
                "importance": min(10, max(6, int(round(p["heuristic_score"] / 1.4)))),
                "tags": [c.upper() for c in p["categories"]],
            }
            for p in candidate_papers[: int(limits["max_papers"])]
        ]
        briefing = {
            "date": now_utc().strftime("%Y-%m-%d"),
            "headline": "Actualización automática sin clave Gemini configurada",
            "intro": "Configura GEMINI_API_KEY en los Secrets del repositorio para activar traducción, curación inteligente y Parte Diario en español.",
            "bullets": [],
        }
    else:
        print(f"==> 3/4 Curando y traduciendo al español con Gemini ({active_model})...")
        previous_feed: dict[str, Any] = {}
        if FEED_JSON_PATH.exists():
            try:
                previous_feed = json.loads(FEED_JSON_PATH.read_text(encoding="utf-8"))
            except Exception:
                previous_feed = {}

        try:
            curated_news = curate_news_with_gemini(candidate_news, int(limits["max_news"]), api_key)
        except Exception as exc:
            print(f"[WARN] Falló curación de noticias con Gemini ({exc}); se conservan noticias previas.", file=sys.stderr)
            curated_news = previous_feed.get("news", [])

        time.sleep(2)

        try:
            curated_papers = curate_papers_with_gemini(candidate_papers, int(limits["max_papers"]), api_key)
        except Exception as exc:
            print(f"[WARN] Falló curación de papers con Gemini ({exc}); se conservan papers previos.", file=sys.stderr)
            curated_papers = previous_feed.get("papers", [])

        time.sleep(2)

        try:
            briefing = generate_daily_briefing(curated_news, curated_papers, api_key)
        except Exception as exc:
            print(f"[WARN] Falló el Parte Diario con Gemini ({exc}); se conserva el anterior.", file=sys.stderr)
            briefing = previous_feed.get("briefing", {
                "date": now_utc().strftime("%Y-%m-%d"),
                "headline": "Pulso diario de IA, FDM y emprendimiento",
                "intro": "Selección actualizada de noticias y papers científicos.",
                "bullets": [],
            })

    print("==> 4/4 Completando imágenes OpenGraph y guardando data/feed.json + feed.xml...")
    enrich_images(curated_news)

    payload = {
        "updated_at": now_utc().isoformat(),
        "edition": now_utc().strftime("%Y.%m.%d"),
        "ai_curated": bool(api_key),
        "briefing": briefing,
        "news": curated_news,
        "papers": curated_papers,
        "stats": {
            "news_count": len(curated_news),
            "papers_count": len(curated_papers),
            "sources_checked": len(cfg["news_feeds"]) + len(cfg["arxiv_queries"]) + len(cfg["openalex_queries"]),
        },
    }

    FEED_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    FEED_JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_rss(payload, cfg["site"])
    print(f"Listo: {len(curated_news)} noticias y {len(curated_papers)} papers guardados en {FEED_JSON_PATH}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
