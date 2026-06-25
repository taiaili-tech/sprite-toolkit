# -*- coding: utf-8 -*-
"""
modules/free_gen/run.py — 自由生图模块（独立运行）

功能：
  用户描述想要的图像 → Gemini 生成30个内容方向 → 用户选择 → 转为 MJ 提示词 → 批量生图

独立运行（CLI）：
  python run.py --desc "我要一张唯美风景图" --select 1,3,5 --ar 16:9

独立运行（API Server，需安装 fastapi uvicorn）：
  python run.py --server

接入聚合平台：
  POST /free_gen/options     → 生成30个内容方向
  POST /free_gen/generate    → 提交选中方向生图
  GET  /free_gen/status/{id} → 查询任务状态

环境变量：
  KUNPO_API_KEY 或 ZIY_API_KEY
"""

import sys, os, json, datetime, time, argparse, uuid
from pathlib import Path

# 支持从项目根或模块目录运行
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_ROOT))

from core.api import (
    get_api_key, call_imagine, call_blend,
    call_gemini_chat, img_to_data_uri_blend,
    save_results, ASPECT_MAP,
    MODEL_GEMINI, MODEL_GEMINI_FB,
    CHAT_URL, CHAT_TIMEOUT, MAX_RETRIES
)
import requests, re

# ──────────────────────────────────────────────────────────────────
# Prompt 模板
# ──────────────────────────────────────────────────────────────────

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
- 禁止解释、禁止分类标题

用户需求：{user_input}\
"""

_SYSTEM_FREE_TO_PROMPT = """\
将以下中文场景描述转化为专业的 Midjourney 英文提示词。

要求：
- 纯英文，20-30词
- 包含：场景主体、光线氛围、构图风格
- 末尾原样追加风格后缀（不修改，直接拼接）
- 只输出提示词文本，不要任何解释，不要 --ar/--v 等参数

中文描述：{option}
风格后缀：{style_suffix}\
"""

DEFAULT_STYLE_SUFFIX = (
    "cinematic composition, hyper-realistic, 8K quality, "
    "a single lone figure for scale, no text, no watermark"
)

# ──────────────────────────────────────────────────────────────────
# 核心函数（独立，不依赖主程序）
# ──────────────────────────────────────────────────────────────────

def gen_options(user_input: str, progress_cb=None) -> list:
    """调用 Gemini 生成30个内容方向，返回字符串列表"""
    if progress_cb: progress_cb("[Gemini] 生成内容方向中…")
    prompt = _SYSTEM_FREE_OPTIONS.format(user_input=user_input)
    payload = {"model": MODEL_GEMINI, "messages": [{"role": "user", "content": prompt}]}
    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            r = requests.post(CHAT_URL, json=payload,
                              headers={"Authorization": f"Bearer {get_api_key()}",
                                       "Content-Type": "application/json"},
                              timeout=CHAT_TIMEOUT)
            if r.status_code == 200:
                text = r.json()["choices"][0]["message"]["content"]
                options = []
                for line in text.split("\n"):
                    m = re.match(r"^\d+[.、。]\s*(.+)$", line.strip())
                    if m: options.append(m.group(1).strip())
                return options
            if r.status_code in (422, 500) and payload["model"] != MODEL_GEMINI_FB:
                payload = dict(payload, model=MODEL_GEMINI_FB); continue
            last_err = f"HTTP {r.status_code}"; time.sleep(3)
        except requests.Timeout:
            last_err = "超时"
            if attempt < MAX_RETRIES: time.sleep(5)
        except Exception as e:
            raise RuntimeError(f"Gemini 错误: {e}")
    raise RuntimeError(f"Gemini 失败: {last_err}")


def option_to_prompt(option: str, style_suffix: str = "", progress_cb=None) -> str:
    """将一个中文方向转化为 MJ 英文提示词"""
    prompt = _SYSTEM_FREE_TO_PROMPT.format(
        option=option, style_suffix=style_suffix or DEFAULT_STYLE_SUFFIX)
    payload = {"model": MODEL_GEMINI, "messages": [{"role": "user", "content": prompt}]}
    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            r = requests.post(CHAT_URL, json=payload,
                              headers={"Authorization": f"Bearer {get_api_key()}",
                                       "Content-Type": "application/json"},
                              timeout=CHAT_TIMEOUT)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"].strip()
            if r.status_code in (422, 500) and payload["model"] != MODEL_GEMINI_FB:
                payload = dict(payload, model=MODEL_GEMINI_FB); continue
            last_err = f"HTTP {r.status_code}"; time.sleep(3)
        except requests.Timeout:
            last_err = "超时"
            if attempt < MAX_RETRIES: time.sleep(5)
        except Exception as e:
            raise RuntimeError(f"Gemini 错误: {e}")
    raise RuntimeError(f"Gemini 失败: {last_err}")


def run_free_gen(user_input: str,
                 selected_indices: list,         # 1-based index list
                 ar: str = "16:9",
                 stylize: int = 900,
                 version: str = "7",
                 style_image_path: str = "",
                 style_suffix: str = "",
                 output_dir: str = "",
                 progress_cb=None) -> dict:
    """
    完整执行自由生图流程，返回结果字典。

    selected_indices: 1-based 序号列表，如 [1, 3, 5]，传 [] 代表全选
    """
    def _log(msg):
        if progress_cb: progress_cb(msg)
        else: print(msg)

    _log(f"[自由生图] 生成内容方向：{user_input}")
    options = gen_options(user_input, progress_cb=_log)
    _log(f"[自由生图] 共生成 {len(options)} 个方向")

    # 按序号选择
    if selected_indices:
        selected = [options[i-1] for i in selected_indices if 1 <= i <= len(options)]
    else:
        selected = options

    _log(f"[自由生图] 选中 {len(selected)} 个方向，开始转换提示词…")

    size = ASPECT_MAP.get(ar, "1024x1024")
    batch_ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_root = Path(output_dir) if output_dir else Path(__file__).parent / "output"
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    out_dir = out_root / today
    out_dir.mkdir(parents=True, exist_ok=True)

    all_results = []
    for i, opt in enumerate(selected):
        _log(f"[{i+1}/{len(selected)}] 转换提示词：{opt[:30]}…")
        mj_prompt = option_to_prompt(opt, style_suffix, progress_cb=_log)
        full_prompt = (mj_prompt.rstrip(", \n") +
                       f" --ar {ar} --v {version} --stylize {stylize} --q 2")

        _log(f"[{i+1}/{len(selected)}] 生图中…")
        if style_image_path and Path(style_image_path).exists():
            data_uri = img_to_data_uri_blend(style_image_path)
            img_bytes = call_blend([data_uri], full_prompt, size, _log)
            suffix = "free_blend"
        else:
            img_bytes = call_imagine(full_prompt, size, _log)
            suffix = "free"

        saved = save_results(img_bytes, out_dir, batch_ts, suffix, {
            "timestamp": batch_ts,
            "module": "free_gen",
            "option": opt,
            "prompt": full_prompt,
            "ar": ar, "stylize": stylize, "version": version,
            "style_image": style_image_path,
        })
        all_results.append({"option": opt, "prompt": full_prompt, "files": saved})
        _log(f"[{i+1}/{len(selected)}] 完成，保存 {len(saved)} 张")

    return {
        "batch_ts": batch_ts,
        "total_images": sum(len(r["files"]) for r in all_results),
        "results": all_results,
        "output_dir": str(out_dir),
    }


# ──────────────────────────────────────────────────────────────────
# FastAPI Server（可选）
# ──────────────────────────────────────────────────────────────────

def start_server(host: str = "0.0.0.0", port: int = 8001):
    try:
        from fastapi import FastAPI
        import uvicorn
    except ImportError:
        print("请先安装依赖：pip install fastapi uvicorn")
        sys.exit(1)

    from pydantic import BaseModel
    from typing import Optional

    app = FastAPI(title="自由生图模块", version="1.0")

    # 内存任务存储（生产环境换成 Redis/数据库）
    _tasks = {}

    class OptionsRequest(BaseModel):
        user_input: str

    class GenerateRequest(BaseModel):
        user_input: str
        selected_indices: list = []   # 空=全选
        ar: str = "16:9"
        stylize: int = 900
        version: str = "7"
        style_image_path: str = ""
        style_suffix: str = ""
        output_dir: str = ""

    @app.get("/health")
    def health():
        return {"status": "ok", "module": "free_gen"}

    @app.post("/free_gen/options")
    def api_gen_options(req: OptionsRequest):
        options = gen_options(req.user_input)
        return {"options": options, "count": len(options)}

    @app.post("/free_gen/generate")
    def api_generate(req: GenerateRequest):
        import threading
        task_id = str(uuid.uuid4())
        _tasks[task_id] = {"status": "pending", "logs": [], "result": None}

        def _run():
            logs = []
            try:
                _tasks[task_id]["status"] = "running"
                result = run_free_gen(
                    user_input=req.user_input,
                    selected_indices=req.selected_indices,
                    ar=req.ar, stylize=req.stylize, version=req.version,
                    style_image_path=req.style_image_path,
                    style_suffix=req.style_suffix,
                    output_dir=req.output_dir,
                    progress_cb=lambda m: logs.append(m)
                )
                _tasks[task_id].update({"status": "done", "result": result, "logs": logs})
            except Exception as e:
                _tasks[task_id].update({"status": "failed", "error": str(e), "logs": logs})

        threading.Thread(target=_run, daemon=True).start()
        return {"task_id": task_id, "status": "pending"}

    @app.get("/free_gen/status/{task_id}")
    def api_status(task_id: str):
        if task_id not in _tasks:
            return {"error": "task not found"}
        return _tasks[task_id]

    print(f"[自由生图模块] 启动 API 服务 → http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)


# ──────────────────────────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="自由生图模块 CLI")
    parser.add_argument("--desc",    required=False, help="图像描述，如「我要一张唯美风景图」")
    parser.add_argument("--select",  default="",     help="选择的方向序号，逗号分隔，如 1,3,5（空=全选）")
    parser.add_argument("--ar",      default="16:9", help="画面比例，默认 16:9")
    parser.add_argument("--stylize", default="900",  help="精细度，默认 900")
    parser.add_argument("--version", default="7",    help="MJ 版本，默认 7")
    parser.add_argument("--style",   default="",     help="风格参考图路径（可选）")
    parser.add_argument("--output",  default="",     help="输出目录（可选）")
    parser.add_argument("--list-options", action="store_true",
                        help="仅生成并列出30个方向，不生图")
    parser.add_argument("--server",  action="store_true", help="启动 API Server 模式")
    parser.add_argument("--host",    default="0.0.0.0")
    parser.add_argument("--port",    default="8001", type=int)
    args = parser.parse_args()

    if not get_api_key():
        print("❌ 未设置 API Key，请配置环境变量 KUNPO_API_KEY 或 ZIY_API_KEY")
        sys.exit(1)

    if args.server:
        start_server(args.host, args.port)
    elif args.list_options:
        if not args.desc:
            print("请用 --desc 指定描述"); sys.exit(1)
        opts = gen_options(args.desc, progress_cb=print)
        print("\n─── 30个内容方向 ───")
        for i, o in enumerate(opts, 1):
            print(f"{i:2d}. {o}")
    else:
        if not args.desc:
            print("请用 --desc 指定描述，或 --help 查看帮助"); sys.exit(1)
        indices = [int(x) for x in args.select.split(",") if x.strip().isdigit()] if args.select else []
        result = run_free_gen(
            user_input=args.desc,
            selected_indices=indices,
            ar=args.ar,
            stylize=int(args.stylize),
            version=args.version,
            style_image_path=args.style,
            output_dir=args.output,
            progress_cb=print,
        )
        print(f"\n✓ 完成！共生成 {result['total_images']} 张图")
        print(f"输出目录：{result['output_dir']}")
