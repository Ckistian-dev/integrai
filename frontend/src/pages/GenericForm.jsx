// src/pages/GenericForm.jsx

import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useParams, useNavigate, Link, useOutletContext } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import api from '../api/axiosConfig';
import FormRenderer from '../components/form/FormRenderer';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import { Save, X, Loader2, RefreshCw, ChevronDown, ChevronRight } from 'lucide-react';
import { MODULE_MAP, HUMAN_MODEL_NAMES, Breadcrumb } from '../components/layout/breadcrumbUtils';

const GenericForm = ({ modelName: propModelName, propId }) => {
  const { modelName: paramModelName, id: paramId } = useParams();
  const { user } = useAuth();
  const modelName = propModelName || paramModelName;
  const id = propId !== undefined ? propId : paramId;
  const navigate = useNavigate();
  const isEditMode = !!id;

  const [metadata, setMetadata] = useState(null);
  const [formData, setFormData] = useState({});

  // Armazena a estrutura das abas: [{ name: 'Dados Gerais', fields: [...] }, ...]
  const [tabs, setTabs] = useState([]);
  // Armazena o NOME da aba ativa
  const [activeTab, setActiveTab] = useState('');

  // --- ESTADOS PARA SUBABAS (sub_tab) ---
  const [activeSubTabMap, setActiveSubTabMap] = useState({});
  const [openSubTabDropdown, setOpenSubTabDropdown] = useState(null);
  const subTabDropdownRef = useRef(null);

  // --- ESTADO PARA PARCELAMENTO (CONTAS) ---
  const [installmentConfig, setInstallmentConfig] = useState({
    active: false,
    count: 1,
    type: 'monthly', // 'monthly' or 'days'
    interval: 28, // dia do mês ou intervalo de dias
  });

  const [loadingMetadata, setLoadingMetadata] = useState(true);
  const [loadingData, setLoadingData] = useState(false); // Apenas para modo de edição
  const [isSaving, setIsSaving] = useState(false); // Para o submit
  const [isSyncing, setIsSyncing] = useState(false); // Para o sync AtendAI
  const [formErrors, setFormErrors] = useState({});

  const handleSyncAtendai = async () => {
    setIsSyncing(true);
    try {
      const res = await api.post('/atendai/sync');
      toast.success(res.data.message || 'Pedidos sincronizados com o AtendAI com sucesso!');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erro ao sincronizar pedidos com o AtendAI.');
    } finally {
      setIsSyncing(false);
    }
  };

  // Ref para rastrear qual campo foi editado por último (para cálculo bidirecional de frete)
  const lastEditedField = useRef(null);

  // Ref para rastrear qual era o cliente anterior (para preenchimento automático ao trocar)
  const previousClientIdRef = useRef(null);

  // Filtra abas que possuem pelo menos um campo visível
  const visibleTabs = useMemo(() => {
    return tabs.filter(tab => tab.fields.some(field => field.visible !== false));
  }, [tabs]);

  // --- LÓGICA DE PERMISSÕES GRANULARES ---
  const permissionKey = useMemo(() => {
    // Mapeia models que usam permissões de outros módulos
    if (modelName === 'perfis') return 'usuarios';
    // Rotas de configuração (ex: meli_configuracoes) usam a permissão do módulo 'integracoes'
    if (modelName.endsWith('_configuracoes')) return 'integracoes';
    return modelName;
  }, [modelName]);

  const userPermissions = user?.permissoes?.[permissionKey] || { acesso: false, acoes: [] };

  // Para integrações, a ação 'manage' concede permissão de edição/criação.
  const canManageIntegrations = permissionKey === 'integracoes' && userPermissions.acoes?.includes('manage');
  const canCreate = user?.perfil === 'admin' || userPermissions.acoes?.includes('create') || canManageIntegrations;
  const canEdit = user?.perfil === 'admin' || userPermissions.acoes?.includes('edit') || canManageIntegrations;

  const canSave = isEditMode ? canEdit : canCreate;

  // Inicializa o formulário vazio com base nos metadados
  const initializeFormData = useCallback((fields) => {
    const initialData = {};
    fields.forEach((field) => {
      // 1. Prioridade: Default vindo do Backend (Model/Metadata)
      if (field.default_value !== undefined && field.default_value !== null) {
        initialData[field.name] = field.default_value;
        return;
      }

      // Trata APENAS checkboxes puros como booleano
      if (field.type === 'boolean') {
        if (field.name === 'situacao') {
          initialData[field.name] = true;
        } else if (field.name === 'considerar') {
          initialData[field.name] = true;
        } else {
          initialData[field.name] = false;
        }
      } else if (field.name === 'data_emissao' || field.name === 'data_orcamento') {
        // Preenche com a data atual (YYYY-MM-DD)
        const now = new Date();
        const year = now.getFullYear();
        const month = String(now.getMonth() + 1).padStart(2, '0');
        const day = String(now.getDate()).padStart(2, '0');
        initialData[field.name] = `${year}-${month}-${day}`;
      } else if (field.name === 'data_validade' && modelName === 'pedidos') {
        // Preenche data_validade com hoje + validade_orcamento (do usuário/empresa)
        const validadeDias = user?.empresa?.validade_orcamento || 7;
        const now = new Date();
        now.setDate(now.getDate() + validadeDias);
        const year = now.getFullYear();
        const month = String(now.getMonth() + 1).padStart(2, '0');
        const day = String(now.getDate()).padStart(2, '0');
        initialData[field.name] = `${year}-${month}-${day}`;
      } else if (field.name === 'indicador_presenca') {
        initialData[field.name] = 2; // Default: Operação não presencial, pela Internet
      } else if (field.name === 'modelo_fiscal') {
        initialData[field.name] = 55; // Default: 55 - Nota Fiscal Eletrônica (NF-e)
      } else if (field.name === 'data_despacho') {
        initialData[field.name] = null; // Não preenche automaticamente, será preenchido ao despachar
      } else if (field.type === 'order_items' && !initialData[field.name]) { // Only initialize if not already set
        initialData[field.name] = [{
          id_produto: null,
          quantidade: 1,
          valor_unitario: 0,
          ipi_aliquota: 0,
          valor_ipi: 0,
          total_com_ipi: 0
        }];
      } else {
        // Todo o resto (text, select, etc.) começa como string vazia
        initialData[field.name] = null;
      }
    });
    return initialData;
  }, []);

  // useEffect fetchMetadata (MODIFICADO para processar abas)
  useEffect(() => {
    const fetchMetadata = async () => {
      setLoadingMetadata(true);
      setMetadata(null);
      setFormData({});
      setTabs([]); // Limpa abas antigas
      setActiveTab(''); // Limpa aba ativa

      try {
        const metaRes = await api.get(`/metadata/${modelName}`);
        const meta = metaRes.data;
        setMetadata(meta);

        // --- 2. LÓGICA DE AGRUPAMENTO DE ABAS (PRESERVANDO A ORDEM) ---
        const structuredTabs = []; // Array final
        // Helper p/ agrupar fields na aba correta (pelo índice)
        const tabNameMap = {}; // Ex: { 'Dados Gerais': 0, 'Endereço': 1 }

        const isAdmin = user?.perfil === 'admin' || user?.perfil === 'Admin';
        const isSingleRecordModel = meta.is_single_record ||
          modelName === 'empresas' ||
          modelName?.endsWith('_configuracoes') ||
          modelName?.endsWith('_configuracao');

        meta.fields.forEach((field) => {
          if (field.name === 'id') return;
          if (isSingleRecordModel && field.name === 'id_sequencial') return;
          if (field.visible === false) return;

          const tabName = field.tab || 'Dados Gerais';

          // Se a aba ainda não foi vista, crie-a
          if (tabNameMap[tabName] === undefined) {
            tabNameMap[tabName] = structuredTabs.length; // Salva o índice
            structuredTabs.push({
              name: tabName,
              fields: [],
            });
          }

          // Adiciona o campo na aba correta (pelo índice salvo)
          const tabIndex = tabNameMap[tabName];

          // Se for admin e o campo for data_emissao, ou se for total/total_desconto do pedido, garante que não seja read_only para o FormRenderer
          const fieldToPush = (field.name === 'data_emissao' && isAdmin) || (modelName === 'pedidos' && (field.name === 'total' || field.name === 'total_desconto'))
            ? { ...field, read_only: false }
            : field;

          structuredTabs[tabIndex].fields.push(fieldToPush);
        });

        setTabs(structuredTabs);

        // Pré-seleciona a primeira subaba de cada aba que possui sub_tabs
        const initialSubTabMap = {};
        structuredTabs.forEach(tab => {
          const firstSubTab = tab.fields.find(f => f.sub_tab && f.visible !== false)?.sub_tab;
          if (firstSubTab) {
            initialSubTabMap[tab.name] = firstSubTab;
          }
        });
        setActiveSubTabMap(initialSubTabMap);

        // Define a primeira aba VISÍVEL como ativa
        const firstVisibleTab = structuredTabs.find(tab =>
          tab.fields.some(field => field.visible !== false)
        );
        if (firstVisibleTab) {
          setActiveTab(firstVisibleTab.name);
        }

      } catch (err) {
        toast.error("Erro ao carregar formulário.");
      } finally {
        setLoadingMetadata(false);
      }
    };
    fetchMetadata();
  }, [modelName, user?.perfil]);

  // Fecha o dropdown de subabas ao clicar fora
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (subTabDropdownRef.current && !subTabDropdownRef.current.contains(e.target)) {
        setOpenSubTabDropdown(null);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // useEffect para cálculo automático de totais (Pedidos)
  useEffect(() => {
    if (modelName === 'pedidos') {
      const items = formData.itens || [];
      const desconto = Number(formData.desconto) || 0;
      const frete = Number(formData.valor_frete) || 0;

      const totalItens = items.reduce((acc, item) => {
        const qtd = Number(item.quantidade) || 0;
        const preco = Number(item.valor_unitario) || 0;
        const ipiAliquota = Number(item.ipi_aliquota) || 0;

        // Se o item já tiver o total calculado (com IPI), usa ele, 
        // senão calcula: (qtd * preco) + IPI
        const subtotal = qtd * preco;
        const valorIpi = Number(item.valor_ipi) || (subtotal * (ipiAliquota / 100));
        const totalItem = (item.total_com_ipi !== undefined && item.total_com_ipi !== null) ? Number(item.total_com_ipi) : (subtotal + valorIpi);

        return acc + totalItem;
      }, 0);

      // Cálculo do Peso Total
      const totalPeso = items.reduce((acc, item) => {
        const qtd = Number(item.quantidade) || 0;
        const peso = Number(item.peso) || 0;
        return acc + (qtd * peso);
      }, 0);
      const totalPesoFormatted = parseFloat(totalPeso.toFixed(3));

      // Cálculo da Porcentagem Média de IPI dos Itens
      let somaPonderadaIpi = 0;
      let totalValorItens = 0;

      items.forEach((item) => {
        const qtd = Number(item.quantidade) || 0;
        const preco = Number(item.valor_unitario) || 0;
        const totalItem = qtd * preco;
        const ipi = Number(item.ipi_aliquota) || 0;

        somaPonderadaIpi += totalItem * ipi;
        totalValorItens += totalItem;
      });

      let weightedIpiPercent = 0;
      if (totalValorItens > 0) {
        weightedIpiPercent = somaPonderadaIpi / totalValorItens;
      }

      // Lógica Bidirecional: Base -> Total OU Total -> Base
      let newValorFrete = Number(formData.valor_frete) || 0;
      let newTotalFrete = Number(formData.total_frete) || 0;
      let newIpiFreteValor = 0;

      if (lastEditedField.current === 'total_frete') {
        // Cálculo Reverso: Usuário digitou o Total, calculamos a Base
        // Total = Base * (1 + IPI%)  =>  Base = Total / (1 + IPI%)
        const divisor = 1 + (weightedIpiPercent / 100);
        if (divisor !== 0) {
          newValorFrete = newTotalFrete / divisor;
        }
        newIpiFreteValor = newTotalFrete - newValorFrete;
      } else {
        // Cálculo Normal: Usuário digitou a Base (ou itens mudaram), calculamos o Total
        newIpiFreteValor = newValorFrete * (weightedIpiPercent / 100);
        newTotalFrete = newValorFrete + newIpiFreteValor;
      }

      // Arredondamentos
      newValorFrete = parseFloat(newValorFrete.toFixed(2));
      newIpiFreteValor = parseFloat(newIpiFreteValor.toFixed(2));
      newTotalFrete = parseFloat(newTotalFrete.toFixed(2));

      const isComplemento = formData.tipo_operacao === 'complemento' || formData.tipo_operacao === 'Complementar';

      const totalComDesconto = (isComplemento || lastEditedField.current === 'total_desconto')
        ? (Number(formData.total_desconto) || 0)
        : parseFloat(Math.max(0, totalItens - desconto + newValorFrete + newIpiFreteValor).toFixed(2));

      const total = (isComplemento || lastEditedField.current === 'total')
        ? (Number(formData.total) || 0)
        : parseFloat(Math.max(0, totalItens + newValorFrete + newIpiFreteValor).toFixed(2));

      const currentTotal = Number(formData.total) || 0;
      const currentTotalDesconto = Number(formData.total_desconto) || 0;
      const currentPesoBruto = Number(formData.volumes_peso_bruto) || 0;
      const currentPesoLiquido = Number(formData.volumes_peso_liquido) || 0;
      const currentValorFrete = Number(formData.valor_frete) || 0;
      const currentIpiFrete = Number(formData.ipi_frete) || 0;
      const currentTotalFrete = Number(formData.total_frete) || 0;

      if (
        Math.abs(currentTotal - total) > 0.01 ||
        Math.abs(currentTotalDesconto - totalComDesconto) > 0.01 ||
        Math.abs(currentPesoBruto - totalPesoFormatted) > 0.001 ||
        Math.abs(currentPesoLiquido - totalPesoFormatted) > 0.001 ||
        Math.abs(currentValorFrete - newValorFrete) > 0.01 ||
        Math.abs(currentIpiFrete - newIpiFreteValor) > 0.01 ||
        Math.abs(currentTotalFrete - newTotalFrete) > 0.01
      ) {
        setFormData((prev) => ({
          ...prev,
          total: total,
          total_desconto: totalComDesconto,
          volumes_peso_bruto: totalPesoFormatted,
          volumes_peso_liquido: totalPesoFormatted,
          valor_frete: newValorFrete,
          ipi_frete: newIpiFreteValor,
          total_frete: newTotalFrete,
        }));
      }
    }
  }, [formData.itens, formData.desconto, formData.valor_frete, modelName, formData.total, formData.total_desconto, formData.volumes_peso_bruto, formData.volumes_peso_liquido, formData.ipi_frete, formData.total_frete]);

  // useEffect loadFormContent (MODIFICADO para usar 'tabs' na inicialização)
  useEffect(() => {
    // Agora depende das 'tabs' terem sido processadas (do effect anterior)
    if (tabs.length === 0) return;

    const loadFormContent = async () => {
      if (isEditMode) {
        setLoadingData(true);
        try {
          const itemRes = await api.get(`/generic/${modelName}/${id}`);
          setFormData(itemRes.data);

          // 🎯 CORREÇÃO: Evita que o preenchimento automático de endereço 
          // sobreponha o endereço já salvo no pedido ao carregar o formulário.
          if (modelName === 'pedidos' && itemRes.data.id_cliente) {
            previousClientIdRef.current = itemRes.data.id_cliente;
          }
        } catch (err) {
          toast.error("Erro ao carregar dados do item.");
        } finally {
          setLoadingData(false);
        }
      } else {
        // Inicializa o form vazio usando os fields de TODAS as abas
        const allFields = tabs.flatMap(tab => tab.fields);
        setFormData(initializeFormData(allFields));
      }
    };

    loadFormContent();
    // ⚠️ Dependência 'metadata' trocada por 'tabs'
  }, [tabs, id, isEditMode, modelName, initializeFormData]);

  // --- INTEGRAÇÃO BRASIL API ---
  const fetchAddressFromCep = useCallback(async (cepValue, isDeliveryAddress = false) => {
    const cep = String(cepValue).replace(/\D/g, '');
    if (cep.length !== 8) return;

    try {
      // 1. Busca dados do CEP (Rua, Bairro, Cidade, Estado)
      const res = await fetch(`https://brasilapi.com.br/api/cep/v2/${cep}`);
      if (!res.ok) return;

      const data = await res.json();

      setFormData(prev => ({
        ...prev,
        [isDeliveryAddress ? 'endereco_logradouro' : 'logradouro']: prev[isDeliveryAddress ? 'endereco_logradouro' : 'logradouro'] || data.street || '',
        [isDeliveryAddress ? 'endereco_bairro' : 'bairro']: prev[isDeliveryAddress ? 'endereco_bairro' : 'bairro'] || data.neighborhood || '',
        [isDeliveryAddress ? 'endereco_cidade' : 'cidade']: prev[isDeliveryAddress ? 'endereco_cidade' : 'cidade'] || data.city || '',
        [isDeliveryAddress ? 'endereco_estado' : 'estado']: prev[isDeliveryAddress ? 'endereco_estado' : 'estado'] || data.state || '',
      }));

      // 2. Busca Código IBGE (Requer Estado e Cidade)
      if (data.state && data.city) {
        try {
          const resIbge = await fetch(`https://brasilapi.com.br/api/ibge/municipios/v1/${data.state}`);
          if (resIbge.ok) {
            const cities = await resIbge.json();
            // Normalização para comparação segura (remove acentos e uppercase)
            const normalize = (str) => str.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/-/g, " ").toUpperCase();
            const targetCity = normalize(data.city);

            const found = cities.find(c => normalize(c.nome) === targetCity);

            if (found) {
              setFormData(prev => ({
                ...prev,
                [isDeliveryAddress ? 'endereco_cidade_ibge' : 'cidade_ibge']: prev[isDeliveryAddress ? 'endereco_cidade_ibge' : 'cidade_ibge'] || String(found.codigo_ibge)
              }));
            }
          }
        } catch (errIbge) {
        }
      }

    } catch (err) {
      toast.error("Erro ao buscar CEP.");
    }
  }, []);

  // --- INTEGRAÇÃO BRASIL API (CNPJ) ---
  const fetchCnpjData = useCallback(async (cnpjValue) => {
    const cnpj = String(cnpjValue).replace(/[^a-zA-Z0-9]/g, '').toUpperCase();
    if (cnpj.length !== 14) return;

    try {
      const res = await fetch(`https://brasilapi.com.br/api/cnpj/v1/${cnpj}`);
      if (!res.ok) return;

      const data = await res.json();

      setFormData(prev => ({
        ...prev,
        tipo_pessoa: prev.tipo_pessoa || 'juridica',
        nome_razao: prev.nome_razao || (data.razao_social ? data.razao_social.toUpperCase() : ''),
        fantasia: prev.fantasia || (data.nome_fantasia ? data.nome_fantasia.toUpperCase() : ''),
        cep: prev.cep || (data.cep ? data.cep.replace(/\D/g, '') : ''),
        logradouro: prev.logradouro || data.logradouro || '',
        numero: prev.numero || data.numero || '',
        complemento: prev.complemento || data.complemento || '',
        bairro: prev.bairro || data.bairro || '',
        cidade: prev.cidade || data.municipio || '',
        estado: prev.estado || data.uf || '',
        email: prev.email || (data.email ? data.email.toLowerCase() : ''),
        telefone: prev.telefone || (data.ddd_telefone_1 ? `(${data.ddd_telefone_1.substring(0, 2)}) ${data.ddd_telefone_1.substring(2)}` : '')
      }));

      // Busca Código IBGE (Requer Estado e Cidade)
      if (data.uf && data.municipio) {
        try {
          const resIbge = await fetch(`https://brasilapi.com.br/api/ibge/municipios/v1/${data.uf}`);
          if (resIbge.ok) {
            const cities = await resIbge.json();
            const normalize = (str) => str.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/-/g, " ").toUpperCase();
            const targetCity = normalize(data.municipio);
            const found = cities.find(c => normalize(c.nome) === targetCity);
            if (found) {
              setFormData(prev => ({ ...prev, cidade_ibge: prev.cidade_ibge || String(found.codigo_ibge) }));
            }
          }
        } catch (errIbge) { }
      }
    } catch (err) { toast.error("Erro ao buscar CNPJ."); }
  }, []);

  // Handler genérico para atualizar o estado do formulário
  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;

    // Registra qual campo está sendo editado para a lógica de cálculo reverso
    lastEditedField.current = name;

    let val;
    if (type === 'checkbox') {
      val = checked;
    } else {
      val = value;

      // --- NOVA LÓGICA: CAIXA ALTA PARA NOME/RAZÃO E FANTASIA ---
      if (['nome_razao', 'fantasia', 'razao'].includes(name) && typeof val === 'string') {
        val = val.toUpperCase();
      }

      // Se o valor for uma string vazia e o campo for de data, converte para null
      // Isso evita erro de validação no Pydantic (input is too short)
      if (val === '' && (type === 'date' || type === 'datetime-local')) {
        val = null;
      }
    }

    setFormData((prev) => {
      const newData = { ...prev, [name]: val };

      // Clear classification when account type is changed
      if (modelName === 'contas' && name === 'tipo_conta') {
        newData.id_classificacao_contabil = null;
      }

      // Automação para Contas: Se marcar como Pago e não tiver data de baixa, define hoje
      if (modelName === 'contas' && name === 'situacao' && val === 'Pago') {
        if (!newData.data_baixa) {
          const now = new Date();
          const year = now.getFullYear();
          const month = String(now.getMonth() + 1).padStart(2, '0');
          const day = String(now.getDate()).padStart(2, '0');
          newData.data_baixa = `${year}-${month}-${day}`;
        }
      }

      return newData;
    });

    // Dispara busca de CEP se for o campo 'cep' ou 'endereco_cep' e tiver 8 dígitos
    if (name === 'cep' || name === 'endereco_cep') {
      const cleanCep = String(val).replace(/\D/g, '');
      if (cleanCep.length === 8) {
        fetchAddressFromCep(val, name === 'endereco_cep');
      }
    }

    // Dispara busca de CNPJ se for o campo 'cpf_cnpj' e tiver 14 dígitos
    if (name === 'cpf_cnpj') {
      const cleanVal = String(val).replace(/[^a-zA-Z0-9]/g, '').toUpperCase();
      if (cleanVal.length === 14) {
        setFormData(prev => ({ ...prev, tipo_pessoa: 'juridica' }));
        fetchCnpjData(val);
      }
    }
  };

  // --- PREENCHIMENTO AUTOMÁTICO DE ENDEREÇO AO TROCAR CLIENTE ---
  useEffect(() => {
    // Só executa para o modelo 'pedidos'
    if (modelName !== 'pedidos') return;

    const currentClientId = formData.id_cliente;
    const previousClientId = previousClientIdRef.current;

    // Se não há cliente selecionado ou é o mesmo, não faz nada
    if (!currentClientId || currentClientId === previousClientId) return;

    // Cliente mudou! Atualiza a referência e busca os dados
    previousClientIdRef.current = currentClientId;

    api.get(`/generic/cadastros/${currentClientId}`)
      .then(res => {
        const cliente = res.data;
        setFormData(prev => ({
          ...prev,
          // Sobrescreve com os dados do novo cliente
          endereco_cep: cliente.cep || '',
          endereco_logradouro: cliente.logradouro || '',
          endereco_numero: cliente.numero || '',
          endereco_complemento: cliente.complemento || '',
          endereco_bairro: cliente.bairro || '',
          endereco_cidade: cliente.cidade || '',
          endereco_estado: cliente.estado || '',
        }));
      })
      .catch(err => {
        console.error("Erro ao buscar dados do cliente para preencher endereço", err);
      });
  }, [formData.id_cliente, modelName]);

  // --- AUTO-ATIVAR PARCELAMENTO (CONTAS) ---
  useEffect(() => {
    if (modelName === 'contas' && !isEditMode) {
      // 03: Cartão de Crédito, 05: Crédito Loja, 14: Duplicata, 15: Boleto
      const installmentTypes = ['03', '05', '14', '15'];
      const isInstallment = installmentTypes.includes(formData.pagamento);

      setInstallmentConfig(prev => ({
        ...prev,
        active: isInstallment
      }));
    }
  }, [formData.pagamento, modelName, isEditMode]);

  // Handler de submit
  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsSaving(true);
    setFormErrors({});

    // Validação genérica para campos obrigatórios (required)
    const errors = {};
    const allFields = tabs.flatMap(tab => tab.fields || []);
    allFields.forEach((field) => {
      if (field.required && field.visible !== false && field.read_only !== true) {
        const val = formData[field.name];
        if (
          val === null ||
          val === undefined ||
          String(val).trim() === '' ||
          (Array.isArray(val) && val.length === 0)
        ) {
          errors[field.name] = `${field.label} é obrigatório.`;
        }
      }
    });

    // Validações específicas para Contas
    if (modelName === 'contas') {
      const situacao = formData.situacao;

      if (situacao === 'Em Aberto') {
        if (!formData.data_vencimento) {
          errors.data_vencimento = 'Data de vencimento é obrigatória.';
        }
      } else if (situacao === 'Pago') {
        if (!formData.caixa_destino_origem) {
          errors.caixa_destino_origem = 'Conta bancária é obrigatória.';
        }
        if (!formData.pagamento) {
          errors.pagamento = 'Forma de pagamento é obrigatória.';
        }
      }
    }
    // Validação específica para Pedidos Complementares: deve ter pelo menos um item
    if (modelName === 'pedidos' && (formData.tipo_operacao === 'complemento' || formData.tipo_operacao === 'Complementar')) {
      const items = formData.itens || [];
      if (items.length === 0) {
        errors.itens = "Uma Nota Fiscal Complementar deve possuir pelo menos um item (mesmo que com quantidade e valor zerados).";
      }
    }

    if (Object.keys(errors).length > 0) {
      setFormErrors(errors);
      if (errors.itens) {
        toast.error(errors.itens);
      } else {
        toast.error('Verifique os campos obrigatórios.');
      }
      setIsSaving(false);
      return;
    }

    try {
      if (isEditMode) {
        // Atualização (PUT)
        await api.put(`/generic/${modelName}/${id}`, formData);
      } else {
        // --- LÓGICA DE PARCELAMENTO (CONTAS - CRIAÇÃO EM LOTE) ---
        if (modelName === 'contas' && installmentConfig.active) {
          const num = Math.max(1, parseInt(installmentConfig.count));
          const valuePerInstallment = Number(formData.valor) || 0;

          const baseDate = formData.data_vencimento ? new Date(formData.data_vencimento + 'T12:00:00') : new Date();

          for (let i = 1; i <= num; i++) {
            const currentData = { ...formData };
            currentData.valor = valuePerInstallment;

            // Formata descrição: "Descrição Original (Parcela 1/10)"
            const descBase = formData.descricao || '';
            currentData.descricao = num > 1 ? `${descBase} (Parcela ${i}/${num})` : descBase;

            // Calcula data de vencimento
            let dueDate = new Date(baseDate);
            if (i > 1) {
              if (installmentConfig.type === 'monthly') {
                dueDate.setMonth(baseDate.getMonth() + (i - 1));
              } else {
                dueDate.setDate(baseDate.getDate() + (installmentConfig.interval * (i - 1)));
              }
            }
            currentData.data_vencimento = dueDate.toISOString().split('T')[0];

            // Envia a criação individual de cada parcela
            await api.post(`/generic/${modelName}`, currentData);
          }
          toast.success(`${num} parcelas criadas com sucesso!`);
          navigate(-1);
          return;
        }

        // Criação (POST)
        await api.post(`/generic/${modelName}`, formData);
      }
      // Sucesso, volta para a página anterior
      navigate(-1);
    } catch (err) {
      const backendMessage = err.response?.data?.detail;

      if (err.response && err.response.status === 422) {
        toast.error('Erro de validação. Verifique os campos.');
        // Idealmente, o backend retornaria os erros por campo
        // setFormErrors(err.response.data.detail);
      } else if (err.response && err.response.status === 400 && backendMessage) {
        toast.error(backendMessage);
      } else {
        toast.error('Erro ao salvar. Tente novamente.');
      }
    } finally {
      setIsSaving(false);
    }
  };

  // Função para lidar com a navegação entre abas via teclado (Tab)
  const handleTabPress = (e, tabIndex, fieldIndex) => {
    if (e.key === 'Tab' && !e.shiftKey) {
      const currentTab = visibleTabs[tabIndex];
      if (!currentTab) return;

      // Encontra o índice do último campo VISÍVEL desta aba
      let lastVisibleIndex = -1;
      for (let i = currentTab.fields.length - 1; i >= 0; i--) {
        if (currentTab.fields[i].type !== 'hidden' && currentTab.fields[i].visible !== false) {
          lastVisibleIndex = i;
          break;
        }
      }

      // Verifica se é o último campo visível da aba atual
      if (fieldIndex === lastVisibleIndex) {
        // Verifica se existe uma próxima aba
        if (tabIndex < visibleTabs.length - 1) {
          e.preventDefault();
          const nextTab = visibleTabs[tabIndex + 1];
          setActiveTab(nextTab.name);

          // Foca no primeiro campo VISÍVEL da próxima aba
          setTimeout(() => {
            const firstVisibleField = nextTab.fields.find(f => f.type !== 'hidden' && f.visible !== false);
            if (firstVisibleField) {
              const element = document.getElementById(firstVisibleField.name);
              if (element) {
                element.focus();
              }
            }
          }, 50);
        }
      }
    }
  };

  const outletContext = useOutletContext();
  const setPageHeader = outletContext?.setPageHeader;

  // --- BREADCRUMB & HEADER: Hooks DEVEM ficar ANTES dos early returns (Rules of Hooks) ---
  const pageTitle = useMemo(() => {
    const singularName = metadata?.display_name_singular || metadata?.display_name || HUMAN_MODEL_NAMES[modelName] || modelName.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    return isEditMode ? `Editar ${singularName}` : `Novo ${singularName}`;
  }, [metadata, modelName, isEditMode]);

  const breadcrumbCrumbs = useMemo(() => {
    const entry = MODULE_MAP[modelName];
    const crumbs = [{ label: 'Home', path: '/dashboard' }];

    const singularName = metadata?.display_name_singular || metadata?.display_name || HUMAN_MODEL_NAMES[modelName] || modelName.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    const currentPageLabel = isEditMode ? `Editar ${singularName}` : `Novo ${singularName}`;

    if (entry) {
      crumbs.push({ label: entry.module, path: entry.modulePath || `/${modelName}` });
    }

    crumbs.push({ label: currentPageLabel, path: null });
    return crumbs;
  }, [modelName, metadata, isEditMode]);

  useEffect(() => {
    if (setPageHeader && metadata) {
      setPageHeader({
        title: pageTitle,
        crumbs: breadcrumbCrumbs
      });
    }
  }, [pageTitle, breadcrumbCrumbs, setPageHeader, metadata]);

  if (loadingMetadata) {
    return <LoadingSpinner />;
  }

  // --- INÍCIO DAS MUDANÇAS DE LAYOUT ---

  return (
    // Para replicar a imagem, adicionamos um fundo cinza à página
    <div className="bg-gray-100 min-h-screen p-8">
      <div className="container mx-auto max-w-7xl"> {/* Limita a largura máxima */}
        <form onSubmit={handleSubmit} autoComplete="off">
          <div className="">

            {/* 1. CABEÇALHO DO CARD: Breadcrumb e Título */}
            <div className="flex flex-col gap-1 mb-6">
              <Breadcrumb crumbs={breadcrumbCrumbs} />
              <h1 className="text-2xl font-bold text-gray-800 tracking-tight">
                {pageTitle}
              </h1>
            </div>

            {/* --- 3. RENDERIZAÇÃO DA BARRA DE ABAS E SUBABAS --- */}
            {visibleTabs.length > 0 && (
              <div className="mb-4 border-b border-gray-200">
                <nav ref={subTabDropdownRef} className="-mb-px flex space-x-2" aria-label="Tabs">
                  {visibleTabs.map((tab) => {
                    const subTabs = Array.from(new Set(tab.fields.map(f => f.sub_tab).filter(Boolean)));
                    const hasSubTabs = subTabs.length > 0;
                    const isTabActive = activeTab === tab.name;

                    return (
                      <div key={tab.name} className="relative inline-block">
                        <button
                          type="button"
                          onClick={() => {
                            setActiveTab(tab.name);
                            if (hasSubTabs) {
                              setOpenSubTabDropdown(prev => (prev === tab.name ? null : tab.name));
                            } else {
                              setOpenSubTabDropdown(null);
                            }
                          }}
                          className={`whitespace-nowrap py-3 px-4 border-b-2 font-medium text-base flex items-center gap-1.5 cursor-pointer ${isTabActive
                            ? 'bg-teal-600 text-white rounded-t-lg border-teal-600'
                            : 'border-transparent text-gray-500 hover:text-gray-700'
                            }`}
                        >
                          <span>{tab.name}</span>
                          {hasSubTabs && (
                            <ChevronDown className={`w-4 h-4 transition-transform ${openSubTabDropdown === tab.name ? 'rotate-180' : ''}`} />
                          )}
                        </button>

                        {/* Dropdown de Subabas (aparece ao clicar na aba/setinha) */}
                        {hasSubTabs && openSubTabDropdown === tab.name && (
                          <div className="absolute left-0 mt-1 w-52 bg-white border border-gray-200 rounded-lg shadow-xl z-50 py-1 font-sans">
                            {subTabs.map(subName => (
                              <button
                                key={subName}
                                type="button"
                                onClick={() => {
                                  setActiveTab(tab.name);
                                  setActiveSubTabMap(prev => ({ ...prev, [tab.name]: subName }));
                                  setOpenSubTabDropdown(null);
                                }}
                                className={`w-full text-left px-4 py-2 text-xs font-semibold hover:bg-gray-50 transition-colors flex items-center justify-between ${activeSubTabMap[tab.name] === subName ? 'text-teal-600 font-bold bg-teal-50/50' : 'text-gray-700'
                                  }`}
                              >
                                <span>{subName}</span>
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </nav>
              </div>
            )}

            {/* 2. CORPO DO CARD: Alerta de Erro e Campos do Formulário */}
            <div className="pb-6">

              {/* --- 4. RENDERIZAÇÃO DO CONTEÚDO DA ABA ATIVA --- */}
              {isEditMode && loadingData ? (
                <div className="flex justify-center items-center h-48">
                  <LoadingSpinner />
                </div>
              ) : (
                // Itera sobre as abas e renderiza o conteúdo
                visibleTabs.map((tab, tabIndex) => {
                  const currentSubTab = activeSubTabMap[tab.name] || null;
                  const isSingleRecordModel = metadata?.is_single_record ||
                    modelName === 'empresas' ||
                    modelName?.endsWith('_configuracoes') ||
                    modelName?.endsWith('_configuracao');
                  const filteredFields = tab.fields.filter(field => {
                    if (field.visible === false) return false;
                    if (field.name === 'id') return false;
                    if (isSingleRecordModel && field.name === 'id_sequencial') return false;
                    if (currentSubTab && field.sub_tab && field.sub_tab !== currentSubTab) return false;
                    return true;
                  });

                  const hasCol3 = filteredFields.some(f => f.col_span === 3);
                  const gridColsClass = hasCol3 ? 'grid grid-cols-1 md:grid-cols-3 gap-x-6 gap-y-4' : 'grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4';

                  return (
                    <div
                      key={tab.name}
                      className={activeTab !== tab.name ? 'hidden' : ''}
                    >
                      <div className={gridColsClass}>
                        {/* Renderiza apenas os campos da aba ativa e subaba selecionada */}
                        {filteredFields.map((field, fieldIndex) => {
                          let colSpanClass = '';
                          if (field.col_span === 3) colSpanClass = 'md:col-span-3';
                          else if (field.col_span === 2) colSpanClass = 'md:col-span-2';

                          // O FormRenderer é envolvido por uma div para aplicar o col-span.
                          // A 'key' é movida para o elemento mais externo do loop.
                          return (
                            <React.Fragment key={field.name}>
                              <div className={colSpanClass}>
                                <FormRenderer
                                  field={field.name === 'valor' && installmentConfig.active ? { ...field, label: 'Valor da Parcela' } : field}
                                  value={formData[field.name] ?? ''}
                                  onChange={handleChange}
                                  error={formErrors[field.name]}
                                  modelName={modelName}
                                  formData={formData}
                                  onKeyDown={(e) => handleTabPress(e, tabIndex, fieldIndex)}
                                />
                              </div>

                              {/* Injeção dos campos de parcelamento logo após o campo 'valor' */}
                              {modelName === 'contas' && !isEditMode && installmentConfig.active && field.name === 'valor' && (
                                <>
                                  <div className="flex flex-col">
                                    <label className="mb-1.5 text-sm font-medium text-gray-700">Nº de Parcelas</label>
                                    <input
                                      type="number"
                                      min="1"
                                      value={installmentConfig.count}
                                      onChange={(e) => setInstallmentConfig({ ...installmentConfig, count: parseInt(e.target.value) || 1 })}
                                      className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                                    />
                                  </div>

                                  <div className="flex flex-col">
                                    <label className="mb-1.5 text-sm font-medium text-gray-700">Tipo de Vencimento</label>
                                    <select
                                      value={installmentConfig.type}
                                      onChange={(e) => setInstallmentConfig({ ...installmentConfig, type: e.target.value })}
                                      className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                                    >
                                      <option value="monthly">Mensal (Mesmo dia de cada mês)</option>
                                      <option value="days">Intervalo de Dias (ex: a cada 30 dias)</option>
                                    </select>
                                  </div>

                                  {installmentConfig.type === 'days' && (
                                    <div className="flex flex-col">
                                      <label className="mb-1.5 text-sm font-medium text-gray-700">Dias entre Parcelas</label>
                                      <input
                                        type="number"
                                        min="1"
                                        value={installmentConfig.interval}
                                        onChange={(e) => setInstallmentConfig({ ...installmentConfig, interval: parseInt(e.target.value) || 30 })}
                                        className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                                      />
                                    </div>
                                  )}
                                </>
                              )}
                            </React.Fragment>
                          );
                        })}
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            <div className="flex justify-end space-x-3 py-4 border-gray-200">

              {modelName === 'atendai_configuracoes' && (
                <button
                  type="button"
                  onClick={handleSyncAtendai}
                  disabled={isSyncing || isSaving}
                  className="flex items-center px-4 py-2 bg-indigo-600 text-white rounded-lg shadow-md hover:bg-indigo-700 disabled:bg-indigo-400 disabled:cursor-not-allowed"
                >
                  {isSyncing ? (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    <RefreshCw className="w-4 h-4 mr-2" />
                  )}
                  {isSyncing ? 'Sincronizando...' : 'Sincronizar Pedidos'}
                </button>
              )}

              {/* Botão "Voltar" (Estilo cinza da imagem) */}
              <button
                type="button"
                onClick={() => navigate(-1)}
                disabled={isSaving}
                className="flex items-center px-4 py-2 bg-gray-200 text-gray-800 rounded-lg hover:bg-gray-300 disabled:opacity-50"
              >
                Voltar
              </button>

              {/* Botão "Criar Cadastro" / Salvar (Estilo teal da imagem) */}
              <button
                type="submit"
                disabled={isSaving || loadingData || !canSave}
                className="flex items-center px-4 py-2 bg-teal-600 text-white rounded-lg shadow-md hover:bg-teal-700 disabled:bg-teal-400 disabled:cursor-not-allowed"
              >
                {isSaving ? (
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                ) : null}

                {/* Texto do botão (MANTIDO DINÂMICO) */}
                {isSaving
                  ? 'Salvando...'
                  : (isEditMode
                    ? `Salvar Alterações` // Texto mais limpo para edição
                    : `Criar Cadastro`) // Texto fixo para criação
                }
              </button>
            </div>

          </div> {/* Fim do card 'bg-white' */}
        </form>
      </div>
    </div>
  );
};

export default GenericForm;