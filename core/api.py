# -*- coding: utf-8 -*-
"""
core/api.py — MJ 生图 + Gemini 分析 核心 API 封装

所有模块共用，独立可运行（每个模块也可直接复制此文件）。

环境变量：
  KUNPO_API_KEY  或  ZIY_API_KEY  → API Key
"""

import os, sys, re, json, base64, io, time, datetime
import http.client as _hc, ssl as _ssl
from pathlib import Path

import requests
from PIL import Image

# ──────────────────────────────────────────────────────────────────
# 配置（与主程序保持同步）
# ──────────────────────────────────────────────────────────────────
API_BASE         = "https://llm.ziy.cc"
CHAT_URL         = API_BASE + "/v1/chat/completions"
GENERATIONS_URL  = API_BASE + "/v1/images/generations"

MODEL_IMAGINE    = "Image-MI"
MODEL_BLEND      = "Image-MI"
MODEL_GEMINI     = "google/gemini-3.1-flash-lite-preview"
MODEL_GEMINI_FB  = "google/gemini-2.0-flash"

MAX_RETRIES      = 2
CHAT_TIMEOUT     = 90
IMAGINE_TIMEOUT  = 300

MAX_LONG_EDGE       = 1024
MAX_FILE_KB         = 1024
MAX_BLEND_LONG_EDGE = 512
MAX_BLEND_KB        = 150

ASPECT_MAP = {
    "1:1":   "1024x1024",
    "4:3":   "1365x1024",
    "3:4":   "1024x1365",
    "16:9":  "1536x864",
    "9:16":  "864x1536",
    "3:2":   "1536x1024",
    "2:3":   "1024x1536",
    "21:9":  "1792x768",
}

# ──────────────────────────────────────────────────────────────────
# API Key
# ──────────────────────────────────────────────────────────────────

def get_api_key() -> str:
    return (os.environ.get("KUNPO_API_KEY") or
            os.environ.get("ZIY_API_KEY") or "")


def _headers() -> dict:
    key = get_api_key()
    if not key:
        raise RuntimeError("未配置 API Key，请设置环境变量 KUNPO_API_KEY 或 ZIY_API_KEY")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


# ──────────────────────────────────────────────────────────────────
# 图片工具
# ──────────────────────────────────────────────────────────────────

def downscale_image(path) -> bytes:
    img = Image.open(path)
    if img.mode in ("P", "PA"): img = img.convert("RGBA")
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3]); img = bg
    elif img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > MAX_LONG_EDGE:
        r = MAX_LONG_EDGE / max(w, h)
        img = img.resize((int(w*r), int(h*r)), Image.LANCZOS)
    quality = 85
    while True:
        buf = io.BytesIO(); img.save(buf, format="JPEG", quality=quality)
        if len(buf.getvalue()) // 1024 <= MAX_FILE_KB or quality <= 20: break
        quality -= 10
    return buf.getvalue()


def img_to_data_uri(path: str) -> str:
    raw = downscale_image(path)
    return "data:image/jpeg;base64," + base64.b64encode(raw).decode()


def img_to_data_uri_blend(path: str) -> str:
    img = Image.open(path)
    if img.mode in ("P", "PA"): img = img.convert("RGBA")
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3]); img = bg
    elif img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > MAX_BLEND_LONG_EDGE:
        r = MAX_BLEND_LONG_EDGE / max(w, h)
        img = img.resize((int(w*r), int(h*r)), Image.LANCZOS)
    quality = 80
    while True:
        buf = io.BytesIO(); img.save(buf, format="JPEG", quality=quality)
        if len(buf.getvalue()) // 1024 <= MAX_BLEND_KB or quality <= 20: break
        quality -= 10
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


# ──────────────────────────────────────────────────────────────────
# MJ 生图 API
# ──────────────────────────────────────────────────────────────────

def call_imagine(prompt: str, size: str = "1024x1024",
                 progress_cb=None) -> list:
    """文生图，返回 list[bytes]（4张图）"""
    return _call_generations(MODEL_IMAGINE, prompt, size,
                              "Image-MI 文生图", progress_cb)


def call_blend(data_uris: list, extra_prompt: str, size: str = "1024x1024",
               progress_cb=None) -> list:
    """图生图，data_uris 为 base64 data URI 列表，返回 list[bytes]"""
    prompt = extra_prompt.strip() or "超写实电影级图像，8K质感"
    return _call_generations(MODEL_BLEND, prompt, size,
                              "Image-MI 图生图", progress_cb,
                              base64_array=data_uris if data_uris else None)


def _call_generations(model: str, prompt: str, size: str = "1024x1024",
                       label: str = "", progress_cb=None,
                       base64_array: list = None) -> list:
    tag = label or model
    if progress_cb: progress_cb(f"[{tag}] 提交请求，等待生成…（约 45s）")
    payload = {"model": model, "prompt": prompt,
               "size": size, "quality": "standard", "n": 4}
    if base64_array:
        payload["base64Array"] = base64_array
    payload_bytes = json.dumps(payload).encode("utf-8")

    from urllib.parse import urlparse as _up
    _parsed = _up(GENERATIONS_URL)
    _host   = _parsed.netloc
    _path   = _parsed.path or "/v1/images/generations"
    _ctx    = _ssl.create_default_context()

    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        if progress_cb and attempt:
            progress_cb(f"[{tag}] 重试 {attempt}…")
        try:
            conn = _hc.HTTPSConnection(_host, timeout=IMAGINE_TIMEOUT, context=_ctx)
            conn.request("POST", _path, body=payload_bytes, headers={
                "Authorization": f"Bearer {get_api_key()}",
                "Content-Type":  "application/json",
                "Content-Length": str(len(payload_bytes)),
            })
            resp = conn.getresponse()
            try:
                raw = resp.read()
            except _hc.IncompleteRead as ir:
                raw = ir.partial
            conn.close()

            data = json.loads(raw.decode("utf-8"))
            if "error" in data:
                code = data["error"].get("code","")
                if code in ("do_request_failed","bad_response_status_code") and attempt < MAX_RETRIES:
                    time.sleep(6*(attempt+1)); continue
                raise RuntimeError(data["error"].get("message", str(data["error"])))

            urls = [item.get("url","") for item in data.get("data",[])]
            urls = [u for u in urls if u]
            if not urls:
                raise RuntimeError(f"API 返回空 URL 列表: {raw[:200]}")

            if progress_cb: progress_cb(f"[{tag}] 下载 {len(urls)} 张图片…")
            result = []
            for i, url in enumerate(urls):
                if progress_cb: progress_cb(f"[{tag}] 下载第 {i+1}/{len(urls)} 张…")
                r = requests.get(url, timeout=60)
                r.raise_for_status()
                result.append(r.content)
            return result

        except (_hc.HTTPException, ConnectionError, TimeoutError) as e:
            last_err = str(e)
            if attempt < MAX_RETRIES: time.sleep(6*(attempt+1))
        except RuntimeError:
            raise
        except Exception as e:
            last_err = str(e)
            if attempt < MAX_RETRIES: time.sleep(5)

    raise RuntimeError(f"MJ 多次重试失败: {last_err}")


# ──────────────────────────────────────────────────────────────────
# Gemini API
# ──────────────────────────────────────────────────────────────────

def _parse_gemini_content(data: dict) -> str:
    msg = (data.get("choices") or [{}])[0].get("message", {})
    content = msg.get("content", "")
    if isinstance(content, str) and content.strip():
        return content.strip()
    if isinstance(content, list):
        texts = [p.get("text","") for p in content if p.get("type")=="text"]
        if texts: return "\n".join(texts).strip()
    raise ValueError("Gemini 未返回有效文本")


def call_gemini_chat(user_content, progress_cb=None) -> str:
    """通用 Gemini 对话，user_content 可以是 str 或 list[dict]"""
    if progress_cb: progress_cb("[Gemini] 发送请求…")
    payload = {"model": MODEL_GEMINI, "messages": [
        {"role": "user", "content": user_content}
    ]}
    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            r = requests.post(CHAT_URL, json=payload, headers=_headers(),
                              timeout=CHAT_TIMEOUT)
            if r.status_code == 200:
                return _parse_gemini_content(r.json())
            if r.status_code in (422, 500) and payload["model"] != MODEL_GEMINI_FB:
                payload = dict(payload, model=MODEL_GEMINI_FB)
                continue
            last_err = f"HTTP {r.status_code}: {r.text[:200]}"
            time.sleep(3)
        except requests.Timeout:
            last_err = "请求超时"
            if attempt < MAX_RETRIES: time.sleep(5)
        except Exception as e:
            raise RuntimeError(f"Gemini 网络错误: {e}")
    raise RuntimeError(f"Gemini 多次重试失败: {last_err}")


def call_gemini_analyze_refs(image_paths: list,
                              meta_prompt: str,
                              inline_tags: list = None,
                              progress_cb=None) -> str:
    """分析参考图并生成 MJ 提示词。meta_prompt 已格式化完毕传入。"""
    n = len(image_paths)
    if n == 0: return ""
    if progress_cb: progress_cb(f"[Gemini] 编码 {n} 张参考图…")

    content_parts = [{"type": "text", "text": meta_prompt}]
    for i, path in enumerate(image_paths):
        if progress_cb: progress_cb(f"[Gemini] 编码图 {i+1}/{n}…")
        if inline_tags and i < len(inline_tags):
            content_parts.append({"type": "text", "text": inline_tags[i]})
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": img_to_data_uri(path)}
        })

    return call_gemini_chat(content_parts, progress_cb)


# ──────────────────────────────────────────────────────────────────
# 保存结果
# ──────────────────────────────────────────────────────────────────

def save_results(all_bytes: list, out_dir: Path,
                 batch_ts: str, suffix: str,
                 meta: dict) -> list:
    """保存生成的 4 张图 + meta.json，返回文件路径列表"""
    out_dir.mkdir(parents=True, exist_ok=True)
    ts_ms = int(time.time() * 1000) % 100000
    saved = []
    for i, img_bytes in enumerate(all_bytes):
        fname    = f"{batch_ts}_{suffix}_{ts_ms:05d}_{i+1}of{len(all_bytes)}_result.png"
        out_path = out_dir / fname
        out_path.write_bytes(img_bytes)
        saved.append(str(out_path))

    meta["outputs"] = saved
    meta_fname = f"{batch_ts}_{suffix}_{ts_ms:05d}_meta.json"
    (out_dir / meta_fname).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return saved
