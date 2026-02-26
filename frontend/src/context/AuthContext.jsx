import React, { createContext, useContext, useState, useEffect } from 'react';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem('km_token'));
  const [user, setUser] = useState(() => {
    const u = localStorage.getItem('km_user');
    return u ? JSON.parse(u) : null;
  });

  const login = (tokenValue, userData) => {
    localStorage.setItem('km_token', tokenValue);
    localStorage.setItem('km_user', JSON.stringify(userData));
    setToken(tokenValue);
    setUser(userData);
  };

  const logout = () => {
    localStorage.removeItem('km_token');
    localStorage.removeItem('km_user');
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ token, user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
