import React, { useState, useEffect } from 'react';
import { Eye, EyeOff, Trash2, ChevronDown, ChevronUp, CheckCircle2, Upload, Download, Info, Plus, X, Palette } from 'lucide-react';
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

export const REACT_SELECT_CUSTOM_STYLES = (error = false) => ({
  control: (provided, state) => ({
    ...provided,
    minHeight: '38px',
    height: '38px',
    maxHeight: '38px',
    borderRadius: '0.375rem',
    borderColor: error ? '#ef4444' : (state.isFocused ? '#3b82f6' : '#d1d5db'),
    boxShadow: state.isFocused ? '0 0 0 1px #3b82f6' : '0 1px 2px 0 rgb(0 0 0 / 0.05)',
    '&:hover': {
      borderColor: state.isFocused ? '#3b82f6' : '#9ca3af'
    },
    backgroundColor: state.isDisabled ? '#f3f4f6' : 'white',
    fontSize: '0.875rem',
  }),
  valueContainer: (provided) => ({
    ...provided,
    height: '38px',
    padding: '0 10px',
    display: 'flex',
    alignItems: 'center'
  }),
  singleValue: (provided) => ({
    ...provided,
    color: '#1f2937',
    margin: 0,
    padding: 0
  }),
  placeholder: (provided) => ({
    ...provided,
    color: '#9ca3af',
    margin: 0,
    padding: 0
  }),
  input: (provided) => ({
    ...provided,
    margin: '0px',
    padding: '0px'
  }),
  indicatorsContainer: (provided) => ({
    ...provided,
    height: '38px'
  }),
  indicatorSeparator: () => ({
    display: 'none'
  }),
  dropdownIndicator: (provided) => ({
    ...provided,
    padding: '6px',
    color: '#9ca3af'
  }),
  clearIndicator: (provided) => ({
    ...provided,
    padding: '4px 6px',
    color: '#9ca3af',
    cursor: 'pointer',
    '&:hover': {
      color: '#ef4444'
    }
  }),
  menu: (provided) => ({
    ...provided,
    zIndex: 50,
    borderRadius: '0.375rem',
    boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)',
  }),
  option: (provided, state) => ({
    ...provided,
    backgroundColor: state.isSelected ? '#dde2eb' : (state.isFocused ? '#f3f4f6' : 'white'),
    color: '#1f2937',
    cursor: 'pointer',
    fontSize: '0.875rem',
    padding: '6px 10px',
  }),
  menuPortal: (base) => ({ ...base, zIndex: 9999 })
});

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
      {label && (
        <label htmlFor={name} className="mb-1.5 text-sm font-medium text-gray-700">
          {label} {required && <span className="text-red-500">*</span>}
        </label>
      )}
      <input
        type={inputType}
        id={name}
        name={name}
        autoComplete="off"
        ref={finalRef}
        required={required}
        placeholder={placeholder || field?.placeholder || ''}
        className={`w-full h-[38px] px-3 py-1.5 border border-gray-300 rounded-md shadow-2xs text-sm text-gray-800 bg-white placeholder-gray-400 
                    focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500
                    ${error ? 'border-red-500 focus:ring-red-500' : ''}`}
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
export const BooleanInput = ({ field, value, onChange, error, modelName, disabled, placeholder, ...props }) => {
  const { label, name, required } = field || {};

  const isSituacaoField = name ? name.toLowerCase().includes('situacao') : false;
  const trueLabel = isSituacaoField ? 'Ativo' : 'Sim';
  const falseLabel = isSituacaoField ? 'Inativo' : 'Não';

  const options = React.useMemo(() => [
    { value: 'true', label: trueLabel },
    { value: 'false', label: falseLabel }
  ], [trueLabel, falseLabel]);

  const selectedOption = React.useMemo(() => {
    if (value === true || value === 'true') return { value: 'true', label: trueLabel };
    if (value === false || value === 'false') return { value: 'false', label: falseLabel };
    return null;
  }, [value, trueLabel, falseLabel]);

  const handleChange = (selected) => {
    let booleanValue = null;
    if (selected) {
      booleanValue = selected.value === 'true';
    }
    onChange({
      target: {
        name: name,
        value: booleanValue,
      },
    });
  };

  return (
    <div className="flex flex-col">
      {label && (
        <label htmlFor={name} className="mb-1.5 text-sm font-medium text-gray-700">
          {label} {required && <span className="text-red-500">*</span>}
        </label>
      )}
      <Select
        id={name}
        name={name}
        autoComplete="off"
        isDisabled={disabled}
        options={options}
        value={selectedOption}
        onChange={handleChange}
        placeholder={placeholder || field?.placeholder || ''}
        classNamePrefix="react-select"
        menuPortalTarget={document.body}
        styles={REACT_SELECT_CUSTOM_STYLES(!!error)}
        isClearable={!required}
        {...props}
      />
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
    <div className="flex flex-col space-y-3 md:col-span-3">
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
            </ul>
          </div>
        </div>
      )}

      <div className="space-y-3">
        {items.map((item, index) => (
          <div key={index} className="grid grid-cols-1 md:grid-cols-12 gap-x-4 gap-y-3 items-start">
            {/* Produto (5 cols) */}
            <div className="md:col-span-5 flex flex-col">
              {index === 0 && (
                <label className="mb-1.5 text-sm font-medium text-gray-700">
                  Produto
                </label>
              )}
              <AsyncProductSelect
                value={item.id_produto}
                onChange={(opt) => handleProductChange(index, opt)}
                error={!item.id_produto && error}
              />
            </div>

            {/* Quantidade (2 cols) */}
            <div className="md:col-span-2 flex flex-col">
              {index === 0 && (
                <label className="mb-1.5 text-sm font-medium text-gray-700">
                  Qtd
                </label>
              )}
              <input
                type="number"
                value={item.quantidade}
                onChange={(e) => handleItemChange(index, 'quantidade', e.target.value === '' ? '' : Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm text-gray-800 bg-white"
                placeholder="Qtd"
                min={isComplemento ? "0" : "1"}
              />
            </div>

            {/* Valor Unitário (2 cols) */}
            <div className="md:col-span-2 flex flex-col">
              {index === 0 && (
                <label className="mb-1.5 text-sm font-medium text-gray-700">
                  Valor Unit. (R$)
                </label>
              )}
              <IMaskInput
                mask={MASKS['currency'].mask}
                blocks={{
                  num: { ...MASKS['currency'].blocks.num, padFractionalZeros: true }
                }}
                lazy={MASKS['currency'].lazy}
                value={item.valor_unitario !== undefined && item.valor_unitario !== null && item.valor_unitario !== '' && item.valor_unitario !== 0 ? String(item.valor_unitario).replace('.', ',') : ''}
                unmask={true}
                onAccept={(val, mask) => {
                  let rawVal = mask.unmaskedValue;
                  if (rawVal !== undefined && rawVal !== null && rawVal !== '') {
                    const parsed = parseFloat(String(rawVal).replace(',', '.'));
                    if (!isNaN(parsed) && parsed !== item.valor_unitario) {
                      handleItemChange(index, 'valor_unitario', parsed);
                    }
                  } else if (item.valor_unitario !== '') {
                    handleItemChange(index, 'valor_unitario', '');
                  }
                }}
                className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm text-gray-800 bg-white"
                placeholder="0,00"
              />
            </div>

            {/* Total com IPI + Lixeira (3 cols) */}
            <div className="md:col-span-3 flex flex-col">
              {index === 0 && (
                <label className="mb-1.5 text-sm font-medium text-gray-700">
                  Total c/ IPI (R$)
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
                    value={item.total_com_ipi !== undefined && item.total_com_ipi !== null && item.total_com_ipi !== '' && item.total_com_ipi !== 0 ? String(item.total_com_ipi).replace('.', ',') : ''}
                    unmask={true}
                    onAccept={(val, mask) => {
                      let rawVal = mask.unmaskedValue;
                      if (rawVal !== undefined && rawVal !== null && rawVal !== '') {
                        const parsed = parseFloat(String(rawVal).replace(',', '.'));
                        if (!isNaN(parsed) && parsed !== item.total_com_ipi) {
                          handleItemChange(index, 'total_com_ipi', parsed);
                        }
                      } else if (item.total_com_ipi !== '') {
                        handleItemChange(index, 'total_com_ipi', '');
                      }
                    }}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm font-semibold text-gray-800 bg-white"
                    placeholder="0,00"
                  />
                </div>
                {items.length > 1 && (
                  <button
                    type="button"
                    onClick={() => handleRemoveItem(index)}
                    className="p-2 text-gray-400 hover:text-red-600 transition-colors shrink-0"
                    title="Remover item"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="pt-2">
        <button
          type="button"
          onClick={handleAddItem}
          className="w-full py-2.5 px-4 border border-dashed border-gray-300 hover:border-teal-600 bg-gray-50/60 hover:bg-teal-50/40 text-gray-600 hover:text-teal-700 rounded-md text-xs font-semibold flex items-center justify-center gap-2 transition-all shadow-2xs group"
        >
          <div className="p-1 rounded bg-white group-hover:bg-teal-600 text-gray-500 group-hover:text-white border border-gray-200 group-hover:border-teal-600 transition-colors shadow-2xs">
            <Plus className="w-3.5 h-3.5" />
          </div>
          <span>Adicionar Item ao Pedido</span>
        </button>
      </div>

      {error && <span className="mt-1 text-xs text-red-500">{error}</span>}
    </div>
  );
};

const AsyncProductSelect = ({ value, onChange, error }) => {
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
      styles={REACT_SELECT_CUSTOM_STYLES(!!error)}
      isClearable={true}
    />
  );
};

export const SelectInput = ({ field, value, onChange, error, options = [], modelName, formData, disabled, placeholder, ...props }) => {
  const { label, name, required } = field || {};

  const formattedOptions = React.useMemo(() => {
    return (options || []).map((opt) => ({
      value: typeof opt === 'object' ? opt.value : opt,
      label: typeof opt === 'object' ? formatLabel(opt.label || opt.value) : formatLabel(opt),
    }));
  }, [options]);

  const selectedOption = React.useMemo(() => {
    if (value === null || value === undefined || value === '') return null;
    const stringVal = String(value);
    return formattedOptions.find((opt) => String(opt.value) === stringVal) || { value, label: formatLabel(String(value)) };
  }, [value, formattedOptions]);

  const handleChange = (selected) => {
    const val = selected ? selected.value : null;
    onChange({
      target: {
        name: name,
        value: val,
      },
    });
  };

  return (
    <div className="flex flex-col">
      {label && (
        <label htmlFor={name} className="mb-1.5 text-sm font-medium text-gray-700">
          {label} {required && <span className="text-red-500">*</span>}
        </label>
      )}
      <Select
        id={name}
        name={name}
        autoComplete="off"
        isDisabled={disabled}
        options={formattedOptions}
        value={selectedOption}
        onChange={handleChange}
        placeholder={placeholder || field?.placeholder || "Selecione..."}
        classNamePrefix="react-select"
        menuPortalTarget={document.body}
        styles={REACT_SELECT_CUSTOM_STYLES(!!error)}
        isClearable={true}
        {...props}
      />
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
        styles={REACT_SELECT_CUSTOM_STYLES(!!error)}
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
        styles={REACT_SELECT_CUSTOM_STYLES(!!error)}
        isClearable
        {...props}
      />
      {error && <span className="mt-1 text-xs text-red-500">{error}</span>}
    </div>
  );
};

/** * Componente de Input de Senha * Renderiza um campo type="password" com botão de "Mostrar/Ocultar" */
export const PasswordInput = ({ field, value, onChange, error, modelName, formData, disabled, placeholder, ...props }) => {
  const { label, name, required } = field || {};
  const [showPassword, setShowPassword] = useState(false);

  // Se o valor for um hash bcrypt antigo ($2b$ ou $2a$), esconde a hash e pede nova senha se desejar alterar
  const isLegacyBcryptHash = value && (String(value).startsWith('$2b$') || String(value).startsWith('$2a$'));
  const inputValue = isLegacyBcryptHash ? '' : (value || '');
  const activePlaceholder = isLegacyBcryptHash 
    ? '(Senha salva - digite nova para alterar)' 
    : (placeholder || field?.placeholder || '');

  const toggleShowPassword = () => {
    setShowPassword((prev) => !prev);
  };

  return (
    <div className="flex flex-col">
      {label && (
        <label htmlFor={name} className="mb-1.5 text-sm font-medium text-gray-700">
          {label} {required && <span className="text-red-500">*</span>}
        </label>
      )}

      <div className="relative flex items-center">
        <input
          type={showPassword ? 'text' : 'password'}
          id={name}
          name={name}
          autoComplete="new-password"
          value={inputValue}
          onChange={onChange}
          required={required && !isLegacyBcryptHash}
          disabled={disabled}
          placeholder={activePlaceholder}
          className={`w-full h-[38px] px-3 py-1.5 pr-10 border border-gray-300 rounded-md shadow-2xs text-sm text-gray-800 bg-white placeholder-gray-400 
                      focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500
                      ${error ? 'border-red-500 focus:ring-red-500' : ''}
                      ${disabled ? 'bg-gray-100 cursor-not-allowed text-gray-400' : ''}`}
          {...props}
        />
        <button
          type="button"
          onClick={toggleShowPassword}
          disabled={disabled}
          className="absolute right-0 h-[38px] w-9 flex items-center justify-center text-gray-400 hover:text-gray-600 transition-colors"
          aria-label={showPassword ? "Ocultar senha" : "Mostrar senha"}
        >
          {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
        </button>
      </div>

      {error && <span className="mt-1 text-xs text-red-500">{error}</span>}
    </div>
  );
};


/** * Componente para Data (calendário) e Data/Hora * Usa o input nativo do HTML5 (<input type="date" />) * que abre um pop-up de calendário. */
export const DateInput = ({ field, value, onChange, error, disabled, modelName, formData, ...props }) => {
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
      {label && (
        <label htmlFor={name} className="mb-1.5 text-sm font-medium text-gray-700">
          {label} {required && <span className="text-red-500">*</span>}
        </label>
      )}
      <input
        type={inputType}
        id={name}
        name={name}
        autoComplete="off"
        value={formattedValue}
        onChange={onChange}
        required={required}
        disabled={disabled}
        className={`w-full h-[38px] px-3 py-1.5 border border-gray-300 rounded-md shadow-2xs text-sm text-gray-800 bg-white placeholder-gray-400 
                    focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500
                    ${error ? 'border-red-500 focus:ring-red-500' : ''}
                    ${disabled ? 'bg-gray-100 cursor-not-allowed text-gray-400' : ''}`}
        {...props}
      />
      {error && <span className="mt-1 text-xs text-red-500">{error}</span>}
    </div>
  );
};

/** * Componente de Upload de Arquivo (Converte para Base64) */
export const FileInput = ({ field, value, onChange, error, fileName, onKeyDown, ...props }) => {
  const { label, name, required, placeholder } = field || {};
  const fileInputRef = React.useRef(null);

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) {
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
    e.stopPropagation();
    if (!value) return;

    let mimeType = 'text/plain';
    let extension = 'txt';
    let isBase64 = false;

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

  const displayText = fileName || (value ? "Arquivo disponível" : "");

  return (
    <div className="flex flex-col">
      {label && (
        <label htmlFor={name} className="mb-1.5 text-sm font-medium text-gray-700">
          {label} {required && <span className="text-red-500">*</span>}
        </label>
      )}

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
          className={`w-full h-[38px] px-3 py-1.5 pr-20 border border-gray-300 rounded-md shadow-2xs 
                      cursor-pointer bg-white flex items-center text-sm text-gray-800
                      focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500
                      ${error ? 'border-red-500 focus:ring-red-500' : 'hover:border-gray-400'}`}
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
            {displayText || placeholder || field?.placeholder || ''}
          </span>

          <div className="absolute inset-y-0 right-0 flex items-center pr-2 space-x-1">
            {value && (
              <button
                type="button"
                onClick={handleDownload}
                className="p-1 text-blue-600 hover:text-blue-800 hover:bg-blue-50 rounded-full transition-colors z-10"
                title="Baixar arquivo"
              >
                <Download className="w-4 h-4" />
              </button>
            )}
            <div className="p-1 pointer-events-none text-gray-400">
              <Upload className="w-4 h-4" />
            </div>
          </div>
        </div>
      </div>

      {error && <span className="mt-1 text-xs text-red-500">{error}</span>}
    </div>
  );
};

export const ImageUploadOrUrlInput = ({ field, value, onChange, error, disabled, placeholder, fileName: externalFileName, ...props }) => {
  const { label, name, required } = field || {};
  const fileInputRef = React.useRef(null);
  const [internalFileName, setInternalFileName] = useState('');

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      setInternalFileName(file.name);
      if (field?.filename_field) {
        onChange({
          target: {
            name: field.filename_field,
            value: file.name,
          },
        });
      }
      const reader = new FileReader();
      reader.onload = () => {
        const rawBase64 = reader.result;
        // Embute o nome do arquivo no cabeçalho do Data URL: data:image/png;name=logo.png;base64,...
        const base64WithName = rawBase64.replace(/^data:(image\/[^;]+);base64,/, `data:$1;name=${encodeURIComponent(file.name)};base64,`);
        onChange({
          target: {
            name: name,
            value: base64WithName,
          },
        });
      };
      reader.readAsDataURL(file);
    }
  };

  const handleTextChange = (e) => {
    setInternalFileName('');
    onChange({
      target: {
        name: name,
        value: e.target.value,
      },
    });
  };

  const handleClear = (e) => {
    e.stopPropagation();
    setInternalFileName('');
    onChange({
      target: {
        name: name,
        value: '',
      },
    });
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleTriggerClick = () => {
    fileInputRef.current?.click();
  };

  const parseFileNameFromDataUrl = (val) => {
    if (!val || typeof val !== 'string') return null;
    const match = val.match(/;name=([^;]+);/);
    if (match && match[1]) {
      try {
        return decodeURIComponent(match[1]);
      } catch {
        return match[1];
      }
    }
    return null;
  };

  const hasValue = !!value;
  const isBase64 = value && String(value).startsWith('data:');
  const currentFileName = externalFileName || internalFileName || parseFileNameFromDataUrl(value) || 'imagem_anexada.png';

  // Se for base64, exibe o nome do arquivo na caixa de texto em vez da hash gigante
  const displayValue = isBase64 ? currentFileName : (value || '');


  return (
    <div className="flex flex-col">
      {label && (
        <label htmlFor={name} className="mb-1.5 text-sm font-medium text-gray-700">
          {label} {required && <span className="text-red-500">*</span>}
        </label>
      )}

      <div className="relative flex items-center">
        <input
          type="file"
          id={`${name}_file`}
          accept="image/*"
          ref={fileInputRef}
          onChange={handleFileChange}
          className="hidden"
          disabled={disabled}
        />

        <div
          className={`w-full h-[38px] px-2.5 border border-gray-300 rounded-md shadow-2xs bg-white 
                      flex items-center gap-2 text-sm text-gray-800 focus-within:ring-2 focus-within:ring-blue-500 focus-within:border-blue-500
                      ${error ? 'border-red-500 focus-within:ring-red-500' : ''}
                      ${disabled ? 'bg-gray-100 cursor-not-allowed text-gray-400' : ''}`}
        >
          {/* Visualização no início do campo antes da URL/Texto */}
          {hasValue && (
            <div className="w-6 h-6 rounded border border-gray-200 overflow-hidden bg-gray-50 flex items-center justify-center shrink-0">
              <img
                src={value}
                alt="preview"
                className="w-full h-full object-cover"
                onError={(e) => {
                  e.target.style.display = 'none';
                }}
              />
            </div>
          )}

          {/* Campo de Texto para colar a URL ou visualizar o Nome do Arquivo */}
          <input
            type="text"
            id={name}
            name={name}
            value={displayValue}
            onChange={handleTextChange}
            readOnly={isBase64}
            placeholder={placeholder || field?.placeholder || ''}
            disabled={disabled}
            className="flex-1 bg-transparent border-none outline-none focus:outline-none focus:ring-0 p-0 text-sm text-gray-800 placeholder-gray-400 min-w-0"
            {...props}
          />

          {/* Botões de Ação na Direita (Limpar e Upload) */}
          <div className="flex items-center gap-1 shrink-0">

            {hasValue && !disabled && (
              <button
                type="button"
                onClick={handleClear}
                className="p-1 text-gray-400 hover:text-red-500 rounded transition-colors"
                title="Limpar imagem"
              >
                <X className="w-4 h-4" />
              </button>
            )}
            <button
              type="button"
              onClick={handleTriggerClick}
              disabled={disabled}
              className="p-1 text-gray-400 hover:text-blue-600 rounded transition-colors"
              title="Carregar arquivo de imagem"
            >
              <Upload className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {error && <span className="mt-1 text-xs text-red-500">{error}</span>}
    </div>
  );
};

/**
 * Componente de Seleção de Cores (Color Picker com Pop-up RGB/HEX)
 */
export const ColorInput = ({ field, value, onChange, error, disabled, placeholder, ...props }) => {
  const { label, name, required } = field || {};
  const colorInputRef = React.useRef(null);

  const colorValue = value || '#3b82f6';

  const handleNativeColorChange = (e) => {
    onChange({
      target: {
        name: name,
        value: e.target.value,
      },
    });
  };

  const handleTextChange = (e) => {
    onChange({
      target: {
        name: name,
        value: e.target.value,
      },
    });
  };

  const handleClear = (e) => {
    e.stopPropagation();
    onChange({
      target: {
        name: name,
        value: '',
      },
    });
  };

  const openPicker = () => {
    if (!disabled) {
      colorInputRef.current?.click();
    }
  };

  return (
    <div className="flex flex-col">
      {label && (
        <label htmlFor={name} className="mb-1.5 text-sm font-medium text-gray-700">
          {label} {required && <span className="text-red-500">*</span>}
        </label>
      )}

      <div className="relative flex items-center">
        <input
          type="color"
          ref={colorInputRef}
          value={colorValue.startsWith('#') && colorValue.length === 7 ? colorValue : '#3b82f6'}
          onChange={handleNativeColorChange}
          disabled={disabled}
          className="absolute opacity-0 pointer-events-none w-0 h-0"
        />

        <div
          className={`w-full h-[38px] px-2.5 border border-gray-300 rounded-md shadow-2xs bg-white 
                      flex items-center gap-2 text-sm text-gray-800 focus-within:ring-2 focus-within:ring-blue-500 focus-within:border-blue-500
                      ${error ? 'border-red-500 focus-within:ring-red-500' : ''}
                      ${disabled ? 'bg-gray-100 cursor-not-allowed text-gray-400' : ''}`}
        >
          {/* Amostra visual de cor que abre o pop-up RGB/HEX */}
          <button
            type="button"
            onClick={openPicker}
            disabled={disabled}
            className="w-6 h-6 rounded-md border border-gray-300 shadow-2xs shrink-0 cursor-pointer transition-transform hover:scale-105 active:scale-95 flex items-center justify-center overflow-hidden"
            style={{ backgroundColor: colorValue }}
            title="Clique para abrir a paleta de cores (RGB / HEX)"
          />

          {/* Campo de texto para visualizar/digitar o código HEX ou RGB */}
          <input
            type="text"
            id={name}
            name={name}
            value={value || ''}
            onChange={handleTextChange}
            placeholder={placeholder || field?.placeholder || '#000000 ou rgb(...)'}
            disabled={disabled}
            className="flex-1 bg-transparent border-none outline-none focus:outline-none focus:ring-0 p-0 text-sm font-mono text-gray-800 placeholder-gray-400 min-w-0"
            {...props}
          />

          {/* Botões de Ação na Direita */}
          <div className="flex items-center gap-1 shrink-0">
            {value && !disabled && (
              <button
                type="button"
                onClick={handleClear}
                className="p-1 text-gray-400 hover:text-red-500 rounded transition-colors"
                title="Limpar cor"
              >
                <X className="w-4 h-4" />
              </button>
            )}
            <button
              type="button"
              onClick={openPicker}
              disabled={disabled}
              className="p-1 text-gray-400 hover:text-blue-600 rounded transition-colors"
              title="Selecionar Cor"
            >
              <Palette className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {error && <span className="mt-1 text-xs text-red-500">{error}</span>}
    </div>
  );
};
