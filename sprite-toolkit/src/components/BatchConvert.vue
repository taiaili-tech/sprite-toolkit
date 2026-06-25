<!-- src/components/BatchConvert.vue -->
<template>
  <div>
    <h2 style="font-size:20px;font-weight:700;margin-bottom:16px;">批量格式转换</h2>

    <!-- 设置栏 -->
    <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:16px;">
      <span class="form-label" style="margin:0;">目标格式</span>
      <div style="display:flex;gap:6px;">
        <button v-for="f in formats" :key="f.value" class="preset-btn"
          :class="{ active: targetFormat === f.value }"
          @click="targetFormat = f.value">{{ f.label }}</button>
      </div>
      <template v-if="targetFormat !== 'png'">
        <span class="form-label tip" style="margin:0;" title="数值越高质量越好，文件越大">质量</span>
        <input type="range" v-model.number="quality" min="1" max="100" style="width:100px;" />
        <span style="font-size:13px;color:#6366f1;font-weight:600;min-width:32px;">{{ quality }}%</span>
      </template>
    </div>

    <!-- 上传区 -->
    <div class="upload-zone" :class="{ dragover: isDragging }"
      @click="fileInput.click()"
      @dragover.prevent="isDragging = true"
      @dragleave="isDragging = false"
      @drop.prevent="onDrop">
      <input ref="fileInput" type="file" accept="image/*" multiple @change="onFileChange" />
      <div v-if="!items.length">点击或拖入图片（PNG / JPG / WebP / GIF，支持批量）</div>
      <div v-else style="font-size:13px;">
        已载入 {{ items.length }} 张&nbsp;
        <span style="color:#6366f1;cursor:pointer;text-decoration:underline;" @click.stop="addMore">继续添加</span>
        &nbsp;/&nbsp;
        <span style="color:#ef4444;cursor:pointer;text-decoration:underline;" @click.stop="items=[]">清空</span>
      </div>
    </div>

    <!-- 文件列表 -->
    <div v-if="items.length" style="margin-top:16px;">
      <table class="convert-table">
        <thead>
          <tr>
            <th>文件名</th>
            <th>原始大小</th>
            <th>原格式</th>
            <th>转换后预估</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(item, idx) in items" :key="idx">
            <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" :title="item.name">{{ item.name }}</td>
            <td>{{ fmtSize(item.originalSize) }}</td>
            <td style="text-transform:uppercase;">{{ item.ext }}</td>
            <td>
              <span v-if="item.convertedSize != null" :style="{ color: item.convertedSize < item.originalSize ? '#16a34a' : '#dc2626' }">
                {{ fmtSize(item.convertedSize) }}
                <span style="font-size:11px;margin-left:4px;">
                  ({{ item.convertedSize < item.originalSize ? '↓' : '↑' }}{{ Math.round(Math.abs(item.convertedSize - item.originalSize) / item.originalSize * 100) }}%)
                </span>
              </span>
              <span v-else style="color:#94a3b8;">-</span>
            </td>
            <td>
              <button class="remove-btn" @click="items.splice(idx,1)" title="移除">×</button>
            </td>
          </tr>
        </tbody>
      </table>

      <div style="margin-top:16px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
        <button class="btn-primary" :disabled="processing" @click="doConvert">
          {{ processing ? `转换中… ${progressText}` : items.length === 1 ? '转换并下载' : `转换并下载 ZIP (${items.length} 张)` }}
        </button>
        <button class="btn-secondary" :disabled="processing" @click="doPreview">预估大小</button>
      </div>
    </div>

    <div v-if="error" class="error-msg">{{ error }}</div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { downloadAsZip } from '../utils/zipHelper.js'

const fileInput = ref(null)
const isDragging = ref(false)
const items = ref([])
const targetFormat = ref('jpg')
const quality = ref(85)
const processing = ref(false)
const progressText = ref('')
const error = ref('')

const formats = [
  { label: 'JPG', value: 'jpg' },
  { label: 'PNG', value: 'png' },
  { label: 'WebP', value: 'webp' },
]

function fmtSize(bytes) {
  if (bytes == null) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(2) + ' MB'
}

async function loadFiles(files) {
  for (const f of Array.from(files)) {
    if (!f.type.startsWith('image/')) continue
    const ext = f.name.split('.').pop().toLowerCase()
    items.value.push({ name: f.name, file: f, originalSize: f.size, ext, convertedSize: null })
  }
}

function onFileChange(e) { items.value = []; loadFiles(e.target.files); e.target.value = '' }
function addMore() { fileInput.value.click() }
function onDrop(e) { isDragging.value = false; loadFiles(e.dataTransfer.files) }

function imgToCanvas(file) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    const url = URL.createObjectURL(file)
    img.onload = () => { URL.revokeObjectURL(url); resolve(img) }
    img.onerror = reject
    img.src = url
  })
}

function canvasToBlob(canvas, fmt, q) {
  const mime = fmt === 'jpg' ? 'image/jpeg' : fmt === 'webp' ? 'image/webp' : 'image/png'
  const qVal = (fmt === 'png') ? undefined : q / 100
  return new Promise(res => canvas.toBlob(res, mime, qVal))
}

async function doPreview() {
  error.value = ''
  for (const item of items.value) {
    try {
      const img = await imgToCanvas(item.file)
      const canvas = document.createElement('canvas')
      canvas.width = img.naturalWidth; canvas.height = img.naturalHeight
      canvas.getContext('2d').drawImage(img, 0, 0)
      const blob = await canvasToBlob(canvas, targetFormat.value, quality.value)
      item.convertedSize = blob.size
    } catch {}
  }
}

async function doConvert() {
  if (!items.value.length) return
  processing.value = true; error.value = ''
  try {
    const results = []
    for (let i = 0; i < items.value.length; i++) {
      const item = items.value[i]
      progressText.value = `(${i + 1}/${items.value.length})`
      const img = await imgToCanvas(item.file)
      const canvas = document.createElement('canvas')
      canvas.width = img.naturalWidth; canvas.height = img.naturalHeight
      canvas.getContext('2d').drawImage(img, 0, 0)
      const blob = await canvasToBlob(canvas, targetFormat.value, quality.value)
      item.convertedSize = blob.size
      const baseName = item.name.replace(/\.[^.]+$/, '')
      results.push({ name: `${baseName}.${targetFormat.value}`, blob })
    }
    if (results.length === 1) {
      const a = document.createElement('a')
      a.href = URL.createObjectURL(results[0].blob)
      a.download = results[0].name; a.click()
    } else {
      await downloadAsZip(results, `converted_${targetFormat.value}.zip`)
    }
  } catch (e) {
    error.value = '转换失败：' + e.message
  } finally {
    processing.value = false; progressText.value = ''
  }
}
</script>

<style scoped>
.convert-table { width:100%; border-collapse:collapse; font-size:13px; }
.convert-table th { text-align:left; padding:8px 10px; background:#f8fafc; border-bottom:2px solid #e2e8f0; color:#64748b; font-weight:600; }
.convert-table td { padding:8px 10px; border-bottom:1px solid #f1f5f9; }
.convert-table tr:hover td { background:#fafafa; }
.remove-btn { width:22px;height:22px;border-radius:50%;border:1px solid #e2e8f0;background:#f8fafc;font-size:14px;cursor:pointer;color:#94a3b8;transition:all .15s; }
.remove-btn:hover { background:#fee2e2;border-color:#fca5a5;color:#ef4444; }
.btn-secondary { padding:8px 16px;border-radius:8px;border:1px solid #6366f1;background:#fff;color:#6366f1;font-size:14px;font-weight:500;cursor:pointer;transition:all .15s; }
.btn-secondary:hover { background:#eef2ff; }
.btn-secondary:disabled { opacity:.4;cursor:default; }
</style>
