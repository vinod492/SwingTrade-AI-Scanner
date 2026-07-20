import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { api, getTokens, setTokens } from "../api/client";

interface AuthState {
  loggedIn: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState>({
  loggedIn: false,
  login: async () => {},
  register: async () => {},
  logout: () => {},
});

interface TokenPair {
  access_token: string;
  refresh_token: string;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [loggedIn, setLoggedIn] = useState(getTokens() !== null);

  useEffect(() => {
    const sync = () => setLoggedIn(getTokens() !== null);
    window.addEventListener("swingtrade-auth", sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener("swingtrade-auth", sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await api<TokenPair>("/auth/login", { method: "POST", body: { email, password } });
    setTokens(tokens);
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    const tokens = await api<TokenPair>("/auth/register", { method: "POST", body: { email, password } });
    setTokens(tokens);
  }, []);

  const logout = useCallback(() => setTokens(null), []);

  return (
    <AuthContext.Provider value={{ loggedIn, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
