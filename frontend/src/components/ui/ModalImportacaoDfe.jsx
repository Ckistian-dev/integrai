import React, { useState, useEffect, Fragment } from 'react';
import { Transition, Dialog } from '@headlessui/react';
import { X, FileDown, Loader2, Plus } from 'lucide-react';
import api from '../../api/axiosConfig';
import { toast } from 'react-toastify';
import AsyncSelect from 'react-select/async';
import AsyncCreatableSelect from 'react-select/async-creatable';

const OPCOES_PAGAMENTO = [
  { value: '01', label: 'Dinheiro' },
  { value: '02', label: 'Cheque' },
  { value: '03', label: 'Cartão de Crédito' },
  { value: '04', label: 'Cartão de Débito' },
  { value: '05', label: 'Crédito Loja' },
  { value: '10', label: 'Vale Alimentação' },
  { value: '11', label: 'Vale Refeição' },
  { value: '12', label: 'Vale Presente' },
  { value: '13', label: 'Vale Combustível' },
  { value: '14', label: 'Duplicata Mercantil' },
  { value: '15', label: 'Boleto Bancário' },
  { value: '16', label: 'Depósito Bancário' },
  { value: '17', label: 'PIX' },
  { value: '18', label: 'Débito em Conta' },
  { value: '90', label: 'Sem Pagamento' },
  { value: '99', label: 'Outros' },
];

const AsyncProductSelect = ({ value, onChange }) => {
  const [selectedOption, setSelectedOption] = useState(null);
  
  const loadOptions = (inputValue, callback) => {
    api.get(`/generic/produtos`, {
      params: { search_term: inputValue, limit: 1000, situacao: 'true' }
    }).then(response => {
      const options = response.data.items.map(item => ({
        value: item.id,
        label: `${item.sku} - ${item.descricao}`
      }));
      callback(options);
    }).catch(() => callback([]));
  };

  useEffect(() => {
    if (value && (!selectedOption || selectedOption.value !== value)) {
      api.get(`/generic/produtos/${value}`)
        .then(response => {
            const item = response.data;
            setSelectedOption({ value: item.id, label: `${item.sku} - ${item.descricao}` });
        })
        .catch(() => setSelectedOption({ value, label: `ID ${value}` }));
    } else if (!value) {
        setSelectedOption(null);
    }
  }, [value]);

  return (
    <AsyncSelect
      cacheOptions
      defaultOptions
      loadOptions={loadOptions}
      value={selectedOption}
      onChange={(opt) => {
          setSelectedOption(opt);
          onChange(opt ? opt.value : null);
      }}
      placeholder="Buscar produto..."
      menuPortalTarget={document.body}
      styles={{
        control: (base) => ({ ...base, minHeight: '38px', borderColor: '#d1d5db', fontSize: '14px' }),
        menu: (base) => ({ ...base, zIndex: 9999, fontSize: '14px' }),
        menuPortal: (base) => ({ ...base, zIndex: 9999 })
      }}
      isClearable
    />
  );
};

// Componente para buscar o Plano de Contas
const AsyncPlanoContaSelect = ({ value, onChange }) => {
  const [selectedOption, setSelectedOption] = useState(null);

  const loadOptions = (inputValue, callback) => {
    api.get(`/generic/classificacao_contabil`, {
      params: { search_term: inputValue, limit: 1000 }
    }).then(response => {
      const options = response.data.items.map(item => ({
        value: item.id,
        label: `${item.grupo || ''} - ${item.descricao}`.replace(/^- /, '')
      }));
      callback(options);
    }).catch(() => callback([]));
  };

  useEffect(() => {
    if (value && (!selectedOption || selectedOption.value !== value)) {
      api.get(`/generic/classificacao_contabil/${value}`)
        .then(response => {
          const item = response.data;
          setSelectedOption({ value: item.id, label: `${item.grupo || ''} - ${item.descricao}`.replace(/^- /, '') });
        })
        .catch(() => setSelectedOption({ value, label: `ID ${value}` }));
    } else if (!value) {
      setSelectedOption(null);
    }
  }, [value]);

  return (
    <AsyncSelect
      cacheOptions
      defaultOptions
      loadOptions={loadOptions}
      value={selectedOption}
      onChange={(opt) => {
        setSelectedOption(opt);
        onChange(opt ? opt.value : null);
      }}
      placeholder="Buscar plano de contas..."
      menuPortalTarget={document.body}
      styles={{
        control: (base) => ({ ...base, minHeight: '38px', borderColor: '#d1d5db', fontSize: '14px' }),
        menu: (base) => ({ ...base, zIndex: 9999, fontSize: '14px' }),
        menuPortal: (base) => ({ ...base, zIndex: 9999 })
      }}
      isClearable
    />
  );
};

// Componente para buscar/criar a Conta Bancária
const AsyncCaixaSelect = ({ value, onChange }) => {
  const [selectedOption, setSelectedOption] = useState(null);

  const loadOptions = (inputValue, callback) => {
    api.get(`/generic/opcoes_campos`, {
      params: { search_term: inputValue, model_name: 'contas', field_name: 'caixa_destino_origem', limit: 1000 }
    }).then(response => {
      const options = response.data.items.map(item => ({
        value: item.valor,
        label: item.valor
      }));
      callback(options);
    }).catch(() => callback([]));
  };

  useEffect(() => {
    if (value) {
      setSelectedOption({ value, label: value });
    } else {
      setSelectedOption(null);
    }
  }, [value]);

  return (
    <AsyncCreatableSelect
      cacheOptions
      defaultOptions
      loadOptions={loadOptions}
      value={selectedOption}
      onChange={(opt) => {
        setSelectedOption(opt);
        onChange(opt ? opt.value : '');
      }}
      placeholder="Buscar ou digitar nova..."
      formatCreateLabel={(inputValue) => `Criar "${inputValue}"`}
      menuPortalTarget={document.body}
      styles={{
        control: (base) => ({ ...base, minHeight: '38px', borderColor: '#d1d5db', fontSize: '14px' }),
        menu: (base) => ({ ...base, zIndex: 9999, fontSize: '14px' }),
        menuPortal: (base) => ({ ...base, zIndex: 9999 })
      }}
      isClearable
    />
  );
};

const ModalImportacaoDfe = ({ isOpen, onClose, notaId, onSuccess }) => {
  const [loading, setLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [nota, setNota] = useState(null);
  const [mapeamento, setMapeamento] = useState([]); // [{sku_forn, id_erp, qty}]
  const [config, setConfig] = useState({
    estoque: true,
    financeiro: true,
    id_classificacao_contabil: '',
    caixa_destino_origem: '',
    forma_pagamento: '90'
  });

  useEffect(() => {
    if (isOpen && notaId) {
      const fetchData = async () => {
        setLoading(true);
        try {
          const res = await api.get(`/dfe/detalhes/${notaId}`);
          setNota(res.data);
          // Inicializa mapeamento com base no que o backend já reconhece via 'variacoes'
          setMapeamento(res.data.itens);
          setConfig(prev => ({
            ...prev,
            forma_pagamento: res.data.forma_pagamento || '90'
          }));
        } catch (e) { 
            toast.error("Erro ao carregar detalhes da nota."); 
            onClose(); 
        } finally { 
            setLoading(false); 
        }
      };
      fetchData();
    }
  }, [isOpen, notaId]);

  const handleConfirm = async () => {
    if (config.financeiro && (!config.id_classificacao_contabil || !config.caixa_destino_origem)) {
      toast.warning("Selecione o Plano de Contas e a Conta Bancária para gerar o financeiro.");
      return;
    }

    setIsSaving(true);
    try {
      await api.post(`/dfe/importar`, {
        nota_id: notaId,
        mapeamento: mapeamento,
        movimentar_estoque: config.estoque,
        gerar_financeiro: config.financeiro,
        id_classificacao_contabil: config.financeiro ? config.id_classificacao_contabil : null,
        caixa_destino_origem: config.financeiro ? config.caixa_destino_origem : null,
        forma_pagamento: config.financeiro ? config.forma_pagamento : null
      });
      toast.success("Nota importada e estoque/financeiro atualizados!");
      onSuccess();
      onClose();
    } catch (e) { 
      toast.error(e.response?.data?.detail || "Falha na importação."); 
    } finally {
      setIsSaving(false);
    }
  };

  const handleCreateProduct = async (idx, item) => {
    const copy = [...mapeamento];
    copy[idx].isCreating = true;
    setMapeamento(copy);

    try {
      const res = await api.post('/generic/produtos', {
        sku: item.sku_fornecedor || `NFE-${Date.now().toString().slice(-6)}`,
        descricao: item.descricao,
        unidade: 'un',
        tipo_produto: 'mercadoria de revenda',
        origem: 'nacional',
        ipi_aliquota: 0,
        estoque_negativo: false,
        situacao: true,
        variacoes: item.sku_fornecedor ? [item.sku_fornecedor] : []
      });
      toast.success('Produto criado com sucesso!');
      setMapeamento(prev => prev.map((m, i) => i === idx ? { ...m, id_produto_erp: res.data.id, isCreating: false } : m));
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erro ao criar produto. Verifique se o SKU já existe.');
      setMapeamento(prev => prev.map((m, i) => i === idx ? { ...m, isCreating: false } : m));
    }
  };

  if (!isOpen) return null;

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
              <Dialog.Panel className="relative transform overflow-visible rounded-lg bg-white text-left shadow-xl transition-all sm:my-8 sm:w-full sm:max-w-4xl">
                <button
                  type="button"
                  className="absolute top-3 right-2.5 text-gray-400 bg-transparent hover:bg-gray-200 hover:text-gray-900 rounded-lg text-sm p-1.5 ml-auto inline-flex items-center"
                  onClick={onClose}
                >
                  <X className="w-5 h-5" />
                </button>

                <div className="bg-white px-4 pt-5 pb-4 sm:p-6 sm:pb-4 rounded-t-lg">
                  <Dialog.Title as="h3" className="text-2xl font-bold leading-6 text-gray-900 mb-6 flex items-center">
                    <FileDown className="w-6 h-6 mr-2 text-green-600" />
                    Importar Nota Fiscal (Entrada)
                  </Dialog.Title>

                  {loading ? (
                     <div className="flex justify-center py-8"><Loader2 className="animate-spin h-8 w-8 text-blue-500" /></div>
                  ) : (
                    <div className="space-y-6">
                      <p className="text-sm text-gray-600">
                        Vincule os produtos presentes no XML da nota aos cadastros do seu sistema ERP:
                      </p>
                      
                      <div className="overflow-x-auto border border-gray-200 rounded-lg">
                        <table className="min-w-full divide-y divide-gray-200">
                          <thead className="bg-gray-50">
                            <tr>
                              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-1/3">Item na Nota (Fornecedor)</th>
                              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-1/2">Produto Correspondente (ERP)</th>
                              <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider w-1/6">Qtd.</th>
                            </tr>
                          </thead>
                          <tbody className="bg-white divide-y divide-gray-200">
                            {mapeamento.map((item, idx) => (
                              <tr key={idx} className="hover:bg-gray-50">
                                <td className="px-4 py-3 text-sm text-gray-900">
                                  <span className="font-bold text-blue-700">{item.sku_fornecedor}</span>
                                  <div className="text-xs text-gray-500 mt-1">{item.descricao}</div>
                                </td>
                                <td className="px-4 py-3">
                                  <div className="flex items-center gap-2">
                                    <div className="flex-1 min-w-[200px]">
                                      <AsyncProductSelect 
                                        value={item.id_produto_erp}
                                        onChange={(val) => {
                                          const copy = [...mapeamento];
                                          copy[idx].id_produto_erp = val;
                                          setMapeamento(copy);
                                        }}
                                      />
                                    </div>
                                    {!item.id_produto_erp && (
                                      <button
                                        type="button"
                                        onClick={() => handleCreateProduct(idx, item)}
                                        disabled={item.isCreating}
                                        className="p-2 bg-blue-50 text-blue-600 rounded-md hover:bg-blue-100 border border-blue-200 transition-colors flex-shrink-0"
                                        title="Cadastrar Produto Automaticamente"
                                      >
                                        {item.isCreating ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />}
                                      </button>
                                    )}
                                  </div>
                                </td>
                                <td className="px-4 py-3 text-sm text-center font-bold text-gray-700">
                                  {item.quantidade}
                                </td>
                              </tr>
                            ))}
                            {mapeamento.length === 0 && (
                                <tr>
                                    <td colSpan="3" className="px-4 py-4 text-center text-sm text-gray-500">
                                        Nenhum item encontrado na nota.
                                    </td>
                                </tr>
                            )}
                          </tbody>
                        </table>
                      </div>
                      
                      <div className="flex flex-col gap-4 p-4 bg-gray-50 border border-gray-200 rounded-md">
                        <div className="flex gap-6">
                            <label className="flex items-center gap-2 cursor-pointer">
                                <input 
                                    type="checkbox" 
                                    className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                                    checked={config.estoque} 
                                    onChange={e => setConfig({...config, estoque: e.target.checked})} 
                                /> 
                                <span className="text-sm font-medium text-gray-700">Movimentar Estoque (Entrada)</span>
                            </label>
                            
                            <label className="flex items-center gap-2 cursor-pointer">
                                <input 
                                    type="checkbox" 
                                    className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                                    checked={config.financeiro} 
                                    onChange={e => setConfig({
                                        ...config, 
                                        financeiro: e.target.checked,
                                        id_classificacao_contabil: e.target.checked ? config.id_classificacao_contabil : '',
                                        caixa_destino_origem: e.target.checked ? config.caixa_destino_origem : ''
                                    })} 
                                /> 
                                <span className="text-sm font-medium text-gray-700">Gerar Financeiro (A Pagar)</span>
                            </label>
                        </div>

                        {config.financeiro && (
                          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-2 pt-4 border-t border-gray-200">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Plano de Contas</label>
                                <AsyncPlanoContaSelect
                                    value={config.id_classificacao_contabil}
                                    onChange={(val) => setConfig({...config, id_classificacao_contabil: val})}
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Conta Bancária / Caixa Prevista</label>
                                <AsyncCaixaSelect
                                    value={config.caixa_destino_origem}
                                    onChange={(val) => setConfig({...config, caixa_destino_origem: val})}
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Forma de Pagamento</label>
                                <select
                                    className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 text-sm h-[38px] px-3"
                                    value={config.forma_pagamento}
                                    onChange={e => setConfig({...config, forma_pagamento: e.target.value})}
                                >
                                    {OPCOES_PAGAMENTO.map(opt => (
                                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                                    ))}
                                </select>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>

                <div className="bg-gray-50 px-4 py-3 sm:flex sm:flex-row-reverse sm:px-6 rounded-b-lg border-t border-gray-200">
                  <button
                    type="button"
                    disabled={loading || isSaving || mapeamento.some(m => !m.id_produto_erp)}
                    className="inline-flex w-full justify-center rounded-md border border-transparent bg-green-600 px-4 py-2 text-base font-medium text-white shadow-sm hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 sm:ml-3 sm:w-auto sm:text-sm disabled:cursor-not-allowed disabled:opacity-70"
                    onClick={handleConfirm}
                  >
                    {isSaving ? <Loader2 className="w-5 h-5 mr-2 animate-spin" /> : null}
                    Confirmar Importação
                  </button>
                  <button
                    type="button"
                    disabled={isSaving}
                    className="mt-3 inline-flex w-full justify-center rounded-md border border-gray-300 bg-white px-4 py-2 text-base font-medium text-gray-700 shadow-sm hover:bg-gray-50 focus:outline-none sm:mt-0 sm:w-auto sm:text-sm"
                    onClick={onClose}
                  >
                    Cancelar
                  </button>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition.Root>
  );
};

export default ModalImportacaoDfe;
