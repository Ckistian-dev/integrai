import React, { useState, useEffect, useMemo, Fragment, useRef } from 'react';
// Removendo imports não utilizados (useParams, Link) e adicionando (LayoutGrid)
// Manterei o Link e o useParams, pois "Novo" e a lógica do modelName ainda os utilizam.
import DatePicker, { registerLocale } from "react-datepicker";
import "react-datepicker/dist/react-datepicker.css";
import ptBR from 'date-fns/locale/pt-BR';
import { Dialog, Transition, Popover, Menu } from '@headlessui/react';
import { useParams, useNavigate, Link, useOutletContext } from 'react-router-dom';
import { toast } from 'react-toastify';
import { useAuth } from '../contexts/AuthContext';
import api from '../api/axiosConfig';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import ProgramacaoPedidoModal from '../components/ui/ProgramacaoPedidoModal'; // 1. IMPORTAR O NOVO MODAL
import ModalVisualizarPedido from '../components/ModalVisualizarPedido'; // Importar o modal de visualização
import ConferenciaPedidoModal from '../components/ui/ConferenciaPedidoModal'; // Importar o modal de conferência
import FaturamentoModal from '../components/ui/FaturamentoModal';
import ModalCotacaoIntelipost from '../components/ui/ModalCotacaoIntelipost'; // Ajuste o caminho
import ModalImportacaoDfe from '../components/ui/ModalImportacaoDfe'; // NOVO COMPONENTE
import ModalInventario from '../components/ui/ModalInventario'; // Modal de Inventário
import Modal from '../components/ui/Modal';
import { DefaultFiltersInput } from '../components/ui/InputFields';
import {
  Plus,
  Edit,
  Trash2,
  FileDown,
  ChevronLeft,
  ChevronDown,
  ChevronRight,
  Search,
  Loader2,
  CheckSquare,
  Check,
  ThumbsUp,
  Send,
  Package,
  CheckCircle,
  Eye,
  Box,
  Truck,
  Filter,
  Settings,
  X,
  RefreshCw,
  SlidersHorizontal,
  Ban,
  FileText,
  RotateCcw,
  Tag,
  Calendar,
  Play,
  GripVertical,
  ArrowUp,
  ArrowDown,
  FileCode,
  Download,
  ClipboardList,
  AlertCircle
} from 'lucide-react';
import { MODULE_MAP, HUMAN_MODEL_NAMES, Breadcrumb } from '../components/layout/breadcrumbUtils';

registerLocale('pt-BR', ptBR);

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

// Helper para formatar labels dinâmicos (ex: customer_name -> Customer Name)
const formatLabel = (key) => {
  if (!key) return '';
  if (key === 'id_sequencial' || key === 'id') return 'ID';
  return key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
};

const formatCurrency = (value) => {
  if (value === null || value === undefined || value === '') return '';
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Number(value));
};

const formatDate = (value) => {
  if (!value) return '';
  return new Date(value).toLocaleString('pt-BR');
};

const formatDisplayValue = (value) => {
  // Se for uma string com underscore (provavelmente um enum não mapeado), formata para leitura.
  // Ex: "em_aberto" -> "Em Aberto". Ignora se tiver ponto (nomes de arquivo).
  if (typeof value === 'string' && value.includes('_') && !value.includes('.')) {
    return formatLabel(value);
  }
  return value;
};

const BooleanDisplay = ({ value, trueLabel = 'Ativo', falseLabel = 'Inativo', trueColor = 'green', falseColor = 'gray' }) => {
  const text = value ? trueLabel : falseLabel;
  // Nota: Para Tailwind JIT funcionar com cores dinâmicas, as classes completas devem existir no bundle.
  const bgColor = value ? `bg-${trueColor}-100` : `bg-${falseColor}-100`;
  const textColor = value ? `text-${trueColor}-800` : `text-${falseColor}-800`;

  return (
    <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${bgColor} ${textColor}`}>
      {text}
    </span>
  );
};

const TableSkeleton = ({ columns, rows = 5 }) => {
  const widths = ['w-1/2', 'w-3/4', 'w-2/3', 'w-full', 'w-5/6'];
  return (
    <>
      {[...Array(rows)].map((_, rowIndex) => (
        <tr key={rowIndex} className="border-b border-gray-50">
          {columns.map((col, colIndex) => (
            <td key={colIndex} className="px-6 py-5">
              {col !== '' && (
                <div className={`h-3 bg-gray-200 rounded-full animate-pulse ${colIndex === 0 ? 'w-12' : widths[(rowIndex + colIndex) % widths.length]
                  }`}></div>
              )}
            </td>
          ))}
        </tr>
      ))}
    </>
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
      buttonClasses: "bg-purple-600 hover:bg-purple-700",
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
      buttonClasses: "bg-green-600 hover:bg-green-700",
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
      buttonClasses: "bg-cyan-600 hover:bg-cyan-700",
      // Chave especial para nosso handler customizado
      onClickHandler: 'programar'
    },
    {
      // Ação para finalizar Produção -> ir para Embalagem
      currentStatus: "Produção",
      newStatus: "Embalagem",
      buttonLabel: "Finalizar Produção",
      buttonIcon: Package,
      buttonClasses: "bg-indigo-600 hover:bg-indigo-700",
      onClickHandler: 'conferencia', // Handler genérico para conferência
      modalTitle: "Conferência de Produção",
      modalConfirmText: "Confirmar e Enviar para Embalagem",
      modalVariant: "indigo"
    },
    {
      currentStatus: "Embalagem",
      newStatus: "Embalagem",
      buttonLabel: "Etiqueta Volume",
      buttonIcon: Tag,
      buttonClasses: "bg-yellow-600 hover:bg-yellow-700",
      onClickHandler: 'imprimir_etiqueta_volume'
    },

    {
      // Ação para finalizar Embalagem -> ir para Expedição
      currentStatus: "Embalagem",
      newStatus: "Faturamento",
      buttonLabel: "Finalizar Embalagem",
      buttonIcon: CheckCircle,
      buttonClasses: "bg-teal-600 hover:bg-teal-700",
      onClickHandler: 'conferencia',
      modalTitle: "Conferência de Embalagem",
      modalConfirmText: "Concluir Embalagem",
      modalVariant: "teal",
      showVolumes: true
    },

    {
      currentStatus: "Faturamento", // Ou o nome exato do status anterior à expedição
      newStatus: "Expedição",
      buttonLabel: "Faturar",
      buttonIcon: Box, // ou DollarSign
      buttonClasses: "bg-emerald-600 hover:bg-emerald-700",
      onClickHandler: 'faturamento' // Handler específico
    },
    {
      currentStatus: "Expedição",
      newStatus: "Expedição",
      buttonLabel: "DANFE",
      buttonIcon: FileDown,
      buttonClasses: "bg-gray-600 hover:bg-gray-700",
      onClickHandler: 'download_danfe'
    },
    {
      currentStatus: "Expedição",
      newStatus: "Expedição",
      buttonLabel: "Etiqueta",
      buttonIcon: Tag,
      buttonClasses: "bg-pink-600 hover:bg-pink-700",
      onClickHandler: 'imprimir_etiqueta'
    },
    {
      currentStatus: "Nota Fiscal",
      newStatus: "Nota Fiscal",
      buttonLabel: "DANFE",
      buttonIcon: FileDown,
      buttonClasses: "bg-gray-600 hover:bg-gray-700",
      onClickHandler: 'download_danfe'
    },
    {
      currentStatus: "Nota Fiscal",
      newStatus: "Cancelado",
      buttonLabel: "Cancelar NFe",
      buttonIcon: Ban,
      buttonClasses: "bg-red-500 hover:bg-red-600",
      onClickHandler: 'cancelar_nfe'
    },
    {
      currentStatus: "Expedição",
      newStatus: "Despachado",
      buttonLabel: "Despachar",
      buttonIcon: Truck,
      buttonClasses: "bg-indigo-600 hover:bg-indigo-700",
      modalTitle: "Despachar Pedido",
      modalDescription: "Deseja marcar este pedido como Despachado? Isso indica que ele saiu para entrega.",
      modalConfirmText: "Sim, Despachar"
    },
    {
      currentStatus: "Nota Fiscal",
      newStatus: "Despachado", // Ajustado de Finalizado para Despachado
      buttonLabel: "Corrigir NFE",
      buttonIcon: FileText,
      buttonClasses: "bg-orange-500 hover:bg-orange-600",
      onClickHandler: 'carta_correcao'
    },
    {
      currentStatus: "Nota Fiscal",
      newStatus: "Despachado", // Ajustado de Finalizado para Despachado
      buttonLabel: "Devolução",
      buttonIcon: RotateCcw,
      buttonClasses: "bg-red-600 hover:bg-red-700",
      onClickHandler: 'devolucao'
    },
    {
      currentStatus: "Nota Fiscal",
      newStatus: "Despachado",
      buttonLabel: "Complemento",
      buttonIcon: Plus,
      buttonClasses: "bg-teal-600 hover:bg-teal-700",
      onClickHandler: 'complemento'
    }
  ]
};

const getSortArray = (sort, hasIdSeq = false) => {
  if (!sort) return [];
  let arr = [];
  if (Array.isArray(sort)) arr = [...sort];
  else if (sort && sort.field) arr = [sort];

  arr = arr.filter(s => s && s.field);

  if (hasIdSeq) {
    arr = arr.map(s => (s.field === 'id' ? { ...s, field: 'id_sequencial' } : s));
  }
  return arr;
};

const GenericList = () => {
  const { modelName: paramModelName, statusFilter } = useParams();
  const isIntelipostView = paramModelName === 'intelipost';
  const isMeliView = paramModelName === 'mercadolivre_pedidos';
  const isMagentoView = paramModelName === 'magento_pedidos';
  const isTiktokView = paramModelName === 'tiktok_pedidos';
  const isShopeeView = paramModelName === 'shopee_pedidos';
  const isEmailRulesView = paramModelName === 'email_regras';

  const modelName = isMeliView ? 'mercadolivre_pedidos' :
    isMagentoView ? 'magento_pedidos' :
      isTiktokView ? 'tiktok_pedidos' :
        isShopeeView ? 'shopee_pedidos' :
          (paramModelName === 'intelipost' ? 'pedidos' : paramModelName);

  const navigate = useNavigate();
  const { user } = useAuth();

  // --- LÓGICA DE PERMISSÕES GRANULARES ---
  // Mapeia o modelName da rota para a chave de permissão correta
  const permissionKey = useMemo(() => {
    // Para as visualizações de integração, a chave de permissão é 'integracoes'
    if (isMeliView || isMagentoView || isTiktokView || isShopeeView || isIntelipostView) {
      return 'integracoes';
    }
    if (paramModelName === 'perfis') {
      return 'usuarios';
    }
    return modelName; // Fallback para o nome do modelo principal
  }, [paramModelName, modelName, isMeliView, isMagentoView, isIntelipostView]);

  const userPermissions = user?.permissoes?.[permissionKey] || { acesso: false, acoes: [], colunas: [], subpaginas: [] };

  // Se for admin, libera tudo. Se não, checa a lista de ações.
  const canCreate = user?.perfil === 'admin' || userPermissions.acoes?.includes('create');
  const canEdit = user?.perfil === 'admin' || userPermissions.acoes?.includes('edit');
  const canDelete = user?.perfil === 'admin' || userPermissions.acoes?.includes('delete');
  const canExport = user?.perfil === 'admin' || userPermissions.acoes?.includes('export');
  // ---------------------------------------

  // --- PROTEÇÃO DE SUBPÁGINAS (STATUS) ---
  useEffect(() => {
    if (user?.perfil === 'admin') return;

    // Verifica se é o módulo de pedidos (que usa abas de status controladas) e se tem filtro
    if (permissionKey === 'pedidos') {
      const currentSub = statusFilter || 'Todos';
      const allowedSubpages = userPermissions.subpaginas || [];
      if (!allowedSubpages.includes(currentSub)) {
        toast.error(`Você não tem permissão para acessar a aba: ${currentSub}`);
        navigate('/dashboard');
      }
    }
  }, [statusFilter, userPermissions, user, navigate, modelName, permissionKey]);

  const [metadata, setMetadata] = useState(null);
  const [data, setData] = useState([]);

  const [loadingPreferences, setLoadingPreferences] = useState(true);
  const [loadingMetadata, setLoadingMetadata] = useState(true);
  const [isFetchingData, setIsFetchingData] = useState(false);
  const [exportingFormat, setExportingFormat] = useState(null);
  const [error, setError] = useState('');

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [actionToConfirm, setActionToConfirm] = useState(null);

  const [isProgramacaoModalOpen, setIsProgramacaoModalOpen] = useState(false);
  const [currentPedidoDetails, setCurrentPedidoDetails] = useState(null);
  const [isFetchingDetails, setIsFetchingDetails] = useState(false);

  const [isConferenciaModalOpen, setIsConferenciaModalOpen] = useState(false);
  const [conferenciaConfig, setConferenciaConfig] = useState(null);

  const [isFaturamentoModalOpen, setIsFaturamentoModalOpen] = useState(false);
  const [isBatchFaturamentoModalOpen, setIsBatchFaturamentoModalOpen] = useState(false);
  const [pedidoParaFaturar, setPedidoParaFaturar] = useState(null);

  const [isVisualizarModalOpen, setIsVisualizarModalOpen] = useState(false);
  const [pedidoParaVisualizar, setPedidoParaVisualizar] = useState(null);

  const [isDfeImportModalOpen, setIsDfeImportModalOpen] = useState(false);
  const [notaParaImportar, setNotaParaImportar] = useState(null);

  const [isFilterModalOpen, setIsFilterModalOpen] = useState(false);
  const [magentoConfig, setMagentoConfig] = useState(null);

  const [isIntelipostModalOpen, setIsIntelipostModalOpen] = useState(false);
  const [pedidoParaCotar, setPedidoParaCotar] = useState(null);

  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [isTiktokAuthModalOpen, setIsTiktokAuthModalOpen] = useState(false);
  const [isMeliAuthModalOpen, setIsMeliAuthModalOpen] = useState(false);
  const [pendingAuthUrl, setPendingAuthUrl] = useState('');
  const [ordersToImport, setOrdersToImport] = useState([]);

  // --- ESTADOS PARA MODAL DANFE (COMPLETA / SIMPLIFICADA) ---
  const [isDanfeModalOpen, setIsDanfeModalOpen] = useState(false);
  const [danfeModalIds, setDanfeModalIds] = useState([]);

  // --- ESTADOS PARA CANCELAMENTO NFE ---
  const [isCancelNFeModalOpen, setIsCancelNFeModalOpen] = useState(false);
  const [cancelJustification, setCancelJustification] = useState('');

  // --- ESTADOS PARA CARTA DE CORREÇÃO ---
  const [isCCeModalOpen, setIsCCeModalOpen] = useState(false);
  const [cceText, setCceText] = useState('');

  // --- ESTADO PARA DEVOLUÇÃO ---
  const [isDevolucaoModalOpen, setIsDevolucaoModalOpen] = useState(false);

  // --- ESTADO PARA COMPLEMENTO ---
  const [isComplementoModalOpen, setIsComplementoModalOpen] = useState(false);
  const [isFetchingComplementoDetails, setIsFetchingComplementoDetails] = useState(false);
  const [complementoData, setComplementoData] = useState({
    tipo_complemento: 'preco',
    itens: [],
    observacoes_nf: ''
  });
  const [activeTaxTabs, setActiveTaxTabs] = useState({});
  const [pedidoOriginal, setPedidoOriginal] = useState(null);

  const totalComplemento = useMemo(() => {
    let totalItens = 0;
    let totalIcms = 0;
    let totalIpi = 0;
    let totalPis = 0;
    let totalCofins = 0;

    const itens = Array.isArray(complementoData.itens) ? complementoData.itens : [];
    itens.forEach(item => {
      const targetSubtotal = (Number(item.quantidade) || 0) * (Number(item.valor_unitario) || 0);
      const originalSubtotal = (item.quantidade_original || 0) * (item.valor_unitario_original || 0);
      totalItens += Math.max(0, targetSubtotal - originalSubtotal);

      totalIcms += Math.max(0, (Number(item.icms_valor) || 0) - (item.icms_valor_original || 0));
      totalIpi += Math.max(0, (Number(item.ipi_valor) || 0) - (item.ipi_valor_original || 0));
      totalPis += Math.max(0, (Number(item.pis_valor) || 0) - (item.pis_valor_original || 0));
      totalCofins += Math.max(0, (Number(item.cofins_valor) || 0) - (item.cofins_valor_original || 0));
    });

    return { totalItens, totalIcms, totalIpi, totalPis, totalCofins };
  }, [complementoData.itens]);

  // --- ESTADO PARA INVENTÁRIO ---
  const [isInventarioModalOpen, setIsInventarioModalOpen] = useState(false);

  // Lógica de agrupamento para a aba de Inventário do Estoque (Movido para o topo para respeitar as regras de hooks)
  const groupedData = useMemo(() => {
    if (modelName === 'estoque' && statusFilter === 'Inventário' && data) {
      const groups = {};
      data.forEach(item => {
        const date = new Date(item.criado_em);
        const windowMs = 1 * 60 * 1000; // Janela de 1 minuto
        const windowKey = Math.floor(date.getTime() / windowMs) * windowMs;
        const key = `${windowKey}`;
        if (!groups[key]) {
          groups[key] = {
            key,
            data_hora: item.criado_em,
            itens: []
          };
        }
        groups[key].itens.push(item);
      });
      return Object.values(groups).sort((a, b) => new Date(b.data_hora) - new Date(a.data_hora));
    }
    return null;
  }, [modelName, statusFilter, data]);

  const [selectedRowIds, setSelectedRowIds] = useState([]);
  const [selectedGroupKey, setSelectedGroupKey] = useState(null);

  const selectedRowId = selectedRowIds.length > 0 ? selectedRowIds[0] : null;
  const selectedItem = useMemo(() => data.find(i => i.id === selectedRowId), [selectedRowId, data]);

  // A seleção agora é baseada no GRUPO (cabeçalho) para o módulo de estoque/inventário
  const isInventorySelected = modelName === 'estoque' && selectedGroupKey !== null;

  const selectedItemName = useMemo(() => {
    if (selectedRowIds.length === 1) {
      const item = selectedItem;
      return item?.descricao || item?.id;
    }
    return null;
  }, [selectedItem, selectedRowIds.length]);
  const [anchorIndex, setAnchorIndex] = useState(-1);
  const [focusIndex, setFocusIndex] = useState(-1);
  const [caixaOptions, setCaixaOptions] = useState([]);
  const [selectedCaixa, setSelectedCaixa] = useState('');
  const [isBatchBaixaModalOpen, setIsBatchBaixaModalOpen] = useState(false);

  const [searchTerm, setSearchTerm] = useState("");
  const debouncedSearchTerm = useDebounce(searchTerm, 500);
  const [searchColumn, setSearchColumn] = useState("");

  // --- ESTADOS PARA FILTRO RÁPIDO DE DATA ---
  const [dateFilterColumn, setDateFilterColumn] = useState("");
  const [dateStart, setDateStart] = useState("");
  const [dateEnd, setDateEnd] = useState("");

  // --- ESTADOS PARA FILTRO RÁPIDO DE DROPDOWN ---
  const [dropdownFilterColumn, setDropdownFilterColumn] = useState("");
  const [dropdownFilterValue, setDropdownFilterValue] = useState("");

  // --- ESTADOS PARA FILTROS RÁPIDOS DINÂMICOS ---
  const [quickFilterValues, setQuickFilterValues] = useState({});
  const debouncedQuickFilterValuesJson = useDebounce(JSON.stringify(quickFilterValues), 500);
  const debouncedQuickFilterValues = useMemo(() => JSON.parse(debouncedQuickFilterValuesJson), [debouncedQuickFilterValuesJson]);

  const [magentoDynamicFilters, setMagentoDynamicFilters] = useState([]);
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(10);
  const [totalCount, setTotalCount] = useState(0);
  const [totals, setTotals] = useState({});
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  // --- ESTADOS PARA EDIÇÃO DE TABELA ---
  const [isEditMode, setIsEditMode] = useState(false);
  const [addColumnSearch, setAddColumnSearch] = useState("");
  const [userPreferences, setUserPreferences] = useState({ visibleColumns: null, columnWidths: {}, filters: [], sort: [{ field: 'id', direction: 'desc' }] });
  const [columnsToDisplay, setColumnsToDisplay] = useState([]); // Colunas efetivamente renderizadas
  const [draggedColName, setDraggedColName] = useState(null);
  const [dragTargetColName, setDragTargetColName] = useState(null);

  // Pré-visualização dinâmica em tempo real da tabela enquanto arrasta a coluna
  const displayColumns = useMemo(() => {
    if (!draggedColName || !dragTargetColName || draggedColName === dragTargetColName) {
      return columnsToDisplay;
    }
    const fromIdx = columnsToDisplay.indexOf(draggedColName);
    const toIdx = columnsToDisplay.indexOf(dragTargetColName);
    if (fromIdx === -1 || toIdx === -1) return columnsToDisplay;

    const result = [...columnsToDisplay];
    const [removed] = result.splice(fromIdx, 1);
    result.splice(toIdx, 0, removed);
    return result;
  }, [columnsToDisplay, draggedColName, dragTargetColName]);

  // --- LÓGICA DE TOTAIS E LIMITE EFETIVO ---
  // A paginação deve ser baseada estritamente no limite selecionado pelo usuário
  // para evitar problemas de deslocamento de offset, duplicação e linhas ocultas.
  // A linha de totais (se existir) será renderizada como uma linha adicional no final da tabela.
  const hasTotalsField = useMemo(() => {
    return (modelName === 'pedidos' || modelName === 'contas') && Object.keys(totals || {}).length > 0;
  }, [modelName, totals]);

  const effectiveLimit = limit;

  // Estabiliza as dependências do useEffect para evitar loops infinitos
  const filtersJson = JSON.stringify(userPreferences.filters);
  const sortsJson = JSON.stringify(userPreferences.sort);

  useEffect(() => {
    const fetchMetadata = async () => {
      setLoadingMetadata(true);
      setLoadingPreferences(true); // Bloqueia a busca de dados até que as preferências do novo modelo sejam carregadas
      setIsFetchingData(true); // Também ativamos este para o loading inicial
      setError('');
      setMetadata(null); // Limpa metadados antigos
      setData([]); // Limpa dados antigos
      setTotals({}); // Limpa totais antigos
      setPage(1); // Reseta a página
      setSearchTerm(""); // Reseta a busca
      setSearchColumn(""); // Reseta a coluna de busca
      setDateFilterColumn(""); // Reseta filtro de data
      setDateStart("");
      setDateEnd("");
      setDropdownFilterColumn(""); // Reseta filtro de dropdown
      setDropdownFilterValue("");

      // Reseta estados que podem persistir entre navegações e causar conflitos
      setUserPreferences({ visibleColumns: null, filters: [], sort: [{ field: 'id', direction: 'desc' }] });
      setColumnsToDisplay([]);
      setMagentoDynamicFilters([]);
      setQuickFilterValues({}); // Limpa filtros da tela anterior para evitar busca com parâmetros errados

      isInitialLoad.current = true; // Reseta a flag de carga inicial para garantir a aplicação dos filtros
      lastFetchedParamsRef.current = null; // Limpa o cache de busca para o novo modelo

      try {
        const metaRes = await api.get(`/metadata/${modelName}`);
        setMetadata({ ...metaRes.data, model_name: modelName }); // Vincula o metadata ao modelo atual
      } catch (err) {
        setError(`Não foi possível carregar os metadados para "${modelName}".`);
        toast.error(`Erro ao carregar metadados: ${err.message || 'Erro desconhecido'}`);
      } finally {
        setLoadingMetadata(false);
        // isFetchingData será controlado pelo useEffect de dados
      }
    };
    fetchMetadata();
  }, [modelName]);

  // --- IDENTIFICA COLUNAS DE DATA ---
  const dateColumns = useMemo(() => {
    if (!metadata?.fields) return [];
    return metadata.fields.filter(f => f.type === 'date' || f.type === 'datetime');
  }, [metadata]);

  // --- IDENTIFICA COLUNAS DE DROPDOWN (SELECT) ---
  const dropdownColumns = useMemo(() => {
    if (!metadata?.fields) return [];
    return metadata.fields.filter(f => f.type === 'select' && f.options && f.options.length > 0);
  }, [metadata]);

  const hasIdSeq = useMemo(() => {
    return metadata?.fields?.some(f => f.name === 'id_sequencial');
  }, [metadata]);

  // --- OBTER CONFIGURAÇÃO PADRÃO DE PREFERÊNCIAS ---
  const getDefaultPreferences = () => {
    const defaultSortField = metadata?.fields?.some(f => f.name === 'id_sequencial') ? 'id_sequencial' : 'id';
    if (!metadata?.fields || metadata.fields.length === 0) {
      return {
        visibleColumns: null,
        columnWidths: {},
        quickFilterFields: [],
        quickFilterValues: {},
        sort: [{ field: defaultSortField, direction: 'desc' }],
        filters: [],
        customColumnLabels: {},
        isExplicitlyCleared: false
      };
    }

    const allCols = metadata.fields
      .map(f => f.name)
      .filter(c => c !== 'id' && c !== 'itens' && c !== 'retiradas_detalhadas' && c !== 'retiradas_detalhadas_json');

    if (allCols.includes('id_sequencial')) {
      const idSeqIdx = allCols.indexOf('id_sequencial');
      if (idSeqIdx > -1) {
        allCols.splice(idSeqIdx, 1);
        allCols.unshift('id_sequencial');
      }
    }

    const defaultQuickFields = [];
    const defaultQuickValues = {};
    const now = Date.now();

    const searchKey = `__search__:${now}`;
    defaultQuickFields.push(searchKey);
    defaultQuickValues[searchKey] = { column: "", term: "" };

    if (dropdownColumns.length > 0) {
      const dropdownKey = `__dropdown__:${now + 1}`;
      defaultQuickFields.push(dropdownKey);
      defaultQuickValues[dropdownKey] = { column: dropdownColumns[0].name, value: "" };
    }

    if (dateColumns.length > 0) {
      const dateKey = `__date__:${now + 2}`;
      defaultQuickFields.push(dateKey);
      const preferred = dateColumns.find(c => ['data_orcamento', 'data_emissao', 'data', 'created_at', 'criado_em'].includes(c.name));
      defaultQuickValues[dateKey] = {
        column: preferred ? preferred.name : dateColumns[0].name,
        start: "",
        end: ""
      };
    }

    return {
      visibleColumns: allCols,
      columnWidths: {},
      quickFilterFields: defaultQuickFields,
      quickFilterValues: defaultQuickValues,
      sort: [{ field: defaultSortField, direction: 'desc' }],
      filters: [],
      customColumnLabels: {},
      isExplicitlyCleared: false
    };
  };

  const handleResetTablePreferences = async () => {
    const resetConfig = {
      ...getDefaultPreferences(),
      visibleColumns: [],
      columnWidths: {},
      isExplicitlyCleared: true
    };
    setUserPreferences(resetConfig);
    setQuickFilterValues(resetConfig.quickFilterValues || {});
    setColumnsToDisplay([]);
    try {
      await api.post(`/preferences/${modelName}`, resetConfig);
      toast.success("Todos os campos da tabela foram excluídos!");
    } catch (err) {
      toast.error("Erro ao resetar configurações da tabela.");
    }
  };

  // --- CARREGAR PREFERÊNCIAS DO USUÁRIO ---
  useEffect(() => {
    if (!modelName || !metadata) return; // Aguarda os metadados para evitar carregamento prematuro ou sem fallback

    const fetchPreferences = async () => {
      setLoadingPreferences(true);
      try {
        const res = await api.get(`/preferences/${modelName}`);
        if (res.data && res.data.config && Object.keys(res.data.config).length > 0) {
          const config = { ...res.data.config };
          if (hasIdSeq && config.sort) {
            config.sort = getSortArray(config.sort, true);
          }
          setUserPreferences(config);
          if (config.quickFilterValues) {
            setQuickFilterValues(config.quickFilterValues);
          }
        } else {
          const defaultConfig = getDefaultPreferences();
          setUserPreferences(defaultConfig);
          setQuickFilterValues(defaultConfig.quickFilterValues || {});
        }
      } catch (err) {
        // Silencioso ou toast se crítico
      } finally {
        setLoadingPreferences(false);
      }
    };
    fetchPreferences();
  }, [modelName, !!metadata]); // Depende apenas da existência do metadata para evitar re-execuções desnecessárias

  // --- SALVAMENTO AUTOMÁTICO DE FILTROS RÁPIDOS ---
  useEffect(() => {
    if (!metadata || loadingMetadata) return;

    const timeoutId = setTimeout(async () => {
      const currentValues = userPreferences.quickFilterValues || {};
      const currentFields = userPreferences.quickFilterFields || [];

      const hasChanged =
        JSON.stringify(currentValues) !== JSON.stringify(quickFilterValues) ||
        JSON.stringify(currentFields) !== JSON.stringify(userPreferences.quickFilterFields);

      if (hasChanged) {
        const configToSave = {
          ...userPreferences,
          quickFilterValues: quickFilterValues
        };

        try {
          await api.post(`/preferences/${modelName}`, configToSave);
        } catch (err) {
          console.error("Erro ao salvar filtros rápidos:", err);
        }
      }
    }, 1000); // Debounce de 1 segundo

    return () => clearTimeout(timeoutId);
  }, [userPreferences, modelName, metadata, loadingMetadata, quickFilterValues]);

  // --- RESET DA PAGINAÇÃO EM ATUALIZAÇÕES ---
  // Garante que a página volte para 1 sempre que filtros, status, ordenação ou dados forem atualizados
  useEffect(() => {
    if (!isInitialLoad.current) {
      setPage(1);
      setSelectedRowIds([]);
    }
  }, [
    modelName,
    statusFilter,
    debouncedQuickFilterValuesJson,
    filtersJson,
    sortsJson,
    refreshTrigger,
    limit,
    setSelectedGroupKey // Adicionado para permitir o reset
  ]);

  // Reset do grupo selecionado ao mudar de aba ou modelo
  useEffect(() => {
    setSelectedGroupKey(null);
  }, [modelName, statusFilter]);

  const isInitialLoad = React.useRef(true);
  const lastFetchedParamsRef = React.useRef(null);
  const tableContainerRef = React.useRef(null);
  const prevColumnsLength = React.useRef(0);
  const scrollAnimationFrameRef = useRef(null);
  const scrollVelocityRef = useRef(0);

  // Efeito para rolar a tabela para a direita ao adicionar uma nova coluna
  useEffect(() => {
    if (columnsToDisplay.length > prevColumnsLength.current && tableContainerRef.current && !isInitialLoad.current) {
      // Pequeno delay para garantir que o DOM renderizou a nova coluna antes de calcular o scrollWidth
      setTimeout(() => {
        if (tableContainerRef.current) {
          tableContainerRef.current.scrollTo({
            left: tableContainerRef.current.scrollWidth,
            behavior: 'smooth'
          });
        }
      }, 100);
    }
    prevColumnsLength.current = columnsToDisplay.length;
  }, [columnsToDisplay.length]);

  useEffect(() => {
    return () => {
      if (scrollAnimationFrameRef.current) cancelAnimationFrame(scrollAnimationFrameRef.current);
    };
  }, []);

  const startAutoScroll = () => {
    if (scrollAnimationFrameRef.current) return;

    const scroll = () => {
      if (scrollVelocityRef.current !== 0 && tableContainerRef.current) {
        tableContainerRef.current.scrollLeft += scrollVelocityRef.current;
        scrollAnimationFrameRef.current = requestAnimationFrame(scroll);
      } else {
        scrollAnimationFrameRef.current = null;
      }
    };
    scrollAnimationFrameRef.current = requestAnimationFrame(scroll);
  };

  const handleDragOverContainer = (e) => {
    if (!isEditMode || !draggedColName) return;
    e.preventDefault();
    const container = tableContainerRef.current;
    if (!container) return;

    const threshold = 100; // Distância da borda em pixels para iniciar o scroll
    const maxSpeed = 12;   // Velocidade máxima do scroll
    const rect = container.getBoundingClientRect();

    let velocity = 0;
    if (e.clientX < rect.left + threshold) {
      // Scroll para a esquerda
      const intensity = (rect.left + threshold - e.clientX) / threshold;
      velocity = -maxSpeed * Math.min(intensity, 1);
    } else if (e.clientX > rect.right - threshold) {
      // Scroll para a direita
      const intensity = (e.clientX - (rect.right - threshold)) / threshold;
      velocity = maxSpeed * Math.min(intensity, 1);
    }

    scrollVelocityRef.current = velocity;
    if (velocity !== 0) {
      startAutoScroll();
    }
  };

  const stopAutoScroll = () => {
    scrollVelocityRef.current = 0;
  };

  // --- HANDLERS PARA ARRASTE E PRÉ-VISUALIZAÇÃO DE COLUNAS ---
  const handleColumnDragStart = (e, colName) => {
    if (!isEditMode) return;
    setDraggedColName(colName);
    setDragTargetColName(colName);
    if (e.dataTransfer) {
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', colName);
    }
  };

  const handleColumnDragOver = (e, colName) => {
    if (!isEditMode || !draggedColName) return;
    e.preventDefault();
    if (e.dataTransfer) {
      e.dataTransfer.dropEffect = 'move';
    }
    // PROTEÇÃO ANTI-FLICKERING: Ignora dragOver se for a própria coluna que está sendo arrastada
    if (colName !== draggedColName && dragTargetColName !== colName) {
      setDragTargetColName(colName);
    }
  };

  const handleColumnDrop = (e, targetColName) => {
    if (!isEditMode || !draggedColName) return;
    e.preventDefault();
    e.stopPropagation();

    const fromCol = draggedColName;
    const toCol = (dragTargetColName && dragTargetColName !== draggedColName) ? dragTargetColName : targetColName;

    setDraggedColName(null);
    setDragTargetColName(null);
    stopAutoScroll();

    if (fromCol && toCol && fromCol !== toCol) {
      moveColumn(fromCol, toCol);
    }
  };

  const handleColumnDragEnd = () => {
    if (draggedColName && dragTargetColName && draggedColName !== dragTargetColName) {
      moveColumn(draggedColName, dragTargetColName);
    }
    setDraggedColName(null);
    setDragTargetColName(null);
    stopAutoScroll();
  };

  const handleResizeStart = (e, colName) => {
    if (!isEditMode) return;
    e.preventDefault();
    e.stopPropagation();

    const startX = e.clientX;
    const thElement = e.currentTarget.parentElement;
    const initialWidth = thElement ? thElement.offsetWidth : 150;
    const startWidth = userPreferences.columnWidths?.[colName] || initialWidth;

    let rafId = null;

    const onMouseMove = (moveEvent) => {
      moveEvent.preventDefault();
      const deltaX = moveEvent.clientX - startX;
      const newWidth = Math.max(20, Math.round(startWidth + deltaX));

      if (rafId) cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        setUserPreferences(prev => ({
          ...prev,
          columnWidths: {
            ...(prev.columnWidths || {}),
            [colName]: newWidth
          }
        }));
      });
    };

    const onMouseUp = () => {
      if (rafId) cancelAnimationFrame(rafId);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);

      setUserPreferences(latest => {
        handleSavePreferences(latest);
        return latest;
      });
    };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  };

  useEffect(() => {
    // Não busca dados se os metadados ainda não carregaram ou falharam
    // Também bloqueia se o metadata for de um modelo anterior (durante a transição de rota)
    if (!metadata || loadingPreferences || metadata.model_name !== modelName) return;

    // Evita o carregamento duplo e busca com dados obsoletos:
    // Se os valores dos filtros mudaram (por digitação ou carga de preferências), 
    // aguarda o debounce (500ms) para disparar a busca única com os valores processados.
    const isStale = debouncedQuickFilterValuesJson !== JSON.stringify(quickFilterValues);
    if (isStale) return;

    const fetchData = async () => {
      // Monta uma chave única para identificar se os parâmetros de busca mudaram de fato
      const paramsKey = JSON.stringify({
        modelName, page, effectiveLimit, statusFilter,
        filtersJson, sortsJson,
        refreshTrigger, isMeliView, isMagentoView,
        debouncedQuickFilterValuesJson
      });

      // Se os parâmetros são idênticos aos da última busca, ignora para evitar a "piscada" (double fetch)
      // Isso acontece principalmente quando o debouncedSearchTerm "alcança" o searchTerm inicial
      if (paramsKey === lastFetchedParamsRef.current) {
        return;
      }

      setIsFetchingData(true);
      setSelectedRowIds([]);

      try {
        const skip = (page - 1) * effectiveLimit;

        // CORREÇÃO 1: Declarar a variável url
        let url = '';

        const sortList = getSortArray(userPreferences.sort, hasIdSeq);
        const defaultSortField = hasIdSeq ? 'id_sequencial' : 'id';
        const params = {
          skip,
          limit: effectiveLimit,
          sort_by: sortList.length > 0 ? sortList.map(s => s.field).join(',') : defaultSortField,
          sort_order: sortList.length > 0 ? sortList.map(s => s.direction).join(',') : 'desc'
        };

        if (isMeliView) {
          // ROTA ESPECÍFICA PROXY DO ML
          url = `/mercadolivre/pedidos`;
        } else if (isMagentoView) {
          // ROTA ESPECÍFICA PROXY DO MAGENTO
          url = `/magento/pedidos`;
        } else if (isTiktokView) {
          // ROTA ESPECÍFICA PROXY DO TIKTOK
          url = `/tiktok/pedidos`;
        } else if (isShopeeView) {
          // ROTA ESPECÍFICA PROXY DA SHOPEE
          url = `/shopee/pedidos`;
        } else {
          // ROTA PADRÃO GENÉRICA
          url = `/generic/${modelName}`;
        }

        if (statusFilter && statusFilter !== 'Todos') {
          if (statusFilter === 'Nota Fiscal') {
            params.situacao = "Expedição,Despachado,Cancelado";
          } else {
            params.situacao = statusFilter;
          }
        }

        // Aplica filtros avançados (JSON)
        // Combina filtros salvos com filtros rápidos de data
        let activeFilters = userPreferences.filters ? [...userPreferences.filters] : [];

        // --- PROCESSA FILTROS RÁPIDOS (NOVA LÓGICA MULTI-FILTRO) ---
        let mainSearchTerm = "";
        (userPreferences.quickFilterFields || []).forEach(key => {
          const val = debouncedQuickFilterValues[key];
          if (val === undefined || val === null || val === "") return;

          const [type] = key.split(':');

          if (type === '__search__') {
            if (val.term) {
              if (!mainSearchTerm && !val.column) {
                mainSearchTerm = val.term;
              } else {
                activeFilters.push({ field: val.column || '', operator: 'contains', value: val.term });
              }
            }
          } else if (type === '__date__') {
            if (val.column) {
              if (val.start) activeFilters.push({ field: val.column, operator: 'gte', value: val.start });
              if (val.end) {
                let endVal = val.end;
                const fieldMeta = dateColumns.find(f => f.name === val.column);
                if (fieldMeta?.type === 'datetime' && endVal.length === 10) endVal += ' 23:59:59';
                activeFilters.push({ field: val.column, operator: 'lte', value: endVal });
              }
            }
          } else if (type === '__dropdown__') {
            if (val.column && val.value) {
              activeFilters.push({ field: val.column, operator: 'equals', value: val.value });
            }
          } else {
            // Campo pinado normal
            const field = fieldMetaMap.get(type);
            if (field) {
              const op = (field.type === 'text' || field.type === 'email') ? 'contains' : 'equals';
              activeFilters.push({ field: type, operator: op, value: val });
            }
          }
        });

        if (mainSearchTerm) {
          params.search_term = mainSearchTerm;
        }

        if (activeFilters.length > 0) {
          params.filters = JSON.stringify(activeFilters);
        }

        // CORREÇÃO 2: Usar a variável 'url' definida acima, e não o texto fixo
        const dataRes = await api.get(url, { params });

        // Ajuste para garantir que o Magento retorne 'id' para a tabela
        // Se a API retornar 'entity_id', mapeamos para 'id' para o componente GenericList funcionar
        const rawItems = (dataRes.data.items || []).map(item => ({
          ...item,
          id: item.id || item.entity_id || item.id // Garante ID
        }));

        // Desduplicação defensiva por ID para evitar re-renderização de itens repetidos no DOM
        const seenIds = new Set();
        const items = rawItems.filter(item => {
          if (!item.id) return true;
          if (seenIds.has(item.id)) return false;
          seenIds.add(item.id);
          return true;
        });

        // --- LÓGICA DINÂMICA DE CAMPOS ---
        // Se o metadata não trouxe campos (ex: Magento/ML), construímos a partir dos dados recebidos
        if (metadata.fields.length === 0 && items.length > 0) {
          const dynamicFields = Object.keys(items[0]).map(key => ({
            name: key,
            label: formatLabel(key),
            type: 'text' // Tipo padrão, renderização ajusta se for booleano/etc
          }));

          setMetadata(prev => ({ ...prev, fields: dynamicFields }));

          // Define colunas visíveis iniciais mais limpas por padrão para as integrações (ML, Magento, TikTok, etc.)
          let defaultCols = dynamicFields.map(f => f.name);
          if (isMagentoView) {
            const magentoMainCols = ['increment_id', 'created_at', 'status', 'grand_total', 'ja_importado', 'customer_firstname', 'customer_lastname', 'customer_email'];
            const foundMain = magentoMainCols.filter(c => defaultCols.includes(c));
            if (foundMain.length > 0) defaultCols = foundMain;
          } else if (isMeliView) {
            const meliMainCols = ['id', 'date_created', 'status', 'total_amount', 'ja_importado', 'buyer_nickname', 'buyer_name'];
            const foundMain = meliMainCols.filter(c => defaultCols.includes(c));
            if (foundMain.length > 0) defaultCols = foundMain;
          } else if (isTiktokView) {
            const tiktokMainCols = ['id', 'create_time', 'order_status', 'payment_amount', 'ja_importado', 'buyer_email'];
            const foundMain = tiktokMainCols.filter(c => defaultCols.includes(c));
            if (foundMain.length > 0) defaultCols = foundMain;
          } else if (isShopeeView) {
            const shopeeMainCols = ['order_sn', 'create_time', 'order_status', 'total_amount', 'ja_importado', 'buyer_user_name'];
            const foundMain = shopeeMainCols.filter(c => defaultCols.includes(c));
            if (foundMain.length > 0) defaultCols = foundMain;
          }

          setUserPreferences(prev => ({
            ...prev,
            visibleColumns: (Array.isArray(prev.visibleColumns) && prev.visibleColumns.length > 0 && prev.isExplicitlyCleared !== true)
              ? prev.visibleColumns
              : (prev.isExplicitlyCleared ? [] : defaultCols)
          }));
        }
        // ---------------------------------

        // Se for Magento, captura os filtros dinâmicos vindos no 'extra'
        if (isMagentoView && dataRes.data.extra?.available_filters) {
          setMagentoDynamicFilters(dataRes.data.extra.available_filters);
        }

        setData(items);
        setTotalCount(dataRes.data.total_count);
        setTotals(dataRes.data.totals || {});

        lastFetchedParamsRef.current = paramsKey;
        isInitialLoad.current = false;
      } catch (err) {
        console.error('[fetchData] Erro ao buscar dados:', err?.response?.data || err?.message || err);
        // Só define o erro se já não houver um erro de metadados
        if (!error) {
          if (err.response && err.response.status === 403 && isMeliView) {
            setError("Não conectado ao Mercado Livre. Clique em 'Sincronizar' para conectar.");
          } else if (err.response && err.response.status === 403 && isShopeeView) {
            setError(err.response?.data?.detail || "Shopee não autorizada. Conecte sua conta Shopee.");
          } else if (err.response && err.response.status === 403 && isTiktokView) {
            setError(err.response?.data?.detail || "TikTok Shop não autorizado. Conecte sua conta TikTok Shop.");
          } else if (isMagentoView) {
            const detail = err.response?.data?.detail || err?.message || 'Erro ao conectar com o Magento.';
            setError(detail);
            toast.error(`Magento: ${detail}`);
          } else {
            setError(err.response?.data?.detail || `Não foi possível carregar os dados.`);
            toast.error(err.response?.data?.detail || "Erro ao carregar dados.");
          }
        }
      } finally {
        setIsFetchingData(false);
      }
    };

    fetchData();
  }, [
    metadata,
    loadingPreferences,
    page,
    limit,
    statusFilter,
    isMeliView,
    modelName,
    refreshTrigger,
    filtersJson,
    sortsJson,
    debouncedQuickFilterValuesJson,
    effectiveLimit
  ]);

  const fieldMetaMap = useMemo(() => {
    if (!metadata) return new Map();

    const map = new Map();
    metadata.fields.forEach(field => {
      map.set(field.name, field);
    });
    return map;
  }, [metadata]); // Só roda quando os metadados mudam

  // Calcula as colunas a exibir baseado nas preferências
  useEffect(() => {
    // Aguarda o carregamento das preferências terminar para evitar calcular colunas temporárias
    if (!metadata || loadingPreferences) return;

    let cols = [];
    // Se tiver preferência salva válida de colunas, usa ela.
    // Se for um Array VAZIO ([]), só considera limpo se isExplicitlyCleared for true.
    if (Array.isArray(userPreferences.visibleColumns) && (userPreferences.visibleColumns.length > 0 || userPreferences.isExplicitlyCleared)) {
      cols = userPreferences.visibleColumns;
    } else {
      // Fallback padrão: todas as colunas do metadata, garantindo id_sequencial sempre em primeiro lugar
      cols = metadata.fields.map((field) => field.name);
      if (cols.includes('id_sequencial')) {
        const idSeqIdx = cols.indexOf('id_sequencial');
        if (idSeqIdx > -1) {
          cols.splice(idSeqIdx, 1);
          cols.unshift('id_sequencial');
        }
      }
    }

    // --- FILTRO DE PERMISSÕES DE COLUNA ---
    if (user?.perfil !== 'admin' && userPermissions.colunas && userPermissions.colunas.length > 0) {
      cols = cols.filter(col => userPermissions.colunas.includes(col));
    }

    // Filtra colunas complexas que quebram a tabela (JSONs grandes), ID primário e valores nulos
    const finalCols = cols.filter((col) =>
      col &&
      col !== 'id' &&
      col !== 'itens' &&
      col !== 'retiradas_detalhadas' &&
      col !== 'retiradas_detalhadas_json'
    );

    setColumnsToDisplay(finalCols);
  }, [metadata, userPreferences, isMagentoView, loadingPreferences]);

  const magentoFilterOptions = useMemo(() => {
    if (!isMagentoView) return [];

    // Prioriza filtros dinâmicos carregados da requisição
    if (magentoDynamicFilters.length > 0) return magentoDynamicFilters;

    if (metadata) {
      const filterField = metadata.fields.find(f => f.name === 'available_filters');
      return filterField ? filterField.options : [];
    }
    return [];
  }, [isMagentoView, metadata, magentoDynamicFilters]);

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
      if (modelName === 'pedidos') {
        await api.put(`/generic/${modelName}/${selectedRowId}`, { situacao: 'Cancelado' });

        if (statusFilter) {
          setData(data.filter((item) => item.id !== selectedRowId));
          setTotalCount(prev => prev - 1);
        } else {
          setData(data.map((item) => item.id === selectedRowId ? { ...item, situacao: 'Cancelado' } : item));
        }
        toast.success('Pedido cancelado com sucesso.');
      } else {
        await api.delete(`/generic/${modelName}/${selectedRowId}`);
        setData(data.filter((item) => item.id !== selectedRowId));
        setTotalCount(prev => prev - 1);
      }
      // Reseta a seleção após a exclusão
      setSelectedRowIds([]);
    } catch (err) {
      toast.error(modelName === 'pedidos' ? 'Não foi possível cancelar o pedido.' : 'Não foi possível excluir o item.');
    } finally {
      setIsModalOpen(false); // Fecha o modal
    }
  };

  const handleEditClick = () => {
    if (selectedRowId) {
      const targetId = selectedItem?.id_sequencial ?? selectedRowId;
      // Adiciona o "/edit/" no caminho para bater com a rota do App.jsx
      navigate(`/${modelName}/edit/${targetId}`);
    }
  };

  /** * 1. Abre o modal genérico populando o estado 'actionToConfirm' * @param {object} actionDetails - O objeto de ação vindo da config 'statusChangeActions' */
  const handleStatusChangeClick = (actionDetails) => {
    if (selectedRowIds.length === 0) return;
    setActionToConfirm(actionDetails);
  };

  /** * 2. Fecha o modal genérico limpando o estado. */
  const handleCloseStatusModal = () => {
    setActionToConfirm(null);
  };

  /** * 3. Confirma a ação, envia o PUT (único ou em lote) e atualiza a UI. * Usa os dados do estado 'actionToConfirm'. */
  const handleConfirmStatusChange = async () => {
    if (selectedRowIds.length === 0 || !actionToConfirm) return;

    // Pega os detalhes da ação que está no estado
    const { newStatus, errorLog, errorAlert } = actionToConfirm;

    try {
      // Faz a chamada PUT, alterando APENAS a situação
      const payload = { situacao: newStatus };
      if (newStatus === 'Despachado') {
        payload.data_despacho = new Date().toISOString().split('T')[0]; // Current date in YYYY-MM-DD format
      }

      if (selectedRowIds.length > 1) {
        // Atualização em Lote
        await api.put(`/generic/${modelName}/batch-update`, {
          ids: selectedRowIds,
          item_data: payload
        });

        if (statusFilter) {
          setData(prev => prev.filter((item) => !selectedRowIds.includes(item.id)));
          setTotalCount(prevCount => Math.max(0, prevCount - selectedRowIds.length));
        } else {
          setData(prev => prev.map((item) =>
            selectedRowIds.includes(item.id)
              ? { ...item, situacao: newStatus, ...(newStatus === 'Despachado' ? { data_despacho: payload.data_despacho } : {}) }
              : item
          ));
        }

        const count = selectedRowIds.length;
        setSelectedRowIds([]);
        toast.success(newStatus === 'Despachado'
          ? `${count} pedidos despachados com sucesso!`
          : `${count} itens atualizados com sucesso!`
        );
      } else {
        const idToUpdate = selectedRowId;
        await api.put(`/generic/${modelName}/${idToUpdate}`, payload);

        if (statusFilter) {
          setData(prev => prev.filter((item) => item.id !== idToUpdate));
          setTotalCount(prevCount => Math.max(0, prevCount - 1));
        } else {
          setData(prev => prev.map((item) =>
            item.id === idToUpdate
              ? { ...item, situacao: newStatus, ...(newStatus === 'Despachado' ? { data_despacho: payload.data_despacho } : {}) }
              : item
          ));
        }

        setSelectedRowIds([]);
        toast.success(newStatus === 'Despachado'
          ? `Pedido despachado com sucesso.`
          : `Item alterado para ${newStatus} com sucesso.`
        );
      }

    } catch (err) {
      console.error(errorLog || "Erro ao alterar status:", err);
      toast.error(err.response?.data?.detail || errorAlert || "Não foi possível alterar o status.");
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
      toast.error("Não foi possível carregar os detalhes do pedido.");
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

  const handleOpenIntelipost = async (itemRow) => {
    // É boa prática buscar o item completo atualizado antes de abrir, 
    // mas se itemRow já tiver tudo (cliente, itens), pode usar direto.
    // Aqui vou assumir que precisamos buscar os detalhes completos (incluindo itens JSON)
    try {
      setIsFetchingData(true);
      const res = await api.get(`/generic/pedidos/${itemRow.id}`);
      setPedidoParaCotar(res.data);
      setIsIntelipostModalOpen(true);
    } catch (err) {
      toast.error("Erro ao carregar dados do pedido.");
    } finally {
      setIsFetchingData(false);
    }
  };

  const handleFreteSelecionado = async (dadosFrete) => {
    if (!pedidoParaCotar) return;

    try {
      // Atualiza o pedido com os dados do frete (PATCH ou PUT)
      await api.put(`/generic/pedidos/${pedidoParaCotar.id}`, {
        valor_frete: Number(dadosFrete.valor_frete || 0).toFixed(2),
        id_transportadora: dadosFrete.transportadora_id,
        modalidade_frete: dadosFrete.modalidade_frete,

        // --- ADICIONE ESTES CAMPOS ---
        // Salva o ID do método de entrega (ex: 15707)
        delivery_method_id: dadosFrete.delivery_method_id ? String(dadosFrete.delivery_method_id) : null,

        // Salva o ID da cotação para validar o preço depois (ESSENCIAL)
        quote_id: dadosFrete.quote_id ? String(dadosFrete.quote_id) : null,

        // Salva a previsão de entrega para enviar no shipment_order depois
        // Calcula a data de entrega com base no prazo em dias
        data_entrega: (() => {
          const prazoDias = dadosFrete.prazo_entrega; // This comes from selectedOption.delivery_time
          if (prazoDias !== undefined && prazoDias !== null) {
            const today = new Date();
            today.setDate(today.getDate() + parseInt(prazoDias, 10));
            return today.toISOString().split('T')[0]; // Format as YYYY-MM-DD
          }
          return null;
        })(),
      });

      // Atualiza a lista localmente para refletir mudança (opcional)
      setData(prevData => prevData.map(p =>
        p.id === pedidoParaCotar.id
          ? { ...p, valor_frete: dadosFrete.valor_frete }
          : p
      ));

      toast.success("Frete vinculado ao pedido com sucesso!");
      setIsIntelipostModalOpen(false); // Fecha o modal após salvar

    } catch (err) {
      toast.error("Erro ao salvar dados do frete.");
    }
  };

  const handleMagentoConfigClick = async () => {
    try {
      setIsFetchingData(true);
      const response = await api.get('/generic/magento_configuracoes');
      const items = response.data.items;
      if (items && items.length > 0) {
        navigate(`/magento_configuracoes/edit/${items[0].id_sequencial ?? items[0].id}`);
      } else {
        navigate(`/magento_configuracoes/new`);
      }
    } catch (err) {
      navigate(`/magento_configuracoes/new`);
    } finally {
      setIsFetchingData(false);
    }
  };

  const handleMagentoSyncClick = async () => {
    try {
      setIsFetchingData(true);
      setRefreshTrigger(prev => prev + 1);
      toast.success("Pedidos sincronizados com a Magento!");
    } catch (err) {
      toast.error("Erro ao sincronizar com Magento.");
    } finally {
      setIsFetchingData(false);
    }
  };

  const handleOpenMagentoFilters = async () => {
    setIsFetchingData(true);
    try {
      const response = await api.get('/generic/magento_configuracoes');
      if (response.data.items && response.data.items.length > 0) {
        setMagentoConfig(response.data.items[0]);
        setIsFilterModalOpen(true);
      } else {
        toast.warn("Configure o Magento primeiro em Integrações.");
      }
    } catch (err) {
    } finally {
      setIsFetchingData(false);
    }
  };

  const handleSaveMagentoFilters = async () => {
    setIsFetchingData(true);
    try {
      await api.put(`/generic/magento_configuracoes/${magentoConfig.id}`, {
        filtros_padrao: magentoConfig.filtros_padrao
      });
      setIsFilterModalOpen(false);
      setRefreshTrigger(prev => prev + 1);
    } catch (err) {
      toast.error("Erro ao salvar filtros.");
    } finally {
      setIsFetchingData(false);
    }
  };

  const handleImportMagentoOrder = () => {
    const toImport = selectedRowIds.filter(id => !data.find(d => d.id === id)?.ja_importado);
    if (toImport.length === 0) {
      toast.info("Os pedidos selecionados já foram importados.");
      return;
    }
    setOrdersToImport(toImport);
    setIsImportModalOpen(true);
  };

  const handleImportMeliOrder = () => {
    const toImport = selectedRowIds.filter(id => !data.find(d => d.id === id)?.ja_importado);
    if (toImport.length === 0) {
      toast.info("Os pedidos selecionados já foram importados.");
      return;
    }
    setOrdersToImport(toImport);
    setIsImportModalOpen(true);
  };

  const handleImportTiktokOrder = () => {
    const toImport = selectedRowIds.filter(id => !data.find(d => d.id === id)?.ja_importado);
    if (toImport.length === 0) {
      toast.info("Os pedidos selecionados já foram importados.");
      return;
    }
    setOrdersToImport(toImport);
    setIsImportModalOpen(true);
  };

  const handleImportShopeeOrder = () => {
    const toImport = selectedRowIds.filter(id => !data.find(d => d.id === id)?.ja_importado);
    if (toImport.length === 0) {
      toast.info("Os pedidos selecionados já foram importados.");
      return;
    }
    setOrdersToImport(toImport);
    setIsImportModalOpen(true);
  };

  const confirmImportOrder = async () => {
    if (ordersToImport.length === 0) return;

    setIsImportModalOpen(false);
    setIsFetchingData(true);

    let successCount = 0;
    let errorCount = 0;

    try {
      for (const orderId of ordersToImport) {
        try {
          const endpoint = isMeliView
            ? `/mercadolivre/pedidos/${orderId}/importar`
            : isTiktokView
              ? `/tiktok/pedidos/${orderId}/importar`
              : isShopeeView
                ? `/shopee/pedidos/${orderId}/importar`
                : `/magento/pedidos/${orderId}/importar`;

          await api.post(endpoint);
          successCount++;

          // Atualiza o estado local para refletir a importação
          setData(prev => prev.map(item =>
            item.id === orderId ? { ...item, ja_importado: true } : item
          ));
        } catch (err) {
          errorCount++;
          console.error(`Erro ao importar pedido ${orderId}:`, err.response?.data?.detail || err.message);
        }
      }

      if (successCount > 0) toast.success(`${successCount} pedido(s) importado(s) com sucesso!`);
      if (errorCount > 0) toast.error(`${errorCount} pedido(s) falharam na importação. Verifique o console.`);

    } finally {
      setIsFetchingData(false);
      setOrdersToImport([]);
      setSelectedRowIds([]);
    }
  };

  const handleDfeSync = async () => {
    setIsFetchingData(true);
    try {
      const res = await api.post('/dfe/sync');
      setRefreshTrigger(prev => prev + 1);
      if (res.data && res.data.message) {
        toast.info(res.data.message);
      } else {
        toast.success(`Busca na SEFAZ concluída! ${res.data?.novas_notas > 0 ? res.data.novas_notas + ' novas notas baixadas.' : 'Nenhuma nota nova no momento.'}`);
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || "Erro ao sincronizar com SEFAZ.");
    } finally {
      setIsFetchingData(false);
    }
  };

  const handleXmlUpload = async (e) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
      formData.append('files', files[i]);
    }

    const toastId = toast.loading("Enviando e processando XMLs...");

    try {
      const response = await api.post('/dfe/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      if (response.data.success) {
        toast.update(toastId, {
          render: response.data.message,
          type: "success",
          isLoading: false,
          autoClose: 3000
        });
        setRefreshTrigger(prev => prev + 1);
      } else {
        toast.update(toastId, {
          render: "Erro ao importar alguns arquivos.",
          type: "error",
          isLoading: false,
          autoClose: 5000
        });
      }

      if (response.data.errors && response.data.errors.length > 0) {
        response.data.errors.forEach(err => toast.error(err));
      }

    } catch (err) {
      console.error("Erro no upload de XML:", err);
      toast.update(toastId, {
        render: "Erro ao enviar arquivos para o servidor.",
        type: "error",
        isLoading: false,
        autoClose: 5000
      });
    } finally {
      e.target.value = '';
    }
  };

  const handleManifestarCiencia = async () => {
    try {
      await api.post(`/dfe/manifest/${selectedRowId}`);
      toast.success("Ciência enviada! O XML será baixado na próxima sincronização.");
      setRefreshTrigger(prev => prev + 1);
    } catch (err) { toast.error("Erro ao enviar manifestação."); }
  };

  const handleEmailConfigClick = async () => {
    try {
      setIsFetchingData(true);
      const response = await api.get('/generic/elastic_email_configuracoes');
      const items = response.data.items;
      if (items && items.length > 0) {
        navigate(`/elastic_email_configuracoes/edit/${items[0].id_sequencial ?? items[0].id}`);
      } else {
        navigate(`/elastic_email_configuracoes/new`);
      }
    } catch (err) {
      navigate(`/elastic_email_configuracoes/new`);
    } finally {
      setIsFetchingData(false);
    }
  };

  const handleMeliConfigClick = async () => {
    try {
      // Verifica se já existe config
      const response = await api.get('/generic/meli_configuracoes');
      const items = response.data.items;
      if (items && items.length > 0) {
        navigate(`/meli_configuracoes/edit/${items[0].id_sequencial ?? items[0].id}`);
      } else {
        navigate(`/meli_configuracoes/new`);
      }
    } catch (err) {
      navigate(`/meli_configuracoes/new`);
    }
  };

  const handleMeliSyncClick = async () => {
    try {
      setIsFetchingData(true);
      await api.post('/mercadolivre/sync');
      setRefreshTrigger(prev => prev + 1); // Recarrega a lista após sincronizar
      toast.success("Conexão sincronizada com sucesso!");
    } catch (err) {
      // Se receber 403, significa que precisa autenticar (token inválido ou inexistente)
      if (err.response && err.response.status === 403) {
        try {
          const res = await api.get('/mercadolivre/auth_url');
          const { url, verifier } = res.data;
          setPendingAuthUrl(url);
          if (verifier) localStorage.setItem('meli_verifier', verifier);
          setIsMeliAuthModalOpen(true);
        } catch (authErr) {
          toast.error("Erro ao iniciar autenticação.");
        }
      } else {
        toast.error("Erro ao sincronizar conexão com Mercado Livre.");
      }
      setIsFetchingData(false);
    }
  };

  const handleTiktokConfigClick = async () => {
    try {
      setIsFetchingData(true);
      const response = await api.get('/generic/tiktok_configuracoes');
      const items = response.data.items;
      if (items && items.length > 0) {
        navigate(`/tiktok_configuracoes/edit/${items[0].id_sequencial ?? items[0].id}`);
      } else {
        navigate(`/tiktok_configuracoes/new`);
      }
    } catch (err) {
      navigate(`/tiktok_configuracoes/new`);
    } finally {
      setIsFetchingData(false);
    }
  };

  const handleTiktokSyncClick = async () => {
    try {
      setIsFetchingData(true);
      await api.post('/tiktok/sync');
      setRefreshTrigger(prev => prev + 1);
      toast.success("Conexão sincronizada com sucesso!");
    } catch (err) {
      if (err.response && err.response.status === 403) {
        try {
          const res = await api.get('/tiktok/auth_url');
          setPendingAuthUrl(res.data.url);
          setIsTiktokAuthModalOpen(true);
        } catch (authErr) {
          toast.error("Erro ao iniciar autenticação.");
        }
      } else {
        toast.error("Erro ao sincronizar conexão com Tiktok Shop.");
      }
      setIsFetchingData(false);
    }
  };

  const handleShopeeConfigClick = async () => {
    try {
      setIsFetchingData(true);
      const response = await api.get('/generic/shopee_configuracoes');
      const items = response.data.items;
      if (items && items.length > 0) {
        navigate(`/shopee_configuracoes/edit/${items[0].id_sequencial ?? items[0].id}`);
      } else {
        navigate(`/shopee_configuracoes/new`);
      }
    } catch (err) {
      navigate(`/shopee_configuracoes/new`);
    } finally {
      setIsFetchingData(false);
    }
  };

  const handleShopeeSyncClick = async () => {
    try {
      setIsFetchingData(true);
      await api.post('/shopee/sync');
      setRefreshTrigger(prev => prev + 1);
      toast.success("Conexão com a Shopee sincronizada com sucesso!");
    } catch (err) {
      if (err.response && err.response.status === 403) {
        try {
          const redirectUri = window.location.origin + '/shopee/callback';
          const res = await api.get('/shopee/auth_url', { params: { redirect_uri: redirectUri } });
          if (res.data && res.data.url) {
            window.location.href = res.data.url;
          } else {
            toast.error("URL de autorização da Shopee indisponível. Verifique as credenciais.");
          }
        } catch (authErr) {
          toast.error("Configure Partner ID e Partner Key primeiro em Integrações.");
        }
      } else {
        toast.error("Erro ao sincronizar conexão com a Shopee.");
      }
    } finally {
      setIsFetchingData(false);
    }
  };

  // --- HANDLER DOWNLOAD DANFE (COMPLETA / SIMPLIFICADA) ---
  const handleConfirmDownloadDanfe = async (tipo) => {
    setIsDanfeModalOpen(false);
    if (!danfeModalIds || danfeModalIds.length === 0) return;
    try {
      setIsFetchingData(true);
      let response;
      if (danfeModalIds.length > 1) {
        response = await api.post(`/nfe/danfe-lote`, { pedido_ids: danfeModalIds, tipo }, {
          responseType: 'blob'
        });
      } else {
        response = await api.get(`/nfe/danfe/${danfeModalIds[0]}?tipo=${tipo}`, {
          responseType: 'blob'
        });
      }
      const url = window.URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }));
      window.open(url, '_blank');
      toast.success("DANFE gerada com sucesso!");
    } catch (err) {
      const msg = err.response?.data?.detail || "Erro ao gerar DANFE.";
      toast.error(msg);
    } finally {
      setIsFetchingData(false);
      setDanfeModalIds([]);
    }
  };

  // --- HANDLERS CANCELAMENTO NFE ---
  const handleOpenCancelNFeModal = () => {
    if (!selectedRowId) return;
    setCancelJustification('');
    setIsCancelNFeModalOpen(true);
  };

  const handleConfirmCancelNFe = async () => {
    if (cancelJustification.length < 15) {
      toast.warning("A justificativa deve ter pelo menos 15 caracteres.");
      return;
    }
    try {
      await api.post(`/nfe/cancelar/${selectedRowId}`, { justificativa: cancelJustification });
      toast.success("NFe Cancelada com sucesso!");
      // Remove da lista pois o status mudou para Cancelado
      setData(data.filter(i => i.id !== selectedRowId));
      setTotalCount(prev => prev - 1);
      setSelectedRowIds([]);
      setIsCancelNFeModalOpen(false);
    } catch (err) {
      const msg = err.response?.data?.detail || "Erro ao cancelar NFe.";
      toast.error(msg);
    }
  };

  // --- HANDLERS CARTA DE CORREÇÃO ---
  const handleOpenCCeModal = () => {
    if (!selectedRowId) return;
    setCceText('');
    setIsCCeModalOpen(true);
  };

  const handleConfirmCCe = async () => {
    if (cceText.length < 15) {
      toast.warning("O texto da correção deve ter pelo menos 15 caracteres.");
      return;
    }
    try {
      const res = await api.post(`/nfe/corrigir/${selectedRowId}`, { correcao: cceText });
      toast.success(res.data.message || "Carta de Correção registrada com sucesso!");

      // --- LÓGICA PARA ABRIR O PDF DA CARTA DE CORREÇÃO ---
      if (res.data.pdf) {
        try {
          const binaryString = window.atob(res.data.pdf);
          const len = binaryString.length;
          const bytes = new Uint8Array(len);
          for (let i = 0; i < len; i++) {
            bytes[i] = binaryString.charCodeAt(i);
          }
          const blob = new Blob([bytes], { type: 'application/pdf' });
          const url = window.URL.createObjectURL(blob);
          window.open(url, '_blank'); // Abre em nova aba
        } catch (e) {
          console.error("Erro ao abrir PDF da CC-e:", e);
          toast.error("A correção foi registrada, mas houve um erro ao exibir o PDF.");
        }
      }

      setIsCCeModalOpen(false);
    } catch (err) {
      const msg = err.response?.data?.detail || "Erro ao registrar Carta de Correção.";
      toast.error(msg);
    }
  };

  const handleOpenDevolucaoModal = () => {
    if (!selectedRowId) return;
    setIsDevolucaoModalOpen(true);
  };

  const handleConfirmDevolucao = async () => {
    if (!selectedRowId) return;
    try {
      const res = await api.post(`/nfe/devolucao/${selectedRowId}`);
      toast.success("Devolução gerada com sucesso! Verifique o novo pedido na lista.");
      setRefreshTrigger(prev => prev + 1);
      setSelectedRowIds([]);
    } catch (err) {
      const msg = err.response?.data?.detail || "Erro ao gerar devolução.";
      toast.error(msg);
    } finally {
      setIsDevolucaoModalOpen(false);
    }
  };

  const handleOpenComplementoModal = () => {
    if (!selectedRowId) return;
    setIsComplementoModalOpen(true);
  };

  const handleConfirmComplemento = async () => {
    if (!selectedRowId) return;
    setIsFetchingData(true);
    try {
      const res = await api.post(`/nfe/complemento/${selectedRowId}`);
      toast.success(res.data.message || "Pedido de complemento gerado com sucesso! Verifique o novo pedido na lista.");
      setIsComplementoModalOpen(false);
      setRefreshTrigger(prev => prev + 1);
      setSelectedRowIds([]);
    } catch (err) {
      const msg = err.response?.data?.detail || "Erro ao gerar pedido de complemento.";
      toast.error(msg);
    } finally {
      setIsFetchingData(false);
    }
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

      // Navega para a aba da nova situação (Produção)
      navigate(`/pedidos/${payload.situacao}`);

      // Sucesso! Remove o item da lista atual
      setData(data.filter((item) => item.id !== selectedRowId));
      setTotalCount(prevCount => prevCount - 1);
      setSelectedRowIds([]);

      // Fecha o modal
      handleCloseProgramacaoModal();

    } catch (err) {
      toast.error("Não foi possível salvar a programação. Verifique os dados e tente novamente.");
      // NOTA: Não fechamos o modal, para o usuário corrigir
    }
  };

  const handleSaveFaturamento = async (payload) => {
    try {
      // Chama o endpoint específico de emissão de NFe
      // O payload agora contém { id_regra_tributaria, itens, total_nota, ... }
      const res = await api.post(`/nfe/emitir/${selectedRowId}`, payload);
      const data = res.data;

      // 1. Toast para NFe (Sucesso)
      if (data.nfe && data.nfe.success) {
        toast.success(data.nfe.message);
      }

      // 2. Toast para Mercado Livre
      if (data.meli) {
        if (data.meli.success) toast.success(data.meli.message);
        else toast.warning(data.meli.message);
      }

      // 3. Toast para Intelipost
      if (data.intelipost) {
        if (data.intelipost.success) {
          if (data.intelipost.warning) toast.warning(data.intelipost.message);
          else toast.success(data.intelipost.message);
        } else {
          toast.warning(data.intelipost.message);
        }
      }

      // 4. Toast para E-mail
      if (data.email) {
        if (data.email.success) toast.success(data.email.message);
        else toast.warning(data.email.message);
      }

      // Abre a DANFE automaticamente se retornada
      if (data.pdf) {
        try {
          const binaryString = window.atob(data.pdf);
          const len = binaryString.length;
          const bytes = new Uint8Array(len);
          for (let i = 0; i < len; i++) {
            bytes[i] = binaryString.charCodeAt(i);
          }
          const blob = new Blob([bytes], { type: 'application/pdf' });
          const url = window.URL.createObjectURL(blob);
          window.open(url, '_blank');
        } catch (e) {
          console.error("Erro ao abrir PDF automático:", e);
        }
      }

      // Navega para a aba de Nota Fiscal apenas se a situação foi alterada
      if (data.situation_changed) {
        navigate(`/pedidos/Nota Fiscal`);
        // Atualiza a lista local
        setData(prev => prev.filter((item) => item.id !== selectedRowId));
        setTotalCount(prev => prev - 1);
      }

      setSelectedRowIds([]);
      // setIsFaturamentoModalOpen(false); // Deixa o Modal fechar a si mesmo via onClose()
    } catch (err) {
      const msg = err.response?.data?.detail || "Erro ao processar faturamento.";
      throw new Error(msg); // Lança o erro para o Modal exibir e não fechar
    }
  }

  const handleConfirmBatchFaturamento = async () => {
    setIsFetchingData(true);
    setIsBatchFaturamentoModalOpen(false);
    try {
      const res = await api.post(`/pedidos/emitir-lote`, { pedido_ids: selectedRowIds });
      const resultados = res.data;

      const sucessos = resultados.filter(r => r.success);
      const falhas = resultados.filter(r => !r.success);

      if (sucessos.length > 0) {
        toast.success(`${sucessos.length} notas autorizadas com sucesso!`);
        const idsSucesso = sucessos.map(r => r.id);
        // Remove da lista os que deram certo
        setData(prev => prev.filter(item => !idsSucesso.includes(item.id)));
        setTotalCount(prev => prev - idsSucesso.length);
      }

      if (falhas.length > 0) {
        toast.error(`${falhas.length} pedidos falharam no faturamento. Verifique o console para detalhes.`);
        console.error("Falhas no faturamento em lote:", falhas);
      }

      setSelectedRowIds([]);
      // Força recarregamento se necessário
      if (sucessos.length > 0) setRefreshTrigger(prev => prev + 1);

    } catch (err) {
      toast.error("Erro ao processar faturamento em lote.");
    } finally {
      setIsFetchingData(false);
    }
  };

  /**
   * Handler para abrir o modal de conferência (Produção/Embalagem)
   */
  const handleOpenConferenciaModal = async (actionDetails) => {
    if (!selectedRowId) return;

    setIsFetchingDetails(true);
    setConferenciaConfig(actionDetails); // Salva a config (título, novo status, etc)

    try {
      const res = await api.get(`/generic/pedidos/${selectedRowId}`);
      const rawPedido = res.data;
      const pedidoAdaptado = {
        ...rawPedido,
        cliente_nome: rawPedido.cliente?.nome_razao || 'Não informado',
      };
      setCurrentPedidoDetails(pedidoAdaptado);
      setIsConferenciaModalOpen(true);
    } catch (err) {
      toast.error("Não foi possível carregar os detalhes do pedido.");
    } finally {
      setIsFetchingDetails(false);
    }
  };

  const handleCloseConferenciaModal = () => {
    setIsConferenciaModalOpen(false);
    setConferenciaConfig(null);
    setCurrentPedidoDetails(null);
  };

  const handleConfirmConferencia = async (modalData = {}) => {
    if (!selectedRowId || !conferenciaConfig) return;

    try {
      await api.put(`/generic/pedidos/${selectedRowId}`, {
        situacao: conferenciaConfig.newStatus,
        ...modalData
      });

      // Se estiver finalizando a embalagem, abre a etiqueta de volume automaticamente
      if (conferenciaConfig.currentStatus === 'Embalagem' && conferenciaConfig.newStatus === 'Faturamento') {
        try {
          const params = {};
          if (modalData.volumes_quantidade) {
            params.volumes = modalData.volumes_quantidade;
          }
          const response = await api.get(`/pedidos/etiqueta_volume/${selectedRowId}`, {
            params,
            responseType: 'blob'
          });
          const url = window.URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }));
          window.open(url, '_blank');
        } catch (err) {
          toast.warning("Pedido atualizado, mas erro ao gerar etiqueta.");
        }
      }

      // Navega para a aba da nova situação (Trata 'Expedição' como 'Nota Fiscal')
      const targetTab = (conferenciaConfig.newStatus === 'Expedição')
        ? 'Nota Fiscal'
        : conferenciaConfig.newStatus;
      navigate(`/pedidos/${targetTab}`);

      setData(data.filter((item) => item.id !== selectedRowId));
      setTotalCount(prev => prev - 1);
      setSelectedRowIds([]);
      handleCloseConferenciaModal();
    } catch (err) {
      toast.error("Erro ao atualizar o status do pedido.");
    }
  };

  /**
   * Handler para abrir o modal de visualização do pedido.
   */
  const handleOpenVisualizarModal = async () => {
    if (!selectedRowId) return;

    setIsFetchingDetails(true);
    try {
      const res = await api.get(`/generic/pedidos/${selectedRowId}`);
      const rawPedido = res.data;

      // O modal de visualização espera um formato um pouco diferente do que a API retorna.
      // Criamos um objeto adaptado para ele.
      const pedidoAdaptado = {
        ...rawPedido,
        cliente_nome: rawPedido.cliente?.nome_razao || 'Não informado',
        vendedor_nome: rawPedido.vendedor?.nome_razao || 'Não informado',
        transportadora_nome: rawPedido.transportadora?.nome_razao || '',
        // O modal espera 'itens' e 'pagamento' no formato que vem do backend,
        // então não precisamos converter para string aqui.
      };

      setPedidoParaVisualizar(pedidoAdaptado);
      setIsVisualizarModalOpen(true);
    } catch (err) {
      toast.error("Não foi possível carregar os detalhes do pedido.");
    } finally {
      setIsFetchingDetails(false);
    }
  };

  const handleCloseVisualizarModal = () => {
    setIsVisualizarModalOpen(false);
    setPedidoParaVisualizar(null);
  };

  const handleExportCSV = async () => {
    setExportingFormat('generic');
    try {
      const params = {};

      // Adiciona filtro de situação (abas)
      if (statusFilter && statusFilter !== 'Todos') {
        if (statusFilter === 'Nota Fiscal') {
          params.situacao = "Expedição,Despachado,Finalizado,Cancelado";
        } else {
          params.situacao = statusFilter;
        }
      }

      // Aplica filtros avançados (JSON) - IGUAL AO FETCHDATA
      let activeFilters = userPreferences.filters ? [...userPreferences.filters] : [];

      // --- PROCESSA FILTROS RÁPIDOS (NOVA LÓGICA MULTI-FILTRO) ---
      let mainSearchTerm = "";
      (userPreferences.quickFilterFields || []).forEach(key => {
        const val = debouncedQuickFilterValues[key];
        if (val === undefined || val === null || val === "") return;

        const [type] = key.split(':');

        if (type === '__search__') {
          if (val.term) {
            if (!mainSearchTerm && !val.column) {
              mainSearchTerm = val.term;
            } else {
              activeFilters.push({ field: val.column || '', operator: 'contains', value: val.term });
            }
          }
        } else if (type === '__date__') {
          if (val.column) {
            if (val.start) activeFilters.push({ field: val.column, operator: 'gte', value: val.start });
            if (val.end) {
              let endVal = val.end;
              const fieldMeta = dateColumns.find(f => f.name === val.column);
              if (fieldMeta?.type === 'datetime' && endVal.length === 10) endVal += ' 23:59:59';
              activeFilters.push({ field: val.column, operator: 'lte', value: endVal });
            }
          }
        } else if (type === '__dropdown__') {
          if (val.column && val.value) {
            activeFilters.push({ field: val.column, operator: 'equals', value: val.value });
          }
        } else {
          // Campo pinado normal
          const field = fieldMetaMap.get(type);
          if (field) {
            const op = (field.type === 'text' || field.type === 'email') ? 'contains' : 'equals';
            activeFilters.push({ field: type, operator: op, value: val });
          }
        }
      });

      if (mainSearchTerm) {
        params.search_term = mainSearchTerm;
      }

      if (activeFilters.length > 0) {
        params.filters = JSON.stringify(activeFilters);
      }

      // Adiciona ordenação
      const sortList = getSortArray(userPreferences.sort, hasIdSeq);
      const defaultSortField = hasIdSeq ? 'id_sequencial' : 'id';
      params.sort_by = sortList.length > 0 ? sortList.map(s => s.field).join(',') : defaultSortField;
      params.sort_order = sortList.length > 0 ? sortList.map(s => s.direction).join(',') : 'desc';

      // Adiciona colunas visíveis (Respeitando a configuração da tabela)
      if (columnsToDisplay && columnsToDisplay.length > 0) {
        params.visible_columns = columnsToDisplay.join(',');
      }

      // Chama o novo endpoint de exportação
      const response = await api.get(`/generic/${modelName}/export`, {
        params,
        responseType: 'blob', // Importante: informa ao axios para tratar a resposta como um arquivo (blob)
      });

      // Extrai o nome do arquivo do header ou gera um padrão
      let filename = `${modelName}_${new Date().toISOString().slice(0, 10)}.csv`;
      const disposition = response.headers['content-disposition'];
      if (disposition && disposition.includes('filename=')) {
        const match = disposition.match(/filename="?([^";]+)"?/);
        if (match && match[1]) {
          filename = match[1];
        }
      }

      // Cria uma URL temporária para o arquivo (blob)
      const url = window.URL.createObjectURL(new Blob([response.data], { type: 'text/csv' }));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);

    } catch (err) {
      // Você pode substituir isso por um toast/notificação
      toast.error('Não foi possível gerar o arquivo CSV.');
    } finally {
      setExportingFormat(null);
    }
  };

  const handleDownloadXml = async () => {
    if (!selectedRowId) return;

    try {
      setIsFetchingData(true);
      // Chamada para a nova rota de download
      const response = await api.get(`/dfe/download-xml/${selectedRowId}`, {
        responseType: 'blob' // Importante para lidar com download de arquivos
      });

      // Cria um link temporário para disparar o download no navegador
      const blob = new Blob([response.data], { type: 'application/xml' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');

      // Busca dados da linha atual para nomear o arquivo
      const item = data.find(i => i.id === selectedRowId);
      const filename = `NFe_${item?.chave_acesso || selectedRowId}.xml`;

      link.href = url;
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);

      toast.success("XML baixado com sucesso!");
    } catch (err) {
      // Tenta ler a mensagem de erro do blob se houver falha
      if (err.response?.data instanceof Blob) {
        const reader = new FileReader();
        reader.onload = () => {
          const errorData = JSON.parse(reader.result);
          toast.error(errorData.detail || "Erro ao baixar XML.");
        };
        reader.readAsText(err.response.data);
      } else {
        toast.error(err.response?.data?.detail || "Erro ao baixar XML.");
      }
    } finally {
      setIsFetchingData(false);
    }
  };

  const handleIntelipostConfigClick = async () => {
    try {
      setIsFetchingData(true);
      // Verifica se já existe alguma configuração salva
      const response = await api.get('/generic/intelipost_configuracoes');
      const items = response.data.items;

      if (items && items.length > 0) {
        // Se existir, abre o formulário de edição do primeiro item
        navigate(`/intelipost_configuracoes/edit/${items[0].id_sequencial ?? items[0].id}`);
      } else {
        // Se não existir, abre o formulário de criação
        navigate(`/intelipost_configuracoes/new`);
      }
    } catch (err) {
      toast.error('Não foi possível verificar as configurações.');
    } finally {
      setIsFetchingData(false);
    }
  };

  const handleGenerateReport = async (reportId, format = 'csv') => {
    setExportingFormat(format);
    try {
      let endpoint = '';
      if (format === 'pdf') endpoint = `/reports/generate-pdf/${reportId}`;
      else if (format === 'xml') endpoint = `/reports/generate-xml/${reportId}`;
      else endpoint = `/reports/generate/${reportId}`;

      const response = await api.get(endpoint, {
        responseType: 'blob',
      });

      const report = data.find(r => r.id === reportId);
      const reportName = report?.nome?.replace(/\s+/g, '_') || 'Relatorio';
      const timestamp = new Date().toLocaleString('pt-BR').replace(/[/:, ]/g, '_');

      let extension = 'csv';
      let mimeType = 'text/csv';

      if (format === 'pdf') {
        extension = 'pdf';
        mimeType = 'application/pdf';
      } else if (format === 'xml') {
        extension = 'zip';
        mimeType = 'application/zip';
      }

      let filename = `${reportName}_${timestamp}.${extension}`;

      const disposition = response.headers['content-disposition'];
      if (disposition && disposition.includes('filename=')) {
        const match = disposition.match(/filename="?([^";]+)"?/);
        if (match && match[1]) filename = match[1];
      }

      const url = window.URL.createObjectURL(new Blob([response.data], { type: mimeType }));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(`Erro ao gerar relatório em ${format.toUpperCase()}.`);
    } finally {
      setExportingFormat(null);
    }
  };

  const handleExportInventory = async (windowKey, format = 'csv') => {
    try {
      const dateStart = new Date(Number(windowKey));
      const dateEnd = new Date(Number(windowKey) + 60000);

      const inventoryFilters = [
        { field: 'criado_em', operator: 'gte', value: dateStart.toISOString() },
        { field: 'criado_em', operator: 'lt', value: dateEnd.toISOString() },
        { field: 'situacao', operator: 'equals', value: 'Inventário' }
      ];

      // Mapeia colunas visíveis na tabela para a exportação
      const configColumns = columnsToDisplay.map(colName => {
        const field = fieldMetaMap.get(colName);
        let label = field?.label || colName;
        let fieldPath = colName;

        // Ajustes para campos de relacionamento e virtuais no Estoque
        if (colName === 'id_produto') {
          fieldPath = 'produto.descricao';
          label = 'Produto';
        } else if (colName === 'custo') {
          fieldPath = 'custo'; // Resolvido no backend (injetado)
          label = 'Custo Unit.';
        } else if (colName === 'valor_total') {
          fieldPath = 'valor_total'; // Resolvido no backend (injetado)
          label = 'Valor Total';
        }

        if (label === 'id') label = 'ID';
        if (label === 'criado_em') label = 'Data/Hora';

        return { field: fieldPath, label };
      });

      const config = {
        report_name: `Contagem de Inventário`,
        report_description: `Período: ${dateStart.toLocaleString('pt-BR')} - ID Grupo: ${windowKey}`,
        columns: configColumns,
        filters: inventoryFilters
      };

      // Usa o sistema de relatórios (ID 0) para ambos os formatos
      // Isso garante colunas de relacionamento (dots) e labels corretos
      const endpoint = format === 'pdf' ? `/reports/generate-pdf/0` : `/reports/generate/0`;

      const response = await api.get(endpoint, {
        params: {
          model_name: 'estoque',
          config_json: JSON.stringify(config)
        },
        responseType: 'blob'
      });

      const mimeType = format === 'pdf' ? 'application/pdf' : 'text/csv';
      const extension = format === 'pdf' ? 'pdf' : 'csv';
      const url = window.URL.createObjectURL(new Blob([response.data], { type: mimeType }));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `Inventario_${windowKey}.${extension}`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);

      toast.success('Exportação concluída!');
    } catch (err) {
      console.error("Erro ao exportar inventário:", err);
      toast.error('Erro ao exportar inventário.');
    }
  };

  const handleExportSelectedInventory = (format) => {
    if (!selectedGroupKey) return;
    handleExportInventory(selectedGroupKey, format);
  };

  const handleInventoryBatchAction = async (windowKey, action) => {
    if (action === 'finalizar' && !window.confirm("Deseja finalizar este grupo de inventário? Ele deixará de ser editável nesta aba.")) return;

    setIsFetchingData(true);
    try {
      await api.post(`/generic/estoque/batch-update`, {
        ids: [],
        data: { situacao: 'Finalizado' },
        filters: JSON.stringify([
          { field: 'criado_em', operator: 'gte', value: new Date(Number(windowKey)).toISOString() },
          { field: 'criado_em', operator: 'lt', value: new Date(Number(windowKey) + 60000).toISOString() },
          { field: 'situacao', operator: 'equals', value: 'Inventário' }
        ])
      });
      toast.success("Ação realizada com sucesso!");
      fetchData();
    } catch (err) {
      toast.error("Erro ao realizar ação no grupo de inventário.");
    } finally {
      setIsFetchingData(false);
    }
  };

  const handleRowClick = (e, id, index) => {
    if (e.shiftKey && anchorIndex !== -1) {
      const start = Math.min(anchorIndex, index);
      const end = Math.max(anchorIndex, index);
      const rangeIds = data.slice(start, end + 1).map(item => item.id);
      setSelectedRowIds(rangeIds);
      setFocusIndex(index);
    } else if (e.ctrlKey || e.metaKey) {
      setSelectedRowIds(prev => {
        if (prev.includes(id)) return prev.filter(sid => sid !== id);
        return [...prev, id];
      });
      setAnchorIndex(index);
      setFocusIndex(index);
    } else {
      setSelectedRowIds([id]);
      setAnchorIndex(index);
      setFocusIndex(index);
    }
    // Garante que o container da tabela receba o foco para navegação por teclado imediata
    e.currentTarget.closest('[tabIndex="0"]')?.focus();
  };

  const handleKeyDown = (e) => {
    if (data.length === 0) return;
    if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return;

    e.preventDefault();
    const currentFocus = focusIndex === -1 ? 0 : focusIndex;
    let nextFocus = e.key === 'ArrowDown'
      ? Math.min(currentFocus + 1, data.length - 1)
      : Math.max(currentFocus - 1, 0);

    if (e.shiftKey) {
      const anchor = anchorIndex === -1 ? currentFocus : anchorIndex;
      if (anchorIndex === -1) setAnchorIndex(currentFocus);
      const start = Math.min(anchor, nextFocus);
      const end = Math.max(anchor, nextFocus);
      setSelectedRowIds(data.slice(start, end + 1).map(item => item.id));
    } else {
      setSelectedRowIds([data[nextFocus].id]);
      setAnchorIndex(nextFocus);
    }
    setFocusIndex(nextFocus);
  };

  const handleOpenBatchBaixa = async () => {
    try {
      const res = await api.get('/options/contas/caixa_destino_origem');
      setCaixaOptions(res.data);
      if (res.data.length > 0) setSelectedCaixa(res.data[0].valor);
      setIsBatchBaixaModalOpen(true);
    } catch (err) {
      toast.error("Erro ao carregar opções de caixa.");
    }
  };

  const handleConfirmBatchBaixa = async () => {
    if (!selectedCaixa) {
      toast.warning("Selecione um caixa.");
      return;
    }
    setIsFetchingData(true);
    try {
      const today = new Date().toISOString().split('T')[0];
      await api.put(`/generic/contas/batch-update`, {
        ids: selectedRowIds,
        item_data: {
          situacao: 'Pago',
          caixa_destino_origem: selectedCaixa,
          data_baixa: today
        }
      });
      if (selectedRowIds.length > 1) {
        toast.success(`${selectedRowIds.length} contas baixadas com sucesso!`);
      } else {
        toast.success(`Conta "${selectedItemName}" baixada com sucesso!`);
      }
      setRefreshTrigger(prev => prev + 1);
      setSelectedRowIds([]);
      setIsBatchBaixaModalOpen(false);
    } catch (err) {
      toast.error("Erro ao processar baixa em lote.");
    } finally {
      setIsFetchingData(false);
    }
  };

  const handleSavePreferences = async (newConfig) => {
    setUserPreferences(newConfig);
    try {
      await api.post(`/preferences/${modelName}`, newConfig);
    } catch (err) {
      toast.error("Erro ao salvar configurações.");
    }
  };

  const toggleSort = (field) => {
    let targetField = field;
    if (hasIdSeq && targetField === 'id') {
      targetField = 'id_sequencial';
    }
    const sortList = getSortArray(userPreferences.sort, hasIdSeq);
    const idx = sortList.findIndex(s => s.field === targetField || (targetField === 'id_sequencial' && s.field === 'id'));
    let newSort;

    if (idx === -1) {
      // Nova coluna clicada: torna-se a Primária (1º) com ASC.
      // A antiga primária desloca-se para Secundária (2º). Mantém no máximo 2 ordenações.
      newSort = [{ field: targetField, direction: 'asc' }, ...sortList].slice(0, 2);
    } else if (idx === 0) {
      // Coluna Primária atual clicada:
      const current = sortList[0];
      if (current.direction === 'asc') {
        // Alterna para DESC
        newSort = [{ field: targetField, direction: 'desc' }, ...sortList.slice(1)].slice(0, 2);
      } else {
        // Remove a primária. A secundária (se houver) é promovida a primária.
        const remaining = sortList.slice(1);
        if (remaining.length > 0) {
          newSort = remaining;
        } else {
          // Se não houver secundária, reseta para ordenação padrão (id_sequencial / id desc)
          const defaultSortField = hasIdSeq ? 'id_sequencial' : 'id';
          newSort = [{ field: defaultSortField, direction: 'desc' }];
        }
      }
    } else {
      // Coluna Secundária atual clicada:
      // Promove esta coluna para Primária (mantendo direção ou asc) e desloca a antiga primária para Secundária.
      const current = sortList[idx];
      const otherSorts = sortList.filter((_, i) => i !== idx);
      newSort = [{ field: targetField, direction: current?.direction || 'asc' }, ...otherSorts].slice(0, 2);
    }

    handleSavePreferences({ ...userPreferences, sort: newSort });
  };

  const removeColumn = (colName) => {
    const newCols = (userPreferences.visibleColumns || []).filter(c => c !== colName);
    handleSavePreferences({
      ...userPreferences,
      visibleColumns: newCols,
      isExplicitlyCleared: newCols.length === 0
    });
  };

  const addColumn = (colName) => {
    if ((userPreferences.visibleColumns || []).includes(colName)) return;
    const newCols = [...(userPreferences.visibleColumns || []), colName];
    handleSavePreferences({
      ...userPreferences,
      visibleColumns: newCols,
      isExplicitlyCleared: false
    });
  };

  const moveColumn = (from, to) => {
    const fromColName = typeof from === 'string' ? from : columnsToDisplay[from];
    const toColName = typeof to === 'string' ? to : columnsToDisplay[to];

    if (!fromColName || !toColName || fromColName === toColName) return;

    const currentDisplay = [...columnsToDisplay];
    const fromIdx = currentDisplay.indexOf(fromColName);
    const toIdx = currentDisplay.indexOf(toColName);

    if (fromIdx === -1 || toIdx === -1) return;

    const [removed] = currentDisplay.splice(fromIdx, 1);
    currentDisplay.splice(toIdx, 0, removed);

    // Atualiza imediatamente as colunas renderizadas na tela
    setColumnsToDisplay(currentDisplay);

    // Reordena nas preferências
    const currentVisible = (userPreferences.visibleColumns && userPreferences.visibleColumns.length > 0)
      ? userPreferences.visibleColumns
      : columnsToDisplay;

    const newVisible = [...currentVisible];
    const visFromIdx = newVisible.indexOf(fromColName);
    const visToIdx = newVisible.indexOf(toColName);

    if (visFromIdx !== -1 && visToIdx !== -1) {
      const [visRemoved] = newVisible.splice(visFromIdx, 1);
      newVisible.splice(visToIdx, 0, visRemoved);
    } else {
      newVisible.length = 0;
      newVisible.push(...currentDisplay);
    }

    handleSavePreferences({ ...userPreferences, visibleColumns: newVisible });
  };

  const addQuickFilterField = (type) => {
    const currentFields = userPreferences.quickFilterFields || [];
    if (currentFields.length >= 5) {
      toast.warning("Limite de 5 filtros rápidos atingido.");
      return;
    }

    const uniqueKey = `${type}:${Date.now()}`;

    // Inicializa valores padrão
    let defaultValue = "";
    if (type === '__search__') defaultValue = { column: "", term: "" };
    else if (type === '__date__') {
      const preferred = dateColumns.find(c => ['data_orcamento', 'data_emissao', 'data', 'created_at', 'criado_em'].includes(c.name));
      defaultValue = { column: preferred ? preferred.name : (dateColumns[0]?.name || ""), start: "", end: "" };
    }
    else if (type === '__dropdown__') defaultValue = { column: dropdownColumns[0]?.name || "", value: "" };

    setQuickFilterValues(prev => ({ ...prev, [uniqueKey]: defaultValue }));

    setUserPreferences(prev => ({
      ...prev,
      quickFilterFields: [...currentFields, uniqueKey]
    }));
  };

  const removeQuickFilterField = (uniqueKey) => {
    setUserPreferences(prev => ({
      ...prev,
      quickFilterFields: (prev.quickFilterFields || []).filter(k => k !== uniqueKey)
    }));
    setQuickFilterValues(prev => {
      const next = { ...prev };
      delete next[uniqueKey];
      return next;
    });
  };

  const handleQuickFilterChange = (fieldName, value) => {
    setQuickFilterValues(prev => ({ ...prev, [fieldName]: value }));
  };

  const totalPages = Math.ceil(totalCount / effectiveLimit) || 1; // || 1 para evitar 0

  const outletContext = useOutletContext();
  const setPageHeader = outletContext?.setPageHeader;

  // --- BREADCRUMB & HEADER: Hooks DEVEM ficar ANTES dos early returns (Rules of Hooks) ---
  const pageTitle = useMemo(() => {
    const rawPlural = metadata?.display_name_plural || metadata?.display_name || HUMAN_MODEL_NAMES[modelName] || modelName.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    return statusFilter && statusFilter !== 'Todos' ? `${rawPlural} (${statusFilter})` : rawPlural;
  }, [metadata, modelName, statusFilter]);

  const breadcrumbCrumbs = useMemo(() => {
    const activeModel = paramModelName || modelName;
    const entry = MODULE_MAP[activeModel];
    const crumbs = [{ label: 'Home', path: '/dashboard' }];

    const rawPlural = metadata?.display_name_plural || metadata?.display_name || HUMAN_MODEL_NAMES[activeModel] || activeModel.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    const currentPageLabel = statusFilter && statusFilter !== 'Todos' ? statusFilter : rawPlural;

    if (entry) {
      // Adiciona o módulo pai se seu nome for diferente da página atual (evita duplicados tipo "Pedidos > Pedidos")
      const isSameLabel = entry.module.toLowerCase() === currentPageLabel.toLowerCase();
      if (!isSameLabel) {
        crumbs.push({ label: entry.module, path: entry.modulePath });
      }
    }

    crumbs.push({ label: currentPageLabel, path: null });
    return crumbs;
  }, [paramModelName, modelName, statusFilter, metadata]);

  useEffect(() => {
    if (setPageHeader && metadata) {
      setPageHeader({
        title: pageTitle,
        crumbs: breadcrumbCrumbs
      });
    }
  }, [pageTitle, breadcrumbCrumbs, setPageHeader, metadata]);

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

  return (
    // Fundo cinza claro para a página, como na imagem
    <div className="bg-gray-100 min-h-screen p-8">
      <div className="container mx-auto">
        {/* Header (Breadcrumb, Título e Filtros) */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 gap-4">
          <div className="flex flex-col gap-1">
            <Breadcrumb crumbs={breadcrumbCrumbs} />
            <h1 className="text-2xl font-bold text-gray-800 tracking-tight">
              {pageTitle}
            </h1>
          </div>

          {/* Filtros e Pesquisa */}
          <div className="flex flex-wrap items-center gap-2 mb-[-30px]">

            {/* --- FILTROS RÁPIDOS (ORDEM DINÂMICA) --- */}
            {/* --- GERENCIADOR DE FILTROS RÁPIDOS --- */}
            <Popover className="relative">
              <Popover.Button className="flex items-center justify-center h-[38px] w-[38px] text-gray-500 focus:text-gray-700" title="Configurar filtros rápidos">
                <Plus size={18} />
              </Popover.Button>

              <Transition
                as={Fragment}
                enter="transition ease-out duration-200"
                enterFrom="opacity-0 translate-y-1"
                enterTo="opacity-100 translate-y-0"
                leave="transition ease-in duration-150"
                leaveFrom="opacity-100 translate-y-0"
                leaveTo="opacity-0 translate-y-1"
              >
                <Popover.Panel className="absolute right-0 top-full z-50 mt-2 w-64 bg-white rounded-lg shadow-xl ring-1 ring-black ring-opacity-5 p-2">
                  <div className="max-h-60 overflow-y-auto custom-scrollbar">
                    <p className="text-[10px] font-bold text-gray-400 uppercase px-2 py-1 border-b mb-1">Filtros Disponíveis</p>
                    <div className="p-1 space-y-1 mb-2">
                      <button onClick={() => addQuickFilterField('__search__')} className="w-full text-left px-2 py-1.5 text-xs text-gray-700 hover:bg-gray-100 rounded font-medium">
                        Busca Global / Texto
                      </button>
                      <button onClick={() => addQuickFilterField('__dropdown__')} className="w-full text-left px-2 py-1.5 text-xs text-gray-700 hover:bg-gray-100 rounded font-medium">
                        Dropdown de Coluna
                      </button>
                      <button onClick={() => addQuickFilterField('__date__')} className="w-full text-left px-2 py-1.5 text-xs text-gray-700 hover:bg-gray-100 rounded font-medium">
                        Filtro de Data (Período)
                      </button>
                    </div>
                  </div>
                </Popover.Panel>
              </Transition>
            </Popover>

            {(userPreferences.quickFilterFields || []).map(uniqueKey => {
              const [type] = uniqueKey.split(':');
              const filterVal = quickFilterValues[uniqueKey] || {};

              // 1. BUSCA GLOBAL
              if (type === '__search__') {
                return (
                  <div key={uniqueKey} className="flex items-center bg-white rounded-md shadow-sm border border-gray-300 h-[38px] pr-1">
                    <div className="flex h-full items-center">
                      <Menu as="div" className="relative flex items-center h-full bg-gray-50 border-r rounded-l-md border-gray-200 group hover:bg-gray-100 transition-colors">
                        <Menu.Button className="flex items-center h-full focus:outline-none" title={filterVal.column ? `Filtrando por: ${metadata.fields.find(f => f.name === filterVal.column)?.label}` : "Busca Global"}>
                          <ChevronDown size={14} className="text-gray-400 group-hover:text-gray-600" />
                        </Menu.Button>
                        <Transition
                          as={Fragment}
                          enter="transition ease-out duration-100"
                          enterFrom="transform opacity-0 scale-95"
                          enterTo="transform opacity-100 scale-100"
                          leave="transition ease-in duration-75"
                          leaveFrom="transform opacity-100 scale-100"
                          leaveTo="transform opacity-0 scale-95"
                        >
                          <Menu.Items className="absolute left-0 top-full z-50 mt-1 w-56 origin-top-left rounded-md bg-white shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none max-h-60 overflow-y-auto custom-scrollbar">
                            <div className="p-1">
                              <Menu.Item>
                                {({ active }) => {
                                  const isSelected = filterVal.column === "" || !filterVal.column;
                                  return (
                                    <button onClick={() => handleQuickFilterChange(uniqueKey, { ...filterVal, column: "" })} className={`${active ? 'bg-gray-100 text-gray-900' : 'text-gray-700'} ${isSelected ? 'bg-blue-50 text-blue-700 font-bold' : ''} group flex w-full items-center justify-between rounded-md px-2 py-2 text-sm`}>
                                      <span>Busca Global</span>
                                      {isSelected && <Check size={14} />}
                                    </button>
                                  );
                                }}
                              </Menu.Item>
                              {metadata?.fields?.map((field) => (
                                <Menu.Item key={field.name}>
                                  {({ active }) => {
                                    const isSelected = filterVal.column === field.name;
                                    return (
                                      <button onClick={() => handleQuickFilterChange(uniqueKey, { ...filterVal, column: field.name })} className={`${active ? 'bg-gray-100 text-gray-900' : 'text-gray-700'} ${isSelected ? 'bg-blue-50 text-blue-700 font-bold' : ''} group flex w-full items-center justify-between rounded-md px-2 py-2 text-sm`}>
                                        <span>{field.label}</span>
                                        {isSelected && <Check size={14} />}
                                      </button>
                                    );
                                  }}
                                </Menu.Item>
                              ))}
                            </div>
                          </Menu.Items>
                        </Transition>
                      </Menu>
                      <input
                        type="text"
                        placeholder="Digite para Pesquisar..."
                        value={filterVal.term || ""}
                        onChange={(e) => handleQuickFilterChange(uniqueKey, { ...filterVal, term: e.target.value })}
                        className="h-full w-48 border-none py-0 px-2 text-sm focus:ring-0 outline-none font-medium"
                      />
                    </div>
                    <button
                      onClick={() => filterVal.term ? handleQuickFilterChange(uniqueKey, { ...filterVal, term: "" }) : removeQuickFilterField(uniqueKey)}
                      className="p-1 text-gray-300 hover:text-red-500 transition-colors"
                      title={filterVal.term ? "Limpar busca" : "Remover filtro"}
                    >
                      <X size={14} />
                    </button>
                  </div>
                );
              }

              // 2. DROPDOWN DE COLUNA
              if (type === '__dropdown__' && dropdownColumns.length > 0) {
                const currentColumn = filterVal.column || (dropdownColumns[0]?.name || "");
                const currentField = dropdownColumns.find(c => c.name === currentColumn);
                return (
                  <div key={uniqueKey} className="flex items-center bg-white rounded-md shadow-sm border border-gray-300 h-[38px] pr-1">
                    <Menu as="div" className="relative flex items-center h-full bg-gray-50 border-r rounded-l-md border-gray-200 group hover:bg-gray-100 transition-colors">
                      <Menu.Button className="flex items-center h-fullfocus:outline-none" title={`Coluna: ${currentField?.label}`}>
                        <ChevronDown size={14} className="text-gray-400 group-hover:text-gray-600" />
                      </Menu.Button>
                      <Transition
                        as={Fragment}
                        enter="transition ease-out duration-100"
                        enterFrom="transform opacity-0 scale-95"
                        enterTo="transform opacity-100 scale-100"
                        leave="transition ease-in duration-75"
                        leaveFrom="transform opacity-100 scale-100"
                        leaveTo="transform opacity-0 scale-95"
                      >
                        <Menu.Items className="absolute left-0 top-full z-50 mt-1 w-56 origin-top-left rounded-md bg-white shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none max-h-60 overflow-y-auto custom-scrollbar">
                          <div className="p-1">
                            {dropdownColumns.map(col => (
                              <Menu.Item key={col.name}>
                                {({ active }) => {
                                  const isSelected = currentColumn === col.name;
                                  return (
                                    <button onClick={() => handleQuickFilterChange(uniqueKey, { ...filterVal, column: col.name, value: "" })} className={`${active ? 'bg-gray-100 text-gray-900' : 'text-gray-700'} ${isSelected ? 'bg-blue-50 text-blue-700 font-bold' : ''} group flex w-full items-center justify-between rounded-md px-2 py-2 text-sm`}>
                                      <span>{col.label}</span>
                                      {isSelected && <Check size={14} />}
                                    </button>
                                  );
                                }}
                              </Menu.Item>
                            ))}
                          </div>
                        </Menu.Items>
                      </Transition>
                    </Menu>

                    <Menu as="div" className="relative flex items-center h-full px-2">
                      <Menu.Button className="flex items-center gap-1 text-sm font-medium text-gray-700 hover:text-gray-900 focus:outline-none">
                        <span className="truncate max-w-[120px]">
                          {(() => {
                            const vals = filterVal.value ? String(filterVal.value).split(',') : [];
                            if (vals.length === 0) return "Todos";
                            if (vals.length === 1) return currentField?.options?.find(o => String(o.value) === String(vals[0]))?.label || "Desconhecido";
                            return `${vals.length} selecionados`;
                          })()}
                        </span>
                      </Menu.Button>
                      <Transition
                        as={Fragment}
                        enter="transition ease-out duration-100"
                        enterFrom="transform opacity-0 scale-95"
                        enterTo="transform opacity-100 scale-100"
                        leave="transition ease-in duration-75"
                        leaveFrom="transform opacity-100 scale-100"
                        leaveTo="transform opacity-0 scale-95"
                      >
                        <Menu.Items className="absolute left-0 top-full z-50 mt-1 w-56 origin-top-left rounded-md bg-white shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none max-h-60 overflow-y-auto custom-scrollbar">
                          <div className="p-1">
                            <Menu.Item>
                              {({ active }) => {
                                const isSelected = !filterVal.value;
                                return (
                                  <button onClick={() => handleQuickFilterChange(uniqueKey, { ...filterVal, value: "" })} className={`${active ? 'bg-gray-100 text-gray-900' : 'text-gray-700'} ${isSelected ? 'bg-blue-50 text-blue-700 font-bold' : ''} group flex w-full items-center justify-between rounded-md px-2 py-2 text-sm`}>
                                    <span>Todos</span>
                                    {isSelected && <Check size={14} />}
                                  </button>
                                );
                              }}
                            </Menu.Item>
                            {currentField?.options?.map(opt => (
                              <Menu.Item key={opt.value}>
                                {({ active }) => {
                                  const vals = filterVal.value ? String(filterVal.value).split(',') : [];
                                  const isSelected = vals.includes(String(opt.value));
                                  return (
                                    <div
                                      onClick={(e) => {
                                        e.preventDefault();
                                        e.stopPropagation();
                                        let newVals = [...vals];
                                        if (isSelected) {
                                          newVals = newVals.filter(v => String(v) !== String(opt.value));
                                        } else {
                                          newVals.push(String(opt.value));
                                        }
                                        handleQuickFilterChange(uniqueKey, { ...filterVal, value: newVals.join(',') });
                                      }}
                                      className={`${active ? 'bg-gray-100 text-gray-900 cursor-pointer' : 'text-gray-700 cursor-pointer'} ${isSelected ? 'bg-blue-50 text-blue-700 font-bold' : ''} group flex w-full items-center justify-between rounded-md px-2 py-2 text-sm`}
                                    >
                                      <span>{opt.label}</span>
                                      {isSelected && <Check size={14} />}
                                    </div>
                                  );
                                }}
                              </Menu.Item>
                            ))}
                          </div>
                        </Menu.Items>
                      </Transition>
                    </Menu>
                    <button
                      onClick={() => filterVal.value ? handleQuickFilterChange(uniqueKey, { ...filterVal, value: "" }) : removeQuickFilterField(uniqueKey)}
                      className="p-1 text-gray-300 hover:text-red-500 transition-colors"
                      title={filterVal.value ? "Limpar seleção" : "Remover filtro"}
                    >
                      <X size={14} />
                    </button>
                  </div>
                );
              }

              // 3. RANGE DE DATA
              if (type === '__date__' && dateColumns.length > 0) {
                const currentColumn = filterVal.column || (dateColumns[0]?.name || "");
                return (
                  <div key={uniqueKey} className="flex items-center bg-white rounded-md shadow-sm border border-gray-300 h-[38px] pr-1">
                    <Menu as="div" className="relative flex items-center h-full bg-gray-50 border-r rounded-l-md border-gray-200 group hover:bg-gray-100 transition-colors">
                      <Menu.Button className="flex items-center h-full focus:outline-none" title={`Coluna de Data: ${dateColumns.find(c => c.name === currentColumn)?.label}`}>
                        <ChevronDown size={14} className="text-gray-400 group-hover:text-gray-600" />
                      </Menu.Button>
                      <Transition
                        as={Fragment}
                        enter="transition ease-out duration-100"
                        enterFrom="transform opacity-0 scale-95"
                        enterTo="transform opacity-100 scale-100"
                        leave="transition ease-in duration-75"
                        leaveFrom="transform opacity-100 scale-100"
                        leaveTo="transform opacity-0 scale-95"
                      >
                        <Menu.Items className="absolute left-0 top-full z-50 mt-1 w-56 origin-top-left rounded-md bg-white shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none max-h-60 overflow-y-auto custom-scrollbar">
                          <div className="p-1">
                            {dateColumns.map(col => (
                              <Menu.Item key={col.name}>
                                {({ active }) => {
                                  const isSelected = currentColumn === col.name;
                                  return (
                                    <button onClick={() => handleQuickFilterChange(uniqueKey, { ...filterVal, column: col.name })} className={`${active ? 'bg-gray-100 text-gray-900' : 'text-gray-700'} ${isSelected ? 'bg-blue-50 text-blue-700 font-bold' : ''} group flex w-full items-center justify-between rounded-md px-2 py-2 text-sm`}>
                                      <span>{col.label}</span>
                                      {isSelected && <Check size={14} />}
                                    </button>
                                  );
                                }}
                              </Menu.Item>
                            ))}
                          </div>
                        </Menu.Items>
                      </Transition>
                    </Menu>
                    <Popover className="relative h-full flex items-center">
                      <div className="h-full flex items-center px-2 text-sm text-gray-700 font-medium">
                        <Popover.Button className="focus:outline-none mr-1.5 p-1 hover:bg-gray-100 rounded-md transition-colors group">
                          <Calendar size={14} className="text-gray-400 group-hover:text-blue-600" />
                        </Popover.Button>
                        <input
                          type="text"
                          className="bg-transparent border-none focus:ring-0 p-0 text-sm font-medium w-[160px] outline-none"
                          placeholder="Selecione o Período"
                          value={filterVal.text ?? (
                            !filterVal.start && !filterVal.end
                              ? ""
                              : `${filterVal.start ? filterVal.start.split('-').reverse().join('/') : '...'} - ${filterVal.end ? filterVal.end.split('-').reverse().join('/') : '...'}`
                          )}
                          onChange={(e) => {
                            const val = e.target.value;
                            const parts = val.split(' - ');
                            if (parts.length === 2) {
                              const dateRegex = /^(\d{2})\/(\d{2})\/(\d{4})$/;
                              const m1 = parts[0].trim().match(dateRegex);
                              const m2 = parts[1].trim().match(dateRegex);
                              if (m1 && m2) {
                                const start = `${m1[3]}-${m1[2]}-${m1[1]}`;
                                const end = `${m2[3]}-${m2[2]}-${m2[1]}`;
                                handleQuickFilterChange(uniqueKey, { ...filterVal, start, end, text: val });
                                return;
                              }
                            }
                            handleQuickFilterChange(uniqueKey, { ...filterVal, text: val });
                          }}
                          onBlur={() => {
                            const { text, ...rest } = filterVal;
                            handleQuickFilterChange(uniqueKey, rest);
                          }}
                          onKeyDown={(e) => e.key === 'Enter' && e.target.blur()}
                        />
                      </div>
                      <Transition as={Fragment} enter="transition ease-out duration-200" enterFrom="opacity-0 translate-y-1" enterTo="opacity-100 translate-y-0" leave="transition ease-in duration-150" leaveFrom="opacity-100 translate-y-0" leaveTo="opacity-0 translate-y-1">
                        <Popover.Panel className="absolute right-0 top-full z-50 mt-2 w-screen max-w-[calc(100vw-2rem)] sm:w-auto bg-white rounded-lg shadow-xl ring-1 ring-black ring-opacity-5 p-4">
                          <div className="space-y-4">
                            <div className="flex justify-center border-b border-gray-100 pb-2">
                              <DatePicker
                                selected={filterVal.start ? new Date(filterVal.start + 'T00:00:00') : null}
                                onChange={(update) => {
                                  const [start, end] = update;
                                  const format = (d) => {
                                    if (!d) return '';
                                    const year = d.getFullYear();
                                    const month = String(d.getMonth() + 1).padStart(2, '0');
                                    const day = String(d.getDate()).padStart(2, '0');
                                    return `${year}-${month}-${day}`;
                                  };
                                  handleQuickFilterChange(uniqueKey, { ...filterVal, start: format(start), end: format(end), text: undefined });
                                }}
                                startDate={filterVal.start ? new Date(filterVal.start + 'T00:00:00') : null}
                                endDate={filterVal.end ? new Date(filterVal.end + 'T00:00:00') : null}
                                selectsRange
                                inline
                                locale="pt-BR"
                              />
                            </div>

                          </div>
                        </Popover.Panel>
                      </Transition>
                    </Popover>
                    <button
                      onClick={() => (filterVal.start || filterVal.end || filterVal.text) ? handleQuickFilterChange(uniqueKey, { ...filterVal, start: "", end: "", text: undefined }) : removeQuickFilterField(uniqueKey)}
                      className="p-1 text-gray-300 hover:text-red-500 transition-colors"
                      title={(filterVal.start || filterVal.end || filterVal.text) ? "Limpar período" : "Remover filtro"}
                    >
                      <X size={14} />
                    </button>
                  </div>
                );
              }

              // 4. CAMPOS DINÂMICOS (PINADOS)
              const fieldName = type;
              const field = fieldMetaMap.get(fieldName);
              if (!field) return null;
              const value = filterVal || "";

              return (
                <div key={uniqueKey} className="flex items-center bg-white rounded-md shadow-sm border border-gray-300 h-[38px] px-2 gap-1">
                  <span className="text-[10px] font-bold text-gray-400 uppercase whitespace-nowrap">{field.label}:</span>

                  {field.type === 'select' ? (
                    <Menu as="div" className="relative flex items-center h-full">
                      <Menu.Button className="flex items-center gap-1 text-sm font-medium text-gray-700 hover:text-gray-900 focus:outline-none">
                        <span className="truncate max-w-[120px]">
                          {field.options?.find(o => String(o.value) === String(value))?.label || "Todos"}
                        </span>
                        <ChevronDown size={12} className="text-gray-400" />
                      </Menu.Button>
                      <Transition
                        as={Fragment}
                        enter="transition ease-out duration-100"
                        enterFrom="transform opacity-0 scale-95"
                        enterTo="transform opacity-100 scale-100"
                        leave="transition ease-in duration-75"
                        leaveFrom="transform opacity-100 scale-100"
                        leaveTo="transform opacity-0 scale-95"
                      >
                        <Menu.Items className="absolute left-0 top-full z-50 mt-1 w-56 origin-top-left rounded-md bg-white shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none max-h-60 overflow-y-auto custom-scrollbar">
                          <div className="p-1">
                            <Menu.Item>
                              {({ active }) => {
                                const isSelected = value === "" || !value;
                                return (
                                  <button onClick={() => handleQuickFilterChange(uniqueKey, "")} className={`${active ? 'bg-gray-100 text-gray-900' : 'text-gray-700'} ${isSelected ? 'bg-blue-50 text-blue-700 font-bold' : ''} group flex w-full items-center justify-between rounded-md px-2 py-2 text-sm`}>
                                    <span>Todos</span>
                                    {isSelected && <Check size={14} />}
                                  </button>
                                );
                              }}
                            </Menu.Item>
                            {field.options?.map(opt => (
                              <Menu.Item key={opt.value}>
                                {({ active }) => {
                                  const isSelected = String(value) === String(opt.value);
                                  return (
                                    <button onClick={() => handleQuickFilterChange(uniqueKey, opt.value)} className={`${active ? 'bg-gray-100 text-gray-900' : 'text-gray-700'} ${isSelected ? 'bg-blue-50 text-blue-700 font-bold' : ''} group flex w-full items-center justify-between rounded-md px-2 py-2 text-sm`}>
                                      <span>{opt.label}</span>
                                      {isSelected && <Check size={14} />}
                                    </button>
                                  );
                                }}
                              </Menu.Item>
                            ))}
                          </div>
                        </Menu.Items>
                      </Transition>
                    </Menu>
                  ) : (field.type === 'date' || field.type === 'datetime') ? (
                    <input
                      type="date"
                      value={value}
                      onChange={(e) => handleQuickFilterChange(uniqueKey, e.target.value)}
                      className="h-full text-sm border-none focus:ring-0 text-gray-700 bg-transparent py-0 px-0 outline-none font-medium w-32"
                    />
                  ) : (
                    <input
                      type="text"
                      value={value}
                      onChange={(e) => handleQuickFilterChange(uniqueKey, e.target.value)}
                      placeholder="..."
                      className="h-full text-sm border-none focus:ring-0 text-gray-700 bg-transparent py-0 px-0 outline-none font-medium w-24"
                    />
                  )}

                  <button
                    onClick={() => filterVal ? handleQuickFilterChange(uniqueKey, "") : removeQuickFilterField(uniqueKey)}
                    className="text-gray-300 hover:text-red-500 transition-colors ml-1"
                    title={filterVal ? "Limpar filtro" : "Remover filtro"}
                  >
                    <X size={14} />
                  </button>
                </div>
              );
            })}
            {/* BOTÃO CONFIGURAR TABELA (MODO EDIÇÃO) */}
            {isEditMode && (
              <button
                type="button"
                onClick={handleResetTablePreferences}
                className="flex items-center px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded-md shadow-sm text-sm font-medium transition-colors"
                title="Resetar tabela para a configuração padrão"
              >
                <RotateCcw size={16} className="mr-2" />
                Resetar Tabela
              </button>
            )}
            <button
              onClick={() => setIsEditMode(!isEditMode)}
              className={`flex items-center px-4 py-2 rounded-md shadow-sm text-sm font-medium transition-colors ${isEditMode ? 'bg-blue-800 text-white' : 'bg-blue-600 text-white hover:bg-blue-800'
                }`}
            >
              {isEditMode ? <Check size={16} className="mr-2" /> : <SlidersHorizontal size={16} className="mr-2" />}
              {isEditMode ? 'Configurar' : 'Configurar'}
            </button>

          </div>
        </div>


        {/* Barra de Ações (Botões) */}
        <div className="flex flex-wrap justify-between items-center gap-4 mb-6">
          {/* Botões Lado Esquerdo */}
          <div className="flex gap-2">
            {!isIntelipostView && !isMeliView && !isMagentoView && !isTiktokView && !isShopeeView && modelName !== 'nfe_rece_bidas' && canCreate && (
              <Link
                to={`/${modelName}/new`}
                className="flex items-center px-4 py-2 bg-green-600 text-white rounded-md shadow-sm hover:bg-green-700 text-sm font-medium"
              >
                <Plus size={16} className="mr-2" />
                {isEmailRulesView ? 'Nova Regra' : 'Novo'}
              </Link>
            )}

            {isEmailRulesView && (
              <button
                onClick={handleEmailConfigClick}
                disabled={isFetchingData}
                className="flex items-center px-4 py-2 bg-teal-600 text-white rounded-md shadow-sm hover:bg-teal-700 text-sm font-medium disabled:opacity-70 disabled:cursor-not-allowed"
              >
                <Settings size={16} className="mr-2" />
                Configurações
              </button>
            )}

            {isIntelipostView && (
              <button
                onClick={handleIntelipostConfigClick}
                disabled={isFetchingData}
                className="flex items-center px-4 py-2 bg-gray-800 text-white rounded-md shadow-sm hover:bg-gray-900 text-sm font-medium disabled:opacity-70 disabled:cursor-not-allowed"
              >
                {isFetchingData ? (
                  <Loader2 size={16} className="mr-2 animate-spin" />
                ) : (
                  <Settings size={16} className="mr-2" />
                )}
                Configurações
              </button>
            )}
            {/* BOTÃO CONFIG ML */}
            {isMeliView && (
              <button
                onClick={handleMeliConfigClick}
                className="flex items-center px-4 py-2 bg-yellow-500 text-white rounded-md hover:bg-yellow-600 font-medium"
              >
                <Settings size={16} className="mr-2" />
                Configurações ML
              </button>
            )}

            {/* BOTÕES DF-E */}
            {modelName === 'nfe_recebidas' && (
              <>
                <input
                  type="file"
                  id="xml-upload-input"
                  multiple
                  accept=".xml"
                  className="hidden"
                  onChange={handleXmlUpload}
                />
                <button
                  onClick={() => document.getElementById('xml-upload-input').click()}
                  className="flex items-center px-4 py-2 bg-green-600 text-white rounded-md shadow-sm hover:bg-green-700 text-sm font-medium"
                >
                  <FileCode size={16} className="mr-2" />
                  Importar XML
                </button>
                <button onClick={handleDfeSync} className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 font-medium">
                  <RefreshCw size={16} className={`mr-2 ${isFetchingData ? 'animate-spin' : ''}`} /> Sincronizar SEFAZ
                </button>
              </>
            )}

            {/* BOTÃO SINCRONIZAR ML */}
            {isMeliView && (
              <button
                onClick={handleMeliSyncClick}
                disabled={isFetchingData}
                className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 font-medium disabled:opacity-70"
              >
                <RefreshCw size={16} className={`mr-2 ${isFetchingData ? 'animate-spin' : ''}`} />
                Sincronizar
              </button>
            )}

            {/* BOTÃO CONFIG MAGENTO */}
            {isMagentoView && (
              <button
                onClick={handleMagentoConfigClick}
                className="flex items-center px-4 py-2 bg-orange-600 text-white rounded-md hover:bg-orange-700 font-medium"
              >
                <Settings size={16} className="mr-2" />
                Configurações Magento
              </button>
            )}

            {/* BOTÃO SINCRONIZAR MAGENTO */}
            {isMagentoView && (
              <button
                onClick={handleMagentoSyncClick}
                disabled={isFetchingData}
                className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 font-medium disabled:opacity-70"
              >
                <RefreshCw size={16} className={`mr-2 ${isFetchingData ? 'animate-spin' : ''}`} />
                Sincronizar Magento
              </button>
            )}

            {/* BOTÃO CONFIG TIKTOK */}
            {isTiktokView && (
              <button
                onClick={handleTiktokConfigClick}
                className="flex items-center px-4 py-2 bg-pink-600 text-white rounded-md hover:bg-pink-700 font-medium"
              >
                <Settings size={16} className="mr-2" />
                Configurações TikTok
              </button>
            )}

            {/* BOTÃO SINCRONIZAR TIKTOK */}
            {isTiktokView && (
              <button
                onClick={handleTiktokSyncClick}
                disabled={isFetchingData}
                className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 font-medium disabled:opacity-70"
              >
                <RefreshCw size={16} className={`mr-2 ${isFetchingData ? 'animate-spin' : ''}`} />
                Sincronizar
              </button>
            )}

            {/* BOTÃO CONFIG SHOPEE */}
            {isShopeeView && (
              <button
                onClick={handleShopeeConfigClick}
                className="flex items-center px-4 py-2 bg-orange-600 text-white rounded-md hover:bg-orange-700 font-medium"
              >
                <Settings size={16} className="mr-2" />
                Configurações Shopee
              </button>
            )}

            {/* BOTÃO SINCRONIZAR SHOPEE */}
            {isShopeeView && (
              <button
                onClick={handleShopeeSyncClick}
                disabled={isFetchingData}
                className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 font-medium disabled:opacity-70"
              >
                <RefreshCw size={16} className={`mr-2 ${isFetchingData ? 'animate-spin' : ''}`} />
                Sincronizar Shopee
              </button>
            )}

            {/* BOTÃO EXPORTAR CSV (Escondido para proxy views ML, Magento, TikTok e Shopee) */}
            {!isMeliView && !isMagentoView && !isTiktokView && !isShopeeView && canExport && (
              <button
                onClick={handleExportCSV}
                disabled={exportingFormat !== null || isFetchingData} // Desabilita se estiver exportando ou buscando dados
                className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-md shadow-sm hover:bg-blue-700 text-sm font-medium disabled:cursor-not-allowed"
              >
                {exportingFormat === 'generic' ? (
                  <Loader2 size={16} className="mr-2 animate-spin" />
                ) : (
                  <FileDown size={16} className="mr-2" />
                )}
                {exportingFormat === 'generic' ? 'Exportando...' : 'Exportar CSV'}
              </button>
            )}

            {/* Botão Visualizar Pedido */}
            {modelName === 'pedidos' && (
              <button
                type="button"
                onClick={handleOpenVisualizarModal}
                disabled={!selectedRowId || isFetchingDetails}
                className="flex items-center px-4 py-2 bg-gray-500 text-white rounded-md shadow-sm hover:bg-gray-600 text-sm font-medium disabled:cursor-not-allowed"
              >
                <Eye size={16} className="mr-2" />
                Visualizar
              </button>
            )}

          </div>

          {/* Ações de Seleção (Lado Direito) */}
          <div className="flex flex-wrap items-center gap-2">

            {/* BOTÃO INVENTÁRIO (Apenas para módulo estoque, em todas as abas) */}
            {modelName === 'estoque' && (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setIsInventarioModalOpen(true)}
                  className="flex items-center px-4 py-2 bg-gradient-to-r from-indigo-600 to-purple-600 text-white rounded-md shadow-sm hover:from-indigo-700 hover:to-purple-700 text-sm font-semibold"
                >
                  <ClipboardList size={16} className="mr-2" />
                  Realizar Inventário
                </button>

                {/* Novos botões de exportação vinculados à seleção */}
                {/* Novos botões de exportação vinculados à seleção */}
                <button
                  onClick={() => isInventorySelected && handleExportSelectedInventory('csv')}
                  className={`flex items-center px-4 py-2 text-white rounded-md shadow-sm text-sm font-medium transition-all ${isInventorySelected ? 'bg-emerald-600 hover:bg-emerald-700 cursor-pointer' : 'bg-emerald-600 cursor-not-allowed'
                    }`}
                  title={isInventorySelected ? "Exportar CSV do grupo selecionado" : "Selecione uma linha de inventário"}
                >
                  <Download size={16} className="mr-2" />
                  CSV
                </button>
                <button
                  onClick={() => isInventorySelected && handleExportSelectedInventory('pdf')}
                  className={`flex items-center px-4 py-2 text-white rounded-md shadow-sm text-sm font-medium transition-all ${isInventorySelected ? 'bg-rose-600 hover:bg-rose-700 cursor-pointer' : 'bg-rose-600 cursor-not-allowed'
                    }`}
                  title={isInventorySelected ? "Exportar PDF do grupo selecionado" : "Selecione uma linha de inventário"}
                >
                  <FileText size={16} className="mr-2" />
                  PDF
                </button>
              </div>
            )}

            {/* Botão Editar Atualizado */}
            {!isMeliView && !isMagentoView && !isTiktokView && !isShopeeView && canEdit && modelName !== 'estoque' && (
              <button
                onClick={handleEditClick}
                disabled={!selectedRowId} // Desabilitado se nada selecionado
                className="flex items-center px-4 py-2 bg-blue-500 text-white rounded-md shadow-sm hover:bg-blue-600 text-sm font-medium disabled:cursor-not-allowed"
              >
                <Edit size={16} className="mr-2" />
                Editar
              </button>
            )}

            {/* Novo Botão Deletar / Cancelar */}
            {!isMeliView && !isMagentoView && !isTiktokView && !isShopeeView && canDelete && modelName !== 'estoque' && (
              <button
                onClick={handleDeleteClick} // Chama a função que abre o modal
                disabled={!selectedRowId} // Desabilitado se nada selecionado
                className={`flex items-center px-4 py-2 text-white rounded-md shadow-sm text-sm font-medium disabled:cursor-not-allowed ${modelName === 'pedidos' ? 'bg-red-500 hover:bg-red-600' : 'bg-red-600 hover:bg-red-700'
                  }`}
              >
                {modelName === 'pedidos' ? <Ban size={16} className="mr-2" /> : <Trash2 size={16} className="mr-2" />}
                {modelName === 'pedidos' ? 'Cancelar' : 'Deletar'}
              </button>
            )}

            {/* BOTÕES DF-E */}
            {modelName === 'nfe_recebidas' && (
              <>
                <button onClick={handleManifestarCiencia} disabled={!selectedRowId} className="flex items-center px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 font-medium disabled:cursor-not-allowed">
                  <CheckCircle size={16} className="mr-2" /> Ciência da Operação
                </button>
                <button
                  onClick={handleDownloadXml}
                  disabled={!selectedRowId || isFetchingData}
                  className="flex items-center px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700 font-medium disabled:cursor-not-allowed"
                >
                  <FileCode size={16} className="mr-2" /> Baixar XML
                </button>
                <button onClick={() => setIsDfeImportModalOpen(true)} disabled={!selectedRowId} className="flex items-center px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 font-medium disabled:cursor-not-allowed">
                  <FileDown size={16} className="mr-2" /> Importar Nota
                </button>
              </>
            )}

            {/* BOTÃO IMPORTAR ML */}
            {isMeliView && (
              <button
                onClick={handleImportMeliOrder}
                disabled={selectedRowIds.length === 0 || isFetchingData}
                className="flex items-center px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 font-medium disabled:cursor-not-allowed"
              >
                <FileDown size={16} className="mr-2" />
                {selectedRowIds.length > 1 ? `Importar ${selectedRowIds.length} Pedidos` : 'Importar Pedido'}
              </button>
            )}

            {/* BOTÃO IMPORTAR MAGENTO */}
            {isMagentoView && (
              <button
                onClick={handleImportMagentoOrder}
                disabled={selectedRowIds.length === 0 || isFetchingData}
                className="flex items-center px-4 py-2 bg-orange-600 text-white rounded-md hover:bg-orange-700 font-medium disabled:cursor-not-allowed"
              >
                <FileDown size={16} className="mr-2" />
                {selectedRowIds.length > 1 ? `Importar ${selectedRowIds.length} Pedidos` : 'Importar Pedido'}
              </button>
            )}

            {/* BOTÃO IMPORTAR TIKTOK */}
            {isTiktokView && (
              <button
                onClick={handleImportTiktokOrder}
                disabled={selectedRowIds.length === 0 || isFetchingData}
                className="flex items-center px-4 py-2 bg-pink-600 text-white rounded-md hover:bg-pink-700 font-medium disabled:cursor-not-allowed"
              >
                <FileDown size={16} className="mr-2" />
                {selectedRowIds.length > 1 ? `Importar ${selectedRowIds.length} Pedidos` : 'Importar Pedido'}
              </button>
            )}

            {/* BOTÃO IMPORTAR SHOPEE */}
            {isShopeeView && (
              <button
                onClick={handleImportShopeeOrder}
                disabled={selectedRowIds.length === 0 || isFetchingData}
                className="flex items-center px-4 py-2 bg-orange-600 text-white rounded-md hover:bg-orange-700 font-medium disabled:cursor-not-allowed"
              >
                <FileDown size={16} className="mr-2" />
                {selectedRowIds.length > 1 ? `Importar ${selectedRowIds.length} Pedidos` : 'Importar Pedido'}
              </button>
            )}

            {/* BOTÃO GERAR RELATÓRIO (Apenas para módulo de relatórios) */}
            {modelName === 'relatorios' && (
              <div className="flex gap-2">
                <button
                  onClick={() => handleGenerateReport(selectedRowId, 'csv')}
                  disabled={!selectedRowId || exportingFormat !== null}
                  className="flex items-center px-4 py-2 bg-indigo-600 text-white rounded-md shadow-sm hover:bg-indigo-700 text-sm font-medium disabled:cursor-not-allowed"
                  title="Exportar CSV"
                >
                  {exportingFormat === 'csv' ? <Loader2 size={16} className="mr-2 animate-spin" /> : <FileDown size={16} className="mr-2" />}
                  CSV
                </button>
                <button
                  onClick={() => handleGenerateReport(selectedRowId, 'pdf')}
                  disabled={!selectedRowId || exportingFormat !== null}
                  className="flex items-center px-4 py-2 bg-red-600 text-white rounded-md shadow-sm hover:bg-red-700 text-sm font-medium disabled:cursor-not-allowed"
                  title="Exportar PDF"
                >
                  {exportingFormat === 'pdf' ? <Loader2 size={16} className="mr-2 animate-spin" /> : <FileText size={16} className="mr-2" />}
                  PDF
                </button>
                <button
                  onClick={() => handleGenerateReport(selectedRowId, 'xml')}
                  disabled={!selectedRowId || exportingFormat !== null || data.find(r => r.id === selectedRowId)?.modelo !== 'pedidos'}
                  className={`flex items-center px-4 py-2 bg-green-600 text-white rounded-md shadow-sm text-sm font-medium transition-colors ${!selectedRowId || exportingFormat !== null || data.find(r => r.id === selectedRowId)?.modelo !== 'pedidos'
                    ? 'cursor-not-allowed'
                    : 'hover:bg-green-700'
                    }`}
                  title="Exportar XMLs (apenas Pedidos)"
                >
                  {exportingFormat === 'xml' ? <Loader2 size={16} className="mr-2 animate-spin" /> : <FileCode size={16} className="mr-2" />}
                  XML
                </button>
              </div>
            )}

            {/* BOTÃO COTAR FRETE (Aparece apenas se modelName for pedidos e uma linha selecionada) */}
            {isIntelipostView && (
              <button
                onClick={() => handleOpenIntelipost(data.find(d => d.id === selectedRowId))}
                disabled={!selectedRowId || isFetchingData}
                className="flex items-center px-4 py-2 bg-teal-600 text-white rounded-md shadow-sm hover:bg-teal-700 text-sm font-medium disabled:cursor-not-allowed"
              >
                <Truck size={16} className="mr-2" />
                Cotar Frete
              </button>
            )}

            {/* BOTÃO BAIXA (Apenas para Contas) */}
            {modelName === 'contas' && (
              <button
                onClick={handleOpenBatchBaixa}
                disabled={selectedRowIds.length === 0}
                className="flex items-center px-4 py-2 bg-emerald-600 text-white rounded-md shadow-sm hover:bg-emerald-700 text-sm font-medium disabled:cursor-not-allowed"
              >
                <CheckCircle size={16} className="mr-2" />
                {selectedRowIds.length > 1 ? "Baixa em Lote" : "Baixar Conta"}
              </button>
            )}

            {/* BOTÕES DE STATUS RENDERIZADOS DINAMICAMENTE */}
            {
              statusChangeActions[modelName]?.map((action, index) => {
                // Só mostra o botão se o filtro de status atual bater
                if (action.currentStatus !== statusFilter) {
                  return null;
                }

                // Verifica permissão granular para a ação (se definida no JSON de permissões)
                // Ex: se o botão tem key 'faturar', verifica se 'faturar' está em userPermissions.acoes
                if (user?.perfil !== 'admin' && action.onClickHandler && !userPermissions.acoes?.includes(action.onClickHandler) && !userPermissions.acoes?.includes(action.key)) {
                  // Se a ação não estiver explicitamente permitida, esconde.
                  // Nota: Para ações genéricas de status, talvez precisemos mapear melhor.
                  // Por enquanto, vamos assumir que ações de status complexas (faturar, etiqueta) precisam de permissão explícita
                  // se quisermos restringir. Se não, deixe passar.

                  // Lista de ações críticas que exigem permissão explícita no JSON
                  const criticalActions = [
                    'programar',
                    'conferencia',
                    'imprimir_etiqueta_volume',
                    'faturamento',
                    'download_danfe',
                    'imprimir_etiqueta',
                    'cancelar_nfe',
                    'carta_correcao',
                    'devolucao'
                  ];
                  if (criticalActions.includes(action.onClickHandler)) {
                    return null;
                  }
                }

                const Icon = action.buttonIcon; // Pega o componente do ícone

                let onClickAction;
                if (action.onClickHandler === 'programar') {
                  onClickAction = handleOpenProgramacaoModal;
                } else if (action.onClickHandler === 'conferencia') {
                  onClickAction = () => handleOpenConferenciaModal(action);
                } else if (action.onClickHandler === 'faturamento') {
                  onClickAction = async () => {
                    if (selectedRowIds.length > 1) {
                      setIsBatchFaturamentoModalOpen(true);
                    } else {
                      // Busca detalhes completos antes de abrir
                      setIsFetchingDetails(true);
                      try {
                        const res = await api.get(`/generic/pedidos/${selectedRowId}`);
                        setPedidoParaFaturar(res.data);
                        setIsFaturamentoModalOpen(true);
                      } catch (err) {
                        toast.error("Erro ao buscar dados do pedido");
                      } finally {
                        setIsFetchingDetails(false);
                      }
                    }
                  };
                } else if (action.onClickHandler === 'download_danfe') {
                  onClickAction = () => {
                    const idsToUse = selectedRowIds.length > 0 ? selectedRowIds : (selectedRowId ? [selectedRowId] : []);
                    if (idsToUse.length === 0) return;
                    setDanfeModalIds(idsToUse);
                    setIsDanfeModalOpen(true);
                  };
                } else if (action.onClickHandler === 'imprimir_etiqueta') {
                  onClickAction = async () => {
                    try {
                      setIsFetchingData(true);
                      let response;
                      if (selectedRowIds.length > 1) {
                        response = await api.post(`/pedidos/etiqueta-lote`, { pedido_ids: selectedRowIds }, {
                          responseType: 'blob'
                        });
                      } else {
                        response = await api.get(`/pedidos/etiqueta/${selectedRowId}`, {
                          responseType: 'blob'
                        });
                      }
                      const url = window.URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }));
                      window.open(url, '_blank');
                      toast.success("Etiqueta gerada com sucesso!");
                    } catch (err) {
                      const msg = err.response?.data?.detail || "Erro ao gerar etiqueta de transporte.";
                      toast.error(msg);
                    } finally {
                      setIsFetchingData(false);
                    }
                  };
                } else if (action.onClickHandler === 'imprimir_etiqueta_volume') {
                  onClickAction = async () => {
                    try {
                      setIsFetchingData(true);
                      const response = await api.get(`/pedidos/etiqueta_volume/${selectedRowId}`, {
                        responseType: 'blob'
                      });
                      const url = window.URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }));
                      window.open(url, '_blank');
                      toast.success("Etiquetas de volume geradas com sucesso!");
                    } catch (err) {
                      const msg = err.response?.data?.detail || "Erro ao gerar etiquetas de volume.";
                      toast.error(msg);
                    } finally {
                      setIsFetchingData(false);
                    }
                  };
                } else if (action.onClickHandler === 'cancelar_nfe') {
                  onClickAction = handleOpenCancelNFeModal;
                } else if (action.onClickHandler === 'carta_correcao') {
                  onClickAction = handleOpenCCeModal;
                } else if (action.onClickHandler === 'devolucao') {
                  onClickAction = handleOpenDevolucaoModal;
                } else if (action.onClickHandler === 'complemento') {
                  onClickAction = handleOpenComplementoModal;
                } else {
                  // O padrão genérico
                  onClickAction = () => handleStatusChangeClick(action);
                }



                return (
                  <button
                    key={`${action.newStatus}-${index}`}
                    onClick={onClickAction} // <-- USA A AÇÃO CORRETA
                    // Desabilita se estiver buscando detalhes para o modal complexo
                    disabled={selectedRowIds.length === 0 || isFetchingData || isFetchingDetails || isFetchingComplementoDetails}
                    className={`flex items-center px-4 py-2 text-white rounded-md shadow-sm text-sm font-medium disabled:cursor-not-allowed ${action.buttonClasses}`}
                  >
                    {/* 7. MOSTRAR LOADING SE ESTIVER BUSCANDO DETALHES */}
                    {((isFetchingDetails && action.onClickHandler === 'programar') || (isFetchingComplementoDetails && action.onClickHandler === 'complemento')) ? (
                      <Loader2 size={16} className="mr-2 animate-spin" />
                    ) : (
                      <Icon size={16} className="mr-2" />
                    )}
                    {action.onClickHandler === 'faturamento' && selectedRowIds.length > 1
                      ? `Faturar em Lote`
                      : (action.newStatus === 'Despachado' && selectedRowIds.length > 1)
                        ? `Despachar em Lote`
                        : (selectedRowIds.length > 1 && !action.onClickHandler)
                          ? `${action.buttonLabel} em Lote`
                          : action.buttonLabel}
                  </button>
                );
              })
            }
          </div>
        </div>

        {/* Card Principal (Listagem) */}
        <div
          tabIndex="0"
          onKeyDown={handleKeyDown}
          className={`bg-white rounded-lg shadow-md overflow-hidden transition-opacity outline-none ${isFetchingData && data.length > 0 ? 'opacity-60' : 'opacity-100'
            }`}
        >
          {/* Tabela de Dados */}
          <div
            ref={tableContainerRef}
            className="overflow-x-auto"
            onDragOver={handleDragOverContainer}
            onDragLeave={stopAutoScroll}
            onDrop={(e) => {
              if (isEditMode) {
                e.preventDefault();
                e.stopPropagation();
              }
              stopAutoScroll();
            }}
          >
            <table className="w-full min-w-max">
              <thead className="bg-gray-50">
                <tr className="border-b border-gray-200">
                  {displayColumns.length === 0 && !isFetchingData && !loadingPreferences && (
                    <th className="px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider text-left">
                      {isEditMode ? 'Adicionar Campos à Tabela' : 'Sem Campos Selecionados'}
                    </th>
                  )}
                  {/* Colunas Dinâmicas com Pré-Visualização em Tempo Real */}
                  {displayColumns.map((colName, idx) => {
                    const field = fieldMetaMap.get(colName);
                    const isCurrency = field?.format_mask === 'currency';
                    const sortList = getSortArray(userPreferences.sort, hasIdSeq);
                    const targetCol = (hasIdSeq && colName === 'id') ? 'id_sequencial' : colName;
                    const sortIdx = sortList.findIndex(s => s.field === targetCol || (colName === 'id' && s.field === 'id_sequencial'));
                    const sort = sortIdx !== -1 ? sortList[sortIdx] : null;
                    const sortPriority = sortIdx !== -1 ? sortIdx + 1 : null;

                    const isDraggingThis = colName === draggedColName;
                    const hasCustomWidth = !!userPreferences.columnWidths?.[colName];

                    return (
                      <th
                        key={colName}
                        draggable={isEditMode}
                        onDragStart={(e) => handleColumnDragStart(e, colName)}
                        onDragOver={(e) => handleColumnDragOver(e, colName)}
                        onDrop={(e) => handleColumnDrop(e, colName)}
                        onDragEnd={handleColumnDragEnd}
                        onClick={() => { if (isEditMode) toggleSort(colName); }}
                        style={{
                          width: hasCustomWidth ? `${userPreferences.columnWidths[colName]}px` : undefined,
                          minWidth: hasCustomWidth ? `${userPreferences.columnWidths[colName]}px` : undefined,
                          maxWidth: hasCustomWidth ? `${userPreferences.columnWidths[colName]}px` : undefined
                        }}
                        className={`${hasCustomWidth ? 'px-2' : 'px-6'} py-4 text-sm font-semibold text-gray-600 uppercase tracking-wider relative text-left transition-colors duration-150 ${isEditMode ? 'cursor-grab active:cursor-grabbing hover:bg-gray-100 group' : 'text-gray-600'
                          } ${isDraggingThis
                            ? 'bg-blue-100/90 text-blue-900 border-2 border-dashed border-blue-500 shadow-lg scale-[0.98] opacity-80 z-20'
                            : ''
                          }`}
                      >
                        <div className="flex items-center gap-2 justify-between">
                          <div className="flex items-center gap-1 truncate">
                            {isEditMode && <GripVertical size={12} className="text-gray-300 group-hover:text-gray-400" />}
                            {isEditMode ? (
                              <input
                                type="text"
                                value={userPreferences.customColumnLabels?.[colName] ?? formatLabel(colName === 'id' ? 'ID' : colName === 'ja_importado' ? 'Importado' : (field?.label || colName))}
                                onChange={(e) => {
                                  const newLabels = {
                                    ...(userPreferences.customColumnLabels || {}),
                                    [colName]: e.target.value
                                  };
                                  setUserPreferences({ ...userPreferences, customColumnLabels: newLabels });
                                }}
                                onBlur={() => {
                                  handleSavePreferences(userPreferences);
                                }}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter') {
                                    e.target.blur();
                                  }
                                }}
                                className="bg-transparent border-b border-gray-300 focus:border-blue-500 focus:outline-none w-28 text-sm font-semibold text-gray-700 uppercase"
                                draggable={false}
                                onClick={(e) => e.stopPropagation()}
                                onMouseDown={(e) => e.stopPropagation()}
                                onDragStart={(e) => { e.preventDefault(); e.stopPropagation(); }}
                              />
                            ) : (
                              <span>
                                {userPreferences.customColumnLabels?.[colName] || formatLabel(colName === 'id' ? 'ID' : colName === 'ja_importado' ? 'Importado' : (field?.label || colName))}
                              </span>
                            )}
                          </div>

                          {isEditMode && (
                            <div className="flex items-center gap-1">
                              <button
                                type="button"
                                onClick={(e) => { e.stopPropagation(); toggleSort(colName); }}
                                className={`p-1 rounded hover:bg-gray-200 ${sort ? 'text-blue-600' : 'text-gray-300'}`}
                                title="Ordenar coluna"
                              >
                                <div className="flex items-center gap-0.5">
                                  {sort?.direction === 'desc' ? <ArrowDown size={14} /> : <ArrowUp size={14} className={!sort ? 'opacity-50' : ''} />}
                                  {sortPriority && sortList.length > 1 && (
                                    <span className="text-[10px] bg-blue-100 text-blue-800 rounded px-1 font-extrabold leading-none">
                                      {sortPriority}
                                    </span>
                                  )}
                                </div>
                              </button>
                              <button
                                type="button"
                                onClick={(e) => { e.stopPropagation(); removeColumn(colName); }}
                                className="p-1 rounded hover:bg-red-100 text-gray-300 hover:text-red-500"
                                title="Remover coluna"
                              >
                                <X size={14} />
                              </button>
                            </div>
                          )}
                        </div>

                        {/* Alça de Redimensionamento Drag-to-Resize */}
                        {isEditMode && (
                          <div
                            draggable={false}
                            onMouseDown={(e) => handleResizeStart(e, colName)}
                            onClick={(e) => e.stopPropagation()}
                            title="Arraste para ajustar a largura da coluna"
                            className="absolute right-0 top-0 bottom-0 w-3 h-full cursor-col-resize z-30 select-none hover:bg-blue-500/20 active:bg-blue-600/40 transition-colors group/resizer flex items-center justify-center"
                          >
                            <div className="w-1 h-full bg-transparent group-hover/resizer:bg-blue-500 transition-colors" />
                          </div>
                        )}
                      </th>
                    );
                  })}

                  {/* Botão Adicionar Coluna (Apenas em Modo Edição) */}
                  {isEditMode && (
                    <th className="px-2 py-2 w-10">
                      <Popover className="relative">
                        <Popover.Button className="p-1.5 bg-blue-600 text-white rounded-full hover:bg-blue-700 shadow-md focus:outline-none">
                          <Plus size={16} />
                        </Popover.Button>

                        <Transition
                          as={Fragment}
                          enter="transition ease-out duration-200"
                          enterFrom="opacity-0 translate-y-1"
                          enterTo="opacity-100 translate-y-0"
                          leave="transition ease-in duration-150"
                          leaveFrom="opacity-100 translate-y-0"
                          leaveTo="opacity-0 translate-y-1"
                        >
                          <Popover.Panel className="absolute right-0 z-50 mt-3 w-64 transform px-4 sm:px-0">
                            <div className="overflow-hidden rounded-lg shadow-lg ring-1 ring-black ring-opacity-5 bg-white">
                              <div className="p-3 border-b bg-gray-50">
                                <div className="relative">
                                  <Search className="absolute left-2 top-2.5 text-gray-400" size={14} />
                                  <input
                                    type="text"
                                    placeholder="Pesquisar campos..."
                                    className="w-full pl-8 pr-3 py-1.5 text-xs border rounded-md focus:ring-2 focus:ring-blue-500 outline-none"
                                    value={addColumnSearch}
                                    onChange={(e) => setAddColumnSearch(e.target.value)}
                                    autoFocus
                                  />
                                </div>
                              </div>
                              <div className="max-h-60 overflow-y-auto p-1">
                                {(() => {
                                  const availableFields = (metadata?.fields || [])
                                    .filter(f => f && f.name && f.name !== 'id' && f.name !== 'itens' && f.name !== 'retiradas_detalhadas' && f.name !== 'retiradas_detalhadas_json')
                                    .filter(f => !displayColumns.includes(f.name))
                                    .filter(f => {
                                      const label = f.label || formatLabel(f.name) || '';
                                      const name = f.name || '';
                                      const search = (addColumnSearch || '').toLowerCase();
                                      return label.toLowerCase().includes(search) || name.toLowerCase().includes(search);
                                    });

                                  if (availableFields.length === 0) {
                                    return (
                                      <div className="p-4 text-center text-xs text-gray-400 font-medium">
                                        Nenhum campo disponível para adicionar.
                                      </div>
                                    );
                                  }

                                  return availableFields.map(f => {
                                    const label = f.label || formatLabel(f.name);
                                    return (
                                      <button
                                        key={f.name}
                                        type="button"
                                        onClick={() => { addColumn(f.name); setAddColumnSearch(''); }}
                                        className="w-full text-left px-3 py-2 text-xs text-gray-700 hover:bg-blue-50 rounded transition-colors flex flex-col"
                                      >
                                        <span className="font-medium">{label}</span>
                                        <span className="text-[10px] text-gray-400 font-mono">{f.name}</span>
                                      </button>
                                    );
                                  });
                                })()}
                              </div>
                            </div>
                          </Popover.Panel>
                        </Transition>
                      </Popover>
                    </th>
                  )}
                </tr>
              </thead>

              {/* Corpo da Tabela */}
              <tbody className="bg-white">
                {isFetchingData && data.length === 0 ? (
                  <TableSkeleton columns={isEditMode ? [...displayColumns, ''] : displayColumns} rows={limit} />
                ) : error && data.length === 0 ? (
                  <tr style={{ height: `${limit * 53}px` }}>
                    <td colSpan={Math.max(1, displayColumns.length + (isEditMode ? 1 : 0))} className="px-6 py-12 text-center align-middle text-gray-500 bg-gray-50/20">
                      <div className="flex flex-col items-center justify-center gap-3 max-w-md mx-auto py-6">
                        <div className="p-3 bg-red-50 text-red-600 rounded-full shadow-sm">
                          <AlertCircle size={24} />
                        </div>
                        <h3 className="text-base font-bold text-gray-800 tracking-tight">
                          {isShopeeView ? 'Shopee Não Autorizada' : isMeliView ? 'Mercado Livre Não Autorizado' : isTiktokView ? 'TikTok Shop Não Autorizado' : 'Erro ao Carregar Dados'}
                        </h3>
                        <p className="text-xs text-red-600 max-w-sm leading-relaxed font-medium">
                          {error}
                        </p>
                        {isShopeeView && (
                          <button
                            type="button"
                            onClick={handleShopeeSyncClick}
                            className="mt-2 px-4 py-2 bg-orange-600 hover:bg-orange-700 text-white rounded-md text-xs font-semibold shadow-sm transition-colors flex items-center gap-2"
                          >
                            <RefreshCw size={14} />
                            Conectar / Sincronizar Shopee
                          </button>
                        )}
                        {isMeliView && (
                          <button
                            type="button"
                            onClick={handleMeliSyncClick}
                            className="mt-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-xs font-semibold shadow-sm transition-colors flex items-center gap-2"
                          >
                            <RefreshCw size={14} />
                            Conectar / Sincronizar Mercado Livre
                          </button>
                        )}
                        {isMagentoView && (
                          <button
                            type="button"
                            onClick={handleMagentoSyncClick}
                            className="mt-2 px-4 py-2 bg-orange-600 hover:bg-orange-700 text-white rounded-md text-xs font-semibold shadow-sm transition-colors flex items-center gap-2"
                          >
                            <RefreshCw size={14} />
                            Conectar / Sincronizar Magento
                          </button>
                        )}
                        {isTiktokView && (
                          <button
                            type="button"
                            onClick={handleTiktokSyncClick}
                            className="mt-2 px-4 py-2 bg-pink-600 hover:bg-pink-700 text-white rounded-md text-xs font-semibold shadow-sm transition-colors flex items-center gap-2"
                          >
                            <RefreshCw size={14} />
                            Conectar / Sincronizar TikTok
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ) : displayColumns.length === 0 && !loadingPreferences ? (
                  <tr style={{ height: `${limit * 53}px` }}>
                    <td colSpan={100} className="px-6 py-12 text-center align-middle text-gray-500 bg-gray-50/20">
                      <div className="flex flex-col items-center justify-center gap-3 max-w-md mx-auto py-6">
                        <div className="p-3 bg-blue-50 text-blue-600 rounded-full shadow-sm">
                          <SlidersHorizontal size={24} />
                        </div>
                        <h3 className="text-base font-bold text-gray-800 tracking-tight">Nenhum campo selecionado</h3>
                        <p className="text-xs text-gray-500 max-w-sm leading-relaxed">
                          {isEditMode
                            ? 'Sua tabela não possui nenhum campo visível. Clique no botão "+" no canto superior direito para adicionar os campos desejados.'
                            : 'Sua tabela está sem campos visíveis no momento. Clique no botão abaixo para configurar quais campos deseja visualizar.'}
                        </p>
                        {!isEditMode && (
                          <button
                            type="button"
                            onClick={() => setIsEditMode(true)}
                            className="mt-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-xs font-semibold shadow-sm transition-colors flex items-center gap-2"
                          >
                            <SlidersHorizontal size={14} />
                            Configurar Tabela
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ) : data.length === 0 ? (
                  <tr style={{ height: `${limit * 53}px` }}>
                    <td colSpan={Math.max(1, displayColumns.length + (isEditMode ? 1 : 0))} className="px-6 py-4 text-center align-middle text-gray-500">
                      Nenhum registro encontrado.
                    </td>
                  </tr>
                ) : (
                  (() => {
                    const renderCellContent = (item, colName) => {
                      if (!colName) return null; // Proteção contra colName nulo

                      let value = item[colName];
                      const field = fieldMetaMap.get(colName);

                      // 1. Tenta resolver relacionamento (FK) primeiro para garantir o nome amigável
                      let relationProp = colName;
                      if (relationProp.startsWith('id_')) relationProp = relationProp.substring(3);
                      else if (relationProp.endsWith('_id')) relationProp = relationProp.slice(0, -3);

                      if (item[relationProp] && typeof item[relationProp] === 'object') {
                        const possibleLabels = [field?.foreign_key_label_field, 'nome_razao', 'nome', 'descricao', 'razao_social', 'titulo'];
                        for (const label of possibleLabels) {
                          if (label && item[relationProp][label] !== undefined) {
                            value = item[relationProp][label];
                            break;
                          }
                        }
                      }

                      if (colName === 'id_sequencial') {
                        return <span className="font-semibold text-gray-700">{value ?? item.id}</span>;
                      }

                      if (colName === 'trigger' && modelName === 'email_regras' && value) {
                        const parts = String(value).split('→');
                        return (
                          <div className="flex items-center gap-1.5">
                            {parts.map((p, idx) => (
                              <React.Fragment key={idx}>
                                <span className={`px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-tight ${idx === 0 ? 'bg-gray-100 text-gray-600' : 'bg-teal-100 text-teal-700'
                                  }`}>
                                  {p.trim()}
                                </span>
                                {idx < parts.length - 1 && <span className="text-gray-300 font-bold">→</span>}
                              </React.Fragment>
                            ))}
                          </div>
                        );
                      }

                      if (modelName === 'estoque' && (colName === 'custo' || colName === 'valor_total')) {
                        return <span className="font-medium text-gray-900">{formatCurrency(value || 0)}</span>;
                      }

                      if (colName === 'ja_importado') {
                        return <BooleanDisplay value={value} trueLabel="Importado" falseLabel="Não Importado" trueColor="blue" falseColor="gray" />;
                      }

                      if (colName === 'tipo_documento' && modelName === 'nfe_recebidas') {
                        let docLabel = value; let bgColor = 'bg-gray-100'; let textColor = 'text-gray-800'; let borderColor = 'border-gray-200';
                        if (String(value) === 'nfeProc') { docLabel = 'NFe Completa'; bgColor = 'bg-green-100'; textColor = 'text-green-800'; borderColor = 'border-green-300'; }
                        else if (String(value) === 'resNFe') { docLabel = 'Resumo NFe'; bgColor = 'bg-blue-100'; textColor = 'text-blue-800'; borderColor = 'border-blue-300'; }
                        else if (String(value).includes('210210')) { docLabel = 'Ciência da Operação'; bgColor = 'bg-purple-100'; textColor = 'text-purple-800'; borderColor = 'border-purple-300'; }
                        else if (String(value).includes('110111')) { docLabel = 'Cancelamento'; bgColor = 'bg-red-100'; textColor = 'text-red-800'; borderColor = 'border-red-300'; }
                        else if (String(value).includes('Evento')) { const evCode = String(value).split('_').pop(); docLabel = `Evento (${evCode})`; bgColor = 'bg-orange-100'; textColor = 'text-orange-800'; borderColor = 'border-orange-300'; }
                        return <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium border ${bgColor} ${textColor} ${borderColor}`}>{docLabel}</span>;
                      }

                      if (colName === 'tipo_conta') {
                        const label = (field?.options || []).find(opt => String(opt.value) === String(value))?.label || value;
                        const isReceber = String(value) === 'A Receber'; const isPagar = String(value) === 'A Pagar';
                        return <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium border ${isReceber ? 'bg-green-100 text-green-800 border-green-300' : isPagar ? 'bg-red-100 text-red-800 border-red-300' : 'bg-gray-100 text-gray-800 border-gray-200'}`}>{label}</span>;
                      }

                      if (colName === 'situacao') {
                        if (modelName === 'contas') {
                          const label = (field?.options || []).find(opt => String(opt.value) === String(value))?.label || value;
                          let bgColor = 'bg-gray-100'; let textColor = 'text-gray-800'; let borderColor = 'border-gray-200';
                          if (String(value) === 'Pago') { bgColor = 'bg-green-100'; textColor = 'text-green-800'; borderColor = 'border-green-300'; }
                          else if (String(value) === 'Vencido') { bgColor = 'bg-red-100'; textColor = 'text-red-800'; borderColor = 'border-red-300'; }
                          else if (String(value) === 'Cancelado') { bgColor = 'bg-purple-100'; textColor = 'text-purple-800'; borderColor = 'border-purple-300'; }
                          return <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium border ${bgColor} ${textColor} ${borderColor}`}>{label}</span>;
                        }
                        if (modelName === 'pedidos') {
                          const label = (field?.options || []).find(opt => String(opt.value) === String(value))?.label || value;
                          let bgColor = 'bg-gray-100'; let textColor = 'text-gray-800'; let borderColor = 'border-gray-200';
                          if (String(value) === 'Cancelado') { bgColor = 'bg-red-100'; textColor = 'text-red-800'; borderColor = 'border-red-300'; }
                          return <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium border ${bgColor} ${textColor} ${borderColor}`}>{label}</span>;
                        }
                        if (modelName === 'estoque') {
                          const colors = { 'Inventário': 'bg-indigo-100 text-indigo-800 border-indigo-200', 'Entrada': 'bg-green-100 text-green-800 border-green-200', 'Saída': 'bg-red-100 text-red-800 border-red-200' };
                          return <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium border ${colors[value] || 'bg-gray-100 text-gray-800 border-gray-200'}`}>{value}</span>;
                        }
                      }

                      if (colName === 'data_entrega' && modelName === 'pedidos') {
                        if (!value) return "Não informado";
                        const dataInicioStr = item.data_pedido || item.data_orcamento || (item.criado_em ? item.criado_em.split('T')[0] : null);
                        if (!dataInicioStr) return "Não informado";

                        const date1 = new Date(dataInicioStr + 'T00:00:00');
                        const date2 = new Date(value + 'T00:00:00');
                        if (isNaN(date1.getTime()) || isNaN(date2.getTime())) return "Não informado";
                        if (date1 > date2) return "0 dias úteis";

                        let count = 0;
                        let curDate = new Date(date1.getTime());
                        while (curDate < date2) {
                          curDate.setDate(curDate.getDate() + 1);
                          const dayOfWeek = curDate.getDay();
                          if (dayOfWeek !== 0 && dayOfWeek !== 6) {
                            count++;
                          }
                        }
                        return `${count} dias úteis`;
                      }

                      // 3. Formatações por tipo de campo
                      if (field?.type === 'boolean') return <BooleanDisplay value={value} />;
                      if (field?.format_mask === 'currency') return <span className="font-medium text-gray-900">{formatCurrency(value)}</span>;
                      if (field?.type === 'datetime') return <span className="text-gray-500">{formatDate(value)}</span>;

                      if (field?.type === 'select' || field?.component === 'creatable_select') {
                        const label = (field.options || []).find(opt => String(opt.value) === String(value))?.label;
                        if (label) value = label;
                      }

                      // Proteção final para objetos
                      if (typeof value === 'object' && value !== null && !React.isValidElement(value)) {
                        return <span className="text-gray-400 text-xs italic">{`[Dados: ${Object.keys(value).join(', ')}]`}</span>;
                      }

                      const isPassword = field?.ui_type === 'password' || colName.toLowerCase().includes('senha') || colName.toLowerCase().includes('password');
                      return isPassword ? '*********' : formatDisplayValue(value);
                    };

                    const renderRow = (item, index) => {
                      const rowId = item.id ?? item.order_sn ?? item.id_sequencial;
                      return (
                        <tr
                          key={rowId}
                          onClick={(e) => handleRowClick(e, rowId, index)}
                          onDoubleClick={() => {
                            if (!isMeliView && !isMagentoView && !isShopeeView && !isTiktokView && modelName !== 'estoque') {
                              const targetId = item.id_sequencial ?? rowId;
                              navigate(`/${modelName}/edit/${targetId}`);
                            }
                          }}
                          style={{ height: '53px' }}
                          className={`border-b border-gray-200 cursor-pointer ${(modelName === 'estoque' && statusFilter === 'Inventário')
                            ? 'hover:bg-gray-50' // Desabilita destaque de seleção individual no inventário
                            : selectedRowIds.includes(rowId) ? 'bg-blue-100' : 'hover:bg-gray-50'
                            }`}
                        >
                        {displayColumns.map((colName) => {
                          const isDraggingCell = colName === draggedColName;
                          const hasCustomWidth = !!userPreferences.columnWidths?.[colName];
                          return (
                            <td
                              key={colName}
                              style={{
                                width: hasCustomWidth ? `${userPreferences.columnWidths[colName]}px` : undefined,
                                minWidth: hasCustomWidth ? `${userPreferences.columnWidths[colName]}px` : undefined,
                                maxWidth: hasCustomWidth ? `${userPreferences.columnWidths[colName]}px` : undefined
                              }}
                              className={`${hasCustomWidth ? 'px-2' : 'px-6'} py-0 whitespace-nowrap text-sm text-gray-700 transition-colors duration-150 ${hasCustomWidth ? 'truncate' : ''} ${isDraggingCell
                                ? 'bg-blue-50/60 font-medium text-blue-900 border-x border-blue-200'
                                : ''
                                }`}
                            >
                              {renderCellContent(item, colName)}
                            </td>
                          );
                        })}
                        {isEditMode && <td className="bg-gray-50/30"></td>}
                      </tr>
                    );

                    const totalRowsRendered = (groupedData
                      ? groupedData.reduce((acc, g) => acc + 1 + g.itens.length, 0)
                      : data.length) + (hasTotalsField && data.length > 0 ? 1 : 0);
                    const emptyRowsCount = Math.max(0, limit - totalRowsRendered);

                    return (
                      <>
                        {groupedData ? (
                          groupedData.map(group => (
                            <Fragment key={group.key}>
                              <tr
                                className={`cursor-pointer transition-colors group/header ${selectedGroupKey === group.key ? 'bg-indigo-100 border-indigo-300' : 'bg-indigo-50/50 hover:bg-indigo-100/70 border-indigo-100'
                                  }`}
                                onClick={() => setSelectedGroupKey(group.key === selectedGroupKey ? null : group.key)}
                                title="Clique para selecionar este inventário"
                              >
                                <td colSpan={displayColumns.length + (isEditMode ? 1 : 0)} className="px-6 py-2 border-y">
                                  <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-3">
                                      <div className={`p-1 rounded-full ${selectedGroupKey === group.key ? 'bg-indigo-500 text-white' : 'bg-indigo-100 text-indigo-500'}`}>
                                        <Calendar size={14} />
                                      </div>
                                      <span className={`font-bold text-sm ${selectedGroupKey === group.key ? 'text-indigo-900' : 'text-indigo-800'}`}>
                                        Inventário em {formatDate(group.data_hora)}
                                      </span>
                                      <span className="text-[10px] bg-white/50 text-indigo-700 px-2 py-0.5 rounded-full border border-indigo-200 font-bold uppercase">
                                        {group.itens.length} Movimentações
                                      </span>
                                    </div>
                                    <div className="flex items-center gap-2">
                                      {selectedGroupKey === group.key ? (
                                        <span className="text-[10px] font-bold text-indigo-600 uppercase flex items-center gap-1">
                                          <Check size={12} /> Selecionado
                                        </span>
                                      ) : (
                                        <span className="text-[10px] font-medium text-indigo-400 uppercase opacity-0 group-hover/header:opacity-100 transition-opacity">
                                          Clique para selecionar
                                        </span>
                                      )}
                                    </div>
                                  </div>
                                </td>
                              </tr>
                              {group.itens.map((item, idx) => renderRow(item, idx))}
                            </Fragment>
                          ))
                        ) : (
                          data.map((item, idx) => renderRow(item, idx))
                        )}

                        {/* Linhas vazias para preencher o card (sem bordas internas) */}
                        {data.length > 0 && [...Array(emptyRowsCount)].map((_, i) => (
                          <tr key={`empty-${i}`} style={{ height: '53px' }}>
                            {displayColumns.map((colName) => {
                              const hasCustomWidth = !!userPreferences.columnWidths?.[colName];
                              return (
                                <td
                                  key={`empty-${i}-${colName}`}
                                  style={{
                                    width: hasCustomWidth ? `${userPreferences.columnWidths[colName]}px` : undefined,
                                    minWidth: hasCustomWidth ? `${userPreferences.columnWidths[colName]}px` : undefined,
                                    maxWidth: hasCustomWidth ? `${userPreferences.columnWidths[colName]}px` : undefined
                                  }}
                                  className={`${hasCustomWidth ? 'px-2' : 'px-6'} whitespace-nowrap text-sm`}
                                >
                                  &nbsp;
                                </td>
                              );
                            })}
                            {isEditMode && <td className="bg-gray-50/30"></td>}
                          </tr>
                        ))}

                        {/* Rodapé de Totais (Agora dentro do tbody para ocupar a última linha) */}
                        {hasTotalsField && data.length > 0 && (
                          <tr className="bg-gray-50 border-t-2 border-gray-200 font-bold">
                            {displayColumns.map((colName, idx) => {
                              const field = fieldMetaMap.get(colName);
                              const isCurrency = field?.format_mask === 'currency';

                              let content = '';
                              if (totals && totals[colName] !== undefined && totals[colName] !== null) {
                                content = isCurrency ? formatCurrency(totals[colName]) : totals[colName];
                              } else if (idx === 0) {
                                content = 'TOTAIS';
                              }

                              return (
                                <td
                                  key={`total-${colName}`}
                                  className="px-6 py-3 whitespace-nowrap text-sm text-gray-900 text-left"
                                >
                                  {content}
                                </td>
                              );
                            })}
                            {isEditMode && <td className="bg-gray-50/30"></td>}
                          </tr>
                        )}
                      </>
                    );
                  })()
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Paginação - só renderiza quando há mais de uma página */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between mt-6">
            {/* Total de registros */}
            {totalCount > 0 ? (
              <span className="text-sm text-gray-500">
                Mostrando <span className="font-semibold text-gray-700">{((page - 1) * effectiveLimit) + 1}–{Math.min(page * effectiveLimit, totalCount)}</span> de <span className="font-semibold text-gray-700">{totalCount}</span> registros
              </span>
            ) : (
              <span />
            )}

            {/* Controles de navegação */}
            <div className="flex items-center gap-1">
              {/* Botão Anterior */}
              <button
                onClick={() => setPage(p => p - 1)}
                disabled={page <= 1 || isFetchingData}
                className="flex items-center gap-1 px-3 py-2 rounded-lg text-sm font-medium text-gray-600 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft size={16} />
                Anterior
              </button>

              {/* Páginas numeradas */}
              <div className="flex items-center gap-1 mx-1">
                {(() => {
                  const pages = [];
                  const delta = 2;
                  const left = Math.max(2, page - delta);
                  const right = Math.min(totalPages - 1, page + delta);

                  // Primeira página sempre
                  pages.push(1);

                  // Ellipsis esquerdo
                  if (left > 2) pages.push('...');

                  // Páginas ao redor da atual
                  for (let i = left; i <= right; i++) pages.push(i);

                  // Ellipsis direito
                  if (right < totalPages - 1) pages.push('...');

                  // Última página sempre (se > 1)
                  if (totalPages > 1) pages.push(totalPages);

                  return pages.map((p, idx) =>
                    p === '...' ? (
                      <span key={`ellipsis-${idx}`} className="px-2 text-gray-400 text-sm select-none">…</span>
                    ) : (
                      <button
                        key={p}
                        onClick={() => setPage(p)}
                        disabled={isFetchingData}
                        className={`w-9 h-9 rounded-lg text-sm font-medium transition-colors ${
                          page === p
                            ? 'bg-teal-600 text-white shadow-sm'
                            : 'text-gray-600 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed'
                        }`}
                      >
                        {p}
                      </button>
                    )
                  );
                })()}
              </div>

              {/* Botão Próxima */}
              <button
                onClick={() => setPage(p => p + 1)}
                disabled={page >= totalPages || isFetchingData}
                className="flex items-center gap-1 px-3 py-2 rounded-lg text-sm font-medium text-gray-600 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Próxima
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}

        {/* Quando há apenas uma página, exibe só o contador de registros */}
        {totalPages <= 1 && totalCount > 0 && (
          <div className="flex items-center justify-end mt-4">
            <span className="text-sm text-gray-500">
              <span className="font-semibold text-gray-700">{totalCount}</span> {totalCount === 1 ? 'registro' : 'registros'}
            </span>
          </div>
        )}

        {/* --- MODAL --- */}
        <Modal
          isOpen={isModalOpen}
          onClose={handleCloseModal} // Fechar não reseta mais o ID
          onConfirm={handleConfirmDelete} // Confirmar faz a ação e reseta o ID
          title={modelName === 'pedidos' ? "Confirmar Cancelamento" : "Confirmar Exclusão"}
          variant="danger"
          confirmText={modelName === 'pedidos' ? "Cancelar Pedido" : "Excluir"}
        >
          {modelName === 'pedidos'
            ? "Tem certeza que deseja cancelar este pedido? A situação será alterada para 'Cancelado'."
            : "Tem certeza que deseja excluir este item? Esta ação não pode ser desfeita."
          }
        </Modal>

        {/* 5. MODAL GENÉRICO DE MUDANÇA DE STATUS (ÚNICO E LOTE) */}
        <Modal
          isOpen={!!actionToConfirm} // Abre se actionToConfirm não for null
          onClose={handleCloseStatusModal}
          onConfirm={handleConfirmStatusChange}
          title={
            (selectedRowIds.length > 1 && actionToConfirm?.newStatus === 'Despachado')
              ? "Despachar Pedidos em Lote"
              : selectedRowIds.length > 1
                ? `${actionToConfirm?.buttonLabel || 'Alterar Status'} em Lote`
                : (actionToConfirm?.modalTitle || "Confirmar Ação")
          }
          variant="info"
          confirmText={
            selectedRowIds.length > 1
              ? (actionToConfirm?.newStatus === 'Despachado' ? "Sim, Despachar Todos" : "Confirmar em Lote")
              : (actionToConfirm?.modalConfirmText || "Confirmar")
          }
        >
          {selectedRowIds.length > 1
            ? (actionToConfirm?.newStatus === 'Despachado'
              ? `Deseja marcar os ${selectedRowIds.length} pedidos selecionados como Despachado? Isso indica que eles saíram para entrega.`
              : `Deseja alterar a situação dos ${selectedRowIds.length} itens selecionados para "${actionToConfirm?.newStatus}"?`
            )
            : (actionToConfirm?.modalDescription || "Você tem certeza?")
          }
        </Modal>

        <ProgramacaoPedidoModal
          isOpen={isProgramacaoModalOpen}
          onClose={handleCloseProgramacaoModal}
          onSave={handleSaveProgramacao}
          pedido={currentPedidoDetails} // Passa o pedido completo
        // O modal vai mostrar seu próprio loading se 'pedido' for nulo
        />

        {/* NOVO MODAL DE CONFERÊNCIA (PRODUZIR / EMBALAR) */}
        <ConferenciaPedidoModal
          isOpen={isConferenciaModalOpen}
          onClose={handleCloseConferenciaModal}
          onConfirm={handleConfirmConferencia}
          pedido={currentPedidoDetails}
          title={conferenciaConfig?.modalTitle}
          confirmText={conferenciaConfig?.modalConfirmText}
          variant={conferenciaConfig?.modalVariant}
          showVolumes={conferenciaConfig?.showVolumes}
        />

        {/* MODAL DE FATURAMENTO */}
        <FaturamentoModal
          isOpen={isFaturamentoModalOpen}
          onClose={() => setIsFaturamentoModalOpen(false)}
          pedido={pedidoParaFaturar}
          onConfirm={handleSaveFaturamento}
        />

        {/* MODAL DE FATURAMENTO EM LOTE */}
        <Modal
          isOpen={isBatchFaturamentoModalOpen}
          onClose={() => setIsBatchFaturamentoModalOpen(false)}
          onConfirm={handleConfirmBatchFaturamento}
          title="Faturamento em Lote"
          variant="info"
          confirmText="Confirmar Faturamento"
        >
          Você selecionou <strong>{selectedRowIds.length}</strong> pedidos para faturar.
          Deseja emitir as Notas Fiscais agora? O sistema utilizará as regras tributárias automáticas para cada pedido.
        </Modal>

        {/* MODAL DE VISUALIZAÇÃO DE PEDIDO */}
        {isVisualizarModalOpen && (
          <ModalVisualizarPedido pedido={pedidoParaVisualizar} onClose={handleCloseVisualizarModal} />
        )}


        <ModalCotacaoIntelipost
          isOpen={isIntelipostModalOpen}
          onClose={() => setIsIntelipostModalOpen(false)}
          pedido={pedidoParaCotar}
          onSelectFrete={handleFreteSelecionado}
        />

        <ModalImportacaoDfe
          isOpen={isDfeImportModalOpen}
          onClose={() => setIsDfeImportModalOpen(false)}
          notaId={selectedRowId}
          onSuccess={() => setRefreshTrigger(prev => prev + 1)}
        />

        <Modal
          isOpen={isImportModalOpen}
          onClose={() => setIsImportModalOpen(false)}
          onConfirm={confirmImportOrder}
          title="Importar Pedido"
          variant="info"
          confirmText="Sim, Importar"
        >
          {ordersToImport.length > 1
            ? `Deseja importar os ${ordersToImport.length} pedidos selecionados do ${isMeliView ? "Mercado Livre" : isTiktokView ? "Tiktok Shop" : "Magento"} para o ERP?`
            : `Deseja importar este pedido do ${isMeliView ? "Mercado Livre" : isTiktokView ? "Tiktok Shop" : "Magento"} para o ERP?`
          }
        </Modal>

        {/* MODAIS DE AUTORIZAÇÃO (ML E TIKTOK) */}
        <Modal
          isOpen={isMeliAuthModalOpen}
          onClose={() => setIsMeliAuthModalOpen(false)}
          onConfirm={() => { window.location.href = pendingAuthUrl; }}
          title="Conectar ao Mercado Livre"
          variant="info"
          confirmText="Fazer Login"
        >
          Não há uma conexão ativa com o Mercado Livre. Deseja fazer login agora para sincronizar seus pedidos?
        </Modal>

        <Modal
          isOpen={isTiktokAuthModalOpen}
          onClose={() => setIsTiktokAuthModalOpen(false)}
          onConfirm={() => { window.location.href = pendingAuthUrl; }}
          title="Conectar ao Tiktok Shop"
          variant="info"
          confirmText="Fazer Login"
        >
          Não há uma conexão ativa com o Tiktok Shop. Deseja fazer login agora para sincronizar seus pedidos?
        </Modal>

        {/* MODAL DE CANCELAMENTO DE NFE */}
        <Modal
          isOpen={isCancelNFeModalOpen}
          onClose={() => setIsCancelNFeModalOpen(false)}
          onConfirm={handleConfirmCancelNFe}
          title="Cancelar Nota Fiscal"
          variant="danger"
          confirmText="Confirmar Cancelamento"
        >
          <div className="space-y-3">
            <p className="text-sm text-gray-600">
              Informe a justificativa para o cancelamento da NFe junto à SEFAZ (Mínimo 15 caracteres).
            </p>
            <textarea
              className="w-full border border-gray-300 rounded-md p-2 text-sm focus:ring-red-500 focus:border-red-500"
              rows={3}
              placeholder="Ex: Erro na digitação dos valores dos produtos..."
              value={cancelJustification}
              onChange={(e) => setCancelJustification(e.target.value)}
            />
          </div>
        </Modal>

        {/* MODAL DE CARTA DE CORREÇÃO (CC-e) */}
        <Modal
          isOpen={isCCeModalOpen}
          onClose={() => setIsCCeModalOpen(false)}
          onConfirm={handleConfirmCCe}
          title="Carta de Correção (CC-e)"
          variant="info"
          confirmText="Enviar Correção"
        >
          <div className="space-y-3">
            <p className="text-sm text-gray-600">
              Digite a correção a ser considerada. A correção mais recente substitui as anteriores.
              (Mínimo 15 caracteres).
            </p>
            <textarea
              className="w-full border border-gray-300 rounded-md p-2 text-sm focus:ring-blue-500 focus:border-blue-500"
              rows={4}
              placeholder="Ex: Onde se lê peso bruto 10kg, leia-se peso bruto 12kg..."
              value={cceText}
              onChange={(e) => setCceText(e.target.value)}
            />
          </div>
        </Modal>

        {/* MODAL DE DEVOLUÇÃO */}
        <Modal
          isOpen={isDevolucaoModalOpen}
          onClose={() => setIsDevolucaoModalOpen(false)}
          onConfirm={handleConfirmDevolucao}
          title="Gerar Devolução de NFe"
          variant="danger"
          confirmText="Sim, Gerar Devolução"
        >
          Deseja gerar uma nota de devolução para este pedido? Isso duplicará o pedido e emitirá uma nova NFe.
        </Modal>

        {/* MODAL DE COMPLEMENTO */}
        <Modal
          isOpen={isComplementoModalOpen}
          onClose={() => setIsComplementoModalOpen(false)}
          onConfirm={handleConfirmComplemento}
          title="Gerar Nota Complementar"
          variant="info"
          confirmText="Sim, Gerar Complemento"
        >
          Deseja gerar uma nota complementar para este pedido? Isso duplicará o pedido na situação Faturamento com o tipo de operação alterado para Complementar e a chave original referenciada.
        </Modal>

        {/* MODAL DE BAIXA EM LOTE */}
        <Modal
          isOpen={isBatchBaixaModalOpen}
          onClose={() => setIsBatchBaixaModalOpen(false)}
          onConfirm={handleConfirmBatchBaixa}
          title={selectedRowIds.length > 1 ? "Baixa em Lote" : "Baixar Conta"}
          variant="info"
          confirmText="Confirmar Baixa"
        >
          <div className="space-y-4">
            <p className="text-sm text-gray-600">
              {selectedRowIds.length > 1 ? (
                <>Você está baixando <strong>{selectedRowIds.length}</strong> contas simultaneamente.</>
              ) : (
                <>Você está baixando a conta: <strong>{selectedItemName}</strong>.</>
              )}
              {" "}Selecione o caixa/banco de destino:
            </p>
            <div>
              <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Caixa / Banco</label>
              <select
                value={selectedCaixa}
                onChange={(e) => setSelectedCaixa(e.target.value)}
                className="w-full border border-gray-300 rounded-md p-2 text-sm focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="">Selecione...</option>
                {caixaOptions.map(opt => (
                  <option key={opt.id} value={opt.valor}>{opt.valor}</option>
                ))}
              </select>
            </div>
          </div>
        </Modal>



        {/* MODAL SELEÇÃO DE DANFE (COMPLETA OU SIMPLIFICADA) */}
        <Transition.Root show={isDanfeModalOpen} as={React.Fragment}>
          <Dialog as="div" className="relative z-50" onClose={() => setIsDanfeModalOpen(false)}>
            <Transition.Child as={React.Fragment} enter="ease-out duration-300" enterFrom="opacity-0" enterTo="opacity-100" leave="ease-in duration-200" leaveFrom="opacity-100" leaveTo="opacity-0">
              <div className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity" />
            </Transition.Child>
            <div className="fixed inset-0 z-10 overflow-y-auto">
              <div className="flex min-h-full items-center justify-center p-4 text-center sm:p-0">
                <Transition.Child as={React.Fragment} enter="ease-out duration-300" enterFrom="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95" enterTo="opacity-100 translate-y-0 sm:scale-100" leave="ease-in duration-200" leaveFrom="opacity-100 translate-y-0 sm:scale-100" leaveTo="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95">
                  <Dialog.Panel className="relative transform overflow-hidden rounded-xl bg-white text-left shadow-2xl transition-all sm:my-8 sm:w-full sm:max-w-md">
                    <div className="bg-white px-4 pt-5 pb-4 sm:p-6">
                      <div className="flex items-center justify-between mb-4">
                        <Dialog.Title as="h3" className="text-lg font-bold text-gray-900 flex items-center gap-2">
                          <FileDown className="text-blue-600" size={20} />
                          Selecione o Formato da DANFE
                        </Dialog.Title>
                        <button onClick={() => setIsDanfeModalOpen(false)} className="text-gray-400 hover:text-gray-600">
                          <X size={20} />
                        </button>
                      </div>
                      <p className="text-sm text-gray-600 mb-6">
                        Escolha o modelo de DANFE que deseja visualizar ou baixar:
                      </p>
                      <div className="space-y-3">
                        <button
                          type="button"
                          onClick={() => handleConfirmDownloadDanfe('completa')}
                          className="w-full flex items-center justify-between p-4 border border-gray-200 rounded-lg hover:border-blue-500 hover:bg-blue-50/50 transition-all text-left group"
                        >
                          <div>
                            <div className="font-semibold text-gray-800 text-sm group-hover:text-blue-600">DANFE Completa</div>
                            <div className="text-xs text-gray-500 mt-0.5">Formato A4 padrão com todos os itens e campos detalhados</div>
                          </div>
                          <FileText size={20} className="text-gray-400 group-hover:text-blue-600 shrink-0 ml-3" />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleConfirmDownloadDanfe('simplificada')}
                          className="w-full flex items-center justify-between p-4 border border-gray-200 rounded-lg hover:border-emerald-500 hover:bg-emerald-50/50 transition-all text-left group"
                        >
                          <div>
                            <div className="font-semibold text-gray-800 text-sm group-hover:text-emerald-600">DANFE Simplificada</div>
                            <div className="text-xs text-gray-500 mt-0.5">Etiqueta 10x15cm com chave, código de barras e identificação</div>
                          </div>
                          <Tag size={20} className="text-gray-400 group-hover:text-emerald-600 shrink-0 ml-3" />
                        </button>
                      </div>
                    </div>
                    <div className="bg-gray-50 px-4 py-3 sm:px-6 flex justify-end">
                      <button
                        type="button"
                        className="inline-flex justify-center rounded-lg bg-white px-4 py-2 text-sm font-semibold text-gray-700 shadow-sm ring-1 ring-inset ring-gray-300 hover:bg-gray-50"
                        onClick={() => setIsDanfeModalOpen(false)}
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

        {/* MODAL DE FILTROS MAGENTO */}
        <Transition.Root show={isFilterModalOpen} as={React.Fragment}>
          <Dialog as="div" className="relative z-50" onClose={() => setIsFilterModalOpen(false)}>
            <Transition.Child as={React.Fragment} enter="ease-out duration-300" enterFrom="opacity-0" enterTo="opacity-100" leave="ease-in duration-200" leaveFrom="opacity-100" leaveTo="opacity-0">
              <div className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity" />
            </Transition.Child>
            <div className="fixed inset-0 z-10 overflow-y-auto">
              <div className="flex min-h-full items-center justify-center p-4 text-center sm:p-0">
                <Transition.Child as={React.Fragment} enter="ease-out duration-300" enterFrom="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95" enterTo="opacity-100 translate-y-0 sm:scale-100" leave="ease-in duration-200" leaveFrom="opacity-100 translate-y-0 sm:scale-100" leaveTo="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95">
                  <Dialog.Panel className="relative transform overflow-hidden rounded-xl bg-white text-left shadow-2xl transition-all sm:my-8 sm:w-full sm:max-w-lg">
                    <div className="bg-white px-4 pt-5 pb-4 sm:p-6">
                      <div className="flex items-center justify-between mb-6">
                        <Dialog.Title as="h3" className="text-xl font-bold text-gray-900 flex items-center gap-2">
                          <Filter className="text-blue-600" size={20} />
                          Filtros de Importação Magento
                        </Dialog.Title>
                        <button onClick={() => setIsFilterModalOpen(false)} className="text-gray-400 hover:text-gray-600">
                          <X size={24} />
                        </button>
                      </div>
                      <div className="space-y-4">
                        <p className="text-sm text-gray-500">
                          Defina quais pedidos devem ser listados para importação.
                          A filtragem é realizada nos últimos 200 pedidos do Magento.
                        </p>
                        <DefaultFiltersInput
                          field={{ label: 'Configurar Filtros', name: 'filtros_padrao' }}
                          value={magentoConfig?.filtros_padrao || []}
                          onChange={(e) => setMagentoConfig({ ...magentoConfig, filtros_padrao: e.target.value })}
                          options={magentoFilterOptions}
                        />
                      </div>
                    </div>
                    <div className="bg-gray-50 px-4 py-4 sm:flex sm:flex-row-reverse sm:px-6 gap-3">
                      <button
                        type="button"
                        className="inline-flex w-full justify-center rounded-lg bg-blue-600 px-6 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 sm:w-auto"
                        onClick={handleSaveMagentoFilters}
                      >
                        Salvar e Aplicar
                      </button>
                      <button
                        type="button"
                        className="mt-3 inline-flex w-full justify-center rounded-lg bg-white px-6 py-2.5 text-sm font-semibold text-gray-700 shadow-sm ring-1 ring-inset ring-gray-300 hover:bg-gray-50 sm:mt-0 sm:w-auto"
                        onClick={() => setIsFilterModalOpen(false)}
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

      </div>

      {/* Modal de Inventário */}
      <ModalInventario
        isOpen={isInventarioModalOpen}
        onClose={() => setIsInventarioModalOpen(false)}
        onSuccess={() => setRefreshTrigger(prev => prev + 1)}
      />

    </div >
  );
};

export default GenericList;
