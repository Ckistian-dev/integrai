import React, { useState, useEffect } from 'react';
import { toast } from 'react-toastify';
import { FaTruck, FaSave, FaTimes, FaBoxOpen } from 'react-icons/fa';
import api from '../../api/axiosConfig'; // Ajuste o caminho conforme sua estrutura

export default function ModalCotacaoIntelipost({ isOpen, onClose, pedido, onSelectFrete }) {
    const [resultado, setResultado] = useState(null);
    const [loading, setLoading] = useState(false);
    const [freteSelecionado, setFreteSelecionado] = useState(null);
    const [salvando, setSalvando] = useState(false);

    // Efeito que dispara a cotação quando o modal abre e temos um pedido
    useEffect(() => {
        if (isOpen && pedido) {
            realizarCotacao();
        } else {
            setResultado(null);
            setFreteSelecionado(null);
        }
    }, [isOpen, pedido]);

    const realizarCotacao = async () => {
        setLoading(true);
        setResultado(null);
        try {
            // Chama o endpoint novo que criamos no controller
            const targetId = pedido.id_sequencial;
            const response = await api.post(`/intelipost/cotacao/${targetId}`);
            setResultado(response.data);
        } catch (error) {
            const msg = error.response?.data?.detail || "Erro ao cotar frete.";
            toast.error(msg);
            // onClose(); // Mantém o modal aberto para que o usuário veja o erro
        } finally {
            setLoading(false);
        }
    };

    const handleConfirmarSelecao = async () => {
        if (!freteSelecionado) return;
        setSalvando(true);
        
        try {
            // Tenta achar a transportadora no nosso banco pelo nome
            let transportadoraId = null;
            let transportadoraNome = freteSelecionado.delivery_method_name;

            try {
                const resTransp = await api.get('/intelipost/transportadora/buscar', {
                    params: { nome: freteSelecionado.delivery_method_name }
                });
                transportadoraId = resTransp.data.id;
                transportadoraNome = resTransp.data.nome_razao;
            } catch (ignored) {
                // Se não achar, segue null e salva só o texto
                toast.warn("Transportadora não vinculada no cadastro local. Salvando apenas valor.");
            }

            // Devolve para o componente pai salvar no pedido
            onSelectFrete({
                transportadora_id: transportadoraId,
                transportadora_nome: transportadoraNome, // Apenas visual se necessário
                valor_frete: freteSelecionado.final_shipping_cost,
                prazo_entrega: freteSelecionado.delivery_estimate_business_days,
                modalidade_frete: '1', // Exemplo: FOB ou CIF, depende da regra
                delivery_method_id: freteSelecionado.delivery_method_id,
                quote_id: resultado?.cotacao?.content?.id || resultado?.cotacao?.id
            });
            
            onClose();

        } catch (err) {
            toast.error("Erro ao processar seleção.");
        } finally {
            setSalvando(false);
        }
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 backdrop-blur-sm flex items-center justify-center z-50">
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-5xl max-h-[90vh] flex flex-col overflow-hidden animate-fade-in">
                
                {/* Header */}
                <div className="bg-gray-50 px-6 py-4 border-b flex justify-between items-center">
                    <div>
                        <h2 className="text-xl font-bold text-gray-800 flex items-center gap-2">
                            <FaTruck className="text-teal-600"/> Cotação Intelipost
                        </h2>
                        <p className="text-sm text-gray-500">Pedido #{pedido?.id} - {pedido?.cliente?.nome_razao || "Cliente N/A"}</p>
                    </div>
                    <button onClick={onClose} className="text-gray-400 hover:text-red-500 transition-colors">
                        <FaTimes size={24} />
                    </button>
                </div>

                {/* Body */}
                <div className="flex-grow overflow-y-auto p-6 bg-gray-100">
                    {loading ? (
                        <div className="flex flex-col items-center justify-center h-64 space-y-4">
                            <div className="animate-spin rounded-full h-12 w-12 border-4 border-teal-500 border-t-transparent"></div>
                            <p className="text-gray-600 font-medium">Consultando transportadoras...</p>
                        </div>
                    ) : resultado ? (
                        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                            
                            {/* Coluna Esquerda: Volumes */}
                            <div className="bg-white p-4 rounded-lg shadow-sm lg:col-span-1">
                                <h3 className="font-semibold text-gray-700 mb-3 flex items-center gap-2">
                                    <FaBoxOpen /> Volumes ({resultado.volumes.length})
                                </h3>
                                <div className="space-y-2 max-h-[400px] overflow-y-auto pr-2 custom-scrollbar">
                                    {resultado.volumes.map((vol, idx) => (
                                        <div key={idx} className="text-sm p-3 border border-gray-100 rounded bg-gray-50">
                                            <p className="font-bold text-gray-800">Volume {idx + 1}</p>
                                            <div className="flex justify-between mt-1 text-gray-600 text-xs">
                                                <span>{vol.height}x{vol.width}x{vol.length}cm</span>
                                                <span>{vol.weight}kg</span>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            {/* Coluna Direita: Opções de Frete */}
                            <div className="bg-white p-4 rounded-lg shadow-sm lg:col-span-2">
                                <h3 className="font-semibold text-gray-700 mb-3">Opções de Entrega</h3>
                                <div className="space-y-3">
                                    {resultado.cotacao.content.delivery_options?.length > 0 ? (
                                        resultado.cotacao.content.delivery_options.map((opcao) => (
                                            <div
                                                key={opcao.delivery_method_id}
                                                onClick={() => setFreteSelecionado(opcao)}
                                                className={`
                                                    relative p-4 border rounded-lg cursor-pointer transition-all duration-200 flex justify-between items-center group
                                                    ${freteSelecionado?.delivery_method_id === opcao.delivery_method_id 
                                                        ? 'border-teal-500 bg-teal-50 ring-1 ring-teal-500' 
                                                        : 'border-gray-200 hover:border-teal-300 hover:bg-gray-50'}
                                                `}
                                            >
                                                <div className="flex items-center gap-4">
                                                    <div className={`p-2 rounded-full ${freteSelecionado?.delivery_method_id === opcao.delivery_method_id ? 'bg-teal-200 text-teal-700' : 'bg-gray-200 text-gray-500'}`}>
                                                        <FaTruck />
                                                    </div>
                                                    <div>
                                                        <p className="font-bold text-gray-800 text-sm">{opcao.delivery_method_name}</p>
                                                        <p className="text-xs text-gray-500">{opcao.provider_name}</p>
                                                        <p className="text-xs text-blue-600 mt-1 font-medium">{opcao.delivery_estimate_business_days} dias úteis</p>
                                                    </div>
                                                </div>
                                                <div className="text-right">
                                                    <p className="text-lg font-bold text-gray-900">
                                                        {opcao.final_shipping_cost.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
                                                    </p>
                                                    {freteSelecionado?.delivery_method_id === opcao.delivery_method_id && (
                                                        <span className="text-xs text-teal-600 font-bold">Selecionado</span>
                                                    )}
                                                </div>
                                            </div>
                                        ))
                                    ) : (
                                        <div className="text-center py-10 text-gray-500">
                                            Nenhuma opção de frete disponível para este CEP.
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    ) : (
                        <div className="text-center py-12 text-gray-400">
                            Não foi possível carregar os dados.
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="bg-gray-50 px-6 py-4 border-t flex justify-end gap-3">
                    <button 
                        onClick={onClose}
                        className="px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 font-medium transition-colors"
                    >
                        Cancelar
                    </button>
                    <button 
                        onClick={handleConfirmarSelecao}
                        disabled={!freteSelecionado || salvando}
                        className="px-6 py-2 bg-teal-600 text-white rounded-lg hover:bg-teal-700 font-medium shadow-sm disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 transition-colors"
                    >
                        {salvando ? 'Salvando...' : (
                            <>
                                <FaSave /> Confirmar Frete
                            </>
                        )}
                    </button>
                </div>
            </div>
        </div>
    );
}