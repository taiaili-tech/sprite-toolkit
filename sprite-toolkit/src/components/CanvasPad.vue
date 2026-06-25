<!-- src/components/CanvasPad.vue -->
<template>
  <div>
    <h2 style="font-size:20px;font-weight:700;margin-bottom:16px;">加画布 / 扩边</h2>

    <!-- 边距设置 -->
    <div style="margin-bottom:16px;">
      <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:10px;">
        <button class="preset-btn" :class="{ active: lockAll }" @click="toggleLock">四边相同</button>
        <span style="font-size:12px;color:#94a3b8;">开启后修改任意值同步四边</span>
      </div>
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;max-width:400px;">
        <div v-for="s in sides" :key="s.key" class="form-row" style="flex-direction:column;align-items:flex-start;gap:4px;margin:0;">
          <span class="form-label" style="min-width:auto;">{{ s.label }}</span>
          <input class="form-input" type="number" v-model.number="padding[s.key]" min="0" max="2000" style="width:100%;"
            @input="onPadInput(s.key)" />
        </div>
      </div>

      <div style="display:flex;align-items:center;gap:10px;margin-top:12px;flex-wrap:wrap;">
        <span class="form-label" style="margin:0;">背景</span>
        <input type="color" v-model="bgColor" style="width:36px;height:28px;padding:2px;border:1px solid #e2e8f0;border-radius:6px;cursor:pointer;" />
        <button class="preset-btn" :class="{ active: bgTransparent }" @click="bgTransparent=!bgTransparent">透明</button>
        <div style="display:flex;gap:6px;margin-left:8px;">
          <button v-for="p in quickPads" :key="p" class="preset-btn"
            @click="setAll(p)">+{{ p }}px</button>
        </div>
      </div>
    </div>

    <!-- 上传区 -->
    <div class="upload-zone" :class="{ dragover: isDragging }"
      @click="fileInput.click()"
      @dragover.prevent="isDragging = true"
      @dragleave="isDragging = false"
      @drop.prevent="onDrop">
      <input ref="fileInput" type="file" accept="image/*" multiple @change="onFileChange" />
      <div v-if="!items.length">点击或拖入图片（支持批量）</div>
      <div v-else style="font-size:13px;">
        已载入 {{ items.length }} 张，当前预览：{{ items[currentIdx]?.name }}&nbsp;
        <span style="color:#6366f1;cursor:pointer;text-decoration:underline;" @click.stop="fileInput.click()">重新选择</span>
      </div>
    </div>

    <!-- 文件切换 -->
    <div v-if="items.length > 1" style="margin-top:8px;display:flex;flex-wrap:wrap;gap:6px;">
      <button v-for="(item,idx) in items" :key="idx"
        :class="['tag-btn', { active: currentIdx === idx }]" @click="currentIdx=idx">
        {{ item.name.replace(/\.[^.]+$/,'') }}
        <span style="margin-left:4px;opacity:.5;" @click.stop="items.splice(idx,1)">×</span>
      </button>
    </div>

    <div v-if="error" class="error-msg">{{ error }}</div>

    <!-- 预览 -->
    <div v-if="currentItem" style="margin-top:16px;">
      <div class="preview-wrap">
        <div class="preview-label">
          预览&nbsp;<span style="font-size:11px;color:#94a3b8;">{{ previewInfo }}</span>
        </div>
        <canvas ref="previewCanvas" style="max-width:100%;"></canvas>
      </div>
      <div style="margin-top:16px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
        <button class="btn-primary" :disabled="processing" @click="doExport">
          {{ processing ? `处理中… ${progressText}` : items.length > 1 ? `批量下载 (${items.length} 张) ZIP` : '下载 PNG' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick } from 'vue'
import { downloadAsZip } from '../utils/zipHelper.js'

const fileInput = ref(null)
const previewCanvas = ref(null)
const isDragging = ref(false)
const items = ref([])
const currentIdx = ref(0)
const processing = ref(false)
const progressText = ref('')
const error = ref('')
const lockAll = ref(true)
const bgColor = ref('#ffffff')
const bgTransparent = ref(false)
const padding = reactive({ top: 20, right: 20, bottom: 20, left: 20 })
const quickPads = [10, 20, 40, 80]
const sides = [
  { key: 'top', label: '上' },
  { key: 'right', label: '右' },
  { key: 'bottom', label: '下' },
  { key: 'left', label: '左' },
]

const currentItem = computed(() => items.value[currentIdx.value] ?? null)

const previewInfo = computed(() => {
  if (!currentItem.value) return ''
  const img = currentItem.value.img
  const W = img.naturalWidth + padding.left + padding.right
  const H = img.naturalHeight + padding.top + padding.bottom
  return `${W} × ${H} px（原 ${img.naturalWidth}×${img.naturalHeight}）`
})

function toggleLock() { lockAll.value = !lockAll.value }
function onPadInput(key) { if (lockAll.value) { const v = padding[key]; Object.assign(padding, { top: v, right: v, bottom: v, left: v }) } }
function setAll(v) { Object.assign(padding, { top: v, right: v, bottom: v, left: v }) }

async function loadFiles(files) {
  const arr = []
  for (const f of Array.from(files)) {
    if (!f.type.startsWith('image/')) continue
    const img = await new Promise((res, rej) => {
      const i = new Image(); const url = URL.createObjectURL(f)
      i.onload = () => res(i); i.onerror = rej; i.src = url
    }).catch(() => null)
    if (img) arr.push({ name: f.name, img })
  }
  items.value = arr
  currentIdx.value = 0
  await nextTick()
  drawPreview()
}

function onFileChange(e) { loadFiles(e.target.files); e.target.value = '' }
function onDrop(e) { isDragging.value = false; loadFiles(e.dataTransfer.files) }

watch([() => ({ ...padding }), bgColor, bgTransparent, currentIdx], () => {
  if (currentItem.value) nextTick(drawPreview)
}, { deep: true })

function drawPreview() {
  const canvas = previewCanvas.value
  const item = currentItem.value
  if (!canvas || !item) return
  const img = item.img
  const { top, right, bottom, left } = padding
  const W = img.naturalWidth + left + right
  const H = img.naturalHeight + top + bottom
  const MAX = 700
  const scale = Math.min(1, MAX / Math.max(W, H))
  canvas.width = Math.round(W * scale)
  canvas.height = Math.round(H * scale)
  const ctx = canvas.getContext('2d')
  if (bgTransparent.value) {
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    // draw checkerboard
    const cs = 8
    for (let y = 0; y < canvas.height; y += cs) {
      for (let x = 0; x < canvas.width; x += cs) {
        ctx.fillStyle = ((x / cs + y / cs) % 2 === 0) ? '#e2e8f0' : '#fff'
        ctx.fillRect(x, y, cs, cs)
      }
    }
  } else {
    ctx.fillStyle = bgColor.value
    ctx.fillRect(0, 0, canvas.width, canvas.height)
  }
  ctx.drawImage(img, Math.round(left * scale), Math.round(top * scale),
    Math.round(img.naturalWidth * scale), Math.round(img.naturalHeight * scale))
}

async function buildCanvas(img) {
  const { top, right, bottom, left } = padding
  const W = img.naturalWidth + left + right
  const H = img.naturalHeight + top + bottom
  const canvas = document.createElement('canvas')
  canvas.width = W; canvas.height = H
  const ctx = canvas.getContext('2d')
  if (!bgTransparent.value) { ctx.fillStyle = bgColor.value; ctx.fillRect(0, 0, W, H) }
  ctx.drawImage(img, left, top)
  return canvas
}

async function doExport() {
  processing.value = true; error.value = ''
  try {
    if (items.value.length === 1) {
      const canvas = await buildCanvas(items.value[0].img)
      const blob = await new Promise(res => canvas.toBlob(res, 'image/png'))
      const a = document.createElement('a'); a.href = URL.createObjectURL(blob)
      a.download = items.value[0].name.replace(/\.[^.]+$/, '') + '_padded.png'; a.click()
    } else {
      const zipEntries = []
      for (let i = 0; i < items.value.length; i++) {
        progressText.value = `(${i + 1}/${items.value.length})`
        const canvas = await buildCanvas(items.value[i].img)
        const blob = await new Promise(res => canvas.toBlob(res, 'image/png'))
        zipEntries.push({ name: items.value[i].name.replace(/\.[^.]+$/, '') + '_padded.png', blob })
      }
      await downloadAsZip(zipEntries, 'padded.zip')
    }
  } catch (e) {
    error.value = '导出失败：' + e.message
  } finally {
    processing.value = false; progressText.value = ''
  }
}
</script>

<style scoped>
.tag-btn { padding:4px 10px;border-radius:6px;border:1px solid #e2e8f0;background:#f8fafc;font-size:12px;cursor:pointer;white-space:nowrap;transition:all .15s; }
.tag-btn.active { border-color:#6366f1;background:#eef2ff;color:#4338ca;font-weight:600; }
</style>
