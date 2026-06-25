<!-- src/components/GifToSprite.vue -->
<template>
  <div>
    <h2 style="font-size:20px;font-weight:700;margin-bottom:16px;">GIF → 精灵图</h2>

    <!-- 模式切换 -->
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:14px;">
      <span class="form-label" style="margin:0;">导出模式</span>
      <button
        class="mode-btn"
        :class="{ active: mode === 'sample' }"
        @click="mode = 'sample'"
        title="从全部帧中均匀采样，始终输出1张精灵图"
      >均匀采样</button>
      <button
        class="mode-btn"
        :class="{ active: mode === 'full' }"
        @click="mode = 'full'"
        title="保留全部帧，按布局顺序排入精灵图（帧数多时会生成多张）"
      >全帧顺序</button>
      <span v-if="currentDecoded && mode === 'sample'" style="font-size:12px;color:#6366f1;font-weight:600;">
        → {{ totalFrames }} 帧 ÷ {{ cellCount }} 格 ≈ 每 <strong>{{ sampleInterval }}</strong> 帧取 1 帧，输出 1 张
      </span>
      <span v-if="currentDecoded && mode === 'full'" style="font-size:12px;color:#6366f1;font-weight:600;">
        → {{ totalFrames }} 帧 ÷ {{ cellCount }} = 输出 <strong>{{ sheetCount }}</strong> 张
        <template v-if="lastSheetFrames < cellCount">（最后一张 {{ lastSheetFrames }} 帧）</template>
      </span>
    </div>

    <!-- 布局设置（始终显示） -->
    <div style="margin-bottom:16px;">
      <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:8px;">
        <span class="form-label" style="margin:0;">输出布局预设</span>
        <button
          v-for="p in layoutPresets"
          :key="p.label"
          class="preset-btn"
          :class="{ active: gridCols === p.cols && gridRows === p.rows }"
          @click="gridCols = p.cols; gridRows = p.rows"
        >{{ p.label }}</button>
      </div>
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
        <div class="form-row" style="margin-bottom:0;">
          <span class="form-label tip" title="精灵图横向放几帧">列数</span>
          <input class="form-input" type="number" v-model.number="gridCols" min="1" max="32" style="width:60px;" />
        </div>
        <span style="color:#94a3b8;">×</span>
        <div class="form-row" style="margin-bottom:0;">
          <span class="form-label tip" title="精灵图纵向放几帧">行数</span>
          <input class="form-input" type="number" v-model.number="gridRows" min="1" max="32" style="width:60px;" />
        </div>
        <span style="font-size:12px;color:#94a3b8;">= {{ cellCount }} 格/张</span>
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
      <input ref="fileInput" type="file" accept=".gif,image/gif" multiple @change="onFileChange" />
      <div v-if="fileList.length === 0">点击或拖入 GIF 动画（支持多文件批量）</div>
      <div v-else style="font-size:13px;">
        已载入 {{ fileList.length }} 个 GIF&nbsp;
        <span style="color:#6366f1;cursor:pointer;text-decoration:underline;" @click.stop="fileInput.click()">重新选择</span>
      </div>
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

    <div v-if="currentDecoded">
      <div class="info-msg">
        总帧数：{{ totalFrames }} &nbsp;|&nbsp;
        帧尺寸：{{ currentDecoded.width }}×{{ currentDecoded.height }} px &nbsp;|&nbsp;
        <template v-if="mode === 'sample'">
          采样 {{ cellCount }} 帧（每 {{ sampleInterval }} 帧取 1）&nbsp;|&nbsp; 输出 1 张精灵图
        </template>
        <template v-else>
          全部 {{ totalFrames }} 帧 → {{ sheetCount }} 张精灵图
        </template>
      </div>

      <!-- 预览 -->
      <div style="display:flex;gap:24px;flex-wrap:wrap;margin-top:16px;">
        <div class="preview-wrap" style="flex:1;min-width:160px;">
          <div class="preview-label">原 GIF 预览</div>
          <canvas ref="gifPreview"></canvas>
        </div>
        <div class="preview-wrap" style="flex:2;min-width:280px;">
          <div class="preview-label" style="display:flex;align-items:center;gap:8px;">
            <span>精灵图预览（{{ gridCols }}×{{ gridRows }}）</span>
            <template v-if="mode === 'full' && sheetCount > 1">
              <div style="display:flex;align-items:center;gap:4px;margin-left:auto;">
                <button class="page-btn" :disabled="previewSheet <= 0" @click="previewSheet--">‹</button>
                <span style="font-size:12px;color:#64748b;white-space:nowrap;">
                  第 {{ previewSheet + 1 }} / {{ sheetCount }} 张
                </span>
                <button class="page-btn" :disabled="previewSheet >= sheetCount - 1" @click="previewSheet++">›</button>
              </div>
            </template>
          </div>
          <canvas ref="spritePreview"></canvas>
        </div>
      </div>

      <!-- 导出 -->
      <div style="margin-top:20px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;">
        <button class="btn-primary" :disabled="processing" @click="doExport">
          {{ processing ? '生成中…'
            : fileList.length > 1
              ? `批量下载 (ZIP)`
              : mode === 'full' && sheetCount > 1
                ? `下载 ${sheetCount} 张精灵图 (ZIP)`
                : '下载精灵图 + metadata.json (ZIP)' }}
        </button>
        <span v-if="processing" style="font-size:13px;color:#64748b;">{{ progressText }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onUnmounted } from 'vue'
import { decodeGif } from '../utils/gifDecoder.js'
import { fileToBuffer } from '../utils/canvasCrop.js'
import { downloadAsZip } from '../utils/zipHelper.js'

const fileInput = ref(null)
const gifPreview = ref(null)
const spritePreview = ref(null)

const fileList = ref([])
const currentIdx = ref(0)
const isDragging = ref(false)
const error = ref('')
const processing = ref(false)
const progressText = ref('')
const gridCols = ref(3)
const gridRows = ref(3)
const mode = ref('sample') // 'sample' | 'full'
const previewSheet = ref(0)

let animFrameId = null

const layoutPresets = [
  { label: '2×2', cols: 2, rows: 2 },
  { label: '3×3', cols: 3, rows: 3 },
  { label: '4×4', cols: 4, rows: 4 },
  { label: '2×3', cols: 2, rows: 3 },
  { label: '3×2', cols: 3, rows: 2 },
  { label: '4×2', cols: 4, rows: 2 },
  { label: '8×1', cols: 8, rows: 1 },
]

onUnmounted(() => { if (animFrameId) cancelAnimationFrame(animFrameId) })

const currentDecoded = computed(() => fileList.value[currentIdx.value]?.decoded ?? null)
const totalFrames = computed(() => currentDecoded.value?.frames.length ?? 0)
const cellCount = computed(() => gridCols.value * gridRows.value)

// 均匀采样间隔（保留1位小数显示）
const sampleInterval = computed(() => {
  if (!totalFrames.value) return 1
  return Math.max(1, +(totalFrames.value / cellCount.value).toFixed(1))
})

// 全帧模式：多少张精灵图
const sheetCount = computed(() => {
  if (!totalFrames.value) return 1
  return Math.ceil(totalFrames.value / cellCount.value)
})
const lastSheetFrames = computed(() => {
  const rem = totalFrames.value % cellCount.value
  return rem === 0 ? cellCount.value : rem
})

// 采样后的帧索引列表
function getSampledIndices(total, count) {
  const indices = []
  for (let i = 0; i < count; i++) {
    indices.push(Math.min(total - 1, Math.round(i * total / count)))
  }
  return indices
}

const spriteW = computed(() => currentDecoded.value ? currentDecoded.value.width * gridCols.value : 0)
const spriteH = computed(() => currentDecoded.value ? currentDecoded.value.height * gridRows.value : 0)

// ── file loading ──────────────────────────────────────────────────────────────

async function loadFiles(files) {
  error.value = ''
  const arr = Array.from(files)
  const items = []
  for (const f of arr) {
    try {
      const buffer = await fileToBuffer(f)
      const decoded = await decodeGif(buffer)
      items.push({ name: f.name, decoded })
    } catch (e) {
      error.value = `${f.name} 解析失败：${e.message}`
    }
  }
  fileList.value = items
  currentIdx.value = 0
  if (!items.length) return
  await nextTick()
  startGifPreview()
  drawSpritePreview()
}

function onFileChange(e) { if (e.target.files.length) loadFiles(e.target.files) }
function onDrop(e) { isDragging.value = false; if (e.dataTransfer.files.length) loadFiles(e.dataTransfer.files) }
function removeFile(idx) {
  fileList.value.splice(idx, 1)
  if (currentIdx.value >= fileList.value.length) currentIdx.value = Math.max(0, fileList.value.length - 1)
  nextTick(() => { startGifPreview(); drawSpritePreview() })
}

// ── preview ───────────────────────────────────────────────────────────────────

watch([currentIdx, gridCols, gridRows, mode], () => {
  previewSheet.value = 0
  if (animFrameId) { cancelAnimationFrame(animFrameId); animFrameId = null }
  nextTick(() => { startGifPreview(); drawSpritePreview() })
})
watch(previewSheet, () => nextTick(() => drawSpritePreview()))

function startGifPreview() {
  if (animFrameId) { cancelAnimationFrame(animFrameId); animFrameId = null }
  const canvas = gifPreview.value
  const decoded = currentDecoded.value
  if (!canvas || !decoded) return
  const { frames, width, height } = decoded
  canvas.width = width; canvas.height = height
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

function drawSpritePreview() {
  const canvas = spritePreview.value
  const decoded = currentDecoded.value
  if (!canvas || !decoded) return
  const { frames, width, height } = decoded
  const c = gridCols.value
  const r = gridRows.value
  canvas.width = width * c
  canvas.height = height * r
  const ctx = canvas.getContext('2d')
  ctx.clearRect(0, 0, canvas.width, canvas.height)

  let indices
  if (mode.value === 'sample') {
    indices = getSampledIndices(frames.length, cellCount.value)
  } else {
    const start = previewSheet.value * cellCount.value
    const end = Math.min(start + cellCount.value, frames.length)
    indices = Array.from({ length: end - start }, (_, i) => start + i)
  }

  indices.forEach((fi, i) => {
    const col = i % c
    const row = Math.floor(i / c)
    ctx.putImageData(frames[fi].imageData, col * width, row * height)
  })

  ctx.strokeStyle = 'rgba(79,70,229,0.3)'
  ctx.lineWidth = 1
  for (let ri = 1; ri < r; ri++) {
    ctx.beginPath(); ctx.moveTo(0, ri * height); ctx.lineTo(canvas.width, ri * height); ctx.stroke()
  }
  for (let ci = 1; ci < c; ci++) {
    ctx.beginPath(); ctx.moveTo(ci * width, 0); ctx.lineTo(ci * width, canvas.height); ctx.stroke()
  }
}

// ── export ────────────────────────────────────────────────────────────────────

async function buildSprite(decoded, baseName) {
  const { frames, width, height, loopCount } = decoded
  const c = gridCols.value
  const r = gridRows.value
  const entries = []

  if (mode.value === 'sample') {
    const indices = getSampledIndices(frames.length, cellCount.value)
    const canvas = document.createElement('canvas')
    canvas.width = width * c; canvas.height = height * r
    const ctx = canvas.getContext('2d')
    indices.forEach((fi, i) => {
      ctx.putImageData(frames[fi].imageData, (i % c) * width, Math.floor(i / c) * height)
    })
    const pngBlob = await new Promise(res => canvas.toBlob(res, 'image/png'))
    const meta = {
      mode: 'sample',
      frameCount: indices.length,
      frameWidth: width, frameHeight: height,
      cols: c, rows: r,
      sampledFrom: frames.length,
      sampleInterval: +(frames.length / indices.length).toFixed(2),
      sampledIndices: indices,
      delays: indices.map(fi => frames[fi].delay),
      loopCount: loopCount ?? 0,
    }
    entries.push({ name: `${baseName}.png`, blob: pngBlob })
    entries.push({ name: `${baseName}_metadata.json`, blob: new Blob([JSON.stringify(meta, null, 2)], { type: 'application/json' }) })
  } else {
    // 全帧模式：按 cellCount 分批生成多张精灵图
    const total = frames.length
    const count = Math.ceil(total / cellCount.value)
    const allDelays = []
    for (let s = 0; s < count; s++) {
      const start = s * cellCount.value
      const end = Math.min(start + cellCount.value, total)
      const canvas = document.createElement('canvas')
      canvas.width = width * c; canvas.height = height * r
      const ctx = canvas.getContext('2d')
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      for (let i = start; i < end; i++) {
        const slot = i - start
        ctx.putImageData(frames[i].imageData, (slot % c) * width, Math.floor(slot / c) * height)
        allDelays.push(frames[i].delay)
      }
      const pngBlob = await new Promise(res => canvas.toBlob(res, 'image/png'))
      const suffix = count > 1 ? `_${String(s + 1).padStart(2, '0')}` : ''
      entries.push({ name: `${baseName}${suffix}.png`, blob: pngBlob })
    }
    const meta = {
      mode: 'full',
      frameCount: total,
      frameWidth: width, frameHeight: height,
      cols: c, rows: r,
      sheetCount: count,
      delays: allDelays,
      loopCount: loopCount ?? 0,
    }
    entries.push({ name: `${baseName}_metadata.json`, blob: new Blob([JSON.stringify(meta, null, 2)], { type: 'application/json' }) })
  }

  return entries
}

async function doExport() {
  if (!fileList.value.length) return
  processing.value = true
  error.value = ''
  try {
    const zipEntries = []
    for (let i = 0; i < fileList.value.length; i++) {
      const item = fileList.value[i]
      progressText.value = `处理 ${i + 1}/${fileList.value.length}：${item.name}`
      const baseName = fileList.value.length > 1
        ? item.name.replace(/\.[^.]+$/, '') + '_sprite'
        : 'spritesheet'
      const entries = await buildSprite(item.decoded, baseName)
      zipEntries.push(...entries)
    }
    progressText.value = '打包中…'
    await downloadAsZip(zipEntries, 'gif_to_sprite.zip')
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
.tag-btn.active { border-color: #6366f1; background: #eef2ff; color: #4338ca; font-weight: 600; }
.tip { cursor: help; text-decoration: underline dotted #94a3b8; text-underline-offset: 2px; }
.mode-btn {
  padding: 5px 14px;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  font-size: 13px;
  cursor: pointer;
  transition: all .15s;
}
.mode-btn.active { border-color: #6366f1; background: #eef2ff; color: #4338ca; font-weight: 600; }
.page-btn {
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  font-size: 14px;
  cursor: pointer;
  line-height: 1.4;
}
.page-btn:disabled { opacity: 0.35; cursor: default; }
</style>
