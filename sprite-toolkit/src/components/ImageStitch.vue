<!-- src/components/ImageStitch.vue -->
<template>
  <div>
    <h2 style="font-size:20px;font-weight:700;margin-bottom:16px;">图片拼接</h2>

    <!-- 设置栏 -->
    <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:16px;">
      <!-- 排列方式 -->
      <span class="form-label" style="margin:0;">排列</span>
      <button class="preset-btn" :class="{ active: layout === 'h' }" @click="layout='h'">横排（1行）</button>
      <button class="preset-btn" :class="{ active: layout === 'v' }" @click="layout='v'">竖排（1列）</button>
      <button class="preset-btn" :class="{ active: layout === 'grid' }" @click="layout='grid'">自定义宫格</button>

      <!-- 宫格列数（grid模式） -->
      <template v-if="layout === 'grid'">
        <span class="form-label tip" style="margin:0;" title="每行放几张图，行数根据总图数自动计算">列数</span>
        <input class="form-input" type="number" v-model.number="gridCols" min="1" max="20" style="width:60px;" />
        <span v-if="items.length" style="font-size:12px;color:#94a3b8;">
          × {{ gridRows }} 行（共 {{ items.length }} 张）
        </span>
      </template>

      <!-- 对齐方式（grid模式） -->
      <template v-if="layout === 'grid'">
        <span class="form-label" style="margin:0;margin-left:4px;">对齐</span>
        <button class="preset-btn" :class="{ active: align === 'start' }" @click="align='start'">左/上</button>
        <button class="preset-btn" :class="{ active: align === 'center' }" @click="align='center'">居中</button>
      </template>
    </div>

    <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:16px;">
      <span class="form-label tip" style="margin:0;" title="图片之间的间距（像素）">间距 px</span>
      <input class="form-input" type="number" v-model.number="gap" min="0" max="200" style="width:70px;" />
      <span class="form-label" style="margin:0;">背景</span>
      <input type="color" v-model="bgColor" style="width:36px;height:28px;padding:2px;border:1px solid #e2e8f0;border-radius:6px;cursor:pointer;" />
      <button class="preset-btn" :class="{ active: bgTransparent }" @click="bgTransparent=!bgTransparent">透明</button>

      <!-- 统一尺寸（grid模式） -->
      <template v-if="layout === 'grid'">
        <span style="width:1px;height:20px;background:#e2e8f0;margin:0 4px;"></span>
        <button class="preset-btn" :class="{ active: uniformSize }" @click="uniformSize=!uniformSize"
          title="将所有图片缩放到相同尺寸（以第一张为基准）">统一图片尺寸</button>
      </template>
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
        &nbsp;/&nbsp;
        <span style="color:#ef4444;cursor:pointer;text-decoration:underline;" @click.stop="items=[]">清空</span>
      </div>
    </div>

    <!-- 缩略图排序 -->
    <div v-if="items.length" style="margin-top:12px;">
      <div style="font-size:12px;color:#94a3b8;margin-bottom:6px;">
        拖动调整顺序
        <template v-if="layout === 'grid'">
          · 当前宫格：{{ gridCols }} 列 × {{ gridRows }} 行
          <template v-if="emptySlots > 0">（最后 {{ emptySlots }} 格为空）</template>
        </template>
      </div>
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
          <!-- grid序号 -->
          <div v-if="layout === 'grid'" class="grid-badge">{{ Math.floor(idx/gridCols)+1 }}-{{ idx%gridCols+1 }}</div>
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
import { ref, computed, watch } from 'vue'

const fileInput = ref(null)
const previewCanvas = ref(null)
const isDragging = ref(false)
const items = ref([])
const layout = ref('h')       // 'h' | 'v' | 'grid'
const gridCols = ref(2)
const align = ref('center')
const uniformSize = ref(false)
const gap = ref(0)
const bgColor = ref('#ffffff')
const bgTransparent = ref(false)
const processing = ref(false)
const error = ref('')
const previewInfo = ref('')
let idCounter = 0
let dragSrcIdx = -1
const dragOverIdx = ref(-1)

const gridRows = computed(() => Math.ceil(items.value.length / gridCols.value))
const emptySlots = computed(() => gridRows.value * gridCols.value - items.value.length)

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
function removeItem(idx) {
  URL.revokeObjectURL(items.value[idx].url)
  items.value.splice(idx, 1)
  if (items.value.length >= 2) drawPreview()
}

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

watch([layout, gridCols, align, gap, bgColor, bgTransparent, uniformSize], () => {
  if (items.value.length >= 2) drawPreview()
})

// Calculate canvas size for each layout mode
function calcLayout(imgs) {
  const g = gap.value || 0
  const c = gridCols.value
  const r = gridRows.value

  if (layout.value === 'h') {
    const W = imgs.reduce((s, i) => s + i.naturalWidth, 0) + g * (imgs.length - 1)
    const H = Math.max(...imgs.map(i => i.naturalHeight))
    return { W, H, mode: 'h' }
  }
  if (layout.value === 'v') {
    const W = Math.max(...imgs.map(i => i.naturalWidth))
    const H = imgs.reduce((s, i) => s + i.naturalHeight, 0) + g * (imgs.length - 1)
    return { W, H, mode: 'v' }
  }

  // grid mode
  if (uniformSize.value && imgs.length > 0) {
    const cellW = imgs[0].naturalWidth
    const cellH = imgs[0].naturalHeight
    const W = cellW * c + g * (c - 1)
    const H = cellH * r + g * (r - 1)
    return { W, H, mode: 'grid', cellW, cellH, uniformCell: true, cols: c, rows: r }
  } else {
    // per-row max height, per-col max width
    const colWidths = Array.from({ length: c }, (_, ci) =>
      Math.max(...imgs.filter((_, idx) => idx % c === ci).map(i => i.naturalWidth), 0))
    const rowHeights = Array.from({ length: r }, (_, ri) =>
      Math.max(...imgs.slice(ri * c, ri * c + c).map(i => i.naturalHeight), 0))
    const W = colWidths.reduce((s, w) => s + w, 0) + g * (c - 1)
    const H = rowHeights.reduce((s, h) => s + h, 0) + g * (r - 1)
    return { W, H, mode: 'grid', colWidths, rowHeights, cols: c, rows: r }
  }
}

function renderToCanvas(canvas, imgs, info, scale = 1) {
  canvas.width = Math.round(info.W * scale)
  canvas.height = Math.round(info.H * scale)
  const ctx = canvas.getContext('2d')
  if (bgTransparent.value) {
    ctx.clearRect(0, 0, canvas.width, canvas.height)
  } else {
    ctx.fillStyle = bgColor.value
    ctx.fillRect(0, 0, canvas.width, canvas.height)
  }
  const g = (gap.value || 0) * scale

  if (info.mode === 'h') {
    let x = 0
    for (const img of imgs) {
      const iw = img.naturalWidth * scale
      const ih = img.naturalHeight * scale
      const dy = align.value === 'center' ? (canvas.height - ih) / 2 : 0
      ctx.drawImage(img, x, dy, iw, ih)
      x += iw + g
    }
    return
  }

  if (info.mode === 'v') {
    let y = 0
    for (const img of imgs) {
      const iw = img.naturalWidth * scale
      const ih = img.naturalHeight * scale
      const dx = align.value === 'center' ? (canvas.width - iw) / 2 : 0
      ctx.drawImage(img, dx, y, iw, ih)
      y += ih + g
    }
    return
  }

  // grid
  const { cols } = info
  if (info.uniformCell) {
    const cw = info.cellW * scale
    const ch = info.cellH * scale
    imgs.forEach((img, idx) => {
      const ci = idx % cols
      const ri = Math.floor(idx / cols)
      const iw = img.naturalWidth * scale
      const ih = img.naturalHeight * scale
      const bx = ci * (cw + g)
      const by = ri * (ch + g)
      const dx = align.value === 'center' ? bx + (cw - iw) / 2 : bx
      const dy = align.value === 'center' ? by + (ch - ih) / 2 : by
      ctx.drawImage(img, dx, dy, iw, ih)
    })
  } else {
    const colXs = [0]
    for (let ci = 0; ci < cols - 1; ci++) colXs.push(colXs[ci] + info.colWidths[ci] * scale + g)
    const rowYs = [0]
    for (let ri = 0; ri < info.rows - 1; ri++) rowYs.push(rowYs[ri] + info.rowHeights[ri] * scale + g)
    imgs.forEach((img, idx) => {
      const ci = idx % cols
      const ri = Math.floor(idx / cols)
      const iw = img.naturalWidth * scale
      const ih = img.naturalHeight * scale
      const cellW = info.colWidths[ci] * scale
      const cellH = info.rowHeights[ri] * scale
      const dx = colXs[ci] + (align.value === 'center' ? (cellW - iw) / 2 : 0)
      const dy = rowYs[ri] + (align.value === 'center' ? (cellH - ih) / 2 : 0)
      ctx.drawImage(img, dx, dy, iw, ih)
    })
  }
}

function drawPreview() {
  const canvas = previewCanvas.value
  if (!canvas || items.value.length < 2) return
  const imgs = items.value.map(i => i.img)
  const info = calcLayout(imgs)
  const MAX = 800
  const scale = Math.min(1, MAX / Math.max(info.W, info.H))
  renderToCanvas(canvas, imgs, info, scale)
  previewInfo.value = `输出尺寸：${info.W} × ${info.H} px`
}

async function doExport() {
  processing.value = true
  try {
    const imgs = items.value.map(i => i.img)
    const info = calcLayout(imgs)
    const canvas = document.createElement('canvas')
    renderToCanvas(canvas, imgs, info, 1)
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
.grid-badge {
  position: absolute;
  top: 2px; left: 4px;
  font-size: 10px;
  color: #6366f1;
  font-weight: 700;
  background: #eef2ff;
  border-radius: 3px;
  padding: 0 3px;
  line-height: 16px;
}
.remove-btn { width:20px;height:20px;border-radius:50%;border:1px solid #e2e8f0;background:#fff;font-size:12px;cursor:pointer;color:#94a3b8;transition:all .15s;display:flex;align-items:center;justify-content:center; }
.remove-btn:hover { background:#fee2e2;border-color:#fca5a5;color:#ef4444; }
.btn-secondary { padding:8px 16px;border-radius:8px;border:1px solid #6366f1;background:#fff;color:#6366f1;font-size:14px;font-weight:500;cursor:pointer;transition:all .15s; }
.btn-secondary:hover { background:#eef2ff; }
</style>
