import React, { Fragment, useState, useEffect } from 'react';
import { Transition, Dialog } from '@headlessui/react';
import { X, FileX, AlertTriangle, Loader2, CheckCircle2 } from 'lucide-react';
import { toast } from 'react-toastify';
import api from '../../api/axiosConfig';

const ModalInutilizarNFe = ({
  isOpen,
  onClose,
  onSuccess
}) => {
  const currentYear = new Date().getFullYear();

  const [modelo, setModelo] = useState('55');
  const [serie, setSerie] = useState('1');
  const [numeroInicial, setNumeroInicial] = useState('');
  const [numeroFinal, setNumeroFinal] = useState('');
  const [ano, setAno] = useState(String(currentYear));
  const [justificativa, setJustificativa] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [hasManuallyEditedFinal, setHasManuallyEditedFinal] = useState(false);

  // Reseta formulário sempre que o modal for aberto
  useEffect(() => {
    if (isOpen) {
      setModelo('55');
      setSerie('1');
      setNumeroInicial('');
      setNumeroFinal('');
      setAno(String(new Date().getFullYear()));
      setJustificativa('');
      setIsLoading(false);
      setHasManuallyEditedFinal(false);
    }
  }, [isOpen]);

  const handleNumeroInicialChange = (e) => {
    const val = e.target.value;
    setNumeroInicial(val);
    if (!hasManuallyEditedFinal) {
      setNumeroFinal(val);
    }
  };

  const handleNumeroFinalChange = (e) => {
    const val = e.target.value;
    setNumeroFinal(val);
    setHasManuallyEditedFinal(true);
  };

  const handleSubmit = async (e) => {
    if (e) e.preventDefault();

    const nInicial = parseInt(numeroInicial, 10);
    const nFinal = parseInt(numeroFinal, 10);
    const nSerie = parseInt(serie, 10);
    const nAno = parseInt(ano, 10);
    const just = justificativa.trim();

    if (isNaN(nInicial) || nInicial <= 0) {
      toast.warning('Informe um Número Inicial válido (maior que zero).');
      return;
    }

    if (isNaN(nFinal) || nFinal <= 0) {
      toast.warning('Informe um Número Final válido (maior que zero).');
      return;
    }

    if (nFinal < nInicial) {
      toast.warning('O Número Final deve ser maior ou igual ao Número Inicial.');
      return;
    }

    if (isNaN(nSerie) || nSerie < 0) {
      toast.warning('Informe uma Série válida.');
      return;
    }

    if (isNaN(nAno) || nAno < 2000 || nAno > 2099) {
      toast.warning('Informe um Ano válido de 4 dígitos (ex: 2026).');
      return;
    }

    if (just.length < 15) {
      toast.warning('A justificativa deve conter no mínimo 15 caracteres (exigência SEFAZ).');
      return;
    }

    setIsLoading(true);

    try {
      const payload = {
        modelo,
        serie: nSerie,
        numero_inicial: nInicial,
        numero_final: nFinal,
        ano: nAno,
        justificativa: just
      };

      const res = await api.post('/nfe/inutilizar', payload);
      const data = res.data || {};
      const protocolo = data.protocolo || data.nProt || '';
      const xMotivo = data.xmotivo || data.xMotivo || 'Numeração inutilizada com sucesso';

      toast.success(
        protocolo
          ? `${xMotivo}! Protocolo: ${protocolo}`
          : `${xMotivo}!`
      );

      if (onSuccess) {
        onSuccess(data);
      }

      onClose();
    } catch (err) {
      const errorDetail =
        err.response?.data?.detail ||
        err.response?.data?.xmotivo ||
        err.message ||
        'Falha ao comunicar inutilização com a SEFAZ.';
      toast.error(errorDetail);
    } finally {
      setIsLoading(false);
    }
  };

  const justLength = justificativa.trim().length;
  const isJustificativaValid = justLength >= 15;

  return (
    <Transition.Root show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={isLoading ? () => {} : onClose}>
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
              <Dialog.Panel className="relative transform overflow-hidden rounded-xl bg-white text-left shadow-2xl transition-all sm:my-8 sm:w-full sm:max-w-xl">
                {/* Cabeçalho */}
                <div className="bg-gradient-to-r from-rose-700 to-rose-600 px-6 py-4 text-white">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      <div className="p-2 bg-white/10 rounded-lg">
                        <FileX className="w-6 h-6 text-white" />
                      </div>
                      <div>
                        <Dialog.Title as="h3" className="text-lg font-bold leading-6">
                          Inutilização de Numeração NF-e
                        </Dialog.Title>
                        <p className="text-xs text-rose-100 mt-0.5">
                          Homologação direta de quebra de sequência junto à SEFAZ
                        </p>
                      </div>
                    </div>
                    <button
                      type="button"
                      disabled={isLoading}
                      className="text-white/80 hover:text-white rounded-lg p-1.5 transition-colors disabled:opacity-40"
                      onClick={onClose}
                    >
                      <X className="w-5 h-5" />
                      <span className="sr-only">Fechar modal</span>
                    </button>
                  </div>
                </div>

                {/* Formulário */}
                <form onSubmit={handleSubmit} className="px-6 py-5 space-y-4">
                  {/* Alerta de regra fiscal */}
                  <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 flex items-start space-x-2 text-xs text-amber-800">
                    <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
                    <div>
                      A inutilização só deve ser feita para números que nunca foram utilizados ou autorizados na SEFAZ. Uma vez homologada, essa numeração não poderá mais ser emitida.
                    </div>
                  </div>

                  {/* Grid: Modelo, Série e Ano */}
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div>
                      <label className="block text-xs font-semibold text-gray-700 mb-1">
                        Modelo <span className="text-rose-500">*</span>
                      </label>
                      <select
                        value={modelo}
                        onChange={(e) => setModelo(e.target.value)}
                        disabled={isLoading}
                        className="w-full text-sm border border-gray-300 rounded-lg p-2.5 focus:ring-2 focus:ring-rose-500 focus:border-rose-500 bg-white"
                      >
                        <option value="55">55 - NF-e</option>
                        <option value="65">65 - NFC-e</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-gray-700 mb-1">
                        Série <span className="text-rose-500">*</span>
                      </label>
                      <input
                        type="number"
                        min="1"
                        step="1"
                        value={serie}
                        onChange={(e) => setSerie(e.target.value)}
                        disabled={isLoading}
                        className="w-full text-sm border border-gray-300 rounded-lg p-2.5 focus:ring-2 focus:ring-rose-500 focus:border-rose-500"
                        placeholder="1"
                        required
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-gray-700 mb-1">
                        Ano <span className="text-rose-500">*</span>
                      </label>
                      <input
                        type="number"
                        min="2000"
                        max="2099"
                        step="1"
                        value={ano}
                        onChange={(e) => setAno(e.target.value)}
                        disabled={isLoading}
                        className="w-full text-sm border border-gray-300 rounded-lg p-2.5 focus:ring-2 focus:ring-rose-500 focus:border-rose-500"
                        placeholder="2026"
                        required
                      />
                    </div>
                  </div>

                  {/* Faixa de Numeração: Inicial e Final */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 bg-gray-50 p-3.5 rounded-lg border border-gray-200">
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <label className="text-xs font-semibold text-gray-700">
                          Número Inicial <span className="text-rose-500">*</span>
                        </label>
                      </div>
                      <input
                        type="number"
                        min="1"
                        step="1"
                        value={numeroInicial}
                        onChange={handleNumeroInicialChange}
                        disabled={isLoading}
                        className="w-full text-sm border border-gray-300 rounded-lg p-2.5 focus:ring-2 focus:ring-rose-500 focus:border-rose-500 bg-white"
                        placeholder="Ex: 100"
                        required
                      />
                    </div>

                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <label className="text-xs font-semibold text-gray-700">
                          Número Final <span className="text-rose-500">*</span>
                        </label>
                        {numeroInicial && numeroFinal !== numeroInicial && (
                          <button
                            type="button"
                            onClick={() => {
                              setNumeroFinal(numeroInicial);
                              setHasManuallyEditedFinal(false);
                            }}
                            className="text-[11px] text-rose-600 hover:text-rose-700 font-medium"
                          >
                            Igual ao inicial
                          </button>
                        )}
                      </div>
                      <input
                        type="number"
                        min={numeroInicial || '1'}
                        step="1"
                        value={numeroFinal}
                        onChange={handleNumeroFinalChange}
                        disabled={isLoading}
                        className="w-full text-sm border border-gray-300 rounded-lg p-2.5 focus:ring-2 focus:ring-rose-500 focus:border-rose-500 bg-white"
                        placeholder="Ex: 100"
                        required
                      />
                    </div>

                    <div className="col-span-full text-[11px] text-gray-500">
                      💡 Para inutilizar apenas um número avulso, mantenha o <strong>Número Inicial</strong> e o <strong>Número Final</strong> com o mesmo valor.
                    </div>
                  </div>

                  {/* Justificativa */}
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-xs font-semibold text-gray-700">
                        Justificativa <span className="text-rose-500">*</span>
                      </label>
                      <span
                        className={`text-xs font-semibold ${
                          isJustificativaValid ? 'text-emerald-600' : 'text-amber-600'
                        }`}
                      >
                        {justLength} / 15 caracteres mínimos
                      </span>
                    </div>
                    <textarea
                      rows={3}
                      value={justificativa}
                      onChange={(e) => setJustificativa(e.target.value)}
                      disabled={isLoading}
                      maxLength={255}
                      placeholder="Ex: Pulo de numeração devido a falha de transmissão ou erro operacional na sequência..."
                      className={`w-full text-sm border rounded-lg p-2.5 focus:ring-2 focus:outline-none transition-colors ${
                        justLength > 0 && !isJustificativaValid
                          ? 'border-amber-400 focus:ring-amber-400'
                          : 'border-gray-300 focus:ring-rose-500 focus:border-rose-500'
                      }`}
                      required
                    />
                    {!isJustificativaValid && justLength > 0 && (
                      <p className="text-[11px] text-amber-600 mt-1">
                        Faltam {15 - justLength} caractere(s) para atingir o mínimo exigido pela SEFAZ.
                      </p>
                    )}
                  </div>

                  {/* Rodapé / Botões */}
                  <div className="pt-3 border-t border-gray-100 flex items-center justify-end space-x-3">
                    <button
                      type="button"
                      disabled={isLoading}
                      onClick={onClose}
                      className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors disabled:opacity-50"
                    >
                      Cancelar
                    </button>
                    <button
                      type="submit"
                      disabled={isLoading || !isJustificativaValid || !numeroInicial || !numeroFinal}
                      className="inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-rose-600 hover:bg-rose-700 rounded-lg shadow-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isLoading ? (
                        <>
                          <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                          Comunicando com SEFAZ...
                        </>
                      ) : (
                        <>
                          <FileX className="w-4 h-4 mr-2" />
                          Inutilizar Numeração
                        </>
                      )}
                    </button>
                  </div>
                </form>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition.Root>
  );
};

export default ModalInutilizarNFe;
