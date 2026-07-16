import React, { useState, useEffect, Fragment, useRef } from 'react';
import { Rnd } from 'react-rnd';
import { Settings, Save, Plus, X, BarChart2, Calculator, Table as TableIcon, Filter, Type, Calendar, GripVertical, Search, ArrowUp, ArrowDown } from 'lucide-react';
import { Popover, Transition } from '@headlessui/react';
import DatePicker, { registerLocale } from "react-datepicker";
import "react-datepicker/dist/react-datepicker.css";
import ptBR from 'date-fns/locale/pt-BR';
import api from '../api/axiosConfig';
import axios from 'axios';
import { useAuth } from '../contexts/AuthContext';
import CardConfigModal from '../components/dashboard/CardConfigModal';
import { toast } from 'react-toastify';

// (Seu componente DynamicCard que criamos na resposta anterior, com suporte aos gráficos do Recharts)
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell, CartesianGrid, AreaChart, Area, ComposedChart, ReferenceLine } from 'recharts';

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8'];

registerLocale('pt-BR', ptBR);

const formatLabel = (key) => {
  if (!key) return '';
  return key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
};

// Renderizador Customizado do Eixo X para Datas em 3 linhas
const CustomXAxisTick = ({ x, y, payload }) => {
  const val = payload.value;
  if (typeof val === 'string') {
    // Formato de Data ISO YYYY-MM-DD
    const isIsoDate = /^\d{4}-\d{2}-\d{2}/.test(val);
    if (isIsoDate) {
      const [year, month, day] = val.split('T')[0].split('-');
      const dateObj = new Date(year, parseInt(month) - 1, day);
      const dayStr = String(dateObj.getDate()).padStart(2, '0');
      const monthStr = dateObj.toLocaleString('pt-BR', { month: 'short' }).replace('.', '');
      const yearStr = dateObj.getFullYear();

      return (
        <g transform={`translate(${x},${y})`}>
          <text x={0} y={12} textAnchor="middle" fill="#4b5563" fontSize={11} fontWeight="bold">{dayStr}</text>
          <text x={0} y={24} textAnchor="middle" fill="#6b7280" fontSize={10} style={{ textTransform: 'capitalize' }}>{monthStr}</text>
          <text x={0} y={36} textAnchor="middle" fill="#9ca3af" fontSize={9}>{yearStr}</text>
        </g>
      );
    }
  }
  return (
    <g transform={`translate(${x},${y})`}>
      <text x={0} y={14} textAnchor="middle" fill="#6b7280" fontSize={11}>
        {typeof val === 'string' && val.length > 15 ? val.substring(0, 15) + '...' : val}
      </text>
    </g>
  );
};

const DynamicCard = ({ config, globalFilters, onFilterChange, isEditing, onUpdateConfig, selectedEmpresas = ['current'], empresasTokens = {}, outrasEmpresas = [], onRefreshToken }) => {
  const [data, setData] = useState(null);
  const [filterOptions, setFilterOptions] = useState(config.opcoes || []);
  const [dateInputText, setDateInputText] = useState(undefined);
  const [metadata, setMetadata] = useState(null);
  const [addColumnSearch, setAddColumnSearch] = useState("");
  const tableContainerRef = useRef(null);
  const prevColumnsLength = useRef(0);

  useEffect(() => {
    if (config.tipo === 'tabela' && config.modelo) {
      api.get(`/metadata/${config.modelo}`).then(res => {
        setMetadata(res.data);
      }).catch(err => console.error(err));
    }
  }, [config.tipo, config.modelo]);

  useEffect(() => {
    if (config.tipo === 'filtro' && config.operacao === 'checkbox_list') {
      if (config.opcoes && config.opcoes.length > 0) {
        setFilterOptions(config.opcoes);
      } else if (config.modelo && config.modelo !== 'todos' && config.campo) {
        const fetchOptions = async () => {
          try {
            const getBaseUrl = () => {
              const base = api.defaults.baseURL || '';
              if (base.startsWith('http')) return base;
              return `${window.location.origin}${base.startsWith('/') ? '' : '/'}${base}`;
            };
            const baseUrl = getBaseUrl();
            let allOptionsMap = new Map();

            for (const empId of selectedEmpresas) {
              try {
                let res;
                if (empId === 'current') {
                  res = await api.get(`/generic/${config.modelo}/distinct/${config.campo}`);
                } else {
                  let token = empresasTokens[empId];
                  if (!token) {
                    const emp = outrasEmpresas.find(e => e.id === empId);
                    if (emp?.token) token = emp.token;
                  }
                  if (token) {
                    res = await axios.get(`${baseUrl}/generic/${config.modelo}/distinct/${config.campo}`, {
                      headers: { Authorization: `Bearer ${token}` }
                    });
                  }
                }
                
                if (res && res.data) {
                  const validOptions = res.data.filter(v => v !== null && v !== '');
                  validOptions.forEach(opt => {
                    if (typeof opt === 'object') {
                      const label = String(opt.label).trim();
                      if (allOptionsMap.has(label)) {
                        const existing = allOptionsMap.get(label);
                        const existingVals = String(existing.value).split(',');
                        if (!existingVals.includes(String(opt.value))) {
                          existing.value = existing.value + ',' + String(opt.value);
                        }
                      } else {
                        allOptionsMap.set(label, { label: label, value: String(opt.value) });
                      }
                    } else {
                      const strVal = String(opt).trim();
                      allOptionsMap.set(strVal, { label: strVal, value: strVal });
                    }
                  });
                }
              } catch (e) {
                console.error(`Erro ao buscar opções da empresa ${empId}:`, e);
              }
            }
            
            setFilterOptions(Array.from(allOptionsMap.values()));
          } catch (err) {
            console.error(err);
          }
        };
        fetchOptions();
      }
    }
  }, [config.tipo, config.operacao, config.opcoes, config.modelo, config.campo, selectedEmpresas, empresasTokens, outrasEmpresas]);

  // Efeito para rolar automaticamente para a direita ao adicionar novas colunas
  useEffect(() => {
    if (config.tipo === 'tabela' && tableContainerRef.current) {
      const currentLen = (config.colunas && config.colunas.length) || 0;
      if (currentLen > prevColumnsLength.current) {
        setTimeout(() => {
          if (tableContainerRef.current) {
            tableContainerRef.current.scrollTo({
              left: tableContainerRef.current.scrollWidth,
              behavior: 'smooth'
            });
          }
        }, 100);
      }
      prevColumnsLength.current = currentLen;
    }
  }, [config.colunas, config.tipo]);

  useEffect(() => {
    if (!config || !config.modelo) return;
    if (config.tipo === 'filtro' || config.tipo === 'texto') return; // Filtros e textos não buscam dados via API desta forma

    // Filtros globais (apenas os que combinam com o modelo do card)
    let mergedFilters = [];

    if (globalFilters) {
      Object.values(globalFilters).forEach(gf => {
        if ((!gf.modelo || gf.modelo === 'todos' || gf.modelo === config.modelo || gf.field === '__search__') && gf.value !== undefined && gf.value !== '') {
          mergedFilters.push({ field: gf.field, operator: gf.operator, value: gf.value });
        }
      });
    }

    if (config.tipo === 'tabela') {
      mergedFilters.push({ field: '__sort__', operator: config.sort_order || 'desc', value: config.sort_by || 'id' });
    }

    const fetchDataForCompanies = async () => {
      try {
        let allData = [];
        
        // Determina a URL base absoluta para evitar erros com caminhos relativos
        const getBaseUrl = () => {
          const base = api.defaults.baseURL || '';
          if (base.startsWith('http')) return base;
          return `${window.location.origin}${base.startsWith('/') ? '' : '/'}${base}`;
        };
        const baseUrl = getBaseUrl();

        for (const empId of selectedEmpresas) {
          try {
            if (empId === 'current') {
              const res = await api.post('/dashboard/custom/data', { ...config, filtros: mergedFilters });
              const processedData = Array.isArray(res.data) ? res.data.map(item => ({...item, _empresa: 'Atual'})) : res.data;

              if (config.tipo === 'metrica') {
                allData.push(processedData);
              } else {
                allData = allData.concat(processedData);
              }
            } else {
              let token = empresasTokens[empId];
              
              // Se não tem token no estado, tenta pegar o que veio do banco (outrasEmpresas)
              if (!token) {
                const emp = outrasEmpresas.find(e => e.id === empId);
                if (emp?.token) token = emp.token;
              }

              if (token) {
                try {
                  const res = await axios.post(`${baseUrl}/dashboard/custom/data`, { ...config, filtros: mergedFilters }, {
                    headers: { Authorization: `Bearer ${token}` }
                  });
                  
                  const empName = outrasEmpresas.find(e => e.id === empId)?.nome || `Empresa ${empId}`;
                  const processedData = Array.isArray(res.data) ? res.data.map(item => ({...item, _empresa: empName})) : res.data;

                  if (config.tipo === 'metrica') {
                    allData.push(processedData);
                  } else {
                    allData = allData.concat(processedData);
                  }
                } catch (reqErr) {
                  // Se der 401 (Unauthorized), o token provavelmente expirou
                  if (reqErr.response?.status === 401 && typeof onRefreshToken === 'function') {
                    console.log(`Token expirado para empresa ${empId}, tentando renovar...`);
                    const newToken = await onRefreshToken(empId);
                    if (newToken) {
                      try {
                        const retryRes = await axios.post(`${baseUrl}/dashboard/custom/data`, { ...config, filtros: mergedFilters }, {
                          headers: { Authorization: `Bearer ${newToken}` }
                        });
                        const empName = outrasEmpresas.find(e => e.id === empId)?.nome || `Empresa ${empId}`;
                        const processedData = Array.isArray(retryRes.data) ? retryRes.data.map(item => ({...item, _empresa: empName})) : retryRes.data;
                        
                        if (config.tipo === 'metrica') {
                          allData.push(processedData);
                        } else {
                          allData = allData.concat(processedData);
                        }
                        continue; // Retry com sucesso, prossegue pro próximo empId
                      } catch (retryErr) {
                        console.error(`Falha no retry para a empresa ${empId}`, retryErr);
                        throw retryErr;
                      }
                    }
                  }
                  throw reqErr;
                }
              }
            }
          } catch (itemErr) {
            console.error(`Erro ao buscar dados da empresa ${empId}:`, itemErr);
            // Continua para as próximas empresas mesmo se uma falhar
          }
        }
        
        if (allData.length === 0) {
          setData(config.tipo === 'metrica' ? { value: 0 } : []);
          return;
        }

        if (config.tipo === 'metrica') {
          const totalVal = allData.reduce((acc, curr) => acc + (curr.value || 0), 0);
          setData({ value: totalVal });
        } else if (config.tipo === 'tabela') {
          setData(allData);
        } else {
          const aggregated = {};
          allData.forEach(item => {
            if (!item || typeof item !== 'object') return;
            const nameKey = item.name || 'Sem Categoria';
            if (!aggregated[nameKey]) aggregated[nameKey] = { ...item, name: nameKey };
            else {
              Object.keys(item).forEach(k => {
                if (k !== 'name' && typeof item[k] === 'number') {
                  aggregated[nameKey][k] = (aggregated[nameKey][k] || 0) + item[k];
                }
              });
            }
          });
          setData(Object.values(aggregated));
        }
      } catch (err) {
        console.error("Erro fatal no fetchDataForCompanies:", err);
        setData(config.tipo === 'metrica' ? { value: 0 } : []);
      }
    };
    
    fetchDataForCompanies();
  }, [config, globalFilters, selectedEmpresas, empresasTokens]);

  // Processa dados dos gráficos inserindo a "Meta Progressiva" se necessário
  const chartData = React.useMemo(() => {
    if (!data || !Array.isArray(data)) return data;
    let processed = [...data];
    
    let accumulations = {};
    const seriesList = config.series && config.series.length > 0 ? config.series : null;
    
    if (seriesList) {
      processed = processed.map((item, index) => {
        let newItem = { ...item };
        seriesList.forEach(s => {
          if (s.is_meta) {
            const metaVal = Number(s.valor_meta) || 0;
            if (s.meta_progressiva) {
              const totalPoints = processed.length;
              newItem[s.id] = totalPoints > 1 ? (metaVal / (totalPoints - 1)) * index : metaVal;
            } else {
              newItem[s.id] = metaVal;
            }
          } else if (s.operacao === 'cumulative_sum') {
            accumulations[s.id] = (accumulations[s.id] || 0) + (Number(item[s.id]) || 0);
            newItem[s.id] = accumulations[s.id];
          }
        });
        return newItem;
      });
    } else {
      // Fallback legado para o Acumular Valores Antigo
      if (config.acumular_valores) {
        let sumY1 = 0; let sumY2 = 0;
        processed = processed.map((item) => {
          sumY1 += Number(item.value) || 0;
          const newItem = { ...item, value: sumY1 };
          if (item.value2 !== undefined) { sumY2 += Number(item.value2) || 0; newItem.value2 = sumY2; }
          return newItem;
        });
      }
      if (config.valor_meta) {
        const metaTarget = Number(config.valor_meta);
        processed = processed.map((item, index) => ({
          ...item,
          metaLine: config.meta_progressiva ? (processed.length > 1 ? (metaTarget / (processed.length - 1)) * index : metaTarget) : metaTarget
        }));
      }
    }
    
    return processed;
  }, [data, config]);

  // Nomes dos campos para tooltip/legendas
  const nameY1 = formatLabel(config.campo) || 'Valor';
  const nameY2 = config.campo2 ? formatLabel(config.campo2) : '';


  if (config.tipo === 'filtro') {
    const currentVal = globalFilters[config.i]?.value || '';
    return (
      <div className="flex flex-col h-full p-4 overflow-visible">
        {config.operacao !== 'boolean' && config.operacao !== 'toggle' && (
          <label className="text-sm font-bold text-gray-700 mb-2 shrink-0 truncate" title={config.titulo}>{config.titulo}</label>
        )}
        {config.operacao === 'boolean' ? (
          <div className="flex-1 flex items-center">
            <label className="flex items-center cursor-pointer group">
              <input
                type="checkbox"
                checked={currentVal === true || currentVal === 'true'}
                onChange={(e) => onFilterChange(config.i, { modelo: config.modelo, field: config.campo, operator: 'equals', value: e.target.checked ? true : '' })}
                className="h-5 w-5 text-blue-600 focus:ring-blue-500 border-gray-300 rounded cursor-pointer"
              />
              <span className="ml-3 text-sm font-bold text-gray-700 group-hover:text-blue-600 transition-colors select-none">{config.titulo}</span>
            </label>
          </div>
        ) : config.operacao === 'toggle' ? (
          <div className="flex-1 flex items-center justify-between w-full">
            <span className="text-sm font-bold text-gray-700 select-none truncate pr-2 group-hover:text-blue-600 transition-colors" title={config.titulo}>{config.titulo}</span>
            <label className="flex items-center cursor-pointer group shrink-0">
              <div className="relative">
                <input
                  type="checkbox"
                  className="sr-only"
                  checked={currentVal === true || currentVal === 'true'}
                  onChange={(e) => onFilterChange(config.i, { modelo: config.modelo, field: config.campo, operator: 'equals', value: e.target.checked ? true : false })}
                />
                <div className={`block w-10 h-6 rounded-full transition-colors ${currentVal === true || currentVal === 'true' ? 'bg-blue-500' : 'bg-gray-300'}`}></div>
                <div className={`absolute left-1 top-1 bg-white w-4 h-4 rounded-full transition-transform ${currentVal === true || currentVal === 'true' ? 'transform translate-x-4' : ''}`}></div>
              </div>
            </label>
          </div>
        ) : config.operacao === 'checkbox_list' ? (
          <div className="flex-1 overflow-auto custom-scrollbar border border-gray-200 rounded-md p-2 bg-white mx-[-18px] mb-[-18px]">
            {filterOptions.length === 0 ? (
              <span className="text-xs text-gray-400 p-1">Carregando opções...</span>
            ) : (
              filterOptions.map((opt, idx) => {
                const currentValues = String(currentVal).split(',').filter(Boolean);
                const optVals = String(opt.value).split(',');
                const isChecked = optVals.some(v => currentValues.includes(v));
                return (
                  <label key={idx} className="flex items-start p-1 hover:bg-gray-50 cursor-pointer rounded border-b border-gray-50 last:border-0 group">
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={(e) => {
                        let newValues = [...currentValues];
                        if (e.target.checked) {
                          optVals.forEach(v => {
                            if (!newValues.includes(v)) newValues.push(v);
                          });
                        } else {
                          newValues = newValues.filter(v => !optVals.includes(v));
                        }
                        onFilterChange(config.i, { modelo: config.modelo, field: config.campo, operator: 'equals', value: newValues.join(',') });
                      }}
                      className="mt-0.5 h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded cursor-pointer shrink-0"
                    />
                    <span className="ml-3 text-sm text-gray-700 transition-colors break-words w-full leading-tight">{opt.label}</span>
                  </label>
                );
              })
            )}
          </div>
        ) : config.operacao === 'date_range' ? (
          <div className="flex-1 flex flex-col justify-center bg-white border border-gray-300 rounded-md">
            <Popover className="relative h-full flex items-center w-full">
              <div className="h-full flex items-center px-2 text-sm text-gray-700 font-medium w-full">
                <Popover.Button className="focus:outline-none mr-1.5 p-1 hover:bg-gray-100 rounded-md transition-colors group shrink-0">
                  <Calendar size={16} className="text-gray-400 group-hover:text-blue-600" />
                </Popover.Button>
                {(() => {
                  const vals = (currentVal || '').split(',');
                  const start = vals[0] || '';
                  const end = vals[1] || '';
                  const displayValue = dateInputText !== undefined ? dateInputText : ((!start && !end) ? "" : `${start ? start.split('-').reverse().join('/') : '...'} - ${end ? end.split('-').reverse().join('/') : '...'}`);
                  return (
                    <input
                      type="text"
                      className="bg-transparent border-none focus:ring-0 p-0 text-sm font-medium w-full outline-none"
                      placeholder="Selecione o período"
                      value={displayValue}
                      onChange={(e) => {
                        const val = e.target.value;
                        setDateInputText(val);
                        const parts = val.split(' - ');
                        if (parts.length === 2) {
                          const dateRegex = /^(\d{2})\/(\d{2})\/(\d{4})$/;
                          const m1 = parts[0].trim().match(dateRegex);
                          const m2 = parts[1].trim().match(dateRegex);
                          if (m1 && m2) {
                            const startStr = `${m1[3]}-${m1[2]}-${m1[1]}`;
                            const endStr = `${m2[3]}-${m2[2]}-${m2[1]}`;
                            onFilterChange(config.i, { modelo: config.modelo, field: config.campo, operator: 'date_range', value: `${startStr},${endStr}` });
                          }
                        } else if (!val) {
                          onFilterChange(config.i, { modelo: config.modelo, field: config.campo, operator: 'date_range', value: '' });
                        }
                      }}
                      onBlur={() => setDateInputText(undefined)}
                      onKeyDown={(e) => e.key === 'Enter' && e.target.blur()}
                    />
                  );
                })()}
              </div>
              <Transition as={Fragment} enter="transition ease-out duration-200" enterFrom="opacity-0 translate-y-1" enterTo="opacity-100 translate-y-0" leave="transition ease-in duration-150" leaveFrom="opacity-100 translate-y-0" leaveTo="opacity-0 translate-y-1">
                <Popover.Panel className="absolute left-0 top-full z-50 mt-2 bg-white rounded-lg shadow-xl ring-1 ring-black ring-opacity-5 p-4">
                  {({ close }) => {
                    const vals = (currentVal || '').split(',');
                    const start = vals[0] ? new Date(vals[0] + 'T00:00:00') : null;
                    const end = vals[1] ? new Date(vals[1] + 'T00:00:00') : null;
                    return (
                      <div className="space-y-4">
                        <div className="flex justify-center border-b border-gray-100 pb-2">
                          <DatePicker
                            selected={start}
                            onChange={(update) => {
                              const [newStart, newEnd] = update;
                              const format = (d) => {
                                if (!d) return '';
                                const year = d.getFullYear();
                                const month = String(d.getMonth() + 1).padStart(2, '0');
                                const day = String(d.getDate()).padStart(2, '0');
                                return `${year}-${month}-${day}`;
                              };
                              const startStr = format(newStart);
                              const endStr = format(newEnd);
                              const newVal = startStr || endStr ? `${startStr},${endStr}` : '';
                              onFilterChange(config.i, { modelo: config.modelo, field: config.campo, operator: 'date_range', value: newVal });
                              setDateInputText(undefined);
                            }}
                            startDate={start}
                            endDate={end}
                            selectsRange
                            inline
                            locale="pt-BR"
                          />
                        </div>
                        <div className="flex justify-between">
                          <button
                            onClick={() => {
                              onFilterChange(config.i, { modelo: config.modelo, field: config.campo, operator: 'date_range', value: '' });
                              close();
                            }}
                            className="text-xs text-red-600 hover:text-red-800 font-bold uppercase"
                          >
                            Limpar
                          </button>
                          <button
                            onClick={() => close()}
                            className="text-xs text-blue-600 hover:text-blue-800 font-bold uppercase"
                          >
                            Fechar
                          </button>
                        </div>
                      </div>
                    );
                  }}
                </Popover.Panel>
              </Transition>
            </Popover>
          </div>
        ) : (
          <div className="flex-1">
            <input
              type="text"
              value={currentVal}
              placeholder={config.campo === '__search__' ? "Busca Global..." : "Buscar..."}
              className="w-full border border-gray-300 rounded-md p-2 text-sm focus:ring-blue-500 focus:border-blue-500 outline-none"
              onChange={(e) => onFilterChange(config.i, { modelo: config.modelo, field: config.campo, operator: 'contains', value: e.target.value })}
            />
          </div>
        )}
      </div>
    );
  }

  if (config.tipo === 'texto') {
    return (
      <div className="flex flex-col h-full p-4 overflow-hidden">
        {config.titulo && <h3 className="text-gray-700 text-sm font-bold mb-2 shrink-0">{config.titulo}</h3>}
        <div className="flex-1 overflow-auto text-gray-600 text-sm whitespace-pre-wrap custom-scrollbar">
          {config.texto_conteudo || 'Nenhum texto configurado. Clique na engrenagem para editar.'}
        </div>
      </div>
    );
  }

  if (!data) return <div className="flex h-full items-center justify-center text-gray-400">
    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
  </div>;

  const formatValue = (val, fmtType = config.formato) => {
    if (fmtType === 'moeda') return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(val);
    if (fmtType === 'dias') return `${val} dias`;
    return new Intl.NumberFormat('pt-BR').format(val);
  };

  if (config.tipo === 'metrica') {
    return (
      <div className="flex flex-col items-center justify-center h-full p-4">
        <h3 className="text-gray-500 text-sm font-medium uppercase tracking-wider">{config.titulo}</h3>
        <p className="text-3xl font-bold text-gray-800 mt-2">{formatValue(data.value)}</p>
      </div>
    );
  }

  if (config.tipo === 'pizza') {
    return (
      <div className="flex flex-col h-full p-4">
        <h3 className="text-gray-700 text-sm font-bold mb-2">{config.titulo}</h3>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={60} fill="#8884d8" label>
              {data.map((entry, index) => <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />)}
            </Pie>
            <Tooltip formatter={(value) => formatValue(value)} />
          </PieChart>
        </ResponsiveContainer>
      </div>
    );
  }

  // --- GRÁFICOS DINÂMICOS (Unificação da Renderização de Gráficos e Metas) ---
  if (['barra', 'linha', 'area', 'composed', 'grafico'].includes(config.tipo)) {
    const seriesList = config.series && config.series.length > 0 ? config.series : null;
    
    if (seriesList) {
      // Encontra formatos únicos para definir se criará eixo esquerdo e direito.
      const uniqueFormats = Array.from(new Set(seriesList.map(s => s.formato || 'numero')));
      
      return (
        <div className="flex flex-col h-full p-4">
          <h3 className="text-gray-700 text-sm font-bold mb-2">{config.titulo}</h3>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
              <XAxis dataKey="name" tick={<CustomXAxisTick />} height={50} stroke="#9ca3af" />
              
              {uniqueFormats.map((fmt, idx) => (
                <YAxis 
                  key={fmt} 
                  yAxisId={fmt} 
                  orientation={idx % 2 === 0 ? 'left' : 'right'} 
                  tickFormatter={(val) => formatValue(val, fmt)} 
                  tick={{ fontSize: 10 }}
                  stroke={idx === 0 ? "#9ca3af" : "#6b7280"}
                  width={fmt === 'moeda' ? 80 : 50}
                />
              ))}
              
              <Tooltip formatter={(value, name, props) => {
                  const serie = seriesList.find(s => s.nome === name || s.id === props.dataKey);
                  return [formatValue(value, serie ? serie.formato : 'numero'), name];
              }} />
              <Legend verticalAlign="top" height={36} />
              
              {seriesList.map((s, idx) => {
                  const color = s.cor || COLORS[idx % COLORS.length];
                  const yAxisId = s.formato || 'numero';
                  const isDashed = s.is_meta && !s.meta_progressiva; // Meta fixa tracejada, meta progressiva contínua
                  const lineProps = isDashed ? { strokeDasharray: "5 5", dot: false } : { dot: { r: 4, fill: color, strokeWidth: 2, stroke: "#fff" } };
                  
                  if (s.tipo === 'linha') return <Line key={s.id} yAxisId={yAxisId} type="monotone" dataKey={s.id} name={s.nome} stroke={color} strokeWidth={s.is_meta ? 2 : 3} {...lineProps} />;
                  if (s.tipo === 'barra') return <Bar key={s.id} yAxisId={yAxisId} dataKey={s.id} name={s.nome} fill={color} radius={[4, 4, 0, 0]} />;
                  if (s.tipo === 'area') return <Area key={s.id} yAxisId={yAxisId} type="monotone" dataKey={s.id} name={s.nome} stroke={color} fill={color} fillOpacity={0.3} />;
                  
                  return null;
              })}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      );
    }
  }

  if (config.tipo === 'tabela') {
    let colunasRender = [];
    if (config.colunas && config.colunas.length > 0) {
      colunasRender = config.colunas;
    } else if (metadata && metadata.fields.length > 0) {
      colunasRender = [...metadata.fields.map(f => f.name).filter(c => c !== 'itens' && c !== 'retiradas_detalhadas' && c !== 'retiradas_detalhadas_json'), '_empresa'];
    } else if (data && data.length > 0) {
      colunasRender = [...Object.keys(data[0]).filter(k => k !== 'id')];
    }

    const toggleSort = (colName) => {
      const currentSort = config.sort_by || 'id';
      const currentDir = config.sort_order || 'desc';
      const newDir = (currentSort === colName && currentDir === 'asc') ? 'desc' : 'asc';
      onUpdateConfig({ ...config, sort_by: colName, sort_order: newDir });
    };

    const moveColumn = (fromIdx, toIdx) => {
      if (isNaN(fromIdx) || isNaN(toIdx)) return;
      const newCols = [...colunasRender];
      if (fromIdx < 0 || fromIdx >= newCols.length || toIdx < 0 || toIdx >= newCols.length) return;
      const [removed] = newCols.splice(fromIdx, 1);
      newCols.splice(toIdx, 0, removed);
      onUpdateConfig({ ...config, colunas: newCols });
    };

    const removeColumn = (colName) => {
      const newCols = colunasRender.filter(c => c !== colName);
      onUpdateConfig({ ...config, colunas: newCols });
    };

    const addColumn = (colName) => {
      if (colunasRender.includes(colName)) return;
      const newCols = [...colunasRender, colName];
      onUpdateConfig({ ...config, colunas: newCols });
    };

    return (
      <div className="flex flex-col h-full overflow-hidden relative">
        {config.titulo && <div className="p-4 pb-2 text-gray-700 text-sm font-bold shrink-0">{config.titulo}</div>}
        <div className="flex-1 overflow-auto custom-scrollbar p-0" ref={tableContainerRef}>
          <table className="w-full min-w-max text-left border-collapse">
            <thead className="bg-gray-50 sticky top-0 shadow-sm z-20">
              <tr>
                {colunasRender.map((col, idx) => {
                  const fieldMeta = metadata?.fields?.find(f => f.name === col);
                  const isSorted = (config.sort_by || 'id') === col;
                  const sortDir = config.sort_order || 'desc';
                  return (
                    <th
                      key={col}
                      draggable={isEditing}
                      onDragStart={(e) => isEditing && e.dataTransfer.setData('colIndex', idx)}
                      onDragOver={(e) => isEditing && e.preventDefault()}
                      onDrop={(e) => {
                        if (!isEditing) return;
                        e.preventDefault();
                        e.stopPropagation();
                        const fromIdx = e.dataTransfer.getData('colIndex');
                        moveColumn(parseInt(fromIdx), idx);
                      }}
                      onMouseDown={(e) => isEditing && e.stopPropagation()} // Previne conflito com o drag do Rnd
                      className={`px-4 py-2 text-xs font-semibold text-gray-600 border-b relative ${isEditing ? 'cursor-move hover:bg-gray-100 group' : ''}`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-1 truncate">
                          {isEditing && <GripVertical size={12} className="text-gray-300 group-hover:text-gray-400" />}
                          <span>{col === '_empresa' ? 'Empresa (Origem)' : (fieldMeta ? fieldMeta.label : formatLabel(col))}</span>
                        </div>

                        {isEditing && (
                          <div className="flex items-center gap-3">
                            <button
                              type="button"
                              onClick={(e) => { e.stopPropagation(); toggleSort(col); }}
                              className={`p-1 rounded hover:bg-gray-200 ${isSorted ? 'text-blue-600' : 'text-gray-300'}`}
                            >
                              {isSorted && sortDir === 'desc' ? <ArrowDown size={14} /> : <ArrowUp size={14} className={!isSorted ? 'opacity-50' : ''} />}
                            </button>
                            <button
                              type="button"
                              onClick={(e) => { e.stopPropagation(); removeColumn(col); }}
                              className="p-1 rounded hover:bg-red-100 text-gray-300 hover:text-red-500"
                            >
                              <X size={14} />
                            </button>
                          </div>
                        )}
                      </div>
                    </th>
                  );
                })}

                {isEditing && metadata && (
                  <th className="px-2 py-2 w-10 border-b" onMouseDown={(e) => e.stopPropagation()}>
                    <Popover className="relative">
                      <Popover.Button className="p-1.5 bg-blue-600 text-white rounded-full hover:bg-blue-700 shadow-md focus:outline-none">
                        <Plus size={16} />
                      </Popover.Button>

                      <Transition as={Fragment} enter="transition ease-out duration-200" enterFrom="opacity-0 translate-y-1" enterTo="opacity-100 translate-y-0" leave="transition ease-in duration-150" leaveFrom="opacity-100 translate-y-0" leaveTo="opacity-0 translate-y-1">
                        <Popover.Panel className="absolute right-0 z-50 mt-3 w-64 transform px-4 sm:px-0">
                          <div className="overflow-hidden rounded-lg shadow-lg ring-1 ring-black ring-opacity-5 bg-white">
                            <div className="p-3 border-b bg-gray-50">
                              <div className="relative">
                                <Search className="absolute left-2 top-2.5 text-gray-400" size={14} />
                                <input type="text" placeholder="Pesquisar campos..." className="w-full pl-8 pr-3 py-1.5 text-xs border rounded-md focus:ring-2 focus:ring-blue-500 outline-none" value={addColumnSearch} onChange={(e) => setAddColumnSearch(e.target.value)} autoFocus />
                              </div>
                            </div>
                            <div className="max-h-60 overflow-y-auto p-1 custom-scrollbar">
                              {metadata.fields.filter(f => !colunasRender.includes(f.name) && f.name !== 'itens' && f.name !== 'retiradas_detalhadas' && f.name !== 'retiradas_detalhadas_json')
                                .filter(f => f.label.toLowerCase().includes(addColumnSearch.toLowerCase()) || f.name.toLowerCase().includes(addColumnSearch.toLowerCase()))
                                .map(f => (
                                  <button key={f.name} type="button" onClick={() => { addColumn(f.name); setAddColumnSearch(''); }} className="w-full text-left px-3 py-2 text-xs text-gray-700 hover:bg-blue-50 rounded transition-colors flex flex-col">
                                    <span className="font-medium">{f.label}</span>
                                    <span className="text-[10px] text-gray-400 font-mono">{f.name}</span>
                                  </button>
                                ))}
                            </div>
                          </div>
                        </Popover.Panel>
                      </Transition>
                    </Popover>
                  </th>
                )}
              </tr>
            </thead>
            <tbody className="bg-white">
              {data.map((row, idx) => (
                <tr key={idx} className="border-b border-gray-50 hover:bg-blue-50/30 transition-colors">
                  {colunasRender.map(col => {
                    const fieldMeta = metadata?.fields?.find(f => f.name === col);
                    let cellValue = row[col];

                    if (fieldMeta && fieldMeta.type === 'boolean') cellValue = cellValue ? 'Sim' : 'Não';
                    else if (fieldMeta && fieldMeta.format_mask === 'currency') cellValue = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Number(cellValue || 0));
                    else if (fieldMeta && (fieldMeta.type === 'date' || fieldMeta.type === 'datetime')) cellValue = cellValue ? new Date(cellValue).toLocaleString('pt-BR') : '';
                    else if (fieldMeta && fieldMeta.type === 'select' && fieldMeta.options) {
                       const opt = fieldMeta.options.find(o => String(o.value) === String(cellValue));
                       cellValue = opt ? opt.label : cellValue;
                    } else if (typeof cellValue === 'object' && cellValue !== null) cellValue = cellValue[fieldMeta?.foreign_key_label_field || 'id'] || '[Detalhes]';
                    
                    if (cellValue === true) cellValue = 'Sim';
                    if (cellValue === false) cellValue = 'Não';
                    
                    return (
                      <td key={col} className={`px-4 py-2 text-sm text-gray-700 ${fieldMeta?.format_mask === 'currency' ? 'text-right' : ''}`}>
                        {cellValue !== null && cellValue !== undefined ? String(cellValue) : ''}
                      </td>
                    );
                  })}
                  {isEditing && metadata && <td className="bg-gray-50/30 border-b border-gray-50"></td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  // Fallback genérico para gráficos de barra
  return (
    <div className="flex flex-col h-full p-4">
      <h3 className="text-gray-700 text-sm font-bold mb-2">{config.titulo}</h3>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
          <XAxis dataKey="name" tick={<CustomXAxisTick />} height={50} stroke="#9ca3af" />
          <YAxis tick={{ fontSize: 10 }} stroke="#9ca3af" tickFormatter={(val) => formatValue(val)} width={60} />
          <Tooltip formatter={(value) => formatValue(value)} />
          {config.valor_meta && <ReferenceLine y={Number(config.valor_meta)} label="Meta" stroke="red" strokeDasharray="3 3" />}
          <Bar dataKey="value" fill="#3b82f6" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};

// Componente do Menu de Seleção de Tipo de Card
const AddCardSelector = ({ onSelect, onCancel }) => {
  const types = [
    { id: 'metrica', name: 'Métrica', desc: 'Número único (Ex: Total de Vendas)', icon: Calculator, color: 'text-indigo-600', bg: 'bg-indigo-50' },
    { id: 'grafico', name: 'Gráfico', desc: 'Pizza, Barra ou Linha', icon: BarChart2, color: 'text-blue-600', bg: 'bg-blue-50' },
    { id: 'tabela', name: 'Tabela', desc: 'Listagem de registros', icon: TableIcon, color: 'text-green-600', bg: 'bg-green-50' },
    { id: 'filtro', name: 'Filtro', desc: 'Filtro global interativo', icon: Filter, color: 'text-orange-600', bg: 'bg-orange-50' },
    { id: 'texto', name: 'Texto', desc: 'Bloco de texto livre', icon: Type, color: 'text-purple-600', bg: 'bg-purple-50' },
  ];
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-white rounded-xl shadow-2xl p-6 w-full max-w-lg relative animate-fade-in">
        <button onClick={onCancel} className="absolute top-4 right-4 text-gray-400 hover:text-gray-600"><X size={20} /></button>
        <h2 className="text-xl font-bold text-gray-800 mb-6">Escolha o Tipo de Card</h2>
        <div className="grid grid-cols-2 gap-4">
          {types.map(t => (
            <button key={t.id} onClick={() => onSelect(t.id)} className="flex flex-col items-center p-4 border border-gray-200 rounded-lg hover:border-blue-500 hover:shadow-md transition-all group text-center">
              <div className={`p-3 rounded-full ${t.bg} mb-3 group-hover:scale-110 transition-transform`}>
                <t.icon className={t.color} size={28} />
              </div>
              <span className="font-bold text-gray-800">{t.name}</span>
              <span className="text-xs text-gray-500 mt-1">{t.desc}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

const CustomDashboard = () => {
  const { user } = useAuth();
  const [isEditing, setIsEditing] = useState(false);
  const [layout, setLayout] = useState([]);
  const [cardsConfig, setCardsConfig] = useState({});
  const [loading, setLoading] = useState(true);
  const [globalFilters, setGlobalFilters] = useState({});

  const [outrasEmpresas, setOutrasEmpresas] = useState([]);
  const [selectedEmpresas, setSelectedEmpresas] = useState(['current']);
  const [empresasTokens, setEmpresasTokens] = useState({});

  const [workspaces, setWorkspaces] = useState([{ id: 'default', name: 'Visão Geral' }]);
  const [activeWorkspace, setActiveWorkspace] = useState('default');
  const [dragOverTabId, setDragOverTabId] = useState(null);

  // Estados do Modal
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [showTypeSelector, setShowTypeSelector] = useState(false);
  const [selectedType, setSelectedType] = useState('metrica');
  const [editingCardId, setEditingCardId] = useState(null);

  useEffect(() => {
    api.get('/dashboard/custom/preferences').then(response => {
      const savedLayout = response.data.layout || [];

      const fixedLayout = savedLayout.map(item => {
        let { x = 0, y = 0, w = 6, h = 8, minW = 3, minH = 3, workspaceId = 'default' } = item;

        // Conversão de unidades de Grid (antigo) para Pixels (novo)
        if (w < 100) w = w * 80;
        if (h < 50) h = h * 40;
        if (item.w && item.w < 100) {
          x = x * 80;
          y = y * 40;
        }
        if (minW < 100) minW = minW * 80;
        if (minH < 50) minH = minH * 40;

        return {
          ...item,
          x, y, w, h, minW, minH, workspaceId
        };
      });

      setLayout(fixedLayout);

      // Extrai os filtros caso tenham sido salvos junto com o layout
      const config = response.data.cards_config || {};

      if (config.__workspaces) {
        setWorkspaces(config.__workspaces);
        delete config.__workspaces;
      }

      if (config.__globalFilters) {
        const savedFilters = config.__globalFilters;
        let isOldFormat = false;
        // Detecta se os filtros foram salvos no formato antigo (sem espaços)
        for (let key in savedFilters) {
          if (key.startsWith('card_')) {
            isOldFormat = true;
            break;
          }
        }

        if (isOldFormat) {
          setGlobalFilters({ default: savedFilters });
        } else {
          setGlobalFilters(savedFilters);
        }
        delete config.__globalFilters;
      }
      setCardsConfig(config);
      setLoading(false);
    });
  }, []);

  useEffect(() => {
    api.get('/generic/outras_empresas_configuracoes').then(res => {
      setOutrasEmpresas(res.data.items || []);
    }).catch(err => console.log('Sem outras empresas configuradas', err));
  }, []);

  // Inicializa tokens do banco se existirem
  useEffect(() => {
    if (outrasEmpresas.length > 0) {
      const dbTokens = {};
      outrasEmpresas.forEach(emp => {
        if (emp.token) dbTokens[emp.id] = emp.token;
      });
      if (Object.keys(dbTokens).length > 0) {
        setEmpresasTokens(prev => ({ ...dbTokens, ...prev }));
      }
    }
  }, [outrasEmpresas]);

  // Evita múltiplas requisições simultâneas de login para a mesma empresa
  const refreshPromises = useRef({});

  const fetchSingleToken = async (empId) => {
    const empresa = outrasEmpresas.find(e => e.id === empId);
    if (!empresa) return;

    // Se já existe uma requisição de login em andamento para esta empresa, aguarda ela
    if (refreshPromises.current[empId]) {
        return refreshPromises.current[empId];
    }

    const performLogin = async () => {
        // Determina a URL base absoluta para o login
        const getBaseUrl = () => {
            const base = api.defaults.baseURL || '';
            if (base.startsWith('http')) return base;
            return `${window.location.origin}${base.startsWith('/') ? '' : '/'}${base}`;
        };
        const baseUrl = getBaseUrl();

        try {
            const form = new URLSearchParams();
            form.append('username', empresa.email);
            form.append('password', empresa.senha);
            const res = await axios.post(`${baseUrl}/login/token`, form, {
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
            });
            
            const newToken = res.data.access_token;
            setEmpresasTokens(prev => ({ ...prev, [empId]: newToken }));

            // Salva o token no banco para uso futuro (persistência)
            api.put(`/generic/outras_empresas_configuracoes/${empId}`, {
                token: newToken,
                token_expiracao: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString() // Fallback 24h
            }).catch(err => console.error("Erro ao persistir token:", err));

            return newToken;
        } catch (e) {
            console.error(`Erro ao fazer login na empresa ${empresa.nome}:`, e);
            toast.error(`Falha ao autenticar na empresa ${empresa.nome}. Verifique as credenciais nas configurações.`);
            return null;
        }
    };

    refreshPromises.current[empId] = performLogin();
    try {
        const result = await refreshPromises.current[empId];
        return result;
    } finally {
        delete refreshPromises.current[empId];
    }
  };

  useEffect(() => {
    const fetchTokens = async () => {
      for (const empId of selectedEmpresas) {
        if (empId === 'current') continue;
        if (!empresasTokens[empId]) {
          await fetchSingleToken(empId);
        }
      }
    };
    
    if (outrasEmpresas.length > 0) {
      fetchTokens();
    }
  }, [selectedEmpresas, outrasEmpresas, empresasTokens]);

  const saveDashboard = async () => {
    try {
      await api.put('/dashboard/custom/preferences', {
        layout: layout,
        cards_config: { ...cardsConfig, __workspaces: workspaces, __globalFilters: globalFilters }
      });
      setIsEditing(false);
      toast.success("Dashboard salvo com sucesso!");
    } catch (error) {
      console.error("Erro ao salvar", error);
      toast.error("Erro ao salvar o dashboard.");
    }
  };

  const addNewWorkspace = () => {
    const name = prompt("Nome do novo espaço:", `Espaço ${workspaces.length + 1}`);
    if (name && name.trim() !== '') {
      const newId = `ws_${Date.now()}`;
      setWorkspaces(prev => [...prev, { id: newId, name: name.trim() }]);
      setActiveWorkspace(newId);
      setGlobalFilters(prev => ({ ...prev, [newId]: {} }));
    }
  };

  const renameWorkspace = (id, oldName) => {
    const newName = prompt("Renomear espaço:", oldName);
    if (newName && newName.trim() !== "") {
      setWorkspaces(prev => prev.map(ws => ws.id === id ? { ...ws, name: newName.trim() } : ws));
    }
  };

  const removeWorkspace = (id) => {
    if (window.confirm("Tem certeza que deseja excluir este espaço e TODOS os seus cards?")) {
      setWorkspaces(prev => prev.filter(ws => ws.id !== id));

      const cardsToDelete = layout.filter(l => l.workspaceId === id).map(l => l.i);
      setLayout(prev => prev.filter(l => l.workspaceId !== id));

      setCardsConfig(prev => {
        const newConfig = { ...prev };
        cardsToDelete.forEach(cardId => delete newConfig[cardId]);
        return newConfig;
      });

      setGlobalFilters(prev => {
        const newFilters = { ...prev };
        delete newFilters[id];
        return newFilters;
      });

      setActiveWorkspace('default');
    }
  };

  const handleFilterChange = (cardId, filterData) => {
    setGlobalFilters(prev => ({
      ...prev,
      [activeWorkspace]: {
        ...(prev[activeWorkspace] || {}),
        [cardId]: filterData
      }
    }));
  };

  const handleEmpresaToggle = (empId) => {
    setSelectedEmpresas(prev => 
      prev.includes(empId) ? prev.filter(id => id !== empId) : [...prev, empId]
    );
  };

  const addCard = (type) => {
    const newId = `card_${Date.now()}`; // ID único
    setSelectedType(type);
    setShowTypeSelector(false);

    let sizingProps = { w: 300, h: 300, minW: 200, minH: 200 };

    switch (type) {
      case 'metrica':
        sizingProps = { w: 250, h: 150, minW: 150, minH: 100 };
        break;
      case 'filtro':
        sizingProps = { w: 300, h: 150, minW: 200, minH: 100 };
        break;
      case 'grafico':
        sizingProps = { w: 500, h: 350, minW: 300, minH: 200 };
        break;
      case 'tabela':
        sizingProps = { w: 800, h: 400, minW: 400, minH: 200 };
        break;
      case 'texto':
        sizingProps = { w: 300, h: 200, minW: 200, minH: 100 };
        break;
    }

    // Posição padrão
    setLayout(prev => [...prev, { i: newId, x: 50, y: 50, workspaceId: activeWorkspace, ...sizingProps }]);

    // Abre o Modal imediatamente para configurar o card que acabou de nascer
    setEditingCardId(newId);
    setIsModalOpen(true);
  };

  const editCard = (cardId) => {
    setEditingCardId(cardId);
    setIsModalOpen(true);
  };

  const handleSaveCardConfig = (newConfig) => {
    setCardsConfig(prev => ({
      ...prev,
      [editingCardId]: newConfig
    }));
    setIsModalOpen(false);
  };

  const removeCard = (cardId) => {
    setLayout(layout.filter(l => l.i !== cardId));
    const newConfig = { ...cardsConfig };
    delete newConfig[cardId];
    setCardsConfig(newConfig);

    setGlobalFilters(prev => {
      const newFilters = { ...prev };
      Object.keys(newFilters).forEach(wsId => {
        if (newFilters[wsId] && newFilters[wsId][cardId]) {
          newFilters[wsId] = { ...newFilters[wsId] };
          delete newFilters[wsId][cardId];
        }
      });
      return newFilters;
    });
  };

  if (loading) return <div className="p-8 text-center">Carregando dashboard...</div>;

  const activeLayout = layout.filter(l => l.workspaceId === activeWorkspace);

  // Calculando altura mínima do container para abrigar todos os Rnds sem cortar no bottom
  const containerHeight = Math.max(
    600,
    ...activeLayout.map(item => (item.y || 0) + (item.h || 0) + 50)
  );

  return (
    <div className="bg-gray-100 min-h-screen p-16">
      <div className="container mx-auto">
        {showTypeSelector && <AddCardSelector onSelect={addCard} onCancel={() => setShowTypeSelector(false)} />}

        {/* HEADER */}
        <div className="flex flex-col md:flex-row justify-between items-center mb-6 gap-4">
          <div>
            <h1 className="text-4xl font-bold text-gray-800">Dashboard</h1>
          </div>

          <div className="flex gap-2 items-center">
            {outrasEmpresas.length > 0 && (
              <Popover className="relative">
                <Popover.Button className="bg-white border border-gray-300 text-gray-700 font-semibold py-2 px-4 rounded-md shadow-sm hover:bg-gray-50 flex items-center gap-2 transition-colors text-sm">
                  <Filter size={16} /> Empresas ({selectedEmpresas.length})
                </Popover.Button>
                <Transition as={Fragment} enter="transition ease-out duration-200" enterFrom="opacity-0 translate-y-1" enterTo="opacity-100 translate-y-0" leave="transition ease-in duration-150" leaveFrom="opacity-100 translate-y-0" leaveTo="opacity-0 translate-y-1">
                  <Popover.Panel className="absolute right-0 z-50 mt-2 w-56 bg-white rounded-lg shadow-xl ring-1 ring-black ring-opacity-5 p-2">
                    <div className="space-y-1">
                      <label className="flex items-center p-2 hover:bg-gray-50 rounded cursor-pointer">
                        <input type="checkbox" checked={selectedEmpresas.includes('current')} onChange={() => handleEmpresaToggle('current')} className="rounded border-gray-300 text-teal-600 shadow-sm focus:ring-teal-500 mr-2" />
                        <span className="text-sm text-gray-700">Empresa Atual</span>
                      </label>
                      {outrasEmpresas.map(emp => (
                        <label key={emp.id} className="flex items-center p-2 hover:bg-gray-50 rounded cursor-pointer">
                          <input type="checkbox" checked={selectedEmpresas.includes(emp.id)} onChange={() => handleEmpresaToggle(emp.id)} className="rounded border-gray-300 text-teal-600 shadow-sm focus:ring-teal-500 mr-2" />
                          <span className="text-sm text-gray-700">{emp.nome}</span>
                        </label>
                      ))}
                    </div>
                  </Popover.Panel>
                </Transition>
              </Popover>
            )}
            
            {isEditing ? (
              <>
                <button onClick={() => setShowTypeSelector(true)} className="flex items-center px-4 py-2 text-sm text-white bg-blue-600 font-medium rounded-md shadow-sm hover:bg-blue-700 transition-colors">
                  <Plus className="w-4 h-4 mr-2" /> Adicionar Card
                </button>
                <button onClick={saveDashboard} className="flex items-center px-4 py-2 text-sm text-white bg-green-600 font-medium rounded-md shadow-sm hover:bg-green-700 transition-colors">
                  <Save className="w-4 h-4 mr-2" /> Salvar Layout
                </button>
              </>
            ) : (
              <button onClick={() => setIsEditing(true)} className="flex items-center px-4 py-2 text-sm text-white bg-blue-600 font-medium rounded-md shadow-sm hover:bg-blue-700 transition-colors">
                <Settings className="w-4 h-4 mr-2" /> Editar Dashboard
              </button>
            )}
          </div>
        </div>

        {/* ABAS (ESPAÇOS) */}
        <div className="mb-4 border-b border-gray-200">
          <nav className="-mb-px flex space-x-2 overflow-x-auto custom-scrollbar" aria-label="Tabs">
            {workspaces.map(ws => (
              <button
                type="button"
                key={ws.id}
                data-workspace-target={ws.id}
                onClick={() => setActiveWorkspace(ws.id)}
                onDoubleClick={() => isEditing && renameWorkspace(ws.id, ws.name)}
                className={`whitespace-nowrap py-3 px-4 border-b-2 font-medium text-base transition-all flex items-center gap-2 select-none ${
                  activeWorkspace === ws.id
                    ? 'bg-teal-600 text-white rounded-t-lg border-teal-600'
                    : dragOverTabId === ws.id
                      ? 'border-green-400 text-green-700 bg-green-50 scale-105 transform origin-bottom rounded-t-lg'
                      : 'border-transparent text-gray-500 hover:text-gray-700'
                  }`}
                title={isEditing ? "Duplo clique para renomear" : ""}
              >
                {ws.name}
                {isEditing && ws.id !== 'default' && activeWorkspace === ws.id && (
                  <span onClick={(e) => { e.stopPropagation(); removeWorkspace(ws.id); }} className="p-1 rounded-full text-teal-200 hover:text-white hover:bg-teal-700 ml-1 transition-colors" title="Excluir espaço">
                    <X size={16} />
                  </span>
                )}
              </button>
            ))}
            {isEditing && (
              <button
                type="button"
                onClick={addNewWorkspace}
                className="whitespace-nowrap py-3 px-4 border-b-2 border-transparent font-medium text-base text-gray-500 hover:text-teal-600 flex items-center gap-1 transition-colors"
                title="Adicionar novo espaço"
              >
                <Plus size={18} /> Novo Espaço
              </button>
            )}
          </nav>
        </div>

        {/* ÁREA DO GRID */}
        <div
          className={isEditing ? "relative bg-gray-200/50 p-2 rounded-xl border-2 border-dashed border-gray-400" : "relative"}
          style={{ minHeight: `${containerHeight}px` }}
        >
          {activeLayout.map((item) => (
            <Rnd
              key={item.i}
              size={{ width: item.w, height: item.h }}
              position={{ x: item.x, y: item.y }}
              onDrag={(e, d) => {
                let clientX, clientY;
                if (e.type.includes('mouse')) {
                  clientX = e.clientX; clientY = e.clientY;
                } else if (e.type.includes('touch') && e.changedTouches && e.changedTouches.length > 0) {
                  clientX = e.changedTouches[0].clientX; clientY = e.changedTouches[0].clientY;
                }

                if (clientX !== undefined && clientY !== undefined && typeof document.elementsFromPoint === 'function') {
                  const elements = document.elementsFromPoint(clientX, clientY);
                  const tabElement = elements.find(el => el && el.getAttribute && el.getAttribute('data-workspace-target'));
                  if (tabElement) {
                    const target = tabElement.getAttribute('data-workspace-target');
                    setDragOverTabId(target !== activeWorkspace ? target : null);
                  } else {
                    setDragOverTabId(null);
                  }
                }
              }}
              onDragStop={(e, d) => {
                setDragOverTabId(null);

                let clientX, clientY;
                if (e.type.includes('mouse')) {
                  clientX = e.clientX; clientY = e.clientY;
                } else if (e.type.includes('touch') && e.changedTouches && e.changedTouches.length > 0) {
                  clientX = e.changedTouches[0].clientX; clientY = e.changedTouches[0].clientY;
                }

                if (clientX !== undefined && clientY !== undefined && typeof document.elementsFromPoint === 'function') {
                  const elements = document.elementsFromPoint(clientX, clientY);
                  const tabElement = elements.find(el => el && el.getAttribute && el.getAttribute('data-workspace-target'));
                  if (tabElement) {
                    const targetWorkspace = tabElement.getAttribute('data-workspace-target');
                    if (targetWorkspace !== activeWorkspace) {
                      // Move o layout
                      setLayout(prev => prev.map(l => l.i === item.i ? { ...l, workspaceId: targetWorkspace } : l));

                      // Migra o filtro para a nova aba
                      setGlobalFilters(prev => {
                        const newFilters = { ...prev };
                        const cardFilter = newFilters[activeWorkspace]?.[item.i];
                        if (cardFilter) {
                          newFilters[targetWorkspace] = { ...(newFilters[targetWorkspace] || {}), [item.i]: cardFilter };
                          newFilters[activeWorkspace] = { ...newFilters[activeWorkspace] };
                          delete newFilters[activeWorkspace][item.i];
                        }
                        return newFilters;
                      });

                      toast.success("Card movido para outro espaço!");
                      return; // Ignora o reposicionamento XY se mudou de aba
                    }
                  }
                }
                setLayout(prev => prev.map(l => l.i === item.i ? { ...l, x: d.x, y: d.y } : l));
              }}
              onResizeStop={(e, direction, ref, delta, position) => {
                setLayout(prev => prev.map(l => l.i === item.i ? {
                  ...l,
                  w: parseInt(ref.style.width, 10),
                  h: parseInt(ref.style.height, 10),
                  ...position
                } : l));
              }}
              minWidth={['filtro', 'metrica', 'texto'].includes(cardsConfig[item.i]?.tipo) ? 150 : (item.minW || 300)}
              minHeight={['filtro', 'metrica', 'texto'].includes(cardsConfig[item.i]?.tipo) ? 50 : 150}
              disableDragging={!isEditing}
              enableResizing={isEditing}
              bounds="parent"
              dragGrid={[8, 8]}
              resizeGrid={[8, 8]}
              className={`bg-white rounded-xl shadow-sm border border-gray-100 group hover:!z-50 focus-within:!z-50 transition-all ${cardsConfig[item.i]?.tipo === 'filtro' ? '!z-40' : '!z-10'}`}
            >

              {/* Wrapper do conteúdo para esconder overflow (ex: tabelas) sem cortar os resizers da grade */}
              <div className={`absolute inset-0 rounded-xl ${cardsConfig[item.i]?.tipo === 'filtro' ? 'overflow-visible' : 'overflow-hidden'}`}>
                {/* O conteúdo real do Card */}
                {cardsConfig[item.i] ? (
                  <DynamicCard 
                    config={{ ...cardsConfig[item.i], i: item.i }} 
                    globalFilters={globalFilters[activeWorkspace] || {}} 
                    onFilterChange={handleFilterChange} 
                    isEditing={isEditing}
                    onUpdateConfig={(newConfig) => {
                      setCardsConfig(prev => ({
                        ...prev,
                        [item.i]: newConfig
                      }));
                    }}
                    selectedEmpresas={selectedEmpresas}
                    empresasTokens={empresasTokens}
                    outrasEmpresas={outrasEmpresas}
                    onRefreshToken={fetchSingleToken}
                  />
                ) : (
                  <div className="flex h-full items-center justify-center text-gray-400 text-sm text-center px-4">
                    Clique na engrenagem para configurar este card.
                  </div>
                )}
              </div>

              {/* Controles de Edição (Canto superior direito com animação de slide) */}
              {isEditing && (
                <div className="absolute top-0 right-0 z-10 overflow-hidden rounded-tr-xl rounded-bl-2xl pointer-events-none">
                  <div className="flex gap-2 p-2 transform -translate-y-full opacity-0 group-hover:translate-y-0 group-hover:opacity-100 transition-all duration-300 pointer-events-auto bg-gray-100/90 border-b border-l border-gray-200 shadow-sm backdrop-blur-sm">
                    <button onClick={() => editCard(item.i)} onMouseDown={(e) => e.stopPropagation()} className="p-1.5 bg-white text-blue-600 rounded-md shadow-sm hover:bg-blue-50 transition-colors cursor-pointer" title="Configurar Card">
                      <Settings className="w-4 h-4" />
                    </button>
                    <button onClick={() => removeCard(item.i)} onMouseDown={(e) => e.stopPropagation()} className="p-1.5 bg-white text-red-600 rounded-md shadow-sm hover:bg-red-50 transition-colors cursor-pointer" title="Remover Card">
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              )}
            </Rnd>
          ))}
        </div>

        {/* Modal de Configuração */}
        <CardConfigModal
          isOpen={isModalOpen}
          onClose={() => {
            setIsModalOpen(false);
            // Se fechou sem salvar um card novo (que ainda não tinha config), removemos ele do layout para não ficar um quadrado fantasma
            if (!cardsConfig[editingCardId]) removeCard(editingCardId);
          }}
          onSave={handleSaveCardConfig}
          initialConfig={cardsConfig[editingCardId]}
          preSelectedType={selectedType}
        />
      </div>
    </div>
  );
};

export default CustomDashboard;
