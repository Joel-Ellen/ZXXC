<template>
  <div class="flex items-center justify-center min-h-screen bg-gradient-to-br from-gray-900 via-gray-950 to-indigo-950 px-4">
    <div class="w-full max-w-lg text-center">
      <div class="mb-8">
        <div class="text-sm text-gray-500 mb-2">冷启动画像构建</div>
        <div class="flex justify-center gap-1.5 mb-4">
          <div
            v-for="i in total"
            :key="i"
            :class="i <= collected ? 'bg-indigo-500' : 'bg-gray-700'"
            class="w-8 h-2 rounded-full transition"
          ></div>
        </div>
        <p class="text-gray-400 text-sm">{{ collected }} / {{ total }} 个维度已完成</p>
      </div>

      <div v-if="probe" class="bg-gray-900/80 border border-gray-800 rounded-2xl p-8 shadow-2xl text-left">
        <p class="text-xs text-indigo-400 font-medium uppercase tracking-wider mb-2">第 {{ collected + 1 }} 题</p>
        <p class="text-white text-lg font-medium mb-6">{{ probe.question }}</p>

        <div class="space-y-3">
          <button
            v-for="(opt, idx) in probe.options"
            :key="idx"
            :disabled="busy"
            class="w-full text-left px-4 py-3 bg-gray-800/60 border border-gray-700 rounded-xl text-gray-300 text-sm hover:border-indigo-500 hover:bg-gray-800 hover:text-white disabled:opacity-50 transition"
            @click="select(opt)"
          >{{ opt }}</button>
        </div>

        <div v-if="busy" class="flex items-center justify-center gap-2 mt-4 text-sm text-gray-400">
          <div class="w-4 h-4 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin"></div>
          提交中...
        </div>
      </div>

      <div v-else class="text-gray-500">
        <div class="w-8 h-8 mx-auto mb-3 border-2 border-gray-600 border-t-indigo-400 rounded-full animate-spin"></div>
        加载探针...
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  probe: Object,
  collected: Number,
  total: Number,
  busy: Boolean,
});
const emit = defineEmits(["submit"]);
function select(opt) { emit("submit", [opt]); }
</script>
