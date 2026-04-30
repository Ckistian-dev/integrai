import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { Fragment } from 'react';
import { toast } from 'react-toastify';
import api from '../../api/axiosConfig';
import {
  X, Search, Loader2, ClipboardList, CheckCircle, AlertTriangle, Package, Calendar
} from 'lucide-react';
import DatePicker, { registerLocale } from "react-datepicker";
import "react-datepicker/dist/react-datepicker.css";
import ptBR from 'date-fns/locale/pt-BR';

registerLocale('pt-BR', ptBR);

const ModalInventario = ({ isOpen, onClose, onSuccess }) => {
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [allItems, setAllItems] = useState([]);
  const [filteredItems, setFilteredItems] = useState([]);
  const [dataInventario, setDataInventario] = useState(new Date());

  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const ITEMS_PER_PAGE = 50;
  const searchDebounceRef = useRef(null);

  const fetchInventario = useCallback(async (search = '', pageNum = 1) => {
    setLoading(true);
    try {
      const res = await api.get('/estoque/inventario', {
        params: {
          search_term: search || undefined,
          skip: (pageNum - 1) * ITEMS_PER_PAGE,
          limit: ITEMS_PER_PAGE
        }
      });
      const items = (res.data.items || []).map(item => ({
        ...item,
        quantidade_inventario: '',
        _modified: false
      }));
      setAllItems(items);
      setFilteredItems(items);
      setTotalCount(res.data.total_count || 0);
    } catch (err) {
      toast.error('Erro ao carregar inventário');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      setSearchTerm('');

      setPage(1);
      setDataInventario(new Date());
      fetchInventario('', 1);
    }
  }, [isOpen, fetchInventario]);

  // Search debounce
  useEffect(() => {
    if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
    searchDebounceRef.current = setTimeout(() => {
      setPage(1);
      fetchInventario(searchTerm, 1);
    }, 400);
    return () => clearTimeout(searchDebounceRef.current);
  }, [searchTerm]);



  const handleQtyChange = (id_produto, value) => {
    setFilteredItems(prev => prev.map(item =>
      item.id_produto === id_produto
        ? { ...item, quantidade_inventario: value, _modified: true }
        : item
    ));
    setAllItems(prev => prev.map(item =>
      item.id_produto === id_produto
        ? { ...item, quantidade_inventario: value, _modified: true }
        : item
    ));
  };



  const handleSubmit = async () => {
    const itensParaEnviar = filteredItems.filter(
      item => item.quantidade_inventario !== '' && item.quantidade_inventario !== null && item.quantidade_inventario !== undefined
    );

    if (itensParaEnviar.length === 0) {
      toast.warning('Preencha a quantidade de ao menos um produto para realizar o inventário.');
      return;
    }

    setSubmitting(true);
    try {
      const res = await api.post('/estoque/inventario', {
        itens: itensParaEnviar.map(item => ({
          id_produto: item.id_produto,
          quantidade_inventario: parseInt(item.quantidade_inventario, 10)
        })),
        data_inventario: dataInventario.toISOString(),
        observacao: `Inventário de Ajuste - Contagem Física Geral`
      });
      toast.success(`Inventário processado! ${res.data.registros_criados} registros criados.`);
      if (onSuccess) onSuccess();
      onClose();
    } catch (err) {
      toast.error('Erro ao processar inventário: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSubmitting(false);
    }
  };

  const countFilled = filteredItems.filter(i => i.quantidade_inventario !== '' && i.quantidade_inventario !== null).length;
  const countDiff = filteredItems.filter(i => {
    const qty = parseInt(i.quantidade_inventario, 10);
    return !isNaN(qty) && qty !== i.saldo_atual;
  }).length;

  return (
    <Transition appear show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={onClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-300" enterFrom="opacity-0" enterTo="opacity-100"
          leave="ease-in duration-200" leaveFrom="opacity-100" leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-300" enterFrom="opacity-0 scale-95" enterTo="opacity-100 scale-100"
              leave="ease-in duration-200" leaveFrom="opacity-100 scale-100" leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel className="w-full max-w-5xl bg-white rounded-2xl shadow-2xl overflow-hidden flex flex-col" style={{ maxHeight: '90vh' }}>
                {/* Header */}
                <div className="bg-gradient-to-r from-indigo-600 to-purple-600 px-6 py-4 flex items-center justify-between flex-shrink-0">
                  <div className="flex items-center gap-3">
                    <ClipboardList size={24} className="text-white" />
                    <div>
                      <Dialog.Title className="text-xl font-bold text-white">Inventário de Estoque</Dialog.Title>
                      <p className="text-indigo-200 text-sm">Informe a quantidade física contada para cada produto</p>
                    </div>
                  </div>
                  <button onClick={onClose} className="text-white/70 hover:text-white transition-colors">
                    <X size={24} />
                  </button>
                </div>

                {/* Stats Bar */}
                <div className="bg-indigo-50 px-6 py-3 flex items-center gap-6 border-b border-indigo-100 flex-shrink-0">
                  <div className="flex items-center gap-2 text-sm text-indigo-700">
                    <Package size={16} />
                    <span>{totalCount} produto(s) no sistema</span>
                  </div>
                  {countFilled > 0 && (
                    <div className="flex items-center gap-2 text-sm text-green-700">
                      <CheckCircle size={16} />
                      <span>{countFilled} preenchido(s)</span>
                    </div>
                  )}
                  {countDiff > 0 && (
                    <div className="flex items-center gap-2 text-sm text-orange-600">
                      <AlertTriangle size={16} />
                      <span>{countDiff} com diferença</span>
                    </div>
                  )}
                </div>

                {/* Controls */}
                <div className="px-6 py-4 border-b border-gray-100 flex-shrink-0">
                  <div className="flex gap-3 flex-wrap">
                    {/* Search existing products */}
                    <div className="relative flex-1 min-w-56">
                      <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                      <input
                        type="text"
                        value={searchTerm}
                        onChange={e => setSearchTerm(e.target.value)}
                        placeholder="Buscar produto na lista..."
                        className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                      />
                    </div>

                    {/* Date/Time Picker */}
                    <div className="flex flex-col gap-1 min-w-48">
                      <label className="text-[10px] font-bold text-indigo-600 uppercase ml-1">Data/Hora do Inventário</label>
                      <div className="relative">
                        <Calendar size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-indigo-500 z-10 pointer-events-none" />
                        <DatePicker
                          selected={dataInventario}
                          onChange={(date) => setDataInventario(date)}
                          showTimeSelect
                          timeFormat="HH:mm"
                          timeIntervals={15}
                          timeCaption="Hora"
                          dateFormat="dd/MM/yyyy HH:mm"
                          maxDate={new Date()}
                          locale="pt-BR"
                          className="w-full pl-9 pr-4 py-2 border border-indigo-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-indigo-50/30"
                        />
                      </div>
                    </div>
                  </div>


                </div>

                {/* Table */}
                <div className="flex-1 overflow-auto">
                  {loading ? (
                    <div className="flex items-center justify-center h-48">
                      <Loader2 size={32} className="animate-spin text-indigo-500" />
                    </div>
                  ) : (
                    <table className="w-full text-sm">
                      <thead className="bg-gray-50 sticky top-0 z-10">
                        <tr>
                          <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide w-12">#</th>
                          <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide w-32">SKU</th>
                          <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Produto</th>
                          <th className="px-4 py-3 text-center text-xs font-semibold text-gray-500 uppercase tracking-wide w-20">Un.</th>
                          <th className="px-4 py-3 text-center text-xs font-semibold text-gray-500 uppercase tracking-wide w-32">Saldo Sistema</th>
                          <th className="px-4 py-3 text-center text-xs font-semibold text-indigo-600 uppercase tracking-wide w-40">Qty. Inventário</th>
                          <th className="px-4 py-3 text-center text-xs font-semibold text-gray-500 uppercase tracking-wide w-28">Diferença</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-50">
                        {filteredItems.length === 0 && (
                          <tr>
                            <td colSpan={7} className="text-center py-12 text-gray-400">
                              Nenhum produto encontrado
                            </td>
                          </tr>
                        )}
                        {filteredItems.map((item, idx) => {
                          const qtyFilled = item.quantidade_inventario !== '' && item.quantidade_inventario !== null;
                          const qtyNum = parseInt(item.quantidade_inventario, 10);
                          const diff = qtyFilled && !isNaN(qtyNum) ? qtyNum - item.saldo_atual : null;
                          const hasDiff = diff !== null && diff !== 0;

                          return (
                            <tr
                              key={item.id_produto}
                              className={`transition-colors ${hasDiff ? 'bg-orange-50/50' : qtyFilled ? 'bg-green-50/30' : 'hover:bg-gray-50'}`}
                            >
                              <td className="px-4 py-2.5 text-gray-400 text-xs">{idx + 1}</td>
                              <td className="px-4 py-2.5 text-gray-500 text-xs font-mono whitespace-nowrap">{item.produto_sku || '-'}</td>
                              <td className="px-4 py-2.5">
                                <span className="font-medium text-gray-800 break-words line-clamp-2">{item.produto_descricao}</span>
                              </td>
                              <td className="px-4 py-2.5 text-center text-gray-500 text-xs uppercase">{item.produto_unidade}</td>
                              <td className="px-4 py-2.5 text-center">
                                <span className={`font-semibold ${item.saldo_atual < 0 ? 'text-red-600' : item.saldo_atual === 0 ? 'text-gray-400' : 'text-gray-700'}`}>
                                  {item.saldo_atual}
                                </span>
                              </td>
                              <td className="px-4 py-2.5 text-center">
                                <input
                                  type="number"
                                  value={item.quantidade_inventario}
                                  onChange={e => handleQtyChange(item.id_produto, e.target.value)}
                                  placeholder="—"
                                  className={`w-28 text-center border rounded-lg py-1.5 px-2 text-sm font-semibold focus:outline-none focus:ring-2 transition-all ${
                                    hasDiff
                                      ? 'border-orange-400 ring-orange-300 bg-orange-50 text-orange-700 focus:ring-orange-400'
                                      : qtyFilled
                                        ? 'border-green-400 ring-green-300 bg-green-50 text-green-700 focus:ring-green-400'
                                        : 'border-gray-200 focus:ring-indigo-400 text-gray-800'
                                  }`}
                                />
                              </td>
                              <td className="px-4 py-2.5 text-center">
                                {diff !== null ? (
                                  <span className={`text-sm font-bold ${diff > 0 ? 'text-green-600' : diff < 0 ? 'text-red-600' : 'text-gray-400'}`}>
                                    {diff > 0 ? `+${diff}` : diff}
                                  </span>
                                ) : (
                                  <span className="text-gray-300">—</span>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  )}
                </div>

                {/* Footer */}
                <div className="px-6 py-4 border-t border-gray-100 flex items-center justify-between bg-gray-50 flex-shrink-0">
                  <div className="text-sm text-gray-500">
                    {countFilled > 0
                      ? <span>Serão criadas entradas para <strong>{countFilled}</strong> produto(s){countDiff > 0 ? `, com ajuste de saldo em <strong>${countDiff}</strong>` : ''}</span>
                      : <span>Preencha as quantidades contadas fisicamente</span>
                    }
                  </div>
                  <div className="flex gap-3">
                    <button
                      onClick={onClose}
                      className="px-5 py-2 text-sm text-gray-600 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
                    >
                      Cancelar
                    </button>
                    <button
                      onClick={handleSubmit}
                      disabled={submitting || countFilled === 0}
                      className="flex items-center gap-2 px-6 py-2 text-sm font-semibold text-white bg-gradient-to-r from-indigo-600 to-purple-600 rounded-lg hover:from-indigo-700 hover:to-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-sm"
                    >
                      {submitting ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle size={16} />}
                      {submitting ? 'Processando...' : `Registrar Inventário (${countFilled})`}
                    </button>
                  </div>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
};

export default ModalInventario;
