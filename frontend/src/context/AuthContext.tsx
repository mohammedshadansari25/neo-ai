import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import {
  apiFetch,
  refreshAccessToken,
  setAccessToken,
  type AuthRequest,
  type LogoutResponse,
  type TokenResponse,
  type UserProfileResponse,
} from "../api/client";

interface AuthContextValue {
  user: UserProfileResponse | null;
  accessToken: string | null;
  isInitializing: boolean;
  login: (payload: AuthRequest) => Promise<void>;
  register: (payload: AuthRequest) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserProfileResponse | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isInitializing, setIsInitializing] = useState(true);

  useEffect(() => {
    let active = true;
    (async () => {
      const fresh = await refreshAccessToken();
      if (fresh && active) {
        try {
          const profile = await apiFetch<UserProfileResponse>("/api/me");
          if (active) {
            setToken(fresh);
            setUser(profile);
          }
        } catch {
          setAccessToken(null);
        }
      }
      if (active) {
        setIsInitializing(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const login = useCallback(async (payload: AuthRequest) => {
    const res = await apiFetch<TokenResponse>(
      "/api/auth/login",
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
      false,
    );
    setAccessToken(res.access_token);
    setToken(res.access_token);
    setUser(res.user);
  }, []);

  const register = useCallback(async (payload: AuthRequest) => {
    const res = await apiFetch<TokenResponse>(
      "/api/auth/register",
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
      false,
    );
    setAccessToken(res.access_token);
    setToken(res.access_token);
    setUser(res.user);
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiFetch<LogoutResponse>("/api/auth/logout", { method: "POST" }, false);
    } finally {
      setAccessToken(null);
      setToken(null);
      setUser(null);
    }
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        accessToken: token,
        isInitializing,
        login,
        register,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return ctx;
}
