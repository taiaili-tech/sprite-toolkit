# -*- coding: utf-8 -*-
"""
packages/build.py — 种子包构建脚本

将 _template/run.py 和 themes/*.json 组合，生成各主题独立包。
每次修改 run.py 或 theme.json 后重新执行此脚本即可同步所有包。

运行方式：
  cd packages
  python build.py
"""

import shutil, json
from pathlib import Path

_HERE      = Path(__file__).resolve().parent
_TEMPLATE  = _HERE / "_template" / "run.py"
_THEMES    = _HERE.parent / "themes"

THEME_PACKAGES = {
    "巨构主义": 8000,
    "赛博朋克": 8001,
    "极简主义": 8002,
    "哥特主义": 8003,
    "结构主义": 8004,
}

def build():
    if not _TEMPLATE.exists():
        print(f"❌ 模板文件不存在: {_TEMPLATE}"); return

    for theme_name, port in THEME_PACKAGES.items():
        pkg_dir    = _HERE / theme_name
        theme_json = _THEMES / f"{theme_name}.json"
        pkg_dir.mkdir(exist_ok=True)

        if not theme_json.exists():
            print(f"⚠  主题文件不存在，跳过: {theme_json}"); continue

        # 复制 run.py
        shutil.copy2(_TEMPLATE, pkg_dir / "run.py")

        # 复制 theme.json
        shutil.copy2(theme_json, pkg_dir / "theme.json")

        # 生成 README.md
        with open(theme_json, encoding="utf-8") as f:
            theme_data = json.load(f)
        title   = theme_data.get("title", f"MJ {theme_name}生图")
        keyword = theme_data.get("theme_keyword", theme_name)
        n_struct = len(theme_data.get("struct_presets", []))
        n_light  = len(theme_data.get("light_presets",  []))
        n_mood   = len(theme_data.get("mood_presets",   []))

        readme = f"""# {title}

> 主题关键词：{keyword}

## 快速开始

```bash
# 设置 API Key
set KUNPO_API_KEY=your_key_here

# 查看预设选项
python run.py --list-presets

# 文生图（从预设生成）
python run.py --mode txt2img --struct 0 --light 0 --mood 0 --count 3

# 自由创作（描述需求 → AI 生成30个方向）
python run.py --mode free --desc "我要一张{keyword}风格图" --select 1,3,5

# 图生图（三层参考图）
python run.py --mode img2img --style 风格图.jpg --subject 主体图.jpg

# 自动批量（文件夹图片自动选材）
python run.py --mode auto --folder ./refs --batches 3

# 启动 API Server（默认端口 {port}）
python run.py --server --port {port}
```

## 预设数量

| 类型 | 数量 |
|------|------|
| 结构预设 | {n_struct} 个 |
| 光效预设 | {n_light} 个 |
| 情绪预设 | {n_mood} 个 |

## API 接口（Server 模式）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/health`           | 健康检查 |
| GET  | `/presets`          | 获取预设选项 |
| POST | `/generate/txt2img` | 预设文生图 |
| POST | `/generate/img2img` | 三层图生图 |
| POST | `/generate/free`    | 自由创作生图 |
| POST | `/generate/auto`    | 自动批量生图 |
| POST | `/free/options`     | 仅获取30个内容方向 |
| GET  | `/status/{{task_id}}` | 查询任务状态 |

## 文件说明

- `run.py`    — 完整独立引擎（所有生图逻辑，无外部模块依赖）
- `theme.json` — 该主题专属配置（预设词库 + Gemini 提示词模板）
- `output/`   — 生成结果目录（按日期自动分文件夹）

## 环境依赖

```bash
pip install requests Pillow
# API Server 模式额外需要：
pip install fastapi uvicorn
```
"""
        (pkg_dir / "README.md").write_text(readme, encoding="utf-8")
        print(f"[OK] {theme_name}/  -> run.py + theme.json + README.md  (port {port})")

    print(f"\n[DONE] 全部 {len(THEME_PACKAGES)} 个种子包构建完成")
    print(f"目录: {_HERE}")

if __name__ == "__main__":
    build()
