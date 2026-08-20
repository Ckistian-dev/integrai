import React, { useMemo, useState, useEffect } from 'react';
import api from '../api/axiosConfig'; // Usar a instância configurada do axios
import { X } from 'lucide-react';
import { FaFilePdf, FaBuilding } from 'react-icons/fa';
import html2pdf from 'html2pdf.js';
import { toast } from 'react-toastify';

// Objeto padrão para evitar erros caso o pedido venha nulo
const pedidoVazio = {
    id: '',
    id_sequencial: '',
    data_emissao: '',
    data_validade: '',
    cliente: null,
    cliente_nome: '',
    vendedor_nome: '',
    origem_venda: '',
    situacao: '',
    modalidade_frete: '',
    transportadora_nome: '',
    valor_frete: 0,
    ipi_frete: 0,
    prazo_entrega: '',
    total: 0,
    desconto: 0,
    total_com_desconto: 0,
    observacao: '',
    observacoes_nf: '',
    itens: '[]', // Alterado para corresponder ao schema do backend
    pagamento: '[]', // Alterado para corresponder ao schema do backend
};

// =================================================================================
// LÓGICA DE CÁLCULO
// =================================================================================

const calcularValoresItem = (item, produtoInfo) => {
    const quantidade = Number(item.quantidade) || Number(item.quantidade_itens) || 1;
    const desconto = Number(item.desconto) || 0;

    // Valor Unitário: Prioridade para o valor salvo no pedido
    let precoUnitario = Number(item.valor_unitario) || Number(item.preco_unitario) || 0;

    // Se não tiver valor no pedido, usa o do banco de dados (produto atual)
    if (precoUnitario === 0 && produtoInfo && produtoInfo.preco) {
        precoUnitario = parseFloat(produtoInfo.preco);
    }

    const subtotal = (quantidade * precoUnitario) - desconto;

    // IPI: Prioridade para o valor salvo no item, senão calcula pela alíquota do produto
    const ipiAliquota = Number(item.ipi_aliquota) || (produtoInfo ? Number(produtoInfo.ipi_aliquota) : 0) || 0;
    const valorIpi = Number(item.valor_ipi) || (subtotal * (ipiAliquota / 100)) || 0;

    // Total do item com IPI
    const totalComIpi = subtotal + valorIpi;

    return { 
        ...item, 
        preco_unitario: precoUnitario,
        desconto: desconto,
        subtotal: subtotal,
        valor_ipi: valorIpi,
        ipi_aliquota: ipiAliquota,
        total_com_desconto: totalComIpi 
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
                <p>CNPJ: {empresa.cnpj}{empresa.inscricao_estadual ? ` | IE: ${empresa.inscricao_estadual}` : ''}</p>
                <p>{empresa.endereco}</p>
                {empresa.telefone && <p>Telefone: {empresa.telefone}</p>}
            </div>
        </header>
    );
}

const calcularDiasUteis = (inicio, fim) => {
    if (!inicio || !fim) return null;
    const date1 = new Date(inicio + 'T00:00:00');
    const date2 = new Date(fim + 'T00:00:00');
    if (isNaN(date1.getTime()) || isNaN(date2.getTime())) return null;
    if (date1 > date2) return 0;
    
    let count = 0;
    let curDate = new Date(date1.getTime());
    while (curDate < date2) {
        curDate.setDate(curDate.getDate() + 1);
        const dayOfWeek = curDate.getDay();
        if (dayOfWeek !== 0 && dayOfWeek !== 6) {
            count++;
        }
    }
    return count;
};

function DetalhesGerais({ pedido }) {
    const dataEmissaoValida = pedido.data_emissao || pedido.data_pedido || pedido.data_orcamento || (pedido.criado_em ? pedido.criado_em.split('T')[0] : null);
    
    const prazoExibido = useMemo(() => {
        if (pedido.prazo_entrega) return `${pedido.prazo_entrega} dias úteis`;
        
        const dias = calcularDiasUteis(dataEmissaoValida, pedido.data_entrega);
        if (dias !== null) {
            return `${dias} dias úteis`;
        }
        return "Não informado";
    }, [pedido.prazo_entrega, pedido.data_entrega, dataEmissaoValida]);

    return (
        <section className="mt-4 text-xs">
            <div className="grid grid-cols-4 gap-x-4 gap-y-2">
                <div className="col-span-1">
                    <span className="text-gray-500">Emissão:</span>
                    <p className="font-semibold text-gray-800">{formatarData(dataEmissaoValida)}</p>
                </div>
                <div className="col-span-1">
                    <span className="text-gray-500">Vendedor:</span>
                    <p className="font-semibold text-gray-800">{pedido.vendedor_nome || "Não informado"}</p>
                </div>
                <div className="col-span-1">
                    <span className="text-gray-500">Validade:</span>
                    <p className="font-semibold text-gray-800">{formatarData(pedido.data_validade)}</p>
                </div>
                <div className="col-span-1">
                    <span className="text-gray-500">Prazo Entrega:</span>
                    <p className="font-semibold text-gray-800">{prazoExibido}</p>
                </div>
                {pedido.transportadora_nome && (
                    <div className="col-span-4">
                        <span className="text-gray-500">Transportadora:</span>
                        <p className="font-semibold text-gray-800 break-words">{pedido.transportadora_nome}</p>
                    </div>
                )}
            </div>
        </section>
    );
}

function SecaoCliente({ cliente, nomeFallback }) {
    if (!cliente) return (
        <section className="mt-4 text-xs border-t pt-3">
            <h3 className="font-bold text-gray-700 mb-2 uppercase">Dados do Cliente</h3>
            <div className="grid grid-cols-4 gap-x-4 gap-y-2">
                <div className="col-span-4">
                    <span className="text-gray-500">Nome/Razão Social:</span>
                    <p className="font-semibold text-gray-800 break-words">{nomeFallback || "Não informado"}</p>
                </div>
            </div>
        </section>
    );

    const endereco = `${cliente.logradouro || ''}, ${cliente.numero || 'S/N'}${cliente.complemento ? ' - ' + cliente.complemento : ''}`;
    const localidade = `${cliente.bairro || ''} - ${cliente.cidade || ''}/${cliente.estado || ''}`;
    const ieCliente = cliente.inscricao_estadual || cliente.ie || "Isento";

    return (
        <section className="mt-4 text-xs border-t pt-3">
            <h3 className="font-bold text-gray-700 mb-2 uppercase">Dados do Cliente</h3>
            <div className="grid grid-cols-4 gap-x-4 gap-y-2">
                <div className="col-span-1">
                    <span className="text-gray-500">Nome/Razão Social:</span>
                    <p className="font-semibold text-gray-800 break-words">{cliente.nome_razao || nomeFallback}</p>
                </div>
                <div className="col-span-1">
                    <span className="text-gray-500">CPF/CNPJ:</span>
                    <p className="font-semibold text-gray-800 break-words">{cliente.cpf_cnpj || "N/A"}</p>
                </div>
                <div className="col-span-1">
                    <span className="text-gray-500">IE (Inscrição Estadual):</span>
                    <p className="font-semibold text-gray-800 break-words">{ieCliente}</p>
                </div>
                <div className="col-span-1">
                    <span className="text-gray-500">Endereço:</span>
                    <p className="font-semibold text-gray-800 break-words">{endereco}</p>
                </div>
                <div className="col-span-1">
                    <span className="text-gray-500">Bairro/Cidade/UF:</span>
                    <p className="font-semibold text-gray-800 break-words">{localidade}</p>
                </div>
                <div className="col-span-1">
                    <span className="text-gray-500">CEP:</span>
                    <p className="font-semibold text-gray-800 break-words">{cliente.cep || "N/A"}</p>
                </div>
                <div className="col-span-1">
                    <span className="text-gray-500">Telefone/Celular:</span>
                    <p className="font-semibold text-gray-800 break-words">{[cliente.telefone, cliente.celular].filter(Boolean).join(' / ') || "N/A"}</p>
                </div>
                <div className="col-span-1">
                    <span className="text-gray-500">E-mail:</span>
                    <p className="font-semibold text-gray-800 break-words">{cliente.email || "N/A"}</p>
                </div>
            </div>
        </section>
    );
}

function TabelaItens({ itens }) {
    const hasIpi = itens.some(item => (item.valor_ipi || 0) > 0);

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
                            {hasIpi && <th scope="col" className="px-3 py-2 text-right">IPI</th>}
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
                                    {hasIpi && <td className="px-3 py-2 text-right">{formatarValor(item.valor_ipi || 0)}</td>}
                                    <td className="px-3 py-2 text-right font-semibold">{formatarValor(item.total_com_desconto)}</td>
                                </tr>
                            ))
                        ) : (
                            <tr><td colSpan={hasIpi ? "5" : "4"} className="text-center py-3 text-gray-500">Nenhum item adicionado.</td></tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

function TotaisOrcamento({ pedido, totalItensRecalculado, totalIpi }) {
    const valorFrete = Number(pedido.valor_frete) || 0;
    const ipiFrete = Number(pedido.ipi_frete) || 0;
    const descontoGeral = Number(pedido.desconto) || 0;
    const totalFinal = totalItensRecalculado + totalIpi + valorFrete + ipiFrete - descontoGeral;

    return (
        <div className="flex justify-end mt-6 text-sm px-2">
            <div className="w-full">
                <div className="flex justify-between py-1">
                    <span className="text-gray-600">Total dos Itens:</span>
                    <span className="font-medium text-gray-800">{formatarValor(totalItensRecalculado)}</span>
                </div>
                {(totalIpi + ipiFrete) > 0 && (
                    <div className="flex justify-between py-1">
                        <span className="text-gray-600">IPI (Produtos e Frete):</span>
                        <span className="font-medium text-gray-800">{formatarValor(totalIpi + ipiFrete)}</span>
                    </div>
                )}
                <div className="flex justify-between py-1">
                    <span className="text-gray-600">Frete:</span>
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
            const targetId = item.id_produto || item.produto_id;
            const produtoInfo = produtosDisponiveis.find(p => p.id === targetId || p.id_sequencial === targetId);
            const descricao = produtoInfo ? produtoInfo.descricao : (item.descricao || item.produto);
            const itemComNome = { ...item, descricao, produto: descricao };
            return calcularValoresItem(itemComNome, produtoInfo);
        });
    }, [itensOriginais, produtosDisponiveis, loading]);
    
    const totalItensRecalculado = useMemo(() => {
        return itensEnriquecidosECalculados.reduce((acc, item) => acc + (item.subtotal || 0), 0);
    }, [itensEnriquecidosECalculados]);

    const totalIpi = useMemo(() => {
        return itensEnriquecidosECalculados.reduce((acc, item) => acc + (item.valor_ipi || 0), 0);
    }, [itensEnriquecidosECalculados]);

    const formasPagamento = useMemo(() => {
        try {
            const raw = pedido.pagamentos || pedido.formas_pagamento;
            return Array.isArray(raw) ? raw : JSON.parse(raw || '[]');
        } catch (e) { return []; }
    }, [pedido.pagamentos, pedido.formas_pagamento]);

    const isOrcamento = pedido.situacao === 'Orçamento';
    const labelDocumento = isOrcamento ? 'Orçamento' : 'Pedido';

    const gerarPDF = () => {
        const elemento = document.getElementById('conteudo-orcamento');
        const botoes = elemento.querySelectorAll('.no-print');
        botoes.forEach(btn => btn.style.visibility = 'hidden');
        const options = {
            margin: [8, 8, 8, 8],
            filename: `${labelDocumento.toLowerCase()}_${pedido.id_sequencial ?? 'sem_numero'}.pdf`,
            image: { type: 'jpeg', quality: 0.98 },
            html2canvas: { scale: 2, dpi: 300, letterRendering: true, useCORS: true },
            jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' }
        };
        html2pdf().set(options).from(elemento).save().finally(() => {
            botoes.forEach(btn => btn.style.visibility = 'visible');
        });
    };

    return (
        <div 
            className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
            onClick={onClose}
        >
            <div 
                className="bg-white rounded-lg shadow-2xl w-full max-w-2xl max-h-[95vh] flex flex-col"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="p-4 overflow-y-auto" id="conteudo-orcamento">
                    {loading ? (
                        <div className="flex justify-center items-center h-64">
                            <p className="text-gray-500">Carregando dados do orçamento...</p>
                        </div>
                    ) : (
                        <>
                            <CabecalhoEmpresa empresa={empresaSelecionada} />
                            <div className="flex justify-between items-center mt-4">
                                <h2 className="text-xl font-bold text-gray-800">{labelDocumento} #{pedido.id_sequencial ?? 'N/A'}</h2>
                            </div>
                            <DetalhesGerais pedido={pedido} />
                            <SecaoCliente cliente={pedido.cliente} nomeFallback={pedido.cliente_nome} />
                            <TabelaItens itens={itensEnriquecidosECalculados} />
                            <TotaisOrcamento pedido={pedido} totalItensRecalculado={totalItensRecalculado} totalIpi={totalIpi} />
                            <InformacoesAdicionais observacao={pedido.observacoes_nf} />
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