import { onBeforeUnmount, onMounted } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'

// 路由切换与关闭标签都可能丢失内存草稿，集中处理这两个离开入口。
export function useUnsavedChanges(hasChanges: () => boolean) {
  onBeforeRouteLeave(() => !hasChanges() || window.confirm('当前编辑或操作尚未完成，确定离开吗？'))

  function beforeUnload(event: BeforeUnloadEvent) {
    if (!hasChanges()) return
    event.preventDefault()
    event.returnValue = ''
  }

  onMounted(() => window.addEventListener('beforeunload', beforeUnload))
  onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
}
