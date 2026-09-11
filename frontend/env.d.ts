/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

// markdown-it 未附带类型声明，这里按项目实际用法补充最小声明
declare module 'markdown-it' {
  interface MarkdownItOptions {
    html?: boolean
    linkify?: boolean
    breaks?: boolean
    typographer?: boolean
    [key: string]: unknown
  }
  class MarkdownIt {
    constructor(options?: MarkdownItOptions)
    render(src: string, env?: unknown): string
  }
  export default MarkdownIt
}

// element-plus 的深路径 locale 导入无类型声明
declare module 'element-plus/dist/locale/zh-cn.mjs' {
  const locale: any
  export default locale
}
