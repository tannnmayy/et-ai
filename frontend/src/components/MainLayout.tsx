import React, { useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import TopNav from './TopNav';
import Sidebar from './Sidebar';

export type AppRole = 'admin' | 'citizen';

export default function MainLayout() {
  const location = useLocation();
  const navigate = useNavigate();

  const [language, setLanguage] = useState<'EN' | 'HI' | 'KN'>('EN');

  // Role is derived from the route so refresh / deep links stay consistent.
  const role: AppRole = location.pathname.startsWith('/citizen') ? 'citizen' : 'admin';

  const setRole = (next: AppRole) => {
    if (next === 'citizen') {
      navigate('/citizen');
    } else {
      navigate('/');
    }
  };

  const getActiveTab = () => {
    const path = location.pathname;
    if (path.startsWith('/citizen')) return 'citizen';
    if (path === '/' || path.includes('/map')) return 'map';
    if (path.includes('/enforcement')) return 'enforcement';
    if (path.includes('/copilot')) return 'copilot';
    if (path.includes('/neighbourhoods')) return 'neighbourhoods';
    return 'map';
  };

  const handleTabChange = (tab: string) => {
    if (tab === 'citizen') {
      navigate('/citizen');
      return;
    }
    if (tab === 'map') {
      navigate('/');
    } else {
      navigate(`/${tab}`);
    }
  };

  const isCitizen = role === 'citizen';

  return (
    <div className="w-screen h-screen flex flex-col bg-black text-white overflow-hidden font-sans select-none">
      <TopNav
        activeTab={getActiveTab()}
        setActiveTab={handleTabChange}
        language={language}
        setLanguage={setLanguage}
        role={role}
        setRole={setRole}
      />

      <div className="flex-1 flex mt-16 h-[calc(100vh-64px)] overflow-hidden">
        {/* Admin ops sidebar only — citizen mode has its own step sidebar inside the page */}
        {!isCitizen && (
          <Sidebar activeTab={getActiveTab()} setActiveTab={handleTabChange} />
        )}

        <main
          className={`flex-grow h-full overflow-hidden bg-black relative animate-fade-in ${
            isCitizen ? 'ml-0' : 'ml-64'
          }`}
        >
          <Outlet />
        </main>
      </div>
    </div>
  );
}
