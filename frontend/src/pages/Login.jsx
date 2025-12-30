import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { User, Lock, ArrowRight } from 'lucide-react';

// --- Mocks para simular o ambiente (Substitua pelos seus imports reais) ---
// Se estiver usando em seu projeto, descomente os imports reais abaixo e remova estes mocks.
import { useAuth } from '../contexts/AuthContext';
import { useNavigate, useLocation } from 'react-router-dom';

// --- Componente da Ilustração do Laptop (CSS/SVG Puro) ---
const LaptopIllustration = () => (
  <svg viewBox="0 0 400 300" className="w-full h-full drop-shadow-2xl">
    <defs>
      <linearGradient id="screenGrad" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stopColor="#1e293b" />
        <stop offset="100%" stopColor="#0f172a" />
      </linearGradient>
    </defs>
    
    {/* Base do Laptop */}
    <g transform="translate(50, 50)">
      {/* Parte inferior (Teclado) */}
      <motion.g
        initial={{ y: 10, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.8, delay: 0.2 }}
      >
        <path d="M20,180 L280,180 L300,200 L0,200 Z" fill="#e2e8f0" /> {/* Topo da base */}
        <path d="M0,200 L300,200 L300,210 L0,210 Z" fill="#cbd5e1" /> {/* Lateral da base */}
        {/* Teclado simulado */}
        <rect x="30" y="185" width="240" height="10" rx="1" fill="#94a3b8" />
        {/* Trackpad */}
        <rect x="120" y="198" width="60" height="15" transform="skewX(-45)" fill="#cbd5e1" opacity="0.5" />
      </motion.g>

      {/* Tela */}
      <motion.g
        initial={{ rotateX: 90, opacity: 0 }}
        animate={{ rotateX: 0, opacity: 1 }}
        transition={{ duration: 1, type: "spring", bounce: 0.4 }}
        style={{ transformOrigin: "bottom" }}
      >
        <path d="M20,180 L20,30 L280,30 L280,180 Z" fill="#0f172a" /> {/* Borda externa */}
        <rect x="30" y="40" width="240" height="130" fill="url(#screenGrad)" /> {/* Tela */}
        
        {/* Logo na tampa (Simulado como um reflexo/logo) */}
        <circle cx="150" cy="105" r="10" fill="#38bdf8" opacity="0.8" />
        
        {/* Brilho na tela */}
        <path d="M30,40 L100,40 L30,170 Z" fill="white" opacity="0.05" />
      </motion.g>
      
      {/* Elemento de Brilho/Estrela flutuante */}
      <motion.path
        d="M275,30 L280,20 L285,30 L295,35 L285,40 L280,50 L275,40 L265,35 Z"
        fill="#fbbf24"
        animate={{ 
          scale: [1, 1.2, 1],
          rotate: [0, 180, 360],
          opacity: [0.8, 1, 0.8]
        }}
        transition={{ duration: 3, repeat: Infinity }}
      />
    </g>
  </svg>
);

// --- Componente Principal ---
const Login = () => {
  // Estados
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // Hooks (Usando Mocks se os reais não existirem no contexto deste exemplo)
  // No seu código real, use: const { login } = useAuth();
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const from = location.state?.from?.pathname || '/';

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      if (err.response && err.response.status === 401) {
        setError('Email ou senha incorretos.');
      } else {
        setError('Falha ao conectar. Tente novamente.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen w-full bg-white overflow-hidden flex items-center justify-center font-sans">
      
      {/* --- Elementos de Fundo (Ondas Escuras) --- */}
      
      {/* Onda Topo Direito */}
      <div className="absolute top-0 right-0 w-3/2 h-1/2 pointer-events-none z-0">
        <svg viewBox="0 0 500 500" className="w-full h-full fill-[#0f1f2c]">
          <path d="M300,0 Q400,200 500,500 L500,0 Z" />
          <path d="M0,0 C150,0 350,100 500,400 L500,0 Z" opacity="0.5" />
        </svg>
      </div>

      {/* Onda Baixo Esquerdo */}
      <div className="absolute bottom-0 left-0 w-3/2 h-1/2 pointer-events-none z-0">
        <svg viewBox="0 0 500 500" className="w-full h-full fill-[#0f1f2c]">
          <path d="M0,500 L200,500 Q100,300 0,0 Z" />
          <path d="M0,500 L500,500 C350,500 150,400 0,100 Z" opacity="0.8" />
        </svg>
      </div>


      {/* --- Cartão Principal --- */}
      <motion.div 
        initial={{ opacity: 0, scale: 0.9, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="relative z-10 w-full max-w-5xl bg-trasparent rounded-3xl shadow-2xl flex overflow-hidden min-h-[600px] m-4"
      >
        
        {/* --- Lado Esquerdo (Formulário) --- */}
        <div className="w-full md:w-2/5 p-8 md:p-12 flex flex-col justify-center relative bg-white/100">
          
          <div className="max-w-md mx-auto w-full">
            {/* Logo */}
            <motion.div 
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.2 }}
              className="mb-12"
            >
              <h1 className="text-4xl font-black text-gray-800 tracking-widest uppercase font-mono" style={{ fontFamily: "'Impact', sans-serif" }}>
                INTEGRA AI
              </h1>
              <div className="h-1 w-12 bg-teal-600 mt-2 rounded-full"></div>
              <p className="text-sm text-gray-400 mt-2 tracking-widest uppercase">ERP | Gestão Empresarial</p>
            </motion.div>

            {/* Formulário */}
            <form onSubmit={handleSubmit} className="space-y-6">
              
              <motion.div 
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.3 }}
              >
                <label className="block text-xs font-bold text-gray-500 uppercase mb-2 ml-1">Email</label>
                <div className="relative group">
                  <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-gray-400 group-focus-within:text-teal-400 transition-colors">
                    <User size={20} />
                  </div>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    placeholder="teste@gmail.com"
                    className="w-full pl-12 pr-4 py-4 bg-[#1e293b] text-white placeholder-gray-500 rounded-2xl focus:outline-none focus:ring-2 focus:ring-teal-500 border border-transparent transition-all duration-300"
                  />
                </div>
              </motion.div>

              <motion.div 
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.4 }}
              >
                <label className="block text-xs font-bold text-gray-500 uppercase mb-2 ml-1">Senha</label>
                <div className="relative group">
                  <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-gray-400 group-focus-within:text-teal-400 transition-colors">
                    <Lock size={20} />
                  </div>
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    placeholder="••••••••"
                    className="w-full pl-12 pr-4 py-4 bg-[#1e293b] text-white placeholder-gray-500 rounded-2xl focus:outline-none focus:ring-2 focus:ring-teal-500 border border-transparent transition-all duration-300"
                  />
                </div>
              </motion.div>

              {error && (
                <motion.div 
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  className="text-red-500 text-sm text-center font-medium bg-red-50 p-2 rounded-lg border border-red-100"
                >
                  {error}
                </motion.div>
              )}

              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.5 }}
                type="submit"
                disabled={loading}
                className="w-full py-4 bg-[#0f5862] hover:bg-[#0b454d] text-white font-bold rounded-full shadow-lg hover:shadow-xl transition-all duration-300 flex items-center justify-center space-x-2 group"
              >
                <span>{loading ? 'Acessando...' : 'Entrar'}</span>
                {!loading && <ArrowRight size={18} className="group-hover:translate-x-1 transition-transform" />}
              </motion.button>
            </form>

            <motion.p 
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.8 }}
              className="mt-12 text-center text-xs text-gray-400"
            >
              Desenvolvido por <span className="font-bold text-teal-700">CJS Soluções</span>
            </motion.p>
          </div>
        </div>

        {/* --- Lado Direito (Visual/Ilustração) --- */}
        <div className="hidden md:flex w-3/5 relative bg-white items-center justify-center overflow-hidden">
          
          {/* Mancha Verde-Azulada de Fundo */}
          <motion.div 
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ duration: 0.8, delay: 0.2 }}
            className="absolute w-[100%] h-[100%] bg-gradient-to-br from-teal-600 to-[#0e4b55] rounded-[100%] transform rotate-12 translate-x-20"
            style={{ 
              borderRadius: '63% 37% 39% 61% / 46% 56% 44% 54%',
              boxShadow: 'inset 20px 20px 60px rgba(0,0,0,0.1)'
            }}
          />
          
          {/* Ilustração Laptop */}
          <motion.div
            className="relative z-10 w-3/4 max-w-sm"
            animate={{ 
              y: [0, -15, 0],
            }}
            transition={{ 
              duration: 6, 
              repeat: Infinity,
              ease: "easeInOut" 
            }}
          >
            <LaptopIllustration />
          </motion.div>

          {/* Partículas flutuantes decorativas */}
          <div className="absolute inset-0 z-0 opacity-30">
             {[...Array(5)].map((_, i) => (
                <motion.div
                  key={i}
                  className="absolute bg-white rounded-full opacity-20"
                  style={{
                    width: Math.random() * 50 + 20,
                    height: Math.random() * 50 + 20,
                    left: `${Math.random() * 100}%`,
                    top: `${Math.random() * 100}%`
                  }}
                  animate={{
                    y: [0, -100],
                    opacity: [0.2, 0]
                  }}
                  transition={{
                    duration: Math.random() * 5 + 5,
                    repeat: Infinity,
                    ease: "linear",
                    delay: Math.random() * 2
                  }}
                />
             ))}
          </div>

        </div>
      </motion.div>
    </div>
  );
};

export default Login;