import React, { Fragment, useState, useEffect } from 'react';
import { Transition, Dialog } from '@headlessui/react';
import { X, Package } from 'lucide-react';
import { toast } from 'react-toastify';

const ConferenciaPedidoModal = ({
  isOpen,
  onClose,
  onConfirm,
  pedido,
  title,
  confirmText,
  variant = 'blue',
  showVolumes = false
}) => {
  const [volumes, setVolumes] = useState(0);

  useEffect(() => {
    if (pedido) {
      setVolumes(pedido.volumes_quantidade || 0);
    }
  }, [pedido]);

  if (!isOpen || !pedido) return null;

  const colorClasses = {
    blue: 'bg-blue-600 hover:bg-blue-700 focus:ring-blue-500',
    green: 'bg-green-600 hover:bg-green-700 focus:ring-green-500',
    cyan: 'bg-cyan-600 hover:bg-cyan-700 focus:ring-cyan-500',
    indigo: 'bg-indigo-600 hover:bg-indigo-700 focus:ring-indigo-500',
    teal: 'bg-teal-600 hover:bg-teal-700 focus:ring-teal-500',
  };

  const btnClass = colorClasses[variant] || colorClasses.blue;

  const handleConfirmClick = () => {
    const data = {};
    if (showVolumes) {
      if (!volumes || Number(volumes) <= 0) {
        toast.error("A quantidade de volumes deve ser maior que zero.");
        return;
      }
      data.volumes_quantidade = Number(volumes);
    }
    onConfirm(data);
  };

  return (
    <Transition.Root show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-10" onClose={onClose}>
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
              <Dialog.Panel className="relative transform overflow-hidden rounded-lg bg-white text-left shadow-xl transition-all sm:my-8 sm:w-full sm:max-w-4xl">
                <button
                  type="button"
                  className="absolute top-3 right-2.5 text-gray-400 bg-transparent hover:bg-gray-200 hover:text-gray-900 rounded-lg text-sm p-1.5 ml-auto inline-flex items-center"
                  onClick={onClose}
                >
                  <X className="w-5 h-5" />
                </button>

                <div className="bg-white px-4 pt-5 pb-4 sm:p-6 sm:pb-4">
                  <Dialog.Title as="h3" className="text-2xl font-bold leading-6 text-gray-900 mb-6">
                    {title}
                  </Dialog.Title>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6 bg-gray-50 p-4 rounded-lg">
                    <div><p className="text-sm text-gray-500">Pedido ID</p><p className="font-bold">#{pedido.id_sequencial ?? pedido.id}</p></div>
                    <div><p className="text-sm text-gray-500">Ordem de Finalização</p><p className="font-bold">{pedido.ordem_finalizacao || '-'}</p></div>
                    <div><p className="text-sm text-gray-500">Cliente</p><p>{pedido.cliente_nome || 'N/A'}</p></div>
                    <div><p className="text-sm text-gray-500">Data Prevista</p><p>{pedido.data_finalizacao || '-'}</p></div>
                    {showVolumes && (
                      <div>
                        <label htmlFor="volumes" className="block text-sm font-medium text-gray-700">Qtd. Volumes</label>
                        <input
                          type="number"
                          id="volumes"
                          min="0"
                          value={volumes}
                          onChange={(e) => setVolumes(e.target.value)}
                          className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-2 border"
                        />
                      </div>
                    )}
                  </div>

                  <h4 className="text-lg font-semibold text-gray-800 mb-2">Itens e Ordens</h4>
                  <div className="overflow-x-auto border rounded-lg">
                    <table className="min-w-full divide-y divide-gray-200">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Produto</th>
                          <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Qtd. Total</th>
                          <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">A Produzir</th>
                          <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">A Retirar</th>
                        </tr>
                      </thead>
                      <tbody className="bg-white divide-y divide-gray-200">
                        {pedido.itens && pedido.itens.map((item, idx) => (
                          <tr key={idx}>
                            <td className="px-4 py-3 text-sm text-gray-900">{item.descricao || item.nome || (item.id_produto ? `Produto #${item.id_produto}` : `Item ${idx + 1}`)}</td>
                            <td className="px-4 py-3 text-sm text-center font-bold">{item.quantidade}</td>
                            <td className="px-4 py-3 text-sm text-center text-gray-500">{item.numero_a_produzir || 0}</td>
                            <td className="px-4 py-3 text-sm text-center text-gray-500">{item.numero_a_retirar || 0}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div className="bg-gray-50 px-4 py-3 sm:flex sm:flex-row-reverse sm:px-6">
                  <button type="button" className={`inline-flex w-full justify-center rounded-md border border-transparent px-4 py-2 text-base font-medium text-white shadow-sm sm:ml-3 sm:w-auto sm:text-sm ${btnClass}`} onClick={handleConfirmClick}>{confirmText}</button>
                  <button type="button" className="mt-3 inline-flex w-full justify-center rounded-md border border-gray-300 bg-white px-4 py-2 text-base font-medium text-gray-700 shadow-sm hover:bg-gray-50 sm:mt-0 sm:w-auto sm:text-sm" onClick={onClose}>Cancelar</button>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition.Root>
  );
};

export default ConferenciaPedidoModal;
