import React, { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'react-toastify';
import api from '../api/axiosConfig';
import LoadingSpinner from '../components/ui/LoadingSpinner';

const ShopeeCallback = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  useEffect(() => {
    const processAuth = async () => {
      const code = searchParams.get('code');
      const shop_id = searchParams.get('shop_id');

      if (!code || !shop_id) {
        toast.error('Parâmetros de autorização da Shopee ausentes.');
        navigate('/shopee_pedidos');
        return;
      }

      try {
        const response = await api.post('/shopee/auth', { code, shop_id });
        toast.success(response.data.message || 'Integração com a Shopee realizada com sucesso!');
        navigate('/shopee_pedidos');
      } catch (err) {
        const errorDetail = err.response?.data?.detail || 'Erro ao conectar com a Shopee.';
        toast.error(`Falha na autorização Shopee: ${errorDetail}`);
        navigate('/shopee_pedidos');
      }
    };

    processAuth();
  }, [searchParams, navigate]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gray-50 dark:bg-slate-900 px-4">
      <div className="p-8 bg-white dark:bg-slate-800 rounded-xl shadow-lg text-center max-w-md w-full border border-gray-100 dark:border-slate-700">
        <LoadingSpinner size="lg" />
        <h2 className="mt-4 text-xl font-semibold text-gray-800 dark:text-gray-100">
          Autenticando com a Shopee...
        </h2>
        <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
          Por favor, aguarde enquanto finalizamos a conexão da sua loja.
        </p>
      </div>
    </div>
  );
};

export default ShopeeCallback;
