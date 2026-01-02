"use client";

import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { auth, Scope } from "@/lib/api";

interface AuthContextType {
  scope: Scope | null;
  isLoading: boolean;
  refetch: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  scope: null,
  isLoading: true,
  refetch: async () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [scope, setScope] = useState<Scope | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const fetchScope = async () => {
    try {
      const data = await auth.me();
      setScope(data.scope);
    } catch {
      setScope(null);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchScope();
  }, []);

  return (
    <AuthContext.Provider value={{ scope, isLoading, refetch: fetchScope }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
