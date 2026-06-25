<!-- src/components/GifToSprite.vue -->
<template>
  <div>
    <h2 style="font-size:20px;font-weight:700;margin-bottom:20px;">GIF → 精灵图</h2>

    <!-- 多文件上传 -->
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

    <!-- 文件 tab 列表 -->
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
      <!-- 输出布局预设 -->
      <div style="margin-top:20px;">
        <div class="form-label" style="display:block;margin-bottom:6px;">输出布局预设</div>
        <div style="display:flex;flex-wrap:wrap;gap:6px;">
          <button
            v-for="p in layoutPresets"
            :key="p.label"
            class="preset-btn"
            :class="{ active: maxCols === p.cols }"
            @click="maxCols = p.cols"
          >{{ p.label }}</button>
        </div>
      </div>

      <!-- 最大列数手动输入 -->
      <div class="form-row" style="margin-top:12px;">
        <span class="form-label">最大列数</span>
        <input class="form-input" type="number" v-model.number="maxCols" min="1" max="32" style="width:70px;" />
        <span style="font-size:12px;color:#94a3b8;margin-left:8px;">
          → {{ actualCols }}列 × {{ actualRows }}行
        </span>
      </div>

      <div class="info-msg">
        帧数：{{ currentDecoded.frames.length }} &nbsp;|&nbsp;
        帧尺寸：{{ currentDecoded.width }}×{{ currentDecoded.height }} px &nbsp;|&nbsp;
        精灵图：{{ spriteW }}×{{ spriteH }} px
      </div>

      <!-- 预览 -->
      <div style="display:flex;gap:24px;flex-wrap:wrap;margin-top:20px;">
        <div class="preview-wrap" style="flex:1;min-width:160px;">
          <div class="preview-label">原 GIF 预览</div>
          <canvas ref="gifPreview"></canvas>
        </div>
        <div class="preview-wrap" style="flex:2;min-width:280px;">
          <div class="preview-label">精灵图预览（{{ actualCols }}×{{ actualRows }}）</div>
          <canvas ref="spritePreview"></canvas>
        </div>
      </div>

      <!-- 导出 -->
      <div style="margin-top:20px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;">
        <button class="btn-primary" :disabled="processing" @click="doExport">
          {{ processing
            ? '生成中…'
            : fileList.length > 1
              ? `批量下载 ${fileList.length} 个精灵图 (ZIP)`
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

const fileList = ref([])      // [{ name, decoded }]
const currentIdx = ref(0)
const isDragging = ref(false)
const error = ref('')
const processing = ref(false)
const progressText = ref('')
const maxCols = ref(8)

let animFrameId = null

const layoutPresets = [
  { label: '2×2', cols: 2 },
  { label: '3×3', cols: 3 },
  { label: '4×4', cols: 4 },
  { label: '5×5', cols: 5 },
  { label: '8列', cols: 8 },
  { label: '4列', cols: 4 },
  { label: '1列', cols: 1 },
]

onUnmounted(() => { if (animFrameId) cancelAnimationFrame(animFrameId) })

const currentDecoded = computed(() => fileList.value[currentIdx.value]?.decoded ?? null)

const actualCols = computed(() => {
  if (!currentDecoded.value) return 0
  return Math.min(maxCols.value, currentDecoded.value.frames.length)
})
const actualRows = computed(() => {
  if (!currentDecoded.value) return 0
  return Math.ceil(currentDecoded.value.frames.length / actualCols.value)
})
const spriteW = computed(() => currentDecoded.value ? currentDecoded.value.width * actualCols.value : 0)
const spriteH = computed(() => currentDecoded.value ? currentDecoded.value.height * actualRows.value : 0)

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
function onDrop(e) {
  isDragging.value = false
  if (e.dataTransfer.files.length) loadFiles(e.dataTransfer.files)
}
function removeFile(idx) {
  fileList.value.splice(idx, 1)
  if (currentIdx.value >= fileList.value.length) currentIdx.value = Math.max(0, fileList.value.length - 1)
  nextTick(() => { startGifPreview(); drawSpritePreview() })
}

// ── preview ───────────────────────────────────────────────────────────────────

watch([currentIdx, maxCols], () => {
  if (animFrameId) { cancelAnimationFrame(animFrameId); animFrameId = null }
  nextTick(() => { startGifPreview(); drawSpritePreview() })
})

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
  canvas.width = spriteW.value
  canvas.height = spriteH.value
  const ctx = canvas.getContext('2d')
  const { frames, width, height } = decoded
  frames.forEach((frame, i) => {
    const col = i % actualCols.value
    const row = Math.floor(i / actualCols.value)
    ctx.putImageData(frame.imageData, col * width, row * height)
  })
  ctx.strokeStyle = 'rgba(79,70,229,0.3)'
  ctx.lineWidth = 1
  for (let r = 1; r < actualRows.value; r++) {
    ctx.beginPath(); ctx.moveTo(0, r * height); ctx.lineTo(canvas.width, r * height); ctx.stroke()
  }
  for (let c = 1; c < actualCols.value; c++) {
    ctx.beginPath(); ctx.moveTo(c * width, 0); ctx.lineTo(c * width, canvas.height); ctx.stroke()
  }
}

// ── export ────────────────────────────────────────────────────────────────────

function buildSpriteEntries(decoded, cols, rows) {
  const { frames, width, height, loopCount } = decoded
  const sw = width * cols
  const sh = height * rows
  const canvas = document.createElement('canvas')
  canvas.width = sw; canvas.height = sh
  const ctx = canvas.getContext('2d')
  frames.forEach((frame, i) => {
    const col = i % cols
    const row = Math.floor(i / cols)
    ctx.putImageData(frame.imageData, col * width, row * height)
  })
  const meta = {
    frameCount: frames.length,
    frameWidth: width,
    frameHeight: height,
    cols,
    rows,
    delays: frames.map(f => f.delay),
    loopCount: loopCount ?? 0,
  }
  return { canvas, meta }
}

async function doExport() {
  if (!fileList.value.length) return
  processing.value = true
  error.value = ''
  try {
    if (fileList.value.length === 1) {
      // Single file
      const decoded = currentDecoded.value
      const { canvas, meta } = buildSpriteEntries(decoded, actualCols.value, actualRows.value)
      const pngBlob = await new Promise(r => canvas.toBlob(r, 'image/png'))
      const metaBlob = new Blob([JSON.stringify(meta, null, 2)], { type: 'application/json' })
      await downloadAsZip(
        [{ name: 'spritesheet.png', blob: pngBlob }, { name: 'metadata.json', blob: metaBlob }],
        'gif_to_sprite.zip'
      )
    } else {
      // Batch
      const zipEntries = []
      for (let i = 0; i < fileList.value.length; i++) {
        const item = fileList.value[i]
        progressText.value = `处理 ${i + 1} / ${fileList.value.length}：${item.name}`
        const { decoded } = item
        const cols = Math.min(maxCols.value, decoded.frames.length)
        const rows = Math.ceil(decoded.frames.length / cols)
        const { canvas, meta } = buildSpriteEntries(decoded, cols, rows)
        const pngBlob = await new Promise(r => canvas.toBlob(r, 'image/png'))
        const metaBlob = new Blob([JSON.stringify(meta, null, 2)], { type: 'application/json' })
        const baseName = item.name.replace(/\.[^.]+$/, '')
        zipEntries.push({ name: `${baseName}_sprite.png`, blob: pngBlob })
        zipEntries.push({ name: `${baseName}_metadata.json`, blob: metaBlob })
      }
      progressText.value = '打包中…'
      await downloadAsZip(zipEntries, 'gif_to_sprite_batch.zip')
    }
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
</style>
