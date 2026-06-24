<!-- src/App.vue -->
<template>
  <div>
    <header class="app-header">
      <div class="app-title">🖼 Sprite Toolkit</div>
      <nav class="tab-nav">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          class="tab-btn"
          :class="{ active: activeTab === tab.id }"
          @click="activeTab = tab.id"
        >{{ tab.label }}</button>
      </nav>
    </header>
    <main class="app-body">
      <GridCutter   v-if="activeTab === 'grid'"      />
      <GifToSprite  v-if="activeTab === 'gif2sprite'" />
      <SpriteToGif  v-if="activeTab === 'sprite2gif'" />
      <GifGridCut   v-if="activeTab === 'gifgrid'"   />
    </main>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import GridCutter  from './components/GridCutter.vue'
import GifToSprite from './components/GifToSprite.vue'
import SpriteToGif from './components/SpriteToGif.vue'
import GifGridCut  from './components/GifGridCut.vue'

const tabs = [
  { id: 'grid',       label: '宫格裁切' },
  { id: 'gif2sprite', label: 'GIF → 精灵图' },
  { id: 'sprite2gif', label: '精灵图 → GIF' },
  { id: 'gifgrid',    label: 'GIF 宫格裁切' },
]
const activeTab = ref('grid')
</script>
