import React, { useState, useEffect, useMemo } from 'react';
import { Trash2, Plus } from 'lucide-react';
import { IMaskInput } from 'react-imask';
import { SelectInput, MASKS, TextInput } from './InputFields';
import { CreatableSelectInput } from './CreatableSelectInput';

export const FORMAS_PAGAMENTO_OPTIONS = [
  { value: '01', label: '01 - Dinheiro' },
  { value: '02', label: '02 - Cheque' },
  { value: '03', label: '03 - Cartão de Crédito' },
  { value: '04', label: '04 - Cartão de Débito' },
  { value: '05', label: '05 - Crédito Loja' },
  { value: '10', label: '10 - Vale Alimentação' },
  { value: '11', label: '11 - Vale Refeição' },
  { value: '12', label: '12 - Vale Presente' },
  { value: '13', label: '13 - Vale Combustível' },
  { value: '14', label: '14 - Duplicata Mercantil' },
  { value: '15', label: '15 - Boleto Bancário' },
  { value: '16', label: '16 - Depósito Bancário' },
  { value: '17', label: '17 - PIX' },
  { value: '18', label: '18 - Débito em Conta' },
  { value: '90', label: '90 - Sem Pagamento' },
  { value: '99', label: '99 - Outros' },
];

export const PaymentMethodsInput = ({ field, value, onChange, formData, disabled }) => {
  const [items, setItems] = useState([]);

  useEffect(() => {
    let parsed = [];
    if (Array.isArray(value)) {
      parsed = value;
    } else if (typeof value === 'string' && value.trim()) {
      try {
        parsed = JSON.parse(value);
      } catch (e) {
        parsed = [];
      }
    }

    const initialValor = (formData?.total_desconto || formData?.total)
      ? Number(formData.total_desconto || formData.total)
      : '';

    if (parsed.length === 0 && (formData?.pagamento || formData?.caixa_destino_origem)) {
      const pagPadrao = typeof formData.pagamento === 'object' && formData.pagamento?.value
        ? formData.pagamento.value
        : (formData.pagamento || '01');

      parsed = [{
        pagamento: pagPadrao,
        caixa_destino_origem: formData.caixa_destino_origem || '',
        valor: initialValor,
        pagamento_descricao: formData.pagamento_descricao || '',
        ind_pag: 0
      }];
    } else if (parsed.length === 0) {
      parsed = [{
        pagamento: '17',
        caixa_destino_origem: '',
        valor: initialValor,
        pagamento_descricao: '',
        ind_pag: 0
      }];
    }

    setItems(parsed);
  }, [value]);

  const totalPedido = useMemo(() => {
    if (!formData) return 0;
    const totDesc = Number(formData.total_desconto);
    if (!isNaN(totDesc) && totDesc > 0) return totDesc;
    const totBruto = Number(formData.total);
    if (!isNaN(totBruto) && totBruto > 0) return totBruto;
    return 0;
  }, [formData?.total_desconto, formData?.total]);

  const totalPagamentos = useMemo(() => {
    return items.reduce((acc, curr) => acc + (Number(curr.valor) || 0), 0);
  }, [items]);

  const updateItems = (newItems) => {
    setItems(newItems);
    onChange({
      target: {
        name: field.name,
        value: newItems,
      },
    });
  };

  const handleAddItem = () => {
    const diff = totalPedido - totalPagamentos;
    const defaultValor = diff > 0 ? Number(diff.toFixed(2)) : '';
    const newItem = {
      pagamento: '17',
      caixa_destino_origem: '',
      valor: defaultValor,
      pagamento_descricao: '',
      ind_pag: 0,
    };
    updateItems([...items, newItem]);
  };

  const handleRemoveItem = (index) => {
    const newItems = items.filter((_, i) => i !== index);
    updateItems(newItems);
  };

  const handleChangeItem = (index, prop, val) => {
    const newItems = [...items];
    let updatedVal = val;

    if (prop === 'valor') {
      updatedVal = (val === '' || val === null || val === undefined) ? '' : (Number(val) || '');
    } else if (prop === 'pagamento') {
      const isPrazo = ['03', '05', '14', '15'].includes(val);
      newItems[index] = {
        ...newItems[index],
        pagamento: val,
        ind_pag: isPrazo ? 1 : 0
      };
      updateItems(newItems);
      return;
    }

    newItems[index] = { ...newItems[index], [prop]: updatedVal };
    updateItems(newItems);
  };

  return (
    <div className="md:col-span-3 space-y-3">
      {items.map((item, idx) => (
        <div key={idx} className="grid grid-cols-1 md:grid-cols-3 gap-x-6 gap-y-4 items-start">
          {/* Coluna 1: Forma de Pagamento */}
          <div>
            <SelectInput
              field={{
                name: 'pagamento',
                label: idx === 0 ? 'Forma de Pagamento' : '',
                placeholder: 'Selecione...'
              }}
              value={item.pagamento || '01'}
              options={FORMAS_PAGAMENTO_OPTIONS}
              onChange={(e) => handleChangeItem(idx, 'pagamento', e.target.value)}
              disabled={disabled}
            />
          </div>

          {/* Coluna 2: Conta Bancária / Caixa (CreatableSelectInput) */}
          <div>
            <CreatableSelectInput
              field={{
                name: 'caixa_destino_origem',
                label: idx === 0 ? 'Conta Bancária / Caixa' : '',
                placeholder: 'Ex: Banco Itaú'
              }}
              value={item.caixa_destino_origem || ''}
              onChange={(e) => handleChangeItem(idx, 'caixa_destino_origem', e.target.value)}
              modelName="pedidos"
              disabled={disabled}
            />
          </div>

          {/* Coluna 3: Valor (R$) (IMaskInput com Máscara de Moedas) */}
          <div className="flex flex-col">
            {idx === 0 && (
              <label className="mb-1.5 text-sm font-medium text-gray-700">
                Valor (R$)
              </label>
            )}
            <div className="flex items-center gap-2">
              <div className="flex-1">
                <IMaskInput
                  mask={MASKS['currency'].mask}
                  blocks={{
                    num: { ...MASKS['currency'].blocks.num, padFractionalZeros: true }
                  }}
                  lazy={MASKS['currency'].lazy}
                  value={item.valor !== undefined && item.valor !== null && item.valor !== '' && item.valor !== 0 ? String(item.valor).replace('.', ',') : ''}
                  unmask={true}
                  onAccept={(val, mask) => {
                    let rawVal = mask.unmaskedValue;
                    if (rawVal !== undefined && rawVal !== null && rawVal !== '') {
                      const parsed = parseFloat(String(rawVal).replace(',', '.'));
                      if (!isNaN(parsed) && parsed !== item.valor) {
                        handleChangeItem(idx, 'valor', parsed);
                      }
                    } else if (item.valor !== '') {
                      handleChangeItem(idx, 'valor', '');
                    }
                  }}
                  disabled={disabled}
                  className="w-full h-[38px] px-3 py-1.5 border border-gray-300 rounded-md shadow-2xs focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm text-gray-800 bg-white"
                  placeholder="0,00"
                />
              </div>
              {items.length > 1 && (
                <button
                  type="button"
                  onClick={() => handleRemoveItem(idx)}
                  disabled={disabled}
                  className="h-[38px] w-[38px] flex items-center justify-center text-gray-400 hover:text-red-600 transition-colors shrink-0"
                  title="Remover Forma de Pagamento"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>

          {/* Se for Outros (99) */}
          {item.pagamento === '99' && (
            <div className="col-span-3">
              <TextInput
                field={{
                  name: `pagamento_descricao_${idx}`,
                  label: 'Descrição do Pagamento (Outros)',
                  placeholder: 'Ex: Saldo em Conta, Vale-Presente'
                }}
                value={item.pagamento_descricao || ''}
                onChange={(e) => handleChangeItem(idx, 'pagamento_descricao', e.target.value)}
                disabled={disabled}
              />
            </div>
          )}
        </div>
      ))}

      <div className="pt-2">
        <button
          type="button"
          onClick={handleAddItem}
          disabled={disabled}
          className="w-full py-2.5 px-4 border border-dashed border-gray-300 hover:border-teal-600 bg-gray-50/60 hover:bg-teal-50/40 text-gray-600 hover:text-teal-700 rounded-md text-xs font-semibold flex items-center justify-center gap-2 transition-all shadow-2xs group disabled:opacity-50"
        >
          <div className="p-1 rounded bg-white group-hover:bg-teal-600 text-gray-500 group-hover:text-white border border-gray-200 group-hover:border-teal-600 transition-colors shadow-2xs">
            <Plus className="w-3.5 h-3.5" />
          </div>
          <span>Adicionar Forma de Pagamento</span>
        </button>
      </div>
    </div>
  );
};

export default PaymentMethodsInput;
