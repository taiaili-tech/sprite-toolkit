<!-- src/components/GridCutter.vue -->
<template>
  <div>
    <h2 style="font-size:20px;font-weight:700;margin-bottom:20px;">宫格裁切</h2>

    <!-- 配置（始终显示） -->
    <div style="margin-bottom:16px;">
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
      <div style="display:flex;align-items:center;gap:8px;line-height:32px;">
        <span class="form-label" style="min-width:auto;">行 × 列</span>
        <input class="form-input" type="number" v-model.number="rows" min="1" max="20" style="width:60px;" />
        <span style="color:#94a3b8;">×</span>
        <input class="form-input" type="number" v-model.number="cols" min="1" max="20" style="width:60px;" />
      </div>
    </div>

    <!-- 上传区 -->
    <div
      class="upload-zone"
      :class="{ dragover: isDragging }"
      @click="fileInput.click()"
      @dragover.prevent="isDragging = true"
      @dragleave="isDragging = false"
      @drop.prevent="onDrop"
    >
      <input ref="fileInput" type="file" accept="image/*" multiple @change="onFileChange" />
      <div v-if="fileList.length === 0">点击或拖入图片（支持多文件批量，PNG / JPG / WebP / GIF）</div>
      <div v-else style="font-size:13px;">
        已载入 {{ fileList.length }} 张图片&nbsp;
        <span style="color:#6366f1;cursor:pointer;text-decoration:underline;" @click.stop="fileInput.click()">重新选择</span>
      </div>
      <div class="upload-hint">GIF 只取第一帧</div>
    </div>

    <!-- 文件 tab -->
    <div v-if="fileList.length > 1" style="margin-top:10px;display:flex;flex-wrap:wrap;gap:6px;">
      <button
        v-for="(item, idx) in fileList"
        :key="idx"
        :class="['tag-btn', { active: currentIdx === idx }]"
        @click="currentIdx = idx"
      >
        {{ item.name }}
        <span style="margin-left:4px;opacity:0.6;" @click.stop="removeFile(idx)">×</span>
      </button>
    </div>

    <div v-if="error" class="error-msg">{{ error }}</div>

    <!-- 预览 -->
    <div v-if="currentItem" class="preview-wrap" style="margin-top:16px;">
      <div class="preview-label">
        预览（每格 {{ cellW }}×{{ cellH }} px）
        <span v-if="fileList.length > 1" style="margin-left:8px;font-size:11px;color:#94a3b8;">
          {{ currentIdx + 1 }}/{{ fileList.length }}
        </span>
      </div>
      <canvas ref="previewCanvas"></canvas>
    </div>

    <div style="margin-top:20px;">
      <button class="btn-primary" :disabled="!fileList.length || processing" @click="doProcess">
        {{ processing
          ? `处理中… ${progressText}`
          : fileList.length > 1
            ? `批量裁切 ${fileList.length} 张并下载 ZIP`
            : '裁切并下载 ZIP' }}
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
const fileList = ref([])   // [{ name, imgEl }]
const currentIdx = ref(0)
const isDragging = ref(false)
const rows = ref(3)
const cols = ref(3)
const error = ref('')
const processing = ref(false)
const progressText = ref('')

const currentItem = computed(() => fileList.value[currentIdx.value] ?? null)
const cellW = computed(() => currentItem.value ? Math.floor(currentItem.value.imgEl.naturalWidth / cols.value) : 0)
const cellH = computed(() => currentItem.value ? Math.floor(currentItem.value.imgEl.naturalHeight / rows.value) : 0)

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

async function loadFiles(files) {
  error.value = ''
  const arr = Array.from(files)
  const items = []
  for (const f of arr) {
    try {
      const imgEl = await fileToImage(f)
      items.push({ name: f.name, imgEl })
    } catch (e) {
      error.value = `${f.name} 加载失败：${e.message}`
    }
  }
  fileList.value = items
  currentIdx.value = 0
  await nextTick()
  drawPreview()
}

function onFileChange(e) { if (e.target.files.length) loadFiles(e.target.files) }
function onDrop(e) { isDragging.value = false; if (e.dataTransfer.files.length) loadFiles(e.dataTransfer.files) }
function removeFile(idx) {
  fileList.value.splice(idx, 1)
  if (currentIdx.value >= fileList.value.length) currentIdx.value = Math.max(0, fileList.value.length - 1)
  nextTick(() => drawPreview())
}

watch([rows, cols, currentIdx], () => { if (currentItem.value) drawPreview() })

function drawPreview() {
  const canvas = previewCanvas.value
  const item = currentItem.value
  if (!canvas || !item) return
  const img = item.imgEl
  const MAX = 600
  const scale = Math.min(1, MAX / Math.max(img.naturalWidth, img.naturalHeight))
  canvas.width = img.naturalWidth * scale
  canvas.height = img.naturalHeight * scale
  const ctx = canvas.getContext('2d')
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
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
  if (!fileList.value.length) return
  error.value = ''
  processing.value = true
  try {
    const zipEntries = []
    for (let i = 0; i < fileList.value.length; i++) {
      const item = fileList.value[i]
      progressText.value = `(${i + 1}/${fileList.value.length})`
      const img = item.imgEl
      const cw = Math.floor(img.naturalWidth / cols.value)
      const ch = Math.floor(img.naturalHeight / rows.value)
      const baseName = fileList.value.length > 1
        ? item.name.replace(/\.[^.]+$/, '')
        : ''
      for (let r = 0; r < rows.value; r++) {
        for (let c = 0; c < cols.value; c++) {
          const blob = await cropToBlob(img, c * cw, r * ch, cw, ch)
          const name = baseName
            ? `${baseName}_r${r + 1}c${c + 1}.png`
            : `r${r + 1}c${c + 1}.png`
          zipEntries.push({ name, blob })
        }
      }
    }
    await downloadAsZip(zipEntries, 'grid_cut.zip')
  } catch (e) {
    error.value = '处理失败：' + e.message
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
.tag-btn.active { border-color: #6366f1; background: #eef2ff; color: #4338ca; font-weight: 600; }
</style>
