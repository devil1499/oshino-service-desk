<script setup lang="ts">
import { statusLabels } from '../demo/workspace'
import type { TicketStatus } from '../demo/workspace'
defineProps<{ status: TicketStatus }>()
</script>

<template><span class="status-badge" :class="status"><i />{{ statusLabels[status] }}</span></template>
