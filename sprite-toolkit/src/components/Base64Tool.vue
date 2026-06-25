<!-- src/components/Base64Tool.vue -->
<template>
  <div>
    <h2 style="font-size:20px;font-weight:700;margin-bottom:16px;">Base64 互转</h2>

    <!-- 模式切换 -->
    <div style="display:flex;gap:8px;margin-bottom:20px;">
      <button class="mode-btn" :class="{ active: mode === 'img2b64' }" @click="mode='img2b64'">图片 → Base64</button>
      <button class="mode-btn" :class="{ active: mode === 'b642img' }" @click="mode='b642img'">Base64 → 图片</button>
    </div>

    <!-- 图片 → Base64 -->
    <template v-if="mode === 'img2b64'">
      <div class="upload-zone" :class="{ dragover: isDragging }"
        @click="fileInput.click()"
        @dragover.prevent="isDragging = true"
        @dragleave="isDragging = false"
        @drop.prevent="onDrop">
        <input ref="fileInput" type="file" accept="image/*" @change="onFileChange" />
        <div v-if="!b64result">点击或拖入任意图片</div>
        <div v-else style="font-size:13px;">{{ imgName }}&nbsp;<span style="color:#6366f1;cursor:pointer;text-decoration:underline;" @click.stop="fileInput.click()">重新选择</span></div>
      </div>

      <div v-if="b64result" style="margin-top:16px;">
        <!-- 预览 -->
        <div style="display:flex;gap:20px;flex-wrap:wrap;margin-bottom:16px;">
          <div class="preview-wrap" style="flex:0 0 auto;">
            <div class="preview-label">图片预览</div>
            <img :src="b64result" style="max-width:200px;max-height:200px;object-fit:contain;display:block;" />
          </div>
          <div style="flex:1;min-width:200px;">
            <div style="font-size:13px;color:#64748b;margin-bottom:6px;">
              文件：{{ imgName }}｜大小：{{ fmtSize(b64result.length * 0.75) }}｜字符数：{{ b64result.length.toLocaleString() }}
            </div>
            <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px;">
              <button class="btn-primary" @click="copyB64(b64result)">{{ copied === 'full' ? '✓ 已复制' : '复制完整 Base64（含前缀）' }}</button>
              <button class="btn-secondary" @click="copyB64(b64result.split(',')[1])">{{ copied === 'raw' ? '✓ 已复制' : '仅复制数据部分' }}</button>
            </div>
          </div>
        </div>

        <!-- 文本框 -->
        <textarea
          :value="b64result"
          readonly
          style="width:100%;height:120px;font-size:11px;font-family:monospace;border:1px solid #e2e8f0;border-radius:8px;padding:10px;resize:vertical;box-sizing:border-box;background:#f8fafc;color:#374151;"
        />
      </div>
    </template>

    <!-- Base64 → 图片 -->
    <template v-else>
      <div style="margin-bottom:12px;">
        <textarea
          v-model="b64input"
          placeholder="粘贴 Base64 字符串（支持带 data:image/xxx;base64, 前缀或纯数据）"
          style="width:100%;height:120px;font-size:11px;font-family:monospace;border:1px solid #e2e8f0;border-radius:8px;padding:10px;resize:vertical;box-sizing:border-box;"
          @input="onB64Input"
        />
        <div style="margin-top:6px;display:flex;gap:8px;">
          <button class="btn-primary" @click="parseB64">解析预览</button>
          <button class="preset-btn" @click="b64input='';previewSrc=''">清空</button>
        </div>
      </div>

      <div v-if="b64error" class="error-msg">{{ b64error }}</div>

      <div v-if="previewSrc" style="margin-top:16px;">
        <div class="preview-wrap" style="display:inline-block;">
          <div class="preview-label">图片预览</div>
          <img :src="previewSrc" style="max-width:400px;max-height:300px;object-fit:contain;display:block;" />
        </div>
        <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;">
          <button class="btn-primary" @click="downloadImg">下载图片</button>
          <span style="font-size:12px;color:#64748b;align-self:center;">{{ detectedType || '' }}</span>
        </div>
      </div>
    </template>

    <div v-if="error" class="error-msg">{{ error }}</div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const fileInput = ref(null)
const isDragging = ref(false)
const mode = ref('img2b64')
const b64result = ref('')
const imgName = ref('')
const copied = ref('')
const b64input = ref('')
const previewSrc = ref('')
const b64error = ref('')
const detectedType = ref('')
const error = ref('')

function fmtSize(b) {
  if (b < 1024) return Math.round(b) + ' B'
  if (b < 1048576) return (b / 1024).toFixed(1) + ' KB'
  return (b / 1048576).toFixed(2) + ' MB'
}

function loadFile(f) {
  if (!f.type.startsWith('image/')) return
  imgName.value = f.name
  const reader = new FileReader()
  reader.onload = e => { b64result.value = e.target.result }
  reader.readAsDataURL(f)
}

function onFileChange(e) { if (e.target.files[0]) loadFile(e.target.files[0]) }
function onDrop(e) { isDragging.value = false; if (e.dataTransfer.files[0]) loadFile(e.dataTransfer.files[0]) }

async function copyB64(text) {
  try {
    await navigator.clipboard.writeText(text)
    copied.value = text === b64result.value ? 'full' : 'raw'
    setTimeout(() => { copied.value = '' }, 2000)
  } catch { error.value = '复制失败，请手动选择文本复制' }
}

function onB64Input() { b64error.value = ''; previewSrc.value = '' }

function parseB64() {
  b64error.value = ''; previewSrc.value = ''
  let str = b64input.value.trim()
  if (!str) return
  if (!str.startsWith('data:')) {
    // try common image types
    const types = ['image/png', 'image/jpeg', 'image/gif', 'image/webp']
    let valid = false
    for (const t of types) {
      const test = `data:${t};base64,${str}`
      const img = new Image()
      img.src = test
      if (img.src) { str = test; detectedType.value = t; valid = true; break }
    }
    if (!valid) str = `data:image/png;base64,${str}`
  } else {
    detectedType.value = str.split(';')[0].replace('data:', '')
  }
  const img = new Image()
  img.onload = () => { previewSrc.value = str }
  img.onerror = () => { b64error.value = '解析失败，请检查 Base64 字符串是否完整' }
  img.src = str
}

function downloadImg() {
  const ext = detectedType.value.split('/')[1] || 'png'
  const a = document.createElement('a')
  a.href = previewSrc.value
  a.download = `image.${ext}`
  a.click()
}
</script>

<style scoped>
.mode-btn { padding:7px 18px;border-radius:8px;border:1px solid #e2e8f0;background:#f8fafc;font-size:14px;cursor:pointer;transition:all .15s; }
.mode-btn.active { border-color:#6366f1;background:#eef2ff;color:#4338ca;font-weight:600; }
.btn-secondary { padding:8px 16px;border-radius:8px;border:1px solid #6366f1;background:#fff;color:#6366f1;font-size:14px;font-weight:500;cursor:pointer;transition:all .15s; }
.btn-secondary:hover { background:#eef2ff; }
</style>
