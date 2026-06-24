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
  decoded.value = null
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
function onDrop(e) {
  isDragging.value = false
  const f = e.dataTransfer.files[0]
  if (f) loadFile(f)
}

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
  error.value = ''
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
