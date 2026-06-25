# -*- coding: utf-8 -*-
"""
modules/auto_batch/run.py — 自动批量生图模块（独立运行）

功能：
  读取本地图片文件夹 → Gemini 自动选材（风格/主体/主题三层）
  → 多批次图生图

独立运行（CLI）：
  python run.py --folder path/to/images --theme "赛博感" --batches 3

独立运行（API Server）：
  python run.py --server --port 8003

接入聚合平台：
  POST /auto_batch/generate    → 提交自动批量任务
  GET  /auto_batch/status/{id} → 查询任务状态

环境变量：
  KUNPO_API_KEY 或 ZIY_API_KEY
"""

import sys, os, json, datetime, time, argparse, uuid, random, re
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_ROOT))

from core.api import (
    get_api_key, call_blend, call_gemini_chat,
    img_to_data_uri, img_to_data_uri_blend,
    save_results, ASPECT_MAP,
    MODEL_GEMINI, MODEL_GEMINI_FB,
    CHAT_URL, CHAT_TIMEOUT, MAX_RETRIES
)
import requests

SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
MAX_CANDIDATES = 12

# ──────────────────────────────────────────────────────────────────
# 自动选材 Gemini Prompt
# ──────────────────────────────────────────────────────────────────

_META_PROMPT_AUTO_SELECT = """\
你是 AI 生图素材选材专家。我给你 {n} 张候选图片，编号 image1~image{n}。
主题关键词：「{theme}」

你的任务：从这 {n} 张图中，为三层结构选出最合适的图片：
- **风格图**（1 张，必选）：最能体现光影质感、氛围色调、整体视觉风格的图
- **主体控制图**（1 张，必选）：最能代表核心建筑/结构形态、几何特征的图
- **主题图**（1~2 张，可选）：最能体现场景意境、情绪氛围的图

选材原则：
- 与主题关键词「{theme}」最契合的优先
- 三层图尽量不重复

输出格式（严格遵守，只输出 JSON，不输出其他内容）：
{{
  "style":   <image 编号，如 "image3">,
  "subject": <image 编号，如 "image1">,
  "themes":  [<可选，0~2个 image 编号>]
}}
"""

_DEFAULT_META_PROMPT_LAYERS = """\
你是 Midjourney 提示词专家。我给你 {n} 张参考图：
{roles}

你的任务：为 Image-MI 写一段融合所有层信息的英文生图提示词。

核心要求：
- 视觉风格遵照 @image1 的光影色调
- 画面核心主体基于 @image2 的形态特征
- 场景意境遵照后续主题图（若无则自由设计）

输出规则：
- 只输出英文提示词，不输出分析，控制在 150 词以内
- 直接开始写\
"""

_DEFAULT_INLINE_TAGS = [
    "【第1张图 = @image1 风格图】",
    "【第2张图 = @image2 主体控制图】",
    "【第3张图 = @image3 内容主题图】",
    "【第4张图 = @image4 内容主题图2】",
]

_DEFAULT_LAYER_LABELS = [
    "image1：风格图", "image2：结构/主体控制图",
    "image3：氛围场景图", "image4：氛围场景图2",
]


# ──────────────────────────────────────────────────────────────────
# 自动选材
# ──────────────────────────────────────────────────────────────────

def auto_select_materials(image_paths: list, theme: str,
                           progress_cb=None) -> dict:
    """
    Gemini 从候选图中自动分配三层角色。
    返回 {"style": path, "subject": path, "themes": [path, ...]}
    """
    def _log(msg):
        if progress_cb: progress_cb(msg)
        else: print(msg)

    candidates = image_paths[:MAX_CANDIDATES]
    n = len(candidates)
    _log(f"[选材] 发送 {n} 张候选图到 Gemini…")

    prompt_text = _META_PROMPT_AUTO_SELECT.format(n=n, theme=theme)
    content_parts = [{"type": "text", "text": prompt_text}]
    for i, path in enumerate(candidates):
        content_parts.append({"type": "text", "text": f"image{i+1}："})
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": img_to_data_uri(path)}
        })

    result_text = call_gemini_chat(content_parts, _log)

    # 解析 JSON
    m = re.search(r'\{.*?\}', result_text, re.DOTALL)
    if not m:
        _log("[选材] 解析失败，随机分配")
        shuffled = candidates[:]
        random.shuffle(shuffled)
        return {"style": shuffled[0], "subject": shuffled[1],
                "themes": shuffled[2:4] if len(shuffled) > 2 else []}

    parsed = json.loads(m.group(0))
    idx_map = {f"image{i+1}": p for i, p in enumerate(candidates)}

    style   = idx_map.get(parsed.get("style",""), candidates[0])
    subject = idx_map.get(parsed.get("subject",""), candidates[min(1, len(candidates)-1)])
    themes  = [idx_map[t] for t in parsed.get("themes",[]) if t in idx_map]

    _log(f"[选材] 风格图: {Path(style).name}  主体图: {Path(subject).name}  "
         f"主题图: {[Path(t).name for t in themes]}")
    return {"style": style, "subject": subject, "themes": themes}


def _gen_prompt_from_refs(ref_paths: list, meta_template: str,
                           inline_tags: list, labels: list,
                           progress_cb=None) -> str:
    n = len(ref_paths)
    roles = "\n".join(f"- {labels[i]}" for i in range(n))
    meta_prompt = meta_template.format(n=n, roles=roles)

    content_parts = [{"type": "text", "text": meta_prompt}]
    for i, path in enumerate(ref_paths):
        if inline_tags and i < len(inline_tags):
            content_parts.append({"type": "text", "text": inline_tags[i]})
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": img_to_data_uri(path)}
        })
    return call_gemini_chat(content_parts, progress_cb)


# ──────────────────────────────────────────────────────────────────
# 核心执行
# ──────────────────────────────────────────────────────────────────

def run_auto_batch(folder_path: str,
                   theme: str = "风格",
                   batches: int = 3,
                   ar: str = "9:16",
                   stylize: int = 900,
                   version: str = "7",
                   theme_json_path: str = "",
                   output_dir: str = "",
                   progress_cb=None) -> dict:
    """
    自动批量生图：每批次重新选材，生成 batches×4 张图。
    """
    def _log(msg):
        if progress_cb: progress_cb(msg)
        else: print(msg)

    # 加载主题 JSON（可选）
    if theme_json_path and Path(theme_json_path).exists():
        with open(theme_json_path, encoding="utf-8") as f:
            theme_data = json.load(f)
        meta_template = theme_data.get("meta_prompt_layers", _DEFAULT_META_PROMPT_LAYERS)
    else:
        meta_template = _DEFAULT_META_PROMPT_LAYERS

    # 收集候选图片
    folder = Path(folder_path)
    if not folder.exists():
        raise FileNotFoundError(f"文件夹不存在: {folder_path}")
    all_images = [str(p) for p in sorted(folder.iterdir())
                  if p.suffix.lower() in SUPPORTED_EXTS]
    if len(all_images) < 2:
        raise ValueError(f"文件夹中图片不足（至少需要2张），当前: {len(all_images)} 张")

    _log(f"[自动批量] 文件夹: {folder_path}，共 {len(all_images)} 张图")
    _log(f"[自动批量] 主题: {theme}，批次: {batches}")

    size = ASPECT_MAP.get(ar, "864x1536")
    batch_ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_root = Path(output_dir) if output_dir else Path(__file__).parent / "output"
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    out_dir = out_root / today

    all_results = []
    for batch_i in range(batches):
        _log(f"\n[批次 {batch_i+1}/{batches}] 开始选材…")

        # 每批随机抽取候选
        candidates = random.sample(all_images, min(MAX_CANDIDATES, len(all_images)))
        selection  = auto_select_materials(candidates, theme, _log)

        style_path   = selection["style"]
        subject_path = selection["subject"]
        theme_paths  = selection["themes"]

        ref_paths = [style_path, subject_path] + theme_paths
        _log(f"[批次 {batch_i+1}] 选材完成，{len(ref_paths)} 张参考图")

        _log(f"[批次 {batch_i+1}] Gemini 反推提示词…")
        gemini_prompt = _gen_prompt_from_refs(
            ref_paths, meta_template,
            _DEFAULT_INLINE_TAGS, _DEFAULT_LAYER_LABELS, _log)

        mj_params = f" --ar {ar} --v {version} --stylize {stylize} --q 2"
        final_prompt = gemini_prompt.rstrip(", \n") + mj_params

        # 主体图优先
        mi_paths = [ref_paths[1], ref_paths[0]] + ref_paths[2:]
        data_uris = [img_to_data_uri_blend(p) for p in mi_paths]

        _log(f"[批次 {batch_i+1}] Image-MI 生图…")
        img_bytes = call_blend(data_uris, final_prompt, size, _log)

        saved = save_results(img_bytes, out_dir, batch_ts, f"auto_b{batch_i+1}", {
            "timestamp": batch_ts,
            "module": "auto_batch",
            "batch": batch_i + 1,
            "theme": theme,
            "prompt": final_prompt,
            "gemini_prompt": gemini_prompt,
            "ref_paths": ref_paths,
            "ar": ar, "stylize": stylize, "version": version,
        })
        all_results.append({
            "batch": batch_i + 1,
            "selection": {k: Path(v).name if isinstance(v,str) else [Path(x).name for x in v]
                          for k, v in selection.items()},
            "prompt": final_prompt,
            "files": saved,
        })
        _log(f"[批次 {batch_i+1}] 完成，保存 {len(saved)} 张")

    return {
        "batch_ts": batch_ts,
        "total_images": sum(len(r["files"]) for r in all_results),
        "results": all_results,
        "output_dir": str(out_dir),
    }


# ──────────────────────────────────────────────────────────────────
# FastAPI Server（可选）
# ──────────────────────────────────────────────────────────────────

def start_server(host: str = "0.0.0.0", port: int = 8003):
    try:
        from fastapi import FastAPI
        import uvicorn
    except ImportError:
        print("请先安装依赖：pip install fastapi uvicorn"); sys.exit(1)

    from pydantic import BaseModel

    app = FastAPI(title="自动批量生图模块", version="1.0")
    _tasks = {}

    class GenerateRequest(BaseModel):
        folder_path: str
        theme: str = "风格"
        batches: int = 3
        ar: str = "9:16"
        stylize: int = 900
        version: str = "7"
        theme_json_path: str = ""
        output_dir: str = ""

    @app.get("/health")
    def health(): return {"status": "ok", "module": "auto_batch"}

    @app.post("/auto_batch/generate")
    def api_generate(req: GenerateRequest):
        import threading
        task_id = str(uuid.uuid4())
        _tasks[task_id] = {"status": "pending", "logs": [], "result": None}

        def _run():
            logs = []
            try:
                _tasks[task_id]["status"] = "running"
                result = run_auto_batch(
                    folder_path=req.folder_path, theme=req.theme,
                    batches=req.batches, ar=req.ar,
                    stylize=req.stylize, version=req.version,
                    theme_json_path=req.theme_json_path,
                    output_dir=req.output_dir,
                    progress_cb=lambda m: logs.append(m)
                )
                _tasks[task_id].update({"status": "done", "result": result, "logs": logs})
            except Exception as e:
                _tasks[task_id].update({"status": "failed", "error": str(e), "logs": logs})

        threading.Thread(target=_run, daemon=True).start()
        return {"task_id": task_id, "status": "pending"}

    @app.get("/auto_batch/status/{task_id}")
    def api_status(task_id: str):
        return _tasks.get(task_id, {"error": "task not found"})

    print(f"[自动批量模块] 启动 API 服务 → http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)


# ──────────────────────────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="自动批量生图模块 CLI")
    parser.add_argument("--folder",  required=False, help="参考图文件夹路径")
    parser.add_argument("--theme",   default="风格",  help="主题关键词")
    parser.add_argument("--batches", default="3",    type=int, help="批次数量")
    parser.add_argument("--ar",      default="9:16")
    parser.add_argument("--stylize", default="900",  type=int)
    parser.add_argument("--version", default="7")
    parser.add_argument("--theme-json", default="")
    parser.add_argument("--output",  default="")
    parser.add_argument("--server",  action="store_true")
    parser.add_argument("--host",    default="0.0.0.0")
    parser.add_argument("--port",    default=8003, type=int)
    args = parser.parse_args()

    if args.server:
        start_server(args.host, args.port)
    else:
        if not args.folder:
            print("请用 --folder 指定图片文件夹"); sys.exit(1)
        result = run_auto_batch(
            folder_path=args.folder, theme=args.theme,
            batches=args.batches, ar=args.ar,
            stylize=args.stylize, version=args.version,
            theme_json_path=args.theme_json, output_dir=args.output,
            progress_cb=print,
        )
        print(f"\n✓ 完成！共生成 {result['total_images']} 张图")
        print(f"输出目录：{result['output_dir']}")
