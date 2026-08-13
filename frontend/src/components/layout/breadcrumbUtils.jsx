import React from 'react';
import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';

// --- MAPA DE MÓDULOS PARA BREADCRUMB ---
// Mapeia o modelName para o item correspondente da Sidebar do MainLayout
export const MODULE_MAP = {
  dashboard:                { module: 'Dashboard', modulePath: '/dashboard' },
  empresas:                 { module: 'Minha Empresa', modulePath: '/empresas' },
  usuarios:                 { module: 'Usuários', modulePath: '/usuarios' },
  perfis:                   { module: 'Usuários', modulePath: '/usuarios' },
  cadastros:                { module: 'Cadastros', modulePath: '/cadastros' },
  produtos:                 { module: 'Produtos', modulePath: '/produtos' },
  pedidos:                  { module: 'Pedidos', modulePath: '/pedidos/Todos' },
  embalagens:               { module: 'Embalagens', modulePath: '/embalagens' },
  estoque:                  { module: 'Estoque', modulePath: '/estoque/Saldo' },
  contas:                   { module: 'Financeiro', modulePath: '/contas' },
  classificacoes_contabeis: { module: 'Financeiro', modulePath: '/contas' },
  classificacao_contabil:   { module: 'Financeiro', modulePath: '/contas' },
  tributacoes:              { module: 'Regras Tributárias', modulePath: '/tributacoes' },
  nfe_recebidas:            { module: 'DF-e', modulePath: '/nfe_recebidas' },
  relatorios:               { module: 'Relatórios', modulePath: '/relatorios' },
  integracoes:              { module: 'Integrações', modulePath: null },
  intelipost:               { module: 'Integrações', modulePath: null },
  intelipost_configuracoes: { module: 'Integrações', modulePath: null },
  mercadolivre_pedidos:     { module: 'Integrações', modulePath: null },
  meli_configuracoes:       { module: 'Integrações', modulePath: null },
  shopee_pedidos:           { module: 'Integrações', modulePath: null },
  shopee_configuracoes:     { module: 'Integrações', modulePath: null },
  magento_pedidos:          { module: 'Integrações', modulePath: null },
  tiktok_pedidos:           { module: 'Integrações', modulePath: null },
  atendai_configuracoes:    { module: 'Integrações', modulePath: null },
  email_regras:             { module: 'Integrações', modulePath: null },
  outras_empresas_configuracoes: { module: 'Integrações', modulePath: null },
};

// Nomes legíveis amigáveis de fallback
export const HUMAN_MODEL_NAMES = {
  perfis: 'Perfis de Usuário',
  intelipost: 'Intelipost',
  mercadolivre_pedidos: 'Mercado Livre',
  shopee_pedidos: 'Shopee',
  shopee_configuracoes: 'Configuração Shopee',
  magento_pedidos: 'Magento',
  tiktok_pedidos: 'Tiktok Shop',
  atendai_configuracoes: 'AtendAI',
  email_regras: 'Regras de E-mail',
  outras_empresas_configuracoes: 'Outras Empresas',
  classificacoes_contabeis: 'Classificação Contábil',
  classificacao_contabil: 'Classificação Contábil',
  tributacoes: 'Regras Tributárias',
  nfe_recebidas: 'DF-e',
};

/**
 * Verifica se um determinado caminho do breadcrumb é de fato uma página acessível para o usuário atual.
 */
export const isPathAccessible = (path, user) => {
  if (!path || path === '#') return false;

  const cleanPath = path.split('?')[0].replace(/\/$/, '');

  // Rotas/seções que não possuem página de lista acessível (agrupadores)
  const nonAccessiblePaths = [
    '/integracoes',
  ];

  if (nonAccessiblePaths.includes(cleanPath)) return false;

  // Modelos de configuração isolados que não têm página de lista
  const configModelsWithoutList = [
    '/meli_configuracoes',
    '/shopee_configuracoes',
    '/intelipost_configuracoes',
    '/atendai_configuracoes',
    '/magento_configuracoes',
    '/tiktok_configuracoes',
    '/email_regras'
  ];

  if (configModelsWithoutList.includes(cleanPath)) return false;

  // Se não houver objeto user (deslogado), não renderiza como link
  if (!user) return false;

  // Administrador tem acesso a qualquer rota válida
  if (user.perfil === 'admin' || user.perfil === 'Admin') return true;

  const permissions = user.permissoes || {};

  // Dashboard
  if (cleanPath === '/dashboard') {
    return permissions.dashboard ? permissions.dashboard.acesso === true : true;
  }

  // Minha Empresa
  if (cleanPath.startsWith('/empresas')) {
    return permissions.empresas?.acesso === true;
  }

  // Usuários
  if (cleanPath.startsWith('/usuarios')) {
    const perm = permissions.usuarios;
    if (!perm?.acesso) return false;
    if (perm.subpaginas) return perm.subpaginas.includes('Usuários');
    return true;
  }

  // Perfis
  if (cleanPath.startsWith('/perfis')) {
    const perm = permissions.usuarios;
    if (!perm?.acesso) return false;
    if (perm.subpaginas) return perm.subpaginas.includes('Perfis');
    return true;
  }

  // Cadastros
  if (cleanPath.startsWith('/cadastros')) {
    return permissions.cadastros?.acesso === true;
  }

  // Produtos
  if (cleanPath.startsWith('/produtos')) {
    return permissions.produtos?.acesso === true;
  }

  // Pedidos
  if (cleanPath.startsWith('/pedidos')) {
    const perm = permissions.pedidos;
    if (!perm?.acesso) return false;
    const parts = cleanPath.split('/');
    const statusFilter = parts[2];
    if (statusFilter && statusFilter !== 'Todos' && perm.subpaginas) {
      return perm.subpaginas.includes(decodeURIComponent(statusFilter));
    }
    return true;
  }

  // Embalagens
  if (cleanPath.startsWith('/embalagens')) {
    return permissions.embalagens?.acesso === true;
  }

  // Estoque
  if (cleanPath.startsWith('/estoque')) {
    const perm = permissions.estoque;
    if (!perm?.acesso) return false;
    const parts = cleanPath.split('/');
    const sub = parts[2];
    if (sub && perm.subpaginas) {
      return perm.subpaginas.includes(decodeURIComponent(sub));
    }
    return true;
  }

  // Financeiro (Contas)
  if (cleanPath.startsWith('/contas')) {
    const perm = permissions.contas;
    if (!perm?.acesso) return false;
    if (perm.subpaginas) return perm.subpaginas.includes('Contas');
    return true;
  }

  // Classificação Contábil
  if (cleanPath.startsWith('/classificacao_contabil') || cleanPath.startsWith('/classificacoes_contabeis')) {
    const perm = permissions.contas;
    if (!perm?.acesso) return false;
    if (perm.subpaginas) return perm.subpaginas.includes('Contábil');
    return true;
  }

  // Regras Tributárias
  if (cleanPath.startsWith('/tributacoes')) {
    return permissions.tributacoes?.acesso === true;
  }

  // DF-e
  if (cleanPath.startsWith('/nfe_recebidas')) {
    return permissions.nfe_recebidas?.acesso === true;
  }

  // Relatórios
  if (cleanPath.startsWith('/relatorios')) {
    return permissions.relatorios?.acesso === true;
  }

  // Subpáginas de Integrações
  const integraMap = {
    '/intelipost': 'Intelipost',
    '/mercadolivre_pedidos': 'Mercado Livre',
    '/shopee_pedidos': 'Shopee',
    '/magento_pedidos': 'Magento',
    '/tiktok_pedidos': 'Tiktok Shop',
  };

  if (integraMap[cleanPath]) {
    const perm = permissions.integracoes;
    if (!perm?.acesso) return false;
    if (perm.subpaginas) return perm.subpaginas.includes(integraMap[cleanPath]);
    return true;
  }

  // Fallback para modelos em permissoes
  const baseModel = cleanPath.split('/')[1];
  if (baseModel && permissions[baseModel] !== undefined) {
    return permissions[baseModel]?.acesso === true;
  }

  return true;
};

// Componente reutilizável de Breadcrumb
export const Breadcrumb = ({ crumbs }) => {
  const { user } = useAuth();
  if (!crumbs || crumbs.length === 0) return null;

  return (
    <nav aria-label="breadcrumb" className="flex items-center gap-1.5 text-sm text-gray-500">
      {crumbs.map((crumb, i) => {
        const isLast = i === crumbs.length - 1;
        const accessible = !isLast && crumb.path && isPathAccessible(crumb.path, user);

        return (
          <span key={i} className="flex items-center gap-1.5">
            {i > 0 && <ChevronRight size={13} className="text-gray-400" />}
            {accessible ? (
              <Link
                to={crumb.path}
                className="hover:text-teal-600 hover:underline transition-colors"
              >
                {crumb.label}
              </Link>
            ) : (
              <span className={isLast ? 'font-semibold text-gray-700 underline underline-offset-2 decoration-gray-400' : 'text-gray-500'}>
                {crumb.label}
              </span>
            )}
          </span>
        );
      })}
    </nav>
  );
};

