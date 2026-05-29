import React, { useState } from 'react';
import { X, Plus, Brackets, Binary, Calculator } from 'lucide-react';

const VAR_FRIENDLY_NAMES = {
  'QTD_A_PROCESSAR': 'Qtd. Restante a Embalar',
  'QTD_TOTAL_PEDIDO': 'Qtd. Total do Pedido',
  'QTD_NESTE_VOLUME': 'Qtd. Neste Volume',
  'PESO_ITEM_UNICO': 'Peso do Item',
  'ALTURA_ITEM_UNICO': 'Altura do Item',
  'LARGURA_ITEM_UNICO': 'Largura do Item',
  'COMPRIMENTO_ITEM_UNICO': 'Comprimento do Item',
  'ACRESCIMO_EMBALAGEM': 'Acréscimo Embalagem'
};

const VAR_BADGE_COLORS = {
  'QTD_A_PROCESSAR': 'bg-blue-50 border-blue-200 text-blue-700 hover:bg-blue-100',
  'QTD_TOTAL_PEDIDO': 'bg-cyan-50 border-cyan-200 text-cyan-700 hover:bg-cyan-100',
  'QTD_NESTE_VOLUME': 'bg-indigo-50 border-indigo-200 text-indigo-700 hover:bg-indigo-100',
  'PESO_ITEM_UNICO': 'bg-orange-50 border-orange-200 text-orange-700 hover:bg-orange-100',
  'ALTURA_ITEM_UNICO': 'bg-purple-50 border-purple-200 text-purple-700 hover:bg-purple-100',
  'LARGURA_ITEM_UNICO': 'bg-fuchsia-50 border-fuchsia-200 text-fuchsia-700 hover:bg-fuchsia-100',
  'COMPRIMENTO_ITEM_UNICO': 'bg-violet-50 border-violet-200 text-violet-700 hover:bg-violet-100',
  'ACRESCIMO_EMBALAGEM': 'bg-pink-50 border-pink-200 text-pink-700 hover:bg-pink-100'
};

// Componente para renderizar um único "token" (peça) da fórmula
const FormulaToken = ({ token, onRemove }) => {
  let bgColorClass, icon, displayValue;

  switch (token.tipo) {
    case 'variavel':
      bgColorClass = VAR_BADGE_COLORS[token.valor] || 'bg-blue-50 border-blue-200 text-blue-700 hover:bg-blue-100';
      icon = <Brackets className="w-3.5 h-3.5" />;
      displayValue = VAR_FRIENDLY_NAMES[token.valor] || token.valor;
      break;
    case 'operador':
      bgColorClass = 'bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100 font-mono font-bold';
      icon = <Calculator className="w-3.5 h-3.5 text-slate-500" />;
      displayValue = token.valor;
      break;
    case 'numero':
      bgColorClass = 'bg-emerald-50 border-emerald-200 text-emerald-700 hover:bg-emerald-100 font-semibold';
      icon = <Binary className="w-3.5 h-3.5 text-emerald-500" />;
      displayValue = token.valor;
      break;
    default:
      bgColorClass = 'bg-red-50 border-red-200 text-red-700 hover:bg-red-100';
      icon = null;
      displayValue = '??';
  }

  return (
    <div className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs transition-all shadow-sm ${bgColorClass}`}>
      {icon}
      <span>{displayValue}</span>
      <button
        type="button"
        onClick={onRemove}
        className="ml-1 p-0.5 rounded-full hover:bg-black/10 transition-colors"
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
    <div className="space-y-3 p-3 bg-slate-50/50 rounded-xl border border-slate-100">
      <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wider">{label}</label>
      
      {/* Área de Exibição da Fórmula */}
      <div className="w-full min-h-[50px] p-2.5 border border-slate-200 rounded-xl bg-white flex flex-wrap items-center gap-2 shadow-inner focus-within:ring-2 focus-within:ring-teal-500/20 transition-all">
        {formula.length > 0 ? (
          formula.map((token, index) => (
            <FormulaToken key={index} token={token} onRemove={() => removeToken(index)} />
          ))
        ) : (
          <span className="text-xs text-slate-400 px-2 italic">Nenhuma fórmula definida (esta dimensão será 0 ou ignorada)</span>
        )}
      </div>

      {/* Controles para Adicionar Tokens */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 pt-1">
        {/* Adicionar Variável */}
        <div>
          <select
            onChange={(e) => {
              addToken('variavel', e.target.value);
              e.target.value = ""; // Reset
            }}
            defaultValue=""
            className="w-full text-xs px-2.5 py-1.5 border border-slate-200 rounded-lg bg-white shadow-sm focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 text-slate-700 font-medium transition-all"
          >
            <option value="" disabled>+ Adicionar Variável</option>
            {variaveisDisponiveis.map(v => (
              <option key={v} value={v}>
                {VAR_FRIENDLY_NAMES[v] || v}
              </option>
            ))}
          </select>
        </div>

        {/* Teclado de Operadores */}
        <div className="flex items-center justify-center gap-1 bg-white border border-slate-200 rounded-lg p-1 shadow-sm">
          {['+', '-', '*', '/', '(', ')'].map(op => (
            <button
              key={op}
              type="button"
              onClick={() => addToken('operador', op)}
              className="flex-1 py-1 text-xs font-semibold font-mono bg-slate-50 hover:bg-slate-100 hover:text-slate-900 rounded-md border border-slate-100 active:scale-95 transition-all text-slate-600"
            >
              {op}
            </button>
          ))}
        </div>
        
        {/* Adicionar Número */}
        <div className="flex items-center shadow-sm rounded-lg overflow-hidden border border-slate-200 bg-white focus-within:ring-2 focus-within:ring-teal-500/20 transition-all">
          <input
            type="number"
            step="any"
            value={numberInput}
            onChange={(e) => setNumberInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), handleAddNumber())}
            placeholder="Digitar valor..."
            className="w-full text-xs px-2.5 py-1.5 focus:outline-none text-slate-700 font-medium placeholder-slate-400"
          />
          <button
            type="button"
            onClick={handleAddNumber}
            className="px-3 py-1.5 text-xs bg-emerald-600 hover:bg-emerald-700 text-white font-semibold transition-colors flex items-center justify-center shrink-0"
            title="Adicionar Número"
          >
            <Plus size={14} />
          </button>
        </div>
      </div>
    </div>
  );
};

export default FormulaBuilder;