# -*- coding: utf-8 -*-
"""
modules/preset_gen/run.py — 预设主题生图模块（独立运行）

功能：
  加载主题 JSON → 用户选择结构/光效/情绪预设 → 批量文生图

独立运行（CLI）：
  python run.py --theme 巨构主义 --struct 0 --light 0 --mood 0 --count 3

独立运行（API Server）：
  python run.py --server

接入聚合平台：
  GET  /preset_gen/themes              → 列出可用主题
  GET  /preset_gen/presets/{theme}     → 获取主题预设选项
  POST /preset_gen/generate            → 提交生图任务
  GET  /preset_gen/status/{task_id}    → 查询状态

环境变量：
  KUNPO_API_KEY 或 ZIY_API_KEY
"""

import sys, os, json, datetime, time, argparse, uuid
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_ROOT))

from core.api import (
    get_api_key, call_imagine, save_results, ASPECT_MAP
)

# ──────────────────────────────────────────────────────────────────
# 主题加载
# ──────────────────────────────────────────────────────────────────

def _themes_dir() -> Path:
    # 优先找项目根的 themes/ 目录，其次 dist/themes/
    for candidate in [_ROOT / "themes", _ROOT / "dist" / "themes"]:
        if candidate.exists():
            return candidate
    return _ROOT / "themes"


def list_themes() -> list:
    """返回可用主题名列表"""
    td = _themes_dir()
    return [p.stem for p in sorted(td.glob("*.json"))]


def load_theme(theme_name: str) -> dict:
    """加载主题 JSON，返回主题数据字典"""
    td = _themes_dir()
    path = td / f"{theme_name}.json"
    if not path.exists():
        raise FileNotFoundError(f"主题文件不存在: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_prompt(theme: dict, struct_idx: int, light_idx: int, mood_idx: int,
                 extra: str = "", ar: str = "16:9",
                 stylize: int = 850, version: str = "7") -> str:
    structs = theme.get("struct_presets", [])
    lights  = theme.get("light_presets", [])
    moods   = theme.get("mood_presets", [])
    suffix  = theme.get("style_suffix", "")

    struct = structs[struct_idx] if struct_idx < len(structs) else ""
    light  = lights [light_idx]  if light_idx  < len(lights)  else ""
    mood   = moods  [mood_idx]   if mood_idx   < len(moods)   else ""

    parts = [p for p in [struct, light, mood, suffix, extra.strip()] if p]
    body  = ", ".join(parts)
    params = f"--ar {ar} --v {version} --stylize {stylize} --q 2"
    return f"{body} {params}"


# ──────────────────────────────────────────────────────────────────
# 核心执行
# ──────────────────────────────────────────────────────────────────

def run_preset_gen(theme_name: str,
                   struct_idx: int = 0,
                   light_idx: int = 0,
                   mood_idx: int = 0,
                   extra: str = "",
                   count: int = 1,
                   ar: str = "16:9",
                   stylize: int = 850,
                   version: str = "7",
                   output_dir: str = "",
                   progress_cb=None) -> dict:
    """
    批量预设主题文生图。count 表示提交次数（每次生成 4 张）。
    """
    def _log(msg):
        if progress_cb: progress_cb(msg)
        else: print(msg)

    theme = load_theme(theme_name)
    _log(f"[预设生图] 主题：{theme_name}，提交 {count} 批次")

    size = ASPECT_MAP.get(ar, "1024x1024")
    batch_ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_root = Path(output_dir) if output_dir else Path(__file__).parent / "output"
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    out_dir = out_root / today
    out_dir.mkdir(parents=True, exist_ok=True)

    all_results = []
    for i in range(count):
        prompt = build_prompt(theme, struct_idx, light_idx, mood_idx,
                              extra, ar, stylize, version)
        _log(f"[{i+1}/{count}] 提示词：{prompt[:80]}…")
        img_bytes = call_imagine(prompt, size, _log)
        saved = save_results(img_bytes, out_dir, batch_ts, "preset", {
            "timestamp": batch_ts,
            "module": "preset_gen",
            "theme": theme_name,
            "prompt": prompt,
            "ar": ar, "stylize": stylize, "version": version,
        })
        all_results.append({"prompt": prompt, "files": saved})
        _log(f"[{i+1}/{count}] 完成，保存 {len(saved)} 张")

    return {
        "batch_ts": batch_ts,
        "total_images": sum(len(r["files"]) for r in all_results),
        "results": all_results,
        "output_dir": str(out_dir),
    }


# ──────────────────────────────────────────────────────────────────
# FastAPI Server（可选）
# ──────────────────────────────────────────────────────────────────

def start_server(host: str = "0.0.0.0", port: int = 8000):
    try:
        from fastapi import FastAPI
        import uvicorn
    except ImportError:
        print("请先安装依赖：pip install fastapi uvicorn")
        sys.exit(1)

    from pydantic import BaseModel

    app = FastAPI(title="预设主题生图模块", version="1.0")
    _tasks = {}

    class GenerateRequest(BaseModel):
        theme_name: str
        struct_idx: int = 0
        light_idx: int = 0
        mood_idx: int = 0
        extra: str = ""
        count: int = 1
        ar: str = "16:9"
        stylize: int = 850
        version: str = "7"
        output_dir: str = ""

    @app.get("/health")
    def health():
        return {"status": "ok", "module": "preset_gen"}

    @app.get("/preset_gen/themes")
    def api_themes():
        return {"themes": list_themes()}

    @app.get("/preset_gen/presets/{theme_name}")
    def api_presets(theme_name: str):
        theme = load_theme(theme_name)
        return {
            "struct_presets": theme.get("struct_presets", []),
            "light_presets":  theme.get("light_presets", []),
            "mood_presets":   theme.get("mood_presets", []),
        }

    @app.post("/preset_gen/generate")
    def api_generate(req: GenerateRequest):
        import threading
        task_id = str(uuid.uuid4())
        _tasks[task_id] = {"status": "pending", "logs": [], "result": None}

        def _run():
            logs = []
            try:
                _tasks[task_id]["status"] = "running"
                result = run_preset_gen(
                    theme_name=req.theme_name,
                    struct_idx=req.struct_idx, light_idx=req.light_idx,
                    mood_idx=req.mood_idx, extra=req.extra,
                    count=req.count, ar=req.ar,
                    stylize=req.stylize, version=req.version,
                    output_dir=req.output_dir,
                    progress_cb=lambda m: logs.append(m)
                )
                _tasks[task_id].update({"status": "done", "result": result, "logs": logs})
            except Exception as e:
                _tasks[task_id].update({"status": "failed", "error": str(e), "logs": logs})

        threading.Thread(target=_run, daemon=True).start()
        return {"task_id": task_id, "status": "pending"}

    @app.get("/preset_gen/status/{task_id}")
    def api_status(task_id: str):
        if task_id not in _tasks:
            return {"error": "task not found"}
        return _tasks[task_id]

    print(f"[预设生图模块] 启动 API 服务 → http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)


# ──────────────────────────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="预设主题生图模块 CLI")
    parser.add_argument("--theme",   default="", help="主题名称，留空列出所有主题")
    parser.add_argument("--struct",  default="0", type=int, help="结构预设序号（0-based）")
    parser.add_argument("--light",   default="0", type=int, help="光效预设序号（0-based）")
    parser.add_argument("--mood",    default="0", type=int, help="情绪预设序号（0-based）")
    parser.add_argument("--extra",   default="", help="额外提示词")
    parser.add_argument("--count",   default="1", type=int, help="批次数量（每批4张）")
    parser.add_argument("--ar",      default="16:9")
    parser.add_argument("--stylize", default="850", type=int)
    parser.add_argument("--version", default="7")
    parser.add_argument("--output",  default="")
    parser.add_argument("--list-presets", action="store_true", help="列出主题所有预设选项")
    parser.add_argument("--server",  action="store_true")
    parser.add_argument("--host",    default="0.0.0.0")
    parser.add_argument("--port",    default=8000, type=int)
    args = parser.parse_args()

    if not args.theme and not args.server:
        print("可用主题：", list_themes())
        sys.exit(0)

    if not get_api_key() and not args.list_presets:
        print("❌ 未设置 API Key"); sys.exit(1)

    if args.server:
        start_server(args.host, args.port)
    elif args.list_presets:
        theme = load_theme(args.theme)
        print(f"\n── {args.theme} 结构预设 ──")
        for i, p in enumerate(theme.get("struct_presets", [])):
            print(f"  {i}: {p}")
        print(f"\n── {args.theme} 光效预设 ──")
        for i, p in enumerate(theme.get("light_presets", [])):
            print(f"  {i}: {p}")
        print(f"\n── {args.theme} 情绪预设 ──")
        for i, p in enumerate(theme.get("mood_presets", [])):
            print(f"  {i}: {p}")
    else:
        result = run_preset_gen(
            theme_name=args.theme,
            struct_idx=args.struct, light_idx=args.light, mood_idx=args.mood,
            extra=args.extra, count=args.count,
            ar=args.ar, stylize=args.stylize, version=args.version,
            output_dir=args.output, progress_cb=print,
        )
        print(f"\n✓ 完成！共生成 {result['total_images']} 张图")
        print(f"输出目录：{result['output_dir']}")
