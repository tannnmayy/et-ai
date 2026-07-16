import React from 'react';
import { Map, Shield, Bot, Building2, BarChart3 } from 'lucide-react';
import { useSession } from '../context/SessionContext';

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
}

const menuItems = [
  { id: 'map', label: 'Map', icon: Map },
  { id: 'enforcement', label: 'Enforcement', icon: Shield },
  { id: 'copilot', label: 'Copilot', icon: Bot },
  { id: 'neighbourhoods', label: 'Neighbourhoods', icon: Building2 },
  { id: 'insights', label: 'Insights', icon: BarChart3 },
] as const;

export default function Sidebar({ activeTab, setActiveTab }: SidebarProps) {
  const { session, roleLabel } = useSession();
  const role = session?.role ?? 'guest';

  return (
    <aside className="fixed left-0 top-16 h-[calc(100vh-64px)] w-64 bg-black/80 backdrop-blur-xl border-r border-white/10 flex flex-col p-4 z-40">
      <div className="flex items-center gap-3 mb-8 p-3 rounded-2xl ui-glass ui-glass-subtle">
        <div className="w-10 h-10 rounded-xl bg-brand-blue/15 border border-brand-blue/25 flex items-center justify-center text-brand-blue">
          <Shield size={18} />
        </div>
        <div className="min-w-0">
          <div className="text-[13px] font-bold text-white font-sans leading-tight truncate">
            Sentinel Ops
          </div>
          <div className="text-[10px] text-brand-orange uppercase tracking-wider font-mono font-medium mt-0.5 truncate">
            {roleLabel(role)}
          </div>
        </div>
      </div>

      <nav className="flex flex-col gap-1.5 flex-1">
        {menuItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => setActiveTab(item.id)}
              className={`flex items-center gap-3 px-4 py-3.5 min-h-[48px] rounded-2xl text-xs font-semibold uppercase tracking-wider transition-all duration-200 group ${
                isActive
                  ? 'bg-brand-blue text-white shadow-lg shadow-brand-blue/20 font-bold'
                  : 'text-apple-secondary hover:bg-white/5 hover:text-white border border-transparent hover:border-white/10'
              }`}
            >
              <Icon
                size={16}
                className={`transition-colors ${
                  isActive ? 'text-white' : 'text-apple-secondary group-hover:text-white'
                }`}
              />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="p-3 border-t border-white/10 text-[10px] font-mono text-apple-secondary flex flex-col gap-1">
        <div>SYSTEM STATUS: ACTIVE</div>
        <div className="truncate">USER: {(session?.name || 'GUEST').toUpperCase()}</div>
        <div className="text-brand-green flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-brand-green animate-pulse" />
          SECURE PROTOCOL V1
        </div>
      </div>
    </aside>
  );
}
