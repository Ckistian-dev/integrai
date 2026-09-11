import React, { useState, useEffect, useMemo } from 'react';
import Select from 'react-select';
import { Link, HelpCircle } from 'lucide-react';
import api from '../../api/axiosConfig';

export const OrderFieldSelectInput = ({ field, value, onChange, disabled, error }) => {
  const { name, label, placeholder } = field || {};
  const [pedidoColumns, setPedidoColumns] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get('/metadata/pedidos')
      .then(res => {
        const rawFields = (res.data?.fields || [])
          .filter(f => f.visible !== false && f.name !== 'id');

        // Campos recomendados que frequentemente armazenam links ou códigos de rastreio
        const priorityFields = [
          'intelipost_tracking_url',
          'intelipost_tracking_code',
          'numero_nf',
          'chave_acesso',
          'observacao',
          'observacoes_nf',
          'meli_tracking_number',
          'shopee_tracking_number'
        ];

        const formatted = rawFields.map(f => {
          const isPriority = priorityFields.includes(f.name);
          return {
            value: f.name,
            label: `${f.label || f.name} (${f.name})`,
            rawLabel: f.label || f.name,
            name: f.name,
            isPriority
          };
        });

        // Ordena colocando os prioritários no topo e o restante em ordem alfabética
        formatted.sort((a, b) => {
          if (a.isPriority && !b.isPriority) return -1;
          if (!a.isPriority && b.isPriority) return 1;
          return a.rawLabel.localeCompare(b.rawLabel);
        });

        setPedidoColumns(formatted);
      })
      .catch(err => {
        console.error('Erro ao carregar colunas de pedidos:', err);
        setPedidoColumns([]);
      })
      .finally(() => setLoading(false));
  }, []);

  const selectedOption = useMemo(() => {
    if (!value) return null;
    const found = pedidoColumns.find(col => col.value === value);
    if (found) return found;
    return { value, label: `${value} (${value})` };
  }, [value, pedidoColumns]);

  const handleSelectChange = (opt) => {
    const newValue = opt ? opt.value : null;
    onChange({
      target: {
        name: name || 'campo_link_rastreio',
        value: newValue
      }
    });
  };

  return (
    <div className="flex flex-col space-y-1.5 w-full">
      <div className="flex items-center justify-between">
        <label className="text-sm font-medium text-gray-700 flex items-center gap-1.5">
          <Link className="w-4 h-4 text-blue-600" />
          <span>{label || 'Campo do Link de Rastreio (Tabela Pedidos)'}</span>
        </label>
      </div>

      <Select
        value={selectedOption}
        onChange={handleSelectChange}
        options={pedidoColumns}
        isDisabled={disabled || loading}
        isLoading={loading}
        isClearable
        placeholder={loading ? 'Carregando colunas...' : (placeholder || 'Selecione a coluna que contém o link de rastreio...')}
        noOptionsMessage={() => 'Nenhuma coluna encontrada'}
        menuPortalTarget={document.body}
        styles={{
          control: (base, state) => ({
            ...base,
            minHeight: '38px',
            height: '38px',
            borderColor: error ? '#ef4444' : state.isFocused ? '#3b82f6' : '#d1d5db',
            boxShadow: state.isFocused ? '0 0 0 2px rgba(59,130,246,0.2)' : 'var(--tw-shadow, 0 1px 2px 0 rgb(0 0 0 / .05))',
            fontSize: '0.875rem',
            backgroundColor: disabled ? '#f9fafb' : '#fff',
            '&:hover': {
              borderColor: error ? '#ef4444' : '#9ca3af'
            }
          }),
          valueContainer: (base) => ({ ...base, padding: '0 12px', flexWrap: 'nowrap' }),
          singleValue: (base) => ({ ...base, color: '#1f2937' }),
          indicatorsContainer: (base) => ({ ...base, height: '38px' }),
          menuPortal: (base) => ({ ...base, zIndex: 9999 }),
        }}
      />

      <div className="flex items-start gap-1.5 text-xs text-gray-500 pt-0.5">
        <HelpCircle className="w-3.5 h-3.5 text-gray-400 shrink-0 mt-0.5" />
        <span>
          Sempre que esta coluna for preenchida ou alterada em um pedido do ERP, o sistema transmitirá automaticamente o link/código para a plataforma correspondente.
        </span>
      </div>

      {error && <span className="text-xs text-red-500">{error}</span>}
    </div>
  );
};

export default OrderFieldSelectInput;
