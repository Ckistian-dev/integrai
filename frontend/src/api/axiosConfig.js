import axios from 'axios';

// Cria uma instância do axios
const api = axios.create({
  // Define a URL base para todas as requisições
  baseURL: 'http://127.0.0.1:8000/api/v1', // URL do seu backend FastAPI
});

// Interceptor de Requisição
// Isso é executado ANTES de cada requisição
api.interceptors.request.use(
  (config) => {
    // Pega o token do localStorage
    const token = localStorage.getItem('authToken');

    if (token) {
      // Se o token existir, adiciona ao header de Authorization
      config.headers['Authorization'] = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    // Em caso de erro na configuração da requisição
    return Promise.reject(error);
  }
);

// Interceptor de Resposta (Opcional, mas recomendado)
// Isso é executado APÓS cada resposta
api.interceptors.response.use(
  (response) => {
    // Se a resposta for bem-sucedida, apenas a retorna
    return response;
  },
  (error) => {
    // Se a resposta for um erro 401 (Não Autorizado)
    if (error.response && error.response.status === 401) {
      // Limpa o token e força o logout
      localStorage.removeItem('authToken');
      // Redireciona para a página de login
      window.location.href = '/login'; 
    }
    return Promise.reject(error);
  }
);

export default api;