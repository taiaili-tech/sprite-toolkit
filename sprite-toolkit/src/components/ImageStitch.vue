<!-- src/components/ImageStitch.vue -->
<template>
  <div>
    <h2 style="font-size:20px;font-weight:700;margin-bottom:16px;">图片拼接</h2>

    <!-- 设置栏 -->
    <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:16px;">
      <span class="form-label" style="margin:0;">方向</span>
      <button class="preset-btn" :class="{ active: direction === 'h' }" @click="direction='h'">横向排列 →</button>
      <button class="preset-btn" :class="{ active: direction === 'v' }" @click="direction='v'">纵向排列 ↓</button>
      <span class="form-label tip" style="margin:0;" title="图片之间的间距（像素）">间距 px</span>
      <input class="form-input" type="number" v-model.number="gap" min="0" max="200" style="width:70px;" />
      <span class="form-label" style="margin:0;">背景</span>
      <div style="display:flex;align-items:center;gap:6px;">
        <input type="color" v-model="bgColor" style="width:36px;height:28px;padding:2px;border:1px solid #e2e8f0;border-radius:6px;cursor:pointer;" />
        <button class="preset-btn" :class="{ active: bgTransparent }" @click="bgTransparent=!bgTransparent">透明</button>
      </div>
    </div>

    <!-- 上传区 -->
    <div class="upload-zone" :class="{ dragover: isDragging }"
      @click="fileInput.click()"
      @dragover.prevent="isDragging = true"
      @dragleave="isDragging = false"
      @drop.prevent="onDrop">
      <input ref="fileInput" type="file" accept="image/*" multiple @change="onFileChange" />
      <div v-if="!items.length">点击或拖入图片（支持多文件，可拖动排序）</div>
      <div v-else style="font-size:13px;">
        已载入 {{ items.length }} 张&nbsp;
        <span style="color:#6366f1;cursor:pointer;text-decoration:underline;" @click.stop="fileInput.click()">继续添加</span>
      </div>
    </div>

    <!-- 排序列表 -->
    <div v-if="items.length" style="margin-top:12px;">
      <div style="font-size:12px;color:#94a3b8;margin-bottom:6px;">拖动调整顺序</div>
      <div style="display:flex;flex-wrap:wrap;gap:8px;">
        <div
          v-for="(item, idx) in items" :key="item.id"
          class="thumb-card"
          draggable="true"
          @dragstart="dragStart(idx)"
          @dragover.prevent="dragOver(idx)"
          @drop.prevent="dragDrop"
          :class="{ 'drag-over': dragOverIdx === idx }"
        >
          <img :src="item.url" style="width:72px;height:72px;object-fit:contain;display:block;border-radius:4px;" />
          <div style="font-size:10px;color:#64748b;margin-top:4px;max-width:72px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" :title="item.name">{{ item.name }}</div>
          <button class="remove-btn" style="position:absolute;top:2px;right:2px;" @click="removeItem(idx)">×</button>
        </div>
      </div>
    </div>

    <div v-if="error" class="error-msg">{{ error }}</div>

    <!-- 预览 -->
    <div v-if="items.length >= 2" style="margin-top:16px;">
      <div style="display:flex;gap:10px;align-items:center;margin-bottom:10px;flex-wrap:wrap;">
        <button class="btn-secondary" @click="drawPreview">刷新预览</button>
        <span style="font-size:12px;color:#94a3b8;">{{ previewInfo }}</span>
      </div>
      <div class="preview-wrap">
        <div class="preview-label">拼接预览</div>
        <canvas ref="previewCanvas" style="max-width:100%;"></canvas>
      </div>
      <div style="margin-top:16px;">
        <button class="btn-primary" :disabled="processing" @click="doExport">
          {{ processing ? '生成中…' : '下载拼接图 PNG' }}
        </button>
      </div>
    </div>
    <div v-else-if="items.length === 1" style="margin-top:10px;font-size:13px;color:#94a3b8;">请至少添加 2 张图片</div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const fileInput = ref(null)
const previewCanvas = ref(null)
const isDragging = ref(false)
const items = ref([])
const direction = ref('h')
const gap = ref(0)
const bgColor = ref('#ffffff')
const bgTransparent = ref(false)
const processing = ref(false)
const error = ref('')
const previewInfo = ref('')
let idCounter = 0
let dragSrcIdx = -1
const dragOverIdx = ref(-1)

async function loadFiles(files) {
  for (const f of Array.from(files)) {
    if (!f.type.startsWith('image/')) continue
    const url = URL.createObjectURL(f)
    const img = await new Promise((res, rej) => {
      const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = url
    }).catch(() => null)
    if (!img) continue
    items.value.push({ id: idCounter++, name: f.name, url, img })
  }
  if (items.value.length >= 2) drawPreview()
}

function onFileChange(e) { loadFiles(e.target.files); e.target.value = '' }
function onDrop(e) { isDragging.value = false; loadFiles(e.dataTransfer.files) }
function removeItem(idx) { URL.revokeObjectURL(items.value[idx].url); items.value.splice(idx, 1); if (items.value.length >= 2) drawPreview() }

// Drag reorder
function dragStart(idx) { dragSrcIdx = idx }
function dragOver(idx) { dragOverIdx.value = idx }
function dragDrop() {
  if (dragSrcIdx < 0 || dragSrcIdx === dragOverIdx.value) { dragOverIdx.value = -1; return }
  const arr = [...items.value]
  const [moved] = arr.splice(dragSrcIdx, 1)
  arr.splice(dragOverIdx.value, 0, moved)
  items.value = arr
  dragOverIdx.value = -1
  drawPreview()
}

watch([direction, gap, bgColor, bgTransparent], () => { if (items.value.length >= 2) drawPreview() })

function calcSize() {
  const imgs = items.value.map(i => i.img)
  const g = gap.value || 0
  let W, H
  if (direction.value === 'h') {
    W = imgs.reduce((s, i) => s + i.naturalWidth, 0) + g * (imgs.length - 1)
    H = Math.max(...imgs.map(i => i.naturalHeight))
  } else {
    W = Math.max(...imgs.map(i => i.naturalWidth))
    H = imgs.reduce((s, i) => s + i.naturalHeight, 0) + g * (imgs.length - 1)
  }
  return { W, H, imgs, g }
}

function drawPreview() {
  const canvas = previewCanvas.value
  if (!canvas || items.value.length < 2) return
  const { W, H, imgs, g } = calcSize()
  const MAX = 800
  const scale = Math.min(1, MAX / Math.max(W, H))
  canvas.width = Math.round(W * scale)
  canvas.height = Math.round(H * scale)
  const ctx = canvas.getContext('2d')
  if (bgTransparent.value) {
    ctx.clearRect(0, 0, canvas.width, canvas.height)
  } else {
    ctx.fillStyle = bgColor.value
    ctx.fillRect(0, 0, canvas.width, canvas.height)
  }
  let offset = 0
  for (const img of imgs) {
    if (direction.value === 'h') {
      ctx.drawImage(img, Math.round(offset * scale), 0, Math.round(img.naturalWidth * scale), Math.round(img.naturalHeight * scale))
      offset += img.naturalWidth + g
    } else {
      ctx.drawImage(img, 0, Math.round(offset * scale), Math.round(img.naturalWidth * scale), Math.round(img.naturalHeight * scale))
      offset += img.naturalHeight + g
    }
  }
  previewInfo.value = `输出尺寸：${W} × ${H} px`
}

async function doExport() {
  processing.value = true
  try {
    const { W, H, imgs, g } = calcSize()
    const canvas = document.createElement('canvas')
    canvas.width = W; canvas.height = H
    const ctx = canvas.getContext('2d')
    if (!bgTransparent.value) { ctx.fillStyle = bgColor.value; ctx.fillRect(0, 0, W, H) }
    let offset = 0
    for (const img of imgs) {
      if (direction.value === 'h') { ctx.drawImage(img, offset, 0); offset += img.naturalWidth + g }
      else { ctx.drawImage(img, 0, offset); offset += img.naturalHeight + g }
    }
    const blob = await new Promise(res => canvas.toBlob(res, 'image/png'))
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'stitched.png'; a.click()
  } catch (e) {
    error.value = '导出失败：' + e.message
  } finally {
    processing.value = false
  }
}
</script>

<style scoped>
.thumb-card {
  position: relative;
  padding: 6px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
  cursor: grab;
  transition: border-color .15s, box-shadow .15s;
  text-align: center;
}
.thumb-card:hover { border-color: #a5b4fc; }
.thumb-card.drag-over { border-color: #6366f1; box-shadow: 0 0 0 3px rgba(99,102,241,0.2); }
.remove-btn { width:20px;height:20px;border-radius:50%;border:1px solid #e2e8f0;background:#fff;font-size:12px;cursor:pointer;color:#94a3b8;transition:all .15s;display:flex;align-items:center;justify-content:center; }
.remove-btn:hover { background:#fee2e2;border-color:#fca5a5;color:#ef4444; }
.btn-secondary { padding:8px 16px;border-radius:8px;border:1px solid #6366f1;background:#fff;color:#6366f1;font-size:14px;font-weight:500;cursor:pointer;transition:all .15s; }
.btn-secondary:hover { background:#eef2ff; }
</style>
