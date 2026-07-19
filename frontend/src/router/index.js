import { createRouter, createWebHistory } from "vue-router";

const LandingView = () => import("../components/LandingView.vue");
const AppWorkspaceView = () => import("../views/AppWorkspaceView.vue");
const ReviewView = () => import("../views/ReviewView.vue");
const RetestView = () => import("../views/RetestView.vue");

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
      path: "/review",
      name: "review",
      component: ReviewView,
    },
    {
      path: "/review/retest",
      name: "retest",
      component: RetestView,
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
