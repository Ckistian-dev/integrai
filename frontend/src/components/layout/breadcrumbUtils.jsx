import React from 'react';
import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';

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
  integracoes:              { module: 'Integrações', modulePath: '/integracoes' },
  intelipost:               { module: 'Integrações', modulePath: '/integracoes' },
  intelipost_configuracoes: { module: 'Integrações', modulePath: '/integracoes' },
  mercadolivre_pedidos:     { module: 'Integrações', modulePath: '/integracoes' },
  meli_configuracoes:       { module: 'Integrações', modulePath: '/integracoes' },
  magento_pedidos:          { module: 'Integrações', modulePath: '/integracoes' },
  tiktok_pedidos:           { module: 'Integrações', modulePath: '/integracoes' },
  atendai_configuracoes:    { module: 'Integrações', modulePath: '/integracoes' },
  email_regras:             { module: 'Integrações', modulePath: '/integracoes' },
  outras_empresas_configuracoes: { module: 'Integrações', modulePath: '/integracoes' },
};

// Nomes legíveis amigáveis de fallback
export const HUMAN_MODEL_NAMES = {
  perfis: 'Perfis de Usuário',
  intelipost: 'Intelipost',
  mercadolivre_pedidos: 'Mercado Livre',
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

// Componente reutilizável de Breadcrumb
export const Breadcrumb = ({ crumbs }) => {
  if (!crumbs || crumbs.length === 0) return null;
  return (
    <nav aria-label="breadcrumb" className="flex items-center gap-1.5 text-sm text-gray-500">
      {crumbs.map((crumb, i) => {
        const isLast = i === crumbs.length - 1;
        return (
          <span key={i} className="flex items-center gap-1.5">
            {i > 0 && <ChevronRight size={13} className="text-gray-400" />}
            {isLast || !crumb.path ? (
              <span className={isLast ? 'font-semibold text-gray-700 underline underline-offset-2 decoration-gray-400' : 'text-gray-500'}>
                {crumb.label}
              </span>
            ) : (
              <Link
                to={crumb.path}
                className="hover:text-teal-600 hover:underline transition-colors"
              >
                {crumb.label}
              </Link>
            )}
          </span>
        );
      })}
    </nav>
  );
};
