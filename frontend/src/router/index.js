import { createRouter, createWebHistory } from "vue-router";

const LandingView = () => import("../components/LandingView.vue");
const AppWorkspaceView = () => import("../views/AppWorkspaceView.vue");

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "landing",
      component: LandingView,
    },
    {
      path: "/app",
      name: "app-workspace",
      component: AppWorkspaceView,
    },
    {
      path: "/:pathMatch(.*)*",
      redirect: "/",
    },
  ],
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) {
      return savedPosition;
    }

    if (to.hash) {
      return { el: to.hash, behavior: "smooth" };
    }

    return { top: 0 };
  },
});

export default router;
