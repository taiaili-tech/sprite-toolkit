<!-- src/components/GridCutter.vue -->
<template>
  <div>
    <h2 style="font-size:20px;font-weight:700;margin-bottom:20px;">宫格裁切</h2>

    <!-- 上传区 -->
    <div
      class="upload-zone"
      :class="{ dragover: isDragging }"
      @click="fileInput.click()"
      @dragover.prevent="isDragging = true"
      @dragleave="isDragging = false"
      @drop.prevent="onDrop"
    >
      <input ref="fileInput" type="file" accept="image/*" @change="onFileChange" />
      <div>{{ file ? file.name : '点击或拖入图片（PNG / JPG / WebP / GIF）' }}</div>
      <div class="upload-hint">GIF 只取第一帧</div>
    </div>

    <!-- 配置 -->
    <div style="margin-top:20px;">
      <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:10px;">
        <span class="form-label" style="margin:0;white-space:nowrap;">快速预设</span>
        <button
          v-for="p in gridPresets"
          :key="p.label"
          class="preset-btn"
          :class="{ active: rows === p.rows && cols === p.cols }"
          @click="setPreset(p.rows, p.cols)"
        >{{ p.label }}</button>
      </div>
      <div class="form-row" style="margin-bottom:0;">
        <span class="form-label">行 × 列</span>
        <input class="form-input" type="number" v-model.number="rows" min="1" max="20" style="width:60px;" />
        <span style="color:#94a3b8;margin:0 4px;">×</span>
        <input class="form-input" type="number" v-model.number="cols" min="1" max="20" style="width:60px;" />
      </div>
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

const gridPresets = [
  { label: '2×2', rows: 2, cols: 2 },
  { label: '3×3', rows: 3, cols: 3 },
  { label: '4×4', rows: 4, cols: 4 },
  { label: '2×3', rows: 2, cols: 3 },
  { label: '3×2', rows: 3, cols: 2 },
  { label: '1×2', rows: 1, cols: 2 },
  { label: '2×1', rows: 2, cols: 1 },
]

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
