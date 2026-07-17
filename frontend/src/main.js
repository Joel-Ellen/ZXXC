import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import router from "./router";
import "./style.css";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/motion.css";
import { initTheme } from "./composables/useTheme.js";
import { initErrorMonitoring } from "./services/errorMonitoring.js";
import { reportClientSessionStarted } from "./services/clientTelemetry.js";

initTheme();

async function bootstrap() {
  const app = createApp(App);
  app.use(createPinia());
  app.use(router);
  await initErrorMonitoring(app, router);
  app.mount("#app");
  void reportClientSessionStarted();
}

void bootstrap();
