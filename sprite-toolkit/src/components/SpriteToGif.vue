<!-- src/components/SpriteToGif.vue -->
<template>
  <div>
    <h2 style="font-size:20px;font-weight:700;margin-bottom:20px;">精灵图 → GIF</h2>

    <!-- 上传区 -->
    <div
      class="upload-zone"
      :class="{ dragover: isDragging }"
      @click="fileInput.click()"
      @dragover.prevent="isDragging = true"
      @dragleave="isDragging = false"
      @drop.prevent="onDrop"
    >
      <input ref="fileInput" type="file" accept="image/png,image/jpeg" @change="onFileChange" />
      <div v-if="!currentItem">点击或拖入精灵图 PNG / JPG</div>
      <div v-else style="font-size:13px;">
        {{ currentItem.name }}&nbsp;
        <span style="color:#6366f1;cursor:pointer;text-decoration:underline;" @click.stop="fileInput.click()">重新选择</span>
      </div>
    </div>

    <!-- metadata.json 上传 -->
    <div style="margin-top:12px;">
      <div
        class="upload-zone"
        style="padding:14px;"
        @click="metaInput.click()"
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

    <div v-if="currentItem" style="margin-top:20px;">

      <!-- 第一行：参数输入（紧凑） -->
      <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;margin-bottom:12px;">
        <div class="form-row" style="margin-bottom:0;flex:1;min-width:90px;">
          <span class="form-label tip" title="精灵图横向有几列格子，每列对应一帧">列数 ⓘ</span>
          <input class="form-input" type="number" v-model.number="cols" min="1" max="64" />
          <span v-if="metaLoaded" class="meta-badge">meta</span>
        </div>
        <div class="form-row" style="margin-bottom:0;flex:1;min-width:90px;">
          <span class="form-label tip" title="精灵图纵向有几行格子，每行对应一帧">行数 ⓘ</span>
          <input class="form-input" type="number" v-model.number="rows" min="1" max="64" />
          <span v-if="metaLoaded" class="meta-badge">meta</span>
        </div>
        <div class="form-row" style="margin-bottom:0;flex:1;min-width:90px;">
          <span class="form-label tip" title="GIF 每秒播放的帧数，数值越大动画越快。常用：10（慢）/ 24（流畅）/ 30（快）">FPS ⓘ</span>
          <input class="form-input" type="number" v-model.number="fps" min="1" max="60" />
          <span v-if="metaLoaded" class="meta-badge">meta</span>
        </div>
        <div class="form-row" style="margin-bottom:0;flex:1;min-width:90px;">
          <span class="form-label tip" title="每个格子四周的透明/空白边距（像素）。大多数精灵图没有边距，填 0 即可">内边距 px ⓘ</span>
          <input class="form-input" type="number" v-model.number="padding" min="0" />
        </div>
        <div class="form-row" style="margin-bottom:0;flex:1;min-width:90px;">
          <span class="form-label tip" title="精灵图里实际有多少帧动画。如果最后一行没填满（如 2×8=16格但只有17帧），填入真实数量，多余的空格会自动跳过">实际帧数 ⓘ</span>
          <input
            class="form-input"
            type="number"
            v-model.number="actualFrameCount"
            :min="1"
            :max="rows * cols"
            :placeholder="rows * cols"
          />
        </div>
      </div>

      <!-- 双预览区（左：网格叠加，右：动画） -->
      <div style="display:flex;gap:20px;flex-wrap:wrap;margin-top:4px;">

        <!-- 左：网格预览 + 上方工具栏 -->
        <div style="flex:3;min-width:220px;">
          <!-- 预设工具栏 -->
          <div class="grid-toolbar">
            <button
              v-for="p in gridPresets"
              :key="p.label"
              class="preset-btn"
              :class="{ active: cols === p.cols && rows === p.rows }"
              @click="applyPreset(p)"
            >{{ p.label }}</button>
          </div>

          <!-- 自动识别结果（上传后自动显示） -->
          <div v-if="detectResults.length" class="detect-panel">
            <span style="font-size:11px;color:#1d4ed8;font-weight:600;">自动识别：</span>
            <button
              v-for="d in detectResults"
              :key="d.label"
              class="preset-btn"
              :class="{ active: cols === d.cols && rows === d.rows }"
              @click="applyDetect(d)"
              :title="`每帧 ${d.fw}×${d.fh} px，共 ${d.totalFrames} 格`"
            >{{ d.label }} <span style="font-size:10px;opacity:0.6;">{{d.fw}}×{{d.fh}}</span></button>
          </div>

          <!-- 网格叠加预览 -->
          <div class="preview-wrap" style="margin-top:8px;">
            <div class="preview-label">
              网格预览
              <span style="font-size:11px;font-weight:400;color:#94a3b8;margin-left:4px;">格子对齐即正确</span>
              <span style="margin-left:auto;font-size:11px;color:#64748b;">
                {{ rows }}行 × {{ cols }}列 = {{ rows*cols }} 格，输出 <strong>{{ effectiveFrameCount }}</strong> 帧
                <template v-if="effectiveFrameCount < rows*cols">（跳过末尾 {{ rows*cols - effectiveFrameCount }} 格）</template>
              </span>
            </div>
            <canvas ref="gridCanvas" style="max-width:100%;"></canvas>
          </div>
        </div>

        <!-- 右：动画预览 -->
        <div style="flex:1;min-width:140px;">
          <div class="preview-wrap">
            <div class="preview-label">动画预览</div>
            <canvas ref="previewCanvas"></canvas>
          </div>
        </div>
      </div>

      <!-- 导出按钮 -->
      <div style="margin-top:16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;">
        <button class="btn-primary" :disabled="processing" @click="doExport">
          {{ processing ? '生成中…' : '下载 GIF' }}
        </button>
        <span v-if="processing" style="font-size:13px;color:#64748b;">{{ progressText }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onUnmounted } from 'vue'
import { fileToImage } from '../utils/canvasCrop.js'
import { encodeGif } from '../utils/gifEncoder.js'
import { triggerDownload, downloadAsZip } from '../utils/zipHelper.js'

const fileInput = ref(null)
const metaInput = ref(null)
const previewCanvas = ref(null)
const gridCanvas = ref(null)

const fileList = ref([])   // [{ name, file, imgEl }] — single item
const currentIdx = ref(0)
const isDragging = ref(false)
const error = ref('')
const processing = ref(false)
const progressText = ref('')

const cols = ref(8)
const rows = ref(2)
const fps = ref(10)
const padding = ref(0)
const actualFrameCount = ref(null)   // null = all cells
const metaLoaded = ref(false)
const metaDelays = ref(null)
const suggestions = ref([])
const detectResults = ref([])

let animFrameId = null

const gridPresets = [
  { label: '1×8', cols: 8, rows: 1 },
  { label: '2×8', cols: 8, rows: 2 },
  { label: '4×4', cols: 4, rows: 4 },
  { label: '3×3', cols: 3, rows: 3 },
  { label: '2×4', cols: 4, rows: 2 },
  { label: '4×2', cols: 2, rows: 4 },
  { label: '2×2', cols: 2, rows: 2 },
  { label: '8×1', cols: 1, rows: 8 },
]

const currentItem = computed(() => fileList.value[currentIdx.value] ?? null)

const effectiveFrameCount = computed(() => {
  const total = rows.value * cols.value
  const n = actualFrameCount.value
  if (!n || n >= total) return total
  return Math.max(1, n)
})

const delay = computed(() => Math.round(1000 / fps.value))

onUnmounted(() => { if (animFrameId) cancelAnimationFrame(animFrameId) })

// ── file loading ─────────────────────────────────────────────────────────────

async function loadFile(f) {
  error.value = ''
  suggestions.value = []
  if (!f.type.startsWith('image/')) return
  const imgEl = await fileToImage(f).catch(e => { error.value = '图片加载失败：' + e.message; return null })
  if (!imgEl) return
  fileList.value = [{ name: f.name, file: f, imgEl }]
  currentIdx.value = 0
  await nextTick()
  autoDetect()
  drawGridPreview()
  startPreview()
}

function onFileChange(e) { if (e.target.files[0]) loadFile(e.target.files[0]) }
function onDrop(e) { isDragging.value = false; const f = e.dataTransfer.files[0]; if (f) loadFile(f) }

// ── metadata ─────────────────────────────────────────────────────────────────

async function loadMeta(f) {
  try {
    const text = await f.text()
    const meta = JSON.parse(text)
    if (meta.cols) cols.value = meta.cols
    if (meta.rows) rows.value = meta.rows
    if (meta.frameCount) actualFrameCount.value = meta.frameCount
    if (meta.delays?.length) {
      metaDelays.value = meta.delays
      const avg = meta.delays.reduce((a, b) => a + b, 0) / meta.delays.length
      fps.value = Math.round(1000 / avg)
    }
    metaLoaded.value = true
  } catch (e) {
    error.value = 'metadata.json 解析失败：' + e.message
  }
}

function onMetaChange(e) { if (e.target.files[0]) loadMeta(e.target.files[0]) }
function onMetaDrop(e) { const f = e.dataTransfer.files[0]; if (f) loadMeta(f) }

// ── grid presets & auto-detect ───────────────────────────────────────────────

function applyPreset(p) {
  cols.value = p.cols
  rows.value = p.rows
}

function applyDetect(d) {
  applyPreset(d)
}

function getDivisors(n) {
  const divs = []
  for (let i = 1; i <= n; i++) {
    if (n % i === 0) divs.push(i)
  }
  return divs
}

// Sample pixel variance along potential separator lines to score a grid layout
function pixelScore(pixelData, W, H, c, r) {
  const fw = W / c
  const fh = H / r
  // Sample step: check every Nth pixel to stay fast
  const step = Math.max(1, Math.floor(Math.min(W, H) / 64))

  let totalUniformity = 0
  let checks = 0

  // Vertical separator lines
  for (let ci = 1; ci < c; ci++) {
    const x = Math.round(ci * fw)
    if (x <= 0 || x >= W) continue
    let sumDiff = 0
    let samples = 0
    for (let y = step; y < H; y += step) {
      const i0 = ((y - step) * W + x) * 4
      const i1 = (y * W + x) * 4
      sumDiff += Math.abs(pixelData[i0] - pixelData[i1])
               + Math.abs(pixelData[i0+1] - pixelData[i1+1])
               + Math.abs(pixelData[i0+2] - pixelData[i1+2])
      samples++
    }
    // Low variance along a vertical line = likely a real separator
    totalUniformity += 1 / (1 + sumDiff / (samples * 255))
    checks++
  }

  // Horizontal separator lines
  for (let ri = 1; ri < r; ri++) {
    const y = Math.round(ri * fh)
    if (y <= 0 || y >= H) continue
    let sumDiff = 0
    let samples = 0
    for (let x = step; x < W; x += step) {
      const i0 = (y * W + (x - step)) * 4
      const i1 = (y * W + x) * 4
      sumDiff += Math.abs(pixelData[i0] - pixelData[i1])
               + Math.abs(pixelData[i0+1] - pixelData[i1+1])
               + Math.abs(pixelData[i0+2] - pixelData[i1+2])
      samples++
    }
    totalUniformity += 1 / (1 + sumDiff / (samples * 255))
    checks++
  }

  return checks > 0 ? totalUniformity / checks : 0
}

function autoDetect() {
  const imgEl = currentItem.value?.imgEl
  if (!imgEl) return
  detectResults.value = []
  suggestions.value = []

  const W = imgEl.naturalWidth
  const H = imgEl.naturalHeight
  const commonSizes = new Set([16, 24, 32, 40, 48, 64, 80, 96, 100, 128, 160, 192, 200, 240, 256, 320, 360, 512])

  // Read pixels once into a temp canvas
  const tmp = document.createElement('canvas')
  tmp.width = W; tmp.height = H
  const tctx = tmp.getContext('2d')
  tctx.drawImage(imgEl, 0, 0)
  const pixelData = tctx.getImageData(0, 0, W, H).data

  const wDivs = getDivisors(W)
  const hDivs = getDivisors(H)

  const candidates = []
  for (const c of wDivs) {
    for (const r of hDivs) {
      const fw = W / c
      const fh = H / r
      const totalFrames = r * c
      if (fw < 8 || fh < 8) continue
      if (totalFrames < 2) continue
      if (totalFrames > 256) continue
      if (c === 1 && r === 1) continue

      const squareness = Math.min(fw / fh, fh / fw)
      const sizeBonus = (commonSizes.has(fw) && commonSizes.has(fh)) ? 0.25
        : (commonSizes.has(fw) || commonSizes.has(fh)) ? 0.1 : 0
      // Pixel-level separator uniformity (only needed for grids with separators)
      const pxScore = (c > 1 || r > 1) ? pixelScore(pixelData, W, H, c, r) : 0
      // Final score: pixel consistency carries the most weight
      const score = pxScore * 2 + squareness * 0.5 + sizeBonus

      candidates.push({ cols: c, rows: r, fw, fh, totalFrames, score,
        label: `${r}行×${c}列` })
    }
  }

  candidates.sort((a, b) => b.score - a.score)
  const top = candidates.slice(0, 8)

  if (!top.length) {
    error.value = '未能识别到合理的网格，请手动填写行列数'
    return
  }

  detectResults.value = top
  applyPreset(top[0])
}

function autoSuggest() {
  const n = actualFrameCount.value || (rows.value * cols.value)
  if (!n || n < 1) return
  // Enumerate candidate grids: rows 1..10, cols 1..10
  const candidates = []
  for (let r = 1; r <= 20; r++) {
    for (let c = 1; c <= 32; c++) {
      const total = r * c
      if (total < n) continue
      if (total > n + Math.ceil(n * 0.5)) continue   // at most 50% empty
      const emptyCount = total - n
      const ratio = Math.max(r, c) / Math.min(r, c)
      candidates.push({ rows: r, cols: c, label: `${r}行×${c}列（空${emptyCount}格）`, score: ratio + emptyCount * 0.2 })
    }
  }
  candidates.sort((a, b) => a.score - b.score)
  suggestions.value = candidates.slice(0, 8).map(s => ({ ...s }))
  if (!suggestions.value.length) {
    suggestions.value = [{ rows: 1, cols: n, label: `1行×${n}列` }]
  }
}

// ── frame extraction ──────────────────────────────────────────────────────────

function getFrames(imgEl) {
  if (!imgEl) return []
  const r = rows.value || 1
  const c = cols.value || 1
  const p = padding.value || 0
  const frameW = Math.floor((imgEl.naturalWidth - p * (c + 1)) / c)
  const frameH = Math.floor((imgEl.naturalHeight - p * (r + 1)) / r)
  if (frameW <= 0 || frameH <= 0) return []
  const limit = effectiveFrameCount.value
  const frames = []
  outer: for (let ri = 0; ri < r; ri++) {
    for (let ci = 0; ci < c; ci++) {
      if (frames.length >= limit) break outer
      const x = p + ci * (frameW + p)
      const y = p + ri * (frameH + p)
      const canvas = document.createElement('canvas')
      canvas.width = frameW; canvas.height = frameH
      const ctx = canvas.getContext('2d')
      ctx.drawImage(imgEl, x, y, frameW, frameH, 0, 0, frameW, frameH)
      const frameIndex = frames.length
      const d = metaDelays.value?.[frameIndex] ?? delay.value
      frames.push({ imageData: ctx.getImageData(0, 0, frameW, frameH), delay: d })
    }
  }
  return frames
}

// ── preview ───────────────────────────────────────────────────────────────────

watch(() => currentIdx.value, () => {
  if (currentItem.value?.imgEl) nextTick(() => { autoDetect(); drawGridPreview(); startPreview() })
})
watch([cols, rows, fps, padding, actualFrameCount], () => {
  if (currentItem.value?.imgEl) nextTick(() => { drawGridPreview(); startPreview() })
})

function drawGridPreview() {
  const canvas = gridCanvas.value
  const imgEl = currentItem.value?.imgEl
  if (!canvas || !imgEl) return
  const r = rows.value || 1
  const c = cols.value || 1
  const p = padding.value || 0
  const W = imgEl.naturalWidth
  const H = imgEl.naturalHeight

  // Scale down for display (max 400px wide)
  const scale = Math.min(1, 400 / W)
  canvas.width = Math.round(W * scale)
  canvas.height = Math.round(H * scale)
  const ctx = canvas.getContext('2d')
  ctx.drawImage(imgEl, 0, 0, canvas.width, canvas.height)

  const fw = Math.floor((W - p * (c + 1)) / c) * scale
  const fh = Math.floor((H - p * (r + 1)) / r) * scale
  const ps = p * scale

  // Dim overlay
  ctx.fillStyle = 'rgba(0,0,0,0.25)'
  ctx.fillRect(0, 0, canvas.width, canvas.height)

  // Highlight each frame cell
  const limit = effectiveFrameCount.value
  let count = 0
  for (let ri = 0; ri < r; ri++) {
    for (let ci = 0; ci < c; ci++) {
      const x = ps + ci * (fw + ps)
      const y = ps + ri * (fh + ps)
      if (count < limit) {
        ctx.fillStyle = 'rgba(99,102,241,0.18)'
        ctx.fillRect(x, y, fw, fh)
        ctx.strokeStyle = '#6366f1'
        ctx.lineWidth = 1.5
        ctx.strokeRect(x, y, fw, fh)
        // frame number
        ctx.fillStyle = 'rgba(255,255,255,0.9)'
        ctx.font = `bold ${Math.max(10, Math.min(16, fw * 0.25))}px system-ui`
        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'
        ctx.fillText(count + 1, x + fw / 2, y + fh / 2)
      } else {
        // empty cell
        ctx.strokeStyle = 'rgba(239,68,68,0.5)'
        ctx.lineWidth = 1
        ctx.setLineDash([4, 3])
        ctx.strokeRect(x + 1, y + 1, fw - 2, fh - 2)
        ctx.setLineDash([])
      }
      count++
    }
  }
}

function startPreview() {
  if (animFrameId) { cancelAnimationFrame(animFrameId); animFrameId = null }
  const item = currentItem.value
  if (!item?.imgEl) return
  const frames = getFrames(item.imgEl)
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

// ── export ────────────────────────────────────────────────────────────────────

async function makeGifBlob(imgEl) {
  const frames = getFrames(imgEl)
  if (!frames.length) throw new Error('无有效帧，请检查行列数和内边距')
  const { width, height } = frames[0].imageData
  return encodeGif(frames, width, height, 0)
}

async function doExport() {
  processing.value = true
  error.value = ''
  try {
    const item = currentItem.value
    if (!item) throw new Error('请先上传精灵图')
    const blob = await makeGifBlob(item.imgEl)
    const baseName = item.name.replace(/\.[^.]+$/, '')
    triggerDownload(blob, `${baseName}.gif`)
  } catch (e) {
    error.value = '导出失败：' + e.message
  } finally {
    processing.value = false
    progressText.value = ''
  }
}
</script>

<style scoped>
.tag-btn {
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: all .15s;
}
.tag-btn.active {
  border-color: #6366f1;
  background: #eef2ff;
  color: #4338ca;
  font-weight: 600;
}
.preset-btn {
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  font-size: 12px;
  cursor: pointer;
  transition: all .15s;
}
.preset-btn:hover { border-color: #6366f1; color: #4338ca; }
.preset-btn.active {
  border-color: #6366f1;
  background: #eef2ff;
  color: #4338ca;
  font-weight: 600;
}
.tip {
  cursor: help;
  text-decoration: underline dotted #94a3b8;
  text-underline-offset: 2px;
}
.btn-detect {
  padding: 4px 12px;
  border-radius: 6px;
  border: 1.5px solid #6366f1;
  background: #eef2ff;
  color: #4338ca;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: all .15s;
}
.btn-detect:hover { background: #6366f1; color: #fff; }
.grid-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 5px;
  padding: 6px 10px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}
.toolbar-divider {
  width: 1px;
  height: 18px;
  background: #e2e8f0;
  margin: 0 2px;
}
.detect-panel {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px;
  margin-top: 6px;
  padding: 7px 10px;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
}
.preview-label {
  display: flex;
  align-items: center;
  gap: 4px;
}
</style>
