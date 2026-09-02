import React, { useState, useEffect } from 'react';
import { Trash2, Plus } from 'lucide-react';
import { SelectInput } from './InputFields';
import CreatableSelect from 'react-select/creatable';
import api from '../../api/axiosConfig';

export const STATUS_SHOPEE_OPTIONS = [
  { value: 'READY_TO_SHIP', label: 'Pronto para Envio / NF Emitida (READY_TO_SHIP)' },
  { value: 'PROCESSED', label: 'Em Expedição / Despacho Solicitado (PROCESSED)' },
  { value: 'SHIPPED', label: 'Despachado / Em Trânsito (SHIPPED)' },
  { value: 'COMPLETED', label: 'Entregue / Concluído (COMPLETED)' },
  { value: 'CANCELLED', label: 'Cancelado (CANCELLED)' },
];

export const ShopeeStatusRulesInput = ({ field, value, onChange, disabled }) => {
  const { name } = field || {};
  const [rules, setRules] = useState([]);
  const [columnOptions, setColumnOptions] = useState({});
  const [pedidoColumns, setPedidoColumns] = useState([]);

  // Carrega todas as colunas da tabela de pedidos via metadata
  useEffect(() => {
    api.get('/metadata/pedidos')
      .then(res => {
        const cols = (res.data?.fields || [])
          .filter(f => f.visible !== false && f.name !== 'id')
          .map(f => ({ value: f.name, label: f.label || f.name }));
        setPedidoColumns(cols);
      })
      .catch(() => setPedidoColumns([]));
  }, []);

  // Sincroniza o estado interno com o valor vindo do formData
  useEffect(() => {
    let parsed = [];
    if (Array.isArray(value)) {
      parsed = value;
    } else if (typeof value === 'string' && value.trim()) {
      try { parsed = JSON.parse(value); } catch (e) { parsed = []; }
    }
    setRules(parsed);
  }, [value]);

  // Carrega os valores distintos de uma coluna no banco para o CreatableSelect
  const fetchColumnOptions = async (coluna) => {
    if (!coluna || columnOptions[coluna]) return;
    try {
      const res = await api.get(`/generic/pedidos/distinct/${coluna}`);
      const data = res.data || [];
      const normalized = data.map(item =>
        typeof item === 'string' ? { value: item, label: item } : item
      );
      setColumnOptions(prev => ({ ...prev, [coluna]: normalized }));
    } catch {
      setColumnOptions(prev => ({ ...prev, [coluna]: [] }));
    }
  };

  // Pré-carrega as colunas das regras existentes
  useEffect(() => {
    rules.forEach(rule => { if (rule.coluna_pedido) fetchColumnOptions(rule.coluna_pedido); });
  }, [rules]);

  const updateRules = (newRules) => {
    setRules(newRules);
    onChange({ target: { name: name || 'regras_atualizacao_status', value: newRules } });
  };

  const handleAddRule = () => {
    const defaultCol = 'status_intelipost';
    fetchColumnOptions(defaultCol);
    updateRules([...rules, { coluna_pedido: defaultCol, valor_coluna: '', status_shopee: 'SHIPPED' }]);
  };

  const handleRemoveRule = (index) => updateRules(rules.filter((_, i) => i !== index));

  const handleRuleChange = (index, prop, val) => {
    const updated = [...rules];
    updated[index] = { ...updated[index], [prop]: val };
    if (prop === 'coluna_pedido') {
      fetchColumnOptions(val);
      updated[index].valor_coluna = '';
    }
    updateRules(updated);
  };

  return (
    <div className="md:col-span-3 space-y-3">
      {rules.map((item, idx) => {
        const currentCol = item.coluna_pedido || '';
        const optsForCol = columnOptions[currentCol] || [];
        const selectedOpt = item.valor_coluna
          ? (optsForCol.find(o => o.value === item.valor_coluna) || { value: item.valor_coluna, label: item.valor_coluna })
          : null;

        return (
          <div key={idx} className="grid grid-cols-1 md:grid-cols-3 gap-x-6 gap-y-4 items-start">

            {/* Coluna 1: Coluna do Pedido */}
            <div>
              <SelectInput
                field={{
                  name: `coluna_pedido_${idx}`,
                  label: idx === 0 ? 'Coluna do Pedido' : '',
                  placeholder: 'Selecione a coluna...'
                }}
                value={item.coluna_pedido || ''}
                options={pedidoColumns}
                onChange={(e) => handleRuleChange(idx, 'coluna_pedido', e.target.value)}
                disabled={disabled}
              />
            </div>

            {/* Coluna 2: Valor na Coluna (CreatableSelect) */}
            <div className="flex flex-col">
              {idx === 0 && (
                <label className="mb-1.5 text-sm font-medium text-gray-700">Valor na Coluna</label>
              )}
              <CreatableSelect
                value={selectedOpt}
                onChange={(opt) => handleRuleChange(idx, 'valor_coluna', opt ? opt.value : '')}
                options={optsForCol}
                isDisabled={disabled}
                isClearable
                placeholder="Escolha ou digite..."
                formatCreateLabel={(val) => `Usar "${val}"`}
                menuPortalTarget={document.body}
                styles={{
                  control: (base, state) => ({
                    ...base,
                    minHeight: '38px',
                    height: '38px',
                    borderColor: state.isFocused ? '#ee4d2d' : '#d1d5db',
                    boxShadow: state.isFocused ? '0 0 0 2px rgba(238,77,45,0.2)' : 'var(--tw-shadow, 0 1px 2px 0 rgb(0 0 0 / .05))',
                    fontSize: '0.875rem',
                    backgroundColor: disabled ? '#f9fafb' : '#fff',
                  }),
                  valueContainer: (base) => ({ ...base, padding: '0 12px', flexWrap: 'nowrap' }),
                  singleValue: (base) => ({ ...base, color: '#1f2937' }),
                  indicatorsContainer: (base) => ({ ...base, height: '38px' }),
                  menuPortal: (base) => ({ ...base, zIndex: 9999 }),
                }}
              />
            </div>

            {/* Coluna 3: Status Shopee + botão remover */}
            <div className="flex flex-col">
              {idx === 0 && (
                <label className="mb-1.5 text-sm font-medium text-gray-700">Status Shopee</label>
              )}
              <div className="flex items-center gap-2">
                <div className="flex-1">
                  <SelectInput
                    field={{
                      name: `status_shopee_${idx}`,
                      label: '',
                      placeholder: 'Selecione o status...'
                    }}
                    value={item.status_shopee || item.status_meli || 'SHIPPED'}
                    options={STATUS_SHOPEE_OPTIONS}
                    onChange={(e) => handleRuleChange(idx, 'status_shopee', e.target.value)}
                    disabled={disabled}
                  />
                </div>

                {rules.length > 0 && (
                  <button
                    type="button"
                    onClick={() => handleRemoveRule(idx)}
                    disabled={disabled}
                    className="h-[38px] w-[38px] flex items-center justify-center text-gray-400 hover:text-red-600 transition-colors shrink-0"
                    title="Remover Regra"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>

          </div>
        );
      })}

      <div className="pt-2">
        <button
          type="button"
          onClick={handleAddRule}
          disabled={disabled}
          className="w-full py-2.5 px-4 border border-dashed border-gray-300 hover:border-orange-500 bg-gray-50/60 hover:bg-orange-50/40 text-gray-600 hover:text-orange-700 rounded-md text-xs font-semibold flex items-center justify-center gap-2 transition-all shadow-2xs group disabled:opacity-50"
        >
          <div className="p-1 rounded bg-white group-hover:bg-[#ee4d2d] text-gray-500 group-hover:text-white border border-gray-200 group-hover:border-[#ee4d2d] transition-colors shadow-2xs">
            <Plus className="w-3.5 h-3.5" />
          </div>
          <span>Adicionar Regra de Status Shopee</span>
        </button>
      </div>
    </div>
  );
};

export default ShopeeStatusRulesInput;
