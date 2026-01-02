import React, { useMemo, useState, useEffect } from 'react';
import api from '../api/axiosConfig'; // Usar a instância configurada do axios
import { X } from 'lucide-react';
import { FaFilePdf, FaBuilding } from 'react-icons/fa';
import html2pdf from 'html2pdf.js';
import { toast } from 'react-toastify';

// Objeto padrão para evitar erros caso o pedido venha nulo
const pedidoVazio = {
    id: '',
    data_emissao: '',
    data_validade: '',
    cliente_nome: '',
    vendedor_nome: '',
    origem_venda: '',
    situacao: '',
    modalidade_frete: '',
    transportadora_nome: '',
    valor_frete: 0,
    prazo_entrega: '',
    total: 0,
    desconto: 0,
    total_com_desconto: 0,
    observacao: '',
    itens: '[]', // Alterado para corresponder ao schema do backend
    pagamento: '[]', // Alterado para corresponder ao schema do backend
};

// =================================================================================
// LÓGICA DE CÁLCULO
// =================================================================================

const calcularValoresItem = (item, produtoInfo) => {
    const quantidade = Number(item.quantidade) || Number(item.quantidade_itens) || 1;
    let totalComDesconto = Number(item.total_com_desconto) || Number(item.subtotal) || 0;
    const desconto = Number(item.desconto) || 0;

    // Valor Unitário: Prioridade para o banco de dados (produto atual)
    let precoUnitario = 0;
    if (produtoInfo && produtoInfo.preco) {
        precoUnitario = parseFloat(produtoInfo.preco);
        // Recalcula o total usando o preço do banco (Qtd * Preço Banco - Desconto)
        totalComDesconto = (quantidade * precoUnitario) - desconto;
    } else {
        // Fallback: valor salvo ou calculado
        precoUnitario = Number(item.preco_unitario) || (quantidade > 0 ? totalComDesconto / quantidade : 0);
    }

    return { 
        ...item, 
        preco_unitario: precoUnitario,
        desconto: desconto,
        total_com_desconto: totalComDesconto 
    };
};


// =================================================================================
// COMPONENTES DE VISUALIZAÇÃO
// =================================================================================
function formatarValor(valor) {
    const numero = Number(valor);
    if (isNaN(numero)) return 'R$ 0,00';
    return numero.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function formatarData(dataStr) {
    if (!dataStr) return "Não informada";
    // Converte 'YYYY-MM-DD' para 'DD/MM/YYYY'
    const data = new Date(dataStr + 'T00:00:00'); // Adiciona tempo para evitar problemas de fuso
    return data.toLocaleDateString('pt-BR');
}

function CabecalhoEmpresa({ empresa }) {
    if (!empresa) return null;
    return (
        <header className="flex justify-between items-start pb-3 border-b">
            <div className="flex-shrink-0">
                {empresa.logo ? (
                    <img src={empresa.logo} alt={`Logo ${empresa.nome}`} className="h-16 w-auto" crossOrigin="anonymous" />
                ) : (
                    <div className="h-16 w-16 bg-gray-100 rounded flex items-center justify-center text-gray-400"><FaBuilding size={24} /></div>
                )}
            </div>
            <div className="text-right text-[11px] text-gray-600">
                <p className="font-bold text-xs text-gray-800">{empresa.nome}</p>
                <p>CNPJ: {empresa.cnpj}</p>
                <p>{empresa.endereco}</p>
                {empresa.telefone && <p>Telefone: {empresa.telefone}</p>}
            </div>
        </header>
    );
}

function DetalhesGerais({ pedido }) {
    return (
        <section className="mt-4 text-xs">
            <div className="grid grid-cols-3 gap-x-4 gap-y-2">
                <div>
                    <span className="text-gray-500">Cliente:</span>
                    <p className="font-semibold text-gray-800">{pedido.cliente_nome || "Não informado"}</p>
                </div>
                <div>
                    <span className="text-gray-500">Emissão:</span>
                    <p className="font-semibold text-gray-800">{formatarData(pedido.data_emissao)}</p>
                </div>
                <div>
                    <span className="text-gray-500">Situação:</span>
                    <p className="font-semibold text-gray-800">{pedido.situacao || "Não informada"}</p>
                </div>
                <div>
                    <span className="text-gray-500">Vendedor:</span>
                    <p className="font-semibold text-gray-800">{pedido.vendedor_nome || "Não informado"}</p>
                </div>
                <div>
                    <span className="text-gray-500">Validade:</span>
                    <p className="font-semibold text-gray-800">{formatarData(pedido.data_validade)}</p>
                </div>
                <div>
                    <span className="text-gray-500">Prazo Entrega:</span>
                    <p className="font-semibold text-gray-800">{pedido.prazo_entrega ? `${pedido.prazo_entrega} dias úteis` : "Não informado"}</p>
                </div>
                {pedido.transportadora_nome && (
                    <div>
                        <span className="text-gray-500">Transportadora:</span>
                        <p className="font-semibold text-gray-800">{pedido.transportadora_nome}</p>
                    </div>
                )}
            </div>
        </section>
    );
}

function TabelaItens({ itens }) {
    return (
        <div className="mt-5">
            <h3 className="text-base font-semibold text-gray-800 mb-2">Itens do Orçamento</h3>
            <div className="overflow-x-auto border rounded-md">
                <table className="w-full text-xs text-left text-gray-600">
                    <thead className="bg-gray-50 text-gray-700 uppercase">
                        <tr>
                            <th scope="col" className="px-3 py-2">Produto/Serviço</th>
                            <th scope="col" className="px-3 py-2 text-center">Qtd.</th>
                            <th scope="col" className="px-3 py-2 text-right">Valor Unit.</th>
                            <th scope="col" className="px-3 py-2 text-right">Total</th>
                        </tr>
                    </thead>
                    <tbody>
                        {itens && itens.length > 0 ? (
                            itens.map((item, index) => (
                                <tr key={item.id_produto || index} className="bg-white border-b last:border-b-0 hover:bg-gray-50">
                                    <td className="px-3 py-2 font-medium text-gray-900">{item.descricao || "Produto não encontrado"}</td>
                                    <td className="px-3 py-2 text-center">{item.quantidade || 0}</td>
                                    <td className="px-3 py-2 text-right">{formatarValor(item.preco_unitario)}</td>
                                    <td className="px-3 py-2 text-right font-semibold">{formatarValor(item.total_com_desconto)}</td>
                                </tr>
                            ))
                        ) : (
                            <tr><td colSpan="4" className="text-center py-3 text-gray-500">Nenhum item adicionado.</td></tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

function TotaisOrcamento({ pedido, totalItensRecalculado }) {
    const valorFrete = Number(pedido.valor_frete) || 0;
    const descontoGeral = Number(pedido.desconto) || 0;
    const totalFinal = totalItensRecalculado + valorFrete - descontoGeral;

    return (
        <div className="flex justify-end mt-6 text-sm px-2">
            <div className="w-full">
                <div className="flex justify-between py-1">
                    <span className="text-gray-600">Total dos Itens:</span>
                    <span className="font-medium text-gray-800">{formatarValor(totalItensRecalculado)}</span>
                </div>
                <div className="flex justify-between py-1">
                    <span className="text-gray-600">Frete ({pedido.modalidade_frete || 'N/D'}):</span>
                    <span className="font-medium text-gray-800">{formatarValor(valorFrete)}</span>
                </div>
                {descontoGeral > 0 && (
                    <div className="flex justify-between py-1">
                        <span className="text-gray-600">Desconto Geral:</span>
                        <span className="font-medium text-red-600">(- {formatarValor(descontoGeral)})</span>
                    </div>
                )}
                <div className="flex justify-between py-2 mt-2 border-t-2 border-gray-200">
                    <span className="text-base font-bold text-gray-900">VALOR TOTAL:</span>
                    <span className="text-base font-bold text-green-700">{formatarValor(totalFinal)}</span>
                </div>
            </div>
        </div>
    );
}

function InformacoesAdicionais({ observacao }) {
    return (
        <footer className="mt-5 pt-3 border-t text-xs text-gray-600 space-y-2">
             {observacao && (<div><h4 className="font-semibold text-gray-700 mb-0.5">Observações</h4><p className="whitespace-pre-wrap">{observacao}</p></div>)}
        </footer>
    );
}

// --- COMPONENTE PRINCIPAL ---
export default function ModalVisualizarPedido({ pedido = pedidoVazio, onClose }) {
    
    const [empresaSelecionada, setEmpresaSelecionada] = useState(null);

    const [produtosDisponiveis, setProdutosDisponiveis] = useState([]);
    const [loading, setLoading] = useState(false);

    const itensOriginais = useMemo(() => {
        try {
            const source = pedido.lista_itens || pedido.itens;
            return Array.isArray(source) ? source : JSON.parse(source || '[]');
        } catch (e) { return []; }
    }, [pedido.lista_itens, pedido.itens]);

    useEffect(() => {
        const fetchEmpresa = async () => {
            try {
                const res = await api.get('/generic/empresas');
                if (res.data.items && res.data.items.length > 0) {
                    const emp = res.data.items[0];
                    // Mapeia os campos do backend para o formato esperado pelo componente
                    setEmpresaSelecionada({
                        ...emp,
                        nome: emp.fantasia || emp.razao,
                        logo: emp.url_logo,
                        endereco: `${emp.logradouro || ''}, ${emp.numero || ''}${emp.bairro ? ' - ' + emp.bairro : ''}, ${emp.cidade || ''} - ${emp.estado || ''}`,
                        telefone: emp.telefone || ''
                    });
                }
            } catch (error) {
                console.error("Erro ao buscar dados da empresa:", error);
            }
        };
        fetchEmpresa();
    }, []);

    useEffect(() => {
        const carregarDadosEssenciais = async () => {
            if (!itensOriginais || itensOriginais.length === 0) {
                setLoading(false);
                return;
            }
            
            setLoading(true);
            try {
                // Identificar IDs únicos dos produtos nos itens para buscar no banco
                const uniqueIds = [...new Set(itensOriginais.map(item => item.id_produto || item.produto_id).filter(id => id))];

                // Buscar detalhes de cada produto individualmente via endpoint genérico
                const productPromises = uniqueIds.map(async (id) => {
                    try {
                        const res = await api.get(`/generic/produtos/${id}`);
                        return res.data;
                    } catch (error) {
                        console.error(`Erro ao buscar produto ${id}:`, error);
                        return null;
                    }
                });

                const productsData = await Promise.all(productPromises);
                setProdutosDisponiveis(productsData.filter(p => p !== null));

            } catch (error) {
                toast.error("Erro ao carregar dados para visualização.");
                console.error("Erro ao buscar dados:", error);
            } finally {
                setLoading(false);
            }
        };

        carregarDadosEssenciais();
    }, [itensOriginais]);

    const itensEnriquecidosECalculados = useMemo(() => {
        if (loading) return [];
        if (!itensOriginais) return [];
        return itensOriginais.map(item => {
            const produtoInfo = produtosDisponiveis.find(p => p.id === (item.id_produto || item.produto_id));
            const itemComNome = { ...item, produto: produtoInfo ? produtoInfo.descricao : item.produto };
            return calcularValoresItem(itemComNome, produtoInfo);
        });
    }, [itensOriginais, produtosDisponiveis, loading]);
    
    const totalItensRecalculado = useMemo(() => {
        return itensEnriquecidosECalculados.reduce((acc, item) => acc + (item.total_com_desconto || 0), 0);
    }, [itensEnriquecidosECalculados]);

    const formasPagamento = useMemo(() => {
        try {
            return Array.isArray(pedido.formas_pagamento) ? pedido.formas_pagamento : JSON.parse(pedido.formas_pagamento || '[]');
        } catch (e) { return []; }
    }, [pedido.formas_pagamento]);

    const gerarPDF = () => {
        const elemento = document.getElementById('conteudo-orcamento');
        const botoes = elemento.querySelectorAll('.no-print');
        botoes.forEach(btn => btn.style.visibility = 'hidden');
        const options = {
            margin: [8, 8, 8, 8],
            filename: `orcamento_${pedido.id || 'sem_numero'}.pdf`,
            image: { type: 'jpeg', quality: 0.98 },
            html2canvas: { scale: 2, dpi: 300, letterRendering: true, useCORS: true },
            jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' }
        };
        html2pdf().set(options).from(elemento).save().finally(() => {
            botoes.forEach(btn => btn.style.visibility = 'visible');
        });
    };

    return (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-white rounded-lg shadow-2xl w-full max-w-2xl max-h-[95vh] flex flex-col">
                <div className="p-4 overflow-y-auto" id="conteudo-orcamento">
                    {loading ? (
                        <div className="flex justify-center items-center h-64">
                            <p className="text-gray-500">Carregando dados do orçamento...</p>
                        </div>
                    ) : (
                        <>
                            <CabecalhoEmpresa empresa={empresaSelecionada} />
                            <div className="flex justify-between items-center mt-4">
                                <h2 className="text-xl font-bold text-gray-800">Orçamento #{pedido.id || 'N/A'}</h2>
                            </div>
                            <DetalhesGerais pedido={pedido} />
                            <TabelaItens itens={itensEnriquecidosECalculados} />
                            <TotaisOrcamento pedido={pedido} totalItensRecalculado={totalItensRecalculado} />
                            <InformacoesAdicionais observacao={pedido.observacao} />
                        </>
                    )}
                </div>
                <div className="flex-shrink-0 p-3 bg-gray-50 border-t rounded-b-lg flex justify-between items-center no-print">
                      <button onClick={onClose} className="text-gray-600 hover:text-gray-900 text-sm font-medium py-1.5 px-3 rounded-md">Fechar</button>
                    <button onClick={gerarPDF} disabled={loading} className="bg-red-700 hover:bg-red-800 text-white font-bold py-1.5 px-3 rounded-md flex items-center gap-2 transition-colors duration-200 text-sm disabled:opacity-50 disabled:cursor-not-allowed"><FaFilePdf /> Baixar PDF</button>
                </div>
            </div>
        </div>
    );
}