import React, { useState, useEffect } from 'react';
import CreatableSelect from 'react-select/creatable';
import api from '../../api/axiosConfig';

export const CreatableSelectInput = ({ field, value, onChange, error, modelName }) => {
  const [options, setOptions] = useState([]);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    const fetchOptions = async () => {
      if (!modelName) return;
      
      setIsLoading(true);
      try {
        // Busca os valores distintos já cadastrados para este campo
        const response = await api.get(`/generic/${modelName}/distinct/${field.name}`);
        const loadedOptions = response.data.map(item => ({
          label: item,
          value: item
        }));
        setOptions(loadedOptions);
      } catch (err) {
        console.error(`Erro ao carregar opções para ${field.name}:`, err);
      } finally {
        setIsLoading(false);
      }
    };

    fetchOptions();
  }, [modelName, field.name]);

  const handleChange = (newValue) => {
    // newValue é { label: 'X', value: 'X' } ou null
    const val = newValue ? newValue.value : '';
    
    // Se o usuário criou uma nova opção, adiciona à lista local temporariamente
    // (Ela será salva no banco quando o formulário for submetido)
    if (newValue && !options.find(opt => opt.value === val)) {
      setOptions(prev => [...prev, newValue]);
    }

    onChange({
      target: {
        name: field.name,
        value: val
      }
    });
  };

  // Converte o valor string atual para o formato do react-select
  const selectedOption = value 
    ? { label: value, value: value }
    : null;

  return (
    <div className="mb-4">
      <label className="block text-gray-700 text-sm font-medium mb-2">
        {field.label}
        {field.required && <span className="text-red-500 ml-1">*</span>}
      </label>
      
      <CreatableSelect
        isClearable
        isDisabled={isLoading}
        isLoading={isLoading}
        onChange={handleChange}
        onCreateOption={(inputValue) => {
            // Handler específico para criação
            const newOption = { label: inputValue, value: inputValue };
            handleChange(newOption);
        }}
        options={options}
        value={selectedOption}
        placeholder="Selecione ou digite..."
        classNamePrefix="react-select"
        className={error ? "border-red-500 rounded" : ""}
        menuPortalTarget={document.body}
        styles={{ menuPortal: (base) => ({ ...base, zIndex: 9999 }) }}
        formatCreateLabel={(inputValue) => `Criar "${inputValue}"`}
      />
      
      {error && <p className="text-red-500 text-xs italic mt-1">{error}</p>}
    </div>
  );
};
