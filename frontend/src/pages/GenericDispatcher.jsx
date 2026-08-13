import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import api from '../api/axiosConfig';
import GenericList from './GenericList';
import GenericForm from './GenericForm';
import LoadingSpinner from '../components/ui/LoadingSpinner';

// Cache simples em memória para evitar requisições de metadados repetidas
const metadataCache = {};

const GenericDispatcher = () => {
  const { modelName } = useParams();

  // Verifica síncronamente por convenção de nome se é tabela de registro único/configuração
  const isKnownSingleRecord =
    modelName !== 'outras_empresas_configuracoes' &&
    (modelName === 'empresas' ||
      modelName?.endsWith('_configuracoes') ||
      modelName?.endsWith('_configuracao'));

  const [loading, setLoading] = useState(true);
  const [isSingleRecord, setIsSingleRecord] = useState(isKnownSingleRecord);
  const [singleRecordId, setSingleRecordId] = useState(null);

  useEffect(() => {
    let isMounted = true;
    setLoading(true);

    const checkAndDispatch = async () => {
      try {
        // Busca metadados se não estiverem no cache
        let meta = metadataCache[modelName];
        if (!meta) {
          const metaRes = await api.get(`/metadata/${modelName}`);
          meta = metaRes.data;
          metadataCache[modelName] = meta;
        }

        const singleRecord = meta?.is_single_record !== undefined ? meta.is_single_record : isKnownSingleRecord;

        if (singleRecord) {
          // Tabela de um único dado: busca o ID do registro existente
          try {
            const dataRes = await api.get(`/generic/${modelName}`);
            const items = dataRes.data.items || (Array.isArray(dataRes.data) ? dataRes.data : []);
            if (isMounted) {
              setSingleRecordId(items && items.length > 0 ? items[0].id : null);
              setIsSingleRecord(true);
            }
          } catch (err) {
            if (isMounted) {
              setSingleRecordId(null);
              setIsSingleRecord(true);
            }
          }
        } else {
          if (isMounted) {
            setIsSingleRecord(false);
          }
        }
      } catch (err) {
        if (isMounted) {
          setIsSingleRecord(isKnownSingleRecord);
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    checkAndDispatch();

    return () => {
      isMounted = false;
    };
  }, [modelName, isKnownSingleRecord]);

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <LoadingSpinner />
      </div>
    );
  }

  if (isSingleRecord) {
    return <GenericForm modelName={modelName} propId={singleRecordId} />;
  }

  return <GenericList />;
};

export default GenericDispatcher;
