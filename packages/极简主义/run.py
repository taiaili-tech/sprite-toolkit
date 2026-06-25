# -*- coding: utf-8 -*-
"""
MJ 主题生图种子包 — 独立引擎 run.py
======================================
每个主题包含此文件 + theme.json，两个文件即可独立运行。
代码完全自包含，无需安装除 requests / Pillow 以外的第三方库。

支持四种生图模式：
  txt2img   预设主题文生图（从 theme.json 下拉预设构建 prompt）
  img2img   三层参考图生图（风格图 + 主体图 + 可选主题图 → Gemini → MJ）
  free      自由创作（描述需求 → Gemini 生成30方向 → 用户选择 → MJ）
  auto      自动批量（文件夹图片 → Gemini 自动选材 → 多批次图生图）

运行方式：
  # 直接生图（CLI）
  python run.py --mode txt2img --struct 0 --light 0 --mood 0 --count 3

  # 自由创作
  python run.py --mode free --desc "我要一张未来城市" --select 1,3,5

  # 图生图
  python run.py --mode img2img --style a.jpg --subject b.jpg

  # 自动批量
  python run.py --mode auto --folder ./refs --batches 3

  # 列出预设选项
  python run.py --list-presets

  # 启动 API Server（接入聚合平台）
  python run.py --server --port 8001

环境变量：KUNPO_API_KEY 或 ZIY_API_KEY
"""

import sys, os, json, base64, io, re, time, datetime, argparse, uuid
import random, threading, concurrent.futures
from pathlib import Path

import requests
from PIL import Image

# ══════════════════════════════════════════════════════════════════
# 0. 加载本主题配置（theme.json 与本文件同目录）
# ══════════════════════════════════════════════════════════════════

_PACKAGE_DIR = Path(__file__).resolve().parent
_THEME_FILE  = _PACKAGE_DIR / "theme.json"

if not _THEME_FILE.exists():
    raise FileNotFoundError(
        f"未找到 theme.json，请确保与 run.py 在同一目录：{_THEME_FILE}")

with open(_THEME_FILE, encoding="utf-8") as _f:
    _T = json.load(_f)

THEME_TITLE    = _T.get("title", "MJ生图种子包")
THEME_KEYWORD  = _T.get("theme_keyword", "风格")
STRUCT_PRESETS = _T.get("struct_presets", [])
LIGHT_PRESETS  = _T.get("light_presets",  [])
MOOD_PRESETS   = _T.get("mood_presets",   [])
STYLE_SUFFIX   = _T.get("style_suffix",   "")
BLEND_DEFAULT  = _T.get("blend_default_prompt", "超写实电影级图像，8K画质")
META_SINGLE    = _T.get("meta_prompt_single",  "")
META_MULTI     = _T.get("meta_prompt_multi",   "")
META_LAYERS    = _T.get("meta_prompt_layers",  "")
LAYER_LABELS_4 = _T.get("layer_labels_4",      [])
LAYER_LABELS_M = _T.get("layer_labels_multi",  [])

# ══════════════════════════════════════════════════════════════════
# 1. API 配置
# ══════════════════════════════════════════════════════════════════

API_BASE        = "https://llm.ziy.cc"
CHAT_URL        = API_BASE + "/v1/chat/completions"
GENERATIONS_URL = API_BASE + "/v1/images/generations"

MODEL_MJ        = "Image-MI"
MODEL_GEMINI    = "google/gemini-3.1-flash-lite-preview"
MODEL_GEMINI_FB = "google/gemini-2.0-flash"

MAX_RETRIES      = 2
CHAT_TIMEOUT     = 90
IMAGINE_TIMEOUT  = 300

ASPECT_MAP = {
    "1:1":  "1024x1024", "4:3":  "1365x1024", "3:4":  "1024x1365",
    "16:9": "1536x864",  "9:16": "864x1536",  "3:2":  "1536x1024",
    "2:3":  "1024x1536", "21:9": "1792x768",
}

MAX_LONG_EDGE       = 1024
MAX_FILE_KB         = 1024
MAX_BLEND_LONG_EDGE = 512
MAX_BLEND_KB        = 150
SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
MAX_CANDIDATES = 12

# ══════════════════════════════════════════════════════════════════
# 2. API Key
# ══════════════════════════════════════════════════════════════════

def get_api_key() -> str:
    return (os.environ.get("KUNPO_API_KEY") or
            os.environ.get("ZIY_API_KEY") or "")

def _auth_headers() -> dict:
    key = get_api_key()
    if not key:
        raise RuntimeError("未配置 API Key，请设置环境变量 KUNPO_API_KEY 或 ZIY_API_KEY")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

# ══════════════════════════════════════════════════════════════════
# 3. 图片工具
# ══════════════════════════════════════════════════════════════════

def _to_jpeg_bytes(path: str, max_edge: int, max_kb: int) -> bytes:
    img = Image.open(path)
    if img.mode in ("P", "PA"): img = img.convert("RGBA")
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3]); img = bg
    elif img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > max_edge:
        r = max_edge / max(w, h)
        img = img.resize((int(w*r), int(h*r)), Image.LANCZOS)
    quality = 85
    while True:
        buf = io.BytesIO(); img.save(buf, format="JPEG", quality=quality)
        if len(buf.getvalue()) // 1024 <= max_kb or quality <= 20: break
        quality -= 10
    return buf.getvalue()

def img_to_data_uri(path: str) -> str:
    raw = _to_jpeg_bytes(path, MAX_LONG_EDGE, MAX_FILE_KB)
    return "data:image/jpeg;base64," + base64.b64encode(raw).decode()

def img_to_data_uri_blend(path: str) -> str:
    raw = _to_jpeg_bytes(path, MAX_BLEND_LONG_EDGE, MAX_BLEND_KB)
    return "data:image/jpeg;base64," + base64.b64encode(raw).decode()

# ══════════════════════════════════════════════════════════════════
# 4. MJ 生图 API
# ══════════════════════════════════════════════════════════════════

def _call_generations(prompt: str, size: str,
                       base64_array: list = None,
                       progress_cb=None) -> list:
    """调用 Image-MI，返回 list[bytes]（4 张图）"""
    import http.client as _hc, ssl as _ssl
    from urllib.parse import urlparse as _up

    tag = "Image-MI"
    if progress_cb: progress_cb(f"[{tag}] 提交请求…（约 45s）")

    payload = {"model": MODEL_MJ, "prompt": prompt,
               "size": size, "quality": "standard", "n": 4}
    if base64_array:
        payload["base64Array"] = base64_array
    payload_bytes = json.dumps(payload).encode("utf-8")

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
                code = data["error"].get("code", "")
                if code in ("do_request_failed", "bad_response_status_code") and attempt < MAX_RETRIES:
                    time.sleep(6*(attempt+1)); continue
                raise RuntimeError(data["error"].get("message", str(data["error"])))

            urls = [item.get("url","") for item in data.get("data",[]) if item.get("url")]
            if not urls:
                raise RuntimeError(f"API 返回空 URL 列表: {raw[:200]}")

            if progress_cb: progress_cb(f"[{tag}] 下载 {len(urls)} 张图…")
            result = []
            for i, url in enumerate(urls):
                if progress_cb: progress_cb(f"[{tag}] 下载 {i+1}/{len(urls)}…")
                r = requests.get(url, timeout=60); r.raise_for_status()
                result.append(r.content)
            return result

        except (_hc.HTTPException, ConnectionError, TimeoutError) as e:
            last_err = str(e)
            if attempt < MAX_RETRIES: time.sleep(6*(attempt+1))
        except RuntimeError: raise
        except Exception as e:
            last_err = str(e)
            if attempt < MAX_RETRIES: time.sleep(5)

    raise RuntimeError(f"MJ 多次重试失败: {last_err}")


def call_txt2img(prompt: str, size: str, progress_cb=None) -> list:
    return _call_generations(prompt, size, progress_cb=progress_cb)

def call_img2img(prompt: str, size: str, data_uris: list, progress_cb=None) -> list:
    return _call_generations(prompt, size, base64_array=data_uris, progress_cb=progress_cb)

# ══════════════════════════════════════════════════════════════════
# 5. Gemini API
# ══════════════════════════════════════════════════════════════════

def _gemini_chat(content, progress_cb=None) -> str:
    """通用 Gemini 对话，content 为 str 或 list[dict]"""
    if progress_cb: progress_cb("[Gemini] 发送请求…")
    payload = {"model": MODEL_GEMINI, "messages": [{"role": "user", "content": content}]}
    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            r = requests.post(CHAT_URL, json=payload, headers=_auth_headers(),
                              timeout=CHAT_TIMEOUT)
            if r.status_code == 200:
                msg = r.json()["choices"][0]["message"]["content"]
                if isinstance(msg, str): return msg.strip()
                if isinstance(msg, list):
                    return "\n".join(p.get("text","") for p in msg if p.get("type")=="text").strip()
                raise ValueError("Gemini 返回内容格式异常")
            if r.status_code in (422, 500) and payload["model"] != MODEL_GEMINI_FB:
                payload = dict(payload, model=MODEL_GEMINI_FB); continue
            last_err = f"HTTP {r.status_code}: {r.text[:200]}"; time.sleep(3)
        except requests.Timeout:
            last_err = "超时"
            if attempt < MAX_RETRIES: time.sleep(5)
        except Exception as e:
            raise RuntimeError(f"Gemini 网络错误: {e}")
    raise RuntimeError(f"Gemini 多次重试失败: {last_err}")


def gemini_analyze_refs(image_paths: list, use_layers: bool = False,
                         progress_cb=None) -> str:
    """分析参考图，生成该主题风格的 MJ 提示词"""
    n = len(image_paths)
    if not n: return ""

    # 选择模板并格式化
    if use_layers and META_LAYERS:
        labels = LAYER_LABELS_4 or [f"image{i+1}" for i in range(n)]
        roles  = "\n".join(f"- {labels[i]}" for i in range(n))
        tc     = ("\n- @image3 与 @image4 共同定义场景意境"
                  if max(0, n-2) >= 2 else "")
        meta   = META_LAYERS.format(n=n, roles=roles, theme_clause=tc)
        tags   = [
            "【第1张图 = @image1 风格图，仅提供视觉风格/光影色调，不作为主体】",
            "【第2张图 = @image2 主体控制图，画面核心主体形态只能来自此图】",
            "【第3张图 = @image3 内容主题图，定义场景意境】",
            "【第4张图 = @image4 内容主题图2，补充场景细节】",
        ]
    elif n == 1 and META_SINGLE:
        meta, tags = META_SINGLE, []
    elif META_MULTI:
        labels = LAYER_LABELS_M or [f"image{i+1}" for i in range(n)]
        roles  = "\n".join(f"- {labels[i]}：参考图 {i+1}" for i in range(n))
        meta, tags = META_MULTI.format(n=n, roles=roles), []
    else:
        meta = ("分析这些参考图，生成适合该风格的 Midjourney 英文提示词，"
                "直接输出提示词，不含 MJ 参数。")
        tags = []

    if progress_cb: progress_cb(f"[Gemini] 编码 {n} 张参考图…")
    content_parts = [{"type": "text", "text": meta}]
    for i, path in enumerate(image_paths):
        if progress_cb: progress_cb(f"[Gemini] 编码图 {i+1}/{n}…")
        if tags and i < len(tags):
            content_parts.append({"type": "text", "text": tags[i]})
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": img_to_data_uri(path)}
        })

    return _gemini_chat(content_parts, progress_cb)


# ── 自由创作两个 Gemini 调用 ──────────────────────────────────────

_PROMPT_FREE_OPTIONS = """\
你是专业的视觉内容策划师。用户描述了想要的图像类型，你需要生成30个具体的内容方向供选择。

当前风格主题：{theme_keyword}

规则：
- 每个方向10-20字中文描述，与当前风格主题相符
- 方向之间有明显差异（不同场景/时间/氛围/情绪/地点）
- 只输出编号+描述，格式严格：
  1. xxx
  2. xxx
  ...30. xxx
- 禁止解释和分类标题

用户需求：{user_input}\
"""

_PROMPT_TO_MJ = """\
将以下中文场景描述转化为专业的 Midjourney 英文提示词。

当前风格主题：{theme_keyword}

要求：
- 纯英文，20-30词
- 包含：场景主体、光线氛围、构图风格
- 末尾原样追加风格后缀（直接拼接，不修改）
- 只输出提示词文本，不含 --ar/--v 等参数

中文描述：{option}
风格后缀：{style_suffix}\
"""

def gemini_free_options(user_input: str, progress_cb=None) -> list:
    prompt = _PROMPT_FREE_OPTIONS.format(
        theme_keyword=THEME_KEYWORD, user_input=user_input)
    text = _gemini_chat(prompt, progress_cb)
    options = []
    for line in text.split("\n"):
        m = re.match(r"^\d+[.、。]\s*(.+)$", line.strip())
        if m: options.append(m.group(1).strip())
    return options

def gemini_option_to_prompt(option: str, progress_cb=None) -> str:
    prompt = _PROMPT_TO_MJ.format(
        theme_keyword=THEME_KEYWORD,
        option=option,
        style_suffix=STYLE_SUFFIX)
    return _gemini_chat(prompt, progress_cb)


# ── 自动选材 Gemini 调用 ──────────────────────────────────────────

_PROMPT_AUTO_SELECT = """\
你是 AI 生图素材选材专家。我给你 {n} 张候选图片，编号 image1~image{n}。
主题关键词：「{theme}」

从这 {n} 张图中，为三层结构选出最合适的图片：
- 风格图（1张，必选）：最能体现光影、氛围、整体视觉风格
- 主体控制图（1张，必选）：最能代表核心结构形态、几何特征
- 主题图（0~2张，可选）：最能体现场景意境、情绪氛围

输出格式（只输出 JSON，不输出其他）：
{{"style":"imageX","subject":"imageX","themes":["imageX"]}}
"""

def gemini_auto_select(image_paths: list, progress_cb=None) -> dict:
    n = len(image_paths)
    prompt_text = _PROMPT_AUTO_SELECT.format(n=n, theme=THEME_KEYWORD)
    content_parts = [{"type": "text", "text": prompt_text}]
    for i, path in enumerate(image_paths):
        content_parts.append({"type": "text", "text": f"image{i+1}："})
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": img_to_data_uri(path)}
        })
    result_text = _gemini_chat(content_parts, progress_cb)
    m = re.search(r'\{.*?\}', result_text, re.DOTALL)
    if not m:
        shuffled = image_paths[:]
        random.shuffle(shuffled)
        return {"style": shuffled[0], "subject": shuffled[1],
                "themes": shuffled[2:4] if len(shuffled) > 2 else []}
    parsed = json.loads(m.group(0))
    idx_map = {f"image{i+1}": p for i, p in enumerate(image_paths)}
    return {
        "style":   idx_map.get(parsed.get("style",""),  image_paths[0]),
        "subject": idx_map.get(parsed.get("subject",""), image_paths[min(1,len(image_paths)-1)]),
        "themes":  [idx_map[t] for t in parsed.get("themes",[]) if t in idx_map],
    }

# ══════════════════════════════════════════════════════════════════
# 6. 保存结果
# ══════════════════════════════════════════════════════════════════

def save_results(all_bytes: list, suffix: str,
                 meta: dict, output_dir: str = "") -> list:
    out_root = Path(output_dir) if output_dir else _PACKAGE_DIR / "output"
    today    = datetime.datetime.now().strftime("%Y-%m-%d")
    out_dir  = out_root / today
    out_dir.mkdir(parents=True, exist_ok=True)

    batch_ts = meta.get("batch_ts", datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
    ts_ms    = int(time.time() * 1000) % 100000
    saved    = []
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

# ══════════════════════════════════════════════════════════════════
# 7. 四种生图模式
# ══════════════════════════════════════════════════════════════════

def run_txt2img(struct_idx: int = 0, light_idx: int = 0, mood_idx: int = 0,
                extra: str = "", count: int = 1,
                ar: str = "16:9", stylize: int = 850, version: str = "7",
                output_dir: str = "", progress_cb=None) -> dict:
    """预设主题文生图"""
    def _log(m): progress_cb(m) if progress_cb else print(m)

    struct  = STRUCT_PRESETS[struct_idx] if struct_idx < len(STRUCT_PRESETS) else ""
    light   = LIGHT_PRESETS [light_idx]  if light_idx  < len(LIGHT_PRESETS)  else ""
    mood    = MOOD_PRESETS  [mood_idx]   if mood_idx   < len(MOOD_PRESETS)   else ""
    size    = ASPECT_MAP.get(ar, "1024x1024")
    batch_ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    parts   = [p for p in [struct, light, mood, STYLE_SUFFIX, extra.strip()] if p]
    base    = ", ".join(parts)
    prompt  = f"{base} --ar {ar} --v {version} --stylize {stylize} --q 2"
    _log(f"[文生图] 提交 {count} 批次，提示词: {prompt[:80]}…")

    all_files = []
    for i in range(count):
        _log(f"[{i+1}/{count}] 生图中…")
        img_bytes = call_txt2img(prompt, size, _log)
        saved = save_results(img_bytes, "txt2img",
                             {"batch_ts": batch_ts, "mode": "txt2img",
                              "theme": THEME_KEYWORD, "prompt": prompt,
                              "ar": ar, "stylize": stylize, "version": version},
                             output_dir)
        all_files.extend(saved)
        _log(f"[{i+1}/{count}] 完成，{len(saved)} 张")

    return {"total_images": len(all_files), "files": all_files,
            "output_dir": str(Path(output_dir or _PACKAGE_DIR / "output"))}


def run_img2img(style_path: str, subject_path: str,
                theme_paths: list = None, extra: str = "",
                ar: str = "9:16", stylize: int = 900, version: str = "7",
                output_dir: str = "", progress_cb=None) -> dict:
    """三层参考图生图（Gemini 反推提示词 → Image-MI）"""
    def _log(m): progress_cb(m) if progress_cb else print(m)

    ref_paths = [style_path, subject_path] + (theme_paths or [])
    ref_paths = [p for p in ref_paths if p and Path(p).exists()]
    if len(ref_paths) < 2:
        raise ValueError("至少需要风格图和主体控制图两张参考图")

    _log(f"[图生图] Step 1/2: Gemini 分析 {len(ref_paths)} 张参考图…")
    gemini_prompt = gemini_analyze_refs(ref_paths, use_layers=True, progress_cb=_log)

    mj_params    = f" --ar {ar} --v {version} --stylize {stylize} --q 2"
    final_prompt = gemini_prompt.rstrip(", \n") + mj_params
    if extra.strip():
        final_prompt += "\n" + extra.strip()

    _log(f"[图生图] Step 2/2: Image-MI 生图…")
    # 主体图优先（调至首位，提高形态权重）
    mi_paths = ([ref_paths[1], ref_paths[0]] + ref_paths[2:]
                if len(ref_paths) >= 2 else ref_paths)
    data_uris = [img_to_data_uri_blend(p) for p in mi_paths]
    size      = ASPECT_MAP.get(ar, "864x1536")
    img_bytes = call_img2img(final_prompt, size, data_uris, _log)

    batch_ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    saved = save_results(img_bytes, "img2img",
                         {"batch_ts": batch_ts, "mode": "img2img",
                          "theme": THEME_KEYWORD, "prompt": final_prompt,
                          "gemini_prompt": gemini_prompt,
                          "ref_paths": ref_paths,
                          "ar": ar, "stylize": stylize, "version": version},
                         output_dir)
    _log(f"[图生图] 完成，保存 {len(saved)} 张")
    return {"total_images": len(saved), "files": saved,
            "prompt": final_prompt, "gemini_prompt": gemini_prompt,
            "output_dir": str(Path(output_dir or _PACKAGE_DIR / "output"))}


def run_free_gen(user_input: str, selected_indices: list = None,
                 style_image: str = "",
                 ar: str = "16:9", stylize: int = 900, version: str = "7",
                 output_dir: str = "", progress_cb=None) -> dict:
    """自由创作：需求描述 → 30方向选择 → 转 MJ 提示词 → 批量生图"""
    def _log(m): progress_cb(m) if progress_cb else print(m)

    _log(f"[自由创作] 生成内容方向：{user_input}")
    options = gemini_free_options(user_input, _log)
    _log(f"[自由创作] 共 {len(options)} 个方向")

    selected = ([options[i-1] for i in (selected_indices or [])
                 if 1 <= i <= len(options)]
                if selected_indices else options)
    _log(f"[自由创作] 选中 {len(selected)} 个方向，转换提示词…")

    size     = ASPECT_MAP.get(ar, "1024x1024")
    batch_ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    all_results = []

    for i, opt in enumerate(selected):
        _log(f"[{i+1}/{len(selected)}] 转换：{opt[:30]}…")
        mj_prompt   = gemini_option_to_prompt(opt, _log)
        full_prompt = (mj_prompt.rstrip(", \n") +
                       f" --ar {ar} --v {version} --stylize {stylize} --q 2")

        if style_image and Path(style_image).exists():
            _log(f"[{i+1}/{len(selected)}] 风格融合生图…")
            img_bytes = call_img2img(full_prompt, size,
                                     [img_to_data_uri_blend(style_image)], _log)
            suffix = "free_blend"
        else:
            _log(f"[{i+1}/{len(selected)}] 文生图…")
            img_bytes = call_txt2img(full_prompt, size, _log)
            suffix = "free"

        saved = save_results(img_bytes, suffix,
                             {"batch_ts": batch_ts, "mode": suffix,
                              "theme": THEME_KEYWORD, "option": opt,
                              "prompt": full_prompt,
                              "ar": ar, "stylize": stylize, "version": version},
                             output_dir)
        all_results.append({"option": opt, "prompt": full_prompt, "files": saved})
        _log(f"[{i+1}/{len(selected)}] 完成，{len(saved)} 张")

    total = sum(len(r["files"]) for r in all_results)
    return {"total_images": total, "results": all_results,
            "options": options,
            "output_dir": str(Path(output_dir or _PACKAGE_DIR / "output"))}


def run_auto_batch(folder_path: str, batches: int = 3,
                   ar: str = "9:16", stylize: int = 900, version: str = "7",
                   output_dir: str = "", progress_cb=None) -> dict:
    """自动批量：文件夹图片 → Gemini 自动选材 → 多批次图生图"""
    def _log(m): progress_cb(m) if progress_cb else print(m)

    folder = Path(folder_path)
    all_images = [str(p) for p in sorted(folder.iterdir())
                  if p.suffix.lower() in SUPPORTED_EXTS]
    if len(all_images) < 2:
        raise ValueError(f"图片不足（至少2张），当前 {len(all_images)} 张")

    _log(f"[自动批量] {folder_path} 共 {len(all_images)} 张，执行 {batches} 批次")
    size     = ASPECT_MAP.get(ar, "864x1536")
    batch_ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    all_results = []

    for bi in range(batches):
        _log(f"\n[批次 {bi+1}/{batches}] 随机抽取候选图…")
        candidates = random.sample(all_images, min(MAX_CANDIDATES, len(all_images)))
        sel = gemini_auto_select(candidates, _log)

        ref_paths = [sel["style"], sel["subject"]] + sel["themes"]
        _log(f"[批次 {bi+1}] 选材：风格={Path(sel['style']).name}  "
             f"主体={Path(sel['subject']).name}  主题={[Path(t).name for t in sel['themes']]}")

        _log(f"[批次 {bi+1}] Gemini 反推提示词…")
        gemini_prompt = gemini_analyze_refs(ref_paths, use_layers=True, progress_cb=_log)
        final_prompt  = (gemini_prompt.rstrip(", \n") +
                         f" --ar {ar} --v {version} --stylize {stylize} --q 2")

        mi_paths  = ([ref_paths[1], ref_paths[0]] + ref_paths[2:]
                     if len(ref_paths) >= 2 else ref_paths)
        data_uris = [img_to_data_uri_blend(p) for p in mi_paths]

        _log(f"[批次 {bi+1}] Image-MI 生图…")
        img_bytes = call_img2img(final_prompt, size, data_uris, _log)
        saved = save_results(img_bytes, f"auto_b{bi+1}",
                             {"batch_ts": batch_ts, "mode": "auto",
                              "theme": THEME_KEYWORD, "batch": bi+1,
                              "prompt": final_prompt,
                              "gemini_prompt": gemini_prompt,
                              "ref_paths": ref_paths,
                              "ar": ar, "stylize": stylize, "version": version},
                             output_dir)
        all_results.append({"batch": bi+1, "files": saved, "prompt": final_prompt})
        _log(f"[批次 {bi+1}] 完成，{len(saved)} 张")

    total = sum(len(r["files"]) for r in all_results)
    return {"total_images": total, "results": all_results,
            "output_dir": str(Path(output_dir or _PACKAGE_DIR / "output"))}

# ══════════════════════════════════════════════════════════════════
# 8. FastAPI Server（接入聚合平台）
# ══════════════════════════════════════════════════════════════════

def start_server(host: str = "0.0.0.0", port: int = 8000):
    try:
        from fastapi import FastAPI
        import uvicorn
    except ImportError:
        print("请先安装：pip install fastapi uvicorn"); sys.exit(1)

    from pydantic import BaseModel
    from typing import List, Optional

    app = FastAPI(title=THEME_TITLE, version="1.0",
                  description=f"「{THEME_KEYWORD}」风格生图模块")
    _tasks: dict = {}

    def _run_task(task_id: str, fn, kwargs: dict):
        logs = []
        try:
            _tasks[task_id]["status"] = "running"
            result = fn(**kwargs, progress_cb=lambda m: logs.append(m))
            _tasks[task_id].update({"status": "done", "result": result, "logs": logs})
        except Exception as e:
            _tasks[task_id].update({"status": "failed", "error": str(e), "logs": logs})

    class Txt2ImgReq(BaseModel):
        struct_idx: int = 0; light_idx: int = 0; mood_idx: int = 0
        extra: str = ""; count: int = 1; ar: str = "16:9"
        stylize: int = 850; version: str = "7"; output_dir: str = ""

    class Img2ImgReq(BaseModel):
        style_path: str; subject_path: str
        theme_paths: List[str] = []; extra: str = ""
        ar: str = "9:16"; stylize: int = 900; version: str = "7"; output_dir: str = ""

    class FreeReq(BaseModel):
        user_input: str; selected_indices: List[int] = []
        style_image: str = ""; ar: str = "16:9"
        stylize: int = 900; version: str = "7"; output_dir: str = ""

    class AutoReq(BaseModel):
        folder_path: str; batches: int = 3; ar: str = "9:16"
        stylize: int = 900; version: str = "7"; output_dir: str = ""

    @app.get("/health")
    def health():
        return {"status": "ok", "theme": THEME_KEYWORD, "title": THEME_TITLE}

    @app.get("/presets")
    def presets():
        return {"struct": STRUCT_PRESETS, "light": LIGHT_PRESETS, "mood": MOOD_PRESETS,
                "style_suffix": STYLE_SUFFIX, "theme_keyword": THEME_KEYWORD}

    def _submit(fn, kwargs) -> dict:
        task_id = str(uuid.uuid4())
        _tasks[task_id] = {"status": "pending", "logs": [], "result": None}
        threading.Thread(target=_run_task, args=(task_id, fn, kwargs), daemon=True).start()
        return {"task_id": task_id, "status": "pending"}

    @app.post("/generate/txt2img")
    def api_txt2img(r: Txt2ImgReq):
        return _submit(run_txt2img, r.model_dump())

    @app.post("/generate/img2img")
    def api_img2img(r: Img2ImgReq):
        return _submit(run_img2img, r.model_dump())

    @app.post("/generate/free")
    def api_free(r: FreeReq):
        return _submit(run_free_gen, r.model_dump())

    @app.post("/generate/auto")
    def api_auto(r: AutoReq):
        return _submit(run_auto_batch, r.model_dump())

    @app.post("/free/options")
    def api_free_options(body: dict):
        """仅获取30个内容方向，不生图"""
        opts = gemini_free_options(body.get("user_input",""))
        return {"options": opts, "count": len(opts)}

    @app.get("/status/{task_id}")
    def api_status(task_id: str):
        return _tasks.get(task_id, {"error": "task not found"})

    print(f"\n{'='*50}")
    print(f"  {THEME_TITLE}")
    print(f"  主题关键词：{THEME_KEYWORD}")
    print(f"  API 文档：http://{host}:{port}/docs")
    print(f"{'='*50}\n")
    uvicorn.run(app, host=host, port=port)

# ══════════════════════════════════════════════════════════════════
# 9. CLI 入口
# ══════════════════════════════════════════════════════════════════

def _cli():
    parser = argparse.ArgumentParser(
        description=f"{THEME_TITLE} — 独立生图引擎",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
示例：
  python run.py --list-presets
  python run.py --mode txt2img --struct 0 --light 2 --mood 1 --count 3
  python run.py --mode img2img --style a.jpg --subject b.jpg
  python run.py --mode free --desc "我要一张{THEME_KEYWORD}风格图" --select 1,3,5
  python run.py --mode auto --folder ./refs --batches 3
  python run.py --server --port 8001
        """
    )
    parser.add_argument("--mode", choices=["txt2img","img2img","free","auto"],
                        help="生图模式")
    parser.add_argument("--list-presets", action="store_true",
                        help="列出所有预设选项")

    # txt2img 参数
    parser.add_argument("--struct",  default="0",  type=int)
    parser.add_argument("--light",   default="0",  type=int)
    parser.add_argument("--mood",    default="0",  type=int)
    parser.add_argument("--extra",   default="")
    parser.add_argument("--count",   default="1",  type=int, help="批次数量（每批4张）")

    # img2img 参数
    parser.add_argument("--style",   default="",   help="风格参考图路径")
    parser.add_argument("--subject", default="",   help="主体控制图路径")
    parser.add_argument("--themes",  default="",   help="主题图路径，逗号分隔（可选）")

    # free 参数
    parser.add_argument("--desc",    default="",   help="图像需求描述")
    parser.add_argument("--select",  default="",   help="选中方向序号，逗号分隔（空=全选）")
    parser.add_argument("--list-options", action="store_true",
                        help="只列出30个方向，不生图")

    # auto 参数
    parser.add_argument("--folder",  default="",   help="参考图文件夹路径")
    parser.add_argument("--batches", default="3",  type=int)

    # 公共参数
    parser.add_argument("--ar",      default="16:9")
    parser.add_argument("--stylize", default="900", type=int)
    parser.add_argument("--version", default="7")
    parser.add_argument("--output",  default="",   help="输出目录（默认 ./output）")

    # server 参数
    parser.add_argument("--server",  action="store_true", help="启动 API Server 模式")
    parser.add_argument("--host",    default="0.0.0.0")
    parser.add_argument("--port",    default="8000", type=int)

    args = parser.parse_args()

    if args.server:
        start_server(args.host, args.port)
        return

    if args.list_presets:
        print(f"\n── {THEME_KEYWORD} · 结构预设 ──")
        for i, p in enumerate(STRUCT_PRESETS): print(f"  {i:2d}: {p}")
        print(f"\n── {THEME_KEYWORD} · 光效预设 ──")
        for i, p in enumerate(LIGHT_PRESETS):  print(f"  {i:2d}: {p}")
        print(f"\n── {THEME_KEYWORD} · 情绪预设 ──")
        for i, p in enumerate(MOOD_PRESETS):   print(f"  {i:2d}: {p}")
        return

    if not get_api_key():
        print("❌ 未设置 API Key"); sys.exit(1)

    if args.mode == "txt2img":
        result = run_txt2img(
            struct_idx=args.struct, light_idx=args.light, mood_idx=args.mood,
            extra=args.extra, count=args.count,
            ar=args.ar, stylize=args.stylize, version=args.version,
            output_dir=args.output, progress_cb=print)

    elif args.mode == "img2img":
        if not args.style or not args.subject:
            print("--mode img2img 需要 --style 和 --subject"); sys.exit(1)
        theme_paths = [p.strip() for p in args.themes.split(",") if p.strip()]
        result = run_img2img(
            style_path=args.style, subject_path=args.subject,
            theme_paths=theme_paths, extra=args.extra,
            ar=args.ar, stylize=args.stylize, version=args.version,
            output_dir=args.output, progress_cb=print)

    elif args.mode == "free":
        if args.list_options:
            if not args.desc: print("请用 --desc 指定描述"); sys.exit(1)
            opts = gemini_free_options(args.desc, progress_cb=print)
            print(f"\n── 30个内容方向（主题：{THEME_KEYWORD}）──")
            for i, o in enumerate(opts, 1): print(f"{i:2d}. {o}")
            return
        if not args.desc: print("请用 --desc 指定描述"); sys.exit(1)
        indices = ([int(x) for x in args.select.split(",") if x.strip().isdigit()]
                   if args.select else [])
        result = run_free_gen(
            user_input=args.desc, selected_indices=indices,
            ar=args.ar, stylize=args.stylize, version=args.version,
            output_dir=args.output, progress_cb=print)

    elif args.mode == "auto":
        if not args.folder: print("请用 --folder 指定图片文件夹"); sys.exit(1)
        result = run_auto_batch(
            folder_path=args.folder, batches=args.batches,
            ar=args.ar, stylize=args.stylize, version=args.version,
            output_dir=args.output, progress_cb=print)
    else:
        parser.print_help(); return

    print(f"\n✓ 完成！共生成 {result.get('total_images', 0)} 张图")
    print(f"输出目录：{result.get('output_dir', '')}")


if __name__ == "__main__":
    _cli()
