# MJ巨构批量生图 v2.0

> 主题关键词：巨构建筑

## 快速开始

```bash
# 设置 API Key
set KUNPO_API_KEY=your_key_here

# 查看预设选项
python run.py --list-presets

# 文生图（从预设生成）
python run.py --mode txt2img --struct 0 --light 0 --mood 0 --count 3

# 自由创作（描述需求 → AI 生成30个方向）
python run.py --mode free --desc "我要一张巨构建筑风格图" --select 1,3,5

# 图生图（三层参考图）
python run.py --mode img2img --style 风格图.jpg --subject 主体图.jpg

# 自动批量（文件夹图片自动选材）
python run.py --mode auto --folder ./refs --batches 3

# 启动 API Server（默认端口 8000）
python run.py --server --port 8000
```

## 预设数量

| 类型 | 数量 |
|------|------|
| 结构预设 | 12 个 |
| 光效预设 | 10 个 |
| 情绪预设 | 8 个 |

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
| GET  | `/status/{task_id}` | 查询任务状态 |

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
