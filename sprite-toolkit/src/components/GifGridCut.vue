<!-- src/components/GifGridCut.vue -->
<template>
  <div>
    <h2 style="font-size:20px;font-weight:700;margin-bottom:20px;">GIF 宫格裁切</h2>

    <div
      class="upload-zone"
      :class="{ dragover: isDragging }"
      @click="fileInput.click()"
      @dragover.prevent="isDragging = true"
      @dragleave="isDragging = false"
      @drop.prevent="onDrop"
    >
      <input ref="fileInput" type="file" accept=".gif,image/gif" @change="onFileChange" />
      <div>{{ file ? file.name : '点击或拖入 GIF（每帧均为宫格布局）' }}</div>
      <div class="upload-hint">例：3×3 动态表情包 → 拆出 9 个独立 GIF</div>
    </div>

    <div v-if="error" class="error-msg">{{ error }}</div>

    <!-- 快捷预设 + 手动输入（始终显示） -->
    <div style="margin-top:16px;">
      <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:10px;">
        <span class="form-label" style="margin:0;white-space:nowrap;">快速预设</span>
        <button
          v-for="p in gridPresets"
          :key="p.label"
          class="preset-btn"
          :class="{ active: rows === p.rows && cols === p.cols }"
          @click="rows = p.rows; cols = p.cols"
        >{{ p.label }}</button>
      </div>
      <div class="form-row" style="margin-bottom:0;">
        <span class="form-label">行 × 列</span>
        <input class="form-input" type="number" v-model.number="rows" min="1" max="10" style="width:60px;" />
        <span style="color:#94a3b8;margin:0 4px;">×</span>
        <input class="form-input" type="number" v-model.number="cols" min="1" max="10" style="width:60px;" />
      </div>
    </div>

    <div v-if="decoded">

      <div class="info-msg">
        输入帧数：{{ decoded.frames.length }} &nbsp;|&nbsp;
        格子尺寸：{{ cellW }}×{{ cellH }} px &nbsp;|&nbsp;
        输出 GIF 数：{{ rows * cols }}
      </div>

      <div class="preview-wrap" style="margin-top:16px;">
        <div class="preview-label">第一帧 + 网格预览</div>
        <canvas ref="previewCanvas"></canvas>
      </div>

      <div style="margin-top:16px;">
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

const gridPresets = [
  { label: '2×2', rows: 2, cols: 2 },
  { label: '3×3', rows: 3, cols: 3 },
  { label: '4×4', rows: 4, cols: 4 },
  { label: '2×3', rows: 2, cols: 3 },
  { label: '3×2', rows: 3, cols: 2 },
  { label: '1×2', rows: 1, cols: 2 },
  { label: '2×1', rows: 2, cols: 1 },
]

const cellW = computed(() => decoded.value ? Math.floor(decoded.value.width / cols.value) : 0)
const cellH = computed(() => decoded.value ? Math.floor(decoded.value.height / rows.value) : 0)

async function loadFile(f) {
  error.value = ''
  file.value = f
  decoded.value = null
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
function onDrop(e) {
  isDragging.value = false
  const f = e.dataTransfer.files[0]
  if (f) loadFile(f)
}

watch([rows, cols], () => { if (decoded.value) drawPreview() })

function drawPreview() {
  const canvas = previewCanvas.value
  if (!canvas || !decoded.value) return
  const { frames, width, height } = decoded.value
  const MAX = 600
  const scale = Math.min(1, MAX / Math.max(width, height))
  canvas.width = Math.round(width * scale)
  canvas.height = Math.round(height * scale)
  const ctx = canvas.getContext('2d')

  // Draw first frame scaled
  const tmp = document.createElement('canvas')
  tmp.width = width; tmp.height = height
  tmp.getContext('2d').putImageData(frames[0].imageData, 0, 0)
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  ctx.drawImage(tmp, 0, 0, canvas.width, canvas.height)

  // Grid overlay
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
    const { frames, width, height, loopCount } = decoded.value
    const cw = Math.floor(width / cols.value)
    const ch = Math.floor(height / rows.value)
    const outputFiles = []

    for (let r = 0; r < rows.value; r++) {
      for (let c = 0; c < cols.value; c++) {
        const cellFrames = frames.map(frame => ({
          imageData: cropImageData(frame.imageData, width, c * cw, r * ch, cw, ch),
          delay: frame.delay,
        }))
        const blob = encodeGif(cellFrames, cw, ch, loopCount)
        outputFiles.push({ name: `r${r + 1}c${c + 1}.gif`, blob })
        progress.value++
        // yield to allow UI to update progress
        await new Promise(resolve => setTimeout(resolve, 0))
      }
    }

    await downloadAsZip(outputFiles, 'gif_grid_cut.zip')
  } catch (e) {
    error.value = '处理失败：' + e.message
  } finally {
    processing.value = false
  }
}
</script>

