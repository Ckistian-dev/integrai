import React from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { Navigate, useLocation } from 'react-router-dom';

const ProtectedRoute = ({ children }) => {
  const { isAuthenticated } = useAuth();
  const location = useLocation();

  if (!isAuthenticated) {
    // Se não estiver autenticado, redireciona para o login
    // 'state' armazena a página que ele tentou acessar,
    // para que possamos redirecioná-lo de volta após o login.
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // Se estiver autenticado, renderiza o componente filho (a página)
  return children;
};

export default ProtectedRoute;
