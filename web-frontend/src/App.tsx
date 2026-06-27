import React, { useState, useEffect } from 'react';
import LeafletMap from './components/LeafletMap';
import AuthOverlay from './components/AuthOverlay';
import ProfessionalLanding from './components/ProfessionalLanding';
import { SubtleParticles } from './components/SubtleParticles';
import ComplaintModal from './components/ComplaintModal';
import MyComplaints from './components/MyComplaints';
import EnterpriseAdminDashboard from './pages/EnterpriseAdminDashboard';
import UserProfilePage from './pages/UserProfile';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

export default function App() {
  const [session, setSession] = useState<any>(null);
  const [userProfile, setUserProfile] = useState<any>(null);
  const [showAdminDashboard, setShowAdminDashboard] = useState<boolean>(false);
  const [showUserProfile, setShowUserProfile] = useState<boolean>(false);
  const [wards, setWards] = useState<any[]>([]);
  const [recs, setRecs] = useState<any[]>([]);
  const [selectedWard, setSelectedWard] = useState<any | null>(null);
  const [geeData, setGeeData] = useState<any | null>(null);
  const [geeLoading, setGeeLoading] = useState<boolean>(false);
  const [geeError, setGeeError] = useState<string | null>(null);
  const [forecast, setForecast] = useState<any[]>([]);
  const [forecastError, setForecastError] = useState<string | null>(null);
  const [wardsError, setWardsError] = useState<string | null>(null);
  const [granularity, setGranularity] = useState<'ward'|'district'>('ward');
  const [showLanding, setShowLanding] = useState<boolean>(true);
  const [showComplaintModal, setShowComplaintModal] = useState(false);

  useEffect(() => {
    if (!selectedWard) {
        setGeeData(null);
        setForecast([]);
        return;
    }
    const API_BASE = import.meta.env.VITE_API_URL || "http://127.0.0.1:8080";
    
    async function fetchGEE() {
        setGeeLoading(true);
        setGeeError(null);
        const start = Date.now();
        try {
            const res = await fetch(`${API_BASE}/api/v1/gee/analyze?lat=${selectedWard.lat}&lon=${selectedWard.lon}`);
            const elapsed = Date.now() - start;
            console.log(`[App] GET /gee/analyze → ${res.status} in ${elapsed}ms`);
            if (!res.ok) throw new Error(`Satellite API returned ${res.status}`);
            setGeeData(await res.json());
        } catch (e: any) {
            setGeeError(e.message || 'Satellite data unavailable');
            setGeeData(null);
        } finally {
            setGeeLoading(false);
        }
    }
    
    async function fetchForecast() {
        setForecastError(null);
        try {
            const res = await fetch(`${API_BASE}/api/v1/dashboard/forecast?lat=${selectedWard.lat}&lon=${selectedWard.lon}`);
            if (!res.ok) throw new Error(`Forecast API returned ${res.status}`);
            const data = await res.json();
            const formatted = data.map((d: any) => ({
                ...d,
                day: new Date(d.time).toLocaleDateString('en-US', { weekday: 'short' })
            }));
            setForecast(formatted);
        } catch (e: any) {
            setForecastError(e.message || 'Forecast unavailable');
            setForecast([]);
        }
    }
    
    fetchGEE();
    fetchForecast();
  }, [selectedWard]);

  useEffect(() => {
    async function fetchDashboardData() {
      setWardsError(null);
      const start = Date.now();
      try {
        const API_BASE = import.meta.env.VITE_API_URL || "http://127.0.0.1:8080";
        const statsRes = await fetch(`${API_BASE}/api/v1/dashboard/wards?level=${granularity}`);
        const elapsed = Date.now() - start;
        console.log(`[App] GET /dashboard/wards → ${statsRes.status} in ${elapsed}ms`);
        if (!statsRes.ok) throw new Error(`Ward data API returned ${statsRes.status}`);
        setWards(await statsRes.json());
        
        // Fetch AI Policy Recommendations (non-critical, don't block UI)
        try {
          console.log('[App] Fetching policy recommendations...');
          const recsRes = await fetch(`${API_BASE}/api/v1/dashboard/recommendations`);
          console.log(`[App] GET /dashboard/recommendations → ${recsRes.status}`);
          if (recsRes.ok) {
            const recsData = await recsRes.json();
            console.log(`[App] Received ${recsData.length} recommendations`);
            setRecs(recsData);
          } else {
            console.warn(`[App] Recommendations API returned ${recsRes.status}`);
          }
        } catch (err) {
          console.error('[App] Failed to fetch recommendations:', err);
          /* non-critical, ticker will show loading state */
        }
      } catch (e: any) {
        setWardsError(e.message || 'Failed to load ward data from backend.');
      }
    }
    fetchDashboardData();
    
    // Set 60-second polling for live presentation
    const interval = setInterval(fetchDashboardData, 60000);
    return () => clearInterval(interval);
  }, [granularity]);

  // HACKATHON RBAC: Auto-lock Citizen to their assigned ward upon load
  useEffect(() => {
    if (userProfile?.role === 'citizen' && wards.length > 0 && !selectedWard) {
        const home = wards.find(w => w.name === userProfile.home_ward);
        if (home) setSelectedWard(home);
    }
  }, [userProfile, wards, selectedWard]);

  const handleWardClick = (ward: any) => {
    if (userProfile?.role === 'citizen' && ward.name !== userProfile.home_ward) {
        window.alert(`Restricted Protocol: As a registered Citizen, your clearance is locked to analyzing your home ward (${userProfile.home_ward}). Escalate to a Mayor or Ward Member 'Admin' account for holistic city tracking.`);
        return;
    }
    setSelectedWard(ward);
  };

  const avgAqi = wards.length > 0 ? Math.round(wards.reduce((acc, curr) => acc + curr.aqi, 0) / wards.length) : 0;

  if (showLanding) {
    return <ProfessionalLanding onLaunch={() => setShowLanding(false)} />;
  }

  if (showAdminDashboard) {
    return <EnterpriseAdminDashboard userProfile={userProfile} session={session} onBack={() => setShowAdminDashboard(false)} />;
  }

  if (showUserProfile) {
    return <UserProfilePage userProfile={userProfile} session={session} onBack={() => setShowUserProfile(false)} />;
  }

  return (
    <div className="bg-slate-950 text-slate-50 font-sans flex flex-col relative w-screen min-h-screen overflow-hidden">
      
      {/* Subtle Particle Background */}
      <SubtleParticles density={40} speed={0.15} opacity={0.25} />
      
      {/* ComplaintModal — real DB submission */}
      {showComplaintModal && (
        <ComplaintModal
          ward={selectedWard}
          userProfile={userProfile}
          onClose={() => setShowComplaintModal(false)}
        />
      )}

      {/* UserProfile Page */}
      {showUserProfile && (
        <UserProfilePage
          userProfile={userProfile}
          session={session}
          onBack={() => setShowUserProfile(false)}
        />
      )}

      {/* ─── Supabase Native Auth Gateway ─── */}
      <AuthOverlay session={session} setSession={setSession} userProfile={userProfile} setUserProfile={setUserProfile} />

      {/* TopNavBar - Minimal, Clean */}
      <header className="fixed top-0 left-0 right-0 z-40 bg-slate-950/80 backdrop-blur-xl border-b border-slate-800/50 h-16">
        <div className="max-w-[1920px] mx-auto px-8 h-full flex items-center justify-between">
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="w-8 h-0.5 bg-gradient-to-r from-blue-500 to-transparent" />
            <div>
              <h1 className="font-light text-lg tracking-tight uppercase">VayuDrishti</h1>
              <p className="text-[9px] text-slate-500 uppercase tracking-widest">Atmospheric Command</p>
            </div>
          </div>
          
          {/* Navigation */}
          <nav className="hidden md:flex items-center gap-8 h-full">
            <button 
              onClick={() => { setGranularity('district'); setSelectedWard(null); setWards([]); }}
              className={`font-mono text-[11px] uppercase tracking-wider h-full flex items-center transition-all border-b-2 ${
                granularity === 'district' 
                  ? 'text-blue-400 border-blue-400' 
                  : 'text-slate-500 border-transparent hover:text-slate-300'
              }`}>
              District View
            </button>
            <button 
              onClick={() => { setGranularity('ward'); setSelectedWard(null); setWards([]); }}
              className={`font-mono text-[11px] uppercase tracking-wider h-full flex items-center transition-all border-b-2 ${
                granularity === 'ward' 
                  ? 'text-blue-400 border-blue-400' 
                  : 'text-slate-500 border-transparent hover:text-slate-300'
              }`}>
              Ward View
            </button>
          </nav>
          
          {/* User Section */}
          <div className="flex items-center gap-4">
            {userProfile?.role === 'admin' && (
              <button
                onClick={() => setShowAdminDashboard(true)}
                className="flex items-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-semibold uppercase tracking-wide transition-all shadow-lg hover:shadow-xl hover:scale-105 border-2 border-blue-400"
              >
                <span className="material-symbols-outlined text-lg">admin_panel_settings</span>
                <span>Admin Dashboard</span>
              </button>
            )}
            {userProfile && userProfile.role !== 'admin' && (
              <button
                onClick={() => setShowUserProfile(true)}
                className="flex items-center gap-3 bg-slate-800 hover:bg-slate-700 px-5 py-3 rounded-lg border-2 border-slate-600 hover:border-slate-500 transition-all shadow-lg cursor-pointer"
              >
                <div className="w-9 h-9 rounded-full bg-blue-600 flex items-center justify-center text-white text-base font-bold uppercase border-2 border-blue-400">
                  {userProfile.full_name?.charAt(0) || userProfile.email?.charAt(0) || 'U'}
                </div>
                <div className="flex flex-col">
                  <span className="text-sm font-semibold text-white">{userProfile.full_name || 'User'}</span>
                  <span className="text-xs text-blue-400 uppercase tracking-wider font-mono">{userProfile.role}</span>
                </div>
              </button>
            )}
          </div>
        </div>
      </header>

      <main className="flex-1 mt-16 flex overflow-hidden relative">
        {/* Central Canvas */}
        <section className="flex-1 relative flex flex-col overflow-hidden">
          
          {/* Central Map Area */}
          <div className="flex-1 relative bg-slate-950 overflow-hidden">
             <div className="absolute inset-0 z-0">
               <LeafletMap wards={wards} selectedWard={selectedWard} onWardClick={handleWardClick} granularity={granularity} />
             </div>
             <div className="absolute inset-0 pointer-events-none shadow-[inset_0_0_100px_rgba(2,6,23,0.8)] z-10"></div>
             
             {/* Asthma Safety Protocol */}
             {userProfile?.has_asthma && selectedWard?.aqi > 200 && (
                <div className="absolute top-8 left-1/2 -translate-x-1/2 z-[1001] pointer-events-none">
                  <div className="px-6 py-3 bg-red-950/90 border border-red-500/50 rounded flex items-center gap-4 backdrop-blur-md">
                    <span className="material-symbols-outlined text-red-400 text-2xl">warning</span>
                    <div className="flex flex-col">
                      <span className="text-red-400 font-mono text-[10px] uppercase tracking-wider">Asthma Protocol Active</span>
                      <span className="text-white text-xs">AQI {selectedWard.aqi} in {selectedWard.name}</span>
                    </div>
                  </div>
                </div>
              )}

             {/* Data Error State */}
             {wardsError && (
               <div className="absolute top-8 left-8 z-20 bg-slate-900/90 border border-slate-700 rounded p-4 max-w-md backdrop-blur-md">
                 <div className="flex items-start gap-3">
                   <span className="material-symbols-outlined text-yellow-400">warning</span>
                   <div>
                     <p className="text-xs font-mono text-yellow-400 uppercase tracking-wider mb-1">Data Source Error</p>
                     <p className="text-xs text-slate-400">{wardsError}</p>
                   </div>
                 </div>
               </div>
             )}
          </div>
          
          {/* Bottom Status Bar */}
          {userProfile?.role === 'admin' && (
            <footer className="h-14 bg-slate-950/90 backdrop-blur-xl border-t border-slate-800/50 flex items-center px-8 gap-8 relative z-20">
              <div className="shrink-0 flex items-center gap-3 border-r border-slate-800 pr-6">
                <span className="material-symbols-outlined text-blue-400 text-sm">public</span>
                <span className="font-mono text-[10px] uppercase tracking-wider text-slate-400">Live Intelligence Feed</span>
              </div>
              <div className="flex-1 overflow-hidden">
                <div className="flex gap-12 animate-marquee whitespace-nowrap items-center hover:[animation-play-state:paused]">
                  {recs.length > 0 ? recs.map((rec, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <span className={`w-1.5 h-1.5 rounded-full ${rec.urgency === 'High' ? 'bg-red-400' : 'bg-blue-400'}`}></span>
                      <span className="font-mono text-xs text-slate-400">
                        <span className="text-slate-200">[{rec.ward}]</span> {rec.action}
                      </span>
                    </div>
                  )) : (
                     <span className="font-mono text-xs text-slate-600">Awaiting intelligence data...</span>
                  )}
                </div>
              </div>
              <div className="font-mono text-[9px] uppercase tracking-wider text-slate-600 ml-auto pl-8 border-l border-slate-800 shrink-0">
                  VayuDrishti System
              </div>
            </footer>
          )}
        </section>

        {/* Right Side Panel - Clean, Minimal Design */}
        <aside className="w-[420px] bg-slate-950/90 backdrop-blur-xl border-l border-slate-800/50 p-8 flex flex-col gap-6 overflow-y-auto z-20 shrink-0 relative no-scrollbar">
          
          {selectedWard ? (
             <div className="flex flex-col h-full animate-fade-in relative">
                
                {/* Ward Header */}
                <div className="flex justify-between items-start mb-6 relative z-10">
                    <div className="flex flex-col">
                        <span className="font-mono text-[10px] tracking-wider uppercase text-blue-400 mb-2">Selected Zone</span>
                        <h2 className="text-3xl font-light tracking-tight text-white">{selectedWard.name}</h2>
                    </div>
                    <button 
                      onClick={() => setSelectedWard(null)} 
                      className="p-2 bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-white rounded transition-all"
                    >
                        <span className="material-symbols-outlined text-sm">close</span>
                    </button>
                </div>

                <div className="flex items-center gap-6 mb-6 bg-slate-900/50 p-6 rounded border border-slate-800">
                    <div className={`text-7xl font-light tracking-tighter ${
                      selectedWard.aqi > 300 ? 'text-red-400' : 'text-blue-400'
                    }`}>
                        {selectedWard.aqi}
                    </div>
                    <div className="flex flex-col gap-2">
                        <span className="font-mono text-[10px] text-slate-500 uppercase tracking-wider">Real-Time AQI</span>
                        <span className={`px-2 py-1 text-[10px] font-mono rounded uppercase tracking-wider ${
                          selectedWard.aqi > 300 
                            ? 'bg-red-500/10 border border-red-500/30 text-red-400' 
                            : 'bg-blue-500/10 border border-blue-500/30 text-blue-400'
                        }`}>
                            {selectedWard.status}
                        </span>
                        <div className="flex items-center gap-2 mt-1">
                           <span className="text-[10px] font-mono text-slate-500 uppercase">PM2.5:</span>
                           <span className="text-sm text-white">{selectedWard.pm25} µg/m³</span>
                        </div>
                    </div>
                </div>

                {/* Chemistry Readout */}
                <div className="grid grid-cols-2 gap-2 mb-6">
                    {[
                        { label: 'PM10', value: selectedWard.pm10, unit: 'µg/m³' },
                        { label: 'NO₂', value: selectedWard.no2, unit: 'µg/m³' },
                        { label: 'SO₂', value: selectedWard.so2, unit: 'µg/m³' },
                        { label: 'CO', value: selectedWard.co, unit: 'mg/m³' },
                    ].map((item, i) => (
                        <div key={i} className="bg-slate-900/50 p-3 rounded border border-slate-800">
                            <span className="font-mono text-[9px] text-slate-500 uppercase tracking-wider block">{item.label}</span>
                            <span className="text-sm text-white">{item.value ?? '—'} <span className="text-[9px] text-slate-500">{item.unit}</span></span>
                        </div>
                    ))}
                </div>

                {/* Satellite Diagnostics */}
                {geeLoading ? (
                    <div className="bg-slate-900/30 border border-slate-800 p-6 rounded flex flex-col items-center justify-center min-h-[140px] mb-6">
                        <span className="material-symbols-outlined text-blue-400 animate-spin text-2xl mb-3">satellite_alt</span>
                        <p className="font-mono text-[10px] text-blue-400 uppercase tracking-wider">Querying satellite...</p>
                    </div>
                ) : geeError ? (
                    <div className="bg-red-500/5 border border-red-500/20 p-4 rounded flex items-start gap-3 mb-6">
                        <span className="material-symbols-outlined text-red-400 text-lg">satellite_alt</span>
                        <div>
                            <p className="text-[10px] font-mono text-red-400 uppercase tracking-wider">Satellite Error</p>
                            <p className="text-xs text-red-400/70 mt-1">{geeError}</p>
                        </div>
                    </div>
                ) : geeData && (
                    <div className="bg-slate-900/30 border border-slate-800 p-6 rounded hover:border-slate-700 transition-all mb-6">
                        <h3 className="font-mono text-[10px] uppercase text-blue-400 tracking-wider mb-4 flex items-center gap-2">
                            <span className="material-symbols-outlined text-sm">insights</span>
                            Satellite Analysis
                        </h3>
                        <div className="space-y-3">
                            <div className="flex justify-between items-center bg-slate-900/80 p-3 rounded border border-slate-800">
                                <span className="font-mono text-slate-400 uppercase text-[10px]">Biomass</span>
                                <span className="text-white text-sm">{geeData.biomass_burning_index} <span className="text-slate-500 text-[10px]">mol/m²</span></span>
                            </div>
                            <div className="flex justify-between items-center bg-slate-900/80 p-3 rounded border border-slate-800">
                                <span className="font-mono text-slate-400 uppercase text-[10px]">Dust</span>
                                <span className="text-white text-sm">{geeData.construction_dust_index} <span className="text-slate-500 text-[10px]">UVAI</span></span>
                            </div>
                            <div className="bg-blue-500/5 border border-blue-500/20 p-3 rounded flex flex-col items-center gap-1">
                                <span className="text-[9px] font-mono text-blue-400 uppercase tracking-wider">Source</span>
                                <span className="text-blue-100 uppercase text-xs font-light">{geeData.dominant_source}</span>
                            </div>
                        </div>
                    </div>
                )}

                {/* 8-Day Forecast */}
                <div className="bg-slate-900/30 p-6 rounded border border-slate-800 flex-1 flex flex-col min-h-[220px]">
                    <h3 className="font-mono text-[10px] uppercase text-green-400 tracking-wider mb-4 flex items-center gap-2">
                        <span className="material-symbols-outlined text-sm">timeline</span>
                        8-Day Forecast
                    </h3>
                    {forecastError ? (
                        <div className="flex-1 flex flex-col items-center justify-center gap-2">
                            <span className="material-symbols-outlined text-slate-600">timeline</span>
                            <p className="text-xs text-slate-500">{forecastError}</p>
                        </div>
                    ) : forecast.length > 0 ? (
                        <div className="flex-1 w-full min-h-0">
                            <ResponsiveContainer width="100%" height="100%">
                                <LineChart data={forecast} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                                    <XAxis dataKey="day" stroke="#64748b" fontSize={9} tickLine={false} axisLine={false} />
                                    <YAxis stroke="#475569" fontSize={9} tickLine={false} axisLine={false} />
                                    <Tooltip 
                                        contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: '8px', fontSize: '11px' }}
                                        itemStyle={{ color: '#34d399' }}
                                    />
                                    <Line type="monotone" dataKey="pm25" stroke="#34d399" strokeWidth={2} dot={{ r: 2 }} />
                                </LineChart>
                            </ResponsiveContainer>
                        </div>
                    ) : (
                        <div className="flex items-center justify-center flex-1">
                            <div className="w-4 h-4 border-2 border-green-400 border-t-transparent rounded-full animate-spin"></div>
                        </div>
                    )}
                </div>

                {/* Report Button */}
                <div className="mt-6">
                  <button 
                    onClick={() => setShowComplaintModal(true)}
                    className="w-full flex items-center justify-center gap-3 py-4 rounded bg-red-600 hover:bg-red-700 text-white font-mono text-xs uppercase tracking-wider transition-all">
                    <span className="material-symbols-outlined text-lg">local_fire_department</span>
                    Report Incident
                  </button>
                  <MyComplaints userProfile={userProfile} />
                </div>
             </div>
          ) : (
             <div className="flex flex-col h-full animate-fade-in">
                {/* Overview Header */}
                <div className="flex items-center justify-between mb-8">
                  <div>
                    <h2 className="text-xl font-light tracking-tight text-white">System Overview</h2>
                    <p className="font-mono text-[10px] text-slate-500 mt-1 uppercase tracking-wider">Live Status</p>
                  </div>
                  <span className="material-symbols-outlined text-blue-400 text-2xl">public</span>
                </div>

                {/* Average AQI */}
                <div className="bg-slate-900/30 p-6 rounded border border-slate-800 mb-6">
                  <span className="font-mono text-[10px] tracking-wider uppercase text-slate-500 block mb-4">Network Average</span>
                  <div className="flex items-baseline gap-3">
                    <span className="text-6xl font-light text-blue-400 tracking-tighter">{avgAqi}</span>
                    <span className="font-mono text-xs text-blue-400/60 uppercase tracking-wider">AQI</span>
                  </div>
                </div>

                {/* Policy Recommendations - Admin Only */}
                {userProfile?.role === 'admin' && (
                  <div className="bg-slate-900/30 rounded border border-slate-800 flex flex-col overflow-hidden flex-1">
                     <div className="p-4 bg-slate-900 border-b border-slate-800 flex items-center justify-between">
                        <span className="font-mono text-[9px] tracking-wider uppercase text-yellow-400">Automated Policy Advisories</span>
                        <div className="w-1.5 h-1.5 rounded-full bg-yellow-400 animate-pulse"></div>
                     </div>
                     <div className="p-4 overflow-y-auto space-y-4 no-scrollbar bg-slate-950/50 flex-1">
                        {recs.length === 0 ? (
                          <div className="flex flex-col items-center justify-center h-full text-center py-8">
                            <div className="w-12 h-12 border-2 border-yellow-400 border-t-transparent rounded-full animate-spin mb-4" />
                            <p className="text-xs text-slate-400">Generating policy recommendations...</p>
                            <p className="text-[10px] text-slate-500 mt-2">AI analyzing real-time AQI data</p>
                          </div>
                        ) : (
                          recs.map((rec, i) => (
                            <div key={i} className="p-4 bg-slate-900 border border-slate-800 rounded hover:border-slate-700 transition-all">
                               <div className="flex justify-between items-center mb-2">
                                   <span className="font-mono text-[11px] text-white uppercase tracking-wider">{rec.ward}</span>
                                   <span className={`font-mono text-[8px] uppercase tracking-wider px-2 py-0.5 rounded ${
                                     rec.urgency === 'Critical' || rec.urgency === 'High' 
                                       ? 'text-red-400 bg-red-500/10 border border-red-500/30' 
                                       : 'text-yellow-400 bg-yellow-500/10 border border-yellow-500/30'
                                   }`}>{rec.urgency}</span>
                               </div>
                               <p className="text-xs text-slate-400 leading-relaxed mb-3">{rec.action}</p>
                               <div className="bg-slate-950 px-3 py-2 rounded border border-slate-800">
                                  <span className="font-mono text-[9px] text-green-400 uppercase tracking-wider block mb-1">Expected Impact</span>
                                  <span className="text-xs text-slate-200">{rec.impact}</span>
                               </div>
                            </div>
                          ))
                        )}
                     </div>
                  </div>
                )}

              </div>
          )}
        </aside>
      </main>
    </div>
  );
}
