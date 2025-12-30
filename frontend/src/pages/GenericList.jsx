import React, { useState, useEffect, useMemo } from 'react';
// Removendo imports não utilizados (useParams, Link) e adicionando (LayoutGrid)
// Manterei o Link e o useParams, pois "Novo" e a lógica do modelName ainda os utilizam.
import { useParams, useNavigate, Link } from 'react-router-dom';
import api from '../api/axiosConfig';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import ProgramacaoPedidoModal from '../components/ui/ProgramacaoPedidoModal'; // 1. IMPORTAR O NOVO MODAL
import Modal from '../components/ui/Modal';
import {
  Plus,
  Edit,
  Trash2,
  FileDown,
  ChevronLeft,
  ChevronRight,
  Search,
  Loader2,
  CheckSquare,
  ThumbsUp,
  Send
} from 'lucide-react';

function useDebounce(value, delay) {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    // Define um temporizador para atualizar o valor debotado
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    // Limpa o temporizador se o valor mudar (ou no desmonte)
    return () => {
      clearTimeout(handler);
    };
  }, [value, delay]); // Só re-executa se o valor ou o atraso mudarem

  return debouncedValue;
}

const BooleanDisplay = ({ value }) => {
  // Você pode mudar os textos aqui se preferir (ex: "Sim"/"Não")
  const text = value ? 'Ativo' : 'Inativo';
  const bgColor = value ? 'bg-green-100' : 'bg-gray-100'; // Mudei inativo para cinza
  const textColor = value ? 'text-green-800' : 'text-gray-800';

  return (
    <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${bgColor} ${textColor}`}>
      {text}
    </span>
  );
};

/**
 * Define as ações de mudança de status que podem aparecer na lista.
 * A chave é o 'modelName'.
 */
const statusChangeActions = {
  // Ações específicas para o modelo 'pedidos'
  'pedidos': [
    {
      // O botão só aparece se o statusFilter for este:
      currentStatus: "Orçamento",
      // O novo status a ser enviado no PUT:
      newStatus: "Aprovação",
      // Textos e estilos do Botão
      buttonLabel: "Converter para Pedido",
      buttonIcon: CheckSquare,
      buttonClasses: "bg-purple-600 hover:bg-purple-700 disabled:bg-purple-400",
      // Textos do Modal
      modalTitle: "Converter Orçamento para Pedido",
      modalDescription: "Tem certeza que deseja converter este orçamento? A situação será alterada para \"Aprovação\" e ele sairá desta lista.",
      modalConfirmText: "Confirmar Conversão",
      // Textos de Erro
      errorLog: "Falha ao converter pedido:",
      errorAlert: "Não foi possível converter o orçamento."
    },
    {
      currentStatus: "Aprovação",
      newStatus: "Programação",
      buttonLabel: "Aprovar Pedido",
      buttonIcon: ThumbsUp,
      buttonClasses: "bg-green-600 hover:bg-green-700 disabled:bg-green-400",
      modalTitle: "Aprovar Pedido para Programação",
      modalDescription: "Tem certeza que deseja aprovar este pedido? A situação será alterada para \"Programação\" e ele sairá desta lista.",
      modalConfirmText: "Aprovar e Enviar",
      errorLog: "Falha ao aprovar pedido:",
      errorAlert: "Não foi possível aprovar o pedido."
    },
    {
      // 3. ADICIONAR A NOVA AÇÃO
      currentStatus: "Programação",
      newStatus: "Produção", // Status de destino
      buttonLabel: "Programar Pedido",
      buttonIcon: Send,
      buttonClasses: "bg-cyan-600 hover:bg-cyan-700 disabled:bg-cyan-400",
      // Chave especial para nosso handler customizado
      onClickHandler: 'programar'
    },
  ]
};

const GenericList = () => {
  const { modelName, statusFilter } = useParams();
  const navigate = useNavigate();

  const [metadata, setMetadata] = useState(null);
  const [data, setData] = useState([]);

  const [loadingMetadata, setLoadingMetadata] = useState(true);
  const [isFetchingData, setIsFetchingData] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [error, setError] = useState('');

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [actionToConfirm, setActionToConfirm] = useState(null);

  const [isProgramacaoModalOpen, setIsProgramacaoModalOpen] = useState(false);
  const [currentPedidoDetails, setCurrentPedidoDetails] = useState(null);
  const [isFetchingDetails, setIsFetchingDetails] = useState(false);

  const [selectedRowId, setSelectedRowId] = useState(null);

  const [searchTerm, setSearchTerm] = useState("");
  const debouncedSearchTerm = useDebounce(searchTerm, 500);

  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(10);
  const [totalCount, setTotalCount] = useState(0);


  useEffect(() => {
    const fetchMetadata = async () => {
      setLoadingMetadata(true);
      setIsFetchingData(true); // Também ativamos este para o loading inicial
      setError('');
      setMetadata(null); // Limpa metadados antigos
      setData([]); // Limpa dados antigos
      setPage(1); // Reseta a página
      setSearchTerm(""); // Reseta a busca

      try {
        const metaRes = await api.get(`/metadata/${modelName}`);
        setMetadata(metaRes.data);
      } catch (err) {
        console.error('Falha ao buscar metadados:', err);
        setError(`Não foi possível carregar os metadados para "${modelName}".`);
      } finally {
        setLoadingMetadata(false);
        // isFetchingData será controlado pelo useEffect de dados
      }
    };
    fetchMetadata();
  }, [modelName]);

  useEffect(() => {
    // Não busca dados se os metadados ainda não carregaram ou falharam
    if (!metadata) return;

    const fetchData = async () => {
      setIsFetchingData(true);
      setSelectedRowId(null);

      try {
        const skip = (page - 1) * limit;
        const params = { skip, limit };
        if (debouncedSearchTerm) {
          params.search_term = debouncedSearchTerm;
        }

        if (statusFilter) {
          params.situacao = statusFilter;
        }

        const dataRes = await api.get(`/generic/${modelName}`, { params });

        setData(dataRes.data.items);
        setTotalCount(dataRes.data.total_count);

      } catch (err) {
        console.error('Falha ao buscar dados:', err);
        // Só define o erro se já não houver um erro de metadados
        if (!error) {
          setError(`Não foi possível carregar os dados.`);
        }
      } finally {
        setIsFetchingData(false);
      }
    };

    fetchData();
  }, [metadata, page, limit, debouncedSearchTerm, statusFilter]);

  const fieldMetaMap = useMemo(() => {
    if (!metadata) return new Map();

    const map = new Map();
    metadata.fields.forEach(field => {
      map.set(field.name, field);
    });
    return map;
  }, [metadata]); // Só roda quando os metadados mudam

  const handleDeleteClick = () => {
    // Só abre o modal se um item estiver selecionado
    if (!selectedRowId) return;
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    // Não reseta o ID aqui, para o caso de cancelar
  };

  const handleConfirmDelete = async () => {
    if (!selectedRowId) return;
    try {
      await api.delete(`/generic/${modelName}/${selectedRowId}`);
      setData(data.filter((item) => item.id !== selectedRowId));
      // Reseta o ID após a exclusão
      setSelectedRowId(null);
    } catch (err) {
      console.error('Falha ao excluir:', err);
      alert('Não foi possível excluir o item.');
    } finally {
      setIsModalOpen(false); // Fecha o modal
    }
  };

  const handleEditClick = () => {
    if (selectedRowId) {
      // Adiciona o "/edit/" no caminho para bater com a rota do App.jsx
      navigate(`/${modelName}/edit/${selectedRowId}`);
    }
  };

  /** * 1. Abre o modal genérico populando o estado 'actionToConfirm' * @param {object} actionDetails - O objeto de ação vindo da config 'statusChangeActions' */
  const handleStatusChangeClick = (actionDetails) => {
    if (!selectedRowId) return;
    setActionToConfirm(actionDetails);
  };

  /** * 2. Fecha o modal genérico limpando o estado. */
  const handleCloseStatusModal = () => {
    setActionToConfirm(null);
  };

  /** * 3. Confirma a ação, envia o PUT e atualiza a UI. * Usa os dados do estado 'actionToConfirm'. */
  const handleConfirmStatusChange = async () => {
    if (!selectedRowId || !actionToConfirm) return;

    // Pega os detalhes da ação que está no estado
    const { newStatus, errorLog, errorAlert } = actionToConfirm;

    try {
      // Faz a chamada PUT, alterando APENAS a situação
      await api.put(`/generic/${modelName}/${selectedRowId}`, {
        situacao: newStatus // Usa o novo status vindo da ação
      });

      // Remove o item da lista atual
      setData(data.filter((item) => item.id !== selectedRowId));
      setTotalCount(prevCount => prevCount - 1); // Ajusta a contagem
      setSelectedRowId(null);

    } catch (err) {
      console.error(errorLog, err); // Usa o log de erro da ação
      alert(errorAlert); // Usa o alerta de erro da ação
    } finally {
      setActionToConfirm(null); // Fecha o modal
    }
  };

  /**
    * 1. Busca os dados completos do pedido e abre o modal.
    */
  const handleOpenProgramacaoModal = async () => {
    if (!selectedRowId) return;

    setIsFetchingDetails(true);
    setIsProgramacaoModalOpen(true); // Abre o modal (vai mostrar um loading)

    try {
      // Busca o pedido completo
      const res = await api.get(`/generic/pedidos/${selectedRowId}`);
      setCurrentPedidoDetails(res.data); // Seta os dados

    } catch (err) {
      console.error("Falha ao buscar detalhes do pedido:", err);
      alert("Não foi possível carregar os detalhes do pedido.");
      setIsProgramacaoModalOpen(false); // Fecha o modal se der erro
    } finally {
      setIsFetchingDetails(false);
    }
  };

  /**
   * 2. Fecha o modal de programação e limpa os dados.
   */
  const handleCloseProgramacaoModal = () => {
    setIsProgramacaoModalOpen(false);
    setCurrentPedidoDetails(null);
  };

  /**
   * 3. (Será passada para o modal) Salva os dados do formulário.
   * @param {object} payload - O objeto vindo do modal (com situacao, itens, etc)
   */
  const handleSaveProgramacao = async (payload) => {
    if (!selectedRowId) return;

    try {
      // O modal já preparou o payload, só precisamos enviar
      await api.put(`/generic/pedidos/${selectedRowId}`, payload);

      // Sucesso! Remove o item da lista atual
      setData(data.filter((item) => item.id !== selectedRowId));
      setTotalCount(prevCount => prevCount - 1);
      setSelectedRowId(null);

      // Fecha o modal
      handleCloseProgramacaoModal();

    } catch (err) {
      console.error("Falha ao salvar programação do pedido:", err);
      alert("Não foi possível salvar a programação. Verifique os dados e tente novamente.");
      // NOTA: Não fechamos o modal, para o usuário corrigir
    }
  };


  const handleExportCSV = async () => {
    setIsExporting(true);
    try {
      const params = {};
      // Usa o termo de busca atual para filtrar a exportação
      if (debouncedSearchTerm) {
        params.search_term = debouncedSearchTerm;
      }

      // Chama o novo endpoint de exportação
      const response = await api.get(`/generic/${modelName}/export`, {
        params,
        responseType: 'blob', // Importante: informa ao axios para tratar a resposta como um arquivo (blob)
      });

      // Cria uma URL temporária para o arquivo (blob)
      const url = window.URL.createObjectURL(new Blob([response.data]));

      // Cria um link "invisível" para acionar o download
      const link = document.createElement('a');
      link.href = url;

      // Tenta pegar o nome do arquivo do header, ou usa um padrão
      const contentDisposition = response.headers['content-disposition'];
      let filename = `${modelName}_export.csv`; // Padrão
      if (contentDisposition) {
        const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/);
        if (filenameMatch && filenameMatch.length > 1) {
          filename = filenameMatch[1];
        }
      }

      link.setAttribute('download', filename); // Define o nome do arquivo

      // Adiciona o link ao DOM, clica nele, e o remove
      document.body.appendChild(link);
      link.click();
      link.remove();

      // Libera a URL do objeto da memória
      window.URL.revokeObjectURL(url);

    } catch (err) {
      console.error('Falha ao exportar CSV:', err);
      // Você pode substituir isso por um toast/notificação
      alert('Não foi possível gerar o arquivo CSV.');
    } finally {
      setIsExporting(false);
    }
  };

  const totalPages = Math.ceil(totalCount / limit) || 1; // || 1 para evitar 0

  // Loading inicial (enquanto busca metadados)
  if (loadingMetadata) {
    return <LoadingSpinner />;
  }

  // Erro fatal (se os metadados falharam)
  if (error && !metadata) {
    return <div className="text-red-500 p-6">{error}</div>;
  }

  // Se o loading terminou mas os metadados não vieram
  if (!metadata) {
    return <div className="p-6">Metadados não encontrados.</div>;
  }

  // Pega o nome plural direto dos metadados (que agora vem do backend)
  const pageTitlePlural = metadata.display_name_plural || metadata.display_name;

  const pageTitle = statusFilter ? `${pageTitlePlural} (${statusFilter})` : pageTitlePlural;

  // Pega os nomes das colunas dos metadados
  const columns = metadata.fields.map((field) => field.name);

  // Na imagem, a coluna ID é mostrada. 
  // Vamos garantir que 'id' esteja na lista de colunas e seja a primeira.
  const displayColumns = columns.filter(col => col !== 'id');


  return (
    // Fundo cinza claro para a página, como na imagem
    <div className="bg-gray-100 min-h-screen p-16">
      <div className="container mx-auto">
        {/* Header (Título) */}
        <h1 className="text-4xl font-bold text-gray-800 mb-6">
          {pageTitle}
        </h1>

        {/* Barra de Ações e Filtros (Baseado na Imagem) */}
        <div className="flex flex-wrap justify-between items-center gap-4 mb-6">
          {/* Botões Lado Esquerdo */}
          <div className="flex gap-2">
            <Link
              to={`/${modelName}/new`}
              className="flex items-center px-4 py-2 bg-green-600 text-white rounded-md shadow-sm hover:bg-green-700 text-sm font-medium"
            >
              <Plus size={16} className="mr-2" />
              Novo
            </Link>
            <button
              onClick={handleExportCSV}
              disabled={isExporting || isFetchingData} // Desabilita se estiver exportando ou buscando dados
              className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-md shadow-sm hover:bg-blue-700 text-sm font-medium disabled:bg-blue-400 disabled:cursor-not-allowed"
            >
              {isExporting ? (
                <Loader2 size={16} className="mr-2 animate-spin" />
              ) : (
                <FileDown size={16} className="mr-2" />
              )}
              {isExporting ? 'Exportando...' : 'Exportar CSV'}
            </button>
          </div>

          {/* Filtros Lado Direito (Conforme a Imagem) */}
          <div className="flex flex-wrap items-center gap-2">
            {/* --- CAMPO DE BUSCA --- */}
            <div className="relative">
              <input
                type="text"
                placeholder="Buscar..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10 pr-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              {/* Ícone dinâmico: Mostra o spinner ou a lupa */}
              {isFetchingData ? (
                <Loader2
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 animate-spin"
                  size={18}
                />
              ) : (
                <Search
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
                  size={18}
                />
              )}
            </div>

            {/* Botão Editar Atualizado */}
            <button
              onClick={handleEditClick}
              disabled={!selectedRowId} // Desabilitado se nada selecionado
              className="flex items-center px-4 py-2 bg-blue-500 text-white rounded-md shadow-sm hover:bg-blue-600 text-sm font-medium disabled:cursor-not-allowed"
            >
              <Edit size={16} className="mr-2" />
              Editar
            </button>

            {/* Novo Botão Deletar */}
            <button
              onClick={handleDeleteClick} // Chama a função que abre o modal
              disabled={!selectedRowId} // Desabilitado se nada selecionado
              className="flex items-center px-4 py-2 bg-red-600 text-white rounded-md shadow-sm hover:bg-red-700 text-sm font-medium disabled:cursor-not-allowed"
            >
              <Trash2 size={16} className="mr-2" />
              Deletar
            </button>

            {/* BOTÕES DE STATUS RENDERIZADOS DINAMICAMENTE */}
            {
              statusChangeActions[modelName]?.map(action => {
                // Só mostra o botão se o filtro de status atual bater
                if (action.currentStatus !== statusFilter) {
                  return null;
                }

                const Icon = action.buttonIcon; // Pega o componente do ícone

                let onClickAction;
                if (action.onClickHandler === 'programar') {
                  onClickAction = handleOpenProgramacaoModal;
                } else {
                  // O padrão genérico
                  onClickAction = () => handleStatusChangeClick(action);
                }

                return (
                  <button
                    key={action.newStatus}
                    onClick={onClickAction} // <-- USA A AÇÃO CORRETA
                    // Desabilita se estiver buscando detalhes para o modal complexo
                    disabled={!selectedRowId || isFetchingData || isFetchingDetails}
                    className={`flex items-center px-4 py-2 text-white rounded-md shadow-sm text-sm font-medium disabled:cursor-not-allowed ${action.buttonClasses}`}
                  >
                    {/* 7. MOSTRAR LOADING SE ESTIVER BUSCANDO DETALHES */}
                    {(isFetchingDetails && action.onClickHandler === 'programar') ? (
                      <Loader2 size={16} className="mr-2 animate-spin" />
                    ) : (
                      <Icon size={16} className="mr-2" />
                    )}
                    {action.buttonLabel}
                  </button>
                );
              })
            }
          </div>
        </div>

        {/* Card Principal (Listagem) */}
        <div
          className={`bg-white rounded-lg shadow-md overflow-hidden transition-opacity ${isFetchingData ? 'opacity-60' : 'opacity-100'
            }`}
        >
          {/* Tabela de Dados */}
          <div className="overflow-x-auto">
            <table className="w-full min-w-max">
              {/* Cabeçalho da Tabela - Estilizado como na imagem */}
              <thead className="bg-gray-50">
                <tr className="border-b border-gray-200">
                  {/* Colunas Dinâmicas */}
                  {displayColumns.map((colName) => (
                    <th
                      key={colName}
                      className="px-6 py-4 text-left text-sm font-semibold text-gray-600 uppercase tracking-wider"
                    >
                      {/* Tenta buscar o label do metadata. Se for 'id', usa 'ID'. */}
                      {metadata.fields.find((f) => f.name === colName)?.label ||
                        (colName === 'id' ? 'ID' : colName)}
                    </th>
                  ))}

                </tr>
              </thead>

              {/* Corpo da Tabela */}
              <tbody className="bg-white">
                {/* 8. Feedback de 'Nenhum resultado' ou 'Erro de dados' */}
                {!isFetchingData && error && data.length === 0 && (
                  <tr>
                    <td colSpan={displayColumns.length} className="px-6 py-4 text-center text-red-500">
                      {error}
                    </td>
                  </tr>
                )}
                {!isFetchingData && !error && data.length === 0 && (
                  <tr>
                    <td colSpan={displayColumns.length} className="px-6 py-4 text-center text-gray-500">
                      Nenhum registro encontrado.
                    </td>
                  </tr>
                )}
                {data.map((item) => (
                  <tr
                    key={item.id}
                    onClick={() => setSelectedRowId(item.id === selectedRowId ? null : item.id)}
                    className={`border-b border-gray-200 cursor-pointer ${selectedRowId === item.id ? 'bg-blue-100' : 'hover:bg-gray-50'
                      }`}
                  >
                    {/* Renderiza as células de cada linha */}
                    {displayColumns.map((colName) => {

                      // --- LÓGICA DE RENDERIZAÇÃO DA CÉLULA ---
                      const value = item[colName];
                      // Busca o 'field' (ex: {name: "is_active", type: "boolean"})
                      const field = fieldMetaMap.get(colName);

                      return (
                        <td
                          key={colName}
                          className="px-6 py-4 whitespace-nowrap text-sm text-gray-700"
                        >
                          {/* Lógica de exibição: 1. Se for booleano, mostra o Badge. 2. Se for senha (verificando metadados ou nome da coluna), mostra asteriscos. 3. Senão, mostra o valor. */}
                          {(field && field.type === 'boolean')
                            ? <BooleanDisplay value={value} />
                            : (field && field.ui_type === 'password') || // Verifica metadados (ex: ui_type)
                              colName.toLowerCase().includes('password') || // Fallback pelo nome (inglês)
                              colName.toLowerCase().includes('senha') // Fallback pelo nome (português)
                              ? '*********'
                              : value
                          }
                        </td>
                      );
                      // --- FIM DA LÓGICA DE RENDERIZAÇÃO ---
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Paginação (Estilizada como na imagem) */}
        <div className="flex items-center justify-between mt-6">
          {/* Mostra o total de registros (Condicional) */}
          {totalCount > 0 ? (
            <span className="text-sm text-gray-700">
              Mostrando {data.length} de {totalCount} registros
            </span>
          ) : (
            /* Um placeholder para manter o justify-between funcionando */
            <span></span>
          )}

          <div className="flex items-center gap-4">
            <button
              onClick={() => setPage(p => p - 1)}
              disabled={page <= 1 || isFetchingData} // <-- Atualizado
              className="flex items-center px-4 py-2 bg-white border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:bg-gray-100 disabled:text-gray-400 disabled:cursor-not-allowed"
            >
              <ChevronLeft size={16} className="mr-1" />
              Anterior
            </button>
            <span className="text-sm text-gray-700">
              Página {page} de {totalPages}
            </span>
            <button
              onClick={() => setPage(p => p + 1)}
              disabled={page >= totalPages || isFetchingData} // <-- Atualizado
              className="flex items-center px-4 py-2 bg-white border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:bg-gray-100 disabled:text-gray-400 disabled:cursor-not-allowed"
            >
              Próxima
              <ChevronRight size={16} className="ml-1" />
            </button>
          </div>
        </div>

        {/* --- MODAL --- */}
        <Modal
          isOpen={isModalOpen}
          onClose={handleCloseModal} // Fechar não reseta mais o ID
          onConfirm={handleConfirmDelete} // Confirmar faz a ação e reseta o ID
          title="Confirmar Exclusão"
          variant="danger"
          confirmText="Excluir"
        >
          Tem certeza que deseja excluir este item? Esta ação não pode ser
          desfeita.
        </Modal>

        {/* 5. MODAL GENÉRICO DE MUDANÇA DE STATUS (ÚNICO)                     */}
        <Modal
          isOpen={!!actionToConfirm} // Abre se actionToConfirm não for null
          onClose={handleCloseStatusModal}
          onConfirm={handleConfirmStatusChange}
          // Popula o modal com os dados do estado 'actionToConfirm'
          title={actionToConfirm?.modalTitle || "Confirmar Ação"}
          variant="info" // Nossas ações são 'info' (azul)
          confirmText={actionToConfirm?.modalConfirmText || "Confirmar"}
        >
          {actionToConfirm?.modalDescription || "Você tem certeza?"}
        </Modal>

        <ProgramacaoPedidoModal
          isOpen={isProgramacaoModalOpen}
          onClose={handleCloseProgramacaoModal}
          onSave={handleSaveProgramacao}
          pedido={currentPedidoDetails} // Passa o pedido completo
        // O modal vai mostrar seu próprio loading se 'pedido' for nulo
        />
      </div>
    </div >
  );
};

export default GenericList;

