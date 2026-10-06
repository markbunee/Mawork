// echarts 按需加载器
//
// echarts 压缩后约 1.1MB，若在组件里静态 `import * as echarts from 'echarts'`，
// 它会被打进主包，首屏白白多下载 1MB+（多数页面根本用不到图表）。
// 这里统一改成动态 import：
//   1. echarts 被拆成独立 chunk，只在真正渲染图表时才下载；
//   2. 多个图表组件共用同一个模块实例，不会重复加载；
//   3. 组件侧只需 `await loadEcharts()`，无需各自写 dynamic import 样板。

type EChartsModule = typeof import('echarts')

let cached: EChartsModule | null = null
let pending: Promise<EChartsModule> | null = null

/** 动态加载 echarts；并发调用共享同一个 Promise，保证只加载一次。 */
export function loadEcharts(): Promise<EChartsModule> {
  if (cached) return Promise.resolve(cached)
  if (!pending) {
    pending = import('echarts').then((m) => {
      cached = m
      return m
    })
  }
  return pending
}

/** 供组件标注图表实例类型（type-only，编译期擦除，不产生运行时依赖） */
export type { ECharts } from 'echarts'
