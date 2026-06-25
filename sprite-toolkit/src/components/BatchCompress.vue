<!-- src/components/BatchCompress.vue -->
<template>
  <div>
    <h2 style="font-size:20px;font-weight:700;margin-bottom:16px;">批量压缩</h2>

    <!-- 压缩设置 -->
    <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:16px;">
      <span class="form-label" style="margin:0;">压缩方式</span>
      <button class="preset-btn" :class="{ active: mode === 'quality' }" @click="mode='quality'">指定质量</button>
      <button class="preset-btn" :class="{ active: mode === 'size' }" @click="mode='size'">限制大小</button>

      <template v-if="mode === 'quality'">
        <span class="form-label tip" style="margin:0;" title="数值越高质量越好，文件越大">质量</span>
        <input type="range" v-model.number="quality" min="1" max="99" style="width:120px;" />
        <span style="font-size:13px;color:#6366f1;font-weight:600;min-width:32px;">{{ quality }}%</span>
      </template>
      <template v-else>
        <span class="form-label" style="margin:0;">每张不超过</span>
        <input class="form-input" type="number" v-model.number="maxKB" min="10" style="width:80px;" />
        <span style="font-size:13px;color:#64748b;">KB</span>
      </template>

      <span class="form-label" style="margin:0;margin-left:8px;">输出格式</span>
      <button v-for="f in formats" :key="f.v" class="preset-btn"
        :class="{ active: outFmt === f.v }" @click="outFmt = f.v">{{ f.l }}</button>
    </div>

    <!-- 上传区 -->
    <div class="upload-zone" :class="{ dragover: isDragging }"
      @click="fileInput.click()"
      @dragover.prevent="isDragging = true"
      @dragleave="isDragging = false"
      @drop.prevent="onDrop">
      <input ref="fileInput" type="file" accept="image/png,image/jpeg,image/webp" multiple @change="onFileChange" />
      <div v-if="!items.length">点击或拖入图片（PNG / JPG / WebP，支持批量）</div>
      <div v-else style="font-size:13px;">
        已载入 {{ items.length }} 张&nbsp;
        <span style="color:#6366f1;cursor:pointer;text-decoration:underline;" @click.stop="fileInput.click()">继续添加</span>
        &nbsp;/&nbsp;
        <span style="color:#ef4444;cursor:pointer;text-decoration:underline;" @click.stop="items=[]">清空</span>
      </div>
    </div>

    <!-- 结果表格 -->
    <div v-if="items.length" style="margin-top:16px;">
      <table class="compress-table">
        <thead>
          <tr>
            <th>文件名</th>
            <th>原始大小</th>
            <th>压缩后</th>
            <th>压缩率</th>
            <th>状态</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(item, idx) in items" :key="idx">
            <td style="max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" :title="item.name">{{ item.name }}</td>
            <td>{{ fmtSize(item.originalSize) }}</td>
            <td>
              <span v-if="item.compressedSize != null" :style="{ color: item.compressedSize < item.originalSize ? '#16a34a' : '#dc2626' }">
                {{ fmtSize(item.compressedSize) }}
              </span>
              <span v-else style="color:#94a3b8;">-</span>
            </td>
            <td>
              <span v-if="item.ratio != null" style="font-weight:600;" :style="{ color: item.ratio > 0 ? '#16a34a' : '#dc2626' }">
                {{ item.ratio > 0 ? '-' : '+' }}{{ Math.abs(item.ratio) }}%
              </span>
              <span v-else style="color:#94a3b8;">-</span>
            </td>
            <td>
              <span v-if="item.status === 'done'" style="color:#16a34a;">✓ 完成</span>
              <span v-else-if="item.status === 'processing'" style="color:#6366f1;">处理中…</span>
              <span v-else-if="item.status === 'skip'" style="color:#f59e0b;" title="压缩后比原文件大，已保留原图">已保留原图</span>
              <span v-else style="color:#94a3b8;">等待</span>
            </td>
            <td><button class="remove-btn" @click="items.splice(idx,1)">×</button></td>
          </tr>
        </tbody>
      </table>

      <!-- 汇总 -->
      <div v-if="summary" style="margin-top:10px;padding:10px 14px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;font-size:13px;color:#166534;">
        {{ summary }}
      </div>

      <div style="margin-top:16px;display:flex;gap:10px;align-items:center;">
        <button class="btn-primary" :disabled="processing" @click="doCompress">
          {{ processing ? `压缩中… ${progressText}` : `开始压缩并下载 (${items.length} 张)` }}
        </button>
      </div>
    </div>

    <div v-if="error" class="error-msg">{{ error }}</div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { downloadAsZip } from '../utils/zipHelper.js'

const fileInput = ref(null)
const isDragging = ref(false)
const items = ref([])
const mode = ref('quality')
const quality = ref(80)
const maxKB = ref(200)
const outFmt = ref('jpg')
const processing = ref(false)
const progressText = ref('')
const error = ref('')

const formats = [{ l: 'JPG', v: 'jpg' }, { l: 'WebP', v: 'webp' }]

function fmtSize(b) {
  if (b == null) return '-'
  if (b < 1024) return b + ' B'
  if (b < 1048576) return (b / 1024).toFixed(1) + ' KB'
  return (b / 1048576).toFixed(2) + ' MB'
}

const summary = computed(() => {
  const done = items.value.filter(i => i.status === 'done' || i.status === 'skip')
  if (!done.length) return ''
  const origTotal = done.reduce((s, i) => s + i.originalSize, 0)
  const compTotal = done.reduce((s, i) => s + (i.compressedSize ?? i.originalSize), 0)
  const saved = origTotal - compTotal
  const pct = Math.round(saved / origTotal * 100)
  return `共处理 ${done.length} 张，总计节省 ${fmtSize(saved)}（${pct}%），${fmtSize(origTotal)} → ${fmtSize(compTotal)}`
})

function loadFiles(files) {
  for (const f of Array.from(files)) {
    if (!f.type.startsWith('image/')) continue
    items.value.push({ name: f.name, file: f, originalSize: f.size, compressedSize: null, ratio: null, status: 'pending' })
  }
}
function onFileChange(e) { items.value = []; loadFiles(e.target.files); e.target.value = '' }
function onDrop(e) { isDragging.value = false; loadFiles(e.dataTransfer.files) }

function imgToCanvas(file) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    const url = URL.createObjectURL(file)
    img.onload = () => { URL.revokeObjectURL(url); resolve(img) }
    img.onerror = reject; img.src = url
  })
}

function canvasToBlob(canvas, q) {
  const mime = outFmt.value === 'webp' ? 'image/webp' : 'image/jpeg'
  return new Promise(res => canvas.toBlob(res, mime, q / 100))
}

async function compressByQuality(canvas, q) { return canvasToBlob(canvas, q) }

async function compressBySize(canvas, targetBytes) {
  let lo = 1, hi = 99, blob = null
  for (let i = 0; i < 8; i++) {
    const mid = Math.round((lo + hi) / 2)
    blob = await canvasToBlob(canvas, mid)
    if (blob.size <= targetBytes) lo = mid + 1
    else hi = mid - 1
    if (lo > hi) break
  }
  // final at lo-1
  blob = await canvasToBlob(canvas, Math.max(1, lo - 1))
  return blob
}

async function doCompress() {
  if (!items.value.length) return
  processing.value = true; error.value = ''
  try {
    const zipEntries = []
    for (let i = 0; i < items.value.length; i++) {
      const item = items.value[i]
      item.status = 'processing'
      progressText.value = `(${i + 1}/${items.value.length})`
      const img = await imgToCanvas(item.file)
      const canvas = document.createElement('canvas')
      canvas.width = img.naturalWidth; canvas.height = img.naturalHeight
      canvas.getContext('2d').drawImage(img, 0, 0)
      let blob
      if (mode.value === 'quality') {
        blob = await compressByQuality(canvas, quality.value)
      } else {
        blob = await compressBySize(canvas, maxKB.value * 1024)
      }
      const useOriginal = blob.size >= item.originalSize
      const finalBlob = useOriginal ? item.file : blob
      item.compressedSize = blob.size
      item.ratio = Math.round((item.originalSize - blob.size) / item.originalSize * 100)
      item.status = useOriginal ? 'skip' : 'done'
      const baseName = item.name.replace(/\.[^.]+$/, '')
      zipEntries.push({ name: `${baseName}.${outFmt.value}`, blob: finalBlob })
    }
    await downloadAsZip(zipEntries, 'compressed.zip')
  } catch (e) {
    error.value = '压缩失败：' + e.message
  } finally {
    processing.value = false; progressText.value = ''
  }
}
</script>

<style scoped>
.compress-table { width:100%;border-collapse:collapse;font-size:13px; }
.compress-table th { text-align:left;padding:8px 10px;background:#f8fafc;border-bottom:2px solid #e2e8f0;color:#64748b;font-weight:600; }
.compress-table td { padding:8px 10px;border-bottom:1px solid #f1f5f9; }
.compress-table tr:hover td { background:#fafafa; }
.remove-btn { width:22px;height:22px;border-radius:50%;border:1px solid #e2e8f0;background:#f8fafc;font-size:14px;cursor:pointer;color:#94a3b8;transition:all .15s; }
.remove-btn:hover { background:#fee2e2;border-color:#fca5a5;color:#ef4444; }
</style>
