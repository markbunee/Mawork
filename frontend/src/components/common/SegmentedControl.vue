<script setup lang="ts">
/**
 * SegmentedControl — 通用分段控件（带滑动指示块）
 *
 * 用途：模块 / 视图切换。已在「知识」「日程」「复盘」三处复用。
 *
 * 设计要点：
 * - 指示块宽度按 items.length 动态计算（calc((100% - 6px) / N)），
 *   新增/减少项无需改样式，避免各处写死 1/2、1/3、1/5。
 * - 位移用 translateX(index * 100%)，100% 即指示块自身宽度，天然对齐。
 * - 受控组件：v-model 传入当前 key。
 */
import { computed } from 'vue'
import '@/styles/segmented.css'

export interface SegItem {
  key: string
  label: string
  /** 可选图标（emoji 或字符） */
  icon?: string
}

const props = defineProps<{
  items: SegItem[]
  modelValue: string
  /** 无障碍标签 */
  ariaLabel?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [key: string] }>()

const activeIndex = computed(() => {
  const i = props.items.findIndex((it) => it.key === props.modelValue)
  return i < 0 ? 0 : i
})

/** 指示块宽度：容器减去左右 3px padding 后 N 等分 */
const indicatorStyle = computed(() => ({
  width: `calc((100% - 6px) / ${props.items.length})`,
  transform: `translateX(${activeIndex.value * 100}%)`,
}))
</script>

<template>
  <div class="seg" role="tablist" :aria-label="ariaLabel">
    <span class="seg-ind" :style="indicatorStyle"></span>
    <button
      v-for="it in items"
      :key="it.key"
      type="button"
      class="seg-tab"
      :class="{ on: modelValue === it.key }"
      role="tab"
      :aria-selected="modelValue === it.key"
      @click="emit('update:modelValue', it.key)"
    >
      <span v-if="it.icon" class="seg-icon">{{ it.icon }}</span>
      <span class="seg-label">{{ it.label }}</span>
    </button>
  </div>
</template>
