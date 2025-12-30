// src/pages/GenericForm.jsx

import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import api from '../api/axiosConfig';
import FormRenderer from '../components/form/FormRenderer';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import { Save, X, Loader2 } from 'lucide-react';

const GenericForm = () => {
  const { modelName, id } = useParams();
  const navigate = useNavigate();
  const isEditMode = !!id;

  const [metadata, setMetadata] = useState(null);
  const [formData, setFormData] = useState({});

  // Armazena a estrutura das abas: [{ name: 'Dados Gerais', fields: [...] }, ...]
  const [tabs, setTabs] = useState([]);
  // Armazena o NOME da aba ativa
  const [activeTab, setActiveTab] = useState('');

  const [loadingMetadata, setLoadingMetadata] = useState(true);
  const [loadingData, setLoadingData] = useState(false); // Apenas para modo de edição
  const [isSaving, setIsSaving] = useState(false); // Para o submit

  const [error, setError] = useState(null);
  const [formErrors, setFormErrors] = useState({});

  // Inicializa o formulário vazio com base nos metadados
  const initializeFormData = useCallback((fields) => {
    const initialData = {};
    fields.forEach((field) => {
      // Trata APENAS checkboxes puros como booleano
      if (field.type === 'boolean') {
        initialData[field.name] = false; 
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
      setError(null);
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

        meta.fields.forEach((field) => {
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
          structuredTabs[tabIndex].fields.push(field);
        });

        setTabs(structuredTabs);

        // Define a primeira aba como ativa
        if (structuredTabs.length > 0) {
          setActiveTab(structuredTabs[0].name);
        }

      } catch (err) {
        console.error('Falha ao carregar metadados:', err);
        setError(`Não foi possível carregar o formulário para "${modelName}".`);
      } finally {
        setLoadingMetadata(false);
      }
    };
    fetchMetadata();
  }, [modelName]);

  // useEffect loadFormContent (MODIFICADO para usar 'tabs' na inicialização)
  useEffect(() => {
    // Agora depende das 'tabs' terem sido processadas (do effect anterior)
    if (tabs.length === 0) return;

    const loadFormContent = async () => {
      setError(null);

      if (isEditMode) {
        setLoadingData(true);
        try {
          const itemRes = await api.get(`/generic/${modelName}/${id}`);
          setFormData(itemRes.data);
        } catch (err) {
          console.error('Falha ao carregar dados do item:', err);
          setError(`Não foi possível carregar o item com ID ${id}.`);
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

  // Handler genérico para atualizar o estado do formulário
  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;

    let val;
    if (type === 'checkbox') {
      val = checked;
    } else {
      // AQUI ESTÁ A MUDANÇA:
      // Simplesmente use o valor que veio do input/select
      val = value;
    }

    setFormData((prev) => ({
      ...prev,
      [name]: val,
    }));
  };

  // Handler de submit
  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsSaving(true);
    setError(null);
    setFormErrors({});

    try {
      if (isEditMode) {
        // Atualização (PUT)
        await api.put(`/generic/${modelName}/${id}`, formData);
      } else {
        // Criação (POST)
        await api.post(`/generic/${modelName}`, formData);
      }
      // Sucesso, volta para a lista
      navigate(`/${modelName}`);
    } catch (err) {
      console.error('Falha ao salvar:', err);
      if (err.response && err.response.status === 422) {
        setError('Houve um erro de validação. Verifique os campos.');
        // Idealmente, o backend retornaria os erros por campo
        // setFormErrors(err.response.data.detail);
      } else {
        setError('Ocorreu um erro ao salvar. Tente novamente.');
      }
    } finally {
      setIsSaving(false);
    }
  };

  if (loadingMetadata) {
    return <LoadingSpinner />;
  }

  // Mova o erro de "metadados não encontrados" para ser tratado pelo 'if (error)'
  if (!metadata && !loadingMetadata && !error) {
    setError(`Metadados para "${modelName}" não foram encontrados.`);
  }

  // Textos dos botões e título (MANTIDOS DO SEU CÓDIGO ORIGINAL)
  const pageTitle = isEditMode
    ? `Editar ${metadata?.display_name || modelName}`
    : `Novo ${metadata?.display_name || modelName}`; // Alterado para "Novo" para se aproximar da imagem

  // --- INÍCIO DAS MUDANÇAS DE LAYOUT ---

  return (
    // Para replicar a imagem, adicionamos um fundo cinza à página
    <div className="bg-gray-100 min-h-screen p-16 overflow-y-scroll">
      <div className="container mx-auto max-w-7xl"> {/* Limita a largura máxima */}
        <form onSubmit={handleSubmit}>
          <div className="overflow-hidden">

            {/* 1. CABEÇALHO DO CARD: Título e Separador */}
            <h1 className="text-4xl font-bold text-gray-800 mb-6">
              {/* Usamos o pageTitle dinâmico do seu código, 
                  mas você pode travar para "Novo Cadastro" se preferir:
                  {isEditMode ? `Editar ${metadata.display_name}` : "Novo Cadastro"}
                */}
              {pageTitle}
            </h1>

            {/* --- 3. RENDERIZAÇÃO DA BARRA DE ABAS --- */}
            {tabs.length > 0 && (
              <div className="mb-6 border-b border-gray-200">
                {/* Ajuste no espaçamento para ficar mais parecido com a imagem */}
                <nav className="-mb-px flex space-x-2" aria-label="Tabs">
                  {tabs.map((tab) => (
                    <button
                      key={tab.name}
                      type="button" // Importante: impede o submit do form
                      onClick={() => setActiveTab(tab.name)}
                      className={`whitespace-nowrap py-3 px-4 border-b-2 
                                  font-medium text-base
                                  ${activeTab === tab.name
                          // (Ativo) Botão sólido com fundo, texto branco e borda da mesma cor
                          ? 'bg-teal-600 text-white rounded-t-lg border-teal-600'
                          // (Inativo) Apenas texto, com borda transparente
                          : 'border-transparent text-gray-500 hover:text-gray-700'
                        }`}
                    >
                      {tab.name}
                    </button>
                  ))}
                </nav>
              </div>
            )}

            {/* 2. CORPO DO CARD: Alerta de Erro e Campos do Formulário */}
            <div className="pb-6">

              {/* Alerta de Erro (dentro do corpo do card) */}
              {error && (
                <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative mb-6" role="alert">
                  <span className="block sm:inline">{error}</span>
                </div>
              )}

              {/* --- 4. RENDERIZAÇÃO DO CONTEÚDO DA ABA ATIVA --- */}
              {isEditMode && loadingData ? (
                <div className="flex justify-center items-center h-48">
                  <LoadingSpinner />
                </div>
              ) : (
                // Itera sobre as abas e renderiza o conteúdo
                tabs.map((tab) => (
                  <div
                    key={tab.name}
                    // Usa 'hidden' para esconder abas inativas
                    // Isso mantém o estado dos inputs ao trocar de aba!
                    className={activeTab !== tab.name ? 'hidden' : ''}
                  >
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-5">
                      {/* Renderiza apenas os campos da aba ativa */}
                      {tab.fields.map((field) => (
                        <FormRenderer
                          key={field.name}
                          field={field}
                          value={formData[field.name] || ''}
                          onChange={handleChange}
                          error={formErrors[field.name]}
                        />
                      ))}
                    </div>
                  </div>
                ))
              )}
            </div>

            <div className="flex justify-end space-x-3 py-4 border-gray-200">

              {/* Botão "Voltar" (Estilo cinza da imagem) */}
              <button
                type="button"
                onClick={() => navigate(`/${modelName}`)}
                disabled={isSaving}
                className="flex items-center px-4 py-2 bg-gray-200 text-gray-800 rounded-lg hover:bg-gray-300 disabled:opacity-50"
              >
                Voltar
              </button>

              {/* Botão "Criar Cadastro" / Salvar (Estilo teal da imagem) */}
              <button
                type="submit"
                disabled={isSaving || loadingData}
                className="flex items-center px-4 py-2 bg-teal-600 text-white rounded-lg shadow-md hover:bg-teal-700 disabled:bg-teal-400"
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