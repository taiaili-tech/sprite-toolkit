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
      <input ref="fileInput" type="file" accept="image/*" multiple @change="onFileChange" />
      <div v-if="fileList.length === 0">点击或拖入图片（支持多文件批量，PNG / JPG / WebP / GIF）</div>
      <div v-else style="font-size:13px;">
        已载入 {{ fileList.length }} 张图片&nbsp;
        <span style="color:#6366f1;cursor:pointer;text-decoration:underline;" @click.stop="fileInput.click()">继续添加 / 重新选择</span>
      </div>
      <div class="upload-hint">GIF 只取第一帧</div>
    </div>

    <div v-if="error" class="error-msg">{{ error }}</div>

    <!-- 图片列表 -->
    <div v-if="fileList.length" style="margin-top:16px;display:flex;flex-direction:column;gap:16px;">
      <div
        v-for="(item, idx) in fileList"
        :key="idx"
        class="item-card"
        :class="{ active: currentIdx === idx }"
        @click="currentIdx = idx"
      >
        <!-- 标题栏 -->
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
          <span style="font-size:13px;font-weight:600;color:#374151;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
            {{ item.name }}
          </span>
          <span style="font-size:11px;color:#94a3b8;">{{ item.imgEl.naturalWidth }}×{{ item.imgEl.naturalHeight }}</span>
          <button class="remove-btn" @click.stop="removeFile(idx)" title="移除">×</button>
        </div>

        <!-- 行列设置 -->
        <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:8px;">
          <button
            v-for="p in gridPresets"
            :key="p.label"
            class="preset-btn"
            :class="{ active: fileList[idx].pendingRows === p.rows && fileList[idx].pendingCols === p.cols }"
            @click.stop="setPending(idx, p.rows, p.cols)"
          >{{ p.label }}</button>
        </div>
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;line-height:32px;">
          <span class="form-label" style="min-width:auto;">行 × 列</span>
          <input class="form-input" type="number" v-model.number="fileList[idx].pendingRows" min="1" max="20" style="width:60px;" @click.stop />
          <span style="color:#94a3b8;">×</span>
          <input class="form-input" type="number" v-model.number="fileList[idx].pendingCols" min="1" max="20" style="width:60px;" @click.stop />
          <button class="confirm-btn" @click.stop="confirmSettings(idx)">✓ 确认</button>
          <span style="font-size:12px;color:#94a3b8;">
            已应用：{{ fileList[idx].rows }}×{{ fileList[idx].cols }}
            &nbsp;每格 {{ Math.floor(item.imgEl.naturalWidth / fileList[idx].cols) }}×{{ Math.floor(item.imgEl.naturalHeight / fileList[idx].rows) }} px
          </span>
        </div>

        <!-- 预览 -->
        <div class="preview-wrap" style="margin-top:10px;">
          <canvas :ref="el => { if(el) canvasRefs[idx] = el }"></canvas>
        </div>
      </div>
    </div>

    <!-- 批量操作 -->
    <div v-if="fileList.length" style="margin-top:20px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
      <button class="btn-primary" :disabled="processing" @click="doProcess">
        {{ processing
          ? `处理中… ${progressText}`
          : fileList.length > 1
            ? `批量裁切 ${fileList.length} 张并下载 ZIP`
            : '裁切并下载 ZIP' }}
      </button>
      <button
        v-if="fileList.length > 1"
        class="btn-secondary"
        @click="applyToAll"
        title="将当前选中图片的已确认行列应用到所有图片"
      >
        同步当前设置到全部
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import { cropToBlob, fileToImage } from '../utils/canvasCrop.js'
import { downloadAsZip } from '../utils/zipHelper.js'

const fileInput = ref(null)
const fileList = ref([])   // [{ name, imgEl, rows, cols }]
const canvasRefs = ref([])
const currentIdx = ref(0)
const isDragging = ref(false)
const error = ref('')
const processing = ref(false)
const progressText = ref('')

const gridPresets = [
  { label: '2×2', rows: 2, cols: 2 },
  { label: '3×3', rows: 3, cols: 3 },
  { label: '4×4', rows: 4, cols: 4 },
  { label: '2×3', rows: 2, cols: 3 },
  { label: '3×2', rows: 3, cols: 2 },
  { label: '1×2', rows: 1, cols: 2 },
  { label: '2×1', rows: 2, cols: 1 },
]

function setPending(idx, r, c) {
  fileList.value[idx].pendingRows = r
  fileList.value[idx].pendingCols = c
}

function confirmSettings(idx) {
  fileList.value[idx].rows = fileList.value[idx].pendingRows
  fileList.value[idx].cols = fileList.value[idx].pendingCols
  nextTick(() => drawPreview(idx))
}

async function loadFiles(files) {
  error.value = ''
  const arr = Array.from(files)
  for (const f of arr) {
    try {
      const imgEl = await fileToImage(f)
      fileList.value.push({ name: f.name, imgEl, rows: 3, cols: 3, pendingRows: 3, pendingCols: 3 })
    } catch (e) {
      error.value = `${f.name} 加载失败：${e.message}`
    }
  }
  await nextTick()
  fileList.value.forEach((_, i) => drawPreview(i))
}

function onFileChange(e) { if (e.target.files.length) loadFiles(e.target.files); e.target.value = '' }
function onDrop(e) { isDragging.value = false; if (e.dataTransfer.files.length) loadFiles(e.dataTransfer.files) }
function removeFile(idx) {
  fileList.value.splice(idx, 1)
  canvasRefs.value.splice(idx, 1)
  if (currentIdx.value >= fileList.value.length) currentIdx.value = Math.max(0, fileList.value.length - 1)
}

function drawPreview(idx) {
  const canvas = canvasRefs.value[idx]
  const item = fileList.value[idx]
  if (!canvas || !item) return
  const img = item.imgEl
  const MAX = 500
  const scale = Math.min(1, MAX / Math.max(img.naturalWidth, img.naturalHeight))
  canvas.width = img.naturalWidth * scale
  canvas.height = img.naturalHeight * scale
  const ctx = canvas.getContext('2d')
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
  ctx.strokeStyle = 'rgba(79,70,229,0.7)'
  ctx.lineWidth = 1
  const cw = canvas.width / item.cols
  const ch = canvas.height / item.rows
  for (let r = 1; r < item.rows; r++) {
    ctx.beginPath(); ctx.moveTo(0, r * ch); ctx.lineTo(canvas.width, r * ch); ctx.stroke()
  }
  for (let c = 1; c < item.cols; c++) {
    ctx.beginPath(); ctx.moveTo(c * cw, 0); ctx.lineTo(c * cw, canvas.height); ctx.stroke()
  }
}

function applyToAll() {
  const cur = fileList.value[currentIdx.value]
  if (!cur) return
  fileList.value.forEach((item, i) => {
    item.rows = cur.rows
    item.cols = cur.cols
    item.pendingRows = cur.rows
    item.pendingCols = cur.cols
    nextTick(() => drawPreview(i))
  })
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
      const cw = Math.floor(img.naturalWidth / item.cols)
      const ch = Math.floor(img.naturalHeight / item.rows)
      const baseName = fileList.value.length > 1
        ? item.name.replace(/\.[^.]+$/, '')
        : ''
      for (let r = 0; r < item.rows; r++) {
        for (let c = 0; c < item.cols; c++) {
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
.item-card {
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 14px;
  background: #fff;
  cursor: pointer;
  transition: border-color .15s, box-shadow .15s;
}
.item-card:hover { border-color: #a5b4fc; }
.item-card.active { border-color: #6366f1; box-shadow: 0 0 0 3px rgba(99,102,241,0.1); }
.remove-btn {
  width: 22px; height: 22px; border-radius: 50%;
  border: 1px solid #e2e8f0; background: #f8fafc;
  font-size: 14px; cursor: pointer; line-height: 1;
  display: flex; align-items: center; justify-content: center;
  color: #94a3b8; flex-shrink: 0;
  transition: all .15s;
}
.remove-btn:hover { background: #fee2e2; border-color: #fca5a5; color: #ef4444; }
.btn-secondary {
  padding: 8px 16px; border-radius: 8px;
  border: 1px solid #6366f1; background: #fff;
  color: #6366f1; font-size: 14px; font-weight: 500;
  cursor: pointer; transition: all .15s;
}
.btn-secondary:hover { background: #eef2ff; }
.confirm-btn {
  padding: 4px 12px; border-radius: 6px;
  border: 1px solid #6366f1; background: #eef2ff;
  color: #4338ca; font-size: 13px; font-weight: 600;
  cursor: pointer; transition: all .15s;
}
.confirm-btn:hover { background: #6366f1; color: #fff; }
</style>
