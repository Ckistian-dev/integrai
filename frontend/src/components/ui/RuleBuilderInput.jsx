import React, { useState, useEffect } from 'react';
import { Plus, Trash2, ChevronUp, ChevronDown } from 'lucide-react';
import { v4 as uuidv4 } from 'uuid';
import { FormulaBuilderInput } from './InputFields';

const VARIAVEIS_CONTEXTO = [
    'QTD_A_PROCESSAR', 'QTD_TOTAL_PEDIDO', 'QTD_NESTE_VOLUME',
    'PESO_ITEM_UNICO', 'ALTURA_ITEM_UNICO', 'LARGURA_ITEM_UNICO',
    'COMPRIMENTO_ITEM_UNICO', 'ACRESCIMO_EMBALAGEM'
];

const criarNovaRegra = () => ({
    id: uuidv4(),
    prioridade: 10,
    formula_condicao: [
        { tipo: 'variavel', valor: 'QTD_A_PROCESSAR' },
        { tipo: 'operador', valor: '>' },
        { tipo: 'numero', valor: '0' }
    ],
    formula_itens: [
        { tipo: 'variavel', valor: 'QTD_A_PROCESSAR' },
        { tipo: 'operador', valor: '-' },
        { tipo: 'numero', valor: '1' }
    ],
    formula_altura: [{ tipo: 'variavel', valor: 'ALTURA_ITEM_UNICO' }],
    formula_largura: [{ tipo: 'variavel', valor: 'LARGURA_ITEM_UNICO' }],
    formula_comprimento: [{ tipo: 'variavel', valor: 'COMPRIMENTO_ITEM_UNICO' }],
    formula_peso: [
        { tipo: 'variavel', valor: 'PESO_ITEM_UNICO' },
        { tipo: 'operador', valor: '*' },
        { tipo: 'variavel', valor: 'QTD_NESTE_VOLUME' }
    ]
});

const RuleRow = ({ rule, index, totalRules, onRegraChange, onRemove, onMoveUp, onMoveDown }) => {
    const handleChange = (campo, valor) => {
        onRegraChange(index, campo, valor);
    };

    const showHeader = totalRules > 1;

    return (
        <div className="pb-5 border-b border-gray-200/70 last:border-b-0 space-y-3">
            {/* Cabeçalho da Regra (Só aparece se houver mais de uma regra) */}
            {showHeader && (
                <div className="flex justify-between items-center pb-0.5">
                    <div className="flex items-center gap-2">
                        <span className="text-gray-500 font-semibold text-xs">
                            Regra #{index + 1}
                        </span>
                    </div>

                    <div className="flex items-center gap-1">
                        <button
                            type="button"
                            onClick={() => onMoveUp(index)}
                            disabled={index === 0}
                            className="p-1 text-gray-400 hover:text-gray-700 disabled:opacity-20 transition-colors cursor-pointer disabled:cursor-not-allowed"
                            title="Mover para cima"
                        >
                            <ChevronUp size={16} />
                        </button>
                        <button
                            type="button"
                            onClick={() => onMoveDown(index)}
                            disabled={index === totalRules - 1}
                            className="p-1 text-gray-400 hover:text-gray-700 disabled:opacity-20 transition-colors cursor-pointer disabled:cursor-not-allowed"
                            title="Mover para baixo"
                        >
                            <ChevronDown size={16} />
                        </button>

                        <button
                            type="button"
                            onClick={() => onRemove(index)}
                            className="text-gray-400 hover:text-red-600 p-1 rounded-md transition-colors cursor-pointer ml-1"
                            title="Remover Regra"
                        >
                            <Trash2 size={16} />
                        </button>
                    </div>
                </div>
            )}

            {/* --- GRID DE 3 LINHAS E 2 COLUNAS (6 campos) --- */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* LINHA 1 */}
                <FormulaBuilderInput
                    label="Condição"
                    formula={rule.formula_condicao || [{ tipo: 'variavel', valor: 'QTD_A_PROCESSAR' }, { tipo: 'operador', valor: '>' }, { tipo: 'numero', valor: '0' }]}
                    onChange={(novaFormula) => handleChange('formula_condicao', novaFormula)}
                    variaveisDisponiveis={VARIAVEIS_CONTEXTO}
                />
                <FormulaBuilderInput
                    label="Decremento de Itens no Volume"
                    formula={rule.formula_itens || [{ tipo: 'variavel', valor: 'QTD_A_PROCESSAR' }, { tipo: 'operador', valor: '-' }, { tipo: 'numero', valor: '1' }]}
                    onChange={(novaFormula) => handleChange('formula_itens', novaFormula)}
                    variaveisDisponiveis={VARIAVEIS_CONTEXTO}
                />

                {/* LINHA 2 */}
                <FormulaBuilderInput
                    label="Altura do Volume (cm)"
                    formula={rule.formula_altura}
                    onChange={(novaFormula) => handleChange('formula_altura', novaFormula)}
                    variaveisDisponiveis={VARIAVEIS_CONTEXTO}
                />
                <FormulaBuilderInput
                    label="Largura do Volume (cm)"
                    formula={rule.formula_largura}
                    onChange={(novaFormula) => handleChange('formula_largura', novaFormula)}
                    variaveisDisponiveis={VARIAVEIS_CONTEXTO}
                />

                {/* LINHA 3 */}
                <FormulaBuilderInput
                    label="Comprimento do Volume (cm)"
                    formula={rule.formula_comprimento}
                    onChange={(novaFormula) => handleChange('formula_comprimento', novaFormula)}
                    variaveisDisponiveis={VARIAVEIS_CONTEXTO}
                />
                <FormulaBuilderInput
                    label="Peso do Volume (kg)"
                    formula={rule.formula_peso}
                    onChange={(novaFormula) => handleChange('formula_peso', novaFormula)}
                    variaveisDisponiveis={VARIAVEIS_CONTEXTO}
                />
            </div>
        </div>
    );
};

export const RuleBuilderInput = ({ field, value, onChange, error }) => {
    const { name } = field;
    const [rules, setRules] = useState([criarNovaRegra()]);

    useEffect(() => {
        if (value && typeof value === 'object' && Array.isArray(value.rules) && value.rules.length > 0) {
            const incomingRules = value.rules.map((r, i) => {
                let defaultCond = r.formula_condicao;
                if (!defaultCond || (Array.isArray(defaultCond) && defaultCond.length === 0)) {
                    const cond = r.condicao_gatilho;
                    const valStr = String(r.valor_gatilho || '0');
                    if (cond === 'MAIOR_IGUAL_A') {
                        defaultCond = [{ tipo: 'variavel', valor: 'QTD_A_PROCESSAR' }, { tipo: 'operador', valor: '>=' }, { tipo: 'numero', valor: valStr }];
                    } else if (cond === 'IGUAL_A') {
                        defaultCond = [{ tipo: 'variavel', valor: 'QTD_A_PROCESSAR' }, { tipo: 'operador', valor: '==' }, { tipo: 'numero', valor: valStr }];
                    } else if (cond === 'MENOR_QUE') {
                        defaultCond = [{ tipo: 'variavel', valor: 'QTD_A_PROCESSAR' }, { tipo: 'operador', valor: '<' }, { tipo: 'numero', valor: valStr }];
                    } else {
                        defaultCond = [{ tipo: 'variavel', valor: 'QTD_A_PROCESSAR' }, { tipo: 'operador', valor: '>' }, { tipo: 'numero', valor: '0' }];
                    }
                }

                const stableId = r.id || (rules[i] ? rules[i].id : uuidv4());

                return {
                    ...criarNovaRegra(),
                    ...r,
                    id: stableId,
                    formula_condicao: defaultCond
                };
            });

            const currentSerialized = JSON.stringify(rules.map(({ _tipo_regra_ui, ...rest }) => rest));
            const incomingSerialized = JSON.stringify(incomingRules.map(({ _tipo_regra_ui, ...rest }) => rest));

            if (currentSerialized !== incomingSerialized) {
                setRules(incomingRules);
            }
        } else if (!value || !value.rules || value.rules.length === 0) {
            if (rules.length === 0) {
                const initial = [criarNovaRegra()];
                setRules(initial);
                triggerOnChange(initial);
            }
        }
    }, [value]);

    const triggerOnChange = (updatedRules) => {
        const total = updatedRules.length;
        const rulesToSave = updatedRules.map(({ _tipo_regra_ui, ...rest }, idx) => {
            return {
                ...rest,
                prioridade: (total - idx) * 10
            };
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
        novasRegras[index] = {
            ...novasRegras[index],
            [campo]: valor
        };
        setRules(novasRegras);
        triggerOnChange(novasRegras);
    };

    const handleMoveUp = (index) => {
        if (index <= 0) return;
        const newRules = [...rules];
        const temp = newRules[index];
        newRules[index] = newRules[index - 1];
        newRules[index - 1] = temp;
        setRules(newRules);
        triggerOnChange(newRules);
    };

    const handleMoveDown = (index) => {
        if (index >= rules.length - 1) return;
        const newRules = [...rules];
        const temp = newRules[index];
        newRules[index] = newRules[index + 1];
        newRules[index + 1] = temp;
        setRules(newRules);
        triggerOnChange(newRules);
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
        <div className="md:col-span-3 space-y-4">
            {/* Lista de Regras */}
            <div className="space-y-4">
                {rules.map((rule, index) => (
                    <RuleRow
                        key={rule.id}
                        rule={rule}
                        index={index}
                        totalRules={rules.length}
                        onRegraChange={handleRegraChange}
                        onRemove={handleRemoveRule}
                        onMoveUp={handleMoveUp}
                        onMoveDown={handleMoveDown}
                    />
                ))}
            </div>

            {/* Botão de Adicionar Nova Regra */}
            <div>
                <button
                    type="button"
                    onClick={handleAddRule}
                    className="w-full py-2.5 px-4 border border-dashed border-gray-300 hover:border-teal-600 bg-gray-50/60 hover:bg-teal-50/40 text-gray-600 hover:text-teal-700 rounded-md text-xs font-semibold flex items-center justify-center gap-2 transition-all shadow-2xs group cursor-pointer"
                >
                    <div className="p-1 rounded bg-white group-hover:bg-teal-600 text-gray-500 group-hover:text-white border border-gray-200 group-hover:border-teal-600 transition-colors shadow-2xs">
                        <Plus className="w-3.5 h-3.5" />
                    </div>
                    <span>Adicionar Nova Regra de Empacotamento</span>
                </button>
            </div>

            {error && <span className="mt-1 text-xs text-red-500 font-bold block">{error}</span>}
        </div>
    );
};

export default RuleBuilderInput;
