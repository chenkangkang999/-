import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { ApiError, http } from "@/api/client";
import type { User } from "@/api/types";

export const useSessionStore = defineStore("session", () => {
  const user = ref<User | null>(null);
  const initialized = ref(false);
  const loading = ref(false);
  const displayName = computed(
    () => user.value?.profile?.display_name || user.value?.username || "",
  );
  let pending: Promise<void> | null = null;
  async function load(force = false) {
    if (initialized.value && !force) return;
    if (pending) return pending;
    pending = (async () => {
      loading.value = true;
      try {
        user.value = (await http.get("/accounts/me/")).data;
      } catch (error) {
        if (
          !(error instanceof ApiError) ||
          ![401, 403].includes(error.status || 0)
        )
          throw error;
        user.value = null;
      } finally {
        initialized.value = true;
        loading.value = false;
        pending = null;
      }
    })();
    return pending;
  }
  async function login(username: string, password: string) {
    await http.get("/accounts/csrf/");
    const { data } = await http.post("/accounts/login/", {
      username,
      password,
    });
    user.value = data.user || data;
    initialized.value = true;
  }
  async function logout() {
    await http.post("/accounts/logout/");
    user.value = null;
    initialized.value = true;
  }
  return { user, initialized, loading, displayName, load, login, logout };
});
