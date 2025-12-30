import React from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';

const Dashboard = () => {
  const { logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-gray-100">
      <div className="p-8 bg-white rounded-lg shadow-md text-center">
        <h1 className="text-2xl font-bold text-gray-900 mb-4">
          Bem-vindo ao ERP!
        </h1>
        <p className="text-gray-700 mb-6">
          Você está logado. (Dashboard em construção)
        </p>
        <button
          onClick={handleLogout}
          className="px-4 py-2 font-medium text-white bg-red-600 rounded-md hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500"
        >
          Sair
        </button>
      </div>
    </div>
  );
};

export default Dashboard;
