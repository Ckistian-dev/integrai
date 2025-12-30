import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import ProtectedRoute from './components/layout/ProtectedRoute';
import MainLayout from './components/layout/MainLayout';
import GenericList from './pages/GenericList';
import GenericForm from './pages/GenericForm';

function App() {
  return (
    <Routes>
      {/* Rota Pública */}
      <Route path="/login" element={<Login />} />

      {/* Rotas Protegidas dentro do Layout Principal */}
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <MainLayout />
          </ProtectedRoute>
        }
      >
        {/* Rota "index" é a página padrão dentro do layout */}
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<Dashboard />} />

        {/* Rotas Genéricas */}
        {/* Rota de Listagem: /customers, /products, etc. */}
        <Route path=":modelName/:statusFilter?" element={<GenericList />} />
        
        {/* Rota de Criação: /customers/new, /products/new, etc. */}
        <Route path=":modelName/new" element={<GenericForm />} />
        
        {/* Rota de Edição: /customers/edit/1, /products/edit/5, etc. */}
        <Route path=":modelName/edit/:id" element={<GenericForm />} />
      </Route>

      {/* Fallback - Redireciona para o login se não houver rota */}
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}

export default App;
