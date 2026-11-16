import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, getToken, setToken, setUnauthorizedHandler } from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(Boolean(getToken()));

  const signOut = useCallback(() => {
    setToken("");
    setUser(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null));
  }, []);

  useEffect(() => {
    if (!getToken()) return;
    let cancelled = false;
    api
      .me()
      .then((me) => !cancelled && setUser(me))
      .catch(() => !cancelled && setToken(""))
      .finally(() => !cancelled && setChecking(false));
    return () => {
      cancelled = true;
    };
  }, []);

  const startSignIn = useCallback((email, password) => api.login(email, password), []);

  const finishSignIn = useCallback(async (challenge, code) => {
    const result = await api.verifyLogin(challenge, code);
    setToken(result.token);
    setUser(result.user);
    return result.user;
  }, []);

  const refresh = useCallback(async () => setUser(await api.me()), []);

  const can = useCallback(
    (...perms) => perms.every((p) => (user?.permissions || []).includes(p)),
    [user]
  );

  const value = useMemo(
    () => ({ user, checking, startSignIn, finishSignIn, signOut, refresh, can }),
    [user, checking, startSignIn, finishSignIn, signOut, refresh, can]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth used outside AuthProvider");
  return context;
}
