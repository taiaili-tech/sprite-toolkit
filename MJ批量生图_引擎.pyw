# -*- coding: utf-8 -*-
"""
MJ 巨构批量生图工具 v1.0
文生图 + 图生图双模式批量生产流水线

API：POST /v1/images/generations  model=Image-MI（腾讯云 AIART Midjourney，一次出 4 张）
图生图：参考图先上传获取 CDN URL，拼入 prompt 前缀后统一调用 generations 接口
"""

import sys, os, json, base64, io, datetime, time, re, threading
import concurrent.futures
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk

import requests

# ── Windows DPI 处理 ──────────────────────────────────────────────
if sys.platform == "win32":
    try:
        import ctypes as _ctypes
        _ctypes.windll.shcore.SetProcessDpiAwareness(0)
    except Exception:
        pass

# ══════════════════════════════════════════════════════════════════
# 源码运行警告
# ══════════════════════════════════════════════════════════════════
if not getattr(sys, 'frozen', False):
    def _show_warn():
        d = tk.Tk(); d.title("⚠️ 注意：开发源码版本")
        d.resizable(False, False); d.attributes("-topmost", True); d.grab_set()
        d.update_idletasks()
        w, h = 420, 240
        x = (d.winfo_screenwidth()  - w) // 2
        y = (d.winfo_screenheight() - h) // 2
        d.geometry(f"{w}x{h}+{x}+{y}")
        tk.Label(d, text="⚠️", font=("", 26), fg="#f59e0b").pack(pady=(16, 0))
        _exe_name = Path(__file__).stem + ".exe"
        tk.Label(d,
            text="您正在运行开发源码版本。\n\n"
                 "正式版本位于：\n"
                 f"  dist\\{_exe_name}\n\n"
                 "如非调试用途，建议使用 dist 中的 .exe。",
            justify="left", wraplength=380, font=("Microsoft YaHei UI", 9)
        ).pack(padx=20, pady=(4, 0))
        result = [False]
        def yes(): result[0] = True;  d.destroy()
        def no():  result[0] = False; d.destroy()
        bf = tk.Frame(d); bf.pack(pady=14)
        tk.Button(bf, text="继续运行（开发调试）", width=22, command=yes).pack(side="left", padx=8)
        tk.Button(bf, text="退出", width=10, bg="#ef4444", fg="white",
                  activebackground="#dc2626", activeforeground="white",
                  command=no).pack(side="left", padx=8)
        d.bind("<Return>", lambda e: yes()); d.bind("<Escape>", lambda e: no())
        d.protocol("WM_DELETE_WINDOW", no); d.mainloop()
        return result[0]
    if not _show_warn():
        sys.exit(0)

# ══════════════════════════════════════════════════════════════════
# API Key 封装（RC4 + SHA256，同 v2.3）
# ══════════════════════════════════════════════════════════════════
_F0 = bytes([0x3f, 0x8c, 0xe7, 0x1a, 0x52, 0xb4])
_F1 = bytes([0x29, 0x6d, 0xf0, 0x83, 0x5c, 0xa1])
_F2 = bytes([0x3e, 0x97, 0x4b, 0x71, 0xc8, 0x2d])

def _rc4(key, data):
    import hashlib as _hl
    S = list(range(256)); j = 0
    for i in range(256):
        j = (j + S[i] + key[i % len(key)]) % 256
        S[i], S[j] = S[j], S[i]
    i = j = 0; out = []
    for byte in data:
        i = (i + 1) % 256; j = (j + S[i]) % 256
        S[i], S[j] = S[j], S[i]
        out.append(byte ^ S[(S[i] + S[j]) % 256])
    return bytes(out)

def _dk(s):
    import hashlib as _hl
    pwd = _F0 + _F1 + _F2
    key = _hl.sha256(pwd).digest()
    return _rc4(key, base64.b64decode(s)).decode('utf-8')

_EMBEDDED_KEY = "XUCkCWo3SWYMQl4g5viekOAqxByB5cRlgtlZo6wSEGgO4P/Db8VdtpsygxbUKokUPboe"

API_BASE         = "https://llm.ziy.cc"
CHAT_URL         = API_BASE + "/v1/chat/completions"
GENERATIONS_URL  = API_BASE + "/v1/images/generations"   # 所有 MJ 生图统一接口（同步）

# ── 模型名 ────────────────────────────────────────────────────────
# 腾讯云 AIART · Image-MI：一次请求返回 4 张图 URL，$0.069/次
MODEL_IMAGINE   = "Image-MI"     # 文生图（一次出4张）
MODEL_BLEND     = "Image-MI"     # 图生图（参考图 URL 拼入 prompt，同模型）
MODEL_UPLOADS   = "mj_uploads"   # 预留：本地图上传（暂未启用）
MODEL_GEMINI    = "google/gemini-3.1-flash-lite-preview"
MODEL_GEMINI_FB = "google/gemini-2.0-flash"


APP_VERSION = "v2.0"

# ══════════════════════════════════════════════════════════════════════════════
# 主题全局变量（由 JSON 种子包填充，不要手动修改）
# ══════════════════════════════════════════════════════════════════════════════
APP_TITLE          = "MJ批量生图引擎 v2.0"
STYLE_SUFFIX       = ""
_BLEND_DEFAULT_PROMPT  = "超写实电影级图像，8K质感，a single lone figure for scale，only one single lone figure"
_THEME_KEYWORD         = "风格"
_THEME_NAME            = ""   # 当前加载的主题文件名（如"巨构主义"），用于报告标签
_META_PROMPT_LAYERS    = ""
_META_PROMPT_MULTI     = ""
_META_PROMPT_SINGLE    = ""
_LAYER_LABELS_4    = [
    "image1：风格图（整体视觉感、光影色调、构图形式）",
    "image2：结构图（主体结构状态、细节分布、高度关系）",
    "image3：氛围场景图（场景环境、天空背景）",
    "image4：氛围场景图2（补充场景细节）",
]

# 三层模式下每张图前插入的定位绑定标签（每图紧邻一个文字节点，强制模型绑定角色）
_LAYER_INLINE_TAGS = [
    "【以下第1张图 = @image1 风格图，仅提供视觉风格/光影色调/构图逻辑，不作为画面主体】",
    "【以下第2张图 = @image2 主体控制图，画面核心主体形态只能来自这张图，"
    "必须精确还原其轮廓与几何特征，提示词开头必须描述这张图的形态】",
    "【以下第3张图 = @image3 内容主题图，定义场景意境与情绪氛围】",
    "【以下第4张图 = @image4 内容主题图2，补充场景细节与视觉元素】",
]
_LAYER_LABELS_MULTI = [
    "image1：构图 & 参考风格",
    "image2：光影 & 氛围参考",
    "image3：结构形态参考",
    "image4：材质 & 色彩参考",
]

def _load_theme(json_path: str):
    """从 JSON 种子包加载主题配置，覆盖所有全局风格变量"""
    global APP_TITLE, STRUCT_PRESETS, LIGHT_PRESETS, MOOD_PRESETS, STYLE_SUFFIX
    global _BLEND_DEFAULT_PROMPT, _THEME_KEYWORD, _THEME_NAME
    global _META_PROMPT_LAYERS, _META_PROMPT_MULTI, _META_PROMPT_SINGLE
    global _LAYER_LABELS_4, _LAYER_LABELS_MULTI
    _THEME_NAME = Path(json_path).stem   # e.g. "巨构主义"
    import json as _json2
    with open(json_path, 'r', encoding='utf-8') as _f:
        t = _json2.load(_f)
    APP_TITLE             = t.get("title", APP_TITLE)
    STRUCT_PRESETS        = t.get("struct_presets",  STRUCT_PRESETS)
    LIGHT_PRESETS         = t.get("light_presets",   LIGHT_PRESETS)
    MOOD_PRESETS          = t.get("mood_presets",    MOOD_PRESETS)
    STYLE_SUFFIX          = t.get("style_suffix",    STYLE_SUFFIX)
    _BLEND_DEFAULT_PROMPT = t.get("blend_default_prompt", _BLEND_DEFAULT_PROMPT)
    _THEME_KEYWORD        = t.get("theme_keyword",   _THEME_KEYWORD)
    _META_PROMPT_LAYERS   = t.get("meta_prompt_layers",   _META_PROMPT_LAYERS)
    _META_PROMPT_MULTI    = t.get("meta_prompt_multi",    _META_PROMPT_MULTI)
    _META_PROMPT_SINGLE   = t.get("meta_prompt_single",   _META_PROMPT_SINGLE)
    _LAYER_LABELS_4       = t.get("layer_labels_4",  _LAYER_LABELS_4)
    _LAYER_LABELS_MULTI   = t.get("layer_labels_multi", _LAYER_LABELS_MULTI)


def _select_theme_at_startup() -> str | None:
    """
    扫描 themes/ 目录，让用户选择种子包；返回所选 JSON 路径。
    若只有一个主题则直接加载（无需弹窗）。

    查找顺序（合并去重）：
      1. exe 同级的 themes/（用户自定义，优先）
      2. _MEIPASS/themes/（PyInstaller onefile 打包内置）
      3. _internal/themes/（PyInstaller onedir 打包内置）
      4. 脚本同级的 themes/（开发模式）
    """
    _meipass = Path(getattr(sys, '_MEIPASS', '')) / "themes" if getattr(sys, '_MEIPASS', None) else None
    seen, jsons = set(), []
    for candidate_dir in [
        _app_dir() / "themes",                   # exe 旁边（用户可编辑，优先）
        _meipass,                                 # PyInstaller onefile 内置路径
        _app_dir() / "_internal" / "themes",     # PyInstaller 6 onedir 内置路径
        Path(__file__).resolve().parent / "themes" if not getattr(sys, 'frozen', False) else None,
    ]:
        if candidate_dir is None:
            continue
        candidate_dir.mkdir(parents=True, exist_ok=True)
        for jp in sorted(candidate_dir.glob("*.json")):
            key = jp.stem
            if key not in seen:
                seen.add(key)
                jsons.append(jp)

    if not jsons:
        return None          # 没有种子包，使用内置默认值
    if len(jsons) == 1:
        return str(jsons[0]) # 只有一个，直接加载

    # 多个主题 → 弹窗选择
    sel: list[str] = [None]
    def _show():
        d = tk.Tk()
        d.title("选择生图主题")
        d.resizable(False, False)
        d.attributes("-topmost", True)
        d.grab_set()
        d.update_idletasks()
        w, h = 360, 260 + len(jsons) * 34
        x = (d.winfo_screenwidth()  - w) // 2
        y = (d.winfo_screenheight() - h) // 2
        d.geometry(f"{w}x{h}+{x}+{y}")
        d.configure(bg="#F4F4F8")

        tk.Label(d, text="🎨 选择生图主题种子包",
                 font=("Microsoft YaHei UI", 13, "bold"),
                 bg="#F4F4F8", fg="#1E1B2E").pack(pady=(18, 6))
        tk.Label(d, text="不同主题包含专属预设和提示词逻辑",
                 font=("Microsoft YaHei UI", 9), bg="#F4F4F8",
                 fg="#6B6B8A").pack(pady=(0, 12))

        var = tk.StringVar(value=str(jsons[0]))
        for jp in jsons:
            name = jp.stem
            tk.Radiobutton(d, text=f"  {name}",
                           variable=var, value=str(jp),
                           font=("Microsoft YaHei UI", 11),
                           bg="#F4F4F8", fg="#1E1B2E",
                           selectcolor="#EDE9FB",
                           activebackground="#F4F4F8").pack(
                               anchor="w", padx=40, pady=4)

        def _ok():
            sel[0] = var.get()
            d.destroy()

        def _cancel():
            d.destroy()
            sys.exit(0)

        tk.Button(d, text="开始生图 →", command=_ok,
                  font=("Microsoft YaHei UI", 11, "bold"),
                  bg="#6D28D9", fg="white",
                  activebackground="#7C3AED", activeforeground="white",
                  relief="flat", cursor="hand2",
                  padx=24, pady=8).pack(pady=(16, 20))
        d.bind("<Return>", lambda e: _ok())
        d.protocol("WM_DELETE_WINDOW", _cancel)
        d.mainloop()
    _show()
    return sel[0]
# ── 统计上报（留空则不上报）──────────────────────────────────────
STATS_URL = ""

# ── 超时 / 轮询 ───────────────────────────────────────────────────
MAX_RETRIES      = 2
CHAT_TIMEOUT     = 90
IMAGINE_TIMEOUT  = 300   # 所有 MJ 接口同步等待最长 5 分钟

ASPECT_MAP  = {"1:1": "1024x1024", "16:9": "1536x864", "9:16": "864x1536",
               "4:3": "1024x768",  "3:4": "768x1024"}
BLEND_DIM   = {"1:1": "square", "16:9": "landscape", "9:16": "portrait",
               "4:3": "landscape", "3:4": "portrait"}

MAX_LONG_EDGE      = 1024   # Gemini 分析用（可大一些）
MAX_FILE_KB        = 1024
MAX_BLEND_LONG_EDGE = 512  # base64Array 图生图用（控制总请求体大小）
MAX_BLEND_KB        = 150
SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

# ══════════════════════════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════════════════════════

def _app_dir():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

# 打包 exe 时：自动设置 playwright 的 node.exe 路径
# dist/playwright_driver/node.exe 由构建脚本预置，无需用户额外安装
if getattr(sys, 'frozen', False):
    _node_exe = _app_dir() / "playwright_driver" / "node.exe"
    if _node_exe.exists():
        os.environ.setdefault("PLAYWRIGHT_NODEJS_PATH", str(_node_exe))

def get_api_key():
    if _EMBEDDED_KEY:
        return _dk(_EMBEDDED_KEY)
    return (os.environ.get("KUNPO_API_KEY") or
            os.environ.get("ZIY_API_KEY") or "")

def _headers():
    key = get_api_key()
    if not key:
        raise RuntimeError("未配置 API Key")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

def downscale_image(path) -> bytes:
    """缩放图片到 MAX_LONG_EDGE，返回 JPEG bytes（用于上传）"""
    img = Image.open(path)
    if img.mode in ("P", "PA"):
        img = img.convert("RGBA")
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

def img_to_data_uri(path) -> str:
    raw = downscale_image(path)
    return "data:image/jpeg;base64," + base64.b64encode(raw).decode()

def img_to_data_uri_blend(path) -> str:
    """专用于 base64Array 图生图，压缩更小以避免请求体超限"""
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

def load_thumbnail(path, size=(80, 80)) -> ImageTk.PhotoImage:
    img = Image.open(path); img.thumbnail(size, Image.LANCZOS)
    return ImageTk.PhotoImage(img)

def _thumb_b64(path, size=(120, 120)) -> str:
    if not path: return ""
    try:
        img = Image.open(path); img.thumbnail(size, Image.LANCZOS)
        if img.mode not in ("RGB", "L"): img = img.convert("RGB")
        buf = io.BytesIO(); img.save(buf, format="JPEG", quality=55)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception: return ""

# ══════════════════════════════════════════════════════════════════
# API 调用
# ══════════════════════════════════════════════════════════════════

class StoppedByUser(Exception):
    pass


def download_image(url: str) -> bytes:
    r = requests.get(url, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"下载失败 HTTP {r.status_code}")
    return r.content

def _scrape_pinterest(query: str, limit: int = 20,
                      scrolls: int = 8, delay_ms: int = 1200,
                      progress_cb=None) -> str:
    """
    用 Python playwright 抓 Pinterest 搜索图片，保存到 output/pinterest/<query>-<ts>/
    返回输出目录路径。
    """
    import re as _re, urllib.request as _ur, urllib.parse as _up
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError(
            "Pinterest 抓图需要 playwright。\n"
            "请在命令行执行：\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        )

    def _norm_url(raw):
        if not raw or raw.startswith("data:") or raw.startswith("blob:"):
            return None
        try:
            u = _up.urlparse(raw)
        except Exception:
            return None
        if u.scheme not in ("http", "https"):
            return None
        path = u.path
        if _re.search(r'\.(svg|gif)$', path, _re.I):
            return None
        if _re.search(r'(?:avatar|profile|icon|logo|30x30|60x60|75x75)', raw, _re.I):
            return None
        # 升级到 736x（最高质量）
        path = _re.sub(r'/(?:60x60|136x136|170x|236x|474x|564x)/', '/736x/', path)
        if not _re.search(r'\.(avif|webp|png|jpe?g)$', path, _re.I):
            return None
        return _up.urlunparse((u.scheme, u.netloc, path, '', '', ''))

    def _identity(url):
        u = _up.urlparse(url)
        if u.netloc.endswith("pinimg.com"):
            return u.netloc + ":" + Path(u.path).name.lower()
        return url

    def _collect(page):
        raw = page.evaluate("""() => {
            const urls = [];
            document.querySelectorAll('img').forEach(img => {
                [img.currentSrc, img.src, img.getAttribute('data-src')].forEach(u => u && urls.push(u));
                const ss = img.getAttribute('srcset');
                if (ss) ss.split(',').forEach(s => urls.push(s.trim().split(/\\s+/)[0]));
            });
            return urls;
        }""")
        seen_id = {}
        for u in raw:
            n = _norm_url(str(u))
            if not n: continue
            iid = _identity(n)
            if iid not in seen_id:
                seen_id[iid] = n
        return list(seen_id.values())

    # 输出目录
    ts  = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    slug = _re.sub(r'[^\w\-]', '-', query.lower())[:40].strip('-') or "pinterest"
    out_dir = _app_dir() / "output" / "pinterest" / f"{slug}-{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    search_url = f"https://www.pinterest.com/search/pins/?q={_up.quote(query)}"
    if progress_cb: progress_cb(f"[Pinterest] 打开浏览器，搜索「{query}」…")

    # 查找系统 Chrome / Edge
    chrome_candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    sys_browser = next((p for p in chrome_candidates if Path(p).exists()), None)

    downloaded = 0
    with sync_playwright() as pw:
        launch_kw = dict(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        if sys_browser:
            browser = pw.chromium.launch(executable_path=sys_browser, **launch_kw)
        elif getattr(sys, 'frozen', False):
            # 打包 exe：使用系统自带的 Microsoft Edge，无需安装 Chromium
            try:
                browser = pw.chromium.launch(channel="msedge", **launch_kw)
            except Exception:
                raise RuntimeError(
                    "未找到 Microsoft Edge。\n"
                    "请确认电脑已安装 Edge 浏览器（Windows 10/11 默认自带）。"
                )
        else:
            browser = pw.chromium.launch(**launch_kw)  # 源码运行：使用 playwright 内置浏览器

        page = browser.new_page(
            viewport={"width": 1440, "height": 1600},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
        )
        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(delay_ms * 2)

            candidates = _collect(page)
            for scroll in range(scrolls):
                if len(candidates) >= limit * 3:
                    break
                page.mouse.wheel(0, 2500)
                page.wait_for_timeout(delay_ms)
                candidates = list({_identity(u): u for u in candidates + _collect(page)}.values())
                if progress_cb:
                    progress_cb(f"[Pinterest] 滚动 {scroll+1}/{scrolls}，已发现 {len(candidates)} 个候选…")

            if progress_cb:
                progress_cb(f"[Pinterest] 开始下载图片（目标 {limit} 张）…")

            for url in candidates:
                if downloaded >= limit:
                    break
                try:
                    req = _ur.Request(url, headers={
                        "Accept": "image/*,*/*;q=0.8",
                        "Referer": "https://www.pinterest.com/",
                        "User-Agent": "Mozilla/5.0"
                    })
                    with _ur.urlopen(req, timeout=15) as resp:
                        data = resp.read()
                    if len(data) < 8000:
                        continue
                    ext = _re.search(r'\.(jpe?g|png|webp|avif)$', url, _re.I)
                    ext = ext.group(1).lower().replace("jpeg","jpg") if ext else "jpg"
                    fname = out_dir / f"{downloaded+1:03d}.{ext}"
                    fname.write_bytes(data)
                    downloaded += 1
                    if progress_cb:
                        progress_cb(f"[Pinterest] 已下载 {downloaded}/{limit} 张…")
                except Exception:
                    continue
        finally:
            browser.close()

    if downloaded == 0:
        raise RuntimeError("未能下载任何图片，请检查网络或关键词")
    if progress_cb:
        progress_cb(f"[Pinterest] 完成，共下载 {downloaded} 张")
    return str(out_dir)


def _call_generations(model: str, prompt: str, size: str = "1024x1024",
                      label: str = "", progress_cb=None,
                      base64_array: list = None) -> list[bytes]:
    """
    统一调用 /v1/images/generations（Image-MI）。
    Image-MI 一次返回 4 张图 URL。

    base64_array: 可选，传入 data URI 列表时启用真正图生图
                  （base64Array 字段，Image-MI 直接参考图片生成）

    ⚠️  KUNPO 服务器 Content-Length 有误（比实际多），导致 requests 抛
        ChunkedEncodingError。改用 http.client 直读底层 socket fp，
        绕过 Content-Length 校验，读到连接真正关闭为止。

    返回：list[bytes]，每个元素是一张图片的 bytes（最多 4 张）。
    """
    import http.client as _hc, json as _json, ssl as _ssl

    tag = label or model
    if progress_cb: progress_cb(f"[{tag}] 提交请求，等待生成…（约 45s）")
    payload = {
        "model": model, "prompt": prompt, "size": size,
        "quality": "standard", "n": 4,
    }
    if base64_array:
        payload["base64Array"] = base64_array
    payload_bytes = json.dumps(payload).encode("utf-8")
    if progress_cb:
        kb = len(payload_bytes) // 1024
        img_n = len(base64_array) if base64_array else 0
        progress_cb(f"[{tag}] 请求体 {kb} KB，含 {img_n} 张参考图")
    last_err = None

    # 解析 GENERATIONS_URL → host / path
    from urllib.parse import urlparse as _up
    _parsed = _up(GENERATIONS_URL)
    _host   = _parsed.netloc
    _path   = _parsed.path or "/v1/images/generations"
    _ctx    = _ssl.create_default_context()

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

            if not raw:
                raise RuntimeError("响应为空")
            data  = _json.loads(raw)
            if "error" in data:
                err = data["error"]
                code = err.get("code", "") if isinstance(err, dict) else ""
                msg  = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                # upstream 临时故障可重试
                if code in ("do_request_failed", "bad_response_status_code") and attempt < MAX_RETRIES:
                    last_err = msg
                    time.sleep(8 * (attempt + 1))
                    continue
                raise RuntimeError(f"API 错误: {err}")
            items = data.get("data", [])
            if not items:
                raise RuntimeError(f"返回 data 为空: {data}")
            # 下载所有返回的图片（Image-MI 一次 4 张）
            result_bytes = []
            for i, item in enumerate(items):
                url = item.get("url","")
                b64 = item.get("b64_json","")
                if url:
                    if progress_cb:
                        progress_cb(f"[{tag}] 下载第 {i+1}/{len(items)} 张…")
                    result_bytes.append(download_image(url))
                elif b64:
                    result_bytes.append(base64.b64decode(b64))
            if not result_bytes:
                raise RuntimeError(f"无法获取图片数据: {items[0]}")
            return result_bytes

        except RuntimeError:
            raise
        except Exception as e:
            last_err = str(e)[:200]
            if attempt < MAX_RETRIES: time.sleep(6 * (attempt+1)); continue
            raise RuntimeError(f"[{tag}] 网络/解析失败: {last_err}")

    raise RuntimeError(f"[{tag}] 多次重试失败: {last_err}")


def call_imagine(prompt: str, size: str = "1024x1024",
                 progress_cb=None) -> list[bytes]:
    """文生图：Image-MI，返回 4 张图 bytes 列表"""
    return _call_generations(MODEL_IMAGINE, prompt, size, "Image-MI", progress_cb)


def call_blend(data_uris: list, extra_prompt: str = "",
               size: str = "1024x1024", progress_cb=None) -> list[bytes]:
    """
    真正图生图：Image-MI + base64Array。
    将风格/主体/主题参考图以 base64Array 传入，Image-MI 直接参考图片生成。
    extra_prompt 作为额外风格文字描述追加到 prompt。
    """
    prompt = (extra_prompt.strip() or _BLEND_DEFAULT_PROMPT)
    return _call_generations(
        MODEL_BLEND, prompt, size, "Image-MI 图生图",
        progress_cb, base64_array=data_uris if data_uris else None)


# ── 巨构 Gemini 反推 META_PROMPT ─────────────────────────────────
# 参考 v2.3「三图分层生成工具」的结构化分析逻辑，适配 Image-MI 巨构三层场景
_META_PROMPT_LAYERS = """\
你是 Midjourney 提示词专家，专门负责该主题风格 AI 生图。我给你 {n} 张参考图：
{roles}

你的任务：为 Image-MI 写一段融合所有层信息的英文生图提示词，以当前主题风格重新诠释。

【主体形态控制 - 三步强制执行】
Step 1：仔细分析 @image2 的整体轮廓（球形/锥形/矩形/有机曲线/复合形态等）、几何细节\
（比例/对称/棱角/曲率/孔洞/突起）和表面材质质感，记住这个形态原型。
Step 2：将 @image2 的形态1:1映射为该主题风格的超现实巨型建筑——保留其轮廓特征，放大至城市尺度。
Step 3：生成的英文提示词必须以描述 @image2 形态的词组开头（至少15词），必须使用具体形态词汇\
（bulbous / tapered / faceted / angular / spherical / tubular / elongated / conical / \
asymmetric / organic 等）。

核心目标：
- 视觉风格完全遵照 @image1 的光影色调、构图逻辑、整体氛围
- 画面核心主体必须是 @image2 的形态原型放大而成的建筑（提示词开头即精确描述其形态）
- 场景意境遵照后续主题图的情境与情绪氛围（若无主题图则自由设计与风格匹配的场景）{theme_clause}

⚠️ 绝对禁止：
- 禁止以 "a tower" / "a building" / "a structure" 等模糊词作为提示词开头，必须先描述 @image2 的形态特征
- 禁止让 @image1 中的建筑形态成为主体，@image1 仅提供光影/色调/氛围/构图逻辑
- 禁止忽略或弱化 @image2 的轮廓形态特征

输出规则：
- 只输出最终英文提示词，不输出分析过程，不输出中文，不输出 --ar/--v 等 MJ 参数
- 逗号分隔关键词组，控制在 180 词以内
- 若有人影必须用 "a single lone figure" 或 "one solitary tiny silhouette" 表达（单数）
- 直接开始写提示词（从 @image2 的形态描述词组起）\
"""

_META_PROMPT_MULTI = """\
你是 Midjourney 提示词专家，专门负责「巨构」风格 AI 生图。我给你 {n} 张参考图：
{roles}

你的任务：写一段用于 Midjourney Image-MI 的英文生图提示词，融合所有参考图的视觉信息，\
并以「巨构」风格重新诠释。

分析维度（从参考图逐一提取）：
1. 【构图 & 视角】仰视 / 俯视 / 平视 / 广角 / 远景，画面空间层次
2. 【光影 & 氛围】光源方向、光质（硬光/漫射/背光）、时段、情绪基调
3. 【色彩 & 材质】主色调倾向、材质（混凝土 / 锈蚀金属 / 岩石 / 玻璃等）
4. 【结构形态】建筑或物体的几何特征、尺度关系、重复韵律

巨构风格必须包含：
- 超现实建筑尺度，令人震撼的宏大感
- 画面中有且仅有一个极小的孤独人影（必须是单人），用于衬托建筑的绝对尺度
- 电影级构图，极度细节，超写实渲染

输出规则：
- 只输出最终英文提示词，不输出分析过程，不输出中文，不输出 --ar/--v 等 MJ 参数
- 逗号分隔关键词组，控制在 150 词以内
- 人影必须用 "a single lone figure" 或 "one solitary tiny silhouette" 表达（单数）
- 直接开始写提示词\
"""

_META_PROMPT_SINGLE = """\
你是 Midjourney 提示词专家，专门负责「巨构」风格 AI 生图。我给你 1 张参考图。

你的任务：分析这张参考图的视觉特征，以「巨构」风格写一段 Midjourney Image-MI 英文生图提示词。

分析维度：
1. 【构图 & 视角】画面空间关系、视角类型
2. 【光影 & 氛围】光源、光质、情绪基调、时间氛围
3. 【色彩 & 材质】主色调、关键材质（混凝土 / 金属 / 岩石等）
4. 【结构特征】几何形态、尺度感、重复韵律

巨构风格必须包含：
- 超现实建筑尺度，令人震撼的宏大感
- 画面中有且仅有一个极小的孤独人影（必须是单人），用于衬托建筑的绝对尺度
- 电影级构图，极度细节，超写实渲染

输出规则：
- 只输出最终英文提示词，不输出分析，不输出中文，不输出 MJ 参数
- 逗号分隔，控制在 120 词以内
- 人影必须用 "a single lone figure" 或 "one solitary tiny silhouette" 表达（单数）
- 直接开始写\
"""

def _parse_gemini_content(data: dict) -> str:
    """从 Gemini /chat/completions 响应中提取文本内容"""
    msg = (data.get("choices") or [{}])[0].get("message", {})
    content = msg.get("content", "")
    if isinstance(content, str) and content.strip():
        return content.strip()
    if isinstance(content, list):
        texts = [p.get("text", "") for p in content if p.get("type") == "text"]
        if texts:
            return "\n".join(texts).strip()
    raise ValueError("Gemini 未返回有效文本")

def call_gemini_analyze_refs(image_paths: list,
                             role_descriptions: list = None,
                             use_layers_prompt: bool = False,
                             progress_cb=None) -> str:
    """
    v2.3 同款逻辑：将所有参考图一次性发给 Gemini，
    使用结构化 META_PROMPT 分析并生成巨构风格 MJ 提示词。

    参数：
      image_paths       : 参考图路径列表（1~4 张）
      role_descriptions : 可选，每张图的角色描述列表，覆盖默认标签
      use_layers_prompt : True 时使用三层专用 META_PROMPT（风格/主体/主题）
    """
    n = len(image_paths)
    if n == 0:
        return ""
    if progress_cb:
        progress_cb(f"[Gemini] 编码 {n} 张参考图…")

    # 选择并构建 META_PROMPT
    if use_layers_prompt:
        # 三层专用模板：动态注入实际角色描述（支持 image4+ 主题图）
        default_layer_labels = _LAYER_LABELS_4
        labels = role_descriptions if role_descriptions else default_layer_labels
        roles = "\n".join(f"- {labels[i]}" for i in range(n))
        # 有多张主题图时，在核心目标中追加说明
        theme_count = max(0, n - 2)  # 减去风格图和主体图
        if theme_count >= 2:
            theme_clause = (f"\n- @image3 与 @image4 共同定义场景意境，"
                            f"综合两张主题图的情境与氛围")
        elif theme_count == 1:
            theme_clause = ""
        else:
            theme_clause = ""
        meta_text = _META_PROMPT_LAYERS.format(
            n=n, roles=roles, theme_clause=theme_clause)
    elif n == 1:
        meta_text = _META_PROMPT_SINGLE
    else:
        default_labels = _LAYER_LABELS_MULTI
        labels = role_descriptions if role_descriptions else default_labels
        roles = "\n".join(f"- {labels[i]}：参考图 {i+1}" for i in range(n))
        meta_text = _META_PROMPT_MULTI.format(n=n, roles=roles)

    # 构建 content：提示词 + 每张图（三层模式下每图前插入定位绑定标签）
    # 裸发时模型靠内容推断角色，易错；带标签后每张图与角色强绑定
    content_parts = [{"type": "text", "text": meta_text}]
    for i, path in enumerate(image_paths):
        if progress_cb:
            progress_cb(f"[Gemini] 编码参考图 {i+1}/{n}：{Path(path).name}…")
        if use_layers_prompt and i < len(_LAYER_INLINE_TAGS):
            content_parts.append({"type": "text", "text": _LAYER_INLINE_TAGS[i]})
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": img_to_data_uri(path)}
        })

    payload = {"model": MODEL_GEMINI, "messages": [
        {"role": "user", "content": content_parts}
    ]}

    if progress_cb:
        progress_cb(f"[Gemini] 提交分析请求（{n} 张图，约 15~30 秒）…")

    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            r = requests.post(CHAT_URL, json=payload, headers=_headers(),
                              timeout=CHAT_TIMEOUT)
            if r.status_code == 200:
                return _parse_gemini_content(r.json())
            if r.status_code in (422, 500) and payload["model"] != MODEL_GEMINI_FB:
                payload = dict(payload, model=MODEL_GEMINI_FB)
                if progress_cb:
                    progress_cb("[Gemini] 切换备用模型重试…")
                continue
            last_err = f"HTTP {r.status_code}: {r.text[:200]}"
            time.sleep(3)
        except requests.Timeout:
            last_err = "请求超时"
            if attempt < MAX_RETRIES:
                time.sleep(5)
        except Exception as e:
            raise RuntimeError(f"Gemini 网络错误: {e}")
    raise RuntimeError(f"Gemini 多次重试失败: {last_err}")

def call_gemini_describe(image_path: str, progress_cb=None) -> str:
    """向后兼容保留，内部改为调用新版多图分析（单图模式）"""
    return call_gemini_analyze_refs([image_path], progress_cb)


# ══════════════════════════════════════════════════════════════════
# 自由生图：Gemini 生成内容方向 & 方向转 MJ 提示词
# ══════════════════════════════════════════════════════════════════

_SYSTEM_FREE_OPTIONS = """\
你是专业的视觉内容策划师。用户描述了想要的图像类型，你需要生成30个具体的内容方向供选择。

规则：
- 每个方向10-20字中文描述
- 方向之间有明显差异（不同场景/时间/氛围/情绪/地点）
- 只输出编号+描述，格式严格为：
  1. xxx
  2. xxx
  ...
  30. xxx
- 禁止解释、禁止分类标题、禁止多余换行

用户需求：{user_input}\
"""

_SYSTEM_FREE_TO_PROMPT = """\
将以下中文场景描述转化为专业的 Midjourney 英文提示词。

要求：
- 纯英文，20-30词
- 包含：场景主体、光线氛围、构图风格
- 末尾原样追加风格后缀（不修改，直接拼接在描述后）
- 只输出提示词文本，不要任何解释，不要 --ar/--v 等参数

中文描述：{option}
风格后缀：{style_suffix}\
"""


def call_gemini_free_gen_options(user_input: str, progress_cb=None) -> list:
    """根据用户描述生成30个内容方向（中文列表）"""
    if progress_cb:
        progress_cb("[Gemini] 生成内容方向中…")
    prompt_text = _SYSTEM_FREE_OPTIONS.format(user_input=user_input)
    payload = {"model": MODEL_GEMINI, "messages": [
        {"role": "user", "content": prompt_text}
    ]}
    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            r = requests.post(CHAT_URL, json=payload, headers=_headers(),
                              timeout=CHAT_TIMEOUT)
            if r.status_code == 200:
                text = _parse_gemini_content(r.json())
                options = []
                for line in text.split("\n"):
                    line = line.strip()
                    m = re.match(r"^\d+[.、。]\s*(.+)$", line)
                    if m:
                        options.append(m.group(1).strip())
                return options
            if r.status_code in (422, 500) and payload["model"] != MODEL_GEMINI_FB:
                payload = dict(payload, model=MODEL_GEMINI_FB)
                continue
            last_err = f"HTTP {r.status_code}: {r.text[:200]}"
            time.sleep(3)
        except requests.Timeout:
            last_err = "请求超时"
            if attempt < MAX_RETRIES:
                time.sleep(5)
        except Exception as e:
            raise RuntimeError(f"Gemini 网络错误: {e}")
    raise RuntimeError(f"Gemini 多次重试失败: {last_err}")


def call_gemini_option_to_prompt(option: str, style_suffix: str = "",
                                  progress_cb=None) -> str:
    """将一个中文内容方向转化为 MJ 英文提示词"""
    prompt_text = _SYSTEM_FREE_TO_PROMPT.format(
        option=option,
        style_suffix=style_suffix or STYLE_SUFFIX
    )
    payload = {"model": MODEL_GEMINI, "messages": [
        {"role": "user", "content": prompt_text}
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
            if attempt < MAX_RETRIES:
                time.sleep(5)
        except Exception as e:
            raise RuntimeError(f"Gemini 网络错误: {e}")
    raise RuntimeError(f"Gemini 多次重试失败: {last_err}")


# ── 自动选材 META_PROMPT ──────────────────────────────────────────
_META_PROMPT_AUTO_SELECT = """\
你是 AI 生图素材选材专家。我给你 {n} 张候选图片，编号 image1~image{n}。
主题关键词：「{theme}」

你的任务：从这 {n} 张图中，为巨构风格图生图的三层结构选出最合适的图片：
- **风格图**（1 张，必选）：最能体现光影质感、氛围色调、整体视觉风格的图
- **主体控制图**（1 张，必选）：最能代表核心建筑/结构形态、几何特征的图
- **主题图**（1~2 张，可选）：最能体现场景意境、情绪氛围、叙事背景的图

选材原则：
- 与主题关键词「{theme}」最契合的优先
- 三层图尽量不重复
- 若候选图数量不足，风格图和主体图可从同一批选，主题图可为空

只输出如下 JSON 格式，不要任何其他文字：
{{
  "style": "image1",
  "subject": "image2",
  "theme": ["image3"]
}}
其中 theme 数组可为 0~2 个元素，值为 image1~image{n} 中的编号。\
"""


def call_gemini_select_materials(image_paths: list, theme: str,
                                 progress_cb=None) -> dict:
    """
    从 image_paths 中让 Gemini 自动选材，返回三层路径字典：
      {"style": path, "subject": path, "theme": [path, ...]}

    image_paths 最多取 12 张（随机采样）。
    """
    import random
    if not image_paths:
        return {"style": "", "subject": "", "theme": []}

    sampled = image_paths if len(image_paths) <= 12 else random.sample(image_paths, 12)
    n = len(sampled)

    if progress_cb:
        progress_cb(f"[Gemini 选材] 编码 {n} 张候选图…")

    meta_text = _META_PROMPT_AUTO_SELECT.format(n=n, theme=theme or _THEME_KEYWORD)
    content_parts = [{"type": "text", "text": meta_text}]
    for i, path in enumerate(sampled):
        if progress_cb:
            progress_cb(f"[Gemini 选材] 编码图片 {i+1}/{n}…")
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": img_to_data_uri(path)}
        })

    payload = {"model": MODEL_GEMINI, "messages": [
        {"role": "user", "content": content_parts}
    ]}

    if progress_cb:
        progress_cb("[Gemini 选材] 分析候选图，自动分配三层（约 15 秒）…")

    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            r = requests.post(CHAT_URL, json=payload, headers=_headers(),
                              timeout=CHAT_TIMEOUT)
            if r.status_code == 200:
                raw = _parse_gemini_content(r.json())
                # 提取 JSON（Gemini 可能在前后加 markdown 代码块）
                m = re.search(r'\{[\s\S]*\}', raw)
                if not m:
                    raise ValueError(f"Gemini 未返回 JSON: {raw[:200]}")
                sel = json.loads(m.group())
                # 将 image1~imageN 映射回实际路径
                def _idx(key):
                    s = sel.get(key, "")
                    if isinstance(s, str):
                        m2 = re.search(r'(\d+)', s)
                        if m2:
                            idx = int(m2.group(1)) - 1
                            if 0 <= idx < len(sampled):
                                return sampled[idx]
                    return ""
                style   = _idx("style")
                subject = _idx("subject")
                theme_raw = sel.get("theme", [])
                if isinstance(theme_raw, str):
                    theme_raw = [theme_raw]
                theme_paths = []
                for t in (theme_raw or []):
                    m3 = re.search(r'(\d+)', str(t))
                    if m3:
                        idx = int(m3.group(1)) - 1
                        if 0 <= idx < len(sampled) and sampled[idx] not in theme_paths:
                            theme_paths.append(sampled[idx])
                return {"style": style, "subject": subject, "theme": theme_paths}

            if r.status_code in (422, 500) and payload["model"] != MODEL_GEMINI_FB:
                payload = dict(payload, model=MODEL_GEMINI_FB)
                continue
            last_err = f"HTTP {r.status_code}: {r.text[:200]}"
            time.sleep(3)
        except (ValueError, json.JSONDecodeError) as e:
            last_err = str(e)
            if attempt < MAX_RETRIES:
                time.sleep(4)
        except requests.Timeout:
            last_err = "请求超时"
            if attempt < MAX_RETRIES:
                time.sleep(5)
        except Exception as e:
            raise RuntimeError(f"Gemini 选材网络错误: {e}")
    raise RuntimeError(f"Gemini 选材失败: {last_err}")

# ══════════════════════════════════════════════════════════════════
# 提示词构建
# ══════════════════════════════════════════════════════════════════

# 巨构风格快速填充词库
STRUCT_PRESETS = [
    "倒置的粗野主义巨塔",
    "巨构内部无限镜像走廊",
    "层叠悬浮的混凝土平台群",
    "半浮出海面的远古巨像遗迹",
    "递归嵌套的几何峡谷壁面",
    "废弃的轨道环形空间站",
    "被雕凿成几何空腔的空心山体",
    "锈蚀铁原野上的孤立方尖碑",
    "晶体冰川构成的要塞城堡",
    "嵌入城市的无尽垂直绝壁",
    "沉入地下的反重力建筑群",
    "被植物吞噬的巨型工业废墟",
]
LIGHT_PRESETS = [
    "黄金时刻逆光，丁达尔光柱",
    "阴天漫射光，银灰色天空",
    "深重阴影，仅有轮廓边缘光",
    "生物荧光迷雾，青色冷光",
    "纯白虚空，无地平线",
    "暴风雨前的戏剧性天光",
    "冷蓝月光，拉长的阴影",
    "暖橙余烬烟霾，漂浮尘粒",
    "日落后的靛蓝暮色",
    "穿云而下的圣光束",
]
MOOD_PRESETS = [
    "荒芜孤寂，深沉的孤独感",
    "静默震撼，令人窒息的尺度",
    "不祥预感，压迫性的张力",
    "忧郁怀旧，时间侵蚀的痕迹",
    "超然宁静，凝固的永恒感",
    "压倒性的宏大，令人眩晕",
    "绝对的秩序，冷酷的理性",
    "没有告别，静默的告别",
]
STYLE_SUFFIX = (
    "电影级构图，a single lone figure for scale，"
    "超写实，极度细节，8K画质，无文字，无水印"
)

def build_imagine_prompt(structure: str, lighting: str, mood: str,
                          extra: str, ar: str, stylize: int, version: str) -> str:
    parts = [p for p in [structure, lighting, mood, STYLE_SUFFIX, extra.strip()] if p]
    body  = ", ".join(parts)
    params = f"--ar {ar} --v {version} --stylize {stylize} --q 2"
    return f"{body} {params}"

# ══════════════════════════════════════════════════════════════════
# 报告 CSS / JS（复刻 v2.3 风格）
# ══════════════════════════════════════════════════════════════════

_REPORT_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Microsoft YaHei UI",system-ui,sans-serif;background:#f0f0f0;color:#1e293b;font-size:13px}
header{background:#fff;border-bottom:1px solid #e2e8f0;padding:14px 24px 12px;position:sticky;top:0;z-index:20;box-shadow:0 1px 4px rgba(0,0,0,.06)}
header h1{font-size:17px;font-weight:700;margin-bottom:8px}
.meta-row{display:flex;gap:20px;color:#64748b;font-size:12px;margin-bottom:6px;flex-wrap:wrap}
.hstats,.stats-row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.st{font-size:12px;font-weight:600;padding:2px 10px;border-radius:10px}
.st.done{background:#dcfce7;color:#166534}
.st.fail{background:#fee2e2;color:#991b1b}
.st.total{background:#f1f5f9;color:#475569}
/* 批次列表（总览） */
.batches{padding:14px 20px;display:flex;flex-direction:column;gap:10px}
details.batch{background:#fff;border-radius:10px;border:1px solid #e2e8f0;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.05)}
details.batch[open]{border-color:#c4b5fd}
summary.bsum{display:flex;align-items:center;gap:10px;padding:11px 16px;cursor:pointer;user-select:none;list-style:none;background:#f8fafc;border-bottom:1px solid transparent}
details.batch[open] summary.bsum{border-bottom-color:#ede9fe;background:#faf5ff}
summary.bsum::-webkit-details-marker{display:none}
summary.bsum::before{content:"\25B6";font-size:10px;color:#a78bfa;transition:transform .2s;flex-shrink:0}
details.batch[open] summary.bsum::before{transform:rotate(90deg)}
.btitle{font-weight:700;color:#1e293b;font-size:13px}
.bnew{background:#6d28d9;color:#fff;font-size:10px;padding:1px 7px;border-radius:8px;font-weight:600}
.btheme{font-size:10px;padding:1px 8px;border-radius:8px;font-weight:600;color:#fff;background:#0891b2}
.bmeta{display:flex;gap:8px;align-items:center;margin-left:auto;flex-wrap:wrap}
.tag{padding:1px 8px;border-radius:8px;font-size:11px;font-weight:500;background:#f1f5f9;color:#475569}
.tag.done{background:#dcfce7;color:#166534}
.tag.fail{background:#fee2e2;color:#991b1b}
.blink{font-size:11px;color:#6d28d9;text-decoration:none;padding:2px 8px;border:1px solid #e9d5ff;border-radius:6px}
.blink:hover{background:#ede9fe}
.bcards{padding:12px 14px;display:flex;flex-direction:column;gap:12px}
/* 单批次报告网格 */
.grid{padding:16px 24px;display:flex;flex-direction:column;gap:14px}
/* 通用卡片 */
.card{background:#f9fafb;border-radius:8px;border:1px solid #e2e8f0;overflow:hidden}
.card.ok{border-left:4px solid #22c55e}
.card.ng{border-left:4px solid #ef4444}
.card.sk{border-left:4px solid #94a3b8}
.ch{display:flex;align-items:center;gap:8px;padding:7px 12px;background:#f1f5f9;border-bottom:1px solid #e2e8f0;flex-wrap:wrap}
.cn{font-weight:700;color:#6d28d9;font-size:11px;min-width:22px}
.cbadge{padding:1px 7px;border-radius:8px;font-size:10px;font-weight:600}
.cbadge.ok{background:#dcfce7;color:#166534}
.cbadge.ng{background:#fee2e2;color:#991b1b}
.cbadge.sk{background:#f1f5f9;color:#94a3b8}
.badge-txt{background:#dbeafe;color:#1d4ed8;font-size:10px;font-weight:700;padding:1px 7px;border-radius:8px}
.badge-img{background:#ccfbf1;color:#0d9488;font-size:10px;font-weight:700;padding:1px 7px;border-radius:8px}
.et{color:#94a3b8;font-size:10px}
.tn{color:#475569;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:220px;margin-left:auto}
.cb{display:flex;align-items:flex-start;gap:0;padding:12px}
.inputs{display:flex;gap:8px;flex-shrink:0}
.ref-wrap{display:flex;flex-direction:column;align-items:center;gap:3px}
.ref-thumb{width:200px;height:200px;object-fit:cover;border-radius:7px;border:1px solid #e2e8f0;cursor:zoom-in;transition:transform .15s,box-shadow .15s}
.ref-thumb:hover{transform:scale(1.05);box-shadow:0 4px 14px rgba(0,0,0,.16)}
.ref-ph{width:200px;height:200px;background:#f1f5f9;border-radius:7px;border:1px solid #e2e8f0;display:flex;align-items:center;justify-content:center;color:#cbd5e1;font-size:22px}
.ref-lbl{font-size:10px;color:#64748b;font-weight:600;text-align:center}
.sep{width:1px;background:#e2e8f0;margin:0 14px;align-self:stretch;flex-shrink:0}
.out{flex:1;min-width:0}
.out-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px;align-items:start}
.out-grid .ri{width:100%;height:auto;max-height:none}
.ri{max-width:100%;border-radius:7px;border:1px solid #e2e8f0;display:block;cursor:zoom-in}
.ri:hover{opacity:.9}
.eb{background:#fee2e2;color:#991b1b;padding:8px 12px;border-radius:5px;font-size:11px}
details.pd{padding:5px 12px 8px;border-top:1px solid #f1f5f9}
details.pd summary{font-size:10px;color:#94a3b8;cursor:pointer;user-select:none}
details.pd summary:hover{color:#6d28d9}
.tog2{color:#94a3b8;font-size:11px;margin-left:4px;transition:transform .2s;display:inline-block}
pre.pt{font-family:Consolas,monospace;font-size:10px;color:#475569;white-space:pre-wrap;word-break:break-all;background:#f8fafc;padding:7px;border-radius:5px;margin-top:5px;max-height:120px;overflow-y:auto;line-height:1.5}
/* 浮窗 */
.fw{position:fixed;min-width:160px;min-height:100px;background:#fff;border-radius:10px;box-shadow:0 8px 40px rgba(0,0,0,.45);z-index:1000;display:flex;flex-direction:column;overflow:hidden}
.fw-bar{display:flex;align-items:center;gap:8px;padding:5px 10px;background:#1e293b;color:#fff;border-radius:10px 10px 0 0;cursor:grab;flex-shrink:0;font-size:11px}
.fw-bar:active{cursor:grabbing}
.fw-ttl{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;opacity:.85}
.fw-x{cursor:pointer;opacity:.7;font-size:14px;line-height:1;flex-shrink:0;background:none;border:none;color:#fff;padding:0 2px}
.fw-x:hover{opacity:1}
.fw-body{flex:1;overflow:hidden;position:relative;min-height:0;background:#0d0d0d}
.fw-body>img{display:block;width:100%;height:100%;object-fit:contain;object-position:center;cursor:move}
.fw-rz{position:absolute;bottom:0;right:0;width:20px;height:20px;cursor:nwse-resize;background:repeating-linear-gradient(-45deg,#94a3b8 0,#94a3b8 1.5px,transparent 1.5px,transparent 4px);opacity:.7;z-index:2}
.fw-nav{display:flex;gap:4px;margin-left:8px;flex-shrink:0}
.fw-nav button{background:rgba(255,255,255,.18);border:none;color:#fff;border-radius:4px;padding:2px 9px;cursor:pointer;font-size:13px;line-height:1.4}
.fw-nav button:hover{background:rgba(255,255,255,.35)}
.fw-nav button:disabled{opacity:.25;cursor:default}
.fw-idxlbl{font-size:10px;color:rgba(255,255,255,.6);min-width:32px;text-align:center;align-self:center}
/* 通过/未通过 */
.verdict-btns{display:flex;gap:8px;margin-top:8px}
.vbtn{padding:3px 12px;border-radius:6px;border:none;cursor:pointer;font-size:12px;font-weight:600;transition:all .15s}
.vbtn.pass{background:#dcfce7;color:#166534;border:1px solid #86efac}
.vbtn.fail{background:#fee2e2;color:#991b1b;border:1px solid #fca5a5}
.vbtn.pass.active{background:#22c55e;color:#fff;border-color:#16a34a}
.vbtn.fail.active{background:#ef4444;color:#fff;border-color:#dc2626}
.card.verdict-fail{background:#fff1f2!important}
.card.verdict-pass{background:#f0fdf4!important}
details.batch.batch-has-fail>summary.bsum{background:#fff1f2!important;border-left:3px solid #ef4444}
details.batch.batch-has-pass>summary.bsum{background:#f0fdf4!important;border-left:3px solid #22c55e}
details.batch.batch-has-mixed>summary.bsum{background:#fffbeb!important;border-left:3px solid #f59e0b}
.exp-btn{font-size:11px;font-weight:600;padding:3px 12px;border-radius:8px;border:1px solid #16a34a;color:#166534;background:#dcfce7;cursor:pointer}
.exp-btn:hover{background:#bbf7d0}
.fav-count{font-size:12px;font-weight:600;color:#166534;background:#dcfce7;padding:2px 10px;border-radius:10px;display:none}
.fav-hint{font-size:11px;color:#94a3b8;font-style:italic}
.ep{background:#fff7ed;border-left:3px solid #f97316;padding:5px 12px;font-size:11px;color:#c2410c;margin:0}
.ep-lbl{font-weight:600;margin-right:4px}
"""

_REPORT_JS = r"""
var _allRIs=[];var _wc=0;
document.addEventListener('DOMContentLoaded',function(){
  document.querySelectorAll('img.ref-thumb[data-full],img.ri[data-full]').forEach(function(el,i){
    el.dataset.riidx=i;_allRIs.push(el);
  });
});
function markVerdict(btn,type){
  var box=btn.closest('.verdict-btns'),card=btn.closest('.card'),batch=btn.closest('details.batch');
  box.querySelectorAll('.vbtn').forEach(function(b){b.classList.remove('active');});
  btn.classList.add('active');
  if(card){card.classList.remove('verdict-pass','verdict-fail');card.classList.add('verdict-'+type);}
  if(batch){
    var cards=batch.querySelectorAll('.card'),nP=0,nF=0,nT=0;
    cards.forEach(function(c){if(c.querySelector('.verdict-btns')){nT++;if(c.classList.contains('verdict-pass'))nP++;if(c.classList.contains('verdict-fail'))nF++;}});
    batch.classList.remove('batch-has-pass','batch-has-fail','batch-has-mixed');
    if(nF>0&&nP>0)batch.classList.add('batch-has-mixed');
    else if(nF>0)batch.classList.add('batch-has-fail');
    else if(nP===nT&&nT>0)batch.classList.add('batch-has-pass');
  }
  var fc=document.getElementById('favCount');
  if(fc){var n=document.querySelectorAll('.vbtn.pass.active').length;fc.style.display=n>0?'inline-block':'none';fc.textContent='\u2713 '+n+' \u5f20\u5df2\u901a\u8fc7';}
}
function exportFavs(){
  var rows=[];
  document.querySelectorAll('.card[data-key]').forEach(function(c){
    if(c.classList.contains('verdict-pass'))rows.push(c.dataset.key);
  });
  if(!rows.length){alert('\u8fd8\u6ca1\u6709\u6807\u8bb0\u300c\u901a\u8fc7\u300d\u7684\u56fe\u7247\u3002');return;}
  var blob=new Blob([rows.join('\n')],{type:'text/plain'});
  var a=document.createElement('a');a.href=URL.createObjectURL(blob);
  a.download='approved_list.txt';a.click();
}
function _updateNav(fw){
  var prev=fw.querySelector('.fw-prev'),next=fw.querySelector('.fw-next'),lbl=fw.querySelector('.fw-idxlbl');
  var idx=parseInt(fw.dataset.curRiidx!==undefined?fw.dataset.curRiidx:'-1');
  if(!prev)return;
  prev.disabled=(idx<=0);next.disabled=(idx<0||idx>=_allRIs.length-1);
  if(lbl)lbl.textContent=(idx>=0)?(idx+1)+'/'+_allRIs.length:'';
}
function _applyResultBar(fw,isResult){
  var bar=fw.querySelector('.fw-bar'),ex=bar.querySelector('.fw-gen-badge');if(ex)ex.remove();
  if(isResult){bar.style.background='#15803d';var bg=document.createElement('span');bg.className='fw-gen-badge';bg.textContent='\u2605 \u751f\u6210';bg.style.cssText='background:rgba(255,255,255,.15);border-radius:3px;padding:1px 5px;font-size:9px;font-weight:700;flex-shrink:0;margin-right:4px';bar.insertBefore(bg,bar.querySelector('.fw-ttl'));}
  else{bar.style.background='';}
}
function openFloat(src,ttl,clickedEl){
  if(!src)return;_wc++;
  var FW=500,FH=560;
  var x=Math.min(40+((_wc-1)%6)*40,window.innerWidth-FW-20);
  var y=Math.min(60+((_wc-1)%6)*28,window.innerHeight-FH-20);
  var riIdx=(clickedEl&&clickedEl.dataset&&clickedEl.dataset.riidx!==undefined)?parseInt(clickedEl.dataset.riidx):-1;
  var navHtml=(_allRIs.length>1)?'<div class="fw-nav"><button class="fw-prev" onclick="_navFloat(-1,this)">&#9664;</button><span class="fw-idxlbl"></span><button class="fw-next" onclick="_navFloat(1,this)">&#9654;</button></div>':'';
  var d=document.createElement('div');d.className='fw';
  d.style.cssText='left:'+x+'px;top:'+y+'px;width:'+FW+'px;height:'+FH+'px';
  d.dataset.curRiidx=riIdx;
  d.innerHTML='<div class="fw-bar"><span class="fw-ttl">'+(ttl||'\u56fe\u7247')+'</span>'+navHtml+'<button class="fw-x">&#x2715;</button></div><div class="fw-body"><img src="'+src+'"><div class="fw-rz"></div></div>';
  d.querySelector('.fw-x').onclick=function(){d.remove();};
  document.body.appendChild(d);_updateNav(d);
  _applyResultBar(d,clickedEl&&clickedEl.dataset&&clickedEl.dataset.isresult==='1');
  _fwDrag(d);_fwSize(d);
}
function _navFloat(delta,btn){
  var fw=btn?btn.closest('.fw'):null;if(!fw||fw.dataset.busy==='1')return;
  var curIdx=parseInt(fw.dataset.curRiidx!==undefined?fw.dataset.curRiidx:'-1');
  var newIdx=curIdx+delta;if(newIdx<0||newIdx>=_allRIs.length)return;
  fw.dataset.curRiidx=newIdx;
  var ri=_allRIs[newIdx],body=fw.querySelector('.fw-body'),oldImg=body.querySelector('img');
  var dir=delta>0?1:-1,MS=260;
  fw.querySelector('.fw-ttl').textContent=ri.title;
  _applyResultBar(fw,ri.dataset.isresult==='1');_updateNav(fw);fw.dataset.busy='1';
  var newImg=new Image();
  newImg.onload=function(){
    var strip=document.createElement('div');strip.style.cssText='display:flex;width:200%;height:100%;will-change:transform;transform:translateX('+(dir>0?'0':'-50%')+')';
    oldImg.style.cssText='display:block;width:50%;height:100%;object-fit:contain;flex-shrink:0';
    newImg.style.cssText='display:block;width:50%;height:100%;object-fit:contain;flex-shrink:0;cursor:move';
    if(dir>0){strip.appendChild(oldImg);strip.appendChild(newImg);}else{strip.appendChild(newImg);strip.appendChild(oldImg);}
    body.appendChild(strip);
    requestAnimationFrame(function(){requestAnimationFrame(function(){strip.style.transition='transform '+MS+'ms cubic-bezier(0.25,0.46,0.45,0.94)';strip.style.transform='translateX('+(dir>0?'-50%':'0')+')';});});
    setTimeout(function(){strip.remove();newImg.style.cssText='display:block;width:100%;height:100%;object-fit:contain;cursor:move';body.appendChild(newImg);fw.dataset.busy='0';},MS+20);
  };newImg.src=ri.dataset.full;
}
function _fwDrag(el){
  var b=el.querySelector('.fw-bar'),sx,sy,sl,st;
  b.onmousedown=function(e){if(e.target.tagName==='BUTTON')return;e.preventDefault();sx=e.clientX;sy=e.clientY;sl=el.offsetLeft;st=el.offsetTop;
    var mm=function(e){el.style.left=(sl+e.clientX-sx)+'px';el.style.top=(st+e.clientY-sy)+'px';};
    var mu=function(){document.removeEventListener('mousemove',mm);document.removeEventListener('mouseup',mu);};
    document.addEventListener('mousemove',mm);document.addEventListener('mouseup',mu);};
}
function _fwSize(el){
  var r=el.querySelector('.fw-rz'),sx,sy,sw,sh;
  r.onmousedown=function(e){e.preventDefault();e.stopPropagation();sx=e.clientX;sy=e.clientY;sw=el.offsetWidth;sh=el.offsetHeight;
    var mm=function(e){el.style.width=Math.max(150,sw+e.clientX-sx)+'px';el.style.height=Math.max(80,sh+e.clientY-sy)+'px';};
    var mu=function(){document.removeEventListener('mousemove',mm);document.removeEventListener('mouseup',mu);};
    document.addEventListener('mousemove',mm);document.addEventListener('mouseup',mu);};
}
function togCard2(hdr){
  var card=hdr.closest('.card');if(!card)return;
  var body=card.querySelector('.cb'),pd=card.querySelector('details.pd');
  var tog=hdr.querySelector('.tog2');
  var collapsed=card.dataset.collapsed==='1';
  if(collapsed){if(body)body.style.display='';if(pd)pd.style.display='';if(tog)tog.style.transform='';card.dataset.collapsed='0';}
  else{if(body)body.style.display='none';if(pd)pd.style.display='none';if(tog)tog.style.transform='rotate(-90deg)';card.dataset.collapsed='1';}
}
"""

# ══════════════════════════════════════════════════════════════════
# 任务数据类
# ══════════════════════════════════════════════════════════════════

class TaskItem:
    __slots__ = ("mode", "prompt", "ref_paths", "ar", "stylize", "version",
                 "extra_prompt", "status", "output_path", "output_paths",
                 "error", "elapsed", "batch_ts")
    def __init__(self, mode, prompt="", ref_paths=None,
                 ar="16:9", stylize=850, version="7", extra_prompt=""):
        self.mode         = mode          # "txt2img" | "img2img"
        self.prompt       = prompt
        self.ref_paths    = ref_paths or []
        self.ar           = ar
        self.stylize      = stylize
        self.version      = version
        self.extra_prompt = extra_prompt
        self.status       = "pending"     # pending | running | done | failed | stopped
        self.output_path  = None
        self.output_paths = []            # 全部 4 张图路径（Image-MI 一次出 4 张）
        self.error        = None
        self.elapsed      = 0.0
        self.batch_ts     = ""

# ══════════════════════════════════════════════════════════════════
# GUI 配色（白色现代主题，同 v2.3）
# ══════════════════════════════════════════════════════════════════
# ── 浅色精致配色 ────────────────────────────────────────────────
BG        = "#F4F4F8"   # 页面背景（微冷灰）
CARD      = "#FFFFFF"   # 卡片白
CARD2     = "#F0F0F5"   # 次级输入/控件背景
BORDER    = "#E2E2EC"   # 边框
BORDER_L  = "#C8C8DC"   # 强调边框
HOVER_BG  = "#EDE9FB"
SEL_BG    = "#EDE9FB"
ACCENT    = "#6D28D9"   # 主紫
ACCENT_H  = "#7C3AED"   # hover 紫
ACCENT_L  = "#EDE9FB"   # 淡紫背景
GOLD      = "#D97706"
GOLD_D    = "#FEF3C7"
TEAL      = "#0D9488"
TEAL_L    = "#CCFBF1"
TEXT      = "#1E1B2E"   # 主文字（深紫黑）
TEXT_DIM  = "#6B6B8A"   # 次要文字
TEXT_HINT = "#A0A0BC"   # 提示文字
GREEN     = "#059669"
RED       = "#DC2626"
AMBER     = "#D97706"
BLUE      = "#2563EB"
BLUE_L    = "#DBEAFE"


class RoundBar(tk.Canvas):
    """圆角进度条"""
    def __init__(self, parent, height=6, radius=3,
                 track=BORDER, fill=ACCENT, **kw):
        super().__init__(parent, height=height, bg=BG,
                         highlightthickness=0, bd=0, **kw)
        self._r = radius; self._track = track; self._fill = fill
        self._value = 0.0; self._maximum = 100.0
        self.bind("<Configure>", lambda e: self._redraw())

    def _rr(self, x1, y1, x2, y2, r, color):
        r = min(r, (y2-y1)//2, max(1,(x2-x1)//2))
        for sx, sy, s, e in [(x1,y1,90,90),(x2-2*r,y1,0,90),
                              (x1,y2-2*r,180,90),(x2-2*r,y2-2*r,270,90)]:
            self.create_arc(sx,sy,sx+2*r,sy+2*r, start=s, extent=e,
                            fill=color, outline=color)
        self.create_rectangle(x1+r,y1,x2-r,y2, fill=color, outline=color)
        self.create_rectangle(x1,y1+r,x2,y2-r, fill=color, outline=color)

    def _redraw(self):
        self.delete("all")
        w = self.winfo_width(); h = self.winfo_height()
        if w < 2: return
        self._rr(0,0,w,h,self._r,self._track)
        if self._maximum > 0:
            pw = int(w * self._value / self._maximum)
            if pw >= 2: self._rr(0,0,min(pw,w),h,self._r,self._fill)

    def configure(self, **kw):
        if "value"   in kw: self._value   = float(kw.pop("value"));   self._redraw()
        if "maximum" in kw: self._maximum = float(kw.pop("maximum")); self._redraw()
        if kw: super().configure(**kw)

    def __setitem__(self, k, v):
        self.configure(**{k: v})
    def __getitem__(self, k):
        if k == "value": return self._value
        if k == "maximum": return self._maximum
        return self.cget(k)


# ══════════════════════════════════════════════════════════════════
# 主应用
# ══════════════════════════════════════════════════════════════════

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(820, 560)
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{min(1020,sw-24)}x{min(1120,sh-48)}")

        self.tasks:    list[TaskItem] = []
        self.running   = False
        self._stop_flag= False
        self._gen_epoch= 0

        # 图生图参考图列表
        # 图生图三层槽位
        self._style_path:   str = ""           # ① 风格图（必选）
        self._style_thumb              = None
        self._subject_path: str = ""           # ② 主体控制图（必选）
        self._subject_thumb            = None
        self._theme_paths:  list[str] = []     # ③ 内容主题图（可选，0~2 张）
        self._theme_thumbs: list      = []

        self._setup_styles()
        self._build_ui()
        self.after(80, self._shrink_to_fit)
        self._check_key()

    # ── ttk 样式 ──────────────────────────────────────────────────
    def _setup_styles(self):
        st = ttk.Style(self)
        st.theme_use("clam")
        # Treeview
        st.configure("Dark.Treeview",
                      background=CARD, foreground=TEXT,
                      fieldbackground=CARD, rowheight=30, borderwidth=0,
                      font=("Microsoft YaHei UI", 9))
        st.configure("Dark.Treeview.Heading",
                      background=CARD2, foreground=TEXT_DIM,
                      font=("Microsoft YaHei UI", 9, "bold"),
                      borderwidth=0, relief="flat")
        st.map("Dark.Treeview",
               background=[("selected", ACCENT_L)],
               foreground=[("selected", ACCENT)])
        # Notebook
        st.configure("Dark.TNotebook", background=BG, borderwidth=0,
                      relief="flat", padding=0,
                      tabmargins=[0, 0, 0, 0])
        st.configure("Dark.TNotebook.Tab",
                      background=CARD2, foreground=TEXT_DIM,
                      padding=[20, 8], font=("Microsoft YaHei UI", 10),
                      borderwidth=0)
        st.map("Dark.TNotebook.Tab",
               background=[("selected", CARD)],
               foreground=[("selected", ACCENT)],
               expand=[("selected", [0, 0, 0, 2])])
        # Scrollbar
        st.configure("Dark.Vertical.TScrollbar",
                      background=CARD2, troughcolor=BG,
                      borderwidth=0, arrowcolor=TEXT_DIM,
                      darkcolor=CARD2, lightcolor=CARD2)
        # Combobox
        st.configure("TCombobox",
                      fieldbackground=CARD2, background=CARD2,
                      foreground=TEXT, selectbackground=ACCENT_L,
                      selectforeground=ACCENT, borderwidth=0,
                      arrowcolor=TEXT_DIM)
        st.map("TCombobox",
               fieldbackground=[("readonly", CARD2)],
               foreground=[("readonly", TEXT)])

    # ── 启动检查 ──────────────────────────────────────────────────
    def _check_key(self):
        if not get_api_key():
            self._set_status("❌ 未找到 API Key，请联系 LF", color=RED)
            self.btn_run.config(state="disabled")
        else:
            self._set_status("就绪 ✓  填写参数后点击「开始生成」")

    def _set_status(self, msg, color=TEXT_DIM):
        self.status_var.set(msg)
        self._status_lbl.configure(fg=color)

    def _shrink_to_fit(self):
        sh = self.winfo_screenheight()
        if self.winfo_height() > sh - 48:
            self.geometry(f"{self.winfo_width()}x{sh-48}")

    # ══════════════════════════════════════════════════════════════
    # 构建 UI
    # ══════════════════════════════════════════════════════════════
    def _build_ui(self):
        # ── 标题栏 ─────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=CARD2)
        hdr.pack(side="top", fill="x")
        tk.Frame(hdr, bg=ACCENT, width=4).pack(side="left", fill="y")
        inner = tk.Frame(hdr, bg=CARD2)
        inner.pack(side="left", fill="both", expand=True, padx=20, pady=12)
        tk.Label(inner, text="AI 批量生图引擎",
                 font=("Microsoft YaHei UI", 15, "bold"),
                 bg=CARD2, fg=TEXT).pack(anchor="w")
        tk.Label(inner, text="Image-MI  ·  腾讯云 AIART Midjourney  ·  一次出 4 张",
                 font=("Microsoft YaHei UI", 9),
                 bg=CARD2, fg=TEXT_DIM).pack(anchor="w", pady=(1, 0))
        tk.Label(hdr, text=APP_VERSION,
                 font=("Consolas", 9), bg=CARD2,
                 fg=ACCENT, padx=20).pack(side="right", anchor="center")

        # ── Notebook 按内容高度自适应，不撑满 ────────────────────────
        nb = self.nb = ttk.Notebook(self, style="Dark.TNotebook")
        nb.pack(side="top", fill="x")

        f1 = tk.Frame(nb, bg=BG)
        f2 = tk.Frame(nb, bg=BG)
        f3 = tk.Frame(nb, bg=BG)
        f4 = tk.Frame(nb, bg=BG)
        nb.add(f1, text="   ✦  文生图   ")
        nb.add(f2, text="   ⬡  图生图   ")
        nb.add(f3, text="   ⚡  自动模式   ")
        nb.add(f4, text="   ✧  自由创作   ")

        self._build_txt2img_tab(f1)
        self._build_img2img_tab(f2)
        self._build_auto_tab(f3)
        self._build_free_gen_tab(f4)

        # ── 底部面板紧接 Notebook 之后 ─────────────────────────────
        self._bottom = tk.Frame(self, bg=BG)
        self._bottom.pack(side="top", fill="x")
        self._build_bottom_panel(self._bottom)

    # ══════════════════════════════════════════════════════════════
    # Tab 1：文生图
    # ══════════════════════════════════════════════════════════════
    def _build_txt2img_tab(self, parent):
        pad = dict(padx=12, pady=5)

        # ── 巨构快速填充 ──────────────────────────────────────────
        quick = self._card(parent, "① 快速填充（选好后点「→ 生成提示词」）")
        quick.pack(fill="x", **pad)

        row1 = tk.Frame(quick, bg=CARD); row1.pack(fill="x", padx=10, pady=(4,0))
        tk.Label(row1, text="结构", bg=CARD, fg=TEXT_DIM,
                 font=("Microsoft YaHei UI",9,"bold")).grid(row=0, column=0, sticky="w")
        self.struct_var = tk.StringVar(value=STRUCT_PRESETS[0])
        ttk.Combobox(row1, textvariable=self.struct_var,
                     values=STRUCT_PRESETS, width=40, state="normal"
                     ).grid(row=0, column=1, padx=(6,20), sticky="ew")

        tk.Label(row1, text="光效", bg=CARD, fg=TEXT_DIM,
                 font=("Microsoft YaHei UI",9,"bold")).grid(row=0, column=2, sticky="w")
        self.light_var = tk.StringVar(value=LIGHT_PRESETS[0])
        ttk.Combobox(row1, textvariable=self.light_var,
                     values=LIGHT_PRESETS, width=34, state="normal"
                     ).grid(row=0, column=3, padx=6, sticky="ew")
        row1.columnconfigure(1, weight=1); row1.columnconfigure(3, weight=1)

        row2 = tk.Frame(quick, bg=CARD); row2.pack(fill="x", padx=10, pady=(4,6))
        tk.Label(row2, text="情绪", bg=CARD, fg=TEXT_DIM,
                 font=("Microsoft YaHei UI",9,"bold")).grid(row=0, column=0, sticky="w")
        self.mood_var = tk.StringVar(value=MOOD_PRESETS[0])
        ttk.Combobox(row2, textvariable=self.mood_var,
                     values=MOOD_PRESETS, width=36, state="normal"
                     ).grid(row=0, column=1, padx=(6,20), sticky="ew")

        tk.Button(row2, text="→ 填充提示词",
                  bg=ACCENT, fg="white",
                  activebackground=ACCENT_H, activeforeground="white",
                  relief="flat", padx=14, pady=4,
                  font=("Microsoft YaHei UI", 9, "bold"),
                  cursor="hand2",
                  command=self._fill_prompt_from_presets
                  ).grid(row=0, column=2, padx=4)
        tk.Button(row2, text="清空",
                  bg=CARD2, fg=TEXT_HINT,
                  activebackground=HOVER_BG, activeforeground=RED,
                  relief="flat", padx=8, pady=4,
                  font=("Microsoft YaHei UI", 9),
                  cursor="hand2",
                  command=lambda: self.prompt_txt.delete("1.0", "end")
                  ).grid(row=0, column=3, padx=4)
        row2.columnconfigure(1, weight=1)

        # ── 提示词输入 ────────────────────────────────────────────
        pc = self._card(parent, "② 提示词（可直接编辑，支持 MJ 参数 --ar --v --stylize）")
        pc.pack(fill="x", **pad)
        self.prompt_txt = tk.Text(pc, height=5, bg=CARD, fg=TEXT,
                                   insertbackground=TEXT,
                                   relief="flat", font=("Consolas",9),
                                   wrap="word", padx=8, pady=6,
                                   highlightthickness=1,
                                   highlightcolor=ACCENT,
                                   highlightbackground=BORDER)
        self.prompt_txt.pack(fill="x", padx=10, pady=(4,10))
        self.prompt_txt.insert("1.0",
            "倒置的粗野主义巨塔，黄金时刻逆光，丁达尔光柱，"
            "荒芜孤寂，深沉的孤独感，电影级构图，"
            "a single lone figure for scale，超写实，8K画质")

        # ── MJ 参数 ───────────────────────────────────────────────
        pp = self._card(parent, "③ MJ 参数")
        pp.pack(fill="x", **pad)
        prow = tk.Frame(pp, bg=CARD); prow.pack(fill="x", padx=10, pady=(4,10))

        def _lbl(t): return tk.Label(prow, text=t, bg=CARD, fg=TEXT_DIM,
                                     font=("Microsoft YaHei UI",9,"bold"))
        def _sp(w=8): return tk.Label(prow, text=" "*w, bg=CARD)

        _lbl("比例").pack(side="left")
        self.t2i_ar_var = tk.StringVar(value="16:9")
        ttk.Combobox(prow, textvariable=self.t2i_ar_var,
                     values=list(ASPECT_MAP.keys()), width=7, state="readonly"
                     ).pack(side="left", padx=(4,0))
        _sp(16).pack(side="left")

        _lbl("版本").pack(side="left")
        self.t2i_ver_var = tk.StringVar(value="7")
        ttk.Combobox(prow, textvariable=self.t2i_ver_var,
                     values=["7","6.1","6","5.2"], width=6, state="readonly"
                     ).pack(side="left", padx=(4,0))
        _sp(16).pack(side="left")

        _lbl("Stylize").pack(side="left")
        self.t2i_stylize_var = tk.StringVar(value="850")
        tk.Entry(prow, textvariable=self.t2i_stylize_var, width=6,
                 bg=CARD2, fg=TEXT, insertbackground=TEXT,
                 relief="flat", highlightthickness=1,
                 highlightbackground=BORDER, highlightcolor=ACCENT,
                 font=("Consolas", 9)
                 ).pack(side="left", padx=(4, 0))
        _sp(16).pack(side="left")

        _lbl("生成 N 张").pack(side="left")
        self.t2i_n_var = tk.StringVar(value="1")
        tk.Spinbox(prow, textvariable=self.t2i_n_var, from_=1, to=20,
                   width=4, bg=CARD2, fg=TEXT,
                   buttonbackground=CARD2,
                   relief="flat", highlightthickness=1,
                   highlightbackground=BORDER,
                   font=("Microsoft YaHei UI", 9)
                   ).pack(side="left", padx=(4, 0))


    # ══════════════════════════════════════════════════════════════
    # Tab 2：图生图
    # ══════════════════════════════════════════════════════════════
    def _build_img2img_tab(self, parent):
        pad = dict(padx=12, pady=5)

        def _slot_card(title, hint, pick_cmd, clear_cmd, thumb_attr, status_attr):
            """构建单张图片槽位卡片，返回 (card_frame, thumb_label, status_label)"""
            card = self._card(parent, title)
            card.pack(fill="x", **pad)
            row = tk.Frame(card, bg=CARD)
            row.pack(fill="x", padx=10, pady=(4, 2))
            tk.Button(row, text="＋ 选择图片",
                      bg=ACCENT, fg="white",
                      activebackground=ACCENT_H, activeforeground="white",
                      relief="flat", padx=12, pady=3,
                      font=("Microsoft YaHei UI", 9, "bold"),
                      cursor="hand2", command=pick_cmd).pack(side="left")
            tk.Button(row, text="清除",
                      bg=CARD2, fg=TEXT_HINT,
                      activebackground=HOVER_BG, activeforeground=RED,
                      relief="flat", padx=8, pady=3,
                      cursor="hand2", command=clear_cmd).pack(side="left", padx=6)
            status_lbl = tk.Label(row, text=hint,
                                  bg=CARD, fg=TEXT_HINT,
                                  font=("Microsoft YaHei UI", 8))
            status_lbl.pack(side="left", padx=6)
            thumb_area = tk.Frame(card, bg=CARD)
            thumb_area.pack(fill="x", padx=10, pady=(2, 8))
            thumb_lbl = tk.Label(thumb_area, bg=CARD)
            thumb_lbl.pack(side="left")
            name_lbl  = tk.Label(thumb_area, text="", bg=CARD, fg=TEXT_DIM,
                                 font=("Microsoft YaHei UI", 7))
            name_lbl.pack(side="left", padx=6)
            setattr(self, thumb_attr,  thumb_lbl)
            setattr(self, status_attr, status_lbl)
            setattr(self, thumb_attr + "_name", name_lbl)
            return card

        # ── ① 风格图 ─────────────────────────────────────────────
        _slot_card(
            "① 风格图（必选）  定义视觉风格 / 光影色调 / 构图方式",
            "未选择",
            self._pick_style, self._clear_style,
            "_style_thumb_lbl", "_style_status_lbl")

        # ── ② 主体控制图 ─────────────────────────────────────────
        _slot_card(
            "② 主体控制图（必选）  定义核心主体结构形态 / 几何特征 / 材质",
            "未选择",
            self._pick_subject, self._clear_subject,
            "_subject_thumb_lbl", "_subject_status_lbl")

        # ── ③ 内容主题图 ─────────────────────────────────────────
        tc = self._card(parent, "③ 内容主题图（可选，最多 2 张）  定义场景意境 / 情绪氛围")
        tc.pack(fill="x", **pad)
        t_row = tk.Frame(tc, bg=CARD)
        t_row.pack(fill="x", padx=10, pady=(4, 2))
        tk.Button(t_row, text="＋ 添加主题图",
                  bg=CARD2, fg=TEXT,
                  activebackground=HOVER_BG, activeforeground=ACCENT,
                  relief="flat", padx=12, pady=3,
                  font=("Microsoft YaHei UI", 9),
                  cursor="hand2", command=self._add_themes).pack(side="left")
        tk.Button(t_row, text="清空",
                  bg=CARD2, fg=TEXT_HINT,
                  activebackground=HOVER_BG, activeforeground=RED,
                  relief="flat", padx=8, pady=3,
                  cursor="hand2", command=self._clear_themes).pack(side="left", padx=6)
        self._theme_count_lbl = tk.Label(t_row, text="已选 0 张",
                                          bg=CARD, fg=TEXT_HINT,
                                          font=("Microsoft YaHei UI", 8))
        self._theme_count_lbl.pack(side="left", padx=6)
        self._theme_strip = tk.Frame(tc, bg=CARD)
        self._theme_strip.pack(fill="x", padx=10, pady=(2, 8))

        # ── ④ 追加提示词（可选）──────────────────────────────────
        ep = self._card(parent, "④ 追加提示词（可选）")
        ep.pack(fill="x", **pad)

        hint_row = tk.Frame(ep, bg=CARD)
        hint_row.pack(fill="x", padx=10, pady=(6, 2))
        tk.Label(hint_row,
                 text="点「▶ 开始生成」后，Gemini 将自动三层反推提示词 → Image-MI 生图",
                 bg=CARD, fg=TEXT_HINT,
                 font=("Microsoft YaHei UI", 8)).pack(side="left")

        extra_hint_row = tk.Frame(ep, bg=CARD)
        extra_hint_row.pack(fill="x", padx=10, pady=(0, 2))
        tk.Label(extra_hint_row,
                 text="此处内容可选，将追加到 Gemini 生成的 prompt 末尾",
                 bg=CARD, fg=TEXT_HINT,
                 font=("Microsoft YaHei UI", 8, "italic")).pack(side="left")

        self.i2i_extra_txt = tk.Text(ep, height=3, bg=CARD, fg=TEXT,
                                      insertbackground=TEXT,
                                      relief="flat", font=("Consolas", 9),
                                      wrap="word", padx=8, pady=6,
                                      highlightthickness=1,
                                      highlightcolor=ACCENT,
                                      highlightbackground=BORDER)
        self.i2i_extra_txt.pack(fill="x", padx=10, pady=(2, 10))

        # ── ⑤ 输出参数 ───────────────────────────────────────────
        pp = self._card(parent, "⑤ 输出参数")
        pp.pack(fill="x", **pad)
        prow = tk.Frame(pp, bg=CARD)
        prow.pack(fill="x", padx=10, pady=(4, 10))

        def _lbl(t): return tk.Label(prow, text=t, bg=CARD, fg=TEXT_DIM,
                                     font=("Microsoft YaHei UI", 9, "bold"))
        def _sp(w=8): return tk.Label(prow, text=" " * w, bg=CARD)

        _lbl("比例").pack(side="left")
        self.i2i_ar_var = tk.StringVar(value="16:9")
        ttk.Combobox(prow, textvariable=self.i2i_ar_var,
                     values=list(ASPECT_MAP.keys()), width=7, state="readonly"
                     ).pack(side="left", padx=(4, 0))
        _sp(16).pack(side="left")

        _lbl("版本").pack(side="left")
        self.i2i_ver_var = tk.StringVar(value="7")
        ttk.Combobox(prow, textvariable=self.i2i_ver_var,
                     values=["7", "6.1", "6", "5.2"], width=6, state="readonly"
                     ).pack(side="left", padx=(4, 0))
        _sp(16).pack(side="left")

        _lbl("Stylize").pack(side="left")
        self.i2i_stylize_var = tk.StringVar(value="900")
        tk.Entry(prow, textvariable=self.i2i_stylize_var, width=6,
                 bg=CARD2, fg=TEXT, insertbackground=TEXT,
                 relief="flat", highlightthickness=1,
                 highlightbackground=BORDER, highlightcolor=ACCENT,
                 font=("Consolas", 9)
                 ).pack(side="left", padx=(4, 0))
        _sp(16).pack(side="left")

        _lbl("生成 N 张").pack(side="left")
        self.i2i_n_var = tk.StringVar(value="1")
        tk.Spinbox(prow, textvariable=self.i2i_n_var, from_=1, to=20,
                   width=4, bg=CARD2, fg=TEXT,
                   buttonbackground=CARD2,
                   relief="flat", highlightthickness=1,
                   highlightbackground=BORDER,
                   font=("Microsoft YaHei UI", 9)
                   ).pack(side="left", padx=(4, 0))
        _sp(16).pack(side="left")

        tk.Label(prow, text="每次「开始生成」重复提交 N 次",
                 bg=CARD, fg=TEXT_HINT,
                 font=("Microsoft YaHei UI", 8)).pack(side="left")

    # ══════════════════════════════════════════════════════════════
    # Tab 3：自动模式
    # ══════════════════════════════════════════════════════════════
    def _build_auto_tab(self, parent):
        pad = dict(padx=12, pady=5)

        self._auto_folder: str = ""          # 选中的图片文件夹路径
        self._auto_thumb_imgs: list = []     # 缩略图引用（防止 GC）
        self._pinterest_proc = None          # Pinterest 抓图子进程

        # ── ① 主题词 + Pinterest 抓图 ─────────────────────────────
        card_theme = self._card(parent, "① 主题关键词")
        card_theme.pack(fill="x", **pad)
        theme_row = tk.Frame(card_theme, bg=CARD)
        theme_row.pack(fill="x", padx=10, pady=(4, 4))
        self.auto_theme_var = tk.StringVar(value="")
        tk.Entry(theme_row, textvariable=self.auto_theme_var,
                 bg=CARD2, fg=TEXT, relief="flat",
                 font=("Microsoft YaHei UI", 10),
                 insertbackground=TEXT).pack(fill="x")
        tk.Label(card_theme,
                 text='  例如："废土城市"  "megastructure brutalist"  "冰川神殿"',
                 bg=CARD, fg=TEXT_HINT,
                 font=("Microsoft YaHei UI", 8)).pack(anchor="w", padx=10, pady=(0, 2))

        # Pinterest 抓图子行
        pin_row = tk.Frame(card_theme, bg=CARD)
        pin_row.pack(fill="x", padx=10, pady=(2, 8))
        tk.Label(pin_row, text="抓取数量:", bg=CARD, fg=TEXT_DIM,
                 font=("Microsoft YaHei UI", 9)).pack(side="left")
        self.auto_pin_n_var = tk.StringVar(value="5")
        tk.Spinbox(pin_row, from_=5, to=80, width=4,
                   textvariable=self.auto_pin_n_var,
                   bg=CARD2, fg=TEXT, relief="flat",
                   buttonbackground=CARD2).pack(side="left", padx=(4, 12))
        self.btn_pinterest = tk.Button(
            pin_row, text="📌 从 Pinterest 抓图",
            bg="#E60023", fg="white",
            activebackground="#AD081B", activeforeground="white",
            relief="flat", padx=10, pady=3,
            font=("Microsoft YaHei UI", 9, "bold"),
            cursor="hand2",
            command=self._start_pinterest_scrape)
        self.btn_pinterest.pack(side="left")
        self._pin_status_lbl = tk.Label(
            pin_row, text="", bg=CARD, fg=TEXT_HINT,
            font=("Microsoft YaHei UI", 8))
        self._pin_status_lbl.pack(side="left", padx=8)

        # ── ② 图片文件夹 ──────────────────────────────────────────
        card_folder = self._card(parent, "② 本地参考图文件夹（AI 自动从中选材）")
        card_folder.pack(fill="x", **pad)

        folder_row = tk.Frame(card_folder, bg=CARD)
        folder_row.pack(fill="x", padx=10, pady=(4, 4))
        tk.Button(folder_row, text="📂 选择文件夹",
                  bg=ACCENT, fg="white",
                  activebackground=ACCENT_H, activeforeground="white",
                  relief="flat", padx=12, pady=3,
                  font=("Microsoft YaHei UI", 9, "bold"),
                  cursor="hand2",
                  command=self._auto_pick_folder).pack(side="left")
        self._auto_folder_lbl = tk.Label(
            folder_row, text="未选择", bg=CARD, fg=TEXT_HINT,
            font=("Microsoft YaHei UI", 9))
        self._auto_folder_lbl.pack(side="left", padx=10)

        # 缩略图预览区（滚动）
        preview_outer = tk.Frame(card_folder, bg=CARD2, relief="flat",
                                 highlightthickness=1,
                                 highlightbackground=BORDER)
        preview_outer.pack(fill="x", padx=10, pady=(2, 8))
        self._auto_preview_frame = tk.Frame(preview_outer, bg=CARD2)
        self._auto_preview_frame.pack(fill="x", padx=4, pady=4)
        self._auto_preview_lbl = tk.Label(
            self._auto_preview_frame,
            text="选择文件夹后这里显示候选图片缩略图",
            bg=CARD2, fg=TEXT_HINT,
            font=("Microsoft YaHei UI", 8))
        self._auto_preview_lbl.pack(pady=12)

        # ── ③ 参数设置 ────────────────────────────────────────────
        card_param = self._card(parent, "③ 生成参数")
        card_param.pack(fill="x", **pad)
        prow = tk.Frame(card_param, bg=CARD)
        prow.pack(fill="x", padx=10, pady=(4, 8))

        def _sp(w): return tk.Frame(prow, bg=CARD, width=w, height=1)

        tk.Label(prow, text="比例", bg=CARD, fg=TEXT_DIM,
                 font=("Microsoft YaHei UI", 9, "bold")).pack(side="left")
        _sp(4).pack(side="left")
        self.auto_ar_var = tk.StringVar(value="16:9")
        ttk.Combobox(prow, textvariable=self.auto_ar_var,
                     values=["16:9","4:3","1:1","9:16","3:4"],
                     width=7, state="readonly").pack(side="left")
        _sp(20).pack(side="left")

        tk.Label(prow, text="批次数", bg=CARD, fg=TEXT_DIM,
                 font=("Microsoft YaHei UI", 9, "bold")).pack(side="left")
        _sp(4).pack(side="left")
        self.auto_n_var = tk.StringVar(value="1")
        tk.Spinbox(prow, from_=1, to=20, width=4,
                   textvariable=self.auto_n_var,
                   bg=CARD2, fg=TEXT, relief="flat",
                   buttonbackground=CARD2).pack(side="left")
        _sp(8).pack(side="left")
        tk.Label(prow, text="批（每批出 4 张，每批重新选材）",
                 bg=CARD, fg=TEXT_HINT,
                 font=("Microsoft YaHei UI", 8)).pack(side="left")

        # ── ④ 选材结果预览 ────────────────────────────────────────
        card_result = self._card(parent, "④ Gemini 选材结果预览（生成后自动填入）")
        card_result.pack(fill="x", **pad)
        self._auto_result_lbl = tk.Label(
            card_result,
            text="点击「一键生成」后，此处显示 Gemini 从文件夹中自动选出的三层图片",
            bg=CARD, fg=TEXT_HINT, justify="left",
            font=("Microsoft YaHei UI", 8), wraplength=580)
        self._auto_result_lbl.pack(padx=10, pady=8, anchor="w")

        # ── 生成按钮 ──────────────────────────────────────────────
        btn_row = tk.Frame(parent, bg=BG)
        btn_row.pack(fill="x", padx=12, pady=(4, 8))
        self.btn_auto_run = tk.Button(
            btn_row,
            text="⚡  一键生成（AI 自动选材 → 图生图）",
            bg=TEAL, fg="white",
            activebackground="#0F766E", activeforeground="white",
            relief="flat", padx=20, pady=8,
            font=("Microsoft YaHei UI", 10, "bold"),
            cursor="hand2",
            command=self._start_auto_generation)
        self.btn_auto_run.pack(side="left")

    # Pinterest 抓图项目路径
    def _start_pinterest_scrape(self):
        """用 Python playwright 抓 Pinterest 图片，不依赖 Node.js"""
        query = self.auto_theme_var.get().strip()
        if not query:
            messagebox.showwarning("Pinterest 抓图", "请先填写主题关键词")
            return
        try:
            n_limit = int(self.auto_pin_n_var.get() or 5)
        except ValueError:
            n_limit = 5

        self.btn_pinterest.config(state="disabled")
        self._pin_status_lbl.config(text="⏳ 抓图中…", fg=AMBER)

        def _worker():
            try:
                out_dir = _scrape_pinterest(
                    query=query,
                    limit=n_limit,
                    progress_cb=lambda msg: self.after(
                        0, lambda m=msg: self._pin_status_lbl.config(
                            text=m[:70], fg=TEXT_DIM))
                )
                self.after(0, lambda d=out_dir: self._on_pinterest_done(d))
            except Exception as e:
                self.after(0, lambda err=str(e): (
                    self._pin_status_lbl.config(text=f"❌ {err[:60]}", fg=RED),
                    self.btn_pinterest.config(state="normal")))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_pinterest_done(self, out_dir: str):
        """Pinterest 抓图完成，自动填入文件夹"""
        exts = {".png", ".jpg", ".jpeg", ".webp", ".avif"}
        imgs = [str(p) for p in Path(out_dir).iterdir()
                if p.suffix.lower() in exts]
        self._auto_folder = out_dir
        lbl = f"{Path(out_dir).name}  （{len(imgs)} 张图）"
        self._auto_folder_lbl.config(text=lbl, fg=TEXT)
        self._pin_status_lbl.config(
            text=f"✓ 已抓取 {len(imgs)} 张，已自动填入文件夹", fg=GREEN)
        self.btn_pinterest.config(state="normal")
        self._refresh_auto_preview(imgs)

    def _auto_pick_folder(self):
        folder = filedialog.askdirectory(title="选择参考图文件夹")
        if not folder:
            return
        self._auto_folder = folder
        exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
        imgs = [str(p) for p in Path(folder).iterdir()
                if p.suffix.lower() in exts]
        lbl = (Path(folder).name + f"  （{len(imgs)} 张图）"
               if imgs else "（文件夹中未找到图片）")
        self._auto_folder_lbl.config(text=lbl, fg=TEXT if imgs else RED)
        self._refresh_auto_preview(imgs)

    def _refresh_auto_preview(self, img_paths: list):
        """刷新候选图缩略图预览（最多显示 12 张）"""
        for w in self._auto_preview_frame.winfo_children():
            w.destroy()
        self._auto_thumb_imgs.clear()

        paths = img_paths[:12]
        if not paths:
            tk.Label(self._auto_preview_frame,
                     text="文件夹中没有图片",
                     bg=CARD2, fg=TEXT_HINT,
                     font=("Microsoft YaHei UI", 8)).pack(pady=10)
            return

        cols = min(len(paths), 6)
        for i, p in enumerate(paths):
            try:
                pil = Image.open(p)
                pil.thumbnail((80, 60))
                tkimg = ImageTk.PhotoImage(pil)
                self._auto_thumb_imgs.append(tkimg)
                cell = tk.Frame(self._auto_preview_frame, bg=CARD2)
                cell.grid(row=i // cols, column=i % cols, padx=2, pady=2)
                tk.Label(cell, image=tkimg, bg=CARD2).pack()
                tk.Label(cell, text=Path(p).stem[:8],
                         bg=CARD2, fg=TEXT_HINT,
                         font=("Microsoft YaHei UI", 7)).pack()
            except Exception:
                pass

        if len(img_paths) > 12:
            tk.Label(self._auto_preview_frame,
                     text=f"… 共 {len(img_paths)} 张，显示前 12 张",
                     bg=CARD2, fg=TEXT_HINT,
                     font=("Microsoft YaHei UI", 8)).grid(
                         row=len(paths) // cols + 1,
                         column=0, columnspan=cols, pady=4)

    def _start_auto_generation(self):
        if not self._auto_folder:
            messagebox.showwarning("自动模式", "请先选择参考图文件夹")
            return
        exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
        all_imgs = [str(p) for p in Path(self._auto_folder).iterdir()
                    if p.suffix.lower() in exts]
        if not all_imgs:
            messagebox.showwarning("自动模式", "所选文件夹中没有图片")
            return

        if self.running:
            messagebox.showwarning("提示", "当前有任务正在执行，请等待完成后再提交")
            return

        theme    = self.auto_theme_var.get().strip()
        n_batch  = max(1, int(self.auto_n_var.get() or 1))
        ar       = self.auto_ar_var.get()

        self.running    = True
        self._stop_flag = False
        self._gen_epoch += 1
        self.btn_auto_run.config(state="disabled")
        self.btn_run.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.progress_bar["value"] = 0
        self._set_status("⚡ 自动模式启动：Gemini 选材中…", color=TEAL)

        epoch = self._gen_epoch

        def _worker():
            try:
                def pcb(msg): self.after(0, lambda m=msg: self._set_status(m, color=TEAL))

                # 每批单独选材
                new_tasks = []
                for batch_i in range(n_batch):
                    if self._stop_flag:
                        break
                    pcb(f"[批次 {batch_i+1}/{n_batch}] Gemini 自动选材…")
                    sel = call_gemini_select_materials(all_imgs, theme, pcb)

                    style   = sel.get("style", "")
                    subject = sel.get("subject", "")
                    themes  = sel.get("theme", [])

                    # 更新选材结果预览（最后一批）
                    def _update_result(s=style, sub=subject, th=themes):
                        lines = [
                            f"风格图：{Path(s).name if s else '未选'}",
                            f"主体图：{Path(sub).name if sub else '未选'}",
                            f"主题图：{', '.join(Path(t).name for t in th) if th else '无'}",
                        ]
                        self._auto_result_lbl.config(
                            text="\n".join(lines), fg=TEXT)
                    self.after(0, _update_result)

                    ref_paths = [p for p in [style, subject] + themes if p]
                    if not ref_paths:
                        continue
                    new_tasks.append(TaskItem(
                        "img2img",
                        ref_paths=ref_paths,
                        ar=ar,
                        extra_prompt=theme))

                if not new_tasks:
                    self.after(0, lambda: messagebox.showwarning(
                        "自动模式", "Gemini 选材结果为空，请检查文件夹图片"))
                    return

                self.after(0, lambda tasks=new_tasks: self._submit_and_run(tasks, epoch))

            except Exception as e:
                err = str(e)
                self.after(0, lambda: self._set_status(f"自动模式失败：{err}", color=RED))
                self.after(0, self._reset_run_buttons)

        threading.Thread(target=_worker, daemon=True).start()

    def _submit_and_run(self, new_tasks: list, epoch: int):
        """在主线程中把任务加队列并启动批次执行"""
        self.tasks.extend(new_tasks)
        self._rebuild_tv()
        threading.Thread(target=self._run_batch,
                         args=(new_tasks, epoch),
                         daemon=True).start()

    # ══════════════════════════════════════════════════════════════
    # Tab 4：自由创作（LLM 引导式自定义生图）
    # ══════════════════════════════════════════════════════════════
    def _build_free_gen_tab(self, parent):
        pad = dict(padx=12, pady=5)
        self._fg_options_list = []   # list of (option_text, tk.BooleanVar)
        self._fg_style_path   = ""

        # ── Card 1：用户描述 ────────────────────────────────────────
        c1 = self._card(parent, "① 描述你想要的图像（一句话）", accent=TEAL)
        c1.pack(fill="x", **pad)

        desc_row = tk.Frame(c1, bg=CARD)
        desc_row.pack(fill="x", padx=10, pady=(4, 8))

        self._fg_desc_txt = tk.Text(
            desc_row, height=3, bg=CARD2, fg=TEXT,
            insertbackground=TEXT, relief="flat",
            font=("Microsoft YaHei UI", 10), wrap="word",
            padx=8, pady=6,
            highlightthickness=1, highlightcolor=TEAL,
            highlightbackground=BORDER)
        self._fg_desc_txt.pack(side="left", fill="x", expand=True)
        self._fg_desc_txt.insert("1.0", "我要一张...")

        self._fg_gen_btn = tk.Button(
            desc_row, text="✦ 生成\n30个方向",
            bg=TEAL, fg="white",
            activebackground="#0F766E", activeforeground="white",
            relief="flat", padx=12, pady=6,
            font=("Microsoft YaHei UI", 9, "bold"),
            cursor="hand2",
            command=self._fg_generate_options)
        self._fg_gen_btn.pack(side="left", padx=(8, 0))

        # ── Card 2：选项列表 ────────────────────────────────────────
        c2 = self._card(parent, "② 选择内容方向（多选，支持全选/反选）", accent=TEAL)
        c2.pack(fill="x", **pad)

        ops_row = tk.Frame(c2, bg=CARD)
        ops_row.pack(fill="x", padx=10, pady=(4, 2))

        def _select_all():
            for _, v in self._fg_options_list: v.set(True)
            self._fg_update_count()
        def _invert():
            for _, v in self._fg_options_list: v.set(not v.get())
            self._fg_update_count()
        def _clear_sel():
            for _, v in self._fg_options_list: v.set(False)
            self._fg_update_count()

        for label, cmd in [("全选", _select_all), ("反选", _invert), ("清空", _clear_sel)]:
            tk.Button(ops_row, text=label, bg=CARD2, fg=TEXT_DIM,
                      relief="flat", padx=8, pady=2,
                      font=("Microsoft YaHei UI", 9),
                      cursor="hand2", command=cmd).pack(side="left", padx=(0, 4))

        self._fg_sel_lbl = tk.Label(ops_row, text="已选 0 项",
                                    bg=CARD, fg=TEXT_DIM,
                                    font=("Microsoft YaHei UI", 9))
        self._fg_sel_lbl.pack(side="left", padx=8)

        # 可滚动选项区
        scroll_wrap = tk.Frame(c2, bg=CARD, height=210)
        scroll_wrap.pack(fill="x", padx=10, pady=(2, 8))
        scroll_wrap.pack_propagate(False)

        self._fg_opts_canvas = tk.Canvas(scroll_wrap, bg=CARD,
                                          highlightthickness=0)
        _sb = ttk.Scrollbar(scroll_wrap, orient="vertical",
                            command=self._fg_opts_canvas.yview,
                            style="Dark.Vertical.TScrollbar")
        self._fg_opts_canvas.configure(yscrollcommand=_sb.set)
        _sb.pack(side="right", fill="y")
        self._fg_opts_canvas.pack(side="left", fill="both", expand=True)

        self._fg_opts_inner = tk.Frame(self._fg_opts_canvas, bg=CARD)
        self._fg_opts_inner_id = self._fg_opts_canvas.create_window(
            (0, 0), window=self._fg_opts_inner, anchor="nw")

        def _on_opts_configure(e):
            self._fg_opts_canvas.configure(
                scrollregion=self._fg_opts_canvas.bbox("all"))
            self._fg_opts_canvas.itemconfig(
                self._fg_opts_inner_id,
                width=self._fg_opts_canvas.winfo_width())
        self._fg_opts_inner.bind("<Configure>", _on_opts_configure)

        def _on_fg_wheel(e):
            self._fg_opts_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        for _w in (self._fg_opts_canvas, self._fg_opts_inner, scroll_wrap):
            _w.bind("<MouseWheel>", _on_fg_wheel)

        # Placeholder
        self._fg_placeholder = tk.Label(
            self._fg_opts_inner,
            text="点击「生成30个方向」后，选项将显示在这里",
            bg=CARD, fg=TEXT_HINT,
            font=("Microsoft YaHei UI", 10))
        self._fg_placeholder.pack(pady=30)

        # ── Card 3：风格参考图（可选）──────────────────────────────
        c3 = self._card(parent, "③ 风格参考图（可选，用作画面风格引导）", accent=TEAL)
        c3.pack(fill="x", **pad)

        style_row = tk.Frame(c3, bg=CARD)
        style_row.pack(fill="x", padx=10, pady=(4, 8))

        self._fg_thumb_lbl = tk.Label(
            style_row, bg=CARD2, width=8, height=4,
            text="点击选图", fg=TEXT_HINT,
            font=("Microsoft YaHei UI", 9),
            relief="flat", cursor="hand2")
        self._fg_thumb_lbl.pack(side="left")
        self._fg_thumb_lbl.bind("<Button-1>", lambda e: self._fg_pick_style())

        style_info = tk.Frame(style_row, bg=CARD)
        style_info.pack(side="left", fill="x", expand=True, padx=(12, 0))

        self._fg_style_name_lbl = tk.Label(
            style_info, text="", bg=CARD, fg=TEXT,
            font=("Microsoft YaHei UI", 9))
        self._fg_style_name_lbl.pack(anchor="w")

        self._fg_style_status_lbl = tk.Label(
            style_info, text="未选择（可选）", bg=CARD, fg=TEXT_HINT,
            font=("Microsoft YaHei UI", 9))
        self._fg_style_status_lbl.pack(anchor="w", pady=(2, 0))

        tk.Button(style_info, text="清除",
                  bg=CARD2, fg=TEXT_HINT, relief="flat",
                  padx=6, pady=2, font=("Microsoft YaHei UI", 9),
                  cursor="hand2",
                  command=self._fg_clear_style).pack(anchor="w", pady=(4, 0))

        # ── Card 4：MJ 参数 ─────────────────────────────────────────
        c4 = self._card(parent, "④ MJ 参数", accent=TEAL)
        c4.pack(fill="x", **pad)

        p_row = tk.Frame(c4, bg=CARD)
        p_row.pack(fill="x", padx=10, pady=(4, 10))

        def _lbl(t): return tk.Label(p_row, text=t, bg=CARD, fg=TEXT_DIM,
                                     font=("Microsoft YaHei UI", 9, "bold"))
        def _sp():   return tk.Label(p_row, text="  ", bg=CARD)

        _lbl("比例").pack(side="left")
        self._fg_ar_var = tk.StringVar(value="16:9")
        ttk.Combobox(p_row, textvariable=self._fg_ar_var,
                     values=list(ASPECT_MAP.keys()), width=7,
                     state="readonly").pack(side="left", padx=(4, 0))
        _sp().pack(side="left")

        _lbl("质量").pack(side="left")
        self._fg_stylize_var = tk.StringVar(value="高质量")
        ttk.Combobox(p_row, textvariable=self._fg_stylize_var,
                     values=["标准", "高质量", "极致"],
                     width=7, state="readonly").pack(side="left", padx=(4, 0))
        _sp().pack(side="left")

        _lbl("版本").pack(side="left")
        self._fg_ver_var = tk.StringVar(value="7")
        ttk.Combobox(p_row, textvariable=self._fg_ver_var,
                     values=["6", "6.1", "7"], width=5,
                     state="readonly").pack(side="left", padx=(4, 0))

        # ── 操作按钮行 ──────────────────────────────────────────────
        btn_row = tk.Frame(parent, bg=BG)
        btn_row.pack(fill="x", padx=12, pady=(4, 10))

        self.btn_free_run = tk.Button(
            btn_row,
            text="🚀  开始批量生图",
            bg=TEAL, fg="white",
            activebackground="#0F766E", activeforeground="white",
            relief="flat", padx=20, pady=8,
            font=("Microsoft YaHei UI", 10, "bold"),
            cursor="hand2",
            command=self._fg_start_batch)
        self.btn_free_run.pack(side="left")

        self._fg_count_lbl = tk.Label(
            btn_row, text="",
            bg=BG, fg=TEXT_DIM,
            font=("Microsoft YaHei UI", 9))
        self._fg_count_lbl.pack(side="left", padx=12)

    # ── 自由创作助手方法 ──────────────────────────────────────────

    def _fg_pick_style(self):
        p = self._pick_single("选择风格参考图")
        if not p:
            return
        self._fg_style_path = p
        self._fg_style_name_lbl.config(text=Path(p).name[:30])
        self._fg_style_status_lbl.config(text="✓ 已选择", fg=GREEN)
        try:
            ph = load_thumbnail(p, (64, 64))
            self._fg_thumb_lbl.config(image=ph, text="")
            self._fg_thumb_lbl._ph = ph
        except Exception:
            pass

    def _fg_clear_style(self):
        self._fg_style_path = ""
        self._fg_thumb_lbl.config(image="", text="点击选图", fg=TEXT_HINT)
        self._fg_thumb_lbl._ph = None
        self._fg_style_name_lbl.config(text="")
        self._fg_style_status_lbl.config(text="未选择（可选）", fg=TEXT_HINT)

    def _fg_generate_options(self):
        user_input = self._fg_desc_txt.get("1.0", "end-1c").strip()
        if not user_input or user_input == "我要一张...":
            messagebox.showwarning("自由创作", "请先描述你想要的图像")
            return
        self._fg_gen_btn.config(state="disabled", text="生成中…")
        self._set_status("Gemini 生成内容方向中，约 10~20 秒…", color=TEAL)

        def _worker():
            try:
                opts = call_gemini_free_gen_options(
                    user_input,
                    progress_cb=lambda m: self.after(0, lambda: self._set_status(m)))
                self.after(0, lambda: self._fg_populate_options(opts))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Gemini 错误", str(e)))
                self.after(0, lambda: self._set_status("生成方向失败，请重试", color=RED))
            finally:
                self.after(0, lambda: self._fg_gen_btn.config(
                    state="normal", text="✦ 生成\n30个方向"))

        threading.Thread(target=_worker, daemon=True).start()

    def _fg_populate_options(self, options: list):
        for w in self._fg_opts_inner.winfo_children():
            w.destroy()
        self._fg_options_list.clear()

        if not options:
            tk.Label(self._fg_opts_inner, text="生成失败，请重试",
                     bg=CARD, fg=RED,
                     font=("Microsoft YaHei UI", 9)).pack(pady=20)
            return

        def _on_fg_wheel(e):
            self._fg_opts_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        for i, opt in enumerate(options):
            var = tk.BooleanVar(value=False)
            self._fg_options_list.append((opt, var))
            row = tk.Frame(self._fg_opts_inner, bg=CARD)
            row.pack(fill="x", padx=4, pady=1)
            row.bind("<MouseWheel>", _on_fg_wheel)
            cb = tk.Checkbutton(
                row, variable=var, bg=CARD,
                activebackground=CARD,
                command=self._fg_update_count,
                cursor="hand2")
            cb.pack(side="left")
            cb.bind("<MouseWheel>", _on_fg_wheel)
            lbl = tk.Label(row,
                     text=f"{i+1:2d}. {opt}",
                     bg=CARD, fg=TEXT,
                     font=("Microsoft YaHei UI", 9),
                     anchor="w")
            lbl.pack(side="left", fill="x")
            lbl.bind("<MouseWheel>", _on_fg_wheel)

        self._fg_update_count()
        self._set_status("内容方向生成完成，请勾选后点击「开始批量生图」", color=GREEN)

    def _fg_update_count(self):
        n = sum(1 for _, v in self._fg_options_list if v.get())
        self._fg_sel_lbl.config(text=f"已选 {n} 项")
        self._fg_count_lbl.config(
            text=f"将生成 {n}×4 = {n*4} 张图" if n > 0 else "")

    def _fg_start_batch(self):
        selected = [opt for opt, v in self._fg_options_list if v.get()]
        if not selected:
            messagebox.showwarning("自由创作", "请先勾选至少一个内容方向")
            return
        if self.running:
            messagebox.showwarning("自由创作", "当前有任务正在执行，请等待完成")
            return

        ar        = self._fg_ar_var.get()
        version   = self._fg_ver_var.get() or "7"
        _stylize_map = {"标准": 750, "高质量": 900, "极致": 1000}
        stylize = _stylize_map.get(self._fg_stylize_var.get(), 900)
        style_path = self._fg_style_path

        epoch = self._gen_epoch = self._gen_epoch + 1
        self.running   = True
        self._stop_flag = False
        self.btn_free_run.config(state="disabled")
        self.btn_run.config(state="disabled")
        self.btn_auto_run.config(state="disabled")
        self.btn_stop.config(state="normal")

        n = len(selected)
        self._set_status(f"转换 {n} 个方向为 MJ 提示词（约 {n*3}~{n*5} 秒）…", color=TEAL)

        def _worker():
            try:
                tasks = []
                for i, opt in enumerate(selected):
                    if self._stop_flag:
                        break
                    self.after(0, lambda i=i, o=opt: self._set_status(
                        f"[{i+1}/{n}] 转换提示词：{o[:24]}…", color=TEAL))
                    mj_prompt  = call_gemini_option_to_prompt(opt, STYLE_SUFFIX)
                    mj_params  = f" --ar {ar} --v {version} --stylize {stylize} --q 2"
                    full_prompt = mj_prompt.rstrip(", \n") + mj_params

                    if style_path:
                        t = TaskItem("free_blend", prompt=full_prompt,
                                     ref_paths=[style_path],
                                     ar=ar, stylize=stylize, version=version)
                    else:
                        t = TaskItem("txt2img", prompt=full_prompt,
                                     ar=ar, stylize=stylize, version=version)
                    tasks.append(t)

                if tasks:
                    self.after(0, lambda ts=tasks: self._submit_and_run(ts, epoch))
                else:
                    self.after(0, self._reset_run_buttons)
            except Exception as e:
                err = str(e)
                self.after(0, lambda: self._set_status(f"提示词转换失败：{err}", color=RED))
                self.after(0, self._reset_run_buttons)

        threading.Thread(target=_worker, daemon=True).start()

    def _reset_run_buttons(self):
        self.running = False
        self.btn_run.config(state="normal")
        self.btn_auto_run.config(state="normal")
        self.btn_free_run.config(state="normal")
        self.btn_stop.config(state="disabled")

    # ══════════════════════════════════════════════════════════════
    # 底部固定面板
    # ══════════════════════════════════════════════════════════════
    def _build_bottom_panel(self, parent):
        # 顶部分隔线（亮色，视觉分区）
        tk.Frame(parent, bg=ACCENT, height=1).pack(fill="x")

        # 队列区背景
        queue_bg = tk.Frame(parent, bg=CARD)
        queue_bg.pack(fill="x")

        # 队列标题行
        hdr = tk.Frame(queue_bg, bg=CARD)
        hdr.pack(fill="x", padx=16, pady=(8, 3))
        tk.Label(hdr, text="生成队列",
                 bg=CARD, fg=TEXT,
                 font=("Microsoft YaHei UI", 10, "bold")).pack(side="left")
        self._queue_lbl = tk.Label(hdr, text="",
                                    bg=CARD, fg=TEXT_DIM,
                                    font=("Microsoft YaHei UI", 9))
        self._queue_lbl.pack(side="left", padx=10)
        tk.Button(hdr, text="清空",
                  bg=CARD, fg=TEXT_HINT,
                  activebackground=HOVER_BG, activeforeground=RED,
                  relief="flat", font=("Microsoft YaHei UI", 8),
                  command=self._clear_queue).pack(side="right")

        # Treeview
        tv_frame = tk.Frame(queue_bg, bg=CARD,
                             highlightthickness=1,
                             highlightbackground=BORDER)
        tv_frame.pack(fill="x", padx=16, pady=(0, 6))
        cols = ("#", "模式", "提示词摘要", "状态", "耗时", "输出")
        self.tv = ttk.Treeview(tv_frame, columns=cols, show="headings",
                                height=6, style="Dark.Treeview",
                                selectmode="browse")
        widths = [36, 64, 340, 64, 56, 180]
        for c, w in zip(cols, widths):
            self.tv.heading(c, text=c)
            self.tv.column(c, width=w, minwidth=w, anchor="w")
        self.tv.tag_configure("done",    background="#F0FDF4", foreground="#065F46")
        self.tv.tag_configure("failed",  background="#FEF2F2", foreground="#991B1B")
        self.tv.tag_configure("running", background="#EFF6FF", foreground="#1D4ED8")
        sb = ttk.Scrollbar(tv_frame, orient="vertical", command=self.tv.yview,
                            style="Dark.Vertical.TScrollbar")
        self.tv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tv.pack(side="left", fill="x", expand=True)
        self.tv.bind("<Double-1>", self._tv_double_click)

        # 按钮行
        btn_row = tk.Frame(queue_bg, bg=CARD)
        btn_row.pack(fill="x", padx=16, pady=(4, 6))

        self.btn_run = tk.Button(
            btn_row, text="▶  开始生成",
            bg=ACCENT, fg="white",
            activebackground=ACCENT_H, activeforeground="white",
            relief="flat", padx=20, pady=6,
            font=("Microsoft YaHei UI", 10, "bold"),
            cursor="hand2",
            command=self._start_generation)
        self.btn_run.pack(side="left")

        self.btn_stop = tk.Button(
            btn_row, text="■  停止",
            bg=CARD2, fg=TEXT_DIM,
            activebackground=HOVER_BG, activeforeground=RED,
            relief="flat", padx=14, pady=6,
            font=("Microsoft YaHei UI", 10),
            state="disabled",
            cursor="hand2",
            command=self._stop_generation)
        self.btn_stop.pack(side="left", padx=8)

        tk.Button(btn_row, text="打开输出文件夹",
                  bg=CARD2, fg=TEXT_DIM,
                  activebackground=HOVER_BG, activeforeground=TEXT,
                  relief="flat", padx=12, pady=6,
                  font=("Microsoft YaHei UI", 9),
                  cursor="hand2",
                  command=self._open_output).pack(side="left", padx=(0, 6))

        tk.Button(btn_row, text="总览报告",
                  bg=CARD2, fg=BLUE,
                  activebackground=HOVER_BG, activeforeground=BLUE,
                  relief="flat", padx=12, pady=6,
                  font=("Microsoft YaHei UI", 9),
                  cursor="hand2",
                  command=self._open_master_report).pack(side="left")

        # 并发设置（右侧）
        tk.Label(btn_row, text="并发路数", bg=CARD, fg=TEXT_DIM,
                 font=("Microsoft YaHei UI", 9)).pack(side="right", padx=(0,4))
        self.concur_var = tk.StringVar(value="3")
        tk.Spinbox(btn_row, textvariable=self.concur_var, from_=1, to=8,
                   width=3, bg=CARD2, fg=TEXT,
                   buttonbackground=CARD2,
                   relief="flat", highlightthickness=1,
                   highlightbackground=BORDER,
                   font=("Microsoft YaHei UI", 9)
                   ).pack(side="right", padx=(0, 4))

        # 进度条区
        pb_frame = tk.Frame(queue_bg, bg=CARD)
        pb_frame.pack(fill="x", padx=16, pady=(0, 8))
        self.progress_bar = RoundBar(pb_frame, height=6)
        self.progress_bar.pack(fill="x", pady=(0, 4))
        self.status_var = tk.StringVar(value="就绪")
        self._status_lbl = tk.Label(pb_frame, textvariable=self.status_var,
                                     bg=CARD, fg=TEXT_HINT,
                                     font=("Consolas", 8))
        self._status_lbl.pack(anchor="w")

    # ══════════════════════════════════════════════════════════════
    # 辅助 UI 构建
    # ══════════════════════════════════════════════════════════════
    def _card(self, parent, title="", accent=None):
        """暗色卡片：顶部彩色线 + 标题（向下兼容，返回 frame 本身）"""
        bar_color = accent or ACCENT
        frame = tk.Frame(parent, bg=CARD,
                         highlightthickness=1,
                         highlightbackground=BORDER)
        # 顶部彩色装饰线
        tk.Frame(frame, bg=bar_color, height=2).pack(fill="x")
        if title:
            tk.Label(frame, text=title,
                     bg=CARD, fg=TEXT_DIM,
                     font=("Microsoft YaHei UI", 9, "bold"),
                     anchor="w").pack(fill="x", padx=12, pady=(7, 2))
        return frame

    # ── 图生图三层槽位操作 ────────────────────────────────────────

    def _pick_single(self, title="选择图片") -> str:
        """弹出单图选择框，返回路径或空串"""
        paths = filedialog.askopenfilenames(
            title=title,
            filetypes=[("图片", "*.png *.jpg *.jpeg *.webp *.bmp")])
        return paths[0] if paths else ""

    def _render_single_slot(self, thumb_lbl, name_lbl, status_lbl, path):
        """刷新单张槽位缩略图 & 状态标签"""
        if path:
            try:
                ph = load_thumbnail(path, (80, 80))
                thumb_lbl.config(image=ph); thumb_lbl._ph = ph
            except Exception:
                thumb_lbl.config(image=""); thumb_lbl._ph = None
            name_lbl.config(text=Path(path).name[:24])
            status_lbl.config(text="✓ 已选择", fg=GREEN)
        else:
            thumb_lbl.config(image=""); thumb_lbl._ph = None
            name_lbl.config(text="")
            status_lbl.config(text="未选择", fg=TEXT_HINT)

    # ── ① 风格图 ─────────────────────────────────────────────────
    def _pick_style(self):
        p = self._pick_single("选择风格图（定义视觉风格 / 光影 / 色调）")
        if p:
            self._style_path = p
            self._render_single_slot(
                self._style_thumb_lbl, self._style_thumb_lbl_name,
                self._style_status_lbl, p)

    def _clear_style(self):
        self._style_path = ""
        self._render_single_slot(
            self._style_thumb_lbl, self._style_thumb_lbl_name,
            self._style_status_lbl, "")

    # ── ② 主体控制图 ─────────────────────────────────────────────
    def _pick_subject(self):
        p = self._pick_single("选择主体控制图（定义核心主体结构 / 形态 / 材质）")
        if p:
            self._subject_path = p
            self._render_single_slot(
                self._subject_thumb_lbl, self._subject_thumb_lbl_name,
                self._subject_status_lbl, p)

    def _clear_subject(self):
        self._subject_path = ""
        self._render_single_slot(
            self._subject_thumb_lbl, self._subject_thumb_lbl_name,
            self._subject_status_lbl, "")

    # ── ③ 内容主题图 ─────────────────────────────────────────────
    def _add_themes(self):
        if len(self._theme_paths) >= 2:
            messagebox.showinfo("提示", "内容主题图最多 2 张"); return
        paths = filedialog.askopenfilenames(
            title="选择内容主题图（可选，最多 2 张）",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.webp *.bmp")])
        if not paths: return
        for p in paths:
            if p not in self._theme_paths and len(self._theme_paths) < 2:
                self._theme_paths.append(p)
        self._refresh_theme_strip()

    def _clear_themes(self):
        self._theme_paths.clear(); self._theme_thumbs.clear()
        self._refresh_theme_strip()

    def _remove_theme(self, idx):
        if 0 <= idx < len(self._theme_paths):
            self._theme_paths.pop(idx)
        self._refresh_theme_strip()

    def _refresh_theme_strip(self):
        for w in self._theme_strip.winfo_children():
            w.destroy()
        self._theme_thumbs.clear()
        for i, p in enumerate(self._theme_paths):
            try:
                ph = load_thumbnail(p, (80, 80))
            except Exception:
                ph = None
            self._theme_thumbs.append(ph)
            cell = tk.Frame(self._theme_strip, bg=CARD)
            cell.pack(side="left", padx=4, pady=4)
            if ph:
                tk.Label(cell, image=ph, bg=CARD).pack()
            tk.Label(cell, text=Path(p).name[:12],
                     bg=CARD, fg=TEXT_DIM,
                     font=("Microsoft YaHei UI", 7),
                     width=12, anchor="center").pack()
            idx = i
            tk.Button(cell, text="×", bg=CARD, fg=RED,
                      font=("Microsoft YaHei UI", 8, "bold"),
                      relief="flat", padx=2,
                      command=lambda i=idx: self._remove_theme(i)).pack()
        n = len(self._theme_paths)
        self._theme_count_lbl.config(
            text=f"已选 {n} 张",
            fg=(TEXT_DIM if n == 0 else GREEN))



    # ── 文生图：从预设填充提示词 ─────────────────────────────────
    def _fill_prompt_from_presets(self):
        try:
            stylize = int(self.t2i_stylize_var.get())
        except ValueError:
            stylize = 850
        ar      = self.t2i_ar_var.get()
        version = self.t2i_ver_var.get()
        prompt  = build_imagine_prompt(
            structure = self.struct_var.get(),
            lighting  = self.light_var.get(),
            mood      = self.mood_var.get(),
            extra     = "",
            ar        = ar,
            stylize   = stylize,
            version   = version)
        self.prompt_txt.delete("1.0", "end")
        self.prompt_txt.insert("1.0", prompt)

    # ══════════════════════════════════════════════════════════════
    # 队列管理
    # ══════════════════════════════════════════════════════════════
    def _rebuild_tv(self):
        self.tv.delete(*self.tv.get_children())
        for i, t in enumerate(self.tasks):
            mode_lbl = "文生图" if t.mode == "txt2img" else "图生图"
            prompt_s = (t.prompt or " | ".join(
                            Path(p).name[:8] for p in t.ref_paths))[:48]
            status_map = {"pending":"等待","running":"⚡生成中",
                          "done":"✓ 完成","failed":"✗ 失败","stopped":"■ 停止"}
            st = status_map.get(t.status, t.status)
            elapsed = f"{t.elapsed:.0f}s" if t.elapsed else ""
            out  = Path(t.output_path).name if t.output_path else ""
            tags = ({"done":"done","failed":"failed","running":"running"}.get(t.status,""),)
            self.tv.insert("", "end", iid=str(i),
                           values=(i+1, mode_lbl, prompt_s, st, elapsed, out),
                           tags=tags)
        total = len(self.tasks)
        done  = sum(1 for t in self.tasks if t.status=="done")
        self._queue_lbl.config(
            text=f"共 {total} 张 | 完成 {done}" if total else "")

    def _clear_queue(self):
        if self.running:
            messagebox.showwarning("提示","生成中，请先停止"); return
        self.tasks.clear(); self._rebuild_tv()

    def _tv_double_click(self, event):
        sel = self.tv.selection()
        if not sel: return
        idx = int(sel[0])
        t   = self.tasks[idx]
        if t.status == "done" and t.output_path and Path(t.output_path).exists():
            os.startfile(t.output_path)
        elif t.status == "failed" and t.error:
            messagebox.showerror(f"任务 #{idx+1} 失败", t.error)

    # ══════════════════════════════════════════════════════════════
    # 生成逻辑
    # ══════════════════════════════════════════════════════════════
    def _start_generation(self):
        if self.running:
            messagebox.showinfo("提示","已在生成中"); return

        # 收集本次新任务（仅收当前激活 Tab 的任务，避免跨 Tab 误触发）
        new_tasks: list[TaskItem] = []
        active_tab = self.nb.index(self.nb.select())  # 0=文生图, 1=图生图

        if active_tab == 0:
            # ── 文生图任务 ────────────────────────────────────────────
            prompt = self.prompt_txt.get("1.0","end").strip()
            if not prompt:
                messagebox.showwarning("提示","请先填写提示词"); return
            try: stylize = int(self.t2i_stylize_var.get())
            except ValueError: stylize = 850
            n = max(1, int(self.t2i_n_var.get() or 1))
            for _ in range(n):
                new_tasks.append(TaskItem(
                    "txt2img", prompt=prompt,
                    ar=self.t2i_ar_var.get(),
                    stylize=stylize,
                    version=self.t2i_ver_var.get()))

        else:
            # ── 图生图任务（三层）────────────────────────────────────
            if not self._style_path or not self._subject_path:
                messagebox.showwarning(
                    "图生图",
                    "请先选择「① 风格图」和「② 主体控制图」（均为必选）")
                return
            # 按层序组合 ref_paths：风格图 → 主体图 → 主题图（若有）
            ref_paths = [self._style_path, self._subject_path]
            ref_paths.extend(self._theme_paths)
            extra = self.i2i_extra_txt.get("1.0", "end").strip()
            n = max(1, int(self.i2i_n_var.get() or 1))
            try: i2i_stylize = int(self.i2i_stylize_var.get())
            except ValueError: i2i_stylize = 900
            for _ in range(n):
                new_tasks.append(TaskItem(
                    "img2img",
                    ref_paths=ref_paths,
                    ar=self.i2i_ar_var.get(),
                    stylize=i2i_stylize,
                    version=self.i2i_ver_var.get(),
                    extra_prompt=extra))

        if not new_tasks:
            messagebox.showwarning("提示","没有可提交的任务"); return

        self.tasks.extend(new_tasks)
        self._rebuild_tv()

        self.running    = True
        self._stop_flag = False
        self._gen_epoch += 1
        self.btn_run.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.progress_bar["value"] = 0
        self.progress_bar["maximum"] = 100

        threading.Thread(target=self._run_batch,
                         args=(new_tasks, self._gen_epoch),
                         daemon=True).start()

    def _stop_generation(self):
        self._stop_flag = True
        self._set_status("正在停止…", color=AMBER)

    def _run_batch(self, tasks: list[TaskItem], epoch: int):
        batch_ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        for t in tasks: t.batch_ts = batch_ts

        try:
            concur = max(1, int(self.concur_var.get() or 3))
        except ValueError:
            concur = 3

        total  = len(tasks)
        done_n = 0
        lock   = threading.Lock()

        def _run_one(t: TaskItem):
            nonlocal done_n
            if self._stop_flag:
                t.status = "stopped"; self._ui_update_row(t); return
            t.status = "running"; self._ui_update_row(t)
            t0 = time.time()
            try:
                out_path = self._execute_task(t, batch_ts)
                t.output_path = out_path
                t.status      = "done"
            except StoppedByUser:
                t.status = "stopped"
            except Exception as e:
                t.status = "failed"; t.error = str(e)
            finally:
                t.elapsed = time.time() - t0
                with lock: done_n += 1
                self._ui_update_row(t)
                pct = done_n / total * 100
                self.after(0, lambda p=pct, d=done_n:
                           self._update_progress(p, d, total, concur))

        self.after(0, lambda: self._set_status(
            f"生成中… 共 {total} 张，{concur} 路并发", color=ACCENT))

        with concurrent.futures.ThreadPoolExecutor(max_workers=concur) as ex:
            futs = [ex.submit(_run_one, t) for t in tasks]
            concurrent.futures.wait(futs)

        if epoch != self._gen_epoch: return  # 被新的 epoch 替代
        self.after(0, self._on_batch_done, tasks, batch_ts)

    def _execute_task(self, t: TaskItem, batch_ts: str) -> str:
        """执行单个任务，返回保存的文件路径"""
        def pcb(msg): self.after(0, lambda m=msg: self._set_status(m))

        today   = datetime.datetime.now().strftime("%Y-%m-%d")
        out_dir = _app_dir() / "output" / today
        out_dir.mkdir(parents=True, exist_ok=True)

        size = ASPECT_MAP.get(t.ar, "1024x1024")

        gemini_prompt = ""   # 记录 Gemini 生成的原始 prompt（img2img 专用）

        if t.mode == "txt2img":
            # ── 文生图：Image-MI，一次返回 4 张 ─────────────────
            # 用 t.ar 强制覆盖 prompt 中的 --ar（防止快速填充后切换比例出现错值）
            import re as _re
            _prompt = t.prompt.rstrip()
            if "--ar" in _prompt:
                _prompt = _re.sub(r'--ar\s+\S+', f'--ar {t.ar}', _prompt)
            else:
                _prompt += f" --ar {t.ar} --v {t.version or '7'} --stylize {t.stylize or 850} --q 2"
            all_bytes = call_imagine(prompt=_prompt, size=size, progress_cb=pcb)

        elif t.mode == "img2img":
            # ── 图生图 Step 1/2：Gemini 三层反推提示词 ───────────
            pcb("Step 1/2: Gemini 三层分析参考图，生成提示词（约 15~30 秒）…")
            gemini_prompt = call_gemini_analyze_refs(
                t.ref_paths,
                use_layers_prompt=True,
                progress_cb=pcb)

            # 拼接用户追加提示词
            user_extra = (t.extra_prompt or "").strip()
            mj_params  = f" --ar {t.ar} --v {t.version or '7'} --stylize {t.stylize or 900} --q 2"
            if user_extra:
                final_prompt = (gemini_prompt.rstrip(", \n")
                                + mj_params + "\n" + user_extra)
            else:
                final_prompt = gemini_prompt.rstrip(", \n") + mj_params

            t.prompt = final_prompt  # 写回任务，供队列/报告显示

            # ── 图生图 Step 2/2：Image-MI（提示词 + 参考图 base64Array）
            valid_paths = [p for p in t.ref_paths if p and Path(p).exists()]
            if valid_paths:
                pcb(f"Step 2/2: Image-MI 传入 {len(valid_paths)} 张参考图 + 提示词生成（约 45 秒）…")
                # 主体图优先：将 ref_paths[1]（主体控制图）调至首位，
                # 使 Image-MI 对主体形态的视觉权重高于风格图
                if len(valid_paths) >= 2:
                    mi_paths = [valid_paths[1], valid_paths[0]] + valid_paths[2:]
                else:
                    mi_paths = valid_paths
                data_uris = [img_to_data_uri_blend(p) for p in mi_paths]
            else:
                pcb("Step 2/2: Image-MI 纯提示词生成（约 45 秒）…")
                data_uris = []
            all_bytes = call_blend(
                data_uris=data_uris,
                extra_prompt=final_prompt,
                size=size,
                progress_cb=pcb)

        elif t.mode == "free_blend":
            # 自由生图：提示词已预生成，可选风格参考图融合
            valid_paths = [p for p in t.ref_paths if p and Path(p).exists()]
            if valid_paths:
                pcb(f"Image-MI 风格融合生成中（{len(valid_paths)} 张参考图，约 45 秒）…")
                data_uris = [img_to_data_uri_blend(p) for p in valid_paths]
                all_bytes = call_blend(
                    data_uris=data_uris,
                    extra_prompt=t.prompt,
                    size=size,
                    progress_cb=pcb)
            else:
                pcb("Image-MI 文生图生成中（约 45 秒）…")
                all_bytes = call_imagine(prompt=t.prompt, size=size, progress_cb=pcb)

        # 保存全部图片（Image-MI 一次 4 张）
        _suffix_map = {"txt2img": "txt2img", "img2img": "img2img", "free_blend": "free"}
        suffix    = _suffix_map.get(t.mode, t.mode)
        ts_ms     = int(time.time() * 1000) % 100000
        saved     = []
        for i, img_bytes in enumerate(all_bytes):
            fname    = f"{batch_ts}_{suffix}_{ts_ms:05d}_{i+1}of{len(all_bytes)}_result.png"
            out_path = out_dir / fname
            out_path.write_bytes(img_bytes)
            saved.append(str(out_path))

        t.output_paths = saved  # 全部 4 张路径，供报告使用

        # meta.json（记录所有输出路径）
        first_out = saved[0] if saved else ""
        meta = {
            "timestamp":     batch_ts,
            "mode":          t.mode,
            "model":         MODEL_IMAGINE,
            "images_count":  len(all_bytes),
            "prompt":        t.prompt,
            "gemini_prompt": gemini_prompt,   # Gemini 原始输出（img2img）
            "extra_prompt":  t.extra_prompt,  # 用户追加内容
            "ref_paths":     t.ref_paths,
            "ar":            t.ar,
            "stylize":       t.stylize,
            "version":       t.version,
            "outputs":       saved,
        }
        meta_fname = f"{batch_ts}_{suffix}_{ts_ms:05d}_meta.json"
        (out_dir / meta_fname).write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        return first_out  # 队列显示第一张路径

    def _update_progress(self, pct, done, total, concur):
        self.progress_bar["value"] = pct
        self._set_status(
            f"生成中… {done}/{total} 张完成  {concur} 路并发",
            color=ACCENT)

    def _ui_update_row(self, t: TaskItem):
        idx = self.tasks.index(t) if t in self.tasks else -1
        if idx < 0: return
        self.after(0, lambda: self._refresh_one_row(idx, t))

    def _refresh_one_row(self, idx, t: TaskItem):
        iid = str(idx)
        if not self.tv.exists(iid): return
        _mode_names = {"txt2img": "文生图", "img2img": "图生图", "free_blend": "自由生图"}
        mode_lbl = _mode_names.get(t.mode, t.mode)
        prompt_s = (t.prompt or " | ".join(
                        Path(p).name[:8] for p in t.ref_paths))[:48]
        status_map = {"pending":"等待","running":"⚡生成中",
                      "done":"✓ 完成","failed":"✗ 失败","stopped":"■ 停止"}
        st      = status_map.get(t.status, t.status)
        elapsed = f"{t.elapsed:.0f}s" if t.elapsed else ""
        out     = Path(t.output_path).name if t.output_path else ""
        tags    = ({"done":"done","failed":"failed","running":"running"}.get(t.status,""),)
        self.tv.item(iid, values=(idx+1, mode_lbl, prompt_s, st, elapsed, out), tags=tags)
        # 更新队列标题
        done_n = sum(1 for x in self.tasks if x.status=="done")
        self._queue_lbl.config(text=f"共 {len(self.tasks)} 张 | 完成 {done_n}")

    # ══════════════════════════════════════════════════════════════
    # 批次完成
    # ══════════════════════════════════════════════════════════════
    def _on_batch_done(self, tasks, batch_ts):
        self.running = False
        self.btn_run.config(state="normal")
        self.btn_auto_run.config(state="normal")
        self.btn_free_run.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.progress_bar["value"] = 100

        done   = [t for t in tasks if t.status=="done"]
        failed = [t for t in tasks if t.status=="failed"]
        self._set_status(
            f"批次完成 ✓  {len(done)} 成功 / {len(failed)} 失败",
            color=(GREEN if not failed else AMBER))

        if done:
            self._generate_batch_report(tasks, batch_ts)

        if failed:
            errs = "\n".join(f"#{self.tasks.index(t)+1}: {t.error}" for t in failed[:5])
            messagebox.showwarning("部分任务失败",
                                   f"{len(failed)} 个任务失败：\n\n{errs}")

    # ══════════════════════════════════════════════════════════════
    # HTML 报告（完全复刻 v2.3 风格）
    # ══════════════════════════════════════════════════════════════

    def _generate_batch_report(self, all_tasks: list, batch_ts: str):
        """生成批次对比 HTML 报告，返回报告文件路径。"""
        today   = datetime.datetime.now().strftime("%Y-%m-%d")
        out_dir = _app_dir() / "output" / today
        out_dir.mkdir(parents=True, exist_ok=True)

        total_elapsed = sum(t.elapsed for t in all_tasks if t.elapsed > 0)
        done_tasks    = [t for t in all_tasks if t.status == "done"]
        fail_tasks    = [t for t in all_tasks if t.status == "failed"]

        def _b64(path, size):
            if not path or not Path(path).is_file(): return ""
            try:
                img = Image.open(path); img.thumbnail(size, Image.LANCZOS)
                if img.mode not in ("RGB","L"): img = img.convert("RGB")
                buf = io.BytesIO(); img.save(buf, format="JPEG", quality=82)
                return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
            except Exception: return ""

        def _ref_img(path, lbl):
            if not path:
                return '<div class="ref-wrap"><div class="ref-ph">?</div><div class="ref-lbl">%s</div></div>' % lbl
            sm = _b64(path, (200,200)); lg = _b64(path, (600,600)); fname = Path(path).name
            if sm:
                return ('<div class="ref-wrap"><img class="ref-thumb" src="%s" data-full="%s" '
                        'title="%s" onclick="openFloat(this.dataset.full,this.title,this)">'
                        '<div class="ref-lbl">%s</div></div>' % (sm, lg or sm, fname, lbl))
            return '<div class="ref-wrap"><div class="ref-ph">?</div><div class="ref-lbl">%s</div></div>' % lbl

        cards_html = []
        for i, t in enumerate(all_tasks):
            if t.status == "pending": continue
            sc  = t.status
            cls = {"done":"ok","failed":"ng"}.get(sc,"sk")
            bn  = {"done":"✓ 完成","failed":"✗ 失败","stopped":"— 停止"}.get(sc,sc)
            et  = ("%.0fs" % t.elapsed) if t.elapsed > 0 else ""

            # 三层参考图（ref_paths：[风格, 主体, 主题1, 主题2]）
            rp = t.ref_paths
            if t.mode == "img2img" and rp:
                inp = (_ref_img(rp[0] if len(rp)>0 else "", "①风格")
                     + _ref_img(rp[1] if len(rp)>1 else "", "②主体")
                     + (_ref_img(rp[2], "③主题") if len(rp)>2 else "")
                     + (_ref_img(rp[3], "③主题2") if len(rp)>3 else ""))
                tn = Path(rp[-1]).name if rp else ""
            else:
                inp = ""; tn = "文生图"

            mode_lbl = "文生图" if t.mode=="txt2img" else "图生图"
            mode_cls = "badge-txt" if t.mode=="txt2img" else "badge-img"

            # 结果图（相对路径）
            def _rel(p):
                try: return os.path.relpath(str(p), str(out_dir)).replace("\\","/")
                except: return Path(p).name

            out_html = ""
            op = t.output_path or ""
            pname = Path(op).name if op else ""
            if sc == "done":
                all_ops = t.output_paths if t.output_paths else ([op] if op else [])
                imgs = []
                for op_path in all_ops:
                    if not op_path or not Path(op_path).is_file(): continue
                    rp = _rel(op_path)
                    if rp:
                        imgs.append('<img class="ri" src="%s" data-full="%s" data-isresult="1" '
                                    'title="%s" onclick="openFloat(this.dataset.full,this.title,this)" loading="lazy">'
                                    % (rp, rp, Path(op_path).name))
                if imgs:
                    out_html = '<div class="out-grid">%s</div>' % "".join(imgs)
            elif sc == "failed":
                err = (t.error or "").replace("&","&amp;").replace("<","&lt;")
                out_html = '<div class="eb">%s</div>' % err

            pr  = (t.prompt or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
            pd  = ('<details class="pd"><summary>Prompt</summary><pre class="pt">%s</pre></details>' % pr) if pr else ""
            ep_txt = (t.extra_prompt or "").strip().replace("&","&amp;").replace("<","&lt;")
            ep  = ('<div class="ep"><span class="ep-lbl">④ 自定义提示：</span>%s</div>' % ep_txt) if ep_txt else ""
            fav = ('<div class="verdict-btns">'
                   '<button class="vbtn pass" onclick="markVerdict(this,\'pass\')">&#10003; 通过</button>'
                   '<button class="vbtn fail" onclick="markVerdict(this,\'fail\')">&#10007; 未通过</button>'
                   '</div>') if sc=="done" else ""
            dk  = ('data-key="%s"' % pname) if sc=="done" else ""

            cards_html.append(
                '<div class="card {c}" {dk}>'
                '<div class="ch" onclick="togCard2(this)" style="cursor:pointer">'
                '<span class="cn">#{n}</span>'
                '<span class="{mc}">{ml}</span>'
                '<span class="cbadge {c}">{b}</span><span class="et">{e}</span>'
                '<span class="tn">{tn}</span><span class="tog2">&#x25BC;</span></div>'
                '<div class="cb"><div class="inputs">{inp}</div>'
                '{sep}<div class="out">{out}{fav}</div></div>{ep}{pd}</div>'.format(
                    c=cls,dk=dk,n=i+1,mc=mode_cls,ml=mode_lbl,b=bn,e=et,tn=tn,
                    inp=inp,sep='<div class="sep"></div>' if inp else "",
                    out=out_html,fav=fav,ep=ep,pd=pd))

        m,s = divmod(int(total_elapsed),60)
        elapsed_str = "%d分%d秒"%(m,s) if m else "%ds"%s

        CSS = _REPORT_CSS
        JS  = _REPORT_JS

        html = ("<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
                "<title>MJ生图报告 %s</title><style>%s</style></head><body>"
                "<header><h1>批量生图对比报告</h1>"
                "<div class='meta-row'><span>批次：%s</span><span>模型：Image-MI</span>"
                "<span>总用时：%s</span></div>"
                "<div class='stats-row'>"
                "<span class='st done'>✓ 完成 %d</span>"
                "<span class='st fail'>✗ 失败 %d</span>"
                "<span class='st total'>共 %d 组</span>"
                "<span class='fav-count' id='favCount'>&#10003; 0 张已通过</span>"
                "<button class='exp-btn' onclick='exportFavs()'>&#128229; 导出通过记录</button>"
                "</div></header>"
                "<div class='grid'>%s</div>"
                "<script>%s</script></body></html>") % (
            batch_ts, CSS, batch_ts, elapsed_str,
            len(done_tasks), len(fail_tasks), len(all_tasks),
            "\n".join(cards_html), JS)

        report_path = out_dir / ("report_%s.html" % batch_ts)
        report_path.write_text(html, encoding="utf-8")

        # 更新总览
        try:
            self._update_master_report(batch_ts, all_tasks, out_dir)
        except Exception as e:
            import traceback; traceback.print_exc()
        return str(report_path)

    def _update_master_report(self, batch_ts: str, tasks: list, out_dir: Path):
        """写入批次历史 JSON，重建 总览HTML/report_总览.html"""
        master_dir  = _app_dir() / "总览HTML"
        master_dir.mkdir(exist_ok=True)
        hist_path   = master_dir / "_batch_history.json"

        history = []
        if hist_path.exists():
            try: history = json.loads(hist_path.read_text(encoding="utf-8"))
            except Exception: pass

        def _rpath(p):
            try: return os.path.relpath(str(p), str(master_dir)).replace("\\","/")
            except: return Path(p).name

        new_batch = {
            "batch_ts":    batch_ts,
            "theme":       _THEME_NAME,
            "done":        sum(1 for t in tasks if t.status=="done"),
            "failed":      sum(1 for t in tasks if t.status=="failed"),
            "elapsed_s":   round(sum(t.elapsed for t in tasks if t.elapsed>0), 1),
            "report_file": _rpath(out_dir / ("report_%s.html" % batch_ts)),
            "tasks": [
                {"n": i+1, "status": t.status,
                 "mode": t.mode,
                 "style_path":   _rpath(t.ref_paths[0]) if len(t.ref_paths)>0 else "",
                 "char_path":    _rpath(t.ref_paths[1]) if len(t.ref_paths)>1 else "",
                 "theme_path":   _rpath(t.ref_paths[2]) if len(t.ref_paths)>2 else "",
                 "theme_path2":  _rpath(t.ref_paths[3]) if len(t.ref_paths)>3 else "",
                 "output_path":  _rpath(t.output_path) if t.output_path else "",
                 "output_paths": [_rpath(p) for p in (t.output_paths or []) if p],
                 "elapsed_s":    round(t.elapsed, 1),
                 "prompt":       t.prompt or "",
                 "extra_prompt": t.extra_prompt or "",
                 "error":        t.error or ""}
                for i, t in enumerate(tasks) if t.status != "pending"
            ],
        }
        history.insert(0, new_batch)
        hist_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
        master_html = self._render_master_html(history, master_dir)
        (master_dir / "report_总览.html").write_text(master_html, encoding="utf-8")

    def _render_master_html(self, history: list, master_dir: Path) -> str:
        """从历史 JSON 渲染累计总览 HTML（完全复刻 v2.3）"""
        total_batches = len(history)
        total_done    = sum(b["done"]   for b in history)
        total_failed  = sum(b.get("failed",0) for b in history)

        def _resolve(p):
            if not p: return None
            pp = Path(p)
            return pp if pp.is_absolute() else master_dir / p

        def _b64(path, size):
            abs_p = _resolve(path)
            if not abs_p or not abs_p.is_file(): return ""
            try:
                img = Image.open(abs_p); img.thumbnail(size, Image.LANCZOS)
                if img.mode not in ("RGB","L"): img = img.convert("RGB")
                buf = io.BytesIO(); img.save(buf, format="JPEG", quality=82)
                return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
            except Exception: return ""

        def _ref_img(path, lbl):
            if not path:
                return '<div class="ref-wrap"><div class="ref-ph">?</div><div class="ref-lbl">%s</div></div>' % lbl
            abs_p = _resolve(path)
            sm = _b64(path,(200,200)); lg = _b64(path,(600,600))
            fname = abs_p.name if abs_p else Path(path).name
            if sm:
                return ('<div class="ref-wrap"><img class="ref-thumb" src="%s" data-full="%s" '
                        'title="%s" onclick="openFloat(this.dataset.full,this.title,this)">'
                        '<div class="ref-lbl">%s</div></div>' % (sm,lg or sm,fname,lbl))
            return '<div class="ref-wrap"><div class="ref-ph">?</div><div class="ref-lbl">%s</div></div>' % lbl

        def _card(t):
            sc  = t["status"]; cls = {"done":"ok","failed":"ng"}.get(sc,"sk")
            bn  = {"done":"✓ 完成","failed":"✗ 失败","stopped":"— 停止"}.get(sc,sc)
            et  = ("%.0fs"%t["elapsed_s"]) if t.get("elapsed_s",0)>0 else ""
            mode = t.get("mode","img2img")
            mode_lbl = "文生图" if mode=="txt2img" else "图生图"
            mode_cls = "badge-txt" if mode=="txt2img" else "badge-img"

            inp = ""
            if mode == "img2img":
                inp = (_ref_img(t.get("style_path",""),"①风格")
                     + _ref_img(t.get("char_path",""),"②主体")
                     + (_ref_img(t.get("theme_path",""),"③主题") if t.get("theme_path") else "")
                     + (_ref_img(t.get("theme_path2",""),"③主题2") if t.get("theme_path2") else ""))
            tn = (Path(t.get("theme_path","")).name if t.get("theme_path")
                  else ("文生图" if mode=="txt2img" else "(无主题)"))

            def _abs_path(p):
                if not p: return None
                pp = Path(p)
                return pp if pp.is_absolute() else master_dir / p
            def _href(p):
                abs_p = _abs_path(p)
                if not abs_p or not abs_p.is_file(): return ""
                try: return os.path.relpath(str(abs_p), str(master_dir)).replace("\\","/")
                except: return abs_p.name

            out_html = ""; op = t.get("output_path",""); pname = Path(op).name if op else ""
            if sc=="done":
                all_ops = t.get("output_paths", []) or ([op] if op else [])
                imgs = []
                for op_path in all_ops:
                    rp = _href(op_path)
                    if rp:
                        imgs.append('<img class="ri" src="%s" data-full="%s" data-isresult="1" '
                                    'title="%s" onclick="openFloat(this.dataset.full,this.title,this)" loading="lazy">'
                                    % (rp, rp, Path(op_path).name))
                if imgs:
                    out_html = '<div class="out-grid">%s</div>' % "".join(imgs)
            elif sc=="failed":
                err=(t.get("error") or "").replace("&","&amp;").replace("<","&lt;")
                out_html='<div class="eb">%s</div>'%err
            pr=(t.get("prompt") or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
            pd=('<details class="pd"><summary>Prompt</summary><pre class="pt">%s</pre></details>'%pr) if pr else ""
            ep_txt=(t.get("extra_prompt") or "").strip().replace("&","&amp;").replace("<","&lt;")
            ep=('<div class="ep"><span class="ep-lbl">④ 自定义提示：</span>%s</div>'%ep_txt) if ep_txt else ""
            fav=('<div class="verdict-btns">'
                 '<button class="vbtn pass" onclick="markVerdict(this,\'pass\')">&#10003; 通过</button>'
                 '<button class="vbtn fail" onclick="markVerdict(this,\'fail\')">&#10007; 未通过</button>'
                 '</div>') if sc=="done" else ""
            dk=('data-key="%s"'%pname) if sc=="done" else ""
            return ('<div class="card {c}" {dk}>'
                    '<div class="ch" onclick="togCard2(this)" style="cursor:pointer">'
                    '<span class="cn">#{n}</span><span class="{mc}">{ml}</span>'
                    '<span class="cbadge {c}">{b}</span><span class="et">{e}</span>'
                    '<span class="tn">{tn}</span><span class="tog2">&#x25BC;</span></div>'
                    '<div class="cb"><div class="inputs">{inp}</div>'
                    '{sep}<div class="out">{out}{fav}</div></div>{ep}{pd}</div>').format(
                c=cls,dk=dk,n=t["n"],mc=mode_cls,ml=mode_lbl,b=bn,e=et,tn=tn,
                inp=inp,sep='<div class="sep"></div>' if inp else "",
                out=out_html,fav=fav,ep=ep,pd=pd)

        batch_sections = []
        for bi, batch in enumerate(history):
            m,s = divmod(int(batch.get("elapsed_s",0)),60)
            et_s = ("%d分%d秒"%(m,s)) if m else ("%ds"%s if s else "")
            cards = "\n".join(_card(t) for t in batch.get("tasks",[]))
            is_new = (bi==0)
            nb  = '<span class="bnew">最新</span>' if is_new else ""
            theme_name = batch.get("theme", "")
            th  = ('<span class="btheme">%s</span>' % theme_name) if theme_name else ""
            dt  = ('<span class="tag done">✓ %d张</span>'%batch["done"]) if batch.get("done") else ""
            ft  = ('<span class="tag fail">✗ %d失败</span>'%batch["failed"]) if batch.get("failed") else ""
            rf  = batch.get("report_file","")
            lk  = ('<a class="blink" href="%s" target="_blank">单独报告</a>'%rf) if rf else ""
            et_tag = ('<span class="tag">%s</span>'%et_s) if et_s else ""
            batch_sections.append(
                '<details class="batch" {op}><summary class="bsum">'
                '<span class="btitle">{ts}</span>{nb}{th}'
                '<div class="bmeta">{et}{dt}{ft}{lk}</div>'
                '</summary><div class="bcards">{cards}</div></details>'.format(
                    op="open" if is_new else "",
                    ts=batch["batch_ts"].replace("_"," "),
                    nb=nb,th=th,et=et_tag,dt=dt,ft=ft,lk=lk,cards=cards))

        fail_tag = ('<span class="st fail">失败 %d 张</span>'%total_failed) if total_failed else ""
        return ("<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
                "<title>生图总览报告</title><style>%s</style></head><body>"
                "<header><h1>&#128202; 生图批次总览</h1><div class='hstats'>"
                "<span class='st total'>共 %d 批次</span>"
                "<span class='st done'>累计完成 %d 张</span>%s"
                "<span class='fav-count' id='favCount'>&#10003; 0 张已通过</span>"
                "<button class='exp-btn' onclick='exportFavs()'>&#128229; 导出通过记录</button>"
                "<span class='fav-hint'>效果满意就点「✓ 通过」</span>"
                "</div></header>"
                "<div class='batches'>%s</div>"
                "<script>%s</script></body></html>") % (
            _REPORT_CSS, total_batches, total_done, fail_tag,
            "\n".join(batch_sections), _REPORT_JS)

    # ── 打开输出 ──────────────────────────────────────────────────
    def _open_output(self):
        d = _app_dir() / "output"
        d.mkdir(exist_ok=True)
        os.startfile(str(d))

    def _open_master_report(self):
        p = _app_dir() / "总览HTML" / "report_总览.html"
        if p.exists():
            os.startfile(str(p))
        else:
            messagebox.showinfo("提示","还没有总览报告，完成第一次生成后会自动创建")


# ══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    _theme_path = _select_theme_at_startup()
    if _theme_path:
        _load_theme(_theme_path)
    app = App()
    app.mainloop()
