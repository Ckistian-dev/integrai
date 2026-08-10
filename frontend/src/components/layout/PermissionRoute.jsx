import React from 'react';
import { Navigate, useParams, useLocation } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
const PermissionRoute = ({ children, module: propModule }) => {
  const { user } = useAuth();
  const { modelName, statusFilter, id } = useParams();

  const location = useLocation();

  // Se for admin, libera tudo
  if (user?.perfil === 'admin' || user?.perfil === 'Admin') {
    return children;
  }

  // Mapeamento de Modelos/Rotas para os códigos de Módulos definidos no Backend (models.py)
  const moduleMap = {
    'empresas': 'empresas',
    'usuarios': 'usuarios',
    'perfis': 'usuarios',
    'cadastros': 'cadastros',
    'produtos': 'produtos',
    'pedidos': 'pedidos',
    'embalagens': 'embalagens',
    'estoque': 'estoque',
    'contas': 'contas',
    'classificacao_contabil': 'contas',
    'tributacoes': 'tributacoes',
    'regras_tributarias': 'tributacoes',
    'relatorios': 'relatorios',
    'intelipost_configuracoes': 'integracoes',
    'atendai_configuracoes': 'integracoes',
    'meli_configuracoes': 'integracoes',
    'magento_configuracoes': 'integracoes',
    'shopee_configuracoes': 'integracoes',
    'mercadolivre_pedidos': 'integracoes',
    'magento_pedidos': 'integracoes',
    'shopee_pedidos': 'integracoes',
    'intelipost': 'integracoes'
  };

  // Determina o módulo atual com base na URL ou parâmetro
  let currentModule = null;
  let requiredSubpage = null;

  if (modelName && moduleMap[modelName]) {
      currentModule = moduleMap[modelName];
      
      // Lógica de Subpáginas
      if (currentModule === 'pedidos') {
          // Só exige a sub-página "Todos" se não houver um status específico na URL 
          // e se não for uma rota de edição (id presente) ou criação (/new)
          if (statusFilter) {
              requiredSubpage = statusFilter;
          } else if (!id && !location.pathname.endsWith('/new')) {
              requiredSubpage = 'Todos';
          }
      } else if (modelName === 'usuarios') {
          requiredSubpage = 'Usuários';
      } else if (modelName === 'perfis') {
          requiredSubpage = 'Perfis';
      } else if (modelName === 'contas') {
          requiredSubpage = 'Contas';
      } else if (modelName === 'classificacao_contabil') {
          requiredSubpage = 'Contábil';
      } else if (currentModule === 'integracoes') {
          if (modelName.includes('intelipost')) requiredSubpage = 'Intelipost';
          if (modelName.includes('mercadolivre') || modelName.includes('meli')) requiredSubpage = 'Mercado Livre';
          if (modelName.includes('shopee')) requiredSubpage = 'Shopee';
          if (modelName.includes('magento')) requiredSubpage = 'Magento';
      }
  } else {
    // Fallback por path para rotas que não usam :modelName
    const path = location.pathname;
    if (path.startsWith('/integracoes')) currentModule = 'integracoes';
    else if (path.startsWith('/contas')) currentModule = 'contas';
    else if (path.startsWith('/classificacao_contabil')) currentModule = 'contas';
    else if (path.startsWith('/tributacoes')) currentModule = 'tributacoes';
    else if (path.startsWith('/dashboard')) currentModule = 'dashboard';
  }  

  // Se a prop 'module' foi passada, usa ela (ex: dashboard)
  if (propModule) {
    currentModule = propModule;
  }

  // Se identificou um módulo e o usuário NÃO tem permissão
    // Lógica inteligente de redirecionamento: vai para a primeira aba que ele TEM permissão
    const modules = [
      { module: 'dashboard', path: '/dashboard' },
      { module: 'empresas', path: `/empresas/edit/${user?.id_empresa}` },
      { module: 'usuarios', path: '/usuarios' },
      { module: 'cadastros', path: '/cadastros' },
      { module: 'produtos', path: '/produtos' },
      { module: 'pedidos', path: '/pedidos' },
      { module: 'embalagens', path: '/embalagens' },
      { module: 'estoque', path: '/estoque' },
      { module: 'contas', path: '/contas' },
      { module: 'tributacoes', path: '/tributacoes' },
      { module: 'integracoes', path: '/integracoes' },
    ];

  if (currentModule && user?.permissoes) {
        const permissions = user?.permissoes || {};
        const modulePerms = permissions[currentModule];

        // 1. Verifica acesso ao módulo
        // 2. Verifica acesso à subpágina (se aplicável)
        const hasModuleAccess = modulePerms?.acesso;
        const hasSubpageAccess = !requiredSubpage || (modulePerms?.subpaginas && modulePerms.subpaginas.includes(requiredSubpage));

        if (!hasModuleAccess || !hasSubpageAccess) {
        const firstAllowed = modules.find(m => permissions[m.module]?.acesso);
    
    // Se não tiver permissão para nada, manda para login, senão vai para a primeira permitida
    const target = firstAllowed ? firstAllowed.path : '/login';
    
    return <Navigate to={target} replace />;
    }
  }


  return children;


};

export default PermissionRoute;