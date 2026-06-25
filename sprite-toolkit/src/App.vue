<!-- src/App.vue -->
<template>
  <div>
    <header class="app-header">
      <div class="app-title">🖼 Sprite Toolkit</div>
      <nav class="tab-nav">
        <div class="tab-group">
          <span class="tab-group-label">精灵图</span>
          <button v-for="tab in spriteTabs" :key="tab.id" class="tab-btn"
            :class="{ active: activeTab === tab.id }"
            @click="activeTab = tab.id">{{ tab.label }}</button>
        </div>
        <div class="tab-group-divider"></div>
        <div class="tab-group">
          <span class="tab-group-label">图片处理</span>
          <button v-for="tab in imageTabs" :key="tab.id" class="tab-btn"
            :class="{ active: activeTab === tab.id }"
            @click="activeTab = tab.id">{{ tab.label }}</button>
        </div>
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

const spriteTabs = [
  { id: 'grid',       label: '宫格裁切' },
  { id: 'gif2sprite', label: 'GIF → 精灵图' },
  { id: 'sprite2gif', label: '精灵图 → GIF' },
]
const imageTabs = [
  { id: 'convert',  label: '格式转换' },
  { id: 'compress', label: '批量压缩' },
  { id: 'stitch',   label: '图片拼接' },
  { id: 'pad',      label: '加画布' },
  { id: 'base64',   label: 'Base64' },
]
const activeTab = ref('grid')
</script>

<style>
.tab-nav {
  display: flex;
  align-items: center;
  gap: 0;
  flex-wrap: wrap;
  row-gap: 4px;
}
.tab-group {
  display: flex;
  align-items: center;
  gap: 4px;
}
.tab-group-label {
  font-size: 11px;
  color: #94a3b8;
  font-weight: 500;
  padding: 0 6px;
  white-space: nowrap;
}
.tab-group-divider {
  width: 1px;
  height: 20px;
  background: #e2e8f0;
  margin: 0 8px;
}
</style>
