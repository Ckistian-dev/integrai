// src/components/ui/ProgramacaoPedidoModal.jsx

import React, { Fragment, useState, useEffect } from 'react';
import { Transition, Dialog } from '@headlessui/react';
import { X, Loader2 } from 'lucide-react';
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

  // Efeito para popular o formulário quando o pedido é carregado
  useEffect(() => {
    if (pedido && pedido.itens) {
      // Formata a data para o input (YYYY-MM-DD)
      const today = new Date().toISOString().split('T')[0];
      setDataFinalizacao(today);
      
      // Garante que a ordem de finalização tenha um valor padrão
      setOrdemFinalizacao(pedido.ordem_finalizacao || '1.0');

      // Inicializa o estado dos itens com os novos campos
      const initializedItens = pedido.itens.map(item => ({
        ...item,
        numero_a_retirar: item.numero_a_retirar || 0,
        numero_a_produzir: item.numero_a_produzir || 0,
        endereco_de_retirada: item.endereco_de_retirada || '',
      }));
      setItensState(initializedItens);

    } else {
      // Reseta o formulário se o pedido for nulo
      setDataFinalizacao('');
      setOrdemFinalizacao('1.0');
      setItensState([]);
    }
  }, [pedido]); // Re-executa quando o 'pedido' (prop) muda

  /**
   * Manipula a mudança nos inputs dos itens
   */
  const handleItemChange = (index, field, value) => {
    // Converte para número se for um campo numérico
    const isNumeric = field === 'numero_a_retirar' || field === 'numero_a_produzir';
    const numericValue = isNumeric ? parseInt(value, 10) || 0 : value;

    // Atualiza o array de itens no estado
    const newItens = [...itensState];
    newItens[index] = {
      ...newItens[index],
      [field]: numericValue,
    };
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
    });

    if (hasError) {
      setIsSaving(false);
      return;
    }

    // Monta o payload para a API
    const payload = {
      situacao: "Produção", // O novo status
      data_finalizacao: dataFinalizacao,
      ordem_finalizacao: ordemFinalizacao,
      itens: itensState, // O JSON de itens atualizado
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
              <Dialog.Panel className="relative transform overflow-hidden rounded-lg bg-white text-left shadow-xl transition-all sm:my-8 sm:w-full sm:max-w-4xl"> {/* Aumentado para max-w-4xl */}
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
                    className="text-xl font-medium leading-6 text-gray-900 mb-4"
                  >
                    Programar Pedido #{pedido?.id}
                  </Dialog.Title>
                  
                  {/* --- CORPO DO FORMULÁRIO --- */}
                  <div className="space-y-6">
                    {/* Linha 1: Data e Ordem */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <div>
                        <label htmlFor="data_finalizacao" className="block text-sm font-medium text-gray-700">Data de Finalização</label>
                        <input
                          type="date"
                          id="data_finalizacao"
                          value={dataFinalizacao}
                          onChange={(e) => setDataFinalizacao(e.target.value)}
                          className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
                        />
                      </div>
                      <div>
                        <label htmlFor="ordem_finalizacao" className="block text-sm font-medium text-gray-700">Ordem de Finalização</label>
                        <input
                          type="number"
                          step="0.1"
                          id="ordem_finalizacao"
                          value={ordemFinalizacao}
                          onChange={(e) => setOrdemFinalizacao(e.target.value)}
                          className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
                        />
                      </div>
                    </div>

                    {/* Linha 2: Tabela de Itens */}
                    <div>
                      <h4 className="text-lg font-medium text-gray-800">Itens do Pedido</h4>
                      <p className="text-sm text-gray-500 mb-2">
                        Defina a origem de cada item (Estoque ou Produção). A soma deve bater com a quantidade total.
                      </p>
                      <div className="overflow-x-auto rounded-lg border">
                        <table className="min-w-full divide-y divide-gray-200">
                          <thead className="bg-gray-50">
                            <tr>
                              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Item</th>
                              <th className="px-2 py-3 text-left text-xs font-medium text-gray-500 uppercase">Qtd. Total</th>
                              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Nº a Retirar</th>
                              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Nº a Produzir</th>
                              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Endereço Retirada (Estoque)</th>
                            </tr>
                          </thead>
                          <tbody className="bg-white divide-y divide-gray-200">
                            {itensState.map((item, index) => (
                              <tr key={item.id || index}>
                                <td className="px-4 py-3 text-sm text-gray-800">{item.descricao}</td>
                                <td className="px-2 py-3 text-sm text-gray-800 font-bold">{item.quantidade}</td>
                                <td className="px-4 py-3">
                                  <input
                                    type="number"
                                    value={item.numero_a_retirar}
                                    onChange={(e) => handleItemChange(index, 'numero_a_retirar', e.target.value)}
                                    className="block w-24 rounded-md border-gray-300 shadow-sm sm:text-sm"
                                  />
                                </td>
                                <td className="px-4 py-3">
                                  <input
                                    type="number"
                                    value={item.numero_a_produzir}
                                    onChange={(e) => handleItemChange(index, 'numero_a_produzir', e.target.value)}
                                    className="block w-24 rounded-md border-gray-300 shadow-sm sm:text-sm"
                                  />
                                </td>
                                <td className="px-4 py-3">
                                  <input
                                    type="text"
                                    placeholder="Ex: R-01, N-02"
                                    value={item.endereco_de_retirada}
                                    onChange={(e) => handleItemChange(index, 'endereco_de_retirada', e.target.value)}
                                    className="block w-full rounded-md border-gray-300 shadow-sm sm:text-sm"
                                  />
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
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