import React, { useState, useEffect } from 'react';
import { Eye, EyeOff, Trash2 } from 'lucide-react';
import AsyncSelect from 'react-select/async';
import api from '../../api/axiosConfig';

import IMask from 'imask';
import { default as IMaskInput } from 'react-imask/esm/mixin';
// Garante o registro de MaskedNumber e CompositeMask
import 'imask/esm/addons/all';


export const MASKS = {
  'cep': '00000-000',
  'ncm': '0000.00.00', // NCM: 8 dígitos numéricos
  // Máscara dinâmica para CPF/CNPJ 
  'cnpj_cpf': [{ mask: '000.000.000-00' }, { mask: '00.000.000/0000-00' }],
  'phone': [
    { mask: '(00) 0000-0000' },
    { mask: '(00) 0 0000-0000' },
  ],
  // Máscara de moeda (Numeric)
  'currency': {
    mask: 'R$ num',
    lazy: false, // Exibe a máscara (R$ __,__) imediatamente
    blocks: {
      num: {
        mask: Number,
        thousandsSeparator: '.',
        radix: ',',
        mapToRadix: ['.'],
        scale: 2,
        padFractionalZeros: true,
        normalizeZeros: true,
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
    padFractionalZeros: true,
    normalizeZeros: true,
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
    padFractionalZeros: true,
    normalizeZeros: true,
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
    padFractionalZeros: true,
    normalizeZeros: true,
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

  // ************ FIM DA CORREÇÃO ************

  return (
    <div className="flex flex-col">
      <label htmlFor={name} className="mb-1.5 text-sm font-medium text-gray-700">
        {label} {required && <span className="text-red-500">*</span>}
      </label>
      <input
        type={inputType}
        id={name}
        name={name}
        // 🎯 PASSA O REF CORRETO PARA O ELEMENTO INPUT DO DOM
        ref={finalRef}
        required={required}
        placeholder={placeholder || `Digite ${label.toLowerCase()}...`}
        className={`w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 
                            focus:outline-none focus:ring-blue-500 focus:border-blue-500
                            ${error ? 'border-red-500' : ''}`}
        // 🎯 PASSA APENAS AS PROPS FILTRADAS
        {...filteredInputProps}
      />
      {error && <span className="mt-1 text-xs text-red-500">{error}</span>}
    </div>
  );
});


/** * Componente Wrapper para o input mascarado. * Ele herda todas as props do TextInput, mas adiciona a funcionalidade de máscara. */
export const MaskedInput = IMaskInput(TextInput);


/** * Componente de Input Booleano (Dropdown Sim/Não) * Renderiza como um <select> com opções "Sim" e "Não". */
export const BooleanInput = ({ field, value, onChange, error }) => {
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

    return 'false'; // Para 'null', 'undefined', etc.
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
export const OrderItemsInput = ({ field, value, onChange, error }) => {
  const { label, name, required } = field;
  // Garante que items seja um array
  const items = Array.isArray(value) ? value : [];

  const handleAddItem = () => {
    const newItems = [...items, { id_produto: null, quantidade: 1 }];
    triggerChange(newItems);
  };

  const handleRemoveItem = (index) => {
    const newItems = items.filter((_, i) => i !== index);
    triggerChange(newItems);
  };

  const handleItemChange = (index, key, val) => {
    const newItems = [...items];
    newItems[index] = { ...newItems[index], [key]: val };
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
      
      <div className="space-y-2">
        {items.map((item, index) => (
          <div key={index} className="flex gap-2 items-start">
            <div className="flex-grow">
               <AsyncProductSelect 
                 value={item.id_produto}
                 onChange={(val) => handleItemChange(index, 'id_produto', val)}
                 error={!item.id_produto && error} // Visual simples de erro
               />
            </div>
            <div className="w-24">
              <input
                type="number"
                value={item.quantidade}
                onChange={(e) => handleItemChange(index, 'quantidade', Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                placeholder="Qtd"
                min="1"
              />
            </div>
            <button 
              type="button" 
              onClick={() => handleRemoveItem(index)}
              className="p-2 text-red-500 hover:text-red-700"
              title="Remover item"
            >
              <Trash2 className="w-5 h-5" />
            </button>
          </div>
        ))}
      </div>

      <button
        type="button"
        onClick={handleAddItem}
        className="flex items-center justify-center px-4 py-2 text-sm font-medium text-blue-600 bg-blue-50 hover:bg-blue-100 rounded-md border border-blue-200 dashed"
      >
        + Adicionar Item
      </button>
      
      {error && <span className="mt-1 text-xs text-red-500">{error}</span>}
    </div>
  );
};

// Componente auxiliar interno para busca de produtos
const AsyncProductSelect = ({ value, onChange }) => {
  const [selectedOption, setSelectedOption] = useState(null);
  
  const loadOptions = (inputValue, callback) => {
    api.get(`/generic/produtos`, {
      params: { search_term: inputValue, limit: 20, situacao: 'true' }
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
        control: (base) => ({ ...base, minHeight: '42px', borderColor: '#d1d5db' }),
        menu: (base) => ({ ...base, zIndex: 9999 }),
        menuPortal: (base) => ({ ...base, zIndex: 9999 })
      }}
    />
  );
};

/** * Componente de Select (Dropdown) */
export const SelectInput = ({ field, value, onChange, error, options = [] }) => {
  const { label, name, required } = field;

  return (
    <div className="flex flex-col">
      <label htmlFor={name} className="mb-1.5 text-sm font-medium text-gray-700">
        {label} {required && <span className="text-red-500">*</span>}
      </label>
      <select
        id={name}
        name={name}
        value={value || ''}
        onChange={onChange}
        required={required}
        className={`w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm 
                            focus:outline-none focus:ring-blue-500 focus:border-blue-500
                            ${error ? 'border-red-500' : ''}`}
      >
        <option value="" disabled>Selecione...</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {formatLabel(option.label || option.value)}
          </option>
        ))}
      </select>
      {error && <span className="mt-1 text-xs text-red-500">{error}</span>}
    </div>
  );
};


/** * Componente de Select Assíncrono com busca (para Foreign Keys) * Usa react-select/async */
export const AsyncSelectInput = ({ field, value, onChange, error }) => {
  const { label, name, required, foreign_key_model, foreign_key_label_field } = field;
  
  // Estado para o objeto de seleção { value, label } e para o carregamento inicial
  const [selectedOption, setSelectedOption] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  // 1. Função para carregar opções (busca)
  const loadOptions = (inputValue, callback) => {
    if (!foreign_key_model || !foreign_key_label_field) return callback([]);

    api.get(`/generic/${foreign_key_model}`, {
      params: {
        search_term: inputValue,
        limit: 20
      }
    }).then(response => {
      const options = response.data.items.map(item => ({
        value: item.id,
        label: item[foreign_key_label_field] || `ID ${item.id}`
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
          const fetchedLabel = response.data[foreign_key_label_field] || `ID ${value}`;
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
      />
      {error && <span className="mt-1 text-xs text-red-500">{error}</span>}
    </div>
  );
};

/** * Componente de Input de Senha * Renderiza um campo type="password" com botão de "Mostrar/Ocultar" */
export const PasswordInput = ({ field, value, onChange, error }) => {
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
          value={value || ''}
          onChange={onChange}
          required={required}
          placeholder={placeholder || `Digite ${label.toLowerCase()}...`}
          // Adiciona padding à direita (pr-10) para o ícone não sobrepor o texto
          className={`w-full px-3 py-2 pr-10 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 
                                focus:outline-none focus:ring-blue-500 focus:border-blue-500
                                ${error ? 'border-red-500' : ''}`}
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
export const DateInput = ({ field, value, onChange, error }) => {
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
        value={formattedValue} // <- Usa o valor formatado
        onChange={onChange}    // <- O onChange nativo já envia o formato correto
        required={required}
        // Adiciona padding à direita para o ícone do calendário não sobrepor o texto
        className={`w-full px-3 py-2 pr-9 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 
                    focus:outline-none focus:ring-blue-500 focus:border-blue-500
                    ${error ? 'border-red-500' : ''}`}
      />
      {error && <span className="mt-1 text-xs text-red-500">{error}</span>}
    </div>
  );
};