import React, { useState } from 'react';
import { X, Plus } from 'lucide-react';

// Componente para renderizar um único "token" (peça) da fórmula
const FormulaToken = ({ token, onRemove }) => {
  let bgColor, textColor, content;

  switch (token.tipo) {
    case 'variavel':
      bgColor = 'bg-blue-100';
      textColor = 'text-blue-800';
      content = token.valor;
      break;
    case 'operador':
      bgColor = 'bg-gray-200';
      textColor = 'text-gray-800';
      content = token.valor;
      break;
    case 'numero':
      bgColor = 'bg-green-100';
      textColor = 'text-green-800';
      content = token.valor;
      break;
    default:
      bgColor = 'bg-red-100';
      textColor = 'text-red-800';
      content = '??';
  }

  return (
    <div className={`flex items-center rounded-md px-2 py-1 text-sm font-mono ${bgColor} ${textColor}`}>
      <span>{content}</span>
      <button
        type="button"
        onClick={onRemove}
        className="ml-1.5 -mr-1 p-0.5 rounded-full hover:bg-black/10"
        title="Remover"
      >
        <X size={12} />
      </button>
    </div>
  );
};

// Componente principal do Construtor de Fórmulas
const FormulaBuilder = ({ label, formula = [], onChange, variaveisDisponiveis }) => {
  const [numberInput, setNumberInput] = useState('');

  const addToken = (tipo, valor) => {
    if (!valor) return;
    onChange([...formula, { tipo, valor }]);
  };

  const handleAddNumber = () => {
    if (numberInput && !isNaN(parseFloat(numberInput))) {
      addToken('numero', numberInput);
      setNumberInput('');
    }
  };

  const removeToken = (index) => {
    onChange(formula.filter((_, i) => i !== index));
  };

  return (
    <div className="space-y-2">
      <label className="block text-sm font-medium text-gray-700">{label}</label>
      
      {/* Área de Exibição da Fórmula */}
      <div className="w-full min-h-[42px] p-2 border border-gray-300 rounded-md bg-gray-50 flex flex-wrap items-center gap-2">
        {formula.length > 0 ? (
          formula.map((token, index) => (
            <FormulaToken key={index} token={token} onRemove={() => removeToken(index)} />
          ))
        ) : (
          <span className="text-sm text-gray-400 px-1">Fórmula vazia</span>
        )}
      </div>

      {/* Controles para Adicionar Tokens */}
      <div className="flex flex-wrap gap-2 items-center">
        <select
          onChange={(e) => addToken('variavel', e.target.value)}
          value=""
          className="flex-grow text-xs px-2 py-1 border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-blue-500"
        >
          <option value="" disabled>Adicionar Variável</option>
          {variaveisDisponiveis.map(v => <option key={v} value={v}>{v}</option>)}
        </select>

        <div className="flex items-center gap-1">
          {['+', '-', '*', '/', '(', ')'].map(op => (
            <button key={op} type="button" onClick={() => addToken('operador', op)} className="px-2 py-1 text-xs bg-gray-200 hover:bg-gray-300 rounded-md font-mono">
              {op}
            </button>
          ))}
        </div>
        
        <div className="flex items-center">
          <input type="number" step="any" value={numberInput} onChange={(e) => setNumberInput(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), handleAddNumber())} placeholder="Nº" className="w-16 text-xs px-2 py-1 border border-gray-300 rounded-l-md focus:outline-none focus:ring-1 focus:ring-blue-500" />
          <button type="button" onClick={handleAddNumber} className="px-2 py-1 text-xs bg-green-600 text-white hover:bg-green-700 rounded-r-md">
            <Plus size={14} />
          </button>
        </div>
      </div>
    </div>
  );
};

export default FormulaBuilder;