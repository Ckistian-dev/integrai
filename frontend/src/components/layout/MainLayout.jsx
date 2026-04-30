import React, { useState, useEffect, useMemo } from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import api from '../../api/axiosConfig';
import {
  Home,
  Users,
  List,
  ShoppingCart,
  Package,
  Landmark,
  Layers,
  LogOut,
  Archive,
  UserCircle, // Para o usuário logado
  Box,
  Building,
  FileText,
  FileSearch,
  BarChart2, // Ícone para Relatórios
} from 'lucide-react';
import { FaWhatsapp } from 'react-icons/fa';
import { useLocation } from 'react-router-dom';
import { ChevronDown } from 'lucide-react'; // Ícone para o acordeão

const MainLayout = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  // O estado de expansão agora é controlado pelo novo layout
  const [isExpanded, setIsExpanded] = useState(false);
  const [isIntegraOpen, setIsIntegraOpen] = useState(false);
  const [isFinanceiroOpen, setIsFinanceiroOpen] = useState(false);
  const [isUsuariosOpen, setIsUsuariosOpen] = useState(false);
  const [isEstoqueOpen, setIsEstoqueOpen] = useState(false);

  // Array de itens do menu (do seu ERP)
  const menuItems = [
    { name: 'Dashboard', path: '/dashboard', icon: Home, exact: true, module: 'dashboard' },
    { name: 'Minha Empresa', path: `/empresas/edit/${user?.id_empresa}`, icon: Building, module: 'empresas' },
    { name: 'Usuários', path: '/usuarios', icon: Users, module: 'usuarios' },
    { name: 'Cadastros', path: '/cadastros', icon: List, module: 'cadastros' },
    { name: 'Produtos', path: '/produtos', icon: Box, module: 'produtos' },
    { name: 'Pedidos', path: '/pedidos', icon: ShoppingCart, module: 'pedidos' },
    { name: 'Embalagens', path: '/embalagens', icon: Archive, module: 'embalagens' },
    { name: 'Estoque', path: '/estoque', icon: Package, module: 'estoque' },
    { name: 'Financeiro', path: '/contas', icon: Landmark, module: 'contas' },
    { name: 'Regras Tributárias', path: '/tributacoes', icon: FileText, module: 'tributacoes' },
    { name: 'DF-e', path: '/nfe_recebidas', icon: FileSearch, module: 'nfe_rece_bidas' },
    { name: 'Relatórios', path: '/relatorios', icon: BarChart2, module: 'relatorios' },
    { name: 'Integrações', path: '/integracoes', icon: Layers, module: 'integracoes' },
    // Adicione mais itens conforme necessário
  ];

  // Verifica se o usuário tem permissão para o módulo
  const hasPermission = (module) => {
    if (!module) return true; // Itens públicos
    
    // Admin tem acesso total (fallback de segurança)
    if (user?.perfil === 'Admin' || user?.perfil === 'admin') return true;

    // Verifica no objeto de permissões
    const permissions = user?.permissoes || {};
    return permissions[module]?.acesso === true;
  };

  // Verifica se o usuário tem permissão para uma subpágina específica
  const hasSubpagePermission = (module, subpageName) => {
    if (user?.perfil === 'Admin' || user?.perfil === 'admin') return true;
    
    // Histórico é exceção, sempre visível se tiver acesso ao módulo
    if (module === 'pedidos' && subpageName === 'Histórico') return true;
    if (module === 'estoque' && (subpageName === 'Saldo' || subpageName === 'Movimentações' || subpageName === 'Inventário')) return true;

    const permissions = user?.permissoes || {};
    const modulePerms = permissions[module];
    
    return modulePerms?.subpaginas?.includes(subpageName);
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const [isPipelineOpen, setIsPipelineOpen] = useState(false);
  const location = useLocation(); // Hook para saber a rota atual

  const pipelineStatus = useMemo(() => [
    { name: 'Orçamento', path: '/pedidos/Orçamento' },
    { name: 'Aprovação', path: '/pedidos/Aprovação' },
    { name: 'Programação', path: '/pedidos/Programação' },
    { name: 'Produção', path: '/pedidos/Produção' },
    { name: 'Embalagem', path: '/pedidos/Embalagem' },
    { name: 'Faturamento', path: '/pedidos/Faturamento' },
    { name: 'Expedição', path: '/pedidos/Expedição' },
    { name: 'Despachado', path: '/pedidos/Despachado' },
    { name: 'Nota Fiscal', path: '/pedidos/Nota Fiscal' },
    { name: 'Cancelado', path: '/pedidos/Cancelado' },
    { name: 'Todos', path: '/pedidos/Todos' },
  ], []); // Array de dependência vazio, é estático

  const integraItems = useMemo(() => [
    { name: 'Intelipost', path: '/intelipost' },
    { name: 'Mercado Livre', path: '/mercadolivre_pedidos' },
    { name: 'Magento', path: '/magento_pedidos' },
    { name: 'Elastic Email', path: '/elastic_email_configuracoes' },
  ], []);

  const financeiroItems = useMemo(() => [
    { name: 'Contas', path: '/contas' },
    { name: 'Contábil', path: '/classificacao_contabil' },
  ], []);

  const usuariosItems = useMemo(() => [
    { name: 'Usuários', path: '/usuarios' },
    { name: 'Perfis', path: '/perfis' },
  ], []);

  const estoqueItems = useMemo(() => [
    { name: 'Saldo', path: '/estoque/Saldo' },
    { name: 'Movimentações', path: '/estoque/Movimentações' },
    { name: 'Inventário', path: '/estoque/Inventário' },
  ], []);

  // [NOVO] Cria a lista de paths
  const pipelinePaths = useMemo(() =>
    pipelineStatus.map(status => status.path),
    [pipelineStatus]
  );

  const integraPaths = useMemo(() =>
    integraItems.map(item => item.path),
    [integraItems]
  );

  const financeiroPaths = useMemo(() =>
    financeiroItems.map(item => item.path),
    [financeiroItems]
  );

  const usuariosPaths = useMemo(() =>
    usuariosItems.map(item => item.path),
    [usuariosItems]
  );

  const estoquePaths = useMemo(() =>
    estoqueItems.map(item => item.path),
    [estoqueItems]
  );

  const isPedidosActive = location.pathname.startsWith('/pedidos');
  const isIntegraActive = location.pathname.startsWith('/integracoes') || location.pathname.startsWith('/intelipost_configuracoes') || location.pathname.startsWith('/elastic_email_configuracoes') || location.pathname.startsWith('/meli_configuracoes') || location.pathname.startsWith('/magento_configuracoes');
  const isFinanceiroActive = location.pathname.startsWith('/contas') || location.pathname.startsWith('/classificacao_contabil');
  const isUsuariosActive = location.pathname.startsWith('/usuarios') || location.pathname.startsWith('/perfis');
  const isEstoqueActive = location.pathname.startsWith('/estoque');

  const isPipelineListActive = useMemo(
    () => {
      // Decodifica o pathname da URL 
      // (ex: /pedidos/Or%C3%A7amento se transforma em /pedidos/Orçamento)
      try {
        const decodedPathname = decodeURIComponent(location.pathname);
        // Agora a comparação funciona
        return pipelinePaths.includes(decodedPathname);
      } catch (e) {
        // Fallback em caso de URL malformada
        console.error("Falha ao decodificar pathname:", location.pathname, e);
        return pipelinePaths.includes(location.pathname);
      }
    },
    [location.pathname, pipelinePaths]
  );

  const isIntegraListActive = useMemo(
    () => {
      try {
        const decodedPathname = decodeURIComponent(location.pathname);
        return integraPaths.includes(decodedPathname);
      } catch (e) {
        return integraPaths.includes(location.pathname);
      }
    },
    [location.pathname, integraPaths]
  );

  const isFinanceiroListActive = useMemo(
    () => {
      try {
        const decodedPathname = decodeURIComponent(location.pathname);
        return financeiroPaths.includes(decodedPathname);
      } catch (e) {
        return financeiroPaths.includes(location.pathname);
      }
    },
    [location.pathname, financeiroPaths]
  );

  const isUsuariosListActive = useMemo(
    () => {
      try {
        const decodedPathname = decodeURIComponent(location.pathname);
        return usuariosPaths.includes(decodedPathname);
      } catch (e) {
        return usuariosPaths.includes(location.pathname);
      }
    },
    [location.pathname, usuariosPaths]
  );

  const isEstoqueListActive = useMemo(
    () => {
      try {
        const decodedPathname = decodeURIComponent(location.pathname);
        return estoquePaths.includes(decodedPathname);
      } catch (e) {
        return estoquePaths.includes(location.pathname);
      }
    },
    [location.pathname, estoquePaths]
  );

  useEffect(() => {
    // SÓ ABRE se a rota for EXATA.
    // NUNCA FECHE (sem 'else'), para não conflitar com o clique manual.
    if (isPipelineListActive) {
      setIsPipelineOpen(true);
    }
    if (isIntegraListActive) {
      setIsIntegraOpen(true);
    }
    if (isFinanceiroListActive) {
      setIsFinanceiroOpen(true);
    }
    if (isUsuariosListActive) {
      setIsUsuariosOpen(true);
    }
    if (isEstoqueListActive) {
      setIsEstoqueOpen(true);
    }
  }, [isPipelineListActive, isIntegraListActive, isFinanceiroListActive, isUsuariosListActive, isEstoqueListActive]); // Depende da booleana específica

  const handleMouseEnter = () => {
    setIsExpanded(true);
    // Reabre a pipeline APENAS se o usuário estiver em uma ROTA DA LISTA.
    if (isPipelineListActive) {
      setIsPipelineOpen(true);
    }
    if (isIntegraListActive) {
      setIsIntegraOpen(true);
    }
    if (isFinanceiroListActive) {
      setIsFinanceiroOpen(true);
    }
    if (isUsuariosListActive) {
      setIsUsuariosOpen(true);
    }
    if (isEstoqueListActive) {
      setIsEstoqueOpen(true);
    }
  };

  // Ele deve fechar o acordeão ao sair.
  const handleMouseLeave = () => {
    setIsExpanded(false);
    setIsPipelineOpen(false); // [Esta é a sua solicitação] Fecha a pipeline
    setIsIntegraOpen(false);
    setIsFinanceiroOpen(false);
    setIsUsuariosOpen(false);
    setIsEstoqueOpen(false);
  };

  const handleSingletonClick = async (e, model) => {
    e.preventDefault();
    try {
      const res = await api.get(`/generic/${model}`);
      const items = res.data.items;
      if (items && items.length > 0) {
        navigate(`/${model}/edit/${items[0].id}`);
      } else {
        navigate(`/${model}/new`);
      }
    } catch (err) {
      navigate(`/${model}/new`);
    }
  };

  return (
    <div className="flex h-screen bg-gray-100 font-sans">
      <style>{`
        ::-webkit-scrollbar {
          width: 6px;
          height: 6px;
        }
        ::-webkit-scrollbar-track {
          background: transparent;
        }
        ::-webkit-scrollbar-thumb {
          background-color: #cbd5e1;
          border-radius: 3px;
        }
        ::-webkit-scrollbar-thumb:hover {
          background-color: #94a3b8;
        }
        .sidebar-scroll {
          scrollbar-color: color-mix(in srgb, var(--sidebar-bg) 70%, white) transparent; /* Firefox */
        }
        .sidebar-scroll::-webkit-scrollbar-thumb {
          background-color: color-mix(in srgb, var(--sidebar-bg) 70%, white);
        }
        .sidebar-scroll::-webkit-scrollbar-thumb:hover {
          background-color: color-mix(in srgb, var(--sidebar-bg) 50%, white);
        }
        .no-scrollbar::-webkit-scrollbar {
          display: none;
        }
        .no-scrollbar {
          -ms-overflow-style: none;  /* IE e Edge */
          scrollbar-width: none;  /* Firefox */
        }
      `}</style>

      {/* Sidebar (Layout copiado do seu exemplo, mas com dados e cores do ERP) */}
      <aside
        className={`relative h-screen text-white p-4 flex flex-col transition-all duration-300 ease-in-out ${isExpanded ? 'w-64' : 'w-20'}`}
        style={{ 
          backgroundColor: user?.cor_sidebar || '#1f2937',
          '--sidebar-bg': user?.cor_sidebar || '#1f2937'
        }}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
      >
        {/* Logo (adaptado do seu exemplo) */}
        <div className="flex items-center mb-10" style={{ height: '40px' }}>
          <div
            className="w-12 h-12 flex items-center justify-center rounded-lg flex-shrink-0"
            style={{
              backgroundColor: user?.cor_sidebar || '#1f2937',
              filter: 'brightness(1.2)'
            }}
          >
            {/* [ALTERADO] Mostra a primeira letra do nome da empresa */}
            <span className="font-bold text-lg text-white">
              ERP
            </span>
          </div>
          <span className={`font-bold text-2xl whitespace-nowrap overflow-hidden transition-all duration-300 ${isExpanded ? 'w-auto opacity-100 ml-3' : 'w-0 opacity-0'}`}>
            {/* [ALTERAÇÃO AQUI] */}
            {user?.empresa_fantasia || 'ERP IntegraAI'}
          </span>
        </div>

        {/* Navegação (adaptada do seu exemplo) */}
        <nav className={`flex-1 flex flex-col space-y-2 overflow-y-auto overflow-x-hidden ${isExpanded ? 'sidebar-scroll' : 'no-scrollbar'}`}>
          {menuItems.map(item => {
            const allowed = hasPermission(item.module);
            
            // Estilo base para item desabilitado
            const disabledClass = "cursor-not-allowed opacity-40 grayscale bg-transparent text-gray-500 hover:bg-transparent";

            // Caso especial para "Usuários"
            if (item.name === 'Usuários') {
              if (!allowed) {
                return (
                  <div key={item.name} className={`flex items-center justify-between w-full p-3 rounded-lg ${disabledClass}`}>
                    <div className="flex items-center">
                      <item.icon size={24} className="flex-shrink-0" />
                      <span className={`ml-4 font-medium whitespace-nowrap overflow-hidden transition-all duration-200 ${isExpanded ? 'opacity-100 w-full' : 'opacity-0 w-0'}`}>{item.name}</span>
                    </div>
                  </div>
                );
              }
              return (
                <div key={item.name}>
                  <button
                    onClick={() => setIsUsuariosOpen(!isUsuariosOpen)}
                    className={`flex items-center justify-between w-full p-3 rounded-lg transition-colors duration-200 ${isUsuariosActive
                      ? 'bg-teal-700 text-white' // Ativo
                      : 'hover:bg-teal-600' // Normal
                      }`}
                  >
                    <div className="flex items-center">
                      <item.icon size={24} className="flex-shrink-0" />
                      <span className={`ml-4 font-medium whitespace-nowrap overflow-hidden transition-all duration-200 ${isExpanded ? 'opacity-100 w-full' : 'opacity-0 w-0'}`}>
                        {item.name}
                      </span>
                    </div>
                    {/* Seta do Acordeão */}
                    <ChevronDown
                      size={20}
                      className={`flex-shrink-0 transition-transform duration-300 ${isUsuariosOpen ? 'rotate-180' : 'rotate-0'
                        } ${isExpanded ? 'opacity-100' : 'opacity-0'}`}
                    />
                  </button>

                  {/* Submenu de Usuários */}
                  <div
                    className={`transition-all duration-300 ease-in-out overflow-hidden ${(isUsuariosOpen && isExpanded) ? 'max-h-[256px]' : 'max-h-0'
                      } ${isExpanded ? 'pl-10' : 'pl-0'}`}
                  >
                    <div className="flex flex-col space-y-1 pt-2">
                      {usuariosItems.map(subItem => {
                        const isAllowed = hasSubpagePermission('usuarios', subItem.name);

                        if (!isAllowed) {
                          return (
                            <div key={subItem.name} className={`flex items-center py-2 px-3 rounded-lg text-sm cursor-not-allowed opacity-40 grayscale bg-transparent text-gray-500 hover:bg-transparent ${!isExpanded ? 'justify-center' : ''}`}>
                              <span className="whitespace-nowrap overflow-hidden">
                                {subItem.name}
                              </span>
                            </div>
                          );
                        }

                        return (
                        <NavLink
                          key={subItem.name}
                          to={subItem.path}
                          className={({ isActive }) =>
                            `flex items-center py-2 px-3 rounded-lg text-sm ${
                              isActive
                              ? 'bg-teal-600 text-white font-medium'
                              : 'text-gray-300 hover:bg-gray-700'
                            } ${!isExpanded ? 'justify-center' : ''}`
                          }
                        >
                          <span className="whitespace-nowrap overflow-hidden">
                            {subItem.name}
                          </span>
                        </NavLink>
                        );
                      })}
                    </div>
                  </div>
                </div>
              );
            }

            // Caso especial para "Pedidos"
            if (item.name === 'Pedidos') {
              if (!allowed) {
                return (
                  <div key={item.name} className={`flex items-center justify-between w-full p-3 rounded-lg ${disabledClass}`}>
                    <div className="flex items-center">
                      <item.icon size={24} className="flex-shrink-0" />
                      <span className={`ml-4 font-medium whitespace-nowrap overflow-hidden transition-all duration-200 ${isExpanded ? 'opacity-100 w-full' : 'opacity-0 w-0'}`}>{item.name}</span>
                    </div>
                  </div>
                );
              }
              return (
                <div key={item.name}>
                  <button
                    onClick={() => setIsPipelineOpen(!isPipelineOpen)}
                    className={`flex items-center justify-between w-full p-3 rounded-lg transition-colors duration-200 ${isPedidosActive
                      ? 'bg-teal-700 text-white' // Ativo
                      : 'hover:bg-teal-600' // Normal
                      }`}
                  >
                    <div className="flex items-center">
                      <item.icon size={24} className="flex-shrink-0" />
                      <span className={`ml-4 font-medium whitespace-nowrap overflow-hidden transition-all duration-200 ${isExpanded ? 'opacity-100 w-full' : 'opacity-0 w-0'}`}>
                        {item.name}
                      </span>
                    </div>
                    {/* Seta do Acordeão */}
                    <ChevronDown
                      size={20}
                      className={`flex-shrink-0 transition-transform duration-300 ${isPipelineOpen ? 'rotate-180' : 'rotate-0'
                        } ${isExpanded ? 'opacity-100' : 'opacity-0'}`}
                    />
                  </button>

                  {/* Submenu da Pipeline (Acordeão) */}
                  <div
                    className={`transition-all duration-300 ease-in-out overflow-hidden ${(isPipelineOpen && isExpanded) ? 'max-h-[500px]' : 'max-h-0'
                      } ${isExpanded ? 'pl-10' : 'pl-0'}`} // Ajusta o recuo quando expandido
                  >
                    <div className="flex flex-col space-y-1 pt-2">
                      {pipelineStatus.map(status => {
                        const isAllowed = hasSubpagePermission('pedidos', status.name);
                        
                        if (!isAllowed) {
                          return (
                            <div key={status.name} className={`flex items-center py-2 px-3 rounded-lg text-sm cursor-not-allowed opacity-40 grayscale bg-transparent text-gray-500 hover:bg-transparent ${!isExpanded ? 'justify-center' : ''}`}>
                              <span className="whitespace-nowrap overflow-hidden">
                                {status.name}
                              </span>
                            </div>
                          );
                        }

                        return (
                        <NavLink
                          key={status.name}
                          to={status.path}
                          className={({ isActive }) =>
                            `flex items-center py-2 px-3 rounded-lg text-sm ${isActive
                              ? 'bg-teal-600 text-white font-medium' // Sub-item ativo
                              : 'text-gray-300 hover:bg-gray-700'
                            } ${!isExpanded ? 'justify-center' : ''}` // Centraliza ícone se contraído
                          }
                        >

                          <span className="whitespace-nowrap overflow-hidden">
                            {status.name}
                          </span>

                        </NavLink>
                        );
                      })}
                    </div>
                  </div>
                </div>
              );
            }

            // Caso especial para "Integrações"
            if (item.name === 'Integrações') {
              if (!allowed) {
                return (
                  <div key={item.name} className={`flex items-center justify-between w-full p-3 rounded-lg ${disabledClass}`}>
                    <div className="flex items-center">
                      <item.icon size={24} className="flex-shrink-0" />
                      <span className={`ml-4 font-medium whitespace-nowrap overflow-hidden transition-all duration-200 ${isExpanded ? 'opacity-100 w-full' : 'opacity-0 w-0'}`}>{item.name}</span>
                    </div>
                  </div>
                );
              }
              return (
                <div key={item.name}>
                  <button
                    onClick={() => setIsIntegraOpen(!isIntegraOpen)}
                    className={`flex items-center justify-between w-full p-3 rounded-lg transition-colors duration-200 ${isIntegraActive
                      ? 'bg-teal-700 text-white' // Ativo
                      : 'hover:bg-teal-600' // Normal
                      }`}
                  >
                    <div className="flex items-center">
                      <item.icon size={24} className="flex-shrink-0" />
                      <span className={`ml-4 font-medium whitespace-nowrap overflow-hidden transition-all duration-200 ${isExpanded ? 'opacity-100 w-full' : 'opacity-0 w-0'}`}>
                        {item.name}
                      </span>
                    </div>
                    {/* Seta do Acordeão */}
                    <ChevronDown
                      size={20}
                      className={`flex-shrink-0 transition-transform duration-300 ${isIntegraOpen ? 'rotate-180' : 'rotate-0'
                        } ${isExpanded ? 'opacity-100' : 'opacity-0'}`}
                    />
                  </button>

                  {/* Submenu de Integrações */}
                  <div
                    className={`transition-all duration-300 ease-in-out overflow-hidden ${(isIntegraOpen && isExpanded) ? 'max-h-96' : 'max-h-0'
                      } ${isExpanded ? 'pl-10' : 'pl-0'}`}
                  >
                    <div className="flex flex-col space-y-1 pt-2">
                      {integraItems.map(subItem => {
                        const isAllowed = hasSubpagePermission('integracoes', subItem.name);

                        if (!isAllowed) {
                          return (
                            <div key={subItem.name} className={`flex items-center py-2 px-3 rounded-lg text-sm cursor-not-allowed opacity-40 grayscale bg-transparent text-gray-500 hover:bg-transparent ${!isExpanded ? 'justify-center' : ''}`}>
                              <span className="whitespace-nowrap overflow-hidden">
                                {subItem.name}
                              </span>
                            </div>
                          );
                        }

                        const isElasticEmail = subItem.name === 'Elastic Email';

                        return (
                        <NavLink
                          key={subItem.name}
                          to={subItem.path}
                          onClick={(e) => isElasticEmail ? handleSingletonClick(e, 'elastic_email_configuracoes') : null}
                          className={({ isActive }) => {
                            const isPathActive = isActive || (isElasticEmail && location.pathname.startsWith('/elastic_email_configuracoes'));
                            return `flex items-center py-2 px-3 rounded-lg text-sm ${
                              isPathActive
                              ? 'bg-teal-600 text-white font-medium'
                              : 'text-gray-300 hover:bg-gray-700'
                            } ${!isExpanded ? 'justify-center' : ''}`;
                          }}
                        >
                          <span className="whitespace-nowrap overflow-hidden">
                            {subItem.name}
                          </span>
                        </NavLink>
                        );
                      })}
                    </div>
                  </div>
                </div>
              );
            }

            // Caso especial para "Financeiro"
            if (item.name === 'Financeiro') {
              if (!allowed) {
                return (
                  <div key={item.name} className={`flex items-center justify-between w-full p-3 rounded-lg ${disabledClass}`}>
                    <div className="flex items-center">
                      <item.icon size={24} className="flex-shrink-0" />
                      <span className={`ml-4 font-medium whitespace-nowrap overflow-hidden transition-all duration-200 ${isExpanded ? 'opacity-100 w-full' : 'opacity-0 w-0'}`}>{item.name}</span>
                    </div>
                  </div>
                );
              }
              return (
                <div key={item.name}>
                  <button
                    onClick={() => setIsFinanceiroOpen(!isFinanceiroOpen)}
                    className={`flex items-center justify-between w-full p-3 rounded-lg transition-colors duration-200 ${isFinanceiroActive
                      ? 'bg-teal-700 text-white' // Ativo
                      : 'hover:bg-teal-600' // Normal
                      }`}
                  >
                    <div className="flex items-center">
                      <item.icon size={24} className="flex-shrink-0" />
                      <span className={`ml-4 font-medium whitespace-nowrap overflow-hidden transition-all duration-200 ${isExpanded ? 'opacity-100 w-full' : 'opacity-0 w-0'}`}>
                        {item.name}
                      </span>
                    </div>
                    {/* Seta do Acordeão */}
                    <ChevronDown
                      size={20}
                      className={`flex-shrink-0 transition-transform duration-300 ${isFinanceiroOpen ? 'rotate-180' : 'rotate-0'
                        } ${isExpanded ? 'opacity-100' : 'opacity-0'}`}
                    />
                  </button>

                  {/* Submenu Financeiro */}
                  <div
                    className={`transition-all duration-300 ease-in-out overflow-hidden ${(isFinanceiroOpen && isExpanded) ? 'max-h-96' : 'max-h-0'
                      } ${isExpanded ? 'pl-10' : 'pl-0'}`}
                  >
                    <div className="flex flex-col space-y-1 pt-2">
                      {financeiroItems.map(subItem => {
                        const isAllowed = hasSubpagePermission('contas', subItem.name);

                        if (!isAllowed) {
                          return (
                            <div key={subItem.name} className={`flex items-center py-2 px-3 rounded-lg text-sm cursor-not-allowed opacity-40 grayscale bg-transparent text-gray-500 hover:bg-transparent ${!isExpanded ? 'justify-center' : ''}`}>
                              <span className="whitespace-nowrap overflow-hidden">
                                {subItem.name}
                              </span>
                            </div>
                          );
                        }
                        return (
                        <NavLink
                          key={subItem.name}
                          to={subItem.path}
                          className={({ isActive }) =>
                            `flex items-center py-2 px-3 rounded-lg text-sm ${isActive
                              ? 'bg-teal-600 text-white font-medium'
                              : 'text-gray-300 hover:bg-gray-700'
                            } ${!isExpanded ? 'justify-center' : ''}`
                          }
                        >
                          <span className="whitespace-nowrap overflow-hidden">
                            {subItem.name}
                          </span>
                        </NavLink>
                        );
                      })}
                    </div>
                  </div>
                </div>
              );
            }

            // Caso especial para "Estoque"
            if (item.name === 'Estoque') {
              if (!allowed) {
                return (
                  <div key={item.name} className={`flex items-center justify-between w-full p-3 rounded-lg ${disabledClass}`}>
                    <div className="flex items-center">
                      <item.icon size={24} className="flex-shrink-0" />
                      <span className={`ml-4 font-medium whitespace-nowrap overflow-hidden transition-all duration-200 ${isExpanded ? 'opacity-100 w-full' : 'opacity-0 w-0'}`}>{item.name}</span>
                    </div>
                  </div>
                );
              }
              return (
                <div key={item.name}>
                  <button
                    onClick={() => setIsEstoqueOpen(!isEstoqueOpen)}
                    className={`flex items-center justify-between w-full p-3 rounded-lg transition-colors duration-200 ${isEstoqueActive
                      ? 'bg-teal-700 text-white' // Ativo
                      : 'hover:bg-teal-600' // Normal
                      }`}
                  >
                    <div className="flex items-center">
                      <item.icon size={24} className="flex-shrink-0" />
                      <span className={`ml-4 font-medium whitespace-nowrap overflow-hidden transition-all duration-200 ${isExpanded ? 'opacity-100 w-full' : 'opacity-0 w-0'}`}>
                        {item.name}
                      </span>
                    </div>
                    {/* Seta do Acordeão */}
                    <ChevronDown
                      size={20}
                      className={`flex-shrink-0 transition-transform duration-300 ${isEstoqueOpen ? 'rotate-180' : 'rotate-0'
                        } ${isExpanded ? 'opacity-100' : 'opacity-0'}`}
                    />
                  </button>

                  {/* Submenu de Estoque */}
                  <div
                    className={`transition-all duration-300 ease-in-out overflow-hidden ${(isEstoqueOpen && isExpanded) ? 'max-h-[256px]' : 'max-h-0'
                      } ${isExpanded ? 'pl-10' : 'pl-0'}`}
                  >
                    <div className="flex flex-col space-y-1 pt-2">
                      {estoqueItems.map(subItem => {
                        const isAllowed = hasSubpagePermission('estoque', subItem.name);

                        if (!isAllowed) {
                          return (
                            <div key={subItem.name} className={`flex items-center py-2 px-3 rounded-lg text-sm cursor-not-allowed opacity-40 grayscale bg-transparent text-gray-500 hover:bg-transparent ${!isExpanded ? 'justify-center' : ''}`}>
                              <span className="whitespace-nowrap overflow-hidden">
                                {subItem.name}
                              </span>
                            </div>
                          );
                        }

                        return (
                        <NavLink
                          key={subItem.name}
                          to={subItem.path}
                          className={({ isActive }) =>
                            `flex items-center py-2 px-3 rounded-lg text-sm ${
                              isActive
                              ? 'bg-teal-600 text-white font-medium'
                              : 'text-gray-300 hover:bg-gray-700'
                            } ${!isExpanded ? 'justify-center' : ''}`
                          }
                        >
                          <span className="whitespace-nowrap overflow-hidden">
                            {subItem.name}
                          </span>
                        </NavLink>
                        );
                      })}
                    </div>
                  </div>
                </div>
              );
            }

            // Itens Padrão Desabilitados
            if (!allowed) {
              return (
                <div key={item.name} className={`flex items-center p-3 rounded-lg ${disabledClass}`}>
                  <item.icon size={24} className="flex-shrink-0" />
                  <span className={`ml-4 font-medium whitespace-nowrap overflow-hidden transition-all duration-200 ${isExpanded ? 'opacity-100 w-full' : 'opacity-0 w-0'}`}>{item.name}</span>
                </div>
              );
            }

            // Lógica original para os outros itens
            return (
              <NavLink
                key={item.name}
                to={item.path}
                end={item.exact}
                className={({ isActive }) =>
                  `flex items-center p-3 rounded-lg transition-colors duration-200 ${isActive ? 'bg-teal-700 text-white' : 'hover:bg-teal-600'
                  }`
                }
              >
                <item.icon size={24} className="flex-shrink-0" />
                <span className={`ml-4 font-medium whitespace-nowrap overflow-hidden transition-all duration-200 ${isExpanded ? 'opacity-100 w-full' : 'opacity-0 w-0'}`}>
                  {item.name}
                </span>
              </NavLink>
            );
          })}
        </nav>

        {/* Rodapé (adaptado do seu exemplo) */}
        <div className="border-t border-white/20 pt-4">

          {/* Informações do Usuário (do seu layout anterior, agora adaptado) */}
          <div className={`flex items-center p-3 rounded-lg overflow-hidden transition-all duration-200 ${isExpanded ? 'opacity-100 mb-2' : 'opacity-0 h-0'}`}>
            <UserCircle size={24} className="flex-shrink-0 text-gray-400" />
            <div className={`ml-4 whitespace-nowrap overflow-hidden transition-all duration-200 ${isExpanded ? 'opacity-100 w-full' : 'opacity-0 w-0'}`}>
              <p className="text-sm font-medium text-gray-100 truncate">{user?.email}</p>
              <p className="text-xs text-gray-400 capitalize">{user?.perfil}</p>
            </div>
          </div>

          {/* Botão Sair */}
          <button
            onClick={handleLogout}
            className="flex items-center p-3 rounded-lg w-full text-red-300 hover:bg-red-600 hover:text-white transition-colors duration-200"
          >
            <LogOut size={24} className="flex-shrink-0" />
            <span className={`ml-4 font-medium whitespace-nowrap text-start overflow-hidden transition-all duration-200 ${isExpanded ? 'opacity-100 w-full' : 'opacity-0 w-0'}`}>
              Sair
            </span>
          </button>
        </div>
      </aside>

      {/* Wrapper para Header e Conteúdo Principal */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header (NOVO) */}
        <header className="bg-white shadow-md py-3 px-4 z-10">
          <div className="flex justify-end items-center">

            {/* Ícones do Header - Ajustado o espaçamento para space-x-4 */}
            <div className="flex items-center space-x-4 text-gray-600">

              {/* ===== BOTÃO DE AJUDA (WHATSAPP) ADICIONADO ===== */}
              <a
                // IMPORTANTE: Troque pelo seu número de WhatsApp
                href="https://wa.me/5545999861237"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center text-green-600 hover:text-green-700 transition-colors duration-200 p-2 rounded-lg hover:bg-green-50"
                title="Ajuda via WhatsApp"
              >
                <FaWhatsapp size={22} />
                <span className='hidden sm:inline ml-1.5 font-medium'>Suporte</span>
              </a>
            </div>
          </div>
        </header>

        {/* Conteúdo Principal (Alterado) */}
        {/* Adicionado bg-gray-100 aqui */}
        <main className="flex-1 overflow-x-hidden overflow-y-scroll bg-gray-100">
          <Outlet />
        </main>
      </div>

    </div>
  );
};

export default MainLayout;
