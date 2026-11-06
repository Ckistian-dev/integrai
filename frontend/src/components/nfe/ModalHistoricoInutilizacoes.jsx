import React, { Fragment, useState, useEffect, useMemo } from 'react';
import { Transition, Dialog } from '@headlessui/react';
import { X, History, RefreshCw, Search, CheckCircle2, AlertCircle, FileText, ArrowRight } from 'lucide-react';
import { toast } from 'react-toastify';
import api from '../../api/axiosConfig';
import LoadingSpinner from '../ui/LoadingSpinner';

const ModalHistoricoInutilizacoes = ({
  isOpen,
  onClose,
  onOpenNovaInutilizacao
}) => {
  const [inutilizacoes, setInutilizacoes] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');

  const fetchHistorico = async () => {
    setIsLoading(true);
    try {
      const res = await api.get('/nfe/inutilizacoes');
      const data = Array.isArray(res.data) ? res.data : (res.data?.items || []);
      setInutilizacoes(data);
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Erro ao carregar histórico de inutilizações.';
      toast.error(msg);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      setSearchTerm('');
      fetchHistorico();
    }
  }, [isOpen]);

  const filteredItems = useMemo(() => {
    if (!searchTerm.trim()) return inutilizacoes;
    const term = searchTerm.toLowerCase().trim();

    return inutilizacoes.filter((item) => {
      const protocolo = String(item.protocolo || '').toLowerCase();
      const just = String(item.justificativa || '').toLowerCase();
      const numIni = String(item.numero_inicial || '');
      const numFim = String(item.numero_final || '');
      const serie = String(item.serie || '');
      const ano = String(item.ano || '');
      const xmotivo = String(item.xmotivo || '').toLowerCase();

      return (
        protocolo.includes(term) ||
        just.includes(term) ||
        numIni.includes(term) ||
        numFim.includes(term) ||
        serie.includes(term) ||
        ano.includes(term) ||
        xmotivo.includes(term)
      );
    });
  }, [inutilizacoes, searchTerm]);

  const formatDateTime = (dateStr) => {
    if (!dateStr) return '-';
    try {
      const d = new Date(dateStr);
      if (isNaN(d.getTime())) return dateStr;
      return d.toLocaleString('pt-BR', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch {
      return dateStr;
    }
  };

  return (
    <Transition.Root show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={onClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-gray-900 bg-opacity-70 backdrop-blur-sm transition-opacity" />
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
              <Dialog.Panel className="relative transform overflow-hidden rounded-xl bg-white text-left shadow-2xl transition-all sm:my-8 sm:w-full sm:max-w-4xl">
                {/* Cabeçalho */}
                <div className="bg-slate-800 px-6 py-4 text-white">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      <div className="p-2 bg-slate-700 rounded-lg">
                        <History className="w-6 h-6 text-slate-200" />
                      </div>
                      <div>
                        <Dialog.Title as="h3" className="text-lg font-bold leading-6">
                          Histórico de Inutilizações de NF-e
                        </Dialog.Title>
                        <p className="text-xs text-slate-300 mt-0.5">
                          Faixas e números inutilizados homologados pela SEFAZ
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center space-x-2">
                      <button
                        type="button"
                        onClick={fetchHistorico}
                        disabled={isLoading}
                        title="Atualizar lista"
                        className="text-slate-300 hover:text-white p-1.5 rounded-lg hover:bg-slate-700 transition-colors disabled:opacity-40"
                      >
                        <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
                      </button>
                      <button
                        type="button"
                        className="text-slate-300 hover:text-white rounded-lg p-1.5 hover:bg-slate-700 transition-colors"
                        onClick={onClose}
                      >
                        <X className="w-5 h-5" />
                        <span className="sr-only">Fechar</span>
                      </button>
                    </div>
                  </div>
                </div>

                {/* Barra de Ações & Busca */}
                <div className="p-4 bg-gray-50 border-b border-gray-200 flex flex-col sm:flex-row items-center justify-between gap-3">
                  <div className="relative w-full sm:w-80">
                    <Search className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 transform -translate-y-1/2" />
                    <input
                      type="text"
                      placeholder="Buscar por número, série, protocolo..."
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e.target.value)}
                      className="w-full pl-9 pr-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-slate-500 focus:border-slate-500 bg-white"
                    />
                  </div>

                  <div className="flex items-center space-x-2 w-full sm:w-auto justify-end">
                    <span className="text-xs text-gray-500">
                      Total: <strong>{filteredItems.length}</strong> {filteredItems.length === 1 ? 'registro' : 'registros'}
                    </span>
                    {onOpenNovaInutilizacao && (
                      <button
                        type="button"
                        onClick={() => {
                          onClose();
                          onOpenNovaInutilizacao();
                        }}
                        className="inline-flex items-center px-3 py-1.5 text-xs font-medium text-white bg-rose-600 hover:bg-rose-700 rounded-lg shadow-sm transition-colors"
                      >
                        Nova Inutilização
                      </button>
                    )}
                  </div>
                </div>

                {/* Conteúdo: Tabela */}
                <div className="max-h-[60vh] overflow-y-auto">
                  {isLoading ? (
                    <div className="py-16">
                      <LoadingSpinner />
                    </div>
                  ) : filteredItems.length === 0 ? (
                    <div className="py-16 text-center text-gray-500 space-y-2">
                      <FileText className="w-12 h-12 mx-auto text-gray-300" />
                      <p className="text-sm font-medium">Nenhuma inutilização encontrada.</p>
                      <p className="text-xs text-gray-400">
                        {searchTerm ? 'Tente ajustar os termos da busca.' : 'Nenhuma quebra de numeração foi inutilizada até o momento.'}
                      </p>
                    </div>
                  ) : (
                    <table className="min-w-full divide-y divide-gray-200 text-left text-xs">
                      <thead className="bg-gray-100 sticky top-0 z-10 text-gray-600 uppercase font-semibold">
                        <tr>
                          <th scope="col" className="px-4 py-3">Data / Hora</th>
                          <th scope="col" className="px-3 py-3">Mod.</th>
                          <th scope="col" className="px-3 py-3">Série</th>
                          <th scope="col" className="px-4 py-3">Faixa Numeração</th>
                          <th scope="col" className="px-4 py-3">Protocolo SEFAZ</th>
                          <th scope="col" className="px-4 py-3">Justificativa</th>
                          <th scope="col" className="px-4 py-3 text-center">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100 bg-white">
                        {filteredItems.map((item) => {
                          const isHomologado = item.sucesso || item.cstat === '102';
                          const isAvulso = item.numero_inicial === item.numero_final;

                          return (
                            <tr key={item.id} className="hover:bg-slate-50 transition-colors">
                              <td className="px-4 py-3 text-gray-700 whitespace-nowrap">
                                {formatDateTime(item.data_recebimento || item.created_at)}
                              </td>
                              <td className="px-3 py-3 whitespace-nowrap">
                                <span className="inline-block px-2 py-0.5 rounded text-[11px] font-semibold bg-gray-100 text-gray-800">
                                  {item.modelo || '55'}
                                </span>
                              </td>
                              <td className="px-3 py-3 font-medium text-gray-700 whitespace-nowrap">
                                {item.serie}
                              </td>
                              <td className="px-4 py-3 whitespace-nowrap">
                                {isAvulso ? (
                                  <span className="font-semibold text-slate-800">
                                    Nº {item.numero_inicial}
                                  </span>
                                ) : (
                                  <span className="font-semibold text-slate-800 flex items-center space-x-1">
                                    <span>{item.numero_inicial}</span>
                                    <ArrowRight className="w-3 h-3 text-gray-400" />
                                    <span>{item.numero_final}</span>
                                  </span>
                                )}
                              </td>
                              <td className="px-4 py-3 font-mono text-[11px] text-gray-700 whitespace-nowrap">
                                {item.protocolo || '-'}
                              </td>
                              <td className="px-4 py-3 text-gray-600 max-w-xs truncate" title={item.justificativa}>
                                {item.justificativa}
                              </td>
                              <td className="px-4 py-3 text-center whitespace-nowrap">
                                {isHomologado ? (
                                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-emerald-100 text-emerald-800">
                                    <CheckCircle2 className="w-3 h-3 mr-1 text-emerald-600" />
                                    {item.cstat === '102' ? 'Homologado (102)' : 'Sucesso'}
                                  </span>
                                ) : (
                                  <span
                                    className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-rose-100 text-rose-800"
                                    title={item.xmotivo || 'Rejeitado'}
                                  >
                                    <AlertCircle className="w-3 h-3 mr-1 text-rose-600" />
                                    {item.cstat ? `Rejeição (${item.cstat})` : 'Falha'}
                                  </span>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  )}
                </div>

                {/* Rodapé */}
                <div className="bg-gray-50 px-6 py-3 border-t border-gray-200 flex justify-end">
                  <button
                    type="button"
                    onClick={onClose}
                    className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 hover:bg-gray-50 rounded-lg shadow-sm transition-colors"
                  >
                    Fechar
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

export default ModalHistoricoInutilizacoes;
