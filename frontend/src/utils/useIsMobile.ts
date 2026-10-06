import { ref, onMounted, onUnmounted } from 'vue'

/**
 * 响应式断点判断。
 * 关键：只在组件挂载后（浏览器环境）读取 matchMedia，SSR/构建期不会报错；
 * 桌面端（>breakpoint）始终返回 false，保证桌面行为完全不变。
 */
export function useIsMobile(breakpoint = 768) {
  const isMobile = ref(false)
  let mql: MediaQueryList | null = null
  const update = () => {
    if (mql) isMobile.value = mql.matches
  }
  onMounted(() => {
    mql = window.matchMedia(`(max-width: ${breakpoint}px)`)
    update()
    mql.addEventListener('change', update)
  })
  onUnmounted(() => mql?.removeEventListener('change', update))
  return isMobile
}
