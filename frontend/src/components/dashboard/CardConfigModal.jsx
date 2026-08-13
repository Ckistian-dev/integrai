import React, { useState, useEffect, Fragment } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { X, Save, BarChart2, Table, Filter, Calculator, Type, Plus} from 'lucide-react';
import api from '../../api/axiosConfig';
import { DefaultFiltersInput } from '../ui/InputFields';
import Select from 'react-select';

const CardConfigModal = ({ isOpen, onClose, onSave, initialConfig, preSelectedType, }) => {
  const [config, setConfig] = useState({
    titulo: '',
    tipo: 'metrica',
    modelo: 'pedidos',
    operacao: 'count',
    campo: 'id',
    campo2: '',
    agrupar_por: '',
    formato: 'numero',
    colunas: [],
    filtros: [],
    series: [],
    texto_conteudo: '',
    valor_meta: '',
    meta_progressiva: false,
    acumular_valores: false,
    eixo_x_nome: '',
    eixo_x_formato: 'data',
    eixo_x_cor: '#6b7280',
    eixo_x_preencher_vazio: false
  });

  const [metadataFields, setMetadataFields] = useState([]);
  const [loadingMetadata, setLoadingMetadata] = useState(false);

  // Tabelas disponíveis para o Dashboard
  const modelosDisponiveis = [
    { value: 'todos', label: 'Todas as Tabelas (Global)' },
    { value: 'pedidos', label: 'Pedidos de Venda' },
    { value: 'contas', label: 'Financeiro (Contas)' },
    { value: 'produtos', label: 'Produtos' },
    { value: 'cadastros', label: 'Clientes/Fornecedores' }
  ];

  // Carrega a configuração inicial quando abre para editar
  useEffect(() => {
    if (isOpen) {
      let initialType = preSelectedType || 'metrica';
      if (initialType === 'grafico') initialType = 'barra'; // Corrige o mapeamento inicial de Gráfico

      let loadedConfig = initialConfig || {};
      let seriesConfig = loadedConfig.series || [];

      // Auto-migra cards antigos para a nova matriz de séries
      if (initialConfig && ['barra', 'linha', 'area', 'composed', 'grafico'].includes(loadedConfig.tipo) && seriesConfig.length === 0) {
        if (loadedConfig.campo) {
          seriesConfig.push({
            id: 'y1',
            nome: loadedConfig.titulo || 'Valor 1',
            tipo: loadedConfig.tipo === 'composed' ? 'barra' : loadedConfig.tipo,
            campo: loadedConfig.campo,
            operacao: (loadedConfig.operacao === 'count' && loadedConfig.campo === 'id') ? 'count' : loadedConfig.operacao,
            formato: loadedConfig.formato || 'numero',
            cor: '#3b82f6',
            is_meta: false
          });
        }
        if (loadedConfig.campo2) {
          seriesConfig.push({
            id: 'y2',
            nome: 'Valor Secundário',
            tipo: loadedConfig.tipo === 'composed' ? 'linha' : loadedConfig.tipo,
            campo: loadedConfig.campo2,
            operacao: loadedConfig.operacao,
            formato: loadedConfig.formato || 'numero',
            cor: '#10b981',
            is_meta: false
          });
        }
        if (loadedConfig.valor_meta) {
          seriesConfig.push({
            id: 'meta1',
            nome: 'Meta',
            tipo: 'linha',
            is_meta: true,
            valor_meta: loadedConfig.valor_meta,
            meta_progressiva: loadedConfig.meta_progressiva,
            formato: loadedConfig.formato || 'numero',
            cor: '#ef4444'
          });
        }
      }

      setConfig({
        titulo: 'Novo Card',
        tipo: initialType,
        modelo: 'pedidos',
        operacao: 'count',
        campo: 'id',
        campo2: '',
        agrupar_por: '',
        formato: 'numero',
        colunas: [],
        filtros: [],
        series: seriesConfig,
        texto_conteudo: '',
        valor_meta: '',
        meta_progressiva: false,
        acumular_valores: false,
        eixo_x_nome: '',
        eixo_x_formato: 'data',
        eixo_x_cor: '#6b7280',
        eixo_x_preencher_vazio: false,
        ...loadedConfig
      });
    }
  }, [isOpen, initialConfig, preSelectedType]);

  // Busca metadados sempre que o "modelo" (tabela) mudar
  useEffect(() => {
    if (!config.modelo || !isOpen || config.modelo === 'todos') return;

    const fetchFields = async () => {
      setLoadingMetadata(true);
      try {
        const res = await api.get(`/metadata/${config.modelo}`);
        setMetadataFields(res.data.fields || []);
        
        // Se mudou de modelo e o campo atual não existe no novo modelo, reseta para 'id'
        const campoExiste = res.data.fields.some(f => f.name === config.campo);
        if (!campoExiste && config.campo !== 'id' && config.campo !== '__search__') {
          setConfig(prev => ({ ...prev, campo: 'id', agrupar_por: '' }));
        }
      } catch (err) {
        console.error("Erro ao buscar metadados:", err);
      } finally {
        setLoadingMetadata(false);
      }
    };

    fetchFields();
  }, [config.modelo, isOpen]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setConfig(prev => ({ ...prev, [name]: value }));
  };

  const handleSave = (e) => {
    e.preventDefault();
    
    // Para filtros, salva as opções de Select no próprio config para não precisar buscar dnv
    let finalConfig = { ...config };
    if (config.tipo === 'filtro' && config.operacao === 'checkbox_list') {
       const fieldMeta = metadataFields.find(f => f.name === config.campo);
       if (fieldMeta && fieldMeta.options) {
           finalConfig.opcoes = fieldMeta.options;
       }
    }
    
    // Para gráficos, salva campo primário e secundário como array de colunas para o backend entender
    if (['pizza', 'barra', 'linha', 'area', 'composed'].includes(config.tipo)) {
       finalConfig.colunas = [config.campo];
       if (config.campo2) finalConfig.colunas.push(config.campo2);
    }
    
    onSave(finalConfig);
  };

  // Handler de Séries Y
  const handleAddSeries = () => {
    const newId = `s_${Date.now()}`;
    setConfig(prev => ({
      ...prev,
      series: [
        ...(prev.series || []),
        { id: newId, nome: `Série ${(prev.series?.length || 0) + 1}`, tipo: 'barra', is_meta: false, campo: 'id', operacao: 'count', formato: 'numero', cor: '#3b82f6' }
      ]
    }));
  };

  const updateSeries = (id, field, value) => {
    setConfig(prev => ({
      ...prev,
      series: prev.series.map(s => s.id === id ? { ...s, ...field } : s)
    }));
  };

  const updateSingleSeriesField = (id, field, value) => {
    updateSeries(id, { [field]: value });
  };

  const removeSeries = (id) => {
    setConfig(prev => ({
      ...prev,
      series: prev.series.filter(s => s.id !== id)
    }));
  };

  // Filtra colunas numéricas para operações de SOMA
  const numericFields = metadataFields.filter(f => 
    f.type === 'number' || f.type === 'currency' || f.format_mask === 'currency'
  );

  // Renderização Dinâmica de Ícone Baseado no Tipo
  const renderIcon = () => {
    switch(config.tipo) {
      case 'metrica': return <Calculator className="w-5 h-5 mr-2 text-indigo-600" />;
      case 'tabela': return <Table className="w-5 h-5 mr-2 text-green-600" />;
      case 'filtro': return <Filter className="w-5 h-5 mr-2 text-orange-600" />;
      case 'texto': return <Type className="w-5 h-5 mr-2 text-purple-600" />;
      default: return <BarChart2 className="w-5 h-5 mr-2 text-blue-600" />;
    }
  };

  return (
    <Transition.Root show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={onClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity" />
        </Transition.Child>

        <div className="fixed inset-0 z-10 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4 text-center sm:p-0">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-300"
              enterFrom="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95"
              enterTo="opacity-100 translate-y-0 sm:scale-100"
              leave="ease-in duration-200"
              leaveFrom="opacity-100 translate-y-0 sm:scale-100"
              leaveTo="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95"
            >
              <Dialog.Panel className="relative transform overflow-hidden rounded-lg bg-white text-left shadow-xl transition-all sm:my-8 sm:w-full sm:max-w-6xl">
                <form onSubmit={handleSave}>
                  <div className="bg-white px-4 pb-4 pt-5 sm:p-6 sm:pb-4">
                    <div className="flex justify-between items-center mb-5">
                      <Dialog.Title as="h3" className="text-xl font-bold leading-6 text-gray-900 flex items-center">
                        {renderIcon()}
                        Configurar Card
                      </Dialog.Title>
                      <button type="button" onClick={onClose} className="text-gray-400 hover:text-gray-500">
                        <X className="h-6 w-6" />
                      </button>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {/* Título */}
                      <div className="md:col-span-2">
                        <label className="block text-sm font-medium text-gray-700">Título do Card</label>
                        <input
                          type="text"
                          name="titulo"
                          required
                          value={config.titulo}
                          onChange={handleChange}
                          className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-blue-500 sm:text-sm"
                          placeholder={config.tipo === 'filtro' ? "Ex: Filtrar por Status" : "Ex: Receita Total"}
                        />
                      </div>

                      {config.tipo === 'texto' && (
                        <div className="md:col-span-2">
                          <label className="block text-sm font-medium text-gray-700">Conteúdo do Texto</label>
                          <textarea
                            name="texto_conteudo"
                            rows={6}
                            value={config.texto_conteudo || ''}
                            onChange={handleChange}
                            className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-blue-500 sm:text-sm"
                            placeholder="Digite o texto aqui..."
                          />
                        </div>
                      )}

                      {config.tipo !== 'texto' && (
                        <>
                      {/* Tabela Base */}
                      <div>
                        <label className="block text-sm font-medium text-gray-700">Fonte de Dados (Tabela)</label>
                        <select
                          name="modelo"
                          value={config.modelo}
                          onChange={handleChange}
                          className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-blue-500 sm:text-sm"
                        >
                          {modelosDisponiveis.map(m => (
                            <option key={m.value} value={m.value}>{m.label}</option>
                          ))}
                        </select>
                      </div>

                      {/* --- CONFIGURAÇÕES ESPECÍFICAS PARA MÉTRICAS E GRÁFICOS --- */}
                      {['metrica', 'pizza', 'barra', 'linha', 'area', 'composed'].includes(config.tipo) && (
                        <>
                          {/* Subtipo de Gráfico (Se for gráfico, permite trocar entre pizza/barra/linha) */}
                          {config.tipo !== 'metrica' && (
                            <div>
                              <label className="block text-sm font-medium text-gray-700">Tipo de Gráfico</label>
                              <select name="tipo" value={config.tipo} onChange={handleChange} className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-blue-500 sm:text-sm">
                                <option value="pizza">Gráfico de Pizza</option>
                                <option value="barra">Gráfico de Colunas/Barras</option>
                                <option value="linha">Gráfico de Linha</option>
                                <option value="area">Gráfico de Crescimento (Área)</option>
                                <option value="composed">Gráfico Misto (Colunas e Linhas)</option>
                              </select>
                            </div>
                          )}

                          {config.tipo !== 'metrica' && (
                            <div className="md:col-span-2 mt-2 bg-gray-50 p-4 rounded-lg border border-gray-200">
                              <h4 className="text-sm font-bold text-gray-800 mb-3 border-b pb-2">Configuração do Eixo X (Horizontal)</h4>
                              <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
                                <div>
                                  <label className="block text-xs font-medium text-gray-500 mb-1">Campo Alvo (Agrupar Por)</label>
                                  <select
                                    name="agrupar_por"
                                    required={true}
                                    value={config.agrupar_por}
                                    onChange={handleChange}
                                    disabled={loadingMetadata}
                                    className="block w-full rounded-md border border-gray-300 px-2 py-1.5 shadow-sm focus:border-blue-500 sm:text-sm disabled:bg-gray-100"
                                  >
                                    <option value="">Selecione um campo...</option>
                                    {metadataFields.map(f => (
                                      <option key={f.name} value={f.name}>{f.label}</option>
                                    ))}
                                  </select>
                                </div>
                                <div>
                                  <label className="block text-xs font-medium text-gray-500 mb-1">Nome do Eixo</label>
                                  <input type="text" name="eixo_x_nome" value={config.eixo_x_nome || ''} onChange={handleChange} className="block w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm shadow-sm focus:border-blue-500" placeholder="Automático" />
                                </div>
                                <div>
                                  <label className="block text-xs font-medium text-gray-500 mb-1">Formato</label>
                                  <select name="eixo_x_formato" value={config.eixo_x_formato || 'data'} onChange={handleChange} className="block w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm shadow-sm focus:border-blue-500">
                                    <option value="texto">Texto Padrão</option>
                                    <option value="data">Data (DD MMM AAAA)</option>
                                  </select>
                                </div>
                                <div>
                                  <label className="block text-xs font-medium text-gray-500 mb-1">Cor da Fonte</label>
                                  <div className="flex items-center gap-2">
                                    <input type="color" name="eixo_x_cor" value={config.eixo_x_cor || '#6b7280'} onChange={handleChange} className="h-8 w-full cursor-pointer rounded border border-gray-300" />
                                  </div>
                                </div>
                              </div>
                              <div className="mt-3 flex items-center">
                                <label className="inline-flex items-center cursor-pointer">
                                  <input type="checkbox" name="eixo_x_preencher_vazio" checked={config.eixo_x_preencher_vazio || false} onChange={(e) => setConfig(prev => ({ ...prev, eixo_x_preencher_vazio: e.target.checked }))} className="form-checkbox text-blue-600 rounded border-gray-300 focus:ring-blue-500 w-4 h-4" />
                                  <span className="ml-2 text-sm text-gray-700 font-medium">Travar Eixo X / Preencher dias vazios com zero</span>
                                </label>
                                <span className="ml-2 text-xs text-gray-500">(útil ao fixar um período no filtro)</span>
                              </div>
                            </div>
                          )}
                      
                      {['barra', 'linha', 'area', 'composed', 'grafico'].includes(config.tipo) ? (
                        <div className="md:col-span-2 mt-4 pt-4 border-t border-gray-200">
                          <div className="flex justify-between items-center mb-3">
                            <div>
                              <label className="block text-sm font-bold text-gray-800">Séries e Metas (Eixo Y Vertical)</label>
                              <p className="text-xs text-gray-500">Cada linha abaixo representa um dado a ser exibido no gráfico.</p>
                            </div>
                            <button type="button" onClick={handleAddSeries} className="text-xs bg-blue-100 text-blue-700 px-3 py-2 rounded-md hover:bg-blue-200 font-bold flex items-center transition-colors">
                              <Plus className="w-4 h-4 mr-1"/> Adicionar Dado
                            </button>
                          </div>
                          
                          <div className="space-y-2 max-h-96 overflow-y-auto pr-2 custom-scrollbar">
                            {/* Header da Tabela de Séries */}
                            {config.series && config.series.length > 0 && (
                              <div className="hidden md:grid grid-cols-12 gap-2 text-[10px] font-bold text-gray-500 uppercase tracking-wider px-2 pb-1 border-b">
                                <div className="col-span-2">Nome na Legenda</div>
                                <div className="col-span-2">Campo Alvo / Dado</div>
                                <div className="col-span-2">Cálculo / Valor</div>
                                <div className="col-span-2">Formato Gráfico</div>
                                <div className="col-span-2">Formatação Visual</div>
                                <div className="col-span-1 text-center">Cor</div>
                                <div className="col-span-1 text-center">Ação</div>
                              </div>
                            )}

                            {(config.series || []).map((serie) => (
                              <div key={serie.id} className={`grid grid-cols-1 md:grid-cols-12 gap-2 items-center p-3 md:p-1.5 rounded-lg md:rounded-md border md:border-b md:border-transparent transition-colors ${serie.is_meta ? 'bg-orange-50 border-orange-200' : 'bg-gray-50 hover:bg-gray-100 border-gray-200'}`}>
                                
                                <div className="col-span-2">
                                  <label className="block md:hidden text-xs text-gray-500 mb-1">Nome</label>
                                  <input type="text" value={serie.nome} onChange={e => updateSingleSeriesField(serie.id, 'nome', e.target.value)} className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm shadow-sm focus:border-blue-500 focus:ring-blue-500" placeholder="Nome" />
                                </div>

                                <div className="col-span-2">
                                  <label className="block md:hidden text-xs text-gray-500 mb-1">Campo</label>
                                  <select value={serie.is_meta ? 'META_FIXA' : serie.campo} onChange={e => {
                                    if (e.target.value === 'META_FIXA') {
                                      updateSeries(serie.id, { is_meta: true, campo: 'META_FIXA', operacao: 'count' });
                                    } else {
                                      updateSeries(serie.id, { is_meta: false, campo: e.target.value });
                                    }
                                  }} className={`w-full rounded-md border px-2 py-1.5 text-sm shadow-sm focus:border-blue-500 focus:ring-blue-500 font-semibold ${serie.is_meta ? 'border-orange-400 text-orange-700 bg-orange-100' : 'border-gray-300 text-gray-700'}`}>
                                    <option value={metadataFields.some(f => f.name === 'id_sequencial') ? 'id_sequencial' : 'id'}>ID (Contagem)</option>
                                    {numericFields.map(f => (<option key={f.name} value={f.name}>{f.label}</option>))}
                                    <option disabled>──────────</option>
                                    <option value="META_FIXA">✨ Inserir Meta Fixa</option>
                                  </select>
                                </div>

                                <div className="col-span-2">
                                  <label className="block md:hidden text-xs text-gray-500 mb-1">{serie.is_meta ? 'Valor da Meta' : 'Operação'}</label>
                                  {!serie.is_meta ? (
                                    <select value={serie.operacao} onChange={e => updateSingleSeriesField(serie.id, 'operacao', e.target.value)} className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm shadow-sm focus:border-blue-500 focus:ring-blue-500">
                                      <option value="sum">Somar Valores</option>
                                      <option value="count">Contar Registros</option>
                                      <option value="avg">Média dos Valores</option>
                                      <option value="cumulative_sum">Soma Cumulativa</option>
                                    </select>
                                  ) : (
                                    <input type="number" value={serie.valor_meta || ''} onChange={e => updateSingleSeriesField(serie.id, 'valor_meta', Number(e.target.value))} className="w-full rounded-md border border-orange-300 px-2 py-1.5 text-sm shadow-sm focus:border-orange-500 focus:ring-orange-500 bg-white" placeholder="Valor alvo..." />
                                  )}
                                </div>

                                <div className="col-span-2">
                                  <label className="block md:hidden text-xs text-gray-500 mb-1">Gráfico</label>
                                  <div className="flex flex-col gap-1">
                                    <select value={serie.tipo} onChange={e => updateSingleSeriesField(serie.id, 'tipo', e.target.value)} className={`w-full rounded-md border px-2 py-1.5 text-sm shadow-sm ${serie.is_meta ? 'border-orange-300 focus:border-orange-500 focus:ring-orange-500' : 'border-gray-300 focus:border-blue-500 focus:ring-blue-500'}`}>
                                      <option value="barra">Colunas</option>
                                      <option value="linha">Linha</option>
                                      <option value="area">Área Preenchida</option>
                                    </select>
                                    {serie.is_meta && (
                                      <label className="inline-flex items-center cursor-pointer">
                                        <input type="checkbox" checked={serie.meta_progressiva || false} onChange={e => updateSingleSeriesField(serie.id, 'meta_progressiva', e.target.checked)} className="form-checkbox text-orange-500 rounded w-3.5 h-3.5 border-orange-300" />
                                        <span className="ml-1.5 text-[10px] font-medium text-gray-700" title="A meta cresce gradativamente ao longo do período">Meta Crescente?</span>
                                      </label>
                                    )}
                                  </div>
                                </div>

                                <div className="col-span-2">
                                  <label className="block md:hidden text-xs text-gray-500 mb-1">Formato</label>
                                  <select value={serie.formato} onChange={e => updateSingleSeriesField(serie.id, 'formato', e.target.value)} className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm shadow-sm focus:border-blue-500 focus:ring-blue-500">
                                    <option value="numero">1.000 (Número)</option>
                                    <option value="moeda">R$ 1.000,00 (Moeda)</option>
                                    <option value="dias">10 dias (Tempo)</option>
                                  </select>
                                </div>

                                <div className="col-span-1">
                                  <label className="block md:hidden text-xs text-gray-500 mb-1">Cor</label>
                                  <input type="color" value={serie.cor || '#000000'} onChange={e => updateSingleSeriesField(serie.id, 'cor', e.target.value)} className="h-8 w-full cursor-pointer rounded border border-gray-300" title="Cor da série" />
                                </div>

                                <div className="col-span-1 flex justify-end md:justify-center">
                                  <button type="button" onClick={() => removeSeries(serie.id)} className="p-1.5 text-gray-400 hover:bg-red-100 hover:text-red-500 rounded transition-colors" title="Remover série">
                                    <X className="w-4 h-4" />
                                  </button>
                                </div>

                              </div>
                            ))}
                            {(!config.series || config.series.length === 0) && (
                              <div className="text-center text-sm text-gray-400 py-6 border-2 border-dashed border-gray-200 rounded-lg">
                                Nenhuma métrica configurada.<br/>Clique em "Adicionar Dado" acima.
                              </div>
                            )}
                          </div>
                        </div>
                      ) : (
                        <>
                        {/* COMPORTAMENTO LEGADO E SIMPLES PARA MÉTRICA */}
                        <div className="md:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">{config.tipo === 'metrica' ? 'Campo a ser calculado' : 'Eixo Y (Valor Primário)'}</label>
                          <div className="flex space-x-2">
                            <select
                              name="campo"
                              value={config.campo}
                              onChange={handleChange}
                              disabled={loadingMetadata}
                              className="block w-2/3 rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-blue-500 sm:text-sm disabled:bg-gray-100"
                            >
                              <option value={metadataFields.some(f => f.name === 'id_sequencial') ? 'id_sequencial' : 'id'}>ID (Contagem de Registros)</option>
                              {numericFields.map(f => (
                                <option key={f.name} value={f.name}>{f.label}</option>
                              ))}
                            </select>
                            <select
                              name="operacao"
                              value={config.operacao}
                              onChange={(e) => {
                                handleChange(e);
                                if (e.target.value === 'count') setConfig(prev => ({ ...prev, campo: metadataFields.some(f => f.name === 'id_sequencial') ? 'id_sequencial' : 'id' }));
                              }}
                              className="block w-1/3 rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-blue-500 sm:text-sm"
                            >
                              <option value="sum">Soma</option>
                              <option value="count">Contagem</option>
                              <option value="avg">Média</option>
                            </select>
                          </div>
                        </div>

                        {/* Eixo Y 2 Opcional (Gráficos) */}
                        {['barra', 'linha', 'area', 'composed'].includes(config.tipo) && (
                          <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">Eixo Y (Secundário / Comparação)</label>
                            <select name="campo2" value={config.campo2 || ''} onChange={handleChange} className="block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-blue-500 sm:text-sm disabled:bg-gray-100">
                              <option value="">Nenhum (Apenas 1 valor)</option>
                              {numericFields.map(f => (<option key={f.name} value={f.name}>{f.label}</option>))}
                            </select>
                          </div>
                        )}
                      </div>

                      {/* Formato de Exibição */}
                      <div className="md:col-span-2">
                        <label className="block text-sm font-medium text-gray-700">Formato de Exibição</label>
                        <div className="mt-2 flex flex-wrap gap-4">
                          <label className="inline-flex items-center">
                            <input type="radio" name="formato" value="numero" checked={config.formato === 'numero'} onChange={handleChange} className="form-radio text-blue-600" />
                            <span className="ml-2 text-sm text-gray-700">Unitário/Número (Ex: 150)</span>
                          </label>
                          <label className="inline-flex items-center">
                            <input type="radio" name="formato" value="moeda" checked={config.formato === 'moeda'} onChange={handleChange} className="form-radio text-blue-600" />
                            <span className="ml-2 text-sm text-gray-700">Moeda (Ex: R$ 1.500,00)</span>
                          </label>
                          <label className="inline-flex items-center">
                            <input type="radio" name="formato" value="dias" checked={config.formato === 'dias'} onChange={handleChange} className="form-radio text-blue-600" />
                            <span className="ml-2 text-sm text-gray-700">Dias (Ex: 5 dias)</span>
                          </label>
                        </div>
                      </div>
                      </>
                      )}
                        </>
                      )}

                      {/* --- CONFIGURAÇÕES ESPECÍFICAS PARA FILTRO --- */}
                      {config.tipo === 'filtro' && (
                        <>
                          <div>
                            <label className="block text-sm font-medium text-gray-700">Campo Alvo do Filtro</label>
                            {config.modelo === 'todos' ? (
                              <input
                                type="text"
                                name="campo"
                                value={config.campo}
                                onChange={handleChange}
                                placeholder="ex: __search__ ou data_criacao"
                                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-blue-500 sm:text-sm"
                              />
                            ) : (
                              <select
                                name="campo"
                                value={config.campo}
                                onChange={handleChange}
                                disabled={loadingMetadata}
                                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-blue-500 sm:text-sm"
                              >
                                <option value="">Selecione...</option>
                                <option value="__search__">Busca Global (Pesquisar em tudo)</option>
                                {metadataFields.map(f => (
                                  <option key={f.name} value={f.name}>{f.label}</option>
                                ))}
                              </select>
                            )}
                          </div>
                          <div>
                            <label className="block text-sm font-medium text-gray-700">Tipo de Comportamento</label>
                            <select
                              name="operacao"
                              value={config.operacao}
                              onChange={handleChange}
                              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-blue-500 sm:text-sm"
                            >
                              <option value="contains">Texto Genérico (Contém)</option>
                              <option value="date_range">Período de Data</option>
                              <option value="boolean">Caixa de Seleção (Checkbox Único)</option>
                              <option value="checkbox_list">Lista Múltipla (Tabela de Checkboxes)</option>
                              <option value="toggle">Botão de Alternância (Toggle)</option>
                            </select>
                          </div>
                        </>
                      )}
                        </>
                      )}

                    </div>
                  </div>
                  <div className="bg-gray-50 px-4 py-3 sm:flex sm:flex-row-reverse sm:px-6 rounded-b-lg">
                    <button
                      type="submit"
                      className="inline-flex w-full justify-center rounded-md bg-blue-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-blue-500 sm:ml-3 sm:w-auto"
                    >
                      <Save className="w-4 h-4 mr-2" /> Salvar Card
                    </button>
                    <button
                      type="button"
                      onClick={onClose}
                      className="mt-3 inline-flex w-full justify-center rounded-md bg-white px-3 py-2 text-sm font-semibold text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 hover:bg-gray-50 sm:mt-0 sm:w-auto"
                    >
                      Cancelar
                    </button>
                  </div>
                </form>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition.Root>
  );
};

export default CardConfigModal;
