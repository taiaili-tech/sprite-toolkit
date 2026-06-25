<!-- src/App.vue -->
<template>
  <div>
    <header class="app-header">
      <div class="app-title">🖼 Sprite Toolkit</div>
      <nav class="tab-nav">
        <button v-for="tab in allTabs" :key="tab.id" class="tab-btn"
          :class="{ active: activeTab === tab.id }"
          @click="activeTab = tab.id">{{ tab.label }}</button>
      </nav>
    </header>
    <main class="app-body">
      <GridCutter     v-if="activeTab === 'grid'" />
      <GifToSprite    v-if="activeTab === 'gif2sprite'" />
      <SpriteToGif    v-if="activeTab === 'sprite2gif'" />
      <BatchConvert   v-if="activeTab === 'convert'" />
      <BatchCompress  v-if="activeTab === 'compress'" />
      <ImageStitch    v-if="activeTab === 'stitch'" />
      <CanvasPad      v-if="activeTab === 'pad'" />
      <Base64Tool     v-if="activeTab === 'base64'" />
    </main>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import GridCutter    from './components/GridCutter.vue'
import GifToSprite   from './components/GifToSprite.vue'
import SpriteToGif   from './components/SpriteToGif.vue'
import BatchConvert  from './components/BatchConvert.vue'
import BatchCompress from './components/BatchCompress.vue'
import ImageStitch   from './components/ImageStitch.vue'
import CanvasPad     from './components/CanvasPad.vue'
import Base64Tool    from './components/Base64Tool.vue'

const allTabs = [
  { id: 'grid',       label: '宫格裁切' },
  { id: 'gif2sprite', label: 'GIF → 精灵图' },
  { id: 'sprite2gif', label: '精灵图 → GIF' },
  { id: 'convert',    label: '格式转换' },
  { id: 'compress',   label: '批量压缩' },
  { id: 'stitch',     label: '图片拼接' },
  { id: 'pad',        label: '加画布' },
  { id: 'base64',     label: 'Base64' },
]
const activeTab = ref('grid')
</script>

