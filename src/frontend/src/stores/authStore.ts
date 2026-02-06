import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { User, Guild } from "@/types";

interface AuthStore {
  token: string | null;
  user: User | null;
  guilds: Guild[];
  setAuth: (token: string, user: User, guilds: Guild[]) => void;
  logout: () => void;
  isAuthenticated: () => boolean;
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      guilds: [],
      setAuth: (token, user, guilds) => set({ token, user, guilds }),
      logout: () => set({ token: null, user: null, guilds: [] }),
      isAuthenticated: () => !!get().token,
    }),
    {
      name: "summarybot-auth",
    }
  )
);
