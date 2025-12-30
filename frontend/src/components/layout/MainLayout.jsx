import React, { useState, useEffect, useMemo } from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
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
} from 'lucide-react';
import { FaWhatsapp } from 'react-icons/fa';
import { useLocation } from 'react-router-dom';
import { ChevronDown } from 'lucide-react'; // Ícone para o acordeão

const MainLayout = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  // O estado de expansão agora é controlado pelo novo layout
  const [isExpanded, setIsExpanded] = useState(false);

  // Array de itens do menu (do seu ERP)
  const menuItems = [
    { name: 'Dashboard', path: '/', icon: Home, exact: true },
    { name: 'Usuários', path: '/usuarios', icon: Users, perfil: 'admin' }, // Exemplo: só admin vê 'users'
    { name: 'Cadastros', path: '/cadastros', icon: List },
    { name: 'Produtos', path: '/produtos', icon: Box },
    { name: 'Pedidos', path: '/pedidos', icon: ShoppingCart },
    { name: 'Embalagens', path: '/embalagens', icon: Archive },
    { name: 'Estoque', path: '/estoque', icon: Package },
    { name: 'Financeiro', path: '/contas', icon: Landmark },
    { name: 'Fiscal', path: '/tributacoes', icon: Layers },
    // Adicione mais itens conforme necessário
  ];

  // Filtra itens do menu com base na perfil do usuário (lógica do ERP)
  const filteredMenuItems = menuItems.filter(item => {
    if (item.perfil && user && user.perfil !== item.perfil) {
      return false;
    }
    return true;
  });

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
    { name: 'Histórico', path: '/pedidos' }, // "Histórico" aponta para a raiz de pedidos
  ], []); // Array de dependência vazio, é estático

  // [NOVO] Cria a lista de paths
  const pipelinePaths = useMemo(() =>
    pipelineStatus.map(status => status.path),
    [pipelineStatus]
  );

  // Esta variável (isPedidosActive) continua correta para o "highlight" do ícone
  const isPedidosActive = location.pathname.startsWith('/pedidos');

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

  useEffect(() => {
    // SÓ ABRE se a rota for EXATA.
    // NUNCA FECHE (sem 'else'), para não conflitar com o clique manual.
    if (isPipelineListActive) {
      setIsPipelineOpen(true);
    }
  }, [isPipelineListActive]); // Depende da booleana específica

  const handleMouseEnter = () => {
    setIsExpanded(true);
    // Reabre a pipeline APENAS se o usuário estiver em uma ROTA DA LISTA.
    if (isPipelineListActive) {
      setIsPipelineOpen(true);
    }
  };

  // Ele deve fechar o acordeão ao sair.
  const handleMouseLeave = () => {
    setIsExpanded(false);
    setIsPipelineOpen(false); // [Esta é a sua solicitação] Fecha a pipeline
  };

  return (
    <div className="flex h-screen bg-gray-100 font-sans">
      {/* Sidebar (Layout copiado do seu exemplo, mas com dados e cores do ERP) */}
      <aside
        className={`relative h-screen bg-gray-800 text-white p-4 flex flex-col transition-all duration-300 ease-in-out ${isExpanded ? 'w-64 overflow-y-auto' : 'w-20'}`}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
      >
        {/* Logo (adaptado do seu exemplo) */}
        <div className="flex items-center mb-10" style={{ height: '40px' }}>
          <div className="bg-gray-700 w-12 h-12 flex items-center justify-center rounded-lg flex-shrink-0">
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
        <nav className="flex-1 flex flex-col space-y-2">
          {filteredMenuItems.map(item => {
            // Caso especial para "Pedidos"
            if (item.name === 'Pedidos') {
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
                    className={`transition-all duration-300 ease-in-out overflow-hidden ${isPipelineOpen ? 'max-h-96' : 'max-h-0'
                      } ${isExpanded ? 'pl-10' : 'pl-0'}`} // Ajusta o recuo quando expandido
                  >
                    <div className="flex flex-col space-y-1 pt-2">
                      {pipelineStatus.map(status => (
                        <NavLink
                          key={status.name}
                          to={status.path}
                          end={status.path === '/pedidos'} // "end" para o Histórico
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
                      ))}
                    </div>
                  </div>
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
