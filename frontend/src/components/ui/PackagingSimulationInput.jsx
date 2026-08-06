import React, { useState, useEffect, useMemo } from 'react';
import { Box, Scale, AlertTriangle } from 'lucide-react';
import { TextInput } from './InputFields';

// Helper de avaliação de fórmulas numéricas
const evaluateFormula = (formulaList, context) => {
  if (!formulaList) return 0;
  let expression = '';

  if (typeof formulaList === 'string') {
    expression = formulaList;
  } else if (Array.isArray(formulaList)) {
    for (const token of formulaList) {
      if (token.tipo === 'variavel') {
        const val = context[token.valor] ?? 0;
        expression += String(val);
      } else if (token.tipo === 'numero' || token.tipo === 'operador') {
        expression += String(token.valor);
      }
    }
  }

  for (const [varName, varVal] of Object.entries(context)) {
    expression = expression.replaceAll(varName, String(varVal ?? 0));
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

// Helper de avaliação de fórmulas de condição (booleana com comparadores)
const evaluateConditionFormula = (formulaVal, context) => {
  if (!formulaVal || (Array.isArray(formulaVal) && formulaVal.length === 0)) {
    return true;
  }
  let expression = '';
  if (typeof formulaVal === 'string') {
    expression = formulaVal;
  } else if (Array.isArray(formulaVal)) {
    expression = formulaVal.map(t => t.valor).join(' ');
  }

  if (!expression || !expression.trim()) return true;

  for (const [varName, varVal] of Object.entries(context)) {
    expression = expression.replaceAll(varName, String(varVal ?? 0));
  }

  // Converte '=' único isolado em '=='
  expression = expression.replace(/(?<![><!=])=(?!=)/g, '==');

  try {
    const cleanExpr = expression.replace(/[^0-9+\-*/().><=!]/g, '');
    if (!cleanExpr) return true;
    const result = new Function(`return Boolean(${cleanExpr})`)();
    return Boolean(result);
  } catch (err) {
    return false;
  }
};

export const PackagingSimulationInput = ({ field, value, onChange, formData, disabled }) => {
  const [simInputs, setSimInputs] = useState({
    quantidade: 25,
    peso: 0.5,
    altura: 10,
    largura: 15,
    comprimento: 20
  });

  useEffect(() => {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      setSimInputs((prev) => ({
        ...prev,
        ...value
      }));
    }
  }, [value]);

  const handleInputChange = (fieldKey, rawVal) => {
    const numVal = rawVal === '' ? '' : Number(rawVal);
    const updated = { ...simInputs, [fieldKey]: numVal };
    setSimInputs(updated);

    if (onChange && field?.name) {
      onChange({
        target: {
          name: field.name,
          value: updated
        }
      });
    }
  };

  const rules = useMemo(() => {
    if (!formData) return [];
    const regrasVal = formData.regras;
    if (regrasVal && typeof regrasVal === 'object' && Array.isArray(regrasVal.rules)) {
      return regrasVal.rules;
    }
    if (Array.isArray(regrasVal)) {
      return regrasVal;
    }
    return [];
  }, [formData?.regras]);

  const simulationResult = useMemo(() => {
    const qty = parseFloat(simInputs.quantidade || 0);
    const weight = parseFloat(simInputs.peso || 0);
    const height = parseFloat(simInputs.altura || 0);
    const width = parseFloat(simInputs.largura || 0);
    const length = parseFloat(simInputs.comprimento || 0);

    if (qty <= 0) {
      return {
        volumes: [],
        warning: 'Informe uma quantidade maior que zero para simular os volumes.'
      };
    }

    if (!rules || rules.length === 0) {
      return {
        volumes: [
          {
            ruleIndex: 1,
            ruleType: 'PADRAO',
            weight: parseFloat((weight * qty).toFixed(3)),
            width: width,
            height: height,
            length: length,
            products_quantity: Math.floor(qty),
            isFallback: false
          }
        ]
      };
    }

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
        const context = {
          'QTD_A_PROCESSAR': qtdRemaining,
          'QTD_TOTAL_PEDIDO': qty,
          'PESO_ITEM_UNICO': weight,
          'ALTURA_ITEM_UNICO': height,
          'LARGURA_ITEM_UNICO': width,
          'COMPRIMENTO_ITEM_UNICO': length,
          'ACRESCIMO_EMBALAGEM': 0
        };

        let match = false;
        if (rule.formula_condicao) {
          match = evaluateConditionFormula(rule.formula_condicao, context);
        } else {
          const cond = rule.condicao_gatilho;
          const valGatilhoStr = rule.valor_gatilho;
          let valGatilho = 0;

          try {
            if (valGatilhoStr && cond !== 'ENTRE') {
              valGatilho = parseFloat(valGatilhoStr);
            }
          } catch (e) { }

          if (cond === 'SEMPRE' || !cond) {
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
        warning: 'Aviso de Loop Infinito: A quantidade a processar não foi reduzida. Verifique as fórmulas.'
      };
    }

    if (qtdRemaining > 0) {
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

  const totals = useMemo(() => {
    const vols = simulationResult.volumes || [];
    const totalVols = vols.length;
    const totalItens = vols.reduce((acc, v) => acc + (v.products_quantity || 0), 0);
    const totalPeso = vols.reduce((acc, v) => acc + (v.weight || 0), 0);
    return {
      totalVols,
      totalItens,
      totalPeso: parseFloat(totalPeso.toFixed(3))
    };
  }, [simulationResult.volumes]);

  return (
    <div className="md:col-span-3 space-y-4">
      {/* Form de Inputs em estilo simples de campos de formulário */}
      <div className="grid grid-cols-1 sm:grid-cols-5 gap-4">
        <div>
          <TextInput
            field={{
              name: 'quantidade',
              label: 'Qtd. no Pedido',
              placeholder: 'Ex: 25',
              type: 'number'
            }}
            value={simInputs.quantidade ?? ''}
            onChange={(e) => handleInputChange('quantidade', e.target.value)}
            disabled={disabled}
          />
        </div>

        <div>
          <TextInput
            field={{
              name: 'peso',
              label: 'Peso do Item (kg)',
              placeholder: 'Ex: 0.5',
              type: 'number'
            }}
            value={simInputs.peso ?? ''}
            onChange={(e) => handleInputChange('peso', e.target.value)}
            disabled={disabled}
          />
        </div>

        <div>
          <TextInput
            field={{
              name: 'altura',
              label: 'Altura (cm)',
              placeholder: 'Ex: 10',
              type: 'number'
            }}
            value={simInputs.altura ?? ''}
            onChange={(e) => handleInputChange('altura', e.target.value)}
            disabled={disabled}
          />
        </div>

        <div>
          <TextInput
            field={{
              name: 'largura',
              label: 'Largura (cm)',
              placeholder: 'Ex: 15',
              type: 'number'
            }}
            value={simInputs.largura ?? ''}
            onChange={(e) => handleInputChange('largura', e.target.value)}
            disabled={disabled}
          />
        </div>

        <div>
          <TextInput
            field={{
              name: 'comprimento',
              label: 'Comprimento (cm)',
              placeholder: 'Ex: 20',
              type: 'number'
            }}
            value={simInputs.comprimento ?? ''}
            onChange={(e) => handleInputChange('comprimento', e.target.value)}
            disabled={disabled}
          />
        </div>
      </div>

      {/* Alerta de Aviso Simples */}
      {simulationResult.warning && (
        <div className="p-3 bg-amber-50 border border-amber-200 text-amber-900 rounded-md flex items-center gap-2 text-xs">
          <AlertTriangle className="w-4 h-4 shrink-0 text-amber-600" />
          <span>{simulationResult.warning}</span>
        </div>
      )}


      {/* Lista Simples de Volumes Resultantes */}
      <div className="space-y-3 pt-2">
        <label className="text-xs font-semibold text-gray-700 uppercase tracking-wider block">
          Resultado dos Volumes ({simulationResult.volumes?.length || 0})
        </label>

        {simulationResult.volumes && simulationResult.volumes.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
            {simulationResult.volumes.map((vol, index) => (
              <div
                key={index}
                className="border border-gray-200 rounded-md p-3 bg-white shadow-2xs space-y-2 text-xs"
              >
                <div className="flex justify-between items-center pb-2 border-b border-gray-100">
                  <div className="flex items-center gap-1.5 font-bold text-gray-800">
                    <Box size={14} className="text-gray-500" />
                    <span>Volume #{index + 1}</span>
                  </div>
                  <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-gray-100 text-gray-700">
                    {`Regra #${vol.ruleIndex || 1}`}
                  </span>
                </div>

                <div className="space-y-1 text-gray-600 text-[11px]">
                  <div className="flex justify-between">
                    <span>Quantidade:</span>
                    <span className="font-semibold text-gray-800">{vol.products_quantity} un</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Dimensões (L x A x C):</span>
                    <span className="font-semibold text-gray-800">{vol.width} x {vol.height} x {vol.length} cm</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Peso do Volume:</span>
                    <span className="font-semibold text-gray-800">{vol.weight} kg</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-6 bg-gray-50 border border-gray-200 rounded-md text-gray-500 text-xs italic">
            Nenhum volume gerado para os parâmetros informados.
          </div>
        )}
      </div>
    </div>
  );
};

export default PackagingSimulationInput;
