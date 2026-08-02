<script setup lang="ts">
import HeaderNav from './components/HeaderNav.vue'
import FooterBar from './components/FooterBar.vue'
</script>

<template>
  <div class="app">
    <HeaderNav />
    <main class="app-main">
      <router-view />
    </main>
    <FooterBar />
  </div>
</template>

<style scoped>
.app {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}
.app-main {
  flex: 1;
  padding: 24px;
}
</style>
