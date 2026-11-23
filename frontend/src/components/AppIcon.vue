<script setup lang="ts">
type IconName =
  | 'ticket'
  | 'clock'
  | 'settings'
  | 'book'
  | 'search'
  | 'arrow-right'
  | 'info'
  | 'chevron-down'
  | 'pencil'
  | 'logout'
  | 'grid'
  | 'plus'
  | 'check'
  | 'assistant'
  | 'upload'

defineProps<{ name: IconName; size?: number }>()
</script>

<template>
  <svg
    :width="size ?? 20"
    :height="size ?? 20"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.7"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <template v-if="name === 'grid'">
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </template>
    <template v-else-if="name === 'plus'"><path d="M12 5v14M5 12h14" /></template>
    <template v-else-if="name === 'upload'"><path d="M12 16V3m-5 5 5-5 5 5M4 15v5h16v-5" /></template>
    <template v-else-if="name === 'check'"><path d="m5 12 4 4L19 6" /></template>
    <template v-else-if="name === 'assistant'">
      <path d="M5 5.5h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H9l-5 3v-13a2 2 0 0 1 2-2Z" />
      <path d="m12 8-.8 2.2L9 11l2.2.8L12 14l.8-2.2L15 11l-2.2-.8L12 8Z" />
    </template>
    <template v-else-if="name === 'ticket'">
      <rect x="5" y="3.5" width="14" height="17.5" rx="2.2" />
      <path d="M9 3.5v3h6v-3" />
      <path d="M9 10h6M9 13.5h6M9 17h4" />
    </template>
    <template v-else-if="name === 'clock'">
      <circle cx="12" cy="12" r="8.2" />
      <path d="M12 7.5v5l3.2 1.9" />
    </template>
    <template v-else-if="name === 'settings'">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.2 12a7 7 0 0 0-.1-1.2l2-1.5-2-3.4-2.3 1a7 7 0 0 0-2-1.2L14.4 3h-4.8l-.4 2.7a7 7 0 0 0-2 1.2l-2.3-1-2 3.4 2 1.5a7 7 0 0 0 0 2.4l-2 1.5 2 3.4 2.3-1a7 7 0 0 0 2 1.2l.4 2.7h4.8l.4-2.7a7 7 0 0 0 2-1.2l2.3 1 2-3.4-2-1.5c.1-.4.1-.8.1-1.2Z" />
    </template>
    <template v-else-if="name === 'book'">
      <path d="M4 5.2A2.2 2.2 0 0 1 6.2 3H20v15.5H6.2A2.2 2.2 0 0 0 4 20.7V5.2Z" />
      <path d="M4 18.5V21M8 7.5h8M8 11h5" />
    </template>
    <template v-else-if="name === 'search'">
      <circle cx="10.8" cy="10.8" r="6.3" />
      <path d="m16 16 4.2 4.2" />
    </template>
    <template v-else-if="name === 'arrow-right'">
      <path d="M4.5 12h14M13 6.5l5.5 5.5L13 17.5" />
    </template>
    <template v-else-if="name === 'info'">
      <circle cx="12" cy="12" r="8.6" />
      <path d="M12 11v5.2M12 7.8h.01" />
    </template>
    <template v-else-if="name === 'chevron-down'">
      <path d="m6 9 6 6 6-6" />
    </template>
    <template v-else-if="name === 'pencil'">
      <path d="m4 20 4.2-1 10.6-10.6a2.1 2.1 0 0 0-3-3L5.2 16 4 20Z" />
      <path d="m14.2 6.8 3 3" />
    </template>
    <template v-else-if="name === 'logout'">
      <path d="M14 4h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-4" />
      <path d="m9 8-4 4 4 4M5 12h10" />
    </template>
  </svg>
</template>
