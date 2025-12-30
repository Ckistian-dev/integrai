import React, { createContext, useContext, useState, useEffect } from 'react';
import api from '../api/axiosConfig';
import { jwtDecode } from 'jwt-decode'; // <-- IMPORTAR O DECODER

// 1. Cria o Contexto
const AuthContext = createContext(null);

// Helper para decodificar e verificar expiração
const decodeToken = (token) => {
  try {
    const decoded = jwtDecode(token);
    // Verifica se o token expirou
    if (decoded.exp * 1000 < Date.now()) {
      localStorage.removeItem('authToken');
      return null;
    }
    return decoded; // Retorna o payload (ex: { user_id, email, role, ... })
  } catch (error) {
    console.error("Token inválido:", error);
    localStorage.removeItem('authToken');
    return null;
  }
};

// 2. Cria o Provedor (Componente)
export const AuthProvider = ({ children }) => {
  // O estado agora armazena o usuário (payload do token) ou null
  const [user, setUser] = useState(null); 
  const [loading, setLoading] = useState(true);

  // Efeito para carregar o token do localStorage na inicialização
  useEffect(() => {
    const storedToken = localStorage.getItem('authToken');
    if (storedToken) {
      const decodedUser = decodeToken(storedToken);
      if (decodedUser) {
        setUser(decodedUser);
      }
    }
    setLoading(false);
  }, []);

  // Função de Login
  const login = async (username, password) => {
    try {
      const params = new URLSearchParams();
      params.append('username', username);
      params.append('password', password);

      const response = await api.post('/login/token', params, {
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
      });

      const { access_token } = response.data;
      const decodedUser = decodeToken(access_token);
      
      if (decodedUser) {
        setUser(decodedUser);
        localStorage.setItem('authToken', access_token);
      } else {
         // Se o token for inválido por algum motivo
         throw new Error("Token inválido recebido do servidor.");
      }

    } catch (error) {
      console.error("Falha no login:", error);
      throw error;
    }
  };

  // Função de Logout
  const logout = () => {
    setUser(null);
    localStorage.removeItem('authToken');
  };

  // Valor fornecido pelo contexto
  const value = {
    user, // O objeto do usuário decodificado (ou null)
    isAuthenticated: !!user, // Booleano (true se 'user' não for null)
    loading,
    login,
    logout,
  };

  return (
    <AuthContext.Provider value={value}>
      {!loading && children}
    </AuthContext.Provider>
  );
};

// 3. Cria o Hook customizado
export const useAuth = () => {
  return useContext(AuthContext);
};
