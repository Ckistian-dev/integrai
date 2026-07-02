import React, { useState, useEffect } from 'react';
import { Eye, EyeOff, Trash2, ChevronDown, ChevronUp, CheckCircle2, Upload, Download, Info } from 'lucide-react';
import AsyncSelect from 'react-select/async';
import Select from 'react-select';
import api from '../../api/axiosConfig';

import IMask from 'imask';
import { IMaskMixin, IMaskInput } from 'react-imask';


export const MASKS = {
  'cep': '00000-000',
  'ncm': '0000.00.00',
  // Adicione 'cnpj' apontando para a mesma estrutura do 'cnpj_cpf' para garantir
  'cnpj': [
    { mask: '000.000.000-00' },
    {
      mask: 'XX.XXX.XXX/XXXX-00',
      definitions: {
        'X': /[0-9a-zA-Z]/
      },
      prepareChar: (str) => str.toUpperCase()
    }
  ],
  'cnpj_cpf': [
    { mask: '000.000.000-00' },
    {
      mask: 'XX.XXX.XXX/XXXX-00',
      definitions: {
        'X': /[0-9a-zA-Z]/
      },
      prepareChar: (str) => str.toUpperCase()
    }
  ],
  'phone': [
    { mask: '(00) 0000-0000' },
    { mask: '(00) 0 0000-0000' },
  ],
  // Máscara de moeda (Numeric)
  'currency': {
    mask: 'R$ num',
    lazy: true, // Exibe a máscara (R$ __,__) imediatamente
    blocks: {
      num: {
        mask: Number,
        thousandsSeparator: '.',
        radix: ',',
        mapToRadix: ['.'],
        scale: 2,
        padFractionalZeros: false,
        normalizeZeros: false,
        autofix: true,
      }
    }
  },
  // Máscara de percentual (Numeric)
  'percent:2': {
    mask: Number,
    thousandsSeparator: '.',
    radix: ',',
    mapToRadix: ['.'],
    scale: 2,
    suffix: ' %',
    padFractionalZeros: false,
    normalizeZeros: false,
    lazy: false,
    autofix: true,
    min: 0,
    max: 999.99,
  },
  // Máscara decimal com 3 casas (Numeric)
  'decimal:3': {
    mask: Number,
    thousandsSeparator: '.',
    radix: ',',
    mapToRadix: ['.'],
    scale: 3,
    padFractionalZeros: false,
    normalizeZeros: false,
    lazy: false,
    autofix: true,
  },
  // Máscara decimal com 2 casas (Numeric) - Sem R$
  'decimal:2': {
    mask: Number,
    thousandsSeparator: '.',
    radix: ',',
    mapToRadix: ['.'],
    scale: 2,
    padFractionalZeros: false,
    normalizeZeros: false,
    lazy: false,
    autofix: true,
  }
};

/**
 * Formata o texto de uma opção de dropdown:
 */
const formatLabel = (text) => {
  if (!text) return '';

  // 1. Substitui _ por espaço e converte para minúsculas
  const withSpaces = text.toLowerCase().replace(/_/g, ' ');

  // 2. Capitaliza a primeira letra de cada palavra
  return withSpaces.split(' ')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
};


/** * Componente de Input de Texto genérico * Adapta-se para text, email, number. * AGORA USAMOS React.forwardRef */
export const TextInput = React.forwardRef(({
  field,
  error,
  // Captura o inputRef que o IMask passa
  inputRef,
  // ⚠️ Desestruture e ignore as props de configuração do IMask ⚠️
  mask,
  radix,
  thousandsSeparator,
  mapToRadix,
  scale,
  padFractionalZeros,
  normalizeZeros,
  lazy,
  suffix,
  // Captura todas as outras props (inclui value, onChange, onAccept, onComplete, etc.)
  ...inputProps
}, ref) => {

  // Props específicas dos metadados
  const { label, name, type, required, placeholder, format_mask } = field;

  // Acessa o ref que o IMaskInput espera: inputRef (do IMask) ou ref (do forwardRef padrão)
  const finalRef = inputRef || ref;

  // Se o tipo for 'number' e NÃO houver máscara, usa type='number' (para teclado móvel).
  // Se tiver máscara (format_mask), usamos 'text', pois o IMask gerencia a entrada.
  const inputType = (type === 'number' && !format_mask) ? 'number' : 'text';

  // ************ CORREÇÃO PARA ATRIBUTOS INVÁLIDOS E WARNINGS ************
  // Lista de props do IMask e outras customizadas que NÃO devem ir para o DOM <input>
  const invalidDomProps = [
    'modelName', 'unmaskedValue', 'mask', 'radix', 'thousandsSeparator',
    'mapToRadix', 'scale', 'padFractionalZeros', 'normalizeZeros', 'typedValue',
    'lazy', 'suffix', 'blocks', 'autofix', 'definitions', 'overwrite'
  ];

  // Filtra as props para remover chaves numéricas (do IMask dynamic) e props inválidas
  const filteredInputProps = Object.keys(inputProps).reduce((acc, key) => {
    if (!/^\d+$/.test(key) && !invalidDomProps.includes(key)) {
      acc[key] = inputProps[key];
    }
    return acc;
  }, {});

  return (
    <div className="flex flex-col">
      <label htmlFor={name} className="mb-1.5 text-sm font-medium text-gray-700">
        {label} {required && <span className="text-red-500">*</span>}
      </label>
      <input
        type={inputType}
        id={name}
        name={name}
        autoComplete="off"
        ref={finalRef} // <--- AQUI É O PULO DO GATO. Sem isso, o IMask não funciona.
        required={required}
        placeholder={placeholder || `Digite ${label.toLowerCase()}...`}
        className={`w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 
                            focus:outline-none focus:ring-blue-500 focus:border-blue-500
                            ${error ? 'border-red-500' : ''}`}
        {...filteredInputProps}
      />
      {error && <span className="mt-1 text-xs text-red-500">{error}</span>}
    </div>
  );
});

/** * Componente de TextArea * Para campos de texto longo. */
export const TextAreaInput = ({ field, value, onChange, error, modelName, ...props }) => {
  const { label, name, required, placeholder } = field;

  return (
    <div className="flex flex-col">
      <label htmlFor={name} className="mb-1.5 text-sm font-medium text-gray-700">
        {label} {required && <span className="text-red-500">*</span>}
      </label>
      <textarea
        id={name}
        name={name}
        autoComplete="off"
        value={value || ''}
        onChange={onChange}
        required={required}
        placeholder={placeholder || `Digite ${label.toLowerCase()}...`}
        rows={5}
        className={`w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 
                    focus:outline-none focus:ring-blue-500 focus:border-blue-500
                    ${error ? 'border-red-500' : ''}`}
        {...props}
      />
      {error && <span className="mt-1 text-xs text-red-500">{error}</span>}
    </div>
  );
};


/** * Componente Wrapper para o input mascarado. * Ele herda todas as props do TextInput, mas adiciona a funcionalidade de máscara. */
export const MaskedInput = IMaskMixin(TextInput);


/** * Componente de Input Booleano (Dropdown Sim/Não) * Renderiza como um <select> com opções "Sim" e "Não". */
export const BooleanInput = ({ field, value, onChange, error, modelName, ...props }) => {
  // ... (restante do código)
  const { label, name, required } = field;

  // 🎯 Lógica para determinar as labels (Ativo/Inativo vs Sim/Não)
  const isSituacaoField = name.toLowerCase().includes('situacao');

  const trueLabel = isSituacaoField ? 'Ativo' : 'Sim';
  const falseLabel = isSituacaoField ? 'Inativo' : 'Não';


  const getStringValue = (boolValue) => {

    // 🎯 CORREÇÃO AQUI:
    // Compara tanto o booleano quanto a string.

    if (boolValue === true || boolValue === 'true') {
      return 'true';
    }
    if (boolValue === false || boolValue === 'false') {
      return 'false';
    }

    return ''; // Para 'null', 'undefined', etc.
  };

  // Handler customizado para converter a string do <select> de volta para booleano
  const handleChange = (e) => {
    const stringValue = e.target.value;
    let booleanValue;

    if (stringValue === 'true') {
      booleanValue = true;
    } else if (stringValue === 'false') {
      booleanValue = false;
    } else {
      booleanValue = null; // Representa o "Selecione..." (campo não preenchido)
    }

    // Simula o evento onChange com o nome e o valor booleano/null
    onChange({
      target: {
        name: name,
        value: booleanValue,
      },
    });
  };

  return (
    <div className="flex flex-col">
      <label htmlFor={name} className="mb-1.5 text-sm font-medium text-gray-700">
        {label} {required && <span className="text-red-500">*</span>}
      </label>
      <select
        id={name}
        name={name}
        value={getStringValue(value)} // Usa o valor string convertido
        onChange={handleChange}      // Usa o handler customizado
        required={required}
        className={`w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm 
                            focus:outline-none focus:ring-blue-500 focus:border-blue-500
                            ${error ? 'border-red-500' : ''}`}
        {...props}
      >
        <option value="" disabled={required}>
          Selecione...
        </option>
        {/* Usando as labels dinâmicas */}
        <option value="true">{trueLabel}</option>
        <option value="false">{falseLabel}</option>
      </select>
      {error && <span className="mt-1 text-xs text-red-500">{error}</span>}
    </div>
  );
};

/**
 * Componente para gerenciar itens de pedido (Produto + Quantidade)
 * Armazena como JSON: [{ id_produto: 1, quantidade: 10 }, ...]
 */
export const OrderItemsInput = ({ field, value, onChange, error, formData }) => {
  const { label, name, required } = field;
  // Garante que items seja um array
  const items = Array.isArray(value) ? value : [];

  const isComplemento = formData?.tipo_operacao === 'complemento' || formData?.tipo_operacao === 'Complementar';

  const [expandedItems, setExpandedItems] = useState({});
  const toggleExpand = (index) => {
    setExpandedItems(prev => ({ ...prev, [index]: !prev[index] }));
  };

  const calculateTotals = (item) => {
    if (isComplemento) {
      return item;
    }
    const qtd = Number(item.quantidade || 0);
    const unitPrice = Number(item.valor_unitario || 0);
    const ipiRate = Number(item.ipi_aliquota || 0);

    const subtotal = qtd * unitPrice;
    const ipiValue = subtotal * (ipiRate / 100);

    return {
      ...item,
      valor_ipi: parseFloat(ipiValue.toFixed(2)),
      total_com_ipi: parseFloat((subtotal + ipiValue).toFixed(2))
    };
  };

  const calculateFromTotal = (item) => {
    if (isComplemento) {
      return item;
    }
    const totalWithIpi = Number(item.total_com_ipi || 0);
    const qtd = Number(item.quantidade || 0);
    const ipiRate = Number(item.ipi_aliquota || 0);

    if (qtd <= 0) return item;

    const factor = 1 + (ipiRate / 100);
    let unitPrice = totalWithIpi / (qtd * factor);

    // Arredonda para 2 casas para manter consistência
    unitPrice = parseFloat(unitPrice.toFixed(2));

    // Recalcula para frente para garantir consistência contábil (Unit * Qtd = Total)
    const subtotal = qtd * unitPrice;
    const ipiValue = subtotal * (ipiRate / 100);
    const newTotal = subtotal + ipiValue;

    return {
      ...item,
      valor_unitario: unitPrice,
      valor_ipi: parseFloat(ipiValue.toFixed(2)),
      total_com_ipi: parseFloat(newTotal.toFixed(2))
    };
  };

  const handleAddItem = () => {
    const newItem = calculateTotals({ id_produto: null, quantidade: 1, valor_unitario: 0, ipi_aliquota: 0 });
    const newItems = [...items, newItem];
    triggerChange(newItems);
  };

  const handleRemoveItem = (index) => {
    const newItems = items.filter((_, i) => i !== index);
    triggerChange(newItems);
  };

  const handleItemChange = (index, key, val) => {
    const newItems = [...items];
    let item = { ...newItems[index], [key]: val };

    if (key === 'total_com_ipi') {
      item = calculateFromTotal(item);
    } else {
      item = calculateTotals(item);
    }

    newItems[index] = item;
    triggerChange(newItems);
  };

  const handleProductChange = (index, option) => {
    const newItems = [...items];
    const product = option ? option.original : null;

    let item = {
      ...newItems[index],
      id_produto: option ? option.value : null,
      sku: product ? product.sku : '',
      descricao: product ? product.descricao : '',
      valor_unitario: product ? Number(product.preco) : 0,
      peso: product ? Number(product.peso) : 0,
      ipi_aliquota: product ? Number(product.ipi_aliquota) : 0
    };

    item = calculateTotals(item);
    newItems[index] = item;
    triggerChange(newItems);
  };

  const triggerChange = (newItems) => {
    onChange({
      target: {
        name: name,
        value: newItems
      }
    });
  };

  return (
    <div className="flex flex-col space-y-3 md:col-span-2">
      <label className="text-sm font-medium text-gray-700">
        {label} {required && <span className="text-red-500">*</span>}
      </label>

      {isComplemento && (
        <div className="bg-teal-50 border-l-4 border-teal-600 p-4 rounded-r-lg shadow-sm space-y-2 mb-2 animate-fade-in">
          <div className="flex items-center gap-2 text-teal-800 font-bold text-sm">
            <Info className="w-5 h-5 text-teal-600 shrink-0" />
            <span>Guia Rápido: Nota Fiscal Complementar (NFe)</span>
          </div>
          <div className="text-teal-950 text-xs leading-relaxed space-y-1.5">
            <p>
              Esta é uma <strong>Nota Fiscal Complementar (Finalidade 2)</strong>. Ela serve unicamente para acrescentar valores, quantidades ou tributos que foram declarados a menor na nota original.
            </p>
            <ul className="list-disc list-inside space-y-1.5 pl-1 pt-1 font-medium text-teal-850">
              <li>
                <strong className="text-teal-950">Apenas os itens complementados:</strong>
                Remova os produtos que não sofreram nenhuma alteração clicando na lixeira vermelha (<Trash2 className="w-3.5 h-3.5 inline text-red-500" />). A nota <strong>não</strong> deve duplicar a original inteira, sob risco de duplicar as vendas e impostos!
              </li>
              <li>
                <strong className="text-teal-950">Diferença de Preço ou Quantidade:</strong>
                Se o preço ou quantidade estavam menores na nota original, informe apenas a <strong>diferença</strong> neste rascunho.
              </li>
              <li>
                <strong className="text-teal-950">Cálculo Automático de Impostos:</strong>
                Os impostos (ICMS, IPI, PIS, COFINS) serão calculados automaticamente pelo sistema com base nas regras cadastradas na tabela de **Regras Tributárias** para a operação "Complementar".
              </li>
            </ul>
          </div>
        </div>
      )}

      <div className="space-y-4">
        {items.map((item, index) => (
          <div key={index} className="border border-gray-200 rounded-lg p-3 bg-white space-y-3 shadow-sm hover:shadow-md transition-shadow">
            <div className="flex flex-col md:flex-row gap-2 items-start md:items-center">
              <div className="flex-grow w-full md:w-auto">
                <AsyncProductSelect
                  value={item.id_produto}
                  onChange={(opt) => handleProductChange(index, opt)}
                  error={!item.id_produto && error} // Visual simples de erro
                />
              </div>

              <div className="flex gap-2 w-full md:w-auto">
                <div className="w-1/2 md:w-20">
                  <input
                    type="number"
                    value={item.quantidade}
                    onChange={(e) => handleItemChange(index, 'quantidade', e.target.value === '' ? '' : Number(e.target.value))}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-center"
                    placeholder="Qtd"
                    min={isComplemento ? "0" : "1"}
                  />
                </div>
                <div className="w-1/2 md:w-28">
                  <IMaskInput
                    mask={MASKS['currency'].mask}
                    blocks={{
                      num: { ...MASKS['currency'].blocks.num, padFractionalZeros: true }
                    }}
                    lazy={MASKS['currency'].lazy}
                    value={String(item.valor_unitario ?? '')}
                    unmask={true}
                    onAccept={(value, mask) => handleItemChange(index, 'valor_unitario', mask.unmaskedValue)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-right"
                    placeholder="Valor Unit."
                  />
                </div>
              </div>

              <div className="flex gap-2 w-full md:w-auto items-center justify-between md:justify-end">
                <div className="w-1/2 md:w-24 px-3 py-2 bg-gray-100 border border-gray-200 rounded-md text-right text-sm text-gray-700" title={`Alíquota: ${item.ipi_aliquota || 0}%`}>
                  <span className="text-xs text-gray-500 mr-2">IPI:</span>
                  {Number(item.valor_ipi || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
                </div>
                <div className="w-1/2 md:w-28">
                  <IMaskInput
                    mask={MASKS['currency'].mask}
                    blocks={{
                      num: { ...MASKS['currency'].blocks.num, padFractionalZeros: true }
                    }}
                    lazy={MASKS['currency'].lazy}
                    value={String(item.total_com_ipi ?? '')}
                    unmask={true}
                    onAccept={(value, mask) => handleItemChange(index, 'total_com_ipi', mask.unmaskedValue)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-right font-semibold text-gray-800"
                    placeholder="Total"
                  />
                </div>
              </div>

              <div className="flex gap-1.5 self-end md:self-center">
                <button
                  type="button"
                  onClick={() => handleRemoveItem(index)}
                  className="p-2 text-red-500 hover:text-red-700 bg-red-50 hover:bg-red-100 rounded-md border border-red-100 transition-colors"
                  title="Remover item"
                >
                  <Trash2 className="w-5 h-5" />
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      <button
        type="button"
        onClick={handleAddItem}
        className="flex items-center justify-center px-4 py-2.5 text-sm font-semibold text-blue-600 bg-blue-50 hover:bg-blue-100 rounded-md border-2 border-blue-200 border-dashed transition-colors duration-150"
      >
        + Adicionar Item
      </button>

      {error && <span className="mt-1 text-xs text-red-500">{error}</span>}
    </div>
  );
};

const AsyncProductSelect = ({ value, onChange }) => {
  const [selectedOption, setSelectedOption] = useState(null);

  const loadOptions = (inputValue, callback) => {
    api.get(`/generic/produtos`, {
      params: { search_term: inputValue, limit: 1000, situacao: 'true' }
    }).then(response => {
      const options = response.data.items.map(item => ({
        value: item.id,
        label: item.descricao,
        original: item
      }));
      callback(options);
    }).catch(() => callback([]));
  };

  useEffect(() => {
    if (value && (!selectedOption || selectedOption.value !== value)) {
      api.get(`/generic/produtos/${value}`)
        .then(response => {
          const item = response.data;
          setSelectedOption({ value: item.id, label: item.descricao, original: item });
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
        onChange(opt);
      }}
      autoComplete="off"
      placeholder="Buscar produto..."
      menuPortalTarget={document.body}
      styles={{
        control: (base) => ({ ...base, minHeight: '42px', borderColor: '#d1d5db' }),
        menu: (base) => ({ ...base, zIndex: 9999 }),
        menuPortal: (base) => ({ ...base, zIndex: 9999 })
      }}
    />
  );
};

/** * Componente de Select (Dropdown) */
export const SelectInput = ({ field, value, onChange, error, options = [], modelName, ...props }) => {
  const { label, name, required } = field;

  const handleChange = (e) => {
    const val = e.target.value;
    onChange({
      target: {
        name: name,
        value: val === '' ? null : val,
      },
    });
  };

  return (
    <div className="flex flex-col">
      <label htmlFor={name} className="mb-1.5 text-sm font-medium text-gray-700">
        {label} {required && <span className="text-red-500">*</span>}
      </label>
      <select
        id={name}
        name={name}
        autoComplete="off"
        value={value || ''}
        onChange={handleChange}
        required={required}
        className={`w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm 
                            focus:outline-none focus:ring-blue-500 focus:border-blue-500
                            ${error ? 'border-red-500' : ''}`}
        {...props}
      >
        <option value="" disabled={required}>Selecione...</option>
        {(options || []).map((option) => (
          <option key={option.value} value={option.value}>
            {formatLabel(option.label || option.value)}
          </option>
        ))}
      </select>
      {error && <span className="mt-1 text-xs text-red-500">{error}</span>}
    </div>
  );
};

/** * Componente de MultiSelect (Dropdown com múltipla seleção) */
export const MultiSelectInput = ({ field, value, onChange, error, options = [], modelName, ...props }) => {
  const { label, name, required } = field;

  // Garante que value seja um array
  const selectedValues = Array.isArray(value) ? value : [];

  // Mapeia os valores selecionados para objetos {label, value} que o react-select entende
  const selectedOptions = options.filter(opt => selectedValues.includes(opt.value));

  const handleChange = (selected) => {
    // selected é um array de objetos [{label, value}, ...] ou null
    const newValues = selected ? selected.map(opt => opt.value) : [];

    onChange({
      target: {
        name: name,
        value: newValues
      }
    });
  };

  return (
    <div className="flex flex-col">
      <label htmlFor={name} className="mb-1.5 text-sm font-medium text-gray-700">
        {label} {required && <span className="text-red-500">*</span>}
      </label>
      <Select
        isMulti
        name={name}
        autoComplete="off"
        closeMenuOnSelect={false}
        options={options}
        value={selectedOptions}
        onChange={handleChange}
        placeholder="Selecione..."
        className="basic-multi-select"
        classNamePrefix="select"
        menuPortalTarget={document.body}
        styles={{
          menuPortal: (base) => ({ ...base, zIndex: 9999 }),
          control: (base, state) => ({
            ...base,
            borderColor: error ? '#ef4444' : (state.isFocused ? '#3b82f6' : '#d1d5db'),
            boxShadow: state.isFocused ? '0 0 0 1px #3b82f6' : '0 1px 2px 0 rgb(0 0 0 / 0.05)',
            '&:hover': {
              borderColor: state.isFocused ? '#3b82f6' : '#d1d5db'
            },
          }),
        }}
        {...props}
      />
      {error && <span className="mt-1 text-xs text-red-500">{error}</span>}
    </div>
  );
};

/**
 * Componente para construir filtros padrão dinâmicos (ex: Magento)
 * Armazena: [{ field: 'status', value: ['pending'] }, ...]
 */
export const DefaultFiltersInput = ({ field, value: activeFilters = [], onChange, error, options = [] }) => {
  const { label, name, required } = field;
  const [expandedField, setExpandedField] = useState(null);

  // Garante que activeFilters seja sempre um array
  const filters = Array.isArray(activeFilters) ? activeFilters : [];
  const availableFields = options || [];

  const handleFilterChange = (fieldName, newValue) => {
    let newFilters = [...filters];
    const existingIndex = newFilters.findIndex(f => f.field === fieldName);

    if (newValue === null || newValue === '' || (Array.isArray(newValue) && newValue.length === 0)) {
      // Remove o filtro se o valor for limpo
      newFilters = newFilters.filter(f => f.field !== fieldName);
    } else {
      if (existingIndex >= 0) {
        newFilters[existingIndex] = { ...newFilters[existingIndex], value: newValue };
      } else {
        newFilters.push({ field: fieldName, value: newValue });
      }
    }

    onChange({ target: { name, value: newFilters } });
  };

  const renderValueInput = (fieldConfig) => {
    const currentFilter = filters.find(f => f.field === fieldConfig.value);
    const currentValue = currentFilter ? currentFilter.value : '';

    const commonClasses = "w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none";

    // Multi-seleção (ex: Status do Pedido)
    if (fieldConfig.type === 'multiselect') {
      const selectOptions = fieldConfig.options || [];
      const selectedValues = Array.isArray(currentValue)
        ? currentValue.map(v => selectOptions.find(o => o.value === v) || { value: v, label: v })
        : [];

      return (
        <div className="space-y-2">
          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => handleFilterChange(fieldConfig.value, selectOptions.map(o => o.value))}
              className="text-[10px] uppercase tracking-wider text-blue-600 hover:text-blue-800 font-bold"
            >
              Selecionar Todos
            </button>
          </div>
          <Select
            isMulti
            options={selectOptions}
            closeMenuOnSelect={false}
            value={selectedValues}
            onChange={(opts) => handleFilterChange(fieldConfig.value, opts ? opts.map(o => o.value) : [])}
            placeholder="Selecione os itens..."
            className="text-sm"
            menuPortalTarget={document.body}
            styles={{ menuPortal: base => ({ ...base, zIndex: 9999 }) }}
          />
        </div>
      );
    }

    // Data
    if (fieldConfig.type === 'date') {
      return (
        <input
          type="date"
          autoComplete="off"
          value={currentValue}
          onChange={(e) => handleFilterChange(fieldConfig.value, e.target.value)}
          className={commonClasses}
        />
      );
    }

    // Texto ou Número padrão
    return (
      <input
        type={fieldConfig.type === 'number' ? 'number' : 'text'}
        autoComplete="off"
        value={currentValue}
        onChange={(e) => handleFilterChange(fieldConfig.value, e.target.value)}
        placeholder={`Filtrar por ${fieldConfig.label.toLowerCase()}...`}
        className={commonClasses}
      />
    );
  };

  return (
    <div className="flex flex-col space-y-3 md:col-span-2">
      <div className="flex items-center justify-between">
        <label className="text-sm font-medium text-gray-700">
          {label} {required && <span className="text-red-500">*</span>}
        </label>
        <button
          type="button"
          onClick={() => onChange({ target: { name, value: [] } })}
          className="text-xs text-red-600 hover:text-red-800 font-bold uppercase tracking-wider"
        >
          Limpar Filtros
        </button>
      </div>

      <div className="space-y-2 max-h-[50vh] overflow-y-auto pr-2 custom-scrollbar border rounded-lg p-2 bg-gray-50/30">
        {availableFields.map((f) => {
          const isExpanded = expandedField === f.value;
          const currentFilter = filters.find(filter => filter.field === f.value);
          const hasActiveFilter = !!currentFilter;

          return (
            <div key={f.value} className={`border rounded-lg transition-all bg-white ${hasActiveFilter ? 'border-blue-200 shadow-sm' : 'border-gray-200'}`}>
              <button
                type="button"
                onClick={() => setExpandedField(isExpanded ? null : f.value)}
                className="w-full flex items-center justify-between p-3 text-left"
              >
                <div className="flex items-center gap-3">
                  <span className={`text-sm font-semibold ${hasActiveFilter ? 'text-blue-700' : 'text-gray-700'}`}>
                    {f.label}
                    {hasActiveFilter && f.type === 'multiselect' && Array.isArray(currentFilter.value) && (
                      <span className="ml-2 text-xs font-normal text-blue-500">
                        ({currentFilter.value.length})
                      </span>
                    )}
                  </span>
                  {hasActiveFilter && <CheckCircle2 size={14} className="text-blue-500" />}
                </div>
                {isExpanded ? <ChevronUp size={16} className="text-gray-400" /> : <ChevronDown size={16} className="text-gray-400" />}
              </button>

              {isExpanded && (
                <div className="px-3 pb-3 pt-0 animate-fade-in">
                  {renderValueInput(f)}
                </div>
              )}
            </div>
          );
        })}
        {availableFields.length === 0 && (
          <div className="text-center py-6 text-gray-500 text-sm">
            Nenhum filtro disponível para configuração.
          </div>
        )}
      </div>
      {error && <span className="mt-1 text-xs text-red-500">{error}</span>}
    </div>
  );
};


/** * Componente de Select Assíncrono com busca (para Foreign Keys) * Usa react-select/async */
export const AsyncSelectInput = ({ field, value, onChange, error, modelName, formData, ...props }) => {
  const { label, name, required, foreign_key_model, foreign_key_label_field } = field;

  // Estado para o objeto de seleção { value, label } e para o carregamento inicial
  const [selectedOption, setSelectedOption] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  // Helper para formatar o label (Exibe Fantasia junto com Razão Social para Cadastros)
  const getOptionLabel = (item) => {
    if (foreign_key_model === 'cadastros') {
      const razao = item.nome_razao || '';
      const fantasia = item.fantasia;
      if (fantasia && fantasia.trim() !== '' && fantasia !== razao) {
        return `${razao} (${fantasia})`;
      }
      return razao;
    }
    return item[foreign_key_label_field] || `ID ${item.id}`;
  };

  // 1. Função para carregar opções (busca)
  const loadOptions = (inputValue, callback) => {
    if (!foreign_key_model || !foreign_key_label_field) return callback([]);

    // Filtros automáticos baseados no nome do campo para Cadastros
    const filters = [];
    if (foreign_key_model === 'cadastros') {
      if (name === 'id_vendedor' || name === 'vendedor') {
        filters.push({ field: 'tipo_cadastro', operator: 'equals', value: 'vendedor' });
      } else if (name === 'id_transportadora' || name === 'transportadora') {
        filters.push({ field: 'tipo_cadastro', operator: 'equals', value: 'transportadora' });
      } else if (name === 'id_cliente' || name === 'cliente') {
        filters.push({ field: 'tipo_cadastro', operator: 'equals', value: 'cliente' });
      } else if (name === 'id_fornecedor' || name === 'fornecedor') {
        // No módulo de Contas, permitimos selecionar qualquer cadastro (Fornecedor, Cliente, Transportadora)
        if (modelName !== 'contas') {
          filters.push({ field: 'tipo_cadastro', operator: 'equals', value: 'fornecedor' });
        }
      }
    }

    // Filtro dinâmico para Plano de Contas baseado no Tipo de Conta (Pagar/Receber)
    if (foreign_key_model === 'classificacao_contabil' && modelName === 'contas') {
      const tipoConta = formData?.tipo_conta;
      if (tipoConta === 'A Receber') {
        filters.push({ field: 'tipo_movimentacao', operator: 'equals', value: 'Entrada' });
      } else if (tipoConta === 'A Pagar') {
        filters.push({ field: 'tipo_movimentacao', operator: 'neq', value: 'Entrada' });
      }
    }

    const params = {
      search_term: inputValue,
      limit: 1000
    };

    if (filters.length > 0) {
      params.filters = JSON.stringify(filters);
    }

    api.get(`/generic/${foreign_key_model}`, {
      params
    }).then(response => {
      const options = response.data.items.map(item => ({
        value: item.id,
        label: getOptionLabel(item)
      }));
      callback(options);
    }).catch(() => {
      callback([]);
    });
  };

  // 2. Efeito para carregar o label do valor inicial (quando 'value' é um ID)
  useEffect(() => {
    // Se temos um ID (value), mas ainda não temos o objeto de seleção correspondente
    if (value && (!selectedOption || selectedOption.value !== value)) {
      setIsLoading(true);
      api.get(`/generic/${foreign_key_model}/${value}`)
        .then(response => {
          const item = response.data;
          const fetchedLabel = getOptionLabel(item);
          setSelectedOption({ value: value, label: fetchedLabel });
        })
        .catch(() => {
          setSelectedOption({ value: value, label: `ID ${value} (Não encontrado)` });
        })
        .finally(() => {
          setIsLoading(false);
        });
    } else if (!value && selectedOption) {
      // Se o valor for limpo externamente (ex: formulário resetado), limpa nosso estado
      setSelectedOption(null);
    }
  }, [value, foreign_key_model, foreign_key_label_field]); // Depende apenas do ID vindo de fora

  // 3. Handler para quando o usuário seleciona um item
  const handleChange = (newlySelectedOption) => {
    // O react-select nos dá o objeto { value, label } ou null
    setSelectedOption(newlySelectedOption);

    // Simula o evento onChange que o GenericForm espera
    onChange({
      target: {
        name: name,
        value: newlySelectedOption ? newlySelectedOption.value : null, // Envia apenas o ID
      },
    });
  };

  // 5. Estilização (básica, para combinar com os outros inputs)
  const customStyles = {
    control: (provided, state) => ({
      ...provided,
      minHeight: '42px', // Altura similar aos outros inputs
      borderColor: error ? '#ef4444' : (state.isFocused ? '#3b82f6' : '#d1d5db'),
      boxShadow: state.isFocused ? '0 0 0 1px #3b82f6' : '0 1px 2px 0 rgb(0 0 0 / 0.05)',
      '&:hover': {
        borderColor: state.isFocused ? '#3b82f6' : '#d1d5db'
      },
    }),
    menu: (provided) => ({
      ...provided,
      zIndex: 20 // Garante que o dropdown fique sobre outros campos
    }),
    menuPortal: (base) => ({ ...base, zIndex: 9999 })
  };

  return (
    <div className="flex flex-col">
      <label htmlFor={name} className="mb-1.5 text-sm font-medium text-gray-700">
        {label} {required && <span className="text-red-500">*</span>}
      </label>
      <AsyncSelect
        id={name}
        name={name}
        autoComplete="off"
        cacheOptions
        defaultOptions // Carrega opções vazias no início
        loadOptions={loadOptions}
        value={selectedOption}
        onChange={handleChange}
        placeholder="Digite para buscar..."
        noOptionsMessage={({ inputValue }) =>
          inputValue ? "Nenhum resultado encontrado" : "Digite para buscar"
        }
        menuPortalTarget={document.body}
        loadingMessage={() => "Buscando..."}
        isLoading={isLoading}
        styles={customStyles}
        isClearable // Permite limpar o campo
        {...props}
      />
      {error && <span className="mt-1 text-xs text-red-500">{error}</span>}
    </div>
  );
};

/** * Componente de Input de Senha * Renderiza um campo type="password" com botão de "Mostrar/Ocultar" */
export const PasswordInput = ({ field, value, onChange, error, modelName, ...props }) => {
  const { label, name, required, placeholder } = field;
  const [showPassword, setShowPassword] = useState(false);

  const toggleShowPassword = () => {
    setShowPassword((prev) => !prev);
  };

  return (
    <div className="flex flex-col">
      <label htmlFor={name} className="mb-1.5 text-sm font-medium text-gray-700">
        {label} {required && <span className="text-red-500">*</span>}
      </label>

      {/* Container relativo para posicionar o botão */}
      <div className="relative">
        <input
          // O tipo muda dinamicamente
          type={showPassword ? 'text' : 'password'}
          id={name}
          name={name}
          autoComplete="new-password"
          value={value || ''}
          onChange={onChange}
          required={required}
          placeholder={placeholder || `Digite ${label.toLowerCase()}...`}
          // Adiciona padding à direita (pr-10) para o ícone não sobrepor o texto
          className={`w-full px-3 py-2 pr-10 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 
                                focus:outline-none focus:ring-blue-500 focus:border-blue-500
                                ${error ? 'border-red-500' : ''}`}
          {...props}
        />
        {/* Botão de Mostrar/Ocultar */}
        <button
          type="button" // Impede que o botão envie o formulário
          onClick={toggleShowPassword}
          className="absolute inset-y-0 right-0 flex items-center justify-center w-10 text-gray-500 hover:text-gray-700"
          aria-label={showPassword ? "Ocultar senha" : "Mostrar senha"}
        >
          {/* 🎯 Substituição dos ícones: Usando Lucide-React */}
          {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
        </button>
      </div>

      {error && <span className="mt-1 text-xs text-red-500">{error}</span>}
    </div>
  );
};

/** * Componente para Data (calendário) e Data/Hora * Usa o input nativo do HTML5 (<input type="date" />) * que abre um pop-up de calendário. */
export const DateInput = ({ field, value, onChange, error, disabled, modelName, ...props }) => {
  const { label, name, required } = field;

  // O tipo vindo do backend é 'date' or 'datetime'.
  // O tipo do input HTML é 'date' or 'datetime-local'.
  const inputType = field.type === 'datetime' ? 'datetime-local' : 'date';

  /**
   * Formata o valor para o input nativo.
   * O backend envia um ISO string (ex: "2025-11-06T19:56:05Z" ou "2025-11-06").
   * O input type="date" espera "YYYY-MM-DD".
   * O input type="datetime-local" espera "YYYY-MM-DDTHH:MM".
   * * Esta função converte o valor (que pode estar em UTC) para a string
   * no formato LOCAL correto que o input espera.
   */
  const formatValueForInput = (val) => {
    if (!val) return '';

    let dateStr = val;

    // FIX: Se o input for do tipo 'date' e o valor já estiver no formato 'YYYY-MM-DD',
    // retornamos diretamente. Isso evita que o new Date() processe o valor enquanto
    // o usuário digita, o que causava o bug de impedir a digitação manual.
    if (inputType === 'date' && typeof dateStr === 'string' && dateStr.length === 10 && !dateStr.includes('T')) {
      return dateStr;
    }

    // 1. Corrige o bug do JS Date() que trata "YYYY-MM-DD" como UTC.
    // Se for SÓ a data, adiciona a hora local para forçar o fuso correto.
    if (dateStr.length === 10 && !dateStr.includes('T')) {
      dateStr = `${dateStr}T00:00:00`;
    }

    const dateObj = new Date(dateStr);

    // Se a data for inválida, retorna vazio
    if (isNaN(dateObj.getTime())) {
      console.warn(`Valor de data inválido recebido: ${val}`);
      return '';
    }

    // 2. Extrai componentes LOCAIS (não UTC)
    const year = dateObj.getFullYear();
    const month = (dateObj.getMonth() + 1).toString().padStart(2, '0');
    const day = dateObj.getDate().toString().padStart(2, '0');

    if (inputType === 'date') {
      // Formato YYYY-MM-DD
      return `${year}-${month}-${day}`;
    } else {
      // Formato YYYY-MM-DDTHH:MM
      const hours = dateObj.getHours().toString().padStart(2, '0');
      const minutes = dateObj.getMinutes().toString().padStart(2, '0');
      return `${year}-${month}-${day}T${hours}:${minutes}`;
    }
  };

  const formattedValue = formatValueForInput(value);

  return (
    <div className="flex flex-col">
      <label htmlFor={name} className="mb-1.5 text-sm font-medium text-gray-700">
        {label} {required && <span className="text-red-500">*</span>}
      </label>
      <input
        type={inputType}
        id={name}
        name={name}
        autoComplete="off"
        value={formattedValue} // <- Usa o valor formatado
        onChange={onChange}    // <- O onChange nativo já envia o formato correto
        required={required}
        disabled={disabled}
        // Adiciona padding à direita para o ícone do calendário não sobrepor o texto
        className={`w-full px-3 py-2 pr-9 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 
                    focus:outline-none focus:ring-blue-500 focus:border-blue-500
                    ${error ? 'border-red-500' : ''}
                    ${disabled ? 'bg-gray-100 cursor-not-allowed' : ''}`}
        {...props}
      />
      {error && <span className="mt-1 text-xs text-red-500">{error}</span>}
    </div>
  );
};

/** * Componente de Upload de Arquivo (Converte para Base64) */
export const FileInput = ({ field, value, onChange, error, fileName, onKeyDown, ...props }) => {
  const { label, name, required, placeholder } = field;
  const fileInputRef = React.useRef(null);

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      // Se houver um campo configurado para salvar o nome do arquivo, atualiza-o
      if (field.filename_field) {
        onChange({
          target: {
            name: field.filename_field,
            value: file.name,
          },
        });
      }

      const reader = new FileReader();
      reader.onload = () => {
        // O resultado vem como "data:application/x-pkcs12;base64,MI..."
        // Precisamos remover o prefixo para enviar apenas o base64 puro para o backend
        const base64String = reader.result.split(',')[1];
        onChange({
          target: {
            name: name,
            value: base64String,
          },
        });
      };
      reader.readAsDataURL(file);
    }
  };

  const handleTriggerClick = () => {
    fileInputRef.current?.click();
  };

  const handleDownload = (e) => {
    e.stopPropagation(); // Impede que o clique abra a seleção de arquivo
    if (!value) return;

    let mimeType = 'text/plain';
    let extension = 'txt';
    let isBase64 = false;

    // Detecta tipo pelo nome do campo
    if (name.includes('xml')) {
      mimeType = 'application/xml';
      extension = 'xml';
    } else if (name.includes('pdf')) {
      mimeType = 'application/pdf';
      extension = 'pdf';
      isBase64 = true;
    } else if (name.includes('certificado')) {
      mimeType = 'application/x-pkcs12';
      extension = 'pfx';
      isBase64 = true;
    }

    const link = document.createElement('a');

    if (isBase64) {
      const cleanValue = value.replace(/^data:.*;base64,/, '');
      link.href = `data:${mimeType};base64,${cleanValue}`;
    } else {
      link.href = `data:${mimeType};charset=utf-8,${encodeURIComponent(value)}`;
    }

    link.download = `${name}_${new Date().getTime()}.${extension}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Define o texto a ser exibido dentro do input simulado
  const displayText = fileName || (value ? "Arquivo disponível" : "");

  return (
    <div className="flex flex-col">
      <label htmlFor={name} className="mb-1.5 text-sm font-medium text-gray-700">
        {label} {required && <span className="text-red-500">*</span>}
      </label>

      <div className="relative">
        <input
          type="file"
          id={name}
          name={name}
          accept=".pfx,.xml,.pdf"
          ref={fileInputRef}
          onChange={handleFileChange}
          className="hidden"
        />

        <div
          onClick={handleTriggerClick}
          className={`w-full px-3 py-2 pr-20 border border-gray-300 rounded-md shadow-sm 
                      cursor-pointer bg-white flex items-center min-h-[42px]
                      focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500
                      ${error ? 'border-red-500' : 'hover:border-gray-400'}`}
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              handleTriggerClick();
            }
            if (onKeyDown) onKeyDown(e);
          }}
        >
          <span className={`truncate ${!displayText ? 'text-gray-400' : 'text-gray-700'}`}>
            {displayText || placeholder || "Clique para selecionar..."}
          </span>

          <div className="absolute inset-y-0 right-0 flex items-center pr-2 space-x-1">
            {value && (
              <button
                type="button"
                onClick={handleDownload}
                className="p-1.5 text-blue-600 hover:text-blue-800 hover:bg-blue-50 rounded-full transition-colors z-10"
                title="Baixar arquivo"
              >
                <Download className="w-5 h-5" />
              </button>
            )}
            <div className="p-1.5 pointer-events-none text-gray-500">
              <Upload className="w-5 h-5" />
            </div>
          </div>
        </div>
      </div>

      {error && <span className="mt-1 text-xs text-red-500">{error}</span>}
    </div>
  );
};

/** * Componente de Upload de Imagem ou Link Direto (URL) */
export const ImageUploadOrUrlInput = ({ field, value, onChange, error, disabled, ...props }) => {
  const { label, name, required, placeholder } = field;
  const [tab, setTab] = useState(() => {
    if (value && String(value).startsWith('data:')) {
      return 'file';
    }
    if (value && (String(value).startsWith('http://') || String(value).startsWith('https://'))) {
      return 'url';
    }
    return 'file'; // default tab
  });

  const fileInputRef = React.useRef(null);

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = () => {
        onChange({
          target: {
            name: name,
            value: reader.result,
          },
        });
      };
      reader.readAsDataURL(file);
    }
  };

  const handleUrlChange = (e) => {
    onChange({
      target: {
        name: name,
        value: e.target.value,
      },
    });
  };

  const handleRemove = () => {
    onChange({
      target: {
        name: name,
        value: '',
      },
    });
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleTriggerClick = () => {
    fileInputRef.current?.click();
  };

  const isBase64 = value && String(value).startsWith('data:');
  const isUrl = value && (String(value).startsWith('http://') || String(value).startsWith('https://'));

  return (
    <div className="flex flex-col space-y-2">
      <label className="text-sm font-medium text-gray-700">
        {label} {required && <span className="text-red-500">*</span>}
      </label>

      {/* Tabs */}
      <div className="flex space-x-1 p-0.5 bg-gray-100 rounded-lg w-fit">
        <button
          type="button"
          onClick={() => setTab('file')}
          className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-all ${
            tab === 'file'
              ? 'bg-white text-gray-800 shadow-sm'
              : 'text-gray-500 hover:text-gray-700'
          }`}
          disabled={disabled}
        >
          Carregar Arquivo
        </button>
        <button
          type="button"
          onClick={() => setTab('url')}
          className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-all ${
            tab === 'url'
              ? 'bg-white text-gray-800 shadow-sm'
              : 'text-gray-500 hover:text-gray-700'
          }`}
          disabled={disabled}
        >
          Link da Imagem
        </button>
      </div>

      {/* Content */}
      <div className="relative">
        {tab === 'file' ? (
          <div>
            <input
              type="file"
              id={name}
              name={name}
              accept="image/*"
              ref={fileInputRef}
              onChange={handleFileChange}
              className="hidden"
              disabled={disabled}
            />
            <div
              onClick={disabled ? undefined : handleTriggerClick}
              className={`w-full px-4 py-3 border border-gray-300 rounded-md shadow-sm 
                          bg-white flex flex-col items-center justify-center min-h-[90px] border-dashed
                          ${disabled ? 'bg-gray-50 cursor-not-allowed opacity-60' : 'cursor-pointer hover:border-blue-500 hover:bg-blue-50/10'}`}
              tabIndex={disabled ? -1 : 0}
              onKeyDown={(e) => {
                if (disabled) return;
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  handleTriggerClick();
                }
              }}
            >
              <Upload className="w-6 h-6 text-gray-400 mb-1" />
              <span className="text-sm font-medium text-gray-600">
                {isBase64 ? "Imagem carregada" : placeholder || "Clique para carregar imagem..."}
              </span>
              <span className="text-xs text-gray-400 mt-0.5">
                Formatos suportados: PNG, JPG, JPEG, GIF
              </span>
            </div>
          </div>
        ) : (
          <input
            type="text"
            id={name}
            name={name}
            value={isUrl ? value : ''}
            onChange={handleUrlChange}
            placeholder="Cole o link direto da imagem (https://...)"
            disabled={disabled}
            className={`w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 
                        focus:outline-none focus:ring-blue-500 focus:border-blue-500
                        ${error ? 'border-red-500' : ''}
                        ${disabled ? 'bg-gray-100 cursor-not-allowed' : ''}`}
            {...props}
          />
        )}
      </div>

      {/* Preview and Remove Button */}
      {value && (
        <div className="flex items-center space-x-4 mt-2 p-2 bg-gray-50 border border-gray-100 rounded-lg animate-fade-in">
          <div className="w-16 h-16 bg-white border border-gray-200 rounded flex items-center justify-center overflow-hidden p-1 shadow-sm">
            <img
              src={value}
              alt="Pré-visualização do Logo"
              className="max-w-full max-h-full object-contain"
              onError={(e) => {
                e.target.style.display = 'none';
              }}
            />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
              Visualização do Logo
            </p>
            <p className="text-xs text-gray-400 truncate mt-0.5">
              {isBase64 ? "Arquivo Base64" : value}
            </p>
          </div>
          {!disabled && (
            <button
              type="button"
              onClick={handleRemove}
              className="p-1.5 text-red-500 hover:text-red-700 hover:bg-red-50 rounded-full transition-colors"
              title="Remover logo"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
        </div>
      )}

      {error && <span className="mt-1 text-xs text-red-500">{error}</span>}
    </div>
  );
};