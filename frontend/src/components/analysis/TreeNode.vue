<script setup lang="ts">
import type { TreeItem } from '@/api/analysis'

const props = defineProps<{
  item: TreeItem
  activePath: string
  collapsed: Record<string, boolean>
}>()

const emit = defineEmits<{
  (e: 'select', path: string): void
  (e: 'toggle', path: string): void
  (e: 'delete', item: TreeItem): void
}>()

function isCollapsed(path: string): boolean {
  return !!props.collapsed[path]
}
</script>

<template>
  <div class="tree-node">
    <!-- 文件夹 -->
    <div v-if="item.type === 'dir'" class="month-head" @click="emit('toggle', item.path)">
      <span class="month-arrow" :class="{ open: !isCollapsed(item.path) }">▸</span>
      <span class="month-title">{{ item.name }}</span>
      <button
        class="del-btn"
        title="删除空文件夹"
        @click.stop="emit('delete', item)"
      >✕</button>
    </div>

    <!-- 文件 -->
    <div
      v-else
      class="date-item tree-file"
      :class="{ active: item.path === activePath }"
      @click="emit('select', item.path)"
    >
      <span class="date-dot"></span>
      <span class="date-text">{{ item.name.replace(/\.md$/i, '') }}</span>
      <button
        class="del-btn"
        title="删除文件"
        @click.stop="emit('delete', item)"
      >✕</button>
    </div>

    <!-- 子级 -->
    <div v-if="item.type === 'dir' && !isCollapsed(item.path)" class="tree-children">
      <TreeNode
        v-for="child in item.children || []"
        :key="child.path"
        :item="child"
        :active-path="activePath"
        :collapsed="collapsed"
        @select="(p) => emit('select', p)"
        @toggle="(p) => emit('toggle', p)"
        @delete="(i) => emit('delete', i)"
      />
    </div>
  </div>
</template>
