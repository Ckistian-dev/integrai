import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import api from '../api/axiosConfig';
import { 
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, 
  PieChart, Pie, Cell, Legend 
} from 'recharts';
import { 
  DollarSign, ShoppingBag, TrendingUp, TrendingDown, 
  AlertCircle, Package, Calendar, LogOut 
} from 'lucide-react';

const Dashboard = () => {
  const { logout } = useAuth();
  const navigate = useNavigate();
  
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [dateRange, setDateRange] = useState({
    start: new Date(new Date().setDate(new Date().getDate() - 30)).toISOString().split('T')[0],
    end: new Date().toISOString().split('T')[0]
  });
  const [selectedPeriod, setSelectedPeriod] = useState('30days');

  // Cores para o gráfico de Pizza
  const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8'];

  useEffect(() => {
    fetchDashboardData();
  }, [dateRange]);

  const fetchDashboardData = async () => {
    setLoading(true);
    try {
      // O axiosConfig já define a baseURL e injeta o token automaticamente
      const response = await api.get('/dashboard/stats', {
        params: {
          start_date: dateRange.start,
          end_date: dateRange.end
        }
      });

      setData(response.data);
    } catch (error) {
      console.error("Erro de conexão:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const formatCurrency = (value) => {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value);
  };

  const handlePeriodChange = (e) => {
    const period = e.target.value;
    setSelectedPeriod(period);

    if (period === 'custom') return;

    const end = new Date();
    let start = new Date();

    switch (period) {
      case 'today':
        // start is today
        break;
      case '7days':
        start.setDate(end.getDate() - 7);
        break;
      case '30days':
        start.setDate(end.getDate() - 30);
        break;
      case 'thisMonth':
        start = new Date(end.getFullYear(), end.getMonth(), 1);
        break;
      default:
        break;
    }

    setDateRange({
      start: start.toISOString().split('T')[0],
      end: end.toISOString().split('T')[0]
    });
  };

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-center mb-8 bg-white p-4 rounded-lg shadow-sm">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Dashboard Geral</h1>
          <p className="text-gray-500 text-sm">Visão geral do seu negócio</p>
        </div>
        
        <div className="flex items-center gap-4 mt-4 md:mt-0">
          <select 
            value={selectedPeriod}
            onChange={handlePeriodChange}
            className="bg-white border border-gray-300 text-gray-700 text-sm rounded-md focus:ring-blue-500 focus:border-blue-500 block p-2"
          >
            <option value="today">Hoje</option>
            <option value="7days">Últimos 7 dias</option>
            <option value="30days">Últimos 30 dias</option>
            <option value="thisMonth">Este Mês</option>
            <option value="custom">Personalizado</option>
          </select>

          <div className="flex items-center bg-gray-100 rounded-md p-2">
            <Calendar className="w-4 h-4 text-gray-500 mr-2" />
            <input 
              type="date" 
              value={dateRange.start}
              onChange={(e) => {
                setDateRange({...dateRange, start: e.target.value});
                setSelectedPeriod('custom');
              }}
              className="bg-transparent text-sm focus:outline-none text-gray-700"
            />
            <span className="mx-2 text-gray-400">até</span>
            <input 
              type="date" 
              value={dateRange.end}
              onChange={(e) => {
                setDateRange({...dateRange, end: e.target.value});
                setSelectedPeriod('custom');
              }}
              className="bg-transparent text-sm focus:outline-none text-gray-700"
            />
          </div>
          
          <button
            onClick={handleLogout}
            className="flex items-center px-4 py-2 text-sm font-medium text-red-600 bg-red-50 rounded-md hover:bg-red-100 transition-colors"
          >
            <LogOut className="w-4 h-4 mr-2" />
            Sair
          </button>
        </div>
      </div>

      {/* Cards de Resumo */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        {/* Card Receita */}
        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100">
          <div className="flex justify-between items-start">
            <div>
              <p className="text-sm font-medium text-gray-500">Receita Total</p>
              <h3 className="text-2xl font-bold text-gray-800 mt-1">
                {formatCurrency(data?.summary.revenue || 0)}
              </h3>
            </div>
            <div className="p-2 bg-blue-50 rounded-lg">
              <DollarSign className="w-6 h-6 text-blue-600" />
            </div>
          </div>
          <div className="mt-4 text-sm text-gray-500">
            <span className="text-blue-600 font-medium">{data?.summary.orders}</span> pedidos no período
          </div>
        </div>

        {/* Card A Receber */}
        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100">
          <div className="flex justify-between items-start">
            <div>
              <p className="text-sm font-medium text-gray-500">A Receber</p>
              <h3 className="text-2xl font-bold text-green-600 mt-1">
                {formatCurrency(data?.summary.to_receive || 0)}
              </h3>
            </div>
            <div className="p-2 bg-green-50 rounded-lg">
              <TrendingUp className="w-6 h-6 text-green-600" />
            </div>
          </div>
          <div className="mt-4 text-sm text-gray-500">Previsão de entrada</div>
        </div>

        {/* Card A Pagar */}
        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100">
          <div className="flex justify-between items-start">
            <div>
              <p className="text-sm font-medium text-gray-500">A Pagar</p>
              <h3 className="text-2xl font-bold text-red-600 mt-1">
                {formatCurrency(data?.summary.to_pay || 0)}
              </h3>
            </div>
            <div className="p-2 bg-red-50 rounded-lg">
              <TrendingDown className="w-6 h-6 text-red-600" />
            </div>
          </div>
          <div className="mt-4 text-sm text-gray-500">Previsão de saída</div>
        </div>

        {/* Card Saldo Líquido */}
        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100">
          <div className="flex justify-between items-start">
            <div>
              <p className="text-sm font-medium text-gray-500">Saldo Previsto</p>
              <h3 className={`text-2xl font-bold mt-1 ${data?.summary.net_balance >= 0 ? 'text-gray-800' : 'text-red-600'}`}>
                {formatCurrency(data?.summary.net_balance || 0)}
              </h3>
            </div>
            <div className="p-2 bg-purple-50 rounded-lg">
              <ShoppingBag className="w-6 h-6 text-purple-600" />
            </div>
          </div>
          <div className="mt-4 text-sm text-gray-500">Receitas - Despesas</div>
        </div>
      </div>

      {/* Gráfico de Evolução de Vendas */}
      <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 mb-8">
        <h3 className="text-lg font-semibold text-gray-800 mb-4">Evolução das Vendas</h3>
        <div className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data?.charts.sales_evolution}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="date" axisLine={false} tickLine={false} />
              <YAxis axisLine={false} tickLine={false} />
              <Tooltip formatter={(value) => formatCurrency(value)} cursor={{ fill: '#f3f4f6' }} />
              <Bar dataKey="value" fill="#3B82F6" radius={[4, 4, 0, 0]} name="Vendas" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Gráficos e Tabelas */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        
        {/* Gráfico de Pizza - Status dos Pedidos */}
        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 lg:col-span-1">
          <h3 className="text-lg font-semibold text-gray-800 mb-4">Status dos Pedidos</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={data?.charts.orders_by_status}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={80}
                  fill="#8884d8"
                  paddingAngle={5}
                  dataKey="value"
                >
                  {data?.charts.orders_by_status.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Tabela de Pedidos Recentes */}
        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 lg:col-span-2">
          <h3 className="text-lg font-semibold text-gray-800 mb-4">Últimos Pedidos</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-gray-700 uppercase bg-gray-50">
                <tr>
                  <th className="px-4 py-3">ID</th>
                  <th className="px-4 py-3">Cliente</th>
                  <th className="px-4 py-3">Data</th>
                  <th className="px-4 py-3">Valor</th>
                  <th className="px-4 py-3">Status</th>
                </tr>
              </thead>
              <tbody>
                {data?.recent_orders.map((order) => (
                  <tr key={order.id} className="border-b hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium">#{order.id}</td>
                    <td className="px-4 py-3">{order.cliente}</td>
                    <td className="px-4 py-3">{new Date(order.data).toLocaleDateString()}</td>
                    <td className="px-4 py-3">{formatCurrency(order.total)}</td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                        {order.situacao}
                      </span>
                    </td>
                  </tr>
                ))}
                {data?.recent_orders.length === 0 && (
                  <tr><td colSpan="5" className="text-center py-4 text-gray-500">Nenhum pedido recente.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Alerta de Estoque Baixo */}
      <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100">
        <div className="flex items-center mb-4">
          <AlertCircle className="w-5 h-5 text-orange-500 mr-2" />
          <h3 className="text-lg font-semibold text-gray-800">Alerta de Estoque Baixo (Top 5)</h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {data?.low_stock.map((item, idx) => (
            <div key={idx} className="flex items-center p-3 bg-orange-50 rounded-lg border border-orange-100">
              <Package className="w-8 h-8 text-orange-400 mr-3" />
              <div>
                <p className="font-medium text-gray-800">{item.produto}</p>
                <p className="text-sm text-gray-600">SKU: {item.sku} | Qtd: <span className="font-bold text-red-600">{item.quantidade}</span></p>
              </div>
            </div>
          ))}
          {data?.low_stock.length === 0 && (
            <p className="text-gray-500 text-sm">Nenhum produto com estoque crítico.</p>
          )}
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
