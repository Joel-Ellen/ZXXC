import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import router from "./router";
import "./style.css";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/motion.css";
import { initTheme } from "./composables/useTheme.js";

initTheme();

createApp(App)
  .use(createPinia())
  .use(router)
  .mount("#app");
