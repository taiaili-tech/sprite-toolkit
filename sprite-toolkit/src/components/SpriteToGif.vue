<!-- src/components/SpriteToGif.vue -->
<template>
  <div>
    <h2 style="font-size:20px;font-weight:700;margin-bottom:20px;">精灵图 → GIF</h2>

    <!-- 精灵图上传 -->
    <div
      class="upload-zone"
      :class="{ dragover: isDragging }"
      @click="fileInput.click()"
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

    <div v-if="imgFile" style="margin-top:20px;">
      <div class="form-row">
        <span class="form-label">列数</span>
        <input class="form-input" type="number" v-model.number="cols" min="1" max="64" />
        <span v-if="metaLoaded" class="meta-badge">来自 metadata</span>
      </div>
      <div class="form-row">
        <span class="form-label">行数</span>
        <input class="form-input" type="number" v-model.number="rows" min="1" max="64" />
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
import { ref, computed, watch, nextTick, onUnmounted } from 'vue'
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

onUnmounted(() => {
  if (animFrameId) cancelAnimationFrame(animFrameId)
})

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
function onDrop(e) {
  isDragging.value = false
  const f = e.dataTransfer.files[0]
  if (f) loadImg(f)
}

async function loadMeta(f) {
  try {
    const text = await f.text()
    const meta = JSON.parse(text)
    if (meta.cols) cols.value = meta.cols
    if (meta.rows) rows.value = meta.rows
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

watch([cols, rows, fps, padding], () => { if (imgEl.value) startPreview() })

function getFrames() {
  const img = imgEl.value
  if (!img) return []
  const r = rows.value || 1
  const c = cols.value || 1
  const p = padding.value || 0
  const frameW = Math.floor((img.naturalWidth - p * (c + 1)) / c)
  const frameH = Math.floor((img.naturalHeight - p * (r + 1)) / r)
  if (frameW <= 0 || frameH <= 0) return []
  const frames = []
  for (let ri = 0; ri < r; ri++) {
    for (let ci = 0; ci < c; ci++) {
      const x = p + ci * (frameW + p)
      const y = p + ri * (frameH + p)
      const canvas = document.createElement('canvas')
      canvas.width = frameW; canvas.height = frameH
      const ctx = canvas.getContext('2d')
      ctx.drawImage(img, x, y, frameW, frameH, 0, 0, frameW, frameH)
      const frameIndex = ri * c + ci
      const d = metaDelays.value?.[frameIndex] ?? delay.value
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
    if (!frames.length) throw new Error('无有效帧，请检查行列数和内边距')
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
