# Sprite Toolkit 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个打包为单 HTML 文件的纯前端图像处理工具，支持静态宫格裁切、GIF↔精灵图互转、GIF 宫格裁切，双击即可在浏览器中使用。

**Architecture:** Vue 3 + Vite 单页应用，通过 `vite-plugin-singlefile` 输出单个自包含 HTML 文件。GIF 处理用纯 JS 库（gifuct-js 解码、gifenc 编码），不使用 Web Worker，确保 `file://` 协议下正常运行。

**Tech Stack:** Vue 3, Vite, vite-plugin-singlefile, gifuct-js, gifenc, jszip

---

## Task 1：项目脚手架

**Files:**
- Create: `sprite-toolkit/package.json`
- Create: `sprite-toolkit/vite.config.js`
- Create: `sprite-toolkit/index.html`
- Create: `sprite-toolkit/src/main.js`

- [ ] **Step 1: 在项目根目录创建 sprite-toolkit 文件夹并初始化**

```bash
cd "C:\Users\lf265601\Desktop\临时\MJ批量生图_引擎"
mkdir sprite-toolkit
cd sprite-toolkit
npm create vite@latest . -- --template vue
```

提示覆盖时选 Yes。

- [ ] **Step 2: 安装依赖**

```bash
cd "C:\Users\lf265601\Desktop\临时\MJ批量生图_引擎\sprite-toolkit"
npm install
npm install gifuct-js gifenc jszip
npm install -D vite-plugin-singlefile
```

- [ ] **Step 3: 配置 vite.config.js**

将 `vite.config.js` 改为：

```js
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { viteSingleFile } from 'vite-plugin-singlefile'

export default defineConfig({
  plugins: [vue(), viteSingleFile()],
  build: {
    target: 'esnext',
    assetsInlineLimit: 100000000,
    cssCodeSplit: false,
  },
})
```

- [ ] **Step 4: 清空 Vite 模板默认文件**

删除 `src/components/HelloWorld.vue`、`src/assets/vue.svg`、`public/vite.svg`。
将 `src/style.css` 内容替换为空文件（后续 Task 2 会写全局样式）。

- [ ] **Step 5: 验证构建能运行**

```bash
cd "C:\Users\lf265601\Desktop\临时\MJ批量生图_引擎\sprite-toolkit"
npm run dev
```

Expected: 浏览器打开 `http://localhost:5173`，显示空白页无报错。

- [ ] **Step 6: 验证单文件打包**

```bash
npm run build
```

Expected: `dist/` 目录下只有 `index.html` 一个文件，大小约几百 KB。

- [ ] **Step 7: Commit**

```bash
git add sprite-toolkit/
git commit -m "feat: scaffold sprite-toolkit vue3+vite project"
```

---

## Task 2：工具函数层

**Files:**
- Create: `sprite-toolkit/src/utils/gifDecoder.js`
- Create: `sprite-toolkit/src/utils/gifEncoder.js`
- Create: `sprite-toolkit/src/utils/canvasCrop.js`
- Create: `sprite-toolkit/src/utils/zipHelper.js`

- [ ] **Step 1: 写 gifDecoder.js**

```js
// src/utils/gifDecoder.js
import { parseGIF, decompressFrames } from 'gifuct-js'

/**
 * 解码 GIF ArrayBuffer，返回帧信息数组
 * @param {ArrayBuffer} buffer
 * @returns {Promise<{frames: DecodedFrame[], width: number, height: number, loopCount: number}>}
 *
 * DecodedFrame: { imageData: ImageData, delay: number }
 */
export async function decodeGif(buffer) {
  const gif = parseGIF(buffer)
  const frames = decompressFrames(gif, true)

  const width = gif.lsd.width
  const height = gif.lsd.height
  const loopCount = gif.application?.NETSCAPE?.[0] ?? 0

  // 将每帧转为 ImageData（完整画布尺寸）
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')

  const result = []
  for (const frame of frames) {
    // 处理 disposal 方法：简单实现，每帧覆盖绘制
    const imageData = ctx.createImageData(frame.dims.width, frame.dims.height)
    imageData.data.set(frame.patch)

    // 绘制到完整画布
    ctx.putImageData(imageData, frame.dims.left, frame.dims.top)

    // 截取完整画布快照
    const fullImageData = ctx.getImageData(0, 0, width, height)
    result.push({
      imageData: fullImageData,
      delay: frame.delay || 100,
    })
  }

  return { frames: result, width, height, loopCount }
}
```

- [ ] **Step 2: 写 gifEncoder.js**

```js
// src/utils/gifEncoder.js
import { GIFEncoder, quantize, applyPalette } from 'gifenc'

/**
 * 将帧数组编码为 GIF Blob
 * @param {Array<{imageData: ImageData, delay: number}>} frames
 * @param {number} width
 * @param {number} height
 * @param {number} loopCount - 0 = 无限循环
 * @returns {Blob}
 */
export function encodeGif(frames, width, height, loopCount = 0) {
  const encoder = GIFEncoder()

  for (const { imageData, delay } of frames) {
    const { data } = imageData
    // 转为 Uint8Array RGB(A) 数组
    const pixels = new Uint8ClampedArray(data.buffer)
    const palette = quantize(pixels, 256, { format: 'rgba4444' })
    const index = applyPalette(pixels, palette, 'rgba4444')

    encoder.writeFrame(index, width, height, {
      palette,
      delay,
      repeat: loopCount,
    })
  }

  encoder.finish()
  const bytes = encoder.bytes()
  return new Blob([bytes], { type: 'image/gif' })
}
```

- [ ] **Step 3: 写 canvasCrop.js**

```js
// src/utils/canvasCrop.js

/**
 * 从 ImageBitmap 或 HTMLImageElement 裁出一个矩形区域，返回 PNG Blob
 * @param {ImageBitmap|HTMLImageElement} source
 * @param {number} x
 * @param {number} y
 * @param {number} w
 * @param {number} h
 * @returns {Promise<Blob>}
 */
export function cropToBlob(source, x, y, w, h) {
  const canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = h
  const ctx = canvas.getContext('2d')
  ctx.drawImage(source, x, y, w, h, 0, 0, w, h)
  return new Promise(resolve => canvas.toBlob(resolve, 'image/png'))
}

/**
 * 从 ImageData 裁出一个矩形区域，返回新的 ImageData
 * @param {ImageData} imageData - 完整帧 ImageData
 * @param {number} srcWidth - 原帧宽度
 * @param {number} x
 * @param {number} y
 * @param {number} w
 * @param {number} h
 * @returns {ImageData}
 */
export function cropImageData(imageData, srcWidth, x, y, w, h) {
  const canvas = document.createElement('canvas')
  canvas.width = srcWidth
  canvas.height = imageData.height || Math.ceil(imageData.data.length / 4 / srcWidth)
  const ctx = canvas.getContext('2d')
  ctx.putImageData(imageData, 0, 0)

  const out = document.createElement('canvas')
  out.width = w
  out.height = h
  const outCtx = out.getContext('2d')
  outCtx.drawImage(canvas, x, y, w, h, 0, 0, w, h)
  return outCtx.getImageData(0, 0, w, h)
}

/**
 * 将 File / Blob 转为 HTMLImageElement（等待 load）
 * @param {File|Blob} file
 * @returns {Promise<HTMLImageElement>}
 */
export function fileToImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => { URL.revokeObjectURL(url); resolve(img) }
    img.onerror = reject
    img.src = url
  })
}

/**
 * 将 File 读取为 ArrayBuffer
 * @param {File} file
 * @returns {Promise<ArrayBuffer>}
 */
export function fileToBuffer(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = e => resolve(e.target.result)
    reader.onerror = reject
    reader.readAsArrayBuffer(file)
  })
}
```

- [ ] **Step 4: 写 zipHelper.js**

```js
// src/utils/zipHelper.js
import JSZip from 'jszip'

/**
 * 打包多个文件并触发浏览器下载
 * @param {Array<{name: string, blob: Blob}>} files
 * @param {string} zipName - 下载文件名，含 .zip
 */
export async function downloadAsZip(files, zipName) {
  const zip = new JSZip()
  for (const { name, blob } of files) {
    zip.file(name, blob)
  }
  const content = await zip.generateAsync({ type: 'blob' })
  triggerDownload(content, zipName)
}

/**
 * 触发浏览器下载单个 Blob
 * @param {Blob} blob
 * @param {string} filename
 */
export function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
```

- [ ] **Step 5: 验证 utils 可 import（无报错）**

在 `src/main.js` 顶部临时加入：
```js
import './utils/gifDecoder.js'
import './utils/gifEncoder.js'
import './utils/canvasCrop.js'
import './utils/zipHelper.js'
```
运行 `npm run dev`，控制台无报错后删除这四行。

- [ ] **Step 6: Commit**

```bash
git add sprite-toolkit/src/utils/
git commit -m "feat: add gif decode/encode, crop, zip utility modules"
```

---

## Task 3：主布局 + Tab 导航

**Files:**
- Modify: `sprite-toolkit/src/style.css`
- Modify: `sprite-toolkit/src/App.vue`

- [ ] **Step 1: 写全局样式 style.css**

```css
/* src/style.css */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: #f8f9fa;
  color: #1a1a2e;
  min-height: 100vh;
}

.app-header {
  background: #fff;
  border-bottom: 1px solid #e2e8f0;
  padding: 0 24px;
}

.app-title {
  font-size: 18px;
  font-weight: 700;
  color: #1a1a2e;
  padding: 16px 0 0;
}

.tab-nav {
  display: flex;
  gap: 0;
  margin-top: 12px;
}

.tab-btn {
  padding: 10px 20px;
  border: none;
  background: none;
  cursor: pointer;
  font-size: 14px;
  color: #64748b;
  border-bottom: 2px solid transparent;
  transition: color 0.15s, border-color 0.15s;
}

.tab-btn:hover { color: #4f46e5; }
.tab-btn.active { color: #4f46e5; border-bottom-color: #4f46e5; font-weight: 600; }

.app-body { padding: 32px 24px; max-width: 960px; margin: 0 auto; }

/* 上传区 */
.upload-zone {
  border: 2px dashed #cbd5e1;
  border-radius: 12px;
  padding: 40px;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  background: #fff;
}
.upload-zone:hover, .upload-zone.dragover {
  border-color: #4f46e5;
  background: #f0f0ff;
}
.upload-zone input[type="file"] { display: none; }
.upload-hint { font-size: 13px; color: #94a3b8; margin-top: 8px; }

/* 控件 */
.form-row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin: 16px 0; }
.form-label { font-size: 13px; color: #475569; min-width: 64px; }
.form-input {
  width: 72px; padding: 6px 10px; border: 1px solid #cbd5e1;
  border-radius: 6px; font-size: 14px; text-align: center;
}
.form-input:focus { outline: 2px solid #4f46e5; border-color: transparent; }

.preset-btn {
  padding: 6px 14px; border: 1px solid #cbd5e1; border-radius: 6px;
  background: #fff; cursor: pointer; font-size: 13px; color: #475569;
  transition: all 0.15s;
}
.preset-btn:hover, .preset-btn.active {
  border-color: #4f46e5; color: #4f46e5; background: #f0f0ff;
}

.btn-primary {
  padding: 10px 24px; background: #4f46e5; color: #fff;
  border: none; border-radius: 8px; cursor: pointer; font-size: 14px;
  font-weight: 600; transition: background 0.15s;
}
.btn-primary:hover { background: #4338ca; }
.btn-primary:disabled { background: #a5b4fc; cursor: not-allowed; }

.error-msg { color: #ef4444; font-size: 13px; margin-top: 8px; }
.info-msg { color: #64748b; font-size: 13px; margin-top: 8px; }

/* 预览 canvas */
.preview-wrap {
  margin-top: 20px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 16px;
  overflow: auto;
}
.preview-wrap canvas { display: block; max-width: 100%; }
.preview-label { font-size: 12px; color: #94a3b8; margin-bottom: 8px; }

.meta-badge {
  display: inline-block; font-size: 11px; background: #e0e7ff;
  color: #4f46e5; padding: 2px 8px; border-radius: 4px; margin-left: 6px;
}
```

- [ ] **Step 2: 写 App.vue**

```vue
<!-- src/App.vue -->
<template>
  <div>
    <header class="app-header">
      <div class="app-title">🖼 Sprite Toolkit</div>
      <nav class="tab-nav">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          class="tab-btn"
          :class="{ active: activeTab === tab.id }"
          @click="activeTab = tab.id"
        >{{ tab.label }}</button>
      </nav>
    </header>
    <main class="app-body">
      <GridCutter   v-if="activeTab === 'grid'"      />
      <GifToSprite  v-if="activeTab === 'gif2sprite'" />
      <SpriteToGif  v-if="activeTab === 'sprite2gif'" />
      <GifGridCut   v-if="activeTab === 'gifgrid'"   />
    </main>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import GridCutter  from './components/GridCutter.vue'
import GifToSprite from './components/GifToSprite.vue'
import SpriteToGif from './components/SpriteToGif.vue'
import GifGridCut  from './components/GifGridCut.vue'

const tabs = [
  { id: 'grid',       label: '宫格裁切' },
  { id: 'gif2sprite', label: 'GIF → 精灵图' },
  { id: 'sprite2gif', label: '精灵图 → GIF' },
  { id: 'gifgrid',    label: 'GIF 宫格裁切' },
]
const activeTab = ref('grid')
</script>
```

- [ ] **Step 3: 创建 4 个占位组件**

分别创建以下文件，内容相同（只改标题文字）：

`src/components/GridCutter.vue`：
```vue
<template><div><h2>宫格裁切</h2><p>开发中…</p></div></template>
```
同理创建 `GifToSprite.vue`、`SpriteToGif.vue`、`GifGridCut.vue`。

- [ ] **Step 4: 验证 Tab 导航**

运行 `npm run dev`，切换 Tab 页面，4 个占位标题正确显示，控制台无报错。

- [ ] **Step 5: Commit**

```bash
git add sprite-toolkit/src/
git commit -m "feat: add app layout with tab navigation and global styles"
```

---

## Task 4：功能 1 — 静态宫格裁切（GridCutter.vue）

**Files:**
- Modify: `sprite-toolkit/src/components/GridCutter.vue`

- [ ] **Step 1: 实现完整组件**

```vue
<!-- src/components/GridCutter.vue -->
<template>
  <div>
    <h2 style="font-size:20px;font-weight:700;margin-bottom:20px;">宫格裁切</h2>

    <!-- 上传区 -->
    <div
      class="upload-zone"
      :class="{ dragover: isDragging }"
      @click="$refs.fileInput.click()"
      @dragover.prevent="isDragging = true"
      @dragleave="isDragging = false"
      @drop.prevent="onDrop"
    >
      <input ref="fileInput" type="file" accept="image/*" @change="onFileChange" />
      <div>{{ file ? file.name : '点击或拖入图片（PNG / JPG / WebP / GIF）' }}</div>
      <div class="upload-hint">GIF 只取第一帧</div>
    </div>

    <!-- 配置 -->
    <div class="form-row" style="margin-top:20px;">
      <span class="form-label">快速预设</span>
      <button class="preset-btn" :class="{active: rows===2&&cols===2}" @click="setPreset(2,2)">2×2</button>
      <button class="preset-btn" :class="{active: rows===3&&cols===3}" @click="setPreset(3,3)">3×3</button>
    </div>
    <div class="form-row">
      <span class="form-label">行 × 列</span>
      <input class="form-input" type="number" v-model.number="rows" min="1" max="20" />
      <span style="color:#94a3b8;">×</span>
      <input class="form-input" type="number" v-model.number="cols" min="1" max="20" />
    </div>

    <div v-if="error" class="error-msg">{{ error }}</div>

    <!-- 预览 -->
    <div v-if="imgSrc" class="preview-wrap">
      <div class="preview-label">预览（每格 {{ cellW }}×{{ cellH }} px）</div>
      <canvas ref="previewCanvas"></canvas>
    </div>

    <div style="margin-top:20px;">
      <button class="btn-primary" :disabled="!imgSrc || processing" @click="doProcess">
        {{ processing ? '处理中…' : '裁切并下载 ZIP' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, computed, nextTick } from 'vue'
import { cropToBlob, fileToImage } from '../utils/canvasCrop.js'
import { downloadAsZip } from '../utils/zipHelper.js'

const fileInput = ref(null)
const previewCanvas = ref(null)
const file = ref(null)
const imgEl = ref(null)
const isDragging = ref(false)
const rows = ref(3)
const cols = ref(3)
const error = ref('')
const processing = ref(false)
const imgSrc = ref('')

const cellW = computed(() => imgEl.value ? Math.floor(imgEl.value.naturalWidth / cols.value) : 0)
const cellH = computed(() => imgEl.value ? Math.floor(imgEl.value.naturalHeight / rows.value) : 0)

function setPreset(r, c) { rows.value = r; cols.value = c }

async function loadFile(f) {
  error.value = ''
  file.value = f
  try {
    imgEl.value = await fileToImage(f)
    imgSrc.value = URL.createObjectURL(f)
    await nextTick()
    drawPreview()
  } catch (e) {
    error.value = '图片加载失败：' + e.message
  }
}

function onFileChange(e) { if (e.target.files[0]) loadFile(e.target.files[0]) }
function onDrop(e) { const f = e.dataTransfer.files[0]; if (f) loadFile(f) }

watch([rows, cols], () => { if (imgEl.value) drawPreview() })

function drawPreview() {
  const canvas = previewCanvas.value
  if (!canvas || !imgEl.value) return
  const img = imgEl.value
  const MAX = 600
  const scale = Math.min(1, MAX / Math.max(img.naturalWidth, img.naturalHeight))
  canvas.width = img.naturalWidth * scale
  canvas.height = img.naturalHeight * scale
  const ctx = canvas.getContext('2d')
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height)

  // 画网格线
  ctx.strokeStyle = 'rgba(79,70,229,0.7)'
  ctx.lineWidth = 1
  const cw = canvas.width / cols.value
  const ch = canvas.height / rows.value
  for (let r = 1; r < rows.value; r++) {
    ctx.beginPath(); ctx.moveTo(0, r * ch); ctx.lineTo(canvas.width, r * ch); ctx.stroke()
  }
  for (let c = 1; c < cols.value; c++) {
    ctx.beginPath(); ctx.moveTo(c * cw, 0); ctx.lineTo(c * cw, canvas.height); ctx.stroke()
  }
}

async function doProcess() {
  if (!imgEl.value) return
  error.value = ''
  processing.value = true
  try {
    const img = imgEl.value
    const cw = Math.floor(img.naturalWidth / cols.value)
    const ch = Math.floor(img.naturalHeight / rows.value)
    const files = []
    for (let r = 0; r < rows.value; r++) {
      for (let c = 0; c < cols.value; c++) {
        const blob = await cropToBlob(img, c * cw, r * ch, cw, ch)
        files.push({ name: `r${r + 1}c${c + 1}.png`, blob })
      }
    }
    await downloadAsZip(files, 'grid_cut.zip')
  } catch (e) {
    error.value = '处理失败：' + e.message
  } finally {
    processing.value = false
  }
}
</script>
```

- [ ] **Step 2: 验证功能**

运行 `npm run dev`，上传一张 PNG：
- 预览显示网格线
- 切换 2×2 / 3×3 预设后网格更新
- 点击「裁切并下载 ZIP」→ 浏览器下载 `grid_cut.zip`
- 解压后图片数量 = rows × cols，尺寸正确

- [ ] **Step 3: Commit**

```bash
git add sprite-toolkit/src/components/GridCutter.vue
git commit -m "feat: implement static grid cutter with zip download"
```

---

## Task 5：功能 2 — GIF → 精灵图（GifToSprite.vue）

**Files:**
- Modify: `sprite-toolkit/src/components/GifToSprite.vue`

- [ ] **Step 1: 实现完整组件**

```vue
<!-- src/components/GifToSprite.vue -->
<template>
  <div>
    <h2 style="font-size:20px;font-weight:700;margin-bottom:20px;">GIF → 精灵图</h2>

    <div
      class="upload-zone"
      :class="{ dragover: isDragging }"
      @click="$refs.fileInput.click()"
      @dragover.prevent="isDragging = true"
      @dragleave="isDragging = false"
      @drop.prevent="onDrop"
    >
      <input ref="fileInput" type="file" accept=".gif,image/gif" @change="onFileChange" />
      <div>{{ file ? file.name : '点击或拖入 GIF 动画' }}</div>
    </div>

    <div v-if="error" class="error-msg">{{ error }}</div>

    <div v-if="decoded">
      <div class="form-row" style="margin-top:20px;">
        <span class="form-label">最大列数</span>
        <input class="form-input" type="number" v-model.number="maxCols" min="1" max="32" />
      </div>
      <div class="info-msg">
        帧数：{{ decoded.frames.length }} &nbsp;|&nbsp;
        帧尺寸：{{ decoded.width }}×{{ decoded.height }} px &nbsp;|&nbsp;
        精灵图：{{ spriteW }}×{{ spriteH }} px
      </div>

      <div style="display:flex;gap:24px;flex-wrap:wrap;margin-top:20px;">
        <div class="preview-wrap" style="flex:1;min-width:200px;">
          <div class="preview-label">原 GIF 预览</div>
          <canvas ref="gifPreview"></canvas>
        </div>
        <div class="preview-wrap" style="flex:2;min-width:300px;">
          <div class="preview-label">精灵图预览</div>
          <canvas ref="spritePreview"></canvas>
        </div>
      </div>

      <div style="margin-top:20px;">
        <button class="btn-primary" :disabled="processing" @click="doExport">
          {{ processing ? '生成中…' : '下载精灵图 + metadata.json (ZIP)' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { decodeGif } from '../utils/gifDecoder.js'
import { fileToBuffer } from '../utils/canvasCrop.js'
import { downloadAsZip } from '../utils/zipHelper.js'

const fileInput = ref(null)
const gifPreview = ref(null)
const spritePreview = ref(null)
const file = ref(null)
const isDragging = ref(false)
const error = ref('')
const processing = ref(false)
const decoded = ref(null)
const maxCols = ref(8)
let animFrameId = null

const actualCols = computed(() => {
  if (!decoded.value) return 0
  return Math.min(maxCols.value, decoded.value.frames.length)
})
const actualRows = computed(() => {
  if (!decoded.value) return 0
  return Math.ceil(decoded.value.frames.length / actualCols.value)
})
const spriteW = computed(() => decoded.value ? decoded.value.width * actualCols.value : 0)
const spriteH = computed(() => decoded.value ? decoded.value.height * actualRows.value : 0)

async function loadFile(f) {
  error.value = ''
  file.value = f
  if (animFrameId) { cancelAnimationFrame(animFrameId); animFrameId = null }
  try {
    const buffer = await fileToBuffer(f)
    decoded.value = await decodeGif(buffer)
    await nextTick()
    startGifPreview()
    drawSpritePreview()
  } catch (e) {
    error.value = 'GIF 解析失败：' + e.message
  }
}

function onFileChange(e) { if (e.target.files[0]) loadFile(e.target.files[0]) }
function onDrop(e) { const f = e.dataTransfer.files[0]; if (f) loadFile(f) }

watch(maxCols, () => { if (decoded.value) drawSpritePreview() })

function startGifPreview() {
  const canvas = gifPreview.value
  if (!canvas || !decoded.value) return
  const { frames, width, height } = decoded.value
  canvas.width = width; canvas.height = height
  const ctx = canvas.getContext('2d')
  let i = 0
  let last = 0
  function tick(now) {
    const delay = frames[i].delay
    if (now - last >= delay) {
      ctx.putImageData(frames[i].imageData, 0, 0)
      i = (i + 1) % frames.length
      last = now
    }
    animFrameId = requestAnimationFrame(tick)
  }
  animFrameId = requestAnimationFrame(tick)
}

function drawSpritePreview() {
  const canvas = spritePreview.value
  if (!canvas || !decoded.value) return
  canvas.width = spriteW.value
  canvas.height = spriteH.value
  const ctx = canvas.getContext('2d')
  const { frames, width, height } = decoded.value
  frames.forEach((frame, i) => {
    const col = i % actualCols.value
    const row = Math.floor(i / actualCols.value)
    ctx.putImageData(frame.imageData, col * width, row * height)
  })
  // 网格辅助线
  ctx.strokeStyle = 'rgba(79,70,229,0.3)'
  ctx.lineWidth = 1
  for (let r = 1; r < actualRows.value; r++) {
    ctx.beginPath(); ctx.moveTo(0, r * height); ctx.lineTo(canvas.width, r * height); ctx.stroke()
  }
  for (let c = 1; c < actualCols.value; c++) {
    ctx.beginPath(); ctx.moveTo(c * width, 0); ctx.lineTo(c * width, canvas.height); ctx.stroke()
  }
}

async function doExport() {
  if (!decoded.value) return
  processing.value = true
  try {
    // 生成精灵图 PNG
    const canvas = document.createElement('canvas')
    canvas.width = spriteW.value; canvas.height = spriteH.value
    const ctx = canvas.getContext('2d')
    const { frames, width, height } = decoded.value
    frames.forEach((frame, i) => {
      const col = i % actualCols.value
      const row = Math.floor(i / actualCols.value)
      ctx.putImageData(frame.imageData, col * width, row * height)
    })
    const pngBlob = await new Promise(r => canvas.toBlob(r, 'image/png'))

    // 生成 metadata.json
    const meta = {
      frameCount: frames.length,
      frameWidth: width,
      frameHeight: height,
      cols: actualCols.value,
      rows: actualRows.value,
      delays: frames.map(f => f.delay),
      loopCount: decoded.value.loopCount,
      originalWidth: width,
      originalHeight: height,
    }
    const metaBlob = new Blob([JSON.stringify(meta, null, 2)], { type: 'application/json' })

    await downloadAsZip(
      [{ name: 'spritesheet.png', blob: pngBlob }, { name: 'metadata.json', blob: metaBlob }],
      'gif_to_sprite.zip'
    )
  } catch (e) {
    error.value = '导出失败：' + e.message
  } finally {
    processing.value = false
  }
}
</script>
```

- [ ] **Step 2: 验证功能**

上传一个 GIF：
- 左侧动画预览正常播放
- 右侧精灵图正确排列
- 下载 ZIP，解压后含 `spritesheet.png` 和 `metadata.json`
- `metadata.json` 中 `frameCount`、`delays`、尺寸字段正确

- [ ] **Step 3: Commit**

```bash
git add sprite-toolkit/src/components/GifToSprite.vue
git commit -m "feat: implement GIF to sprite sheet with metadata.json export"
```

---

## Task 6：功能 3 — 精灵图 → GIF（SpriteToGif.vue）

**Files:**
- Modify: `sprite-toolkit/src/components/SpriteToGif.vue`

- [ ] **Step 1: 实现完整组件**

```vue
<!-- src/components/SpriteToGif.vue -->
<template>
  <div>
    <h2 style="font-size:20px;font-weight:700;margin-bottom:20px;">精灵图 → GIF</h2>

    <!-- 精灵图上传 -->
    <div
      class="upload-zone"
      :class="{ dragover: isDragging }"
      @click="$refs.fileInput.click()"
      @dragover.prevent="isDragging = true"
      @dragleave="isDragging = false"
      @drop.prevent="onDrop"
    >
      <input ref="fileInput" type="file" accept="image/png,image/jpeg" @change="onFileChange" />
      <div>{{ imgFile ? imgFile.name : '点击或拖入精灵图 PNG / JPG' }}</div>
    </div>

    <!-- metadata.json 上传 -->
    <div style="margin-top:12px;">
      <div
        class="upload-zone"
        style="padding:16px;"
        @click="$refs.metaInput.click()"
        @dragover.prevent
        @drop.prevent="onMetaDrop"
      >
        <input ref="metaInput" type="file" accept=".json,application/json" @change="onMetaChange" />
        <div style="font-size:13px;color:#64748b;">
          {{ metaLoaded ? '✓ metadata.json 已载入' : '可选：拖入 metadata.json 自动填参' }}
        </div>
      </div>
    </div>

    <div v-if="error" class="error-msg">{{ error }}</div>

    <div v-if="imgFile" style="margin-top:20px;">
      <div class="form-row">
        <span class="form-label">列数</span>
        <input class="form-input" type="number" v-model.number="cols" min="1" />
        <span v-if="metaLoaded" class="meta-badge">来自 metadata</span>
      </div>
      <div class="form-row">
        <span class="form-label">行数</span>
        <input class="form-input" type="number" v-model.number="rows" min="1" />
        <span v-if="metaLoaded" class="meta-badge">来自 metadata</span>
      </div>
      <div class="form-row">
        <span class="form-label">FPS</span>
        <input class="form-input" type="number" v-model.number="fps" min="1" max="60" />
        <span v-if="metaLoaded" class="meta-badge">来自 metadata</span>
      </div>
      <div class="form-row">
        <span class="form-label">内边距 px</span>
        <input class="form-input" type="number" v-model.number="padding" min="0" />
      </div>
      <div class="info-msg">帧总数：{{ frameCount }}</div>

      <div class="preview-wrap" style="margin-top:20px;">
        <div class="preview-label">动画预览</div>
        <canvas ref="previewCanvas"></canvas>
      </div>

      <div style="margin-top:20px;">
        <button class="btn-primary" :disabled="processing" @click="doExport">
          {{ processing ? '生成中…' : '下载 GIF' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { fileToImage } from '../utils/canvasCrop.js'
import { encodeGif } from '../utils/gifEncoder.js'
import { triggerDownload } from '../utils/zipHelper.js'

const fileInput = ref(null)
const metaInput = ref(null)
const previewCanvas = ref(null)
const imgFile = ref(null)
const imgEl = ref(null)
const isDragging = ref(false)
const error = ref('')
const processing = ref(false)
const cols = ref(8)
const rows = ref(1)
const fps = ref(10)
const padding = ref(0)
const metaLoaded = ref(false)
const metaDelays = ref(null)
let animFrameId = null

const frameCount = computed(() => rows.value * cols.value)
const delay = computed(() => Math.round(1000 / fps.value))

async function loadImg(f) {
  error.value = ''
  imgFile.value = f
  try {
    imgEl.value = await fileToImage(f)
    await nextTick()
    startPreview()
  } catch (e) {
    error.value = '图片加载失败：' + e.message
  }
}

function onFileChange(e) { if (e.target.files[0]) loadImg(e.target.files[0]) }
function onDrop(e) { const f = e.dataTransfer.files[0]; if (f) loadImg(f) }

async function loadMeta(f) {
  try {
    const text = await f.text()
    const meta = JSON.parse(text)
    cols.value = meta.cols ?? cols.value
    rows.value = meta.rows ?? rows.value
    if (meta.delays?.length) {
      metaDelays.value = meta.delays
      const avg = meta.delays.reduce((a, b) => a + b, 0) / meta.delays.length
      fps.value = Math.round(1000 / avg)
    }
    metaLoaded.value = true
  } catch (e) {
    error.value = 'metadata.json 解析失败'
  }
}

function onMetaChange(e) { if (e.target.files[0]) loadMeta(e.target.files[0]) }
function onMetaDrop(e) { const f = e.dataTransfer.files[0]; if (f) loadMeta(f) }

watch([cols, rows, fps, padding], () => { if (imgEl.value) startPreview() })

function getFrames() {
  const img = imgEl.value
  if (!img) return []
  const frameW = Math.floor((img.naturalWidth - padding.value * (cols.value + 1)) / cols.value)
  const frameH = Math.floor((img.naturalHeight - padding.value * (rows.value + 1)) / rows.value)
  const frames = []
  for (let r = 0; r < rows.value; r++) {
    for (let c = 0; c < cols.value; c++) {
      const x = padding.value + c * (frameW + padding.value)
      const y = padding.value + r * (frameH + padding.value)
      const canvas = document.createElement('canvas')
      canvas.width = frameW; canvas.height = frameH
      const ctx = canvas.getContext('2d')
      ctx.drawImage(img, x, y, frameW, frameH, 0, 0, frameW, frameH)
      const d = metaDelays.value?.[r * cols.value + c] ?? delay.value
      frames.push({ imageData: ctx.getImageData(0, 0, frameW, frameH), delay: d })
    }
  }
  return frames
}

function startPreview() {
  if (animFrameId) { cancelAnimationFrame(animFrameId); animFrameId = null }
  const frames = getFrames()
  if (!frames.length) return
  const canvas = previewCanvas.value
  if (!canvas) return
  canvas.width = frames[0].imageData.width
  canvas.height = frames[0].imageData.height
  const ctx = canvas.getContext('2d')
  let i = 0, last = 0
  function tick(now) {
    if (now - last >= frames[i].delay) {
      ctx.putImageData(frames[i].imageData, 0, 0)
      i = (i + 1) % frames.length
      last = now
    }
    animFrameId = requestAnimationFrame(tick)
  }
  animFrameId = requestAnimationFrame(tick)
}

async function doExport() {
  processing.value = true
  error.value = ''
  try {
    const frames = getFrames()
    if (!frames.length) throw new Error('无有效帧')
    const { width, height } = frames[0].imageData
    const blob = encodeGif(frames, width, height, 0)
    triggerDownload(blob, 'animation.gif')
  } catch (e) {
    error.value = '导出失败：' + e.message
  } finally {
    processing.value = false
  }
}
</script>
```

- [ ] **Step 2: 验证功能**

1. 上传精灵图 + 对应 metadata.json → 参数自动填入并标注「来自 metadata」
2. 预览动画正常播放
3. 下载 GIF → 帧数、速度与原 GIF 一致

- [ ] **Step 3: Commit**

```bash
git add sprite-toolkit/src/components/SpriteToGif.vue
git commit -m "feat: implement sprite sheet to GIF converter with metadata support"
```

---

## Task 7：功能 4 — GIF 宫格裁切（GifGridCut.vue）

**Files:**
- Modify: `sprite-toolkit/src/components/GifGridCut.vue`

- [ ] **Step 1: 实现完整组件**

```vue
<!-- src/components/GifGridCut.vue -->
<template>
  <div>
    <h2 style="font-size:20px;font-weight:700;margin-bottom:20px;">GIF 宫格裁切</h2>

    <div
      class="upload-zone"
      :class="{ dragover: isDragging }"
      @click="$refs.fileInput.click()"
      @dragover.prevent="isDragging = true"
      @dragleave="isDragging = false"
      @drop.prevent="onDrop"
    >
      <input ref="fileInput" type="file" accept=".gif,image/gif" @change="onFileChange" />
      <div>{{ file ? file.name : '点击或拖入 GIF（每帧均为宫格布局）' }}</div>
      <div class="upload-hint">例：3×3 动态表情包 → 拆出 9 个独立 GIF</div>
    </div>

    <div v-if="error" class="error-msg">{{ error }}</div>

    <div v-if="decoded">
      <div class="form-row" style="margin-top:20px;">
        <span class="form-label">行 × 列</span>
        <input class="form-input" type="number" v-model.number="rows" min="1" max="10" />
        <span style="color:#94a3b8;">×</span>
        <input class="form-input" type="number" v-model.number="cols" min="1" max="10" />
      </div>
      <div class="info-msg">
        输入帧数：{{ decoded.frames.length }} &nbsp;|&nbsp;
        格子尺寸：{{ cellW }}×{{ cellH }} px &nbsp;|&nbsp;
        输出 GIF 数：{{ rows * cols }}
      </div>

      <div class="preview-wrap" style="margin-top:20px;">
        <div class="preview-label">第一帧 + 网格预览</div>
        <canvas ref="previewCanvas"></canvas>
      </div>

      <div style="margin-top:20px;">
        <button class="btn-primary" :disabled="processing" @click="doProcess">
          {{ processing ? `处理中… (${progress}/${rows*cols})` : `裁切并下载 ZIP（${rows*cols} 个 GIF）` }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { decodeGif } from '../utils/gifDecoder.js'
import { encodeGif } from '../utils/gifEncoder.js'
import { fileToBuffer, cropImageData } from '../utils/canvasCrop.js'
import { downloadAsZip } from '../utils/zipHelper.js'

const fileInput = ref(null)
const previewCanvas = ref(null)
const file = ref(null)
const isDragging = ref(false)
const error = ref('')
const processing = ref(false)
const decoded = ref(null)
const rows = ref(3)
const cols = ref(3)
const progress = ref(0)

const cellW = computed(() => decoded.value ? Math.floor(decoded.value.width / cols.value) : 0)
const cellH = computed(() => decoded.value ? Math.floor(decoded.value.height / rows.value) : 0)

async function loadFile(f) {
  error.value = ''
  file.value = f
  try {
    const buffer = await fileToBuffer(f)
    decoded.value = await decodeGif(buffer)
    await nextTick()
    drawPreview()
  } catch (e) {
    error.value = 'GIF 解析失败：' + e.message
  }
}

function onFileChange(e) { if (e.target.files[0]) loadFile(e.target.files[0]) }
function onDrop(e) { const f = e.dataTransfer.files[0]; if (f) loadFile(f) }

watch([rows, cols], () => { if (decoded.value) drawPreview() })

function drawPreview() {
  const canvas = previewCanvas.value
  if (!canvas || !decoded.value) return
  const { frames, width, height } = decoded.value
  const MAX = 600
  const scale = Math.min(1, MAX / Math.max(width, height))
  canvas.width = width * scale; canvas.height = height * scale
  const ctx = canvas.getContext('2d')
  ctx.putImageData(frames[0].imageData, 0, 0)

  // 缩放绘制
  const tmp = document.createElement('canvas')
  tmp.width = width; tmp.height = height
  tmp.getContext('2d').putImageData(frames[0].imageData, 0, 0)
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  ctx.drawImage(tmp, 0, 0, canvas.width, canvas.height)

  ctx.strokeStyle = 'rgba(79,70,229,0.7)'; ctx.lineWidth = 1
  const cw = canvas.width / cols.value
  const ch = canvas.height / rows.value
  for (let r = 1; r < rows.value; r++) {
    ctx.beginPath(); ctx.moveTo(0, r * ch); ctx.lineTo(canvas.width, r * ch); ctx.stroke()
  }
  for (let c = 1; c < cols.value; c++) {
    ctx.beginPath(); ctx.moveTo(c * cw, 0); ctx.lineTo(c * cw, canvas.height); ctx.stroke()
  }
}

async function doProcess() {
  if (!decoded.value) return
  processing.value = true; progress.value = 0; error.value = ''
  try {
    const { frames, width, height } = decoded.value
    const cw = Math.floor(width / cols.value)
    const ch = Math.floor(height / rows.value)
    const files = []

    for (let r = 0; r < rows.value; r++) {
      for (let c = 0; c < cols.value; c++) {
        const cellFrames = frames.map(frame => ({
          imageData: cropImageData(frame.imageData, width, c * cw, r * ch, cw, ch),
          delay: frame.delay,
        }))
        const blob = encodeGif(cellFrames, cw, ch, decoded.value.loopCount)
        files.push({ name: `r${r + 1}c${c + 1}.gif`, blob })
        progress.value++
        // 让 UI 有机会更新
        await new Promise(resolve => setTimeout(resolve, 0))
      }
    }

    await downloadAsZip(files, 'gif_grid_cut.zip')
  } catch (e) {
    error.value = '处理失败：' + e.message
  } finally {
    processing.value = false
  }
}
</script>
```

- [ ] **Step 2: 验证功能**

上传一个 3×3 动态表情包 GIF：
- 预览第一帧 + 3×3 网格
- 点击处理 → 下载 ZIP，解压后含 9 个 GIF
- 每个 GIF 对应正确的格子位置，动画帧数正确

- [ ] **Step 3: Commit**

```bash
git add sprite-toolkit/src/components/GifGridCut.vue
git commit -m "feat: implement GIF grid cutter outputting N independent GIFs"
```

---

## Task 8：最终打包 + 验收

**Files:**
- No new files

- [ ] **Step 1: 执行生产构建**

```bash
cd "C:\Users\lf265601\Desktop\临时\MJ批量生图_引擎\sprite-toolkit"
npm run build
```

Expected: `dist/index.html` 单文件，无其他文件。

- [ ] **Step 2: 验证单文件可离线使用**

用文件管理器找到 `dist/index.html`，直接双击（使用 `file://` 协议打开），检查：
- 4 个 Tab 切换正常
- 每个功能上传文件后处理正常
- 控制台无 CORS / Worker 报错

- [ ] **Step 3: 检查文件大小**

```bash
(Get-Item "dist\index.html").length / 1KB
```

Expected: < 2000 KB（2MB）。如超过，检查是否有大图片被嵌入。

- [ ] **Step 4: 最终 Commit**

```bash
git add sprite-toolkit/dist/index.html
git commit -m "release: sprite-toolkit v1.0 single-file build"
```

---

## 依赖版本参考

运行 `npm install` 后 `package.json` 中应含：

```json
{
  "dependencies": {
    "gifuct-js": "^2.1.2",
    "gifenc": "^1.0.3",
    "jszip": "^3.10.1",
    "vue": "^3.x"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.x",
    "vite": "^5.x",
    "vite-plugin-singlefile": "^2.x"
  }
}
```
