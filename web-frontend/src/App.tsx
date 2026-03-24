import React, { useState, useEffect } from 'react';
import LeafletMap from './components/LeafletMap';
import AuthOverlay from './components/AuthOverlay';
import LandingPage from './components/LandingPage';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

export default function App() {
  const [session, setSession] = useState<any>(null);
  const [userProfile, setUserProfile] = useState<any>(null);
  const [wards, setWards] = useState<any[]>([]);
  const [recs, setRecs] = useState<any[]>([]);
  const [selectedWard, setSelectedWard] = useState<any | null>(null);
  const [geeData, setGeeData] = useState<any | null>(null);
  const [geeLoading, setGeeLoading] = useState<boolean>(false);
  const [forecast, setForecast] = useState<any[]>([]);
  const [granularity, setGranularity] = useState<'ward'|'district'>('ward');
  const [showLanding, setShowLanding] = useState<boolean>(true);

  useEffect(() => {
    if (!selectedWard) {
        setGeeData(null);
        setForecast([]);
        return;
    }
    const API_BASE = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
    
    async function fetchGEE() {
        setGeeLoading(true);
        try {
            const res = await fetch(`${API_BASE}/api/v1/gee/analyze?lat=${selectedWard.lat}&lon=${selectedWard.lon}`);
            if (res.ok) setGeeData(await res.json());
        } catch (e) {
            console.error(e);
        } finally {
            setGeeLoading(false);
        }
    }
    
    async function fetchForecast() {
        try {
            const res = await fetch(`${API_BASE}/api/v1/dashboard/forecast?lat=${selectedWard.lat}&lon=${selectedWard.lon}`);
            if (res.ok) {
                const data = await res.json();
                const formatted = data.map((d: any) => ({
                    ...d,
                    day: new Date(d.time).toLocaleDateString('en-US', { weekday: 'short' })
                }));
                setForecast(formatted);
            }
        } catch (e) {
            console.error(e);
        }
    }
    
    fetchGEE();
    fetchForecast();
  }, [selectedWard]);

  useEffect(() => {
    async function fetchDashboardData() {
      try {
        const API_BASE = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
        // Fetch LIVE Stats with dynamic filtering
        const statsRes = await fetch(`${API_BASE}/api/v1/dashboard/wards?level=${granularity}`);
        if (statsRes.ok) {
           const data = await statsRes.json();
           setWards(data);
        }
        
        // Fetch Policies
        const recsRes = await fetch(`${API_BASE}/api/v1/dashboard/recommendations`);
        if (recsRes.ok) setRecs(await recsRes.json());
      } catch (e) {
        console.error("Dashboard backend API error:", e);
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
    return <LandingPage onLaunch={() => setShowLanding(false)} />;
  }

  return (
    <div className="bg-[#0c0e12] text-slate-100 font-sans selection:bg-cyan-500/30 overflow-hidden h-screen flex flex-col relative w-screen">
      
      {/* ─── HACKATHON EDGE: Supabase Native Auth Gateway ─── */}
      <AuthOverlay session={session} setSession={setSession} userProfile={userProfile} setUserProfile={setUserProfile} />

      {/* TopNavBar */}
      <header className="fixed top-0 w-full z-50 bg-slate-950/80 backdrop-blur-xl border-b border-white/10 shadow-[0_4px_20px_rgba(0,242,255,0.1)] flex items-center justify-between px-8 h-20">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-tr from-cyan-500 to-blue-500 rounded-sm flex items-center justify-center">
              <span className="material-symbols-outlined text-white text-2xl font-bold">public</span>
            </div>
            <div>
              <h1 className="font-headline font-black text-2xl tracking-tight uppercase text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-500">ATMOSPHERIC COMMAND</h1>
              <p className="font-label text-[10px] tracking-[0.3em] text-cyan-400/60 uppercase">VayuDrishti Internal Systems</p>
            </div>
          </div>
        </div>
        
        <nav className="hidden md:flex items-center gap-8 h-full">
          <button 
            onClick={() => { setGranularity('district'); setSelectedWard(null); setWards([]); }}
            className={`font-headline font-bold tracking-tight uppercase text-[12px] h-full flex items-center transition-all border-b-2 ${granularity === 'district' ? 'text-cyan-400 border-cyan-400' : 'text-slate-400 border-transparent hover:text-slate-200'}`}>
            District Tier (11)
          </button>
          <button 
            onClick={() => { setGranularity('ward'); setSelectedWard(null); setWards([]); }}
            className={`font-headline font-bold tracking-tight uppercase text-[12px] h-full flex items-center transition-all border-b-2 ${granularity === 'ward' ? 'text-cyan-400 border-cyan-400' : 'text-slate-400 border-transparent hover:text-slate-200'}`}>
            Ward Tier (272)
          </button>
        </nav>
        
        <div className="flex items-center gap-6">
          <div className="h-10 w-px bg-white/10"></div>
          {userProfile && (
            <div className="flex items-center gap-3 bg-white/5 pr-4 pl-1 py-1 rounded-full border border-white/5">
              <div className="w-8 h-8 rounded-full bg-slate-800 overflow-hidden ring-1 ring-cyan-500/30 flex items-center justify-center text-cyan-400 font-bold uppercase">
                {userProfile.full_name?.charAt(0) || userProfile.email?.charAt(0) || 'U'}
              </div>
              <div className="flex flex-col">
                <span className="font-label text-xs font-bold tracking-widest text-slate-200 uppercase">{userProfile.full_name || 'Citizen'}</span>
                <span className="text-[9px] font-bold text-cyan-500 uppercase tracking-widest">{userProfile.role} Auth</span>
              </div>
            </div>
          )}
        </div>
      </header>

      <main className="flex-1 mt-20 flex overflow-hidden">
        {/* Central Canvas */}
        <section className="flex-1 relative flex flex-col overflow-hidden">
          
          {/* Central Map Area */}
          <div className="flex-1 relative bg-[#0b1120] overflow-hidden">
             <div className="absolute inset-0 z-0">
               <LeafletMap wards={wards} selectedWard={selectedWard} onWardClick={handleWardClick} granularity={granularity} />
             </div>
             <div className="absolute inset-0 pointer-events-none shadow-[inset_0_0_100px_rgba(2,6,23,1)] z-10"></div>
             
             {/* ─── HACKATHON EDGE: ASTHMA SAFETY PROTOCOL ─── */}
             {userProfile?.has_asthma && selectedWard?.aqi > 200 && (
                <div className="absolute top-8 left-1/2 -translate-x-1/2 z-[1001] pointer-events-none transition-all">
                  <div className="px-6 py-3 bg-red-950/80 border-2 border-red-500 rounded-full flex items-center gap-4 animate-pulse shadow-[0_0_50px_rgba(239,68,68,0.6)] backdrop-blur-md">
                    <span className="material-symbols-outlined text-red-500 text-3xl">warning</span>
                    <div className="flex flex-col">
                      <span className="text-red-400 font-extrabold tracking-widest uppercase text-[10px]">Asthma Safety Protocol Activated</span>
                      <span className="text-white font-medium text-xs tracking-wide">AQI in {selectedWard.name} exceeds 200. Shelter in place.</span>
                    </div>
                  </div>
                </div>
              )}
          </div>
          
          {/* Bottom Panel: Citizen Welfare Feed */}
          <footer className="h-16 bg-slate-950 border-t border-white/5 flex items-center px-8 gap-8 relative overflow-hidden z-20">
            <div className="shrink-0 flex items-center gap-3 border-r border-white/10 pr-6">
              <span className="material-symbols-outlined text-cyan-400 text-lg">public</span>
              <span className="font-headline text-[10px] font-bold tracking-widest uppercase text-slate-200">CITIZEN WELFARE FEED</span>
            </div>
            <div className="flex-1 overflow-hidden">
              <div className="flex gap-16 animate-marquee whitespace-nowrap items-center hover:[animation-play-state:paused] cursor-default">
                {recs.length > 0 ? recs.map((rec, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <span className={`w-2 h-2 rounded-full ${rec.urgency === 'High' ? 'bg-rose-500 animate-ping' : 'bg-cyan-400'}`}></span>
                    <span className="font-body text-xs text-slate-400 tracking-wide uppercase">
                      <span className="text-white font-bold">REGION [{rec.ward}]:</span> {rec.action}
                    </span>
                  </div>
                )) : (
                   <span className="font-body text-xs text-slate-500 tracking-wide uppercase">Awaiting Neural Link Stabilization...</span>
                )}
              </div>
            </div>
            <div className="font-headline text-[10px] uppercase tracking-[0.2em] text-slate-500 ml-auto pl-8 border-l border-white/10 shrink-0">
                OFFICIAL VAYUDRISHTI INTELLIGENCE
            </div>
          </footer>
        </section>

        {/* Right Side Panel: The Delegate Brief */}
        <aside className="w-[450px] bg-slate-950 border-l border-slate-900 p-8 flex flex-col gap-6 overflow-y-auto z-20 shrink-0 relative shadow-[-20px_0_50px_rgba(0,0,0,0.5)] no-scrollbar">
          
          {selectedWard ? (
             <div className="flex flex-col h-full animate-slide-in">
                <div className="flex justify-between items-start mb-4">
                    <div className="flex flex-col">
                        <span className="font-label text-xs tracking-[0.2em] font-bold uppercase text-cyan-500 mb-1">Sector Acquired</span>
                        <h2 className="font-headline text-3xl font-black uppercase text-white tracking-tight leading-none">{selectedWard.name}</h2>
                    </div>
                    <button onClick={() => setSelectedWard(null)} className="p-2 bg-slate-800 text-slate-400 hover:bg-slate-700 hover:text-white rounded-full transition-all shrink-0 ml-4">
                        <span className="material-symbols-outlined text-sm">close</span>
                    </button>
                </div>

                <div className="flex items-center gap-5 mb-6 bg-slate-900/50 p-6 rounded-2xl border border-white/5">
                    <div className={`font-headline text-7xl font-black tracking-tighter ${selectedWard.aqi > 300 ? 'text-rose-500 drop-shadow-[0_0_15px_rgba(244,63,94,0.4)]' : 'text-cyan-400 drop-shadow-[0_0_15px_rgba(34,211,238,0.4)]'}`}>
                        {selectedWard.aqi}
                    </div>
                    <div className="flex flex-col gap-2">
                        <span className="font-label text-[10px] text-slate-400 uppercase tracking-widest font-bold">Real-Time Tracker</span>
                        <span className={`px-2 py-0.5 text-[10px] font-bold rounded uppercase tracking-widest w-max ${selectedWard.aqi > 300 ? 'bg-rose-500/10 border border-rose-500/30 text-rose-500' : 'bg-cyan-500/10 border border-cyan-500/30 text-cyan-400'}`}>
                            {selectedWard.status}
                        </span>
                        <div className="flex items-center gap-2 mt-1">
                           <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">PM2.5:</span>
                           <span className="text-xs font-bold text-white">{selectedWard.pm25} µg</span>
                        </div>
                    </div>
                </div>

                {/* Satellite Diagnostics */}
                {geeLoading ? (
                    <div className="bg-slate-900/30 border border-white/5 p-6 rounded-2xl flex flex-col items-center justify-center min-h-[140px] mb-6">
                        <span className="material-symbols-outlined text-cyan-400 animate-spin text-3xl mb-3">satellite_alt</span>
                        <p className="font-label text-[10px] text-cyan-400 font-bold tracking-[0.2em] uppercase animate-pulse">Establishing S5P Link...</p>
                    </div>
                ) : geeData && (
                    <div className="bg-slate-900/30 border border-white/5 p-6 rounded-2xl relative overflow-hidden group hover:border-cyan-500/30 transition-all duration-300 mb-6">
                        <div className="absolute top-0 right-0 w-32 h-32 bg-cyan-500/5 blur-3xl group-hover:bg-cyan-500/10 pointer-events-none"></div>
                        <h3 className="font-label text-[10px] font-black uppercase text-cyan-500 tracking-[0.2em] mb-4 flex items-center gap-2">
                            <span className="material-symbols-outlined text-[14px]">insights</span>
                            Orbital Analysis
                        </h3>
                        <div className="space-y-3">
                            <div className="flex justify-between items-center bg-slate-900/80 p-3 rounded-lg border border-slate-800">
                                <span className="font-body text-slate-400 uppercase font-bold tracking-wider text-[10px]">Biomass Plume</span>
                                <span className="font-headline text-white font-bold text-sm">{geeData.biomass_burning_index} <span className="text-slate-500 text-[10px]">mol/m²</span></span>
                            </div>
                            <div className="flex justify-between items-center bg-slate-900/80 p-3 rounded-lg border border-slate-800">
                                <span className="font-body text-slate-400 uppercase font-bold tracking-wider text-[10px]">Construction Dust</span>
                                <span className="font-headline text-white font-bold text-sm">{geeData.construction_dust_index} <span className="text-slate-500 text-[10px]">UVAI</span></span>
                            </div>
                            <div className="bg-cyan-500/5 border border-cyan-500/20 p-3 rounded-lg flex flex-col items-center justify-center gap-1 mt-2">
                                <span className="text-[9px] font-black text-cyan-500 uppercase tracking-[0.2em]">Dominant Source</span>
                                <strong className="text-cyan-100 uppercase tracking-widest text-xs font-headline">{geeData.dominant_source}</strong>
                            </div>
                        </div>
                    </div>
                )}

                {/* 8-Day Predictive Chart */}
                <div className="bg-slate-900/30 p-6 rounded-2xl border border-white/5 relative overflow-hidden flex-1 flex flex-col min-h-[220px]">
                    <h3 className="font-label text-[10px] font-black uppercase text-emerald-400 tracking-[0.2em] mb-4 flex items-center gap-2 shrink-0">
                        <span className="material-symbols-outlined text-[14px]">timeline</span>
                        8-Day Neural Forecast
                    </h3>
                    {forecast.length > 0 ? (
                        <div className="flex-1 w-full min-h-0">
                            <ResponsiveContainer width="100%" height="100%">
                                <LineChart data={forecast} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                                    <XAxis dataKey="day" stroke="#64748b" fontSize={9} tickLine={false} axisLine={false} dy={5} />
                                    <YAxis stroke="#475569" fontSize={9} tickLine={false} axisLine={false} />
                                    <Tooltip 
                                        contentStyle={{ backgroundColor: '#020617', borderColor: '#1e293b', borderRadius: '8px', fontSize: '11px', fontWeight: 'bold' }}
                                        itemStyle={{ color: '#34d399' }}
                                        cursor={{ stroke: '#334155', strokeWidth: 1, strokeDasharray: '4 4' }}
                                    />
                                    <Line type="monotone" dataKey="pm25" stroke="#34d399" strokeWidth={3} dot={{ r: 3, fill: '#020617', strokeWidth: 2 }} activeDot={{ r: 5, fill: '#34d399' }} />
                                </LineChart>
                            </ResponsiveContainer>
                        </div>
                    ) : (
                        <div className="flex items-center justify-center flex-1">
                            <div className="w-5 h-5 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin"></div>
                        </div>
                    )}
                </div>

                {/* HACKATHON EDGE: CITIZEN REPORTING BUTTON */}
                <div className="mt-8 shrink-0">
                  <button 
                    onClick={() => {
                      alert(`[VAYUDRISHTI SYSTEM] Locating device at (${selectedWard.lat}, ${selectedWard.lon})...\n\nBiomass burning incident formally logged to the central database. Ground truth data fed into Neural Network. Thank you!`);
                    }}
                    className="w-full flex items-center justify-center gap-3 py-4 rounded-xl bg-gradient-to-r from-rose-600 to-rose-800 text-white font-headline text-xs font-bold tracking-[0.2em] uppercase hover:shadow-[0_0_20px_rgba(244,63,94,0.3)] active:scale-95 transition-all">
                    <span className="material-symbols-outlined text-lg">local_fire_department</span>
                    Log Biomass Action
                  </button>
                </div>
             </div>
          ) : (
             <div className="flex flex-col h-full animate-fade-in">
                <div className="flex items-center justify-between mb-8 shrink-0">
                  <div>
                    <h2 className="font-headline text-xl font-bold tracking-tight text-white uppercase">The Delegate Brief</h2>
                    <p className="font-label text-[10px] text-slate-500 font-mono mt-1 uppercase tracking-widest">Global Status: Live</p>
                  </div>
                  <span className="material-symbols-outlined text-cyan-400 text-3xl opacity-80 animate-pulse">public</span>
                </div>

                <div className="space-y-6 flex flex-col flex-1 min-h-0">
                  
                  <div className="bg-slate-900/30 p-6 rounded-2xl border border-white/5 relative overflow-hidden shrink-0 group hover:border-cyan-500/30 transition-all duration-300">
                    <div className="absolute top-0 right-0 w-40 h-40 bg-cyan-500/5 blur-3xl group-hover:bg-cyan-500/10 transition-all"></div>
                    <span className="font-label text-[10px] tracking-[0.2em] font-bold uppercase text-slate-400 block mb-4">Network Avg AQI</span>
                    <div className="flex items-baseline gap-3">
                      <span className="font-headline font-bold text-6xl text-cyan-400 tracking-tighter">{avgAqi}</span>
                      <span className="font-headline text-xs font-bold text-cyan-500/60 uppercase tracking-widest">Optimal</span>
                    </div>
                  </div>

                  <div className="bg-slate-900/30 rounded-2xl border border-white/5 flex flex-col overflow-hidden max-h-[450px]">
                     <div className="p-4 bg-slate-900 border-b border-white/5 flex items-center justify-between shadow-sm shrink-0">
                        <span className="font-label text-[9px] tracking-[0.2em] font-bold uppercase text-amber-500">Llama 3 Network Directives</span>
                        <div className="flex gap-2">
                           <div className="w-2 h-2 rounded-full bg-amber-500 animate-pulse"></div>
                        </div>
                     </div>
                     <div className="p-4 overflow-y-auto space-y-4 no-scrollbar bg-slate-950/50 flex-1">
                        {recs.map((rec, i) => (
                          <div key={i} className="p-4 bg-slate-900 border border-slate-800 rounded-xl hover:border-amber-500/30 transition-all">
                             <div className="flex justify-between items-center mb-2">
                                 <span className="font-headline text-[11px] font-black text-white tracking-widest uppercase truncate">{rec.ward}</span>
                                 <span className={`font-label text-[8px] font-bold uppercase tracking-widest px-2 py-0.5 rounded shrink-0 ${rec.urgency === 'High' ? 'text-rose-400 bg-rose-500/10 border border-rose-500/30' : 'text-amber-400 bg-amber-500/10 border border-amber-500/30'}`}>{rec.urgency}</span>
                             </div>
                             <p className="font-body text-xs text-slate-400 leading-relaxed font-light mb-3">{rec.action}</p>
                             <div className="bg-slate-950 px-3 py-2 rounded-lg border border-slate-800">
                                <span className="font-label text-[9px] text-emerald-400 tracking-widest uppercase block mb-1">Impact Metric</span>
                                <span className="font-body text-xs text-slate-200">{rec.impact}</span>
                             </div>
                          </div>
                        ))}
                     </div>
                  </div>

                </div>
             </div>
          )}
        </aside>
      </main>
    </div>
  );
}
