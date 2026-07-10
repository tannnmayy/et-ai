import React from 'react';
import { Map, Shield, Bot, Building2 } from 'lucide-react';

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
}

export default function Sidebar({ activeTab, setActiveTab }: SidebarProps) {
  const menuItems = [
    { id: 'map', label: 'Map', icon: Map },
    { id: 'enforcement', label: 'Enforcement', icon: Shield },
    { id: 'copilot', label: 'Copilot', icon: Bot },
    { id: 'neighbourhoods', label: 'Neighbourhoods', icon: Building2 },
  ];

  return (
    <aside className="fixed left-0 top-16 h-[calc(100vh-64px)] w-64 bg-apple-bg border-r border-apple-border flex flex-col p-4 z-40">
      {/* Shift Header Section */}
      <div className="flex items-center gap-3 mb-8 p-3 bg-apple-card/30 rounded-xl border border-apple-border/20">
        <div className="w-10 h-10 rounded-xl bg-brand-blue/10 border border-brand-blue/20 flex items-center justify-center text-brand-blue">
          <Shield size={18} />
        </div>
        <div>
          <div className="text-[14px] font-bold text-white font-sans leading-tight">
            Sentinel Ops
          </div>
          <div className="text-[10px] text-brand-orange uppercase tracking-wider font-mono font-medium mt-0.5">
            Shift Alpha
          </div>
        </div>
      </div>

      {/* Navigation List */}
      <nav className="flex flex-col gap-1.5 flex-1">
        {menuItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id || (item.id === 'neighbourhoods' && activeTab === 'coming-soon');
          return (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`flex items-center gap-3 px-4 py-3 rounded-xl text-xs font-semibold uppercase tracking-wider transition-all duration-200 group ${
                isActive
                  ? 'bg-brand-blue text-white shadow-lg shadow-brand-blue/10 font-bold'
                  : 'text-apple-secondary hover:bg-apple-card hover:text-white border border-transparent'
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

      {/* Bottom Footer Details */}
      <div className="p-3 border-t border-apple-border/50 text-[10px] font-mono text-apple-secondary flex flex-col gap-1">
        <div>SYSTEM STATUS: ACTIVE</div>
        <div>STATIONS LOGGED: 7</div>
        <div className="text-brand-green flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-brand-green animate-pulse" />
          SECURE PROTOCOL V1
        </div>
      </div>
    </aside>
  );
}
