# -*- coding: utf-8 -*-
r"""
create_seed_packages.py
=======================
生成每个主题的完整独立种子包，结构与 MJ巨构批量生图_种子包_v1.0 完全一致。

运行方式：
  cd MJ批量生图_引擎目录
  python create_seed_packages.py

每个种子包产出于 Desktop\临时\ 下：
  MJ赛博朋克批量生图_种子包_v2.0
  MJ极简主义批量生图_种子包_v2.0
  MJ哥特主义批量生图_种子包_v2.0
  MJ结构主义批量生图_种子包_v2.0
  MJ巨构主义批量生图_种子包_v2.0
"""

import shutil, json
from pathlib import Path

# ──────────────────────────────────────────────────────────────────
# 路径配置
# ──────────────────────────────────────────────────────────────────
ENGINE_DIR  = Path(__file__).resolve().parent
SOURCE_PYW  = ENGINE_DIR / "MJ批量生图_引擎.pyw"
ICON_SRC    = ENGINE_DIR / "app_icon.ico"
THEMES_DIR  = ENGINE_DIR / "themes"
OUTPUT_BASE = ENGINE_DIR.parent     # Desktop\临时\

VERSION = "v2.0"

THEMES = {
    "巨构主义": {"keyword": "巨构建筑", "port": 8000, "ar_default": "16:9",  "stylize": 850},
    "赛博朋克": {"keyword": "赛博感",   "port": 8001, "ar_default": "9:16",  "stylize": 900},
    "极简主义": {"keyword": "极简",     "port": 8002, "ar_default": "1:1",   "stylize": 800},
    "哥特主义": {"keyword": "哥特",     "port": 8003, "ar_default": "9:16",  "stylize": 900},
    "结构主义": {"keyword": "结构",     "port": 8004, "ar_default": "16:9",  "stylize": 850},
}

# ──────────────────────────────────────────────────────────────────
# .spec 模板
# ──────────────────────────────────────────────────────────────────
def make_spec(exe_name: str) -> str:
    return f"""\
# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['{exe_name}.pyw'],
    pathex=[],
    binaries=[],
    datas=[
        ('themes', 'themes'),
    ],
    hiddenimports=[
        'playwright',
        'playwright.sync_api',
        'playwright._impl._driver',
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='{exe_name}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=['node.exe'],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app_icon.ico',
)
"""

# ──────────────────────────────────────────────────────────────────
# 使用说明模板
# ──────────────────────────────────────────────────────────────────
def make_readme(theme_name: str, theme_data: dict, exe_name: str,
                n_struct: int, n_light: int, n_mood: int) -> str:
    keyword    = theme_data.get("theme_keyword", theme_name)
    ar_default = THEMES[theme_name]["ar_default"]
    stylize    = THEMES[theme_name]["stylize"]
    title      = theme_data.get("title", f"MJ{theme_name}批量生图 {VERSION}")

    return f"""\
# {title} · 使用说明

## 这个工具能做什么

批量调用 KUNPO API 的 Midjourney 模型，生产「{keyword}」风格 AI 图片。

| 模式 | 说明 |
|------|------|
| **文生图** | 从{theme_name}专属预设选择结构/光效/情绪，一键生成提示词 → 批量出图 |
| **图生图** | 上传三层参考图（风格图+主体图+可选主题图）→ Gemini反推提示词 → 融合生成 |
| **自由创作** | 描述你想要的图像 → AI生成30个{keyword}风格方向 → 选择方向 → 批量出图 |
| **自动模式** | 本地文件夹图片 → Gemini自动选材 → 多批次图生图 |

---

## 快速开始

双击运行 `dist\\{exe_name}.exe`（无需安装 Python）

---

## 文生图用法（Tab1）

### 快速填充

1. 在「① 快速填充」区域分别选择：
   - **结构**：画面主体构造类型（共 {n_struct} 个选项）
   - **光效**：光影氛围（共 {n_light} 个选项）
   - **情绪**：画面情感基调（共 {n_mood} 个选项）
2. 点击「→ 填充提示词」，自动合并填入提示词框
3. 设置比例（推荐 {ar_default}）、版本（推荐 7）、Stylize（推荐 {stylize}）
4. 点击「▶ 开始生成」

### 直接编辑提示词

在提示词框中直接输入完整 MJ 提示词：
```
{keyword}风格建筑, 电影级构图, --ar {ar_default} --v 7 --stylize {stylize} --q 2
```

---

## 图生图用法（Tab2 · 三层参考图）

1. 在「图生图」Tab 中依次选择：
   - **① 风格图**（必选）：定义光影色调 / 构图风格
   - **② 主体控制图**（必选）：定义核心建筑/结构形态
   - **③ 内容主题图**（可选，最多 2 张）：定义场景意境 / 情绪氛围
2. 设置参数，点击「▶ 开始生成」

> **原理**：Gemini 分析三层参考图生成{keyword}风格英文提示词，再将参考图 + 提示词发给 Image-MI，一次出 4 张结果。

---

## 自由创作用法（Tab4）

1. 在「✧ 自由创作」Tab 中输入你想要的图像描述
2. 点击「生成30个方向」，AI 自动生成 30 个{keyword}风格内容方向
3. 勾选你喜欢的方向（可多选）
4. 可选：上传一张风格参考图
5. 点击「开始批量生图」

---

## 自动模式用法（Tab3）

1. 填写主题关键词（默认「{keyword}」）
2. 选择本地图片文件夹或从 Pinterest 抓图
3. 设置批次数，点击「一键生成」

---

## 参数说明

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| 比例 | {ar_default} | 输出图片比例 |
| 版本 | 7 | MJ 模型版本 |
| Stylize | {stylize} | 越高越有 MJ 艺术感（0~1000） |
| 生成 N 张 | 1~5 | 每次点开始生成的重复次数 |
| 并发 | 3 | 同时运行的任务数 |

---

## 输出文件

```
output/
  YYYY-MM-DD/
    时间戳_txt2img_xxxxx_1of4_result.png   ← 生成图片（每批4张）
    时间戳_txt2img_xxxxx_meta.json         ← 元数据
    report_时间戳.html                      ← 批次对比报告
总览HTML/
  report_总览.html                          ← 跨批次汇总报告
```

---

## 更换/扩展主题

将新的主题 `.json` 文件放入 `themes/` 目录，重启程序后会弹出主题选择窗口。

---

## 常见问题

| 问题 | 处理 |
|------|------|
| 双击 exe 无反应 | 确认 `dist\\` 文件夹完整，不要单独复制 exe |
| 提示「未找到 API Key」 | 联系 LF 获取最新版本 |
| 生成超时 | 网络波动，重新点「开始生成」 |
| 质量不满意 | 调高 Stylize（950+）或多生成几张挑选 |

---

## 打包为 exe

```bash
pip install pyinstaller pillow requests
pyinstaller {exe_name}.spec
```

打包完成后运行 `dist\\{exe_name}.exe`。

---

## 联系

有问题请联系 LF。
"""

# ──────────────────────────────────────────────────────────────────
# 主构建函数
# ──────────────────────────────────────────────────────────────────
def build_package(theme_name: str):
    theme_json_src = THEMES_DIR / f"{theme_name}.json"
    if not theme_json_src.exists():
        print(f"[SKIP] 找不到主题文件: {theme_json_src}")
        return

    with open(theme_json_src, encoding="utf-8") as f:
        theme_data = json.load(f)

    n_struct = len(theme_data.get("struct_presets", []))
    n_light  = len(theme_data.get("light_presets",  []))
    n_mood   = len(theme_data.get("mood_presets",   []))

    pkg_name = f"MJ{theme_name}批量生图_种子包_{VERSION}"
    exe_name = f"MJ{theme_name}批量生图_{VERSION}"
    pkg_dir  = OUTPUT_BASE / pkg_name

    print(f"[BUILD] {pkg_name}  ->  {pkg_dir}")

    # 1. 创建目录结构
    (pkg_dir / "themes").mkdir(parents=True, exist_ok=True)
    (pkg_dir / "dist" / "themes").mkdir(parents=True, exist_ok=True)
    (pkg_dir / "dist" / "output").mkdir(parents=True, exist_ok=True)
    (pkg_dir / "dist" / "总览HTML").mkdir(parents=True, exist_ok=True)

    # 2. 复制并重命名 .pyw
    pyw_dest = pkg_dir / f"{exe_name}.pyw"
    shutil.copy2(SOURCE_PYW, pyw_dest)
    print(f"  .pyw  -> {pyw_dest.name}")

    # 3. 写 .spec
    spec_path = pkg_dir / f"{exe_name}.spec"
    spec_path.write_text(make_spec(exe_name), encoding="utf-8")
    print(f"  .spec -> {spec_path.name}")

    # 4. 复制图标
    if ICON_SRC.exists():
        shutil.copy2(ICON_SRC, pkg_dir / "app_icon.ico")
        print(f"  icon  -> app_icon.ico")
    else:
        print(f"  icon  [SKIP] app_icon.ico 不存在")

    # 5. 写使用说明
    readme_path = pkg_dir / "使用说明.md"
    readme_path.write_text(
        make_readme(theme_name, theme_data, exe_name, n_struct, n_light, n_mood),
        encoding="utf-8")
    print(f"  docs  -> 使用说明.md")

    # 6. 复制 theme.json 到 themes/（源码运行用）
    shutil.copy2(theme_json_src, pkg_dir / "themes" / f"{theme_name}.json")
    print(f"  json  -> themes/{theme_name}.json")

    # 7. 复制 theme.json 到 dist/themes/（exe 旁边，运行时读取）
    shutil.copy2(theme_json_src, pkg_dir / "dist" / "themes" / f"{theme_name}.json")
    print(f"  json  -> dist/themes/{theme_name}.json")

    # 8. 复制 playwright node.exe 到 dist/playwright_driver/
    #    程序启动时通过 PLAYWRIGHT_NODEJS_PATH 自动找到，无需用户额外安装
    import playwright as _pw
    node_src = Path(_pw.__file__).parent / "driver" / "node.exe"
    if node_src.exists():
        node_dst_dir = pkg_dir / "dist" / "playwright_driver"
        node_dst_dir.mkdir(exist_ok=True)
        shutil.copy2(node_src, node_dst_dir / "node.exe")
        print(f"  node  -> dist/playwright_driver/node.exe ({node_src.stat().st_size // 1024 // 1024}MB)")
    else:
        print(f"  node  [SKIP] playwright driver not found")

    print(f"  [OK]  {pkg_name} 构建完成\n")


def build_all():
    print(f"源码：{SOURCE_PYW}")
    print(f"输出：{OUTPUT_BASE}\n")

    if not SOURCE_PYW.exists():
        print(f"[ERROR] 找不到源码文件: {SOURCE_PYW}")
        return

    for theme_name in THEMES:
        build_package(theme_name)

    print("=" * 50)
    print(f"全部 {len(THEMES)} 个种子包构建完成")
    print(f"位置: {OUTPUT_BASE}")
    print("=" * 50)
    print()
    print("目录结构（每个种子包）：")
    print("  MJ{主题}批量生图_种子包_v2.0/")
    print("  ├── MJ{主题}批量生图_v2.0.pyw    <- 主程序源码")
    print("  ├── MJ{主题}批量生图_v2.0.spec   <- PyInstaller 打包配置")
    print("  ├── app_icon.ico")
    print("  ├── 使用说明.md")
    print("  ├── themes/")
    print("  │   └── {主题}.json              <- 专属预设配置")
    print("  └── dist/")
    print("      ├── themes/")
    print("      │   └── {主题}.json          <- exe运行时读取")
    print("      ├── output/                  <- 生图结果")
    print("      └── 总览HTML/                <- HTML报告")
    print()
    print("打包为 exe：")
    print("  cd MJ{主题}批量生图_种子包_v2.0")
    print("  pip install pyinstaller pillow requests")
    print("  pyinstaller MJ{主题}批量生图_v2.0.spec")


if __name__ == "__main__":
    build_all()
