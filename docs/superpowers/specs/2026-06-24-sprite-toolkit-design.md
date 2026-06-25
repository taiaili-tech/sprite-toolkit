# Sprite Toolkit 设计文档

**日期：** 2026-06-24  
**状态：** 已批准

---

## 概述

一个纯本地图像处理工具，打包为**单个 HTML 文件**，双击即可在浏览器中使用，无需安装任何软件或服务器。面向有图像素材处理需求的设计师/同事，发给对方一个文件即可使用。

不调用 AI，不做语义识别，不联网。

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 框架 | Vue 3 (Options API / Composition API) |
| 构建 | Vite + `vite-plugin-singlefile`（输出单 HTML） |
| GIF 解码 | `gifuct-js`（纯 JS，无 Worker 限制） |
| GIF 编码 | `gifenc`（纯 JS，无 Worker，`file://` 协议兼容） |
| ZIP 打包 | `jszip` |
| 样式 | 原生 CSS（浅色简洁风，无外部 UI 框架） |

---

## 交付形态

- 开发：`npm run dev` 本地调试
- 发布：`npm run build` → `dist/index.html`（单文件，双击即用）
- 发给同事：直接把 `dist/index.html` 发过去

---

## 项目结构

```
sprite-toolkit/
├── src/
│   ├── main.js                  ← Vue 入口
│   ├── App.vue                  ← 主布局 + Tab 导航
│   ├── components/
│   │   ├── GridCutter.vue       ← 功能1：静态宫格裁切
│   │   ├── GifToSprite.vue      ← 功能2：GIF → 精灵图
│   │   ├── SpriteToGif.vue      ← 功能3：精灵图 → GIF
│   │   └── GifGridCut.vue       ← 功能4：GIF 宫格裁切
│   └── utils/
│       ├── gifDecoder.js        ← gifuct-js 封装：GIF → 帧数组
│       ├── gifEncoder.js        ← gifenc 封装：帧数组 → GIF Blob
│       ├── canvasCrop.js        ← Canvas 裁切工具函数
│       └── zipHelper.js         ← jszip 封装：文件列表 → ZIP 下载
├── index.html
├── package.json
└── vite.config.js
```

---

## 功能 1：静态宫格裁切（GridCutter）

**输入：** PNG / JPG / WebP / GIF（取第一帧）

**配置：**
- 预设按钮：2×2、3×3（一键点选）
- 自定义：行数输入框 + 列数输入框
- 内边距：可选 px 值（默认 0）

**预览：** 上传后在 Canvas 上叠加网格线，显示每格尺寸（像素）

**输出：** ZIP 文件，内含 `r{row}c{col}.png` 命名的单格图片
- 示例：`r1c1.png`、`r1c2.png`、`r2c1.png`…
- 原图不修改、不删除

**边界情况：**
- 图片尺寸不能被行列数整除时：截取整数部分，丢弃余数像素（不拉伸）
- GIF 输入：只取第一帧处理

---

## 功能 2：GIF → 精灵图（GifToSprite）

**输入：** GIF 文件

**配置：**
- 每行最多列数（默认 8，可调）
- 背景色：透明 / 纯色（默认透明）

**预览：**
- 左侧：原 GIF 动画循环播放（Canvas requestAnimationFrame）
- 右侧：精灵图排版预览（含网格辅助线）
- 显示：帧总数、帧尺寸、预计精灵图尺寸

**输出：** ZIP 包含：
1. `spritesheet.png` — 精灵图
2. `metadata.json` — 格式如下：
```json
{
  "frameCount": 12,
  "frameWidth": 64,
  "frameHeight": 64,
  "cols": 8,
  "rows": 2,
  "delays": [100, 100, 100, ...],
  "loopCount": 0,
  "originalWidth": 64,
  "originalHeight": 64
}
```

---

## 功能 3：精灵图 → GIF（SpriteToGif）

**输入：**
- 精灵图 PNG（必须）
- `metadata.json`（可选拖入，自动填参）

**配置：**
- 列数、行数（整数输入）
- 帧速 FPS（默认 10）
- 内边距 px（默认 0，与生成时一致）
- 帧顺序：左→右→下（默认，唯一选项，P0 不做自定义）

**逻辑：**
- 检测到 metadata.json 拖入后，自动填入 cols/rows/delays，并在输入框旁标注「来自 metadata」
- FPS 由 `delays` 数组均值反算（`Math.round(1000 / avgDelay)`）

**预览：** Canvas 实时动画，上传/调参后立即刷新

**输出：** 单个 `animation.gif` 下载

---

## 功能 4：GIF 宫格裁切（GifGridCut）

**输入：** GIF（每帧都是宫格布局）

**配置：** 行数 × 列数

**预览：** 第一帧静图 + 网格叠加线

**处理逻辑：**
1. 解码所有帧 → 帧数组
2. 对每一格位置 (r, c)：从所有帧裁出该位置 → 组成新帧数组 → 编码为独立 GIF
3. 新 GIF 保留原始每帧时长（`delays` 数组）

**输出：** ZIP，内含 `r{row}c{col}.gif` 命名的独立 GIF
- 示例：一张 3×3 的 GIF 表情包 → 解出 9 个独立 GIF

---

## UI 规范

- 风格：浅色、简洁，参考 moeblack.github.io/WebTools/
- 顶部 Tab 导航，4 个工具切换
- 上传区：虚线边框拖拽区，支持 click 选文件 + drag & drop
- 操作按钮：主色 `#4f46e5`（靛蓝），处理中显示 loading 状态
- 错误提示：红色行内提示，不用弹窗
- 移动端：不做响应式（工具类，默认桌面使用）

---

## 数据流

```
用户上传文件
    ↓
FileReader / ArrayBuffer
    ↓
gifDecoder.js (gifuct-js) 或 Image + Canvas
    ↓
处理逻辑（裁切 / 排版 / 编码）
    ↓
gifEncoder.js (gifenc) 或 Canvas.toBlob('image/png')
    ↓
zipHelper.js (jszip) 打包
    ↓
<a download> 触发浏览器下载
```

全程不离开浏览器，无网络请求。

---

## 不在 P0 范围内

- 自定义帧顺序（精灵图→GIF）
- 批量多文件同时处理
- 移动端适配
- 暗色模式
- 撤销/重做
