import React, { useState, useEffect } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { v4 as uuidv4 } from 'uuid';
import FormulaBuilder from './FormulaBuilder';

// --- Configurações e Helpers ---

const VARIAVEIS_CONTEXTO = [
    'QTD_A_PROCESSAR', 'QTD_TOTAL_PEDIDO', 'QTD_NESTE_VOLUME',
    'PESO_ITEM_UNICO', 'ALTURA_ITEM_UNICO', 'LARGURA_ITEM_UNICO',
    'COMPRIMENTO_ITEM_UNICO', 'ACRESCIMO_EMBALAGEM'
];

const OPCOES_GATILHO = [
    { valor: 'VOLUME_COMPLETO', texto: 'Criar Volume Completo (ex: caixa com 100 un)' },
    { valor: 'SEMPRE', texto: 'Sempre Executar (Regra Padrão/Final)' },
    { valor: 'MAIOR_IGUAL_A', texto: 'Qtd. a Embalar >= (Maior ou Igual a)' },
    { valor: 'IGUAL_A', texto: 'Qtd. a Embalar = (Igual a)' },
    { valor: 'MENOR_QUE', texto: 'Qtd. a Embalar < (Menor que)' },
    { valor: 'ENTRE', texto: 'Qtd. a Embalar ENTRE (ex: 5,10)' },
];

const criarNovaRegra = () => ({
    id: uuidv4(), // ID temporário para o React
    prioridade: 10,
    condicao_gatilho: 'SEMPRE',
    valor_gatilho: '',
    formula_itens: [{ tipo: 'variavel', valor: 'QTD_A_PROCESSAR' }],
    formula_altura: [{ tipo: 'variavel', valor: 'ALTURA_ITEM_UNICO' }],
    formula_largura: [{ tipo: 'variavel', valor: 'LARGURA_ITEM_UNICO' }],
    formula_comprimento: [{ tipo: 'variavel', valor: 'COMPRIMENTO_ITEM_UNICO' }],
    formula_peso: [
        { tipo: 'variavel', valor: 'PESO_ITEM_UNICO' },
        { tipo: 'operador', valor: '*' },
        { tipo: 'variavel', valor: 'QTD_NESTE_VOLUME' }
    ],
    _tipo_regra_ui: 'PADRAO' // Campo auxiliar apenas para controle da interface
});

// --- Componentes de UI Internos ---

const InputField = ({ label, name, value, onChange, placeholder, type = "text", obrigatorio = false, ...props }) => (
    <div>
        <label htmlFor={name} className="block text-sm font-medium text-gray-700 mb-1">
            {label} {obrigatorio && <span className="text-red-500">*</span>}
        </label>
        <input
            type={type}
            id={name}
            name={name}
            value={value}
            onChange={onChange}
            placeholder={placeholder}
            className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            {...props}
        />
    </div>
);

const DropdownField = ({ label, value, onChange, opcoes }) => (
    <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
        <select
            value={value}
            onChange={onChange}
            className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
        >
            {opcoes.map(opt => <option key={opt.valor} value={opt.valor}>{opt.texto}</option>)}
        </select>
    </div>
);

// --- Componente para uma Única Regra ---

const RuleRow = ({ rule, index, onRegraChange, onRemove }) => {
    const handleChange = (campo, valor) => {
        onRegraChange(index, campo, valor);
    };

    const tipoRegraUI = rule._tipo_regra_ui;
    const condicaoGatilho = rule.condicao_gatilho;

    return (
        <div className="p-4 border border-gray-200 rounded-lg shadow-sm bg-white">
            <div className="flex justify-between items-start mb-4">
                <h3 className="font-bold text-lg text-teal-700">Regra #{index + 1}</h3>
                <button type="button" onClick={() => onRemove(index)} className="text-red-500 hover:text-red-700 p-1" title="Remover Regra">
                    <Trash2 size={18} />
                </button>
            </div>

            {/* --- Gatilhos e Prioridade --- */}
            <div className="w-full grid grid-cols-1 md:grid-cols-3 gap-6 mb-4">
                <DropdownField
                    label="Condição do Gatilho"
                    opcoes={OPCOES_GATILHO}
                    value={tipoRegraUI === 'VOLUME_COMPLETO' ? 'VOLUME_COMPLETO' : condicaoGatilho}
                    onChange={(e) => handleChange('condicao_gatilho', e.target.value)}
                />

                {tipoRegraUI === 'VOLUME_COMPLETO' ? (
                    <InputField
                        label="Itens no Volume Completo"
                        name="valor_gatilho"
                        value={rule.valor_gatilho}
                        onChange={(e) => handleChange('valor_gatilho', e.target.value)}
                        placeholder="Ex: 100"
                        obrigatorio
                        type="number"
                    />
                ) : condicaoGatilho !== 'SEMPRE' && (
                    <InputField
                        label="Valor do Gatilho"
                        name="valor_gatilho"
                        value={rule.valor_gatilho}
                        onChange={(e) => handleChange('valor_gatilho', e.target.value)}
                        placeholder={condicaoGatilho === 'ENTRE' ? 'Ex: 5,10' : 'Ex: 10'}
                    />
                )}

                <InputField
                    label="Prioridade (maior executa primeiro)"
                    name="prioridade"
                    type="number"
                    value={rule.prioridade}
                    onChange={(e) => handleChange('prioridade', e.target.value)}
                />
            </div>

            {/* --- Fórmulas --- */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4 pt-4 border-t">
                {tipoRegraUI !== 'VOLUME_COMPLETO' ? (
                    <div className="md:col-span-2">
                        <FormulaBuilder
                            label="Fórmula de Itens no Volume"
                            formula={rule.formula_itens}
                            onChange={(novaFormula) => handleChange('formula_itens', novaFormula)}
                            variaveisDisponiveis={VARIAVEIS_CONTEXTO}
                        />
                    </div>
                ) : (
                    <div className="md:col-span-2">
                        <label className="block text-sm font-medium text-gray-700 mb-1">Fórmula de Itens no Volume</label>
                        <div className="w-full min-h-[42px] p-2 border border-gray-200 rounded-md bg-gray-100 flex items-center">
                            <span className="text-sm text-gray-600 font-mono">{rule.valor_gatilho || '...'}</span>
                        </div>
                        <p className="text-xs text-gray-500 mt-1">Este valor é definido automaticamente com base nos "Itens no Volume Completo".</p>
                    </div>
                )}
                <FormulaBuilder label="Fórmula da Altura (cm)" formula={rule.formula_altura} onChange={(novaFormula) => handleChange('formula_altura', novaFormula)} variaveisDisponiveis={VARIAVEIS_CONTEXTO} />
                <FormulaBuilder label="Fórmula da Largura (cm)" formula={rule.formula_largura} onChange={(novaFormula) => handleChange('formula_largura', novaFormula)} variaveisDisponiveis={VARIAVEIS_CONTEXTO} />
                <FormulaBuilder label="Fórmula do Comprimento (cm)" formula={rule.formula_comprimento} onChange={(novaFormula) => handleChange('formula_comprimento', novaFormula)} variaveisDisponiveis={VARIAVEIS_CONTEXTO} />
                <FormulaBuilder label="Fórmula do Peso (kg)" formula={rule.formula_peso} onChange={(novaFormula) => handleChange('formula_peso', novaFormula)} variaveisDisponiveis={VARIAVEIS_CONTEXTO} />
            </div>
        </div>
    );
};

// --- Componente Principal do Rule Builder ---

// Componente principal do Rule Builder
export const RuleBuilderInput = ({ field, value, onChange, error }) => {
    const { label, name, required } = field;
    const [rules, setRules] = useState([]);

    // Popula o estado interno quando o 'value' (da prop do formulário) muda
    useEffect(() => {
        let initialRules = [];
        if (value && typeof value === 'object' && Array.isArray(value.rules)) {
            initialRules = value.rules.map(r => {
                const isVolumeCompleto = r.condicao_gatilho === 'MAIOR_IGUAL_A' &&
                    Array.isArray(r.formula_itens) &&
                    r.formula_itens.length === 1 &&
                    r.formula_itens[0].tipo === 'numero' &&
                    String(r.formula_itens[0].valor) === String(r.valor_gatilho);

                return {
                    ...criarNovaRegra(), // Garante que todos os campos existam
                    ...r,
                    id: r.id || uuidv4(),
                    valor_gatilho: r.valor_gatilho ?? '',
                    _tipo_regra_ui: isVolumeCompleto ? 'VOLUME_COMPLETO' : 'PADRAO'
                };
            });
        }
        // Se não houver regras, começa com uma regra padrão
        setRules(initialRules.length > 0 ? initialRules : [criarNovaRegra()]);
    }, [value]);

    // Propaga as mudanças para o GenericForm
    const triggerOnChange = (updatedRules) => {
        // Remove os campos auxiliares da UI antes de salvar
        const rulesToSave = updatedRules.map(({ id, _tipo_regra_ui, ...rest }) => {
            if (rest.condicao_gatilho === 'SEMPRE' || rest.valor_gatilho === '') {
                rest.valor_gatilho = null;
            }
            return rest;
        });

        onChange({
            target: {
                name: name,
                value: { rules: rulesToSave },
            },
        });
    };

    const handleRegraChange = (index, campo, valor) => {
        const novasRegras = [...rules];
        const regraAtual = { ...novasRegras[index] };

        if (campo === 'condicao_gatilho') {
            if (valor === 'VOLUME_COMPLETO') {
                regraAtual._tipo_regra_ui = 'VOLUME_COMPLETO';
                regraAtual.condicao_gatilho = 'MAIOR_IGUAL_A';
                if (regraAtual.valor_gatilho && !isNaN(parseInt(regraAtual.valor_gatilho))) {
                    regraAtual.formula_itens = [{ tipo: 'numero', valor: String(regraAtual.valor_gatilho) }];
                }
            } else {
                regraAtual._tipo_regra_ui = 'PADRAO';
                regraAtual.condicao_gatilho = valor;
                if (valor === 'SEMPRE') {
                    regraAtual.valor_gatilho = '';
                    regraAtual.formula_itens = [{ tipo: 'variavel', valor: 'QTD_A_PROCESSAR' }];
                }
            }
        } else if (campo === 'valor_gatilho' && regraAtual._tipo_regra_ui === 'VOLUME_COMPLETO') {
            regraAtual.valor_gatilho = valor;
            regraAtual.formula_itens = (valor && !isNaN(parseInt(valor))) ? [{ tipo: 'numero', valor: String(valor) }] : [];
        } else {
            regraAtual[campo] = valor;
        }

        novasRegras[index] = regraAtual;
        setRules(novasRegras);
        triggerOnChange(novasRegras);
    };

    const handleAddRule = () => {
        const updatedRules = [...rules, criarNovaRegra()];
        setRules(updatedRules);
        triggerOnChange(updatedRules);
    };

    const handleRemoveRule = (index) => {
        if (rules.length <= 1) {
            alert('É necessário ter pelo menos uma regra.');
            return;
        }
        const updatedRules = rules.filter((_, i) => i !== index);
        setRules(updatedRules);
        triggerOnChange(updatedRules);
    };

    return (
        <div className="md:col-span-2">
            <label className="mb-1.5 text-sm font-medium text-gray-700">
                {label} {required && <span className="text-red-500">*</span>}
            </label>
            <div className="space-y-8">
                {rules.map((rule, index) => (
                    <RuleRow
                        key={rule.id}
                        rule={rule}
                        index={index}
                        onRegraChange={handleRegraChange}
                        onRemove={handleRemoveRule}
                    />
                ))}
                <div className="mt-4">
                    <button
                        type="button"
                        onClick={handleAddRule}
                        className="flex items-center gap-2 px-4 py-2 bg-teal-50 text-teal-800 rounded-md hover:bg-teal-100 border border-teal-200 font-semibold"
                    >
                        <Plus size={16} />
                        Adicionar Nova Regra
                    </button>
                </div>
            </div>
            {error && <span className="mt-1 text-xs text-red-500">{error}</span>}
        </div>
    );
};
