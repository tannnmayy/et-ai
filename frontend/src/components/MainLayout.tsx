import React from 'react';
import { Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom';
import TopNav from './TopNav';
import Sidebar from './Sidebar';
import { useSession } from '../context/SessionContext';

export default function MainLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { isAuthenticated, session } = useSession();

  if (!isAuthenticated) {
    return <Navigate to="/welcome" replace state={{ from: location.pathname }} />;
  }

  const isCitizen = session?.role === 'citizen' || location.pathname.startsWith('/citizen');

  const getActiveTab = () => {
    const path = location.pathname;
    if (path.startsWith('/citizen')) return 'citizen';
    if (path.startsWith('/dispatch')) return 'enforcement';
    if (path === '/' || path.includes('/map')) return 'map';
    if (path.includes('/enforcement')) return 'enforcement';
    if (path.includes('/copilot')) return 'copilot';
    if (path.includes('/neighbourhoods')) return 'neighbourhoods';
    if (path.includes('/insights')) return 'insights';
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

  return (
    <div className="w-screen h-screen flex flex-col bg-black text-white overflow-hidden font-sans select-none antialiased">
      <TopNav activeTab={getActiveTab()} setActiveTab={handleTabChange} />

      <div className="flex-1 flex mt-16 h-[calc(100vh-64px)] overflow-hidden">
        {!isCitizen && (
          <Sidebar activeTab={getActiveTab()} setActiveTab={handleTabChange} />
        )}

        {/* App chrome stays solid black; glass is reserved for elevated panels inside views */}
        <main
          className={`flex-grow h-full overflow-hidden bg-black relative ${
            isCitizen ? 'ml-0' : 'ml-64'
          }`}
        >
          <Outlet />
        </main>
      </div>
    </div>
  );
}
