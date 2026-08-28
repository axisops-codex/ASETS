import React, { createContext, useContext, useEffect, useState } from "react";
import { api, setToken, loadToken } from "@/src/api/client";

type User = {
  id: string;
  email: string;
  name: string;
  business_name: string;
  address: string;
  utr: string;
  settings: any;
};

type AuthCtx = {
  user: User | null;
  booting: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: (u: User) => void;
};

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [booting, setBooting] = useState(true);

  useEffect(() => {
    (async () => {
      const token = await loadToken();
      if (token) {
        try {
          const me = await api.me();
          setUser(me);
        } catch {
          await setToken(null);
        }
      }
      setBooting(false);
    })();
  }, []);

  const login = async (email: string, password: string) => {
    const res = await api.login({ email, password });
    await setToken(res.access_token);
    setUser(res.user);
  };

  const register = async (email: string, password: string, name: string) => {
    const res = await api.register({ email, password, name });
    await setToken(res.access_token);
    setUser(res.user);
  };

  const logout = async () => {
    await setToken(null);
    setUser(null);
  };

  const refreshUser = (u: User) => setUser(u);

  return (
    <Ctx.Provider value={{ user, booting, login, register, logout, refreshUser }}>
      {children}
    </Ctx.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
