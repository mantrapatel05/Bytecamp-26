import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import apiClient from '@/api/client';

interface AuthState {
  token: string | null;
  username: string | null;
  isLoading: boolean;
}

interface AuthContextType extends AuthState {
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType | null>(null);

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
};

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('depgraph_token'));
  const [username, setUsername] = useState<string | null>(() => localStorage.getItem('depgraph_username'));
  const [isLoading, setIsLoading] = useState(true);

  // Validate stored token on mount
  useEffect(() => {
    if (token) {
      apiClient.getMe()
        .then(data => { setUsername(data.username); })
        .catch(() => {
          localStorage.removeItem('depgraph_token');
          localStorage.removeItem('depgraph_username');
          setToken(null);
          setUsername(null);
        })
        .finally(() => setIsLoading(false));
    } else {
      setIsLoading(false);
    }
  }, []);

  // Listen for 401 forced logout
  useEffect(() => {
    const handler = () => logout();
    window.addEventListener('auth:logout', handler);
    return () => window.removeEventListener('auth:logout', handler);
  }, []);

  const login = useCallback(async (user: string, password: string) => {
    const res = await apiClient.login(user, password);
    localStorage.setItem('depgraph_token', res.token);
    localStorage.setItem('depgraph_username', res.username);
    setToken(res.token);
    setUsername(res.username);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('depgraph_token');
    localStorage.removeItem('depgraph_username');
    setToken(null);
    setUsername(null);
  }, []);

  return (
    <AuthContext.Provider value={{
      token, username, isLoading,
      isAuthenticated: !!token,
      login, logout,
    }}>
      {children}
    </AuthContext.Provider>
  );
};
