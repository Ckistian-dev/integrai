import React, { useState, useEffect, useMemo } from 'react';
import { Plus, Trash2, Box, HelpCircle, Layers, Scale, Sparkles, AlertCircle, AlertTriangle } from 'lucide-react';
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

// Helper de avaliação de fórmulas
const evaluateFormula = (formulaList, context) => {
    if (!formulaList || !Array.isArray(formulaList) || formulaList.length === 0) {
        return 0;
    }
    let expression = '';
    for (const token of formulaList) {
        if (token.tipo === 'variavel') {
            const val = context[token.valor] ?? 0;
            expression += String(val);
        } else if (token.tipo === 'numero') {
            expression += String(token.valor);
        } else if (token.tipo === 'operador') {
            if (['+', '-', '*', '/', '(', ')'].includes(token.valor)) {
                expression += token.valor;
            }
        }
    }
    try {
        const cleanExpr = expression.replace(/[^0-9+\-*/().]/g, '');
        if (!cleanExpr) return 0;
        const result = new Function(`return (${cleanExpr})`)();
        return isFinite(result) ? Number(result) : 0;
    } catch (err) {
        return 0;
    }
};

// --- Componentes de UI Internos ---

const InputField = ({ label, name, value, onChange, placeholder, type = "text", obrigatorio = false, icon, ...props }) => (
    <div>
        <label htmlFor={name} className="block text-xs font-semibold text-slate-600 mb-1.5 uppercase tracking-wider flex items-center gap-1.5">
            {icon}
            <span>{label}</span>
            {obrigatorio && <span className="text-red-500 font-bold">*</span>}
        </label>
        <input
            type={type}
            id={name}
            name={name}
            value={value}
            onChange={onChange}
            placeholder={placeholder}
            className="w-full px-3 py-2 border border-slate-200 rounded-lg shadow-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 transition-all text-sm font-medium text-slate-700 bg-white"
            {...props}
        />
    </div>
);

const DropdownField = ({ label, value, onChange, opcoes, icon }) => (
    <div>
        <label className="block text-xs font-semibold text-slate-600 mb-1.5 uppercase tracking-wider flex items-center gap-1.5">
            {icon}
            <span>{label}</span>
        </label>
        <select
            value={value}
            onChange={onChange}
            className="w-full px-3 py-2 border border-slate-200 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 transition-all text-sm font-medium text-slate-700 bg-white"
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
        <div className="relative group border border-slate-200 hover:border-slate-300 rounded-2xl shadow-sm hover:shadow-md transition-all duration-300 bg-white overflow-hidden">
            <div className="absolute left-0 top-0 bottom-0 w-1.5 bg-teal-500"></div>

            <div className="p-5 sm:p-6">
                {/* Cabeçalho do Card */}
                <div className="flex justify-between items-center mb-5 pb-3 border-b border-slate-100">
                    <div className="flex items-center gap-2">
                        <div className="bg-teal-50 text-teal-700 font-bold px-3 py-1 rounded-full text-xs">
                            # {index + 1}
                        </div>
                        <h3 className="font-bold text-slate-800 text-base flex items-center gap-1.5">
                            Regra de Empacotamento
                            <span className="text-xs font-normal text-slate-500 hidden sm:inline">
                                ({condicaoGatilho === 'SEMPRE' ? 'Execução padrão' : 'Execução condicional'})
                            </span>
                        </h3>
                    </div>
                    <button
                        type="button"
                        onClick={() => onRemove(index)}
                        className="text-slate-400 hover:text-red-600 p-1.5 rounded-lg hover:bg-red-50 active:scale-95 transition-all duration-200"
                        title="Remover Regra"
                    >
                        <Trash2 size={18} />
                    </button>
                </div>

                {/* --- Gatilhos e Prioridade --- */}
                <div className="w-full grid grid-cols-1 md:grid-cols-3 gap-5 mb-6">
                    <DropdownField
                        label="Condição do Gatilho"
                        opcoes={OPCOES_GATILHO}
                        value={tipoRegraUI === 'VOLUME_COMPLETO' ? 'VOLUME_COMPLETO' : condicaoGatilho}
                        onChange={(e) => handleChange('condicao_gatilho', e.target.value)}
                        icon={<Layers className="w-3.5 h-3.5 text-slate-400" />}
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
                            icon={<Box className="w-3.5 h-3.5 text-slate-400" />}
                        />
                    ) : condicaoGatilho !== 'SEMPRE' && (
                        <InputField
                            label="Valor do Gatilho"
                            name="valor_gatilho"
                            value={rule.valor_gatilho}
                            onChange={(e) => handleChange('valor_gatilho', e.target.value)}
                            placeholder={condicaoGatilho === 'ENTRE' ? 'Ex: 5,10' : 'Ex: 10'}
                            icon={<HelpCircle className="w-3.5 h-3.5 text-slate-400" />}
                        />
                    )}

                    <InputField
                        label="Prioridade da Execução"
                        name="prioridade"
                        type="number"
                        value={rule.prioridade}
                        onChange={(e) => handleChange('prioridade', e.target.value)}
                        placeholder="Ex: 10"
                        icon={<Sparkles className="w-3.5 h-3.5 text-slate-400" />}
                    />
                </div>

                {/* --- Fórmulas --- */}
                <div className="pt-5 border-t border-slate-100">
                    <div className="mb-4">
                        {tipoRegraUI !== 'VOLUME_COMPLETO' ? (
                            <FormulaBuilder
                                label="Fórmula de Quantidade de Itens neste Volume"
                                formula={rule.formula_itens}
                                onChange={(novaFormula) => handleChange('formula_itens', novaFormula)}
                                variaveisDisponiveis={VARIAVEIS_CONTEXTO}
                            />
                        ) : (
                            <div className="p-3 bg-slate-50 border border-slate-150 rounded-xl">
                                <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wider mb-1.5">Quantidade de Itens neste Volume</label>
                                <div className="w-full h-10 px-3 border border-slate-200 rounded-lg bg-white flex items-center shadow-inner font-mono text-sm font-bold text-teal-700">
                                    {rule.valor_gatilho || '0'}
                                </div>
                                <p className="text-[11px] text-slate-500 mt-1.5 flex items-center gap-1">
                                    <AlertCircle size={12} className="text-teal-600 shrink-0" />
                                    Esta regra de volume completo cria um volume para cada lote de exatamente {rule.valor_gatilho || '...'} itens.
                                </p>
                            </div>
                        )}
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                        <FormulaBuilder label="Altura Final do Volume (cm)" formula={rule.formula_altura} onChange={(novaFormula) => handleChange('formula_altura', novaFormula)} variaveisDisponiveis={VARIAVEIS_CONTEXTO} />
                        <FormulaBuilder label="Largura Final do Volume (cm)" formula={rule.formula_largura} onChange={(novaFormula) => handleChange('formula_largura', novaFormula)} variaveisDisponiveis={VARIAVEIS_CONTEXTO} />
                        <FormulaBuilder label="Comprimento Final do Volume (cm)" formula={rule.formula_comprimento} onChange={(novaFormula) => handleChange('formula_comprimento', novaFormula)} variaveisDisponiveis={VARIAVEIS_CONTEXTO} />
                        <FormulaBuilder label="Peso Final do Volume (kg)" formula={rule.formula_peso} onChange={(novaFormula) => handleChange('formula_peso', novaFormula)} variaveisDisponiveis={VARIAVEIS_CONTEXTO} />
                    </div>
                </div>
            </div>
        </div>
    );
};

// --- Componente Principal do Rule Builder ---

export const RuleBuilderInput = ({ field, value, onChange, error }) => {
    const { label, name, required } = field;
    const [rules, setRules] = useState([]);

    // Estado da simulação
    const [simInputs, setSimInputs] = useState({
        quantidade: 25,
        peso: 0.5,
        altura: 10,
        largura: 15,
        comprimento: 20
    });

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

    const handleSimInputChange = (e) => {
        const { name, value } = e.target;
        setSimInputs(prev => ({ ...prev, [name]: value }));
    };

    // Executa a simulação em tempo real com base no estado atual das regras e dados inseridos
    const simulationResult = useMemo(() => {
        const qty = parseFloat(simInputs.quantidade || 0);
        const weight = parseFloat(simInputs.peso || 0);
        const height = parseFloat(simInputs.altura || 0);
        const width = parseFloat(simInputs.largura || 0);
        const length = parseFloat(simInputs.comprimento || 0);

        if (qty <= 0) return { volumes: [], warning: 'Por favor, insira uma quantidade maior que zero para iniciar.' };

        // Ordena por prioridade decrescente
        const sortedRules = [...rules].map((r, originalIdx) => ({
            ...r,
            originalIndex: originalIdx + 1
        })).sort((a, b) => parseInt(b.prioridade || 0) - parseInt(a.prioridade || 0));

        let qtdRemaining = qty;
        const volumes = [];
        const loopLimit = 100;
        let loopCount = 0;
        let infiniteLoopDetected = false;

        while (qtdRemaining > 0 && loopCount < loopLimit) {
            loopCount++;
            let matchedRule = null;

            for (const rule of sortedRules) {
                const cond = rule.condicao_gatilho;
                const valGatilhoStr = rule.valor_gatilho;
                let valGatilho = 0;
                try {
                    if (valGatilhoStr && cond !== 'ENTRE') {
                        valGatilho = parseFloat(valGatilhoStr);
                    }
                } catch (e) { }

                let match = false;
                if (cond === 'SEMPRE') {
                    match = true;
                } else if (cond === 'MAIOR_IGUAL_A') {
                    match = qtdRemaining >= valGatilho;
                } else if (cond === 'IGUAL_A') {
                    match = qtdRemaining === valGatilho;
                } else if (cond === 'MENOR_QUE') {
                    match = qtdRemaining < valGatilho;
                } else if (cond === 'ENTRE') {
                    try {
                        const parts = String(valGatilhoStr).split(',');
                        if (parts.length === 2) {
                            const vMin = parseFloat(parts[0]);
                            const vMax = parseFloat(parts[1]);
                            match = qtdRemaining >= vMin && qtdRemaining <= vMax;
                        }
                    } catch (e) {
                        match = false;
                    }
                }

                if (match) {
                    matchedRule = rule;
                    break;
                }
            }

            if (matchedRule) {
                const context = {
                    'QTD_A_PROCESSAR': qtdRemaining,
                    'QTD_TOTAL_PEDIDO': qty,
                    'PESO_ITEM_UNICO': weight,
                    'ALTURA_ITEM_UNICO': height,
                    'LARGURA_ITEM_UNICO': width,
                    'COMPRIMENTO_ITEM_UNICO': length,
                    'ACRESCIMO_EMBALAGEM': 0
                };

                let itemsInVol = evaluateFormula(matchedRule.formula_itens, context);
                itemsInVol = Math.max(1.0, itemsInVol);
                itemsInVol = Math.min(itemsInVol, qtdRemaining);

                context['QTD_NESTE_VOLUME'] = itemsInVol;

                const volH = Math.max(0.1, evaluateFormula(matchedRule.formula_altura, context));
                const volW = Math.max(0.1, evaluateFormula(matchedRule.formula_largura, context));
                const volL = Math.max(0.1, evaluateFormula(matchedRule.formula_comprimento, context));
                const volWeight = Math.max(0.01, evaluateFormula(matchedRule.formula_peso, context));

                volumes.push({
                    ruleIndex: matchedRule.originalIndex,
                    ruleType: matchedRule._tipo_regra_ui || 'PADRAO',
                    weight: parseFloat(volWeight.toFixed(3)),
                    width: parseFloat(volW.toFixed(2)),
                    height: parseFloat(volH.toFixed(2)),
                    length: parseFloat(volL.toFixed(2)),
                    products_quantity: Math.floor(itemsInVol),
                    isFallback: false
                });

                const previousRemaining = qtdRemaining;
                qtdRemaining -= itemsInVol;

                // Proteção contra redução nula (loop infinito)
                if (qtdRemaining >= previousRemaining) {
                    infiniteLoopDetected = true;
                    break;
                }
            } else {
                break;
            }
        }

        if (loopCount >= loopLimit || infiniteLoopDetected) {
            return {
                volumes,
                warning: 'Aviso de Loop Infinito: A quantidade a processar não foi reduzida na avaliação das regras. Verifique a fórmula de quantidade de itens.'
            };
        }

        if (qtdRemaining > 0) {
            // Volume de Fallback (Padrão do backend)
            volumes.push({
                ruleIndex: null,
                ruleType: 'FALLBACK',
                weight: parseFloat((weight * qtdRemaining).toFixed(3)),
                width: width,
                height: height,
                length: length,
                products_quantity: Math.floor(qtdRemaining),
                isFallback: true
            });
        }

        return { volumes };
    }, [rules, simInputs]);

    return (
        <div className="md:col-span-2 space-y-6">
            <div>
                <label className="block text-sm font-semibold text-slate-700 mb-1 flex items-center gap-1.5">
                    {label} {required && <span className="text-red-500 font-bold">*</span>}
                </label>
                <p className="text-xs text-slate-500 mb-4">
                    Adicione regras para automatizar o empacotamento lógico de produtos em volumes físicos enviados para transportadoras como a Intelipost.
                </p>
            </div>

            {/* Lista de Regras */}
            <div className="space-y-6">
                {rules.map((rule, index) => (
                    <RuleRow
                        key={rule.id}
                        rule={rule}
                        index={index}
                        onRegraChange={handleRegraChange}
                        onRemove={handleRemoveRule}
                    />
                ))}
            </div>

            {/* Ações das Regras */}
            <div className="flex justify-between items-center pt-2">
                <button
                    type="button"
                    onClick={handleAddRule}
                    className="flex items-center gap-2 px-5 py-2.5 bg-teal-600 hover:bg-teal-700 text-white rounded-xl shadow-sm hover:shadow-md font-semibold transition-all active:scale-95 text-sm"
                >
                    <Plus size={16} />
                    Adicionar Nova Regra
                </button>
            </div>

            {error && <span className="mt-1 text-xs text-red-500 font-bold block">{error}</span>}

            {/* --- VISUAL SIMULATOR SECTION (THE WOW FACTOR) --- */}
            <div className="mt-12 p-6 bg-slate-50 text-slate-800 rounded-3xl shadow-sm border border-slate-200">
                <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-3 mb-6 pb-4 border-b border-slate-200">
                    <div>
                        <h4 className="text-lg font-bold text-teal-700 flex items-center gap-2">
                            <Sparkles className="w-5 h-5 animate-pulse text-teal-500" />
                            Simulador Gráfico de Empacotamento
                        </h4>
                        <p className="text-xs text-slate-500 mt-0.5">
                            Valide matematicamente as fórmulas de empacotamento em tempo real antes de salvar.
                        </p>
                    </div>
                    <div className="bg-teal-50 border border-teal-200 text-teal-700 px-3.5 py-1 rounded-full text-xs font-semibold self-start sm:self-center">
                        Modo Live
                    </div>
                </div>

                {/* Inputs do Simulador */}
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-4 mb-8 bg-white p-4 rounded-2xl border border-slate-200 shadow-sm">
                    <div>
                        <label className="block text-[10px] uppercase font-bold text-slate-500 tracking-wider mb-1.5">Qtd. no Pedido</label>
                        <input
                            type="number"
                            name="quantidade"
                            value={simInputs.quantidade}
                            onChange={handleSimInputChange}
                            min="1"
                            className="w-full bg-white border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 text-slate-800 font-medium transition-all"
                        />
                    </div>
                    <div>
                        <label className="block text-[10px] uppercase font-bold text-slate-500 tracking-wider mb-1.5">Peso do Item (kg)</label>
                        <input
                            type="number"
                            step="any"
                            name="peso"
                            value={simInputs.peso}
                            onChange={handleSimInputChange}
                            className="w-full bg-white border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 text-slate-800 font-medium transition-all"
                        />
                    </div>
                    <div>
                        <label className="block text-[10px] uppercase font-bold text-slate-500 tracking-wider mb-1.5">Altura (cm)</label>
                        <input
                            type="number"
                            step="any"
                            name="altura"
                            value={simInputs.altura}
                            onChange={handleSimInputChange}
                            className="w-full bg-white border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 text-slate-800 font-medium transition-all"
                        />
                    </div>
                    <div>
                        <label className="block text-[10px] uppercase font-bold text-slate-500 tracking-wider mb-1.5">Largura (cm)</label>
                        <input
                            type="number"
                            step="any"
                            name="largura"
                            value={simInputs.largura}
                            onChange={handleSimInputChange}
                            className="w-full bg-white border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 text-slate-800 font-medium transition-all"
                        />
                    </div>
                    <div>
                        <label className="block text-[10px] uppercase font-bold text-slate-500 tracking-wider mb-1.5">Comprimento (cm)</label>
                        <input
                            type="number"
                            step="any"
                            name="comprimento"
                            value={simInputs.comprimento}
                            onChange={handleSimInputChange}
                            className="w-full bg-white border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 text-slate-800 font-medium transition-all"
                        />
                    </div>
                </div>

                {/* Exibição dos Alertas/Erros do simulador */}
                {simulationResult.warning && (
                    <div className="mb-6 p-4 bg-amber-50 border border-amber-200 text-amber-800 rounded-xl flex items-start gap-2.5 text-xs shadow-sm">
                        <AlertTriangle className="w-4 h-4 shrink-0 text-amber-600 mt-0.5" />
                        <div>
                            <span className="font-bold">Aviso:</span> {simulationResult.warning}
                        </div>
                    </div>
                )}

                {/* Resultado Gráfico */}
                <div>
                    <h5 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-4">Volumes que serão gerados ({simulationResult.volumes?.length || 0})</h5>

                    {simulationResult.volumes && simulationResult.volumes.length > 0 ? (
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
                            {simulationResult.volumes.map((vol, index) => {
                                return (
                                    <div
                                        key={index}
                                        className={`relative border p-6 rounded-2xl transition-all duration-300 shadow-sm ${vol.isFallback
                                            ? 'bg-amber-50/15 border-amber-200 hover:border-amber-300 text-slate-700 hover:shadow-md'
                                            : 'bg-white border-slate-200 hover:border-teal-300 text-slate-700 hover:shadow-md'
                                            }`}
                                    >
                                        <div className="flex justify-between items-start gap-2 mb-4">
                                            <div className="flex items-center gap-2.5">
                                                <div className={`p-2 rounded-xl ${vol.isFallback ? 'bg-amber-50 text-amber-600' : 'bg-teal-50 text-teal-600'}`}>
                                                    <Box size={20} />
                                                </div>
                                                <div>
                                                    <div className="text-xs font-bold text-slate-800">Volume #{index + 1}</div>
                                                    <div className="text-[10px] text-slate-400 font-medium">Tipo: CAIXA / BOX</div>
                                                </div>
                                            </div>

                                            {vol.isFallback ? (
                                                <span className="bg-amber-50 border border-amber-200 text-amber-700 px-2.5 py-0.5 rounded-full text-[9px] font-bold">
                                                    Fallback
                                                </span>
                                            ) : (
                                                <span className="bg-teal-50 border border-teal-200 text-teal-700 px-2.5 py-0.5 rounded-full text-[9px] font-bold">
                                                    Regra #{vol.ruleIndex}
                                                </span>
                                            )}
                                        </div>

                                        <div className="space-y-3.5 text-xs">
                                            <div className="flex justify-between text-[11px] border-b border-slate-100 pb-2.5">
                                                <span className="text-slate-500 font-medium">Itens dentro</span>
                                                <span className="font-semibold text-slate-800">{vol.products_quantity} un</span>
                                            </div>
                                            <div className="flex justify-between text-[11px] border-b border-slate-100 pb-2.5">
                                                <span className="text-slate-500 font-medium">Dimensões</span>
                                                <span className="font-semibold text-slate-800">{vol.width} x {vol.height} x {vol.length} cm</span>
                                            </div>
                                            <div className="flex justify-between text-[11px] pb-0.5">
                                                <span className="text-slate-500 font-medium">Peso Total</span>
                                                <span className="font-semibold text-teal-600 flex items-center gap-1">
                                                    <Scale size={13} />
                                                    {vol.weight} kg
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    ) : (
                        <div className="text-center py-10 bg-white border border-dashed border-slate-200 rounded-2xl text-slate-400 text-xs italic shadow-inner">
                            Aguardando simulação... insira uma quantidade e configure as regras.
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};
