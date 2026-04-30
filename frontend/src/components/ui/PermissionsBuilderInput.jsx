// frontend/src/components/ui/PermissionsBuilderInput.jsx

import React, { useState, useEffect } from 'react';
import { ChevronDown, ChevronRight, Check, Loader2, AlertCircle } from 'lucide-react';
import api from '../../api/axiosConfig';

// Definição dos módulos do sistema e suas capacidades
const SYSTEM_MODULES = [
  { 
    key: 'dashboard', 
    label: 'Dashboard', 
    model: null 
  },
  { 
    key: 'empresas', 
    label: 'Minha Empresa', 
    model: 'empresas', 
    actions: [{key: 'edit', label: 'Editar'}] 
  },
  { 
    key: 'usuarios', 
    label: 'Usuários', 
    model: 'usuarios', 
    actions: [{key: 'create', label: 'Criar'}, {key: 'edit', label: 'Editar'}, {key: 'delete', label: 'Deletar'}],
    subpages: [
      {key: 'Usuários', label: 'Usuários'},
      {key: 'Perfis', label: 'Perfis'}
    ]
  },
  { 
    key: 'cadastros', 
    label: 'Cadastros', 
    model: 'cadastros', 
    actions: [{key: 'create', label: 'Criar'}, {key: 'edit', label: 'Editar'}, {key: 'delete', label: 'Deletar'}, {key: 'export', label: 'Exportar'}] 
  },
  { 
    key: 'produtos', 
    label: 'Produtos', 
    model: 'produtos', 
    actions: [{key: 'create', label: 'Criar'}, {key: 'edit', label: 'Editar'}, {key: 'delete', label: 'Deletar'}, {key: 'export', label: 'Exportar'}] 
  },
  { 
    key: 'pedidos', 
    label: 'Pedidos', 
    model: 'pedidos', 
    actions: [
        {key: 'create', label: 'Criar'}, 
        {key: 'edit', label: 'Editar'}, 
        {key: 'delete', label: 'Deletar'},
        {key: 'export', label: 'Exportar'},
        {key: 'programar', label: 'Programar'},
        {key: 'conferencia', label: 'Conferência'},
        {key: 'imprimir_etiqueta_volume', label: 'Etiqueta Volume'},
        {key: 'faturamento', label: 'Faturar'},
        {key: 'download_danfe', label: 'Baixar DANFE'},
        {key: 'imprimir_etiqueta', label: 'Etiqueta Transporte'},
        {key: 'cancelar_nfe', label: 'Cancelar NFe'},
        {key: 'carta_correcao', label: 'Carta de Correção'},
        {key: 'devolucao', label: 'Devolução'}
    ],
    subpages: [
        {key: 'Todos', label: 'Todos'},
        {key: 'Orçamento', label: 'Orçamento'},
        {key: 'Aprovação', label: 'Aprovação'},
        {key: 'Programação', label: 'Programação'},
        {key: 'Produção', label: 'Produção'},
        {key: 'Embalagem', label: 'Embalagem'},
        {key: 'Faturamento', label: 'Faturamento'},
        {key: 'Expedição', label: 'Expedição'},
        {key: 'Nota Fiscal', label: 'Nota Fiscal'},
        {key: 'Cancelado', label: 'Cancelado'}
    ]
  },
  { 
    key: 'embalagens', 
    label: 'Embalagens', 
    model: 'embalagens', 
    actions: [{key: 'create', label: 'Criar'}, {key: 'edit', label: 'Editar'}, {key: 'delete', label: 'Deletar'}] 
  },
  { 
    key: 'estoque', 
    label: 'Estoque', 
    model: 'estoque', 
    actions: [{key: 'create', label: 'Criar'}, {key: 'edit', label: 'Editar'}, {key: 'delete', label: 'Deletar'}],
    subpages: [
      {key: 'Saldo', label: 'Saldo'},
      {key: 'Movimentações', label: 'Movimentações'}
    ]
  },
  { 
    key: 'contas', 
    label: 'Financeiro', 
    model: 'contas', 
    actions: [{key: 'create', label: 'Criar'}, {key: 'edit', label: 'Editar'}, {key: 'delete', label: 'Deletar'}, {key: 'export', label: 'Exportar'}],
    subpages: [
      {key: 'Contas', label: 'Contas a Pagar/Receber'},
      {key: 'Contábil', label: 'Plano de Contas'}
    ]
  },
  { 
    key: 'tributacoes', 
    label: 'Regras Tributárias', 
    model: 'tributacoes', 
    actions: [{key: 'create', label: 'Criar'}, {key: 'edit', label: 'Editar'}, {key: 'delete', label: 'Deletar'}] 
  },
  { 
    key: 'relatorios', 
    label: 'Relatórios', 
    model: 'relatorios', 
    actions: [{key: 'create', label: 'Criar'}, {key: 'edit', label: 'Editar'}, {key: 'delete', label: 'Deletar'}, {key: 'generate', label: 'Gerar'}] 
  },
  { 
    key: 'integracoes', 
    label: 'Integrações', 
    model: null, 
    actions: [{key: 'manage', label: 'Gerenciar'}],
    subpages: [
      {key: 'Intelipost', label: 'Intelipost'},
      {key: 'Mercado Livre', label: 'Mercado Livre'},
      {key: 'Magento', label: 'Magento'}
    ]
  },
];

export const PermissionsBuilderInput = ({ field, value, onChange }) => {
  // Estado local para gerenciar as permissões
  const [permissions, setPermissions] = useState(value || {});
  const [expandedModule, setExpandedModule] = useState(null);
  
  // Cache de metadados para colunas (model_name -> metadata)
  const [moduleMetadata, setModuleMetadata] = useState({});
  const [loadingMeta, setLoadingMeta] = useState(false);

  // Sincroniza com prop value se mudar externamente
  useEffect(() => {
    if (value) setPermissions(value);
  }, [value]);

  // Função para notificar o componente pai (Form)
  const updateParent = (newPerms) => {
    setPermissions(newPerms);
    onChange({ target: { name: field.name, value: newPerms } });
  };

  // Busca metadados para listar colunas
  const fetchMetadata = async (modelName) => {
    if (moduleMetadata[modelName]) return; // Já carregado
    
    setLoadingMeta(true);
    try {
        const res = await api.get(`/metadata/${modelName}`);
        setModuleMetadata(prev => ({ ...prev, [modelName]: res.data }));
    } catch (err) {
        console.error(`Erro ao buscar metadados para ${modelName}:`, err);
    } finally {
        setLoadingMeta(false);
    }
  };

  // Toggle Módulo (Ativa/Desativa acesso geral)
  const handleModuleToggle = (moduleKey) => {
    const newPermissions = { ...permissions };
    
    if (newPermissions[moduleKey] && newPermissions[moduleKey].acesso) {
      // Se já tem acesso, remove (ou marca como false)
      delete newPermissions[moduleKey];
      if (expandedModule === moduleKey) setExpandedModule(null);
    } else {
      // Concede acesso inicial
      newPermissions[moduleKey] = { 
        acesso: true, 
        acoes: [], 
        subpaginas: [], 
        colunas: [] 
      };
    }
    updateParent(newPermissions);
  };

  // Toggle Expandir Detalhes
  const toggleExpand = (moduleKey, modelName) => {
    if (expandedModule === moduleKey) {
      setExpandedModule(null);
    } else {
      setExpandedModule(moduleKey);
      // Se o módulo tem um model associado e temos acesso, busca colunas
      if (modelName && permissions[moduleKey]?.acesso) {
        fetchMetadata(modelName);
      }
    }
  };

  // Toggle Ação (Botão)
  const handleActionToggle = (moduleKey, actionKey) => {
    const newPermissions = { ...permissions };
    if (!newPermissions[moduleKey]) return;

    const current = newPermissions[moduleKey].acoes || [];
    if (current.includes(actionKey)) {
      newPermissions[moduleKey].acoes = current.filter(k => k !== actionKey);
    } else {
      newPermissions[moduleKey].acoes = [...current, actionKey];
    }
    updateParent(newPermissions);
  };

  // Toggle Subpágina
  const handleSubpageToggle = (moduleKey, subpageKey) => {
    const newPermissions = { ...permissions };
    if (!newPermissions[moduleKey]) return;

    const current = newPermissions[moduleKey].subpaginas || [];
    if (current.includes(subpageKey)) {
      newPermissions[moduleKey].subpaginas = current.filter(k => k !== subpageKey);
    } else {
      newPermissions[moduleKey].subpaginas = [...current, subpageKey];
    }
    updateParent(newPermissions);
  };

  // Toggle Coluna
  const handleColumnToggle = (moduleKey, colName) => {
    const newPermissions = { ...permissions };
    if (!newPermissions[moduleKey]) return;

    const current = newPermissions[moduleKey].colunas || [];
    if (current.includes(colName)) {
      newPermissions[moduleKey].colunas = current.filter(k => k !== colName);
    } else {
      newPermissions[moduleKey].colunas = [...current, colName];
    }
    updateParent(newPermissions);
  };

  // Selecionar Todas as Colunas
  const handleSelectAllColumns = (moduleKey, allColumns) => {
    const newPermissions = { ...permissions };
    if (!newPermissions[moduleKey]) return;

    const current = newPermissions[moduleKey].colunas || [];
    // Se já tem todas, remove todas. Se não, adiciona todas.
    if (current.length === allColumns.length) {
        newPermissions[moduleKey].colunas = [];
    } else {
        newPermissions[moduleKey].colunas = [...allColumns];
    }
    updateParent(newPermissions);
  };

  return (
    <div className="space-y-2 border border-gray-200 rounded-md p-4 bg-gray-50">
      <label className="block text-sm font-medium text-gray-700 mb-2">
        {field.label}
      </label>
      
      <div className="space-y-2">
        {SYSTEM_MODULES.map((mod) => {
          const hasAccess = permissions[mod.key]?.acesso;
          const isExpanded = expandedModule === mod.key;
          
          return (
            <div key={mod.key} className="bg-white border border-gray-200 rounded-md overflow-hidden shadow-sm">
              {/* Header do Módulo */}
              <div className="flex items-center justify-between p-3 bg-gray-50 hover:bg-gray-100 transition-colors">
                <div className="flex items-center gap-3">
                  <input
                    type="checkbox"
                    checked={!!hasAccess}
                    onChange={() => handleModuleToggle(mod.key)}
                    className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded cursor-pointer"
                  />
                  <span className={`font-medium ${hasAccess ? 'text-gray-900' : 'text-gray-500'}`}>
                    {mod.label}
                  </span>
                </div>
                
                {hasAccess && (
                  <button
                    type="button"
                    onClick={() => toggleExpand(mod.key, mod.model)}
                    className="p-1 hover:bg-gray-200 rounded-full text-gray-500"
                  >
                    {isExpanded ? <ChevronDown size={20} /> : <ChevronRight size={20} />}
                  </button>
                )}
              </div>

              {/* Corpo Expansível */}
              {isExpanded && hasAccess && (
                <div className="p-4 border-t border-gray-200 space-y-6 animate-fadeIn">
                  
                  {/* Seção 1: Ações (Botões) */}
                  {mod.actions && mod.actions.length > 0 && (
                    <div>
                      <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Ações Permitidas</h4>
                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                        {mod.actions.map(action => (
                          <label key={action.key} className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer hover:bg-gray-50 p-1 rounded">
                            <input
                              type="checkbox"
                              checked={permissions[mod.key].acoes?.includes(action.key)}
                              onChange={() => handleActionToggle(mod.key, action.key)}
                              className="h-3.5 w-3.5 text-blue-600 border-gray-300 rounded"
                            />
                            {action.label}
                          </label>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Seção 2: Subpáginas (Filtros de Status) */}
                  {mod.subpages && mod.subpages.length > 0 && (
                    <div>
                      <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Sub-páginas (Abas)</h4>
                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                        {mod.subpages.map(sub => (
                          <label key={sub.key} className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer hover:bg-gray-50 p-1 rounded">
                            <input
                              type="checkbox"
                              checked={permissions[mod.key].subpaginas?.includes(sub.key)}
                              onChange={() => handleSubpageToggle(mod.key, sub.key)}
                              className="h-3.5 w-3.5 text-purple-600 border-gray-300 rounded"
                            />
                            {sub.label}
                          </label>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Seção 3: Colunas Visíveis */}
                  {mod.model && (
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider">Colunas Visíveis</h4>
                        {moduleMetadata[mod.model] && (
                            <button 
                                type="button"
                                onClick={() => handleSelectAllColumns(mod.key, moduleMetadata[mod.model].fields.map(f => f.name))}
                                className="text-xs text-blue-600 hover:text-blue-800 font-medium"
                            >
                                {permissions[mod.key].colunas?.length === moduleMetadata[mod.model].fields.length ? 'Desmarcar Todas' : 'Selecionar Todas'}
                            </button>
                        )}
                      </div>
                      
                      {loadingMeta ? (
                        <div className="flex items-center gap-2 text-sm text-gray-500 py-2">
                          <Loader2 size={16} className="animate-spin" /> Carregando colunas...
                        </div>
                      ) : moduleMetadata[mod.model] ? (
                        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2 max-h-60 overflow-y-auto pr-2 border border-gray-100 rounded p-2 bg-gray-50">
                          {moduleMetadata[mod.model].fields.map(f => (
                            <label key={f.name} className="flex items-center gap-2 text-xs text-gray-700 cursor-pointer hover:bg-white p-1 rounded transition-colors">
                              <input
                                type="checkbox"
                                checked={permissions[mod.key].colunas?.includes(f.name)}
                                onChange={() => handleColumnToggle(mod.key, f.name)}
                                className="h-3.5 w-3.5 text-green-600 border-gray-300 rounded"
                              />
                              <span className="truncate" title={f.label}>{f.label}</span>
                            </label>
                          ))}
                        </div>
                      ) : (
                        <div className="text-sm text-gray-400 italic flex items-center gap-1">
                            <AlertCircle size={14} /> Não foi possível carregar as colunas.
                        </div>
                      )}
                      <p className="text-[10px] text-gray-400 mt-1">
                        * Se nenhuma coluna for selecionada, todas serão exibidas por padrão.
                      </p>
                    </div>
                  )}

                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
