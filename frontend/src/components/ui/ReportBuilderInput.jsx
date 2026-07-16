import React, { useState, useEffect, useMemo, Fragment, useRef } from 'react';
import { 
  Plus, Trash2, ArrowUp, ArrowDown, Settings, 
  GripVertical, Search, X, Filter, Calendar, List,
  ChevronDown, ChevronUp, Check, Info, Loader2
} from 'lucide-react';
import { Popover, Transition, Dialog } from '@headlessui/react';
import Select from 'react-select';
import api from '../../api/axiosConfig';

const OPERATORS = [
  { value: 'equals', label: 'Igual a' },
  { value: 'contains', label: 'Contém' },
  { value: 'gt', label: 'Maior que' },
  { value: 'lt', label: 'Menor que' },
  { value: 'gte', label: 'Maior ou Igual' },
  { value: 'lte', label: 'Menor ou Igual' },
  { value: 'is_true', label: 'É Verdadeiro' },
  { value: 'is_false', label: 'É Falso' },
  { value: 'neq', label: 'Diferente de' },
  { value: 'in', label: 'Está na lista (A, B, C)' },
  { value: 'today', label: 'Hoje' },
  { value: 'last_days', label: 'Últimos X dias' },
];

export const ReportBuilderInput = ({ field, value, onChange, formData }) => {
  const [config, setConfig] = useState({
    columns: value?.columns || [],
    filters: value?.filters || [],
    sort: value?.sort || []
  });
  const [availableFields, setAvailableFields] = useState([]);
  const [loadingFields, setLoadingFields] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [previewData, setPreviewData] = useState([]);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [editingColumn, setEditingColumn] = useState(null); // Índice da coluna em configuração
  const tableContainerRef = useRef(null);
  const scrollAnimationFrameRef = useRef(null);
  const scrollVelocityRef = useRef(0);
  const prevColumnsLength = useRef(config.columns?.length || 0);
  
  // O modelo selecionado no formulário principal (ex: 'pedidos')
  const selectedModel = formData?.modelo;

  useEffect(() => {
    if (selectedModel) {
      fetchModelFields(selectedModel);
    }
  }, [selectedModel]);

  useEffect(() => {
    // Atualiza o pai quando o config muda
    onChange({ target: { name: field.name, value: config } });
  }, [config]);

  useEffect(() => {
    return () => {
      if (scrollAnimationFrameRef.current) cancelAnimationFrame(scrollAnimationFrameRef.current);
    };
  }, []);

  // Efeito para rolar a tabela para a direita ao adicionar uma nova coluna
  useEffect(() => {
    const currentLength = config.columns?.length || 0;
    if (currentLength > prevColumnsLength.current && tableContainerRef.current) {
      setTimeout(() => {
        if (tableContainerRef.current) {
          tableContainerRef.current.scrollLeft = tableContainerRef.current.scrollWidth;
        }
      }, 0);
    }
    prevColumnsLength.current = currentLength;
  }, [config.columns?.length]);

  // Efeito para buscar dados reais de exemplo (Preview) conforme filtros e ordenação
  useEffect(() => {
    if (!selectedModel) return;

    const timer = setTimeout(() => {
      fetchPreviewData();
    }, 800); // Debounce para evitar requisições excessivas durante a edição

    return () => clearTimeout(timer);
  }, [config.filters, config.sort, selectedModel]);

  const fetchPreviewData = async () => {
    setLoadingPreview(true);
    try {
      const params = {
        limit: 10, // Ajustado para coincidir com o preenchimento visual
        filters: JSON.stringify(config.filters),
        sort_by: config.sort[0]?.field || 'id',
        sort_order: config.sort[0]?.direction || 'desc'
      };
      const res = await api.get(`/generic/${selectedModel}`, { params });
      setPreviewData(res.data.items || []);
    } catch (err) {
      console.error("Erro ao buscar preview de dados", err);
    } finally {
      setLoadingPreview(false);
    }
  };

  const fetchModelFields = async (modelName) => {
    setLoadingFields(true);
    try {
      const res = await api.get(`/metadata/${modelName}`);
      const mainFields = res.data.fields;

      // Definição de subcampos conhecidos para campos JSON comuns (Desramificação)
      const JSON_SUBFIELDS = {
        'itens': [
          { key: 'sku', label: 'SKU' },
          { key: 'descricao', label: 'Descrição' },
          { key: 'quantidade', label: 'Qtd' },
          { key: 'valor_unitario', label: 'V. Unit' },
          { key: 'subtotal', label: 'Subtotal' },
          { key: 'ipi_aliquota', label: 'Alíq. IPI' },
          { key: 'valor_ipi', label: 'V. IPI' },
          { key: 'total_com_ipi', label: 'Total' }
        ]
      };

      // Adiciona campos do modelo principal
      let fields = [];
      mainFields.forEach(f => {
        fields.push({ 
          value: f.name, 
          label: f.label, 
          type: f.type,
          options: f.options,
          model: 'principal' 
        });

        if (JSON_SUBFIELDS[f.name]) {
          JSON_SUBFIELDS[f.name].forEach(sub => {
            fields.push({
              value: `${f.name}:${sub.key}`,
              real_field: f.name,
              json_key: sub.key,
              label: `${f.label} > ${sub.label}`,
              type: 'json_subfield',
              model: 'principal'
            });
          });
        }
      });

      // Identifica campos que são chaves estrangeiras
      const relationships = mainFields.filter(f => f.foreign_key_model);

      // Busca metadados das tabelas relacionadas dinamicamente
      await Promise.all(relationships.map(async (rel) => {
        try {
            let prefix = rel.name;
            if (prefix.startsWith('id_')) prefix = prefix.substring(3);
            else if (prefix.endsWith('_id')) prefix = prefix.slice(0, -3);

            const relRes = await api.get(`/metadata/${rel.foreign_key_model}`);
            
            relRes.data.fields.forEach(rf => {
                fields.push({
                    value: `${prefix}.${rf.name}`,
                    label: `${rel.label} > ${rf.label}`,
                    type: rf.type,
                    options: rf.options,
                    model: prefix
                });
            });
        } catch (err) {
            console.warn(`Não foi possível carregar detalhes de ${rel.name}`);
        }
      }));

      setAvailableFields(fields);
    } catch (err) {
      console.error("Erro ao buscar campos", err);
    } finally {
      setLoadingFields(false);
    }
  };

  // --- GERENCIAMENTO DE COLUNAS ---
  const addColumn = (fieldValue) => {
    const fieldMeta = availableFields.find(f => f.value === fieldValue);
    if (!fieldMeta) return;

    setConfig(prev => ({
      ...prev,
      columns: [...(prev.columns || []), { 
        field: fieldMeta.real_field || fieldValue, 
        label: fieldMeta.label, 
        json_key: fieldMeta.json_key || '',
        type: fieldMeta.type 
      }]
    }));
  };

  const removeColumn = (index) => {
    const colToRemove = config.columns[index];
    setConfig(prev => ({
      ...prev,
      columns: prev.columns.filter((_, i) => i !== index),
      // Remove filtros e ordenação associados a esta coluna
      filters: prev.filters.filter(f => f.field !== colToRemove.field),
      sort: prev.sort.filter(s => s.field !== colToRemove.field)
    }));
  };

  const moveColumn = (dragIndex, hoverIndex) => {
    if (isNaN(dragIndex) || isNaN(hoverIndex)) return;
    const newCols = [...config.columns];
    if (dragIndex < 0 || dragIndex >= newCols.length || hoverIndex < 0 || hoverIndex >= newCols.length) return;
    const dragCol = newCols[dragIndex];
    newCols.splice(dragIndex, 1);
    newCols.splice(hoverIndex, 0, dragCol);
    setConfig(prev => ({ ...prev, columns: newCols }));
  };

  // --- ORDENAÇÃO ---
  const toggleSort = (fieldPath) => {
    const currentSort = config.sort.find(s => s.field === fieldPath);
    let newSort = config.sort.filter(s => s.field !== fieldPath);

    if (!currentSort) {
      newSort.push({ field: fieldPath, direction: 'asc' });
    } else if (currentSort.direction === 'asc') {
      newSort.push({ field: fieldPath, direction: 'desc' });
    }
    // Se era desc, remove (sem ordenação)

    setConfig(prev => ({ ...prev, sort: newSort }));
  };

  // --- FILTROS (DENTRO DA CONFIG DA COLUNA) ---
  const addColumnFilter = (fieldPath) => {
    setConfig(prev => ({
      ...prev,
      filters: [...(prev.filters || []), { field: fieldPath, operator: 'equals', value: '' }]
    }));
  };

  const removeFilterByIndex = (index) => {
    setConfig(prev => ({
      ...prev,
      filters: prev.filters.filter((_, i) => i !== index)
    }));
  };

  const updateFilterByIndex = (index, key, value) => {
    setConfig(prev => {
      const newFilters = [...prev.filters];
      newFilters[index] = { ...newFilters[index], [key]: value };
      return { ...prev, filters: newFilters };
    });
  };

  const getCellValue = (row, col) => {
    let val = row;
    const fieldPath = col.field.split('.');
    
    // Navega em relacionamentos (ex: cliente.nome_razao)
    for (const part of fieldPath) {
      val = val?.[part];
    }

    // Extração de JSON (lógica complexa para caminhos aninhados e arrays)
    if (col.json_key && val) {
      if (Array.isArray(val)) {
        // Se for array, extrai a chave de cada item e junta
        val = val.map(item => {
            let itemVal = item;
            const jsonPath = col.json_key.split('.');
            for (const part of jsonPath) {
                itemVal = itemVal?.[part];
            }
            return itemVal;
        }).filter(v => v !== undefined && v !== null).join(', ');
      } else {
        const jsonPath = col.json_key.split('.');
        let jsonVal = val;
        for (const part of jsonPath) {
          if (Array.isArray(jsonVal) && !isNaN(part)) jsonVal = jsonVal[parseInt(part)];
          else jsonVal = jsonVal?.[part];
        }
        val = jsonVal;
      }
    }

    if (val === null || val === undefined) return '-';
    if (typeof val === 'boolean') return val ? 'Sim' : 'Não';
    if (typeof val === 'object') return JSON.stringify(val).substring(0, 30) + '...';
    return String(val);
  };

  const rowsToRender = useMemo(() => {
    if (loadingPreview) return [];
    return previewData;
  }, [previewData, loadingPreview]);

  const filteredAvailableFields = useMemo(() => {
    return availableFields.filter(f => 
      f.label.toLowerCase().includes(searchTerm.toLowerCase()) ||
      f.value.toLowerCase().includes(searchTerm.toLowerCase())
    ).filter(f => !config.columns.some(c => 
      c.field === (f.real_field || f.value) && 
      (c.json_key || '') === (f.json_key || '')
    ));
  }, [availableFields, searchTerm, config.columns]);

  const startAutoScroll = () => {
    if (scrollAnimationFrameRef.current) return;

    const scroll = () => {
      if (scrollVelocityRef.current !== 0 && tableContainerRef.current) {
        tableContainerRef.current.scrollLeft += scrollVelocityRef.current;
        scrollAnimationFrameRef.current = requestAnimationFrame(scroll);
      } else {
        scrollAnimationFrameRef.current = null;
      }
    };
    scrollAnimationFrameRef.current = requestAnimationFrame(scroll);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    const container = tableContainerRef.current;
    if (!container) return;

    const threshold = 100;
    const maxSpeed = 12;
    const rect = container.getBoundingClientRect();
    
    let velocity = 0;
    if (e.clientX < rect.left + threshold) {
      // Velocidade proporcional à proximidade da borda esquerda
      const intensity = (rect.left + threshold - e.clientX) / threshold;
      velocity = -maxSpeed * Math.min(intensity, 1);
    } else if (e.clientX > rect.right - threshold) {
      // Velocidade proporcional à proximidade da borda direita
      const intensity = (e.clientX - (rect.right - threshold)) / threshold;
      velocity = maxSpeed * Math.min(intensity, 1);
    }

    scrollVelocityRef.current = velocity;
    if (velocity !== 0) {
      startAutoScroll();
    }
  };

  const stopAutoScroll = () => {
    scrollVelocityRef.current = 0;
  };

  if (!selectedModel) {
    return <div className="text-gray-500 italic p-4 border rounded bg-gray-50">Selecione uma tabela principal na aba Geral primeiro!</div>;
  }

  return (
    <div className="flex flex-col space-y-4">
      <div 
        ref={tableContainerRef} 
        className="overflow-auto border rounded-lg bg-white shadow-sm h-[500px] relative"
        onDragOver={handleDragOver}
        onDragLeave={stopAutoScroll}
        onDrop={(e) => {
          e.preventDefault();
          e.stopPropagation();
          stopAutoScroll();
        }}
      >
        <table className="min-w-full min-h-full divide-y divide-gray-200" style={{ tableLayout: 'fixed' }}>
          <thead className="bg-gray-50">
            <tr>
              {config.columns.map((col, idx) => {
                const sort = config.sort.find(s => s.field === col.field);
                const hasFilter = config.filters.some(f => f.field === col.field);
                
                return (
                  <th 
                    key={idx}
                    draggable
                    onDragStart={(e) => e.dataTransfer.setData('colIndex', idx)}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      const fromIdx = e.dataTransfer.getData('colIndex');
                      moveColumn(parseInt(fromIdx), idx);
                    }}
                    className="group px-4 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider border-r last:border-r-0 relative cursor-move hover:bg-gray-100 transition-colors"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1 truncate">
                        <GripVertical size={12} className="text-gray-300 group-hover:text-gray-400" />
                        <span title={col.field}>{col.label}</span>
                      </div>
                      
                      <div className="flex items-center gap-1">
                        <button 
                          type="button" 
                          onClick={() => toggleSort(col.field)}
                          className={`p-1 rounded hover:bg-gray-200 ${sort ? 'text-blue-600' : 'text-gray-300'}`}
                        >
                          {sort?.direction === 'desc' ? <ArrowDown size={14} /> : <ArrowUp size={14} className={!sort ? 'opacity-50' : ''} />}
                        </button>
                        
                        <button 
                          type="button"
                          onClick={() => setEditingColumn(idx)}
                          className={`p-1 rounded hover:bg-gray-200 ${hasFilter || col.json_key ? 'text-orange-500' : 'text-gray-400'}`}
                        >
                          <Settings size={14} />
                        </button>

                        <button 
                          type="button"
                          onClick={() => removeColumn(idx)}
                          className="p-1 rounded hover:bg-red-100 text-gray-300 hover:text-red-500"
                        >
                          <X size={14} />
                        </button>
                      </div>
                    </div>
                  </th>
                );
              })}
              
              <th className="px-2 py-2 w-10">
                <Popover className="relative">
                  <Popover.Button className="p-2 bg-blue-600 text-white rounded-full hover:bg-blue-700 shadow-md focus:outline-none">
                    <Plus size={18} />
                  </Popover.Button>

                  <Transition
                    as={Fragment}
                    enter="transition ease-out duration-200"
                    enterFrom="opacity-0 translate-y-1"
                    enterTo="opacity-100 translate-y-0"
                    leave="transition ease-in duration-150"
                    leaveFrom="opacity-100 translate-y-0"
                    leaveTo="opacity-0 translate-y-1"
                  >
                    <Popover.Panel className="absolute right-0 z-50 mt-3 w-72 transform px-4 sm:px-0">
                      <div className="overflow-hidden rounded-lg shadow-lg ring-1 ring-black ring-opacity-5 bg-white">
                        <div className="p-3 border-b bg-gray-50">
                          <div className="relative">
                            <Search className="absolute left-2 top-2.5 text-gray-400" size={14} />
                            <input 
                              type="text"
                              placeholder="Pesquisar campos..."
                              className="w-full pl-8 pr-3 py-1.5 text-sm border rounded-md focus:ring-2 focus:ring-blue-500 outline-none"
                              value={searchTerm}
                              onChange={(e) => setSearchTerm(e.target.value)}
                              autoFocus
                            />
                          </div>
                        </div>
                        <div className="max-h-60 overflow-y-auto p-1">
                          {filteredAvailableFields.map(f => (
                            <button
                              key={f.value}
                              type="button"
                              onClick={() => { addColumn(f.value); setSearchTerm(''); }}
                              className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-blue-50 rounded transition-colors flex flex-col"
                            >
                              <span className="font-medium">{f.label}</span>
                              <span className="text-[10px] text-gray-400 font-mono">{f.value}</span>
                            </button>
                          ))}
                          {filteredAvailableFields.length === 0 && (
                            <div className="p-4 text-center text-gray-400 text-xs italic">Nenhum campo encontrado</div>
                          )}
                        </div>
                      </div>
                    </Popover.Panel>
                  </Transition>
                </Popover>
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-100">
            {loadingPreview ? (
              <tr className="h-px">
                <td colSpan={config.columns.length + 1} className="px-4 text-center">
                  <div className="flex flex-col items-center gap-2 text-gray-400">
                    <Loader2 className="animate-spin" size={24} />
                    <span className="text-xs">Carregando dados reais...</span>
                  </div>
                </td>
              </tr>
            ) : rowsToRender.length > 0 ? (
              rowsToRender.map((row, rIdx) => (
                <tr key={rIdx} className="hover:bg-gray-50 transition-colors h-px">
                  {config.columns.map((col, cIdx) => (
                    <td key={cIdx} className="px-4 py-2 text-xs text-gray-600 border-r last:border-r-0 truncate max-w-[200px]">
                      {getCellValue(row, col)}
                    </td>
                  ))}
                  <td className="bg-gray-50/30"></td>
                </tr>
              ))
            ) : (
              <tr className="h-px">
                <td colSpan={config.columns.length + 1} className="px-4 text-center text-gray-400 italic text-xs">
                  Nenhum dado encontrado com os filtros atuais.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Modal de Configuração da Coluna */}
      <Transition show={editingColumn !== null} as={Fragment}>
        <Dialog as="div" className="relative z-50" onClose={() => setEditingColumn(null)}>
          <Transition.Child as={Fragment} enter="ease-out duration-300" enterFrom="opacity-0" enterTo="opacity-100" leave="ease-in duration-200" leaveFrom="opacity-100" leaveTo="opacity-0">
            <div className="fixed inset-0 bg-black bg-opacity-25 backdrop-blur-sm" />
          </Transition.Child>

          <div className="fixed inset-0 overflow-y-auto">
            <div className="flex min-h-full items-center justify-center p-4">
              <Transition.Child as={Fragment} enter="ease-out duration-300" enterFrom="opacity-0 scale-95" enterTo="opacity-100 scale-100" leave="ease-in duration-200" leaveFrom="opacity-100 scale-100" leaveTo="opacity-0 scale-95">
                <Dialog.Panel className="w-full max-w-md transform overflow-hidden rounded-2xl bg-white p-6 text-left align-middle shadow-xl transition-all">
                  <Dialog.Title as="h3" className="text-lg font-bold leading-6 text-gray-900 flex items-center gap-2 border-b pb-3 mb-4">
                    <Settings className="text-blue-600" size={20} />
                    Configurar Coluna: {config.columns[editingColumn]?.label}
                  </Dialog.Title>

                  {editingColumn !== null && (
                    <div className="space-y-5">
                      <div>
                        <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Título Personalizado</label>
                        <input 
                          type="text"
                          className="w-full px-3 py-2 border rounded-md text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                          value={config.columns[editingColumn].label}
                          onChange={(e) => {
                            const newCols = [...config.columns];
                            newCols[editingColumn].label = e.target.value;
                            setConfig(prev => ({ ...prev, columns: newCols }));
                          }}
                        />
                      </div>

                      {(config.columns[editingColumn].type === 'json' || config.columns[editingColumn].field.includes('itens') || config.columns[editingColumn].field.includes('regras')) && (
                        <div className="bg-blue-50 p-3 rounded-lg border border-blue-100">
                          <label className="block text-xs font-bold text-blue-700 uppercase mb-1 flex items-center gap-1">
                            Extração JSON <span className="text-[10px] lowercase font-normal">(Caminho do objeto)</span>
                          </label>
                          <input 
                            type="text"
                            placeholder="Ex: rules.0.valor ou total_com_ipi"
                            className="w-full px-3 py-2 border border-blue-200 rounded-md text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                            value={config.columns[editingColumn].json_key || ''}
                            onChange={(e) => {
                              const newCols = [...config.columns];
                              newCols[editingColumn].json_key = e.target.value;
                              setConfig(prev => ({ ...prev, columns: newCols }));
                            }}
                          />
                        </div>
                      )}

                      <div className="border-t pt-4">
                        <div className="flex justify-between items-center mb-3">
                          <label className="block text-xs font-bold text-gray-500 uppercase flex items-center gap-1">
                            <Filter size={12} /> Filtros da Coluna
                          </label>
                          <button 
                            type="button"
                            onClick={() => addColumnFilter(config.columns[editingColumn].field)}
                            className="text-xs text-blue-600 hover:text-blue-800 font-bold flex items-center gap-1"
                          >
                            <Plus size={12} /> Adicionar
                          </button>
                        </div>
                        
                        <div className="space-y-4">
                          {config.filters.map((filter, fIdx) => {
                            if (filter.field !== config.columns[editingColumn].field) return null;
                            
                            const fieldMeta = availableFields.find(f => f.value === filter.field);
                            
                            return (
                              <div key={fIdx} className="p-3 bg-gray-50 rounded-lg border border-gray-200 space-y-3">
                                <div className="flex gap-2">
                                  <select 
                                    className="flex-1 text-sm border rounded-md p-2 outline-none focus:ring-2 focus:ring-blue-500"
                                    value={filter.operator}
                                    onChange={(e) => updateFilterByIndex(fIdx, 'operator', e.target.value)}
                                  >
                                    {OPERATORS.map(op => <option key={op.value} value={op.value}>{op.label}</option>)}
                                  </select>

                                  <button 
                                    type="button"
                                    onClick={() => removeFilterByIndex(fIdx)}
                                    className="p-2 text-red-500 hover:bg-red-50 rounded"
                                    title="Remover filtro"
                                  >
                                    <Trash2 size={18} />
                                  </button>
                                </div>

                                {!['is_true', 'is_false', 'today'].includes(filter.operator) && (
                                  <div>
                                    {filter.operator === 'last_days' ? (
                                      <input 
                                        type="number" 
                                        placeholder="Quantidade de dias..." 
                                        className="w-full px-3 py-2 border rounded-md text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                                        value={filter.value || ''}
                                        onChange={(e) => updateFilterByIndex(fIdx, 'value', e.target.value)}
                                      />
                                    ) : fieldMeta?.type === 'date' || fieldMeta?.type === 'datetime' ? (
                                      <div className="relative">
                                        <Calendar className="absolute right-3 top-2.5 text-gray-400" size={16} />
                                        <input 
                                          type="date" 
                                          className="w-full px-3 py-2 border rounded-md text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                                          value={filter.value || ''}
                                          onChange={(e) => updateFilterByIndex(fIdx, 'value', e.target.value)}
                                        />
                                      </div>
                                    ) : fieldMeta?.options ? (
                                      <Select
                                        isMulti
                                        closeMenuOnSelect={false}
                                        options={fieldMeta.options}
                                        value={filter.value 
                                          ? String(filter.value).split(',').map(v => 
                                              (fieldMeta.options || []).find(o => String(o.value) === v.trim()) || { value: v.trim(), label: v.trim() }
                                            ) 
                                          : []
                                        }
                                        onChange={(selected) => {
                                          const vals = selected ? selected.map(o => o.value) : [];
                                          updateFilterByIndex(fIdx, 'value', vals.join(','));
                                        }}
                                        placeholder="Selecionar..."
                                        className="text-sm"
                                        menuPortalTarget={document.body}
                                        styles={{ menuPortal: base => ({ ...base, zIndex: 9999 }) }}
                                      />
                                    ) : (
                                      <input 
                                        type="text" 
                                        placeholder="Valor do filtro..." 
                                        className="w-full px-3 py-2 border rounded-md text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                                        value={filter.value || ''}
                                        onChange={(e) => updateFilterByIndex(fIdx, 'value', e.target.value)}
                                      />
                                    )}
                                  </div>
                                )}
                              </div>
                            );
                          })}
                          
                          {config.filters.filter(f => f.field === config.columns[editingColumn].field).length === 0 && (
                            <div className="text-center py-4 text-gray-400 text-xs italic border-2 border-dashed rounded-lg">
                              Nenhum filtro aplicado a esta coluna.
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  )}

                  <div className="mt-8 flex justify-end">
                    <button
                      type="button"
                      className="inline-flex justify-center rounded-md border border-transparent bg-blue-100 px-4 py-2 text-sm font-medium text-blue-900 hover:bg-blue-200 focus:outline-none"
                      onClick={() => setEditingColumn(null)}
                    >
                      Concluído
                    </button>
                  </div>
                </Dialog.Panel>
              </Transition.Child>
            </div>
          </div>
        </Dialog>
      </Transition>
    </div>
  );
};