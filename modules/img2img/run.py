# -*- coding: utf-8 -*-
"""
modules/img2img/run.py — 图生图模块（独立运行）

功能：
  上传风格图 + 主体控制图（+ 可选主题图）
  → Gemini 三层分析反推 MJ 提示词
  → Image-MI 图生图

独立运行（CLI）：
  python run.py --style path/to/style.jpg --subject path/to/subject.jpg --theme-json 巨构主义

独立运行（API Server）：
  python run.py --server --port 8002

接入聚合平台：
  POST /img2img/generate    → 提交图生图任务
  GET  /img2img/status/{id} → 查询任务状态

环境变量：
  KUNPO_API_KEY 或 ZIY_API_KEY
"""

import sys, os, json, datetime, time, argparse, uuid, re
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_ROOT))

from core.api import (
    get_api_key, call_blend, call_gemini_analyze_refs,
    img_to_data_uri, img_to_data_uri_blend,
    save_results, ASPECT_MAP,
    MODEL_GEMINI, MODEL_GEMINI_FB,
    CHAT_URL, CHAT_TIMEOUT, MAX_RETRIES
)
import requests

# ──────────────────────────────────────────────────────────────────
# 三层 Gemini Prompt（从主题 JSON 加载，或使用内置默认值）
# ──────────────────────────────────────────────────────────────────

_DEFAULT_META_PROMPT_LAYERS = """\
你是 Midjourney 提示词专家。我给你 {n} 张参考图：
{roles}

你的任务：为 Image-MI 写一段融合所有层信息的英文生图提示词。

【主体形态控制 - 三步强制执行】
Step 1：仔细分析 @image2 的轮廓（球形/锥形/矩形/有机曲线/复合形态）、几何细节和材质质感。
Step 2：将 @image2 的形态1:1映射为超现实巨型建筑，保留轮廓特征，放大至城市尺度。
Step 3：提示词必须以描述 @image2 形态的词组开头（至少15词），必须使用具体形态词汇。

核心目标：
- 视觉风格遵照 @image1 的光影色调、构图逻辑
- 画面核心主体必须是 @image2 的形态原型放大的建筑
- 场景意境遵照后续主题图（若无则自由设计）{theme_clause}

输出规则：
- 只输出最终英文提示词，不输出分析过程
- 逗号分隔，控制在 180 词以内
- 直接开始写提示词\
"""

_DEFAULT_LAYER_INLINE_TAGS = [
    "【第1张图 = @image1 风格图，仅提供视觉风格/光影色调/构图逻辑，不作为画面主体】",
    "【第2张图 = @image2 主体控制图，画面核心主体形态只能来自这张图】",
    "【第3张图 = @image3 内容主题图，定义场景意境与情绪氛围】",
    "【第4张图 = @image4 内容主题图2，补充场景细节与视觉元素】",
]

_DEFAULT_LAYER_LABELS = [
    "image1：风格图（整体视觉感、光影色调、构图形式）",
    "image2：结构图（主体结构状态、细节分布）",
    "image3：氛围场景图（场景环境、天空背景）",
    "image4：氛围场景图2（补充场景细节）",
]


def _load_meta_prompt(theme_json_path: str = "") -> tuple:
    """返回 (meta_prompt_template, layer_inline_tags, layer_labels)"""
    if theme_json_path and Path(theme_json_path).exists():
        with open(theme_json_path, encoding="utf-8") as f:
            data = json.load(f)
        return (
            data.get("meta_prompt_layers", _DEFAULT_META_PROMPT_LAYERS),
            _DEFAULT_LAYER_INLINE_TAGS,
            data.get("layer_labels_4", _DEFAULT_LAYER_LABELS),
        )
    return _DEFAULT_META_PROMPT_LAYERS, _DEFAULT_LAYER_INLINE_TAGS, _DEFAULT_LAYER_LABELS


def _build_meta_prompt(template: str, n: int, labels: list) -> str:
    roles = "\n".join(f"- {labels[i]}" for i in range(n))
    theme_count = max(0, n - 2)
    if theme_count >= 2:
        theme_clause = "\n- @image3 与 @image4 共同定义场景意境"
    else:
        theme_clause = ""
    return template.format(n=n, roles=roles, theme_clause=theme_clause)


# ──────────────────────────────────────────────────────────────────
# 核心执行
# ──────────────────────────────────────────────────────────────────

def run_img2img(style_path: str,
                subject_path: str,
                theme_paths: list = None,
                extra_prompt: str = "",
                ar: str = "9:16",
                stylize: int = 900,
                version: str = "7",
                theme_json_path: str = "",
                output_dir: str = "",
                progress_cb=None) -> dict:
    """
    图生图：三层参考图 → Gemini 反推提示词 → Image-MI 生图
    """
    def _log(msg):
        if progress_cb: progress_cb(msg)
        else: print(msg)

    ref_paths = [style_path, subject_path] + (theme_paths or [])
    ref_paths = [p for p in ref_paths if p and Path(p).exists()]
    if len(ref_paths) < 2:
        raise ValueError("至少需要风格图和主体控制图两张参考图")

    meta_template, inline_tags, labels = _load_meta_prompt(theme_json_path)
    meta_prompt = _build_meta_prompt(meta_template, len(ref_paths), labels)

    _log(f"[图生图] Step 1/2: Gemini 三层分析 {len(ref_paths)} 张参考图…")
    gemini_prompt = call_gemini_analyze_refs(
        ref_paths, meta_prompt, inline_tags, _log)

    user_extra = extra_prompt.strip()
    mj_params  = f" --ar {ar} --v {version} --stylize {stylize} --q 2"
    final_prompt = (gemini_prompt.rstrip(", \n") + mj_params +
                    ("\n" + user_extra if user_extra else ""))

    _log(f"[图生图] Step 2/2: Image-MI 生图（{len(ref_paths)} 张参考图）…")
    # 主体图优先（调至首位）
    if len(ref_paths) >= 2:
        mi_paths = [ref_paths[1], ref_paths[0]] + ref_paths[2:]
    else:
        mi_paths = ref_paths
    data_uris = [img_to_data_uri_blend(p) for p in mi_paths]
    size = ASPECT_MAP.get(ar, "864x1536")
    img_bytes = call_blend(data_uris, final_prompt, size, _log)

    batch_ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_root = Path(output_dir) if output_dir else Path(__file__).parent / "output"
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    out_dir = out_root / today

    saved = save_results(img_bytes, out_dir, batch_ts, "img2img", {
        "timestamp": batch_ts,
        "module": "img2img",
        "prompt": final_prompt,
        "gemini_prompt": gemini_prompt,
        "extra_prompt": extra_prompt,
        "ref_paths": ref_paths,
        "ar": ar, "stylize": stylize, "version": version,
    })
    _log(f"[图生图] 完成，保存 {len(saved)} 张")

    return {
        "batch_ts": batch_ts,
        "prompt": final_prompt,
        "gemini_prompt": gemini_prompt,
        "total_images": len(saved),
        "files": saved,
        "output_dir": str(out_dir),
    }


# ──────────────────────────────────────────────────────────────────
# FastAPI Server（可选）
# ──────────────────────────────────────────────────────────────────

def start_server(host: str = "0.0.0.0", port: int = 8002):
    try:
        from fastapi import FastAPI
        import uvicorn
    except ImportError:
        print("请先安装依赖：pip install fastapi uvicorn"); sys.exit(1)

    from pydantic import BaseModel
    from typing import List

    app = FastAPI(title="图生图模块", version="1.0")
    _tasks = {}

    class GenerateRequest(BaseModel):
        style_path: str
        subject_path: str
        theme_paths: List[str] = []
        extra_prompt: str = ""
        ar: str = "9:16"
        stylize: int = 900
        version: str = "7"
        theme_json_path: str = ""
        output_dir: str = ""

    @app.get("/health")
    def health(): return {"status": "ok", "module": "img2img"}

    @app.post("/img2img/generate")
    def api_generate(req: GenerateRequest):
        import threading
        task_id = str(uuid.uuid4())
        _tasks[task_id] = {"status": "pending", "logs": [], "result": None}

        def _run():
            logs = []
            try:
                _tasks[task_id]["status"] = "running"
                result = run_img2img(
                    style_path=req.style_path, subject_path=req.subject_path,
                    theme_paths=req.theme_paths, extra_prompt=req.extra_prompt,
                    ar=req.ar, stylize=req.stylize, version=req.version,
                    theme_json_path=req.theme_json_path, output_dir=req.output_dir,
                    progress_cb=lambda m: logs.append(m)
                )
                _tasks[task_id].update({"status": "done", "result": result, "logs": logs})
            except Exception as e:
                _tasks[task_id].update({"status": "failed", "error": str(e), "logs": logs})

        threading.Thread(target=_run, daemon=True).start()
        return {"task_id": task_id, "status": "pending"}

    @app.get("/img2img/status/{task_id}")
    def api_status(task_id: str):
        return _tasks.get(task_id, {"error": "task not found"})

    print(f"[图生图模块] 启动 API 服务 → http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)


# ──────────────────────────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="图生图模块 CLI")
    parser.add_argument("--style",   required=False, help="风格参考图路径（必选）")
    parser.add_argument("--subject", required=False, help="主体控制图路径（必选）")
    parser.add_argument("--themes",  default="",     help="主题图路径，逗号分隔（可选）")
    parser.add_argument("--extra",   default="",     help="额外提示词")
    parser.add_argument("--ar",      default="9:16")
    parser.add_argument("--stylize", default="900", type=int)
    parser.add_argument("--version", default="7")
    parser.add_argument("--theme-json", default="", help="主题 JSON 文件路径（可选）")
    parser.add_argument("--output",  default="")
    parser.add_argument("--server",  action="store_true")
    parser.add_argument("--host",    default="0.0.0.0")
    parser.add_argument("--port",    default=8002, type=int)
    args = parser.parse_args()

    if args.server:
        start_server(args.host, args.port)
    else:
        if not args.style or not args.subject:
            print("请指定 --style 和 --subject 参数"); sys.exit(1)
        theme_paths = [p.strip() for p in args.themes.split(",") if p.strip()]
        result = run_img2img(
            style_path=args.style, subject_path=args.subject,
            theme_paths=theme_paths, extra_prompt=args.extra,
            ar=args.ar, stylize=args.stylize, version=args.version,
            theme_json_path=args.theme_json, output_dir=args.output,
            progress_cb=print,
        )
        print(f"\n✓ 完成！共生成 {result['total_images']} 张图")
        print(f"输出目录：{result['output_dir']}")
