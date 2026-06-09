import React, { useState, useEffect } from 'react';
import Select from 'react-select';
import { components } from 'react-select';
import api from '../../api/axiosConfig';
import { Plus, Trash2, Edit2, Check, X, Loader2 } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';

// --- Componente Customizado de Opção (Inline Edit) ---
const CustomOption = (props) => {
  const { data, selectProps } = props;
  const { editingId, setEditingId, onUpdate, onDelete, isAdmin } = selectProps.customProps;
  const isEditing = editingId === data.id;
  const [editValue, setEditValue] = useState(data.label);

  // Sincroniza o valor quando entra em modo de edição
  useEffect(() => {
    if (isEditing) setEditValue(data.label);
  }, [isEditing, data.label]);

  const handleEditClick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setEditingId(data.id);
  };

  const handleCancelClick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setEditingId(null);
  };

  const handleSaveClick = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (editValue && editValue !== data.label) {
      await onUpdate(data.id, editValue);
    }
    setEditingId(null);
  };

  const handleDeleteClick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (window.confirm(`Excluir "${data.label}"?`)) {
      onDelete(data.id);
    }
  };

  return (
    <components.Option {...props}>
      <div className="flex justify-between items-center h-8 group w-full">
        {isEditing && isAdmin ? (
          <div className="flex items-center flex-1 gap-2 w-full" onMouseDown={(e) => e.stopPropagation()}>
            <input
              type="text"
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              className="flex-1 px-2 py-1 border border-blue-300 rounded text-sm text-gray-800 focus:ring-2 focus:ring-blue-500 outline-none transition-all"
              autoFocus
              onClick={(e) => e.stopPropagation()}
              onKeyDown={(e) => {
                e.stopPropagation();
                if (e.key === 'Enter') handleSaveClick(e);
              }}
            />
            <button onClick={handleSaveClick} onMouseDown={(e) => { e.preventDefault(); e.stopPropagation(); }} className="text-green-600 hover:text-green-800 p-1.5 hover:bg-green-50 rounded-md transition-colors" title="Salvar"><Check size={16} /></button>
            <button onClick={handleCancelClick} onMouseDown={(e) => { e.preventDefault(); e.stopPropagation(); }} className="text-red-500 hover:text-red-700 p-1.5 hover:bg-red-50 rounded-md transition-colors" title="Cancelar"><X size={16} /></button>
          </div>
        ) : (
          <>
            <span className="truncate pr-2 flex-1 text-sm">{data.label}</span>
            {isAdmin && (
              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <button onClick={handleEditClick} onMouseDown={(e) => { e.preventDefault(); e.stopPropagation(); }} className="text-blue-600 hover:text-blue-800 p-1.5 hover:bg-blue-50 rounded-md transition-colors" title="Editar">
                  <Edit2 size={14} />
                </button>
                <button onClick={handleDeleteClick} onMouseDown={(e) => { e.preventDefault(); e.stopPropagation(); }} className="text-red-600 hover:text-red-800 p-1.5 hover:bg-red-50 rounded-md transition-colors" title="Excluir">
                  <Trash2 size={14} />
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </components.Option>
  );
};

// --- Componente Customizado de Menu (Footer Add) ---
const CustomMenuList = (props) => {
  const { selectProps } = props;
  const { isAdding, setIsAdding, onCreate, isAdmin } = selectProps.customProps;
  const [newValue, setNewValue] = useState("");

  const handleAddSubmit = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (newValue.trim()) {
      await onCreate(newValue);
      setNewValue("");
      setIsAdding(false);
    }
  };

  return (
    <components.MenuList {...props}>
      {props.children}
      {isAdmin && (
        <div className="border-t border-gray-100 p-2 mt-1 bg-gray-50 rounded-b-md">
          {isAdding ? (
            <div className="flex items-center gap-2 animate-fade-in" onMouseDown={(e) => e.stopPropagation()}>
              <input
                type="text"
                value={newValue}
                onChange={(e) => setNewValue(e.target.value)}
                placeholder="Digite a nova opção..."
                className="flex-1 px-2 py-1.5 border border-blue-300 rounded text-sm focus:ring-2 focus:ring-blue-500 outline-none transition-all bg-white"
                autoFocus
                onKeyDown={(e) => { 
                  e.stopPropagation(); 
                  if(e.key === 'Enter') handleAddSubmit(e); 
                }}
              />
              <button onClick={handleAddSubmit} onMouseDown={(e) => { e.preventDefault(); e.stopPropagation(); }} className="bg-green-600 text-white p-1.5 rounded-md hover:bg-green-700 transition-colors shadow-sm" title="Confirmar">
                <Check size={16} />
              </button>
              <button onClick={() => setIsAdding(false)} onMouseDown={(e) => { e.preventDefault(); e.stopPropagation(); }} className="bg-white border border-gray-300 text-red-500 hover:text-red-700 hover:bg-red-50 p-1.5 rounded-md transition-colors shadow-sm" title="Cancelar">
                <X size={16} />
              </button>
            </div>
          ) : (
            <button
              onClick={(e) => { e.preventDefault(); e.stopPropagation(); setIsAdding(true); }}
              onMouseDown={(e) => { e.preventDefault(); e.stopPropagation(); }}
              className="flex items-center justify-center bg-green-600 text-white hover:bg-green-700 text-sm font-medium w-full px-3 py-2 rounded-md shadow-sm transition-all"
            >
              <Plus size={16} className="mr-2" /> Adicionar nova opção
            </button>
          )}
        </div>
      )}
    </components.MenuList>
  );
};

export const CreatableSelectInput = ({ field, value, onChange, error, modelName, ...props }) => {
  const { user } = useAuth();
  const isAdmin = user?.perfil === 'admin' || user?.perfil === 'Admin';

  const [options, setOptions] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [isAdding, setIsAdding] = useState(false);

  const fetchOptions = async () => {
    if (!modelName) return;
    
    setIsLoading(true);
    try {
      // Busca da nova rota de opções
      const response = await api.get(`/options/${modelName}/${field.name}`);
      const loadedOptions = response.data.map(item => ({
        label: item.valor,
        value: item.valor,
        id: item.id // Guardamos o ID para deletar se necessário
      }));
      setOptions(loadedOptions);
    } catch (err) {
      console.error(`Erro ao carregar opções para ${field.name}:`, err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchOptions();
  }, [modelName, field.name]);

  // --- Ações do CRUD ---

  const handleCreate = async (inputValue) => {
    setIsLoading(true);
    try {
      const res = await api.post('/options', {
        model_name: modelName,
        field_name: field.name,
        valor: inputValue
      });
      await fetchOptions();
      // Seleciona o valor criado
      onChange({
        target: { name: field.name, value: inputValue }
      });
    } catch (err) {
      console.error("Erro ao criar opção:", err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleUpdate = async (id, newValue) => {
    setIsLoading(true);
    try {
      await api.put(`/options/${id}`, { valor: newValue });
      await fetchOptions();
      // Se o valor editado era o selecionado, atualiza o input
      if (value === options.find(o => o.id === id)?.value) {
         onChange({ target: { name: field.name, value: newValue } });
      }
    } catch (err) {
      console.error("Erro ao atualizar:", err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDelete = async (id) => {
    setIsLoading(true);
    try {
      await api.delete(`/options/${id}`);
      await fetchOptions();
      // Se deletou o selecionado, limpa o campo
      if (value === options.find(o => o.id === id)?.value) {
        onChange({ target: { name: field.name, value: '' } });
      }
    } catch (err) {
      console.error("Erro ao deletar:", err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleChange = (newValue) => {
    // newValue é { label: 'X', value: 'X' } ou null
    const val = newValue ? newValue.value : '';
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

  // Determina se o menu deve ser forçado a ficar aberto (durante edição/adição)
  const isInteracting = editingId !== null || isAdding;

  // Estilização customizada para combinar com os outros inputs (Tailwind)
  const customStyles = {
    control: (provided, state) => ({
      ...provided,
      minHeight: '42px',
      borderRadius: '0.375rem', // rounded-md
      borderColor: error ? '#ef4444' : (state.isFocused ? '#3b82f6' : '#d1d5db'), // red-500 : blue-500 : gray-300
      boxShadow: state.isFocused ? '0 0 0 1px #3b82f6' : '0 1px 2px 0 rgb(0 0 0 / 0.05)', // ring-1 blue-500 : shadow-sm
      '&:hover': {
        borderColor: state.isFocused ? '#3b82f6' : '#9ca3af' // blue-500 : gray-400
      },
      backgroundColor: 'white',
    }),
    menu: (provided) => ({
      ...provided,
      zIndex: 50,
      borderRadius: '0.375rem',
      boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)', // shadow-xl
    }),
    option: (provided, state) => ({
      ...provided,
      backgroundColor: state.isSelected ? '#dde2eb' : (state.isFocused ? '#f3f4f6' : 'white'), // blue-100 : gray-100
      color: '#1f2937', // gray-800
      cursor: 'pointer',
      ':active': {
        backgroundColor: '#bfdbfe', // blue-200
      },
    }),
    menuPortal: (base) => ({ ...base, zIndex: 9999 })
  };

  return (
    <div className="mb-4">
      <label className="block text-gray-700 text-sm font-medium mb-2">
        {field.label}
        {field.required && <span className="text-red-500 ml-1">*</span>}
      </label>
      
      <Select
        isClearable
        isDisabled={isLoading}
        isLoading={isLoading}
        menuIsOpen={isInteracting ? true : undefined}
        onChange={handleChange}
        options={options}
        value={selectedOption}
        placeholder={field.placeholder || (isAdmin ? "Selecione ou digite para criar..." : "Selecione...")}
        classNamePrefix="react-select"
        menuPortalTarget={document.body}
        styles={customStyles}
        // Injeta os componentes customizados
        components={{
          Option: CustomOption,
          MenuList: CustomMenuList
        }}
        // Passa as funções para os componentes internos
        customProps={{
          onCreate: handleCreate,
          onUpdate: handleUpdate,
          onDelete: handleDelete,
          editingId,
          setEditingId,
          isAdding,
          setIsAdding,
          isAdmin
        }}
        {...props}
        noOptionsMessage={() => isAdmin ? "Digite para buscar ou criar..." : "Nenhum resultado encontrado"}
      />
      
      {error && <p className="text-red-500 text-xs italic mt-1">{error}</p>}
    </div>
  );
};
