<script setup lang="ts">
/**
 * 应用根组件。
 *
 * 只做一件事：把页面挂上去。
 * 具体的布局（顶栏、列表、内容区）在 AppShell 里，
 * 因为布局需要知道当前在哪个模块，而根组件不需要。
 */
</script>

<template>
  <RouterView />
</template>
