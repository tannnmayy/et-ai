import React, { useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import TopNav from './TopNav';
import Sidebar from './Sidebar';

export default function MainLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  
  const [language, setLanguage] = useState<'EN' | 'HI' | 'KN'>('EN');
  const [role, setRole] = useState<'admin' | 'citizen'>('admin');

  // Map the current pathname to active tab
  const getActiveTab = () => {
    const path = location.pathname;
    if (path === '/' || path.includes('/map')) return 'map';
    if (path.includes('/enforcement')) return 'enforcement';
    if (path.includes('/copilot')) return 'copilot';
    if (path.includes('/neighbourhoods')) return 'neighbourhoods';
    return 'map';
  };

  const handleTabChange = (tab: string) => {
    if (tab === 'map') {
      navigate('/');
    } else {
      navigate(`/${tab}`);
    }
  };

  return (
    <div className="w-screen h-screen flex flex-col bg-black text-white overflow-hidden font-sans select-none">
      {/* Shared Top Navbar */}
      <TopNav
        activeTab={getActiveTab()}
        setActiveTab={handleTabChange}
        language={language}
        setLanguage={setLanguage}
        role={role}
        setRole={setRole}
      />

      {/* Shared Layout Shell */}
      <div className="flex-1 flex mt-16 h-[calc(100vh-64px)] overflow-hidden">
        {/* Shared Sidebar Navbar */}
        <Sidebar activeTab={getActiveTab()} setActiveTab={handleTabChange} />

        {/* Core Main Action Stage */}
        <main className="flex-grow ml-64 h-full overflow-hidden bg-black relative animate-fade-in">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
