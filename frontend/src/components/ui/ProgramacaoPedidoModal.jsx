// src/components/ui/ProgramacaoPedidoModal.jsx

import React, { Fragment, useState, useEffect } from 'react';
import { Transition, Dialog } from '@headlessui/react';
import { X, Loader2, ChevronDown, ChevronUp, Box } from 'lucide-react';
import api from '../../api/axiosConfig'; // Ajuste o caminho se necessário

const ProgramacaoPedidoModal = ({
  isOpen,
  onClose,
  pedido, // O pedido COMPLETO, com o array de 'itens'
  onSave,  // Função para salvar, que virá da GenericList
}) => {
  // Estados internos do formulário
  const [dataFinalizacao, setDataFinalizacao] = useState('');
  const [ordemFinalizacao, setOrdemFinalizacao] = useState('1.0');
  const [itensState, setItensState] = useState([]);
  const [isSaving, setIsSaving] = useState(false);
  const [isLoadingItems, setIsLoadingItems] = useState(false);
  const [expandedItems, setExpandedItems] = useState({}); // Controla quais linhas estão expandidas para seleção de lote

  // Efeito para popular o formulário quando o pedido é carregado
  useEffect(() => {
    if (pedido && pedido.itens) {
      const loadDetails = async () => {
        setIsLoadingItems(true);
        // Formata a data para o input (YYYY-MM-DD)
        const today = new Date().toISOString().split('T')[0];
        setDataFinalizacao(today);
        
        // Garante que a ordem de finalização tenha um valor padrão
        setOrdemFinalizacao(pedido.ordem_finalizacao || '1.0');

        // Busca detalhes dos produtos e verifica estoque
        const enrichedItens = await Promise.all(pedido.itens.map(async (item) => {
          const qtdTotal = Number(item.quantidade) || 0;
          let aRetirar = item.numero_a_retirar !== undefined ? Number(item.numero_a_retirar) : 0;
          let aProduzir = item.numero_a_produzir !== undefined ? Number(item.numero_a_produzir) : 0;

          // Se não houver definição prévia (ambos 0), sugere produzir tudo por padrão
          if (aRetirar === 0 && aProduzir === 0 && qtdTotal > 0) {
            aProduzir = qtdTotal;
          }

          let descricao = item.descricao || 'Carregando...';
          let temEstoque = false;
          let estoqueOpcoes = [];
          let retiradasIniciais = {}; // Mapa: { id_estoque: quantidade }

          if (item.id_produto) {
            try {
              // 1. Busca descrição do produto
              const prodRes = await api.get(`/generic/produtos/${item.id_produto}`);
              descricao = `${prodRes.data.sku} - ${prodRes.data.descricao}`;

              // 2. Busca TODOS os lotes disponíveis deste produto
              const stockRes = await api.get(`/generic/estoque`, { 
                params: { id_produto: item.id_produto, situacao: 'disponivel', limit: 100 } 
              });
              
              if (stockRes.data.total_count > 0) {
                temEstoque = true;
                estoqueOpcoes = stockRes.data.items;
              }
            } catch (err) {
              console.error("Erro ao carregar detalhes", err);
              descricao = "Erro ao carregar produto";
            }
          }

          return {
            ...item,
            descricao,
            quantidade: qtdTotal,
            numero_a_retirar: aRetirar,
            numero_a_produzir: aProduzir,
            // Novos campos para controle de lote
            temEstoque, // Flag para validação
            estoqueOpcoes, // Array com os lotes disponíveis
            retiradasSelecionadas: retiradasIniciais, // Objeto para controlar quanto tira de cada lote
          };
        }));

        setItensState(enrichedItens);
        setIsLoadingItems(false);
        setExpandedItems({});
      };

      loadDetails();

    } else {
      // Reseta o formulário se o pedido for nulo
      setDataFinalizacao('');
      setOrdemFinalizacao('1.0');
      setItensState([]);
      setExpandedItems({});
    }
  }, [pedido]); // Re-executa quando o 'pedido' (prop) muda

  /**
   * Alterna a visualização dos lotes de um item
   */
  const toggleExpandItem = (index) => {
    setExpandedItems(prev => ({
      ...prev,
      [index]: !prev[index]
    }));
  };

  /**
   * Manipula a seleção de quantidade em um lote específico
   */
  const handleLoteChange = (itemIndex, estoqueId, qtdStr) => {
    const qtd = qtdStr === '' ? 0 : Number(qtdStr);
    const newItens = [...itensState];
    const item = newItens[itemIndex];

    // Atualiza o mapa de retiradas deste item
    const novasRetiradas = { ...item.retiradasSelecionadas };
    if (qtd > 0) {
      novasRetiradas[estoqueId] = qtd;
    } else {
      delete novasRetiradas[estoqueId];
    }

    // Soma o total a retirar baseado nos lotes selecionados
    const totalRetirar = Object.values(novasRetiradas).reduce((acc, curr) => acc + curr, 0);

    // Calcula o produzir (Total - Retirar)
    let produzir = item.quantidade - totalRetirar;
    if (produzir < 0) produzir = 0;

    // Atualiza o estado do item
    newItens[itemIndex] = {
      ...item,
      retiradasSelecionadas: novasRetiradas,
      numero_a_retirar: totalRetirar,
      numero_a_produzir: produzir
    };

    setItensState(newItens);
  };

  /**
   * Manipula a mudança nos inputs dos itens
   */
  const handleItemChange = (index, field, value) => {
    const newItens = [...itensState];
    const currentItem = newItens[index];
    const total = currentItem.quantidade;

    if (field === 'numero_a_produzir') {
      const val = value === '' ? 0 : Number(value);
      const produzir = isNaN(val) ? 0 : val;

      // Calcula automaticamente o quanto retirar (Total - Produzir)
      // Nota: Se alterar manualmente o produzir, precisamos ver como fica a retirada dos lotes.
      // Por simplicidade, se o usuário forçar "Produzir", reduzimos o "Retirar", mas o usuário deve ajustar os lotes manualmente se houver conflito.
      let retirar = total - produzir;
      if (retirar < 0) retirar = 0;

      newItens[index] = {
        ...currentItem,
        numero_a_produzir: produzir,
        numero_a_retirar: retirar,
      };
    }

    setItensState(newItens);
  };

  /**
   * Valida e envia o formulário para a GenericList
   */
  const handleConfirmSave = async () => {
    setIsSaving(true);
    
    // Validação simples (pode ser melhorada)
    let hasError = false;
    itensState.forEach(item => {
      if ((item.numero_a_retirar + item.numero_a_produzir) !== item.quantidade) {
         hasError = true;
         alert(`Erro no item "${item.descricao}": A soma de 'A Retirar' (${item.numero_a_retirar}) e 'A Produzir' (${item.numero_a_produzir}) deve ser igual à Quantidade Total (${item.quantidade}).`);
      }
      
      // Validação extra: Se disse que vai retirar X, tem que ter selecionado X nos lotes
      const totalSelecionadoLotes = Object.values(item.retiradasSelecionadas || {}).reduce((a, b) => a + b, 0);
      if (item.temEstoque && item.numero_a_retirar > 0 && totalSelecionadoLotes !== item.numero_a_retirar) {
         hasError = true;
         alert(`Erro no item "${item.descricao}": Você definiu retirar ${item.numero_a_retirar}, mas selecionou ${totalSelecionadoLotes} nos lotes. Por favor, ajuste a seleção de lotes.`);
      }
    });

    if (hasError) {
      setIsSaving(false);
      return;
    }

    // Prepara o array de retiradas detalhadas para o backend (reservas)
    const retiradasDetalhadas = [];
    itensState.forEach(item => {
      if (item.retiradasSelecionadas) {
        Object.entries(item.retiradasSelecionadas).forEach(([estoqueId, qtd]) => {
          if (qtd > 0) {
            // Encontra o objeto de estoque original para pegar detalhes se necessário
            const estoqueOrigem = item.estoqueOpcoes.find(e => String(e.id) === String(estoqueId));
            retiradasDetalhadas.push({
              id_produto: item.id_produto,
              quantidade: qtd,
              id_estoque_origem: Number(estoqueId),
              lote: estoqueOrigem?.lote,
              deposito: estoqueOrigem?.deposito
            });
          }
        });
      }
    });

    // Monta o payload para a API
    const payload = {
      situacao: "Produção", // O novo status
      data_finalizacao: dataFinalizacao,
      ordem_finalizacao: ordemFinalizacao,
      itens: itensState, // O JSON de itens atualizado
      retiradas_detalhadas: retiradasDetalhadas // Novo campo para o backend processar reservas
    };

    // Chama a função onSave (que fará o PUT)
    await onSave(payload);
    
    setIsSaving(false);
  };

  // Não renderiza nada se não estiver aberto
  if (!isOpen) return null;

  return (
    <Transition.Root show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-10" onClose={onClose}>
        {/* Overlay */}
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity" />
        </Transition.Child>

        <div className="fixed inset-0 z-10 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4 text-center sm:p-0">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-300"
              enterFrom="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95"
              enterTo="opacity-100 translate-y-0 sm:scale-100"
              leave="ease-in duration-200"
              leaveFrom="opacity-100 translate-y-0 sm:scale-100"
              leaveTo="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95"
            >
              {/* Painel do Modal (Aumentamos o tamanho) */}
              <Dialog.Panel className="relative transform overflow-hidden rounded-lg bg-white text-left shadow-xl transition-all sm:my-8 sm:w-full sm:max-w-6xl"> {/* Aumentado para max-w-6xl */}
                {/* Botão de Fechar (X) */}
                <button
                  type="button"
                  className="absolute top-3 right-2.5 text-gray-400 bg-transparent hover:bg-gray-200 hover:text-gray-900 rounded-lg text-sm p-1.5 ml-auto inline-flex items-center"
                  onClick={onClose}
                >
                  <X className="w-5 h-5" />
                  <span className="sr-only">Fechar modal</span>
                </button>

                <div className="bg-white px-4 pt-5 pb-4 sm:p-6 sm:pb-4">
                  <Dialog.Title
                    as="h3"
                    className="text-2xl font-bold leading-6 text-gray-900 mb-6"
                  >
                    Programar Pedido #{pedido?.id}
                  </Dialog.Title>
                  
                  {/* --- CORPO DO FORMULÁRIO --- */}
                  <div className="space-y-6">
                    {/* Linha 1: Data e Ordem */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                      <div>
                        <label htmlFor="data_finalizacao" className="block text-base font-medium text-gray-700 mb-2">Data de Finalização</label>
                        <input
                          type="date"
                          id="data_finalizacao"
                          value={dataFinalizacao}
                          onChange={(e) => setDataFinalizacao(e.target.value)}
                          className="block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 text-base p-3"
                        />
                      </div>
                      <div>
                        <label htmlFor="ordem_finalizacao" className="block text-base font-medium text-gray-700 mb-2">Ordem de Finalização</label>
                        <input
                          type="number"
                          step="0.1"
                          id="ordem_finalizacao"
                          value={ordemFinalizacao}
                          onChange={(e) => setOrdemFinalizacao(e.target.value)}
                          className="block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 text-base p-3"
                        />
                      </div>
                    </div>

                    {/* Linha 2: Tabela de Itens */}
                    <div>
                      <h4 className="text-lg font-medium text-gray-800">Itens do Pedido</h4>
                      <p className="text-sm text-gray-500 mb-4">
                        Defina a origem de cada item. Para retirar do estoque, clique em "Selecionar Lotes".
                      </p>
                      
                      {isLoadingItems ? (
                        <div className="flex justify-center py-8"><Loader2 className="animate-spin h-8 w-8 text-blue-500" /></div>
                      ) : (
                      <div className="overflow-x-auto rounded-lg border">
                        <table className="min-w-full divide-y divide-gray-200">
                          <thead className="bg-gray-50">
                            <tr>
                              <th className="px-6 py-4 text-left text-sm font-bold text-gray-700 uppercase tracking-wider">Item</th>
                              <th className="px-4 py-4 text-center text-sm font-bold text-gray-700 uppercase tracking-wider">Qtd. Total</th>
                              <th className="px-6 py-4 text-left text-sm font-bold text-gray-700 uppercase tracking-wider">Nº a Retirar</th>
                              <th className="px-6 py-4 text-left text-sm font-bold text-gray-700 uppercase tracking-wider">Nº a Produzir</th>
                              <th className="px-6 py-4 text-left text-sm font-bold text-gray-700 uppercase tracking-wider">Ações</th>
                            </tr>
                          </thead>
                          <tbody className="bg-white divide-y divide-gray-200">
                            {itensState.map((item, index) => (
                              <React.Fragment key={item.id || index}>
                                <tr className={expandedItems[index] ? "bg-blue-50" : ""}>
                                  <td className="px-6 py-4 text-base text-gray-800">
                                    {item.descricao}
                                    {!item.temEstoque && <span className="block text-xs text-red-500 font-semibold mt-1">Sem estoque disponível</span>}
                                  </td>
                                  <td className="px-4 py-4 text-base text-center text-gray-800 font-bold">{item.quantidade}</td>
                                  <td className="px-6 py-4">
                                    <div className="flex items-center">
                                      <span className={`font-bold text-lg ${item.numero_a_retirar > 0 ? 'text-blue-600' : 'text-gray-400'}`}>
                                        {item.numero_a_retirar}
                                      </span>
                                      {item.temEstoque && (
                                        <span className="ml-2 text-xs text-gray-500">(Selecionado)</span>
                                      )}
                                    </div>
                                  </td>
                                  <td className="px-6 py-4">
                                    <input
                                      type="number"
                                      value={item.numero_a_produzir}
                                      onChange={(e) => handleItemChange(index, 'numero_a_produzir', e.target.value)}
                                      className="block w-32 rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 text-base p-2"
                                    />
                                  </td>
                                  <td className="px-6 py-4">
                                    {item.temEstoque ? (
                                      <button
                                        type="button"
                                        onClick={() => toggleExpandItem(index)}
                                        className="flex items-center text-sm text-blue-600 hover:text-blue-800 font-medium"
                                      >
                                        {expandedItems[index] ? (
                                          <>
                                            <ChevronUp className="w-4 h-4 mr-1" /> Ocultar Lotes
                                          </>
                                        ) : (
                                          <>
                                            <ChevronDown className="w-4 h-4 mr-1" /> Selecionar Lotes
                                          </>
                                        )}
                                      </button>
                                    ) : (
                                      <span className="text-gray-400 text-sm">-</span>
                                    )}
                                  </td>
                                </tr>
                                {/* SUB-TABELA DE LOTES (EXPANSÍVEL) */}
                                {expandedItems[index] && item.temEstoque && (
                                  <tr>
                                    <td colSpan="5" className="px-6 py-4 bg-gray-50 border-b border-gray-200 shadow-inner">
                                      <div className="bg-white rounded border border-gray-200 p-4">
                                        <h5 className="text-sm font-bold text-gray-700 mb-3 flex items-center">
                                          <Box className="w-4 h-4 mr-2" />
                                          Lotes Disponíveis para {item.descricao}
                                        </h5>
                                        <table className="w-full text-sm">
                                          <thead>
                                            <tr className="text-gray-500 border-b">
                                              <th className="text-left py-2">Lote</th>
                                              <th className="text-left py-2">Depósito / Local</th>
                                              <th className="text-right py-2">Disponível</th>
                                              <th className="text-right py-2 w-32">Qtd. a Usar</th>
                                            </tr>
                                          </thead>
                                          <tbody>
                                            {item.estoqueOpcoes.map((lote) => (
                                              <tr key={lote.id} className="border-b last:border-0 hover:bg-gray-50">
                                                <td className="py-2 font-mono text-gray-700">{lote.lote || 'S/ Lote'}</td>
                                                <td className="py-2 text-gray-600">
                                                  {lote.deposito} {lote.rua ? `- Rua ${lote.rua}` : ''}
                                                </td>
                                                <td className="py-2 text-right font-medium text-green-600">
                                                  {lote.quantidade}
                                                </td>
                                                <td className="py-2 text-right">
                                                  <input
                                                    type="number"
                                                    min="0"
                                                    max={lote.quantidade}
                                                    value={item.retiradasSelecionadas[lote.id] || ''}
                                                    onChange={(e) => handleLoteChange(index, lote.id, e.target.value)}
                                                    className="w-24 p-1 text-right border border-gray-300 rounded focus:ring-blue-500 focus:border-blue-500"
                                                    placeholder="0"
                                                  />
                                                </td>
                                              </tr>
                                            ))}
                                          </tbody>
                                        </table>
                                      </div>
                                    </td>
                                  </tr>
                                )}
                              </React.Fragment>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* --- RODAPÉ COM BOTÕES --- */}
                <div className="bg-gray-50 px-4 py-3 sm:flex sm:flex-row-reverse sm:px-6">
                  <button
                    type="button"
                    disabled={isSaving}
                    className="inline-flex w-full justify-center rounded-md border border-transparent bg-blue-600 px-4 py-2 text-base font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 sm:ml-3 sm:w-auto sm:text-sm disabled:bg-blue-400"
                    onClick={handleConfirmSave}
                  >
                    {isSaving ? (
                      <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                    ) : null}
                    {isSaving ? 'Salvando...' : 'Salvar e Enviar para Produção'}
                  </button>
                  <button
                    type="button"
                    className="mt-3 inline-flex w-full justify-center rounded-md border border-gray-300 bg-white px-4 py-2 text-base font-medium text-gray-700 shadow-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 sm:mt-0 sm:w-auto sm:text-sm"
                    onClick={onClose}
                  >
                    Cancelar
                  </button>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition.Root>
  );
};

export default ProgramacaoPedidoModal;