import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import Login from './pages/Login';
import Dashboard from './pages/CustomDashboard';
import ProtectedRoute from './components/layout/ProtectedRoute';
import MainLayout from './components/layout/MainLayout';
import GenericList from './pages/GenericList';
import GenericForm from './pages/GenericForm';
import GenericDispatcher from './pages/GenericDispatcher';
import PermissionRoute from './components/layout/PermissionRoute';
import MeliCallback from './pages/MeliCallback';
import { useAuth } from './contexts/AuthContext';

// Componente para redirecionar para a primeira aba disponível
const DefaultRedirect = () => {
  const { user } = useAuth();

  // Lista de prioridade de redirecionamento (mesma ordem do menu lateral)
  const modules = [
    { module: 'dashboard', path: '/dashboard', acesso: true },
    { module: 'empresas', path: `/empresas/edit/${user?.id_empresa}` },
    { module: 'usuarios', path: '/usuarios' },
    { module: 'cadastros', path: '/cadastros' },
    { module: 'produtos', path: '/produtos' },
    { module: 'pedidos', path: '/pedidos/Todos' },
    { module: 'embalagens', path: '/embalagens' },
    { module: 'estoque', path: '/estoque' },
    { module: 'contas', path: '/contas' },
    { module: 'tributacoes', path: '/tributacoes' },
    { module: 'nfe_recebidas', path: '/nfe_recebidas' },
    { module: 'integracoes', path: '/integracoes' },
  ];

  // Nova estrutura: user.permissoes é um objeto { "modulo": { acesso: true, ... } }
  const permissions = user?.permissoes || {};
  
  // Encontra o primeiro módulo que o usuário tem permissão
  const firstAllowed = modules.find(m => (user?.perfil === 'admin' || user?.perfil === 'Admin') || permissions[m.module]?.acesso);
  
  // Redireciona para o módulo encontrado ou mantém dashboard como fallback
  const target = firstAllowed ? firstAllowed.path : '/dashboard';
  
  return <Navigate to={target} replace />;
};

function App() {
  return (
    <>
      <ToastContainer autoClose={3000} />
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
          <Route index element={<DefaultRedirect />} />
          <Route path="dashboard" element={
            <PermissionRoute module="dashboard">
              <Dashboard />
            </PermissionRoute>
          } />

          {/* Rotas Genéricas (Dispatcher) */}
          <Route path=":modelName/:statusFilter?" element={
            <PermissionRoute >
              <GenericDispatcher />
            </PermissionRoute>
          } />

          {/* Rota de Criação: /customers/new, /products/new, etc. */}
          <Route path=":modelName/new" element={
            <PermissionRoute >
              <GenericForm />
            </PermissionRoute>
          } />

          {/* Rota de Edição: /customers/edit/1, /products/edit/5, etc. */}
          <Route path=":modelName/edit/:id" element={
            <PermissionRoute>
              <GenericForm />
            </PermissionRoute>
          } />

          {/* ROTA PARA O CALLBACK DO ML */}
          <Route path="/mercadolivre/callback" element={<MeliCallback />} />
          
          {/* ROTAS DE CONFIGURAÇÃO (FORM) */}
          {/* Certifique-se que meli_configuracoes usa o GenericForm */}
          <Route path="/meli_configuracoes/new" element={
            <PermissionRoute>
              <GenericForm modelName="meli_configuracoes" />
            </PermissionRoute>
          } />
          <Route path="/meli_configuracoes/edit/:id" element={
            <PermissionRoute>
              <GenericForm modelName="meli_configuracoes" />
            </PermissionRoute>
          } />

        </Route>
        {/* Fallback - Redireciona para o login se não houver rota */}
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </>
  );
}

export default App;
