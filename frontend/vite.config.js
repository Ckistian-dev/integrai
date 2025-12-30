import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // 🎯 Adicionando a configuração de otimização
  optimizeDeps: {
    include: ['imask', 'react-imask'], // Garante que ambos sejam pré-otimizados
  },
  resolve: {
    alias: {
      // 🎯 NOVA ESTRATÉGIA DE ALIAS: Mapeia o caminho do addon para o pacote ES principal.
      // Isso deve forçar o Vite a pré-otimizar o que precisa.
      'imask/esm/addons/all': 'imask/esm',
      // Mantenha o mixin do react-imask, caso o mixin principal falhe (embora o 'react-imask/esm/mixin' funcione)
      'react-imask/esm/mixin': 'react-imask/esm/mixin',
      
      // Removemos os aliases de /number e /composite porque eles devem ser tratados
      // pela importação de 'imask/esm/addons/all'.
    }
  }
});