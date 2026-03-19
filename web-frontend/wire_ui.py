import os

app_path = 'src/App.tsx'

react_code = """import React, { useState } from 'react';
import LeafletMap from './components/LeafletMap';

function useRealHeatmapData() {
  const [data, setData] = React.useState<any[]>([]);
  React.useEffect(() => {
    async function fetchOpenAQ() {
      try {
        const res = await fetch('https://api.openaq.org/v2/latest?coordinates=28.6139,77.2090&radius=25000&limit=100');
        const json = await res.json();
        if (json && json.results) {
          const points = json.results.map((r: any) => {
            const pm25 = r.measurements.find((m: any) => m.parameter === 'pm25')?.value || 15.0;
            const intensity = Math.min(pm25 / 150.0, 1.0);
            return [r.coordinates.latitude, r.coordinates.longitude, intensity];
          });
          setData(points);
        }
      } catch (e) {
        console.error("OpenAQ live API fetch failed:", e);
      }
    }
    fetchOpenAQ();
  }, []);
  return data;
}

function App() {
  const heatmapData = useRealHeatmapData();
  
  // Real-time Dashboard state
  const [wards, setWards] = useState<any[]>([]);
  const [recs, setRecs] = useState<any[]>([]);

  React.useEffect(() => {
    async function fetchDashboardData() {
      try {
        const API_BASE = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
        // Fetch Ward Stats
        const statsRes = await fetch(`${API_BASE}/api/v1/dashboard/wards`);
        if (statsRes.ok) setWards(await statsRes.json());
        
        // Fetch Automated Policies
        const recsRes = await fetch(`${API_BASE}/api/v1/dashboard/recommendations`);
        if (recsRes.ok) setRecs(await recsRes.json());
      } catch (e) {
        console.error("Dashboard backend API error:", e);
      }
    }
    fetchDashboardData();
  }, []);

  // Calculate city wide average from wards
  const avgAqi = wards.length > 0 ? Math.round(wards.reduce((acc, curr) => acc + curr.aqi, 0) / wards.length) : 0;
  // Get main source (most frequent)
  let mainSource = "Calculating...";
  if (wards.length > 0) {
     const counts = wards.reduce((acc, curr) => { acc[curr.dominant_source] = (acc[curr.dominant_source] || 0) + 1; return acc; }, {});
     mainSource = Object.keys(counts).reduce((a, b) => counts[a] > counts[b] ? a : b);
  }

  return (
    <div className="w-full h-screen relative bg-slate-900 overflow-hidden font-['Inter'] text-slate-100">

<div className="fixed inset-0 pointer-events-none scanning-line z-0"></div>
{/* Top Navigation Bar */}
<header className="fixed top-0 w-full z-50 flex justify-between items-center px-6 h-16 bg-[#020617]/70 backdrop-blur-2xl border-b border-white/5 font-['Space_Grotesk'] tracking-tight">
<div className="flex items-center gap-8">
<div className="text-2xl font-bold tracking-tighter text-[#a7a5ff] uppercase flex items-center gap-3">
<span className="material-symbols-outlined text-3xl" data-icon="cloud_done">cloud_done</span>
            VayuDrishti Terminal
        </div>
<nav className="hidden md:flex items-center gap-6">
<a className="text-[#a7a5ff] border-b-2 border-[#a7a5ff] pb-1 uppercase text-xs font-bold tracking-widest" href="#">Command</a>
<a className="text-slate-400 hover:text-white transition-colors uppercase text-xs font-bold tracking-widest" href="#">Intelligence</a>
<a className="text-slate-400 hover:text-white transition-colors uppercase text-xs font-bold tracking-widest" href="#">Mitigation</a>
<a className="text-slate-400 hover:text-white transition-colors uppercase text-xs font-bold tracking-widest" href="#">Policy</a>
<a className="text-slate-400 hover:text-white transition-colors uppercase text-xs font-bold tracking-widest" href="#">Archive</a>
</nav>
</div>
<div className="flex items-center gap-4">
<div className="relative hidden sm:block">
<span className="absolute left-3 top-1/2 -translate-y-1/2 material-symbols-outlined text-sm text-outline" data-icon="search">search</span>
<input className="bg-white/5 border border-white/10 text-[10px] tracking-widest pl-10 pr-4 py-2 rounded-sm w-64 focus:ring-1 focus:ring-primary focus:bg-white/10 outline-none uppercase placeholder-slate-500" placeholder="QUERY SYSTEM..." type="text"/>
</div>
<div className="flex items-center gap-3">
<button className="p-2 hover:bg-white/5 transition-all duration-200 rounded-sm relative">
<span className="material-symbols-outlined text-on-surface-variant" data-icon="notifications_active">notifications_active</span>
<span className="absolute top-2 right-2 w-2 h-2 bg-error rounded-full ring-2 ring-[#020617]"></span>
</button>
<div className="h-8 w-8 rounded-full border border-primary/30 overflow-hidden ml-2">
<img alt="Administrator Profile" className="h-full w-full object-cover" data-alt="Close-up professional portrait of a government official" src="https://lh3.googleusercontent.com/aida-public/AB6AXuCSH3KKslc6Xbyl5Pbt1oUb_2T1NaFr1yxtgHk7L7dlOkfqBjqRG-cHjjN2Cxtwd5p28NMBE1D2WRY2iIHthVVPiMyGtmhpPNoEzRTpPOr_bsqM-r9P57YIiVFMNvN5pkWoyC2XDUdRPlesDmni9CtnFafmjoO--4FWWSn8_ePi63tyQeAeFLtPOvwhXrazBB9_vPhH83hbMqZ_X75ZKUJbFvcW_GDGqGAYYsB5XN8vN4Rjj2hRc2hhuArHF2_e5bscolNMSA6Mzq5O"/>
</div>
</div>
</div>
</header>
{/* Sidebar Navigation */}
<aside className="fixed left-0 top-16 h-[calc(100vh-4rem)] flex flex-col z-40 bg-slate-950/60 backdrop-blur-2xl border-r border-white/5 w-20 hover:w-64 transition-all duration-300 group overflow-hidden">
<div className="flex flex-col flex-1 py-6">
<div className="flex items-center gap-4 px-6 mb-8 group-hover:opacity-100 transition-opacity">
<div className="w-8 h-8 rounded bg-primary/20 flex items-center justify-center shrink-0">
<span className="material-symbols-outlined text-primary text-xl" data-icon="terminal">terminal</span>
</div>
<div className="flex flex-col whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity">
<span className="text-xs font-bold tracking-widest uppercase">Terminal 01</span>
<span className="text-[10px] text-slate-400">New Delhi Sector</span>
</div>
</div>
<nav className="flex flex-col gap-1">
<a className="flex items-center gap-4 px-6 py-4 bg-primary/10 text-primary border-r-4 border-primary transition-all duration-300" href="#">
<span className="material-symbols-outlined shrink-0" data-icon="dashboard">dashboard</span>
<span className="font-medium uppercase tracking-widest text-xs opacity-0 group-hover:opacity-100 whitespace-nowrap">Overview</span>
</a>
<a className="flex items-center gap-4 px-6 py-4 text-slate-400 hover:bg-white/5 transition-all duration-300" href="#">
<span className="material-symbols-outlined shrink-0" data-icon="location_on">location_on</span>
<span className="font-medium uppercase tracking-widest text-xs opacity-0 group-hover:opacity-100 whitespace-nowrap">Regional</span>
</a>
<a className="flex items-center gap-4 px-6 py-4 text-slate-400 hover:bg-white/5 transition-all duration-300" href="#">
<span className="material-symbols-outlined shrink-0" data-icon="precision_manufacturing">precision_manufacturing</span>
<span className="font-medium uppercase tracking-widest text-xs opacity-0 group-hover:opacity-100 whitespace-nowrap">Automation</span>
</a>
</nav>
<div className="mt-auto px-4 opacity-0 group-hover:opacity-100 transition-opacity py-4">
<button className="w-full bg-primary text-on-primary text-[10px] font-bold tracking-[0.2em] py-3 rounded-sm uppercase transition-transform active:scale-95 shadow-[0_0_15px_rgba(167,165,255,0.4)]">
                DEPLOY MITIGATION
            </button>
</div>
</div>
</aside>
{/* Main Content Canvas */}
<main className="ml-20 pt-16 h-screen flex gap-6 p-6 overflow-hidden">
{/* Left Column: Regional Intelligence */}
<section className="w-1/4 flex flex-col gap-6">
<div className="flex items-center justify-between px-1">
<div className="flex items-center gap-2">
<div className="w-2 h-2 bg-secondary rounded-full animate-pulse shadow-[0_0_8px_#69f6b8]"></div>
<span className="text-[10px] font-bold tracking-widest text-slate-400 uppercase">Live Data Streaming</span>
</div>
<span className="text-[10px] text-outline font-mono">LAT: 28.6139 | LON: 77.2090</span>
</div>
{/* Primary Metric Card */}
<div className="glass-panel rounded-lg p-6 flex flex-col relative overflow-hidden shadow-xl">
<div className="absolute top-0 left-0 w-full h-[2px] bg-error/80"></div>
<div className="flex justify-between items-start mb-4">
<span className="text-xs font-bold tracking-widest uppercase text-slate-400">Delhi Metropolitan AQI</span>
<span className="material-symbols-outlined text-error" data-icon="warning">warning</span>
</div>
<div className="flex items-baseline gap-4">
<h1 className="font-headline text-6xl font-bold text-error drop-shadow-[0_0_10px_rgba(255,110,132,0.4)]">{avgAqi || '...'}</h1>
<div className="flex flex-col">
<span className="text-error text-xs font-bold uppercase tracking-tight">{avgAqi > 200 ? 'Very Poor' : 'Poor'}</span>
<span className="text-[10px] text-slate-400">{mainSource}</span>
</div>
</div>
</div>
{/* Critical Wards List */}
<div className="glass-panel rounded-lg p-6 flex-1 flex flex-col shadow-xl">
<h3 className="text-xs font-bold tracking-[0.2em] uppercase mb-6 text-slate-400">Top 3 Critical Wards</h3>
<div className="flex flex-col gap-4">

  {wards.slice(0, 3).map(ward => (
    <div key={ward.id} className={`flex items-center justify-between p-3 bg-white/5 rounded-sm border border-white/5 border-l-4 transition-colors hover:bg-white/10 ${ward.aqi > 300 ? 'border-l-error' : ward.aqi > 200 ? 'border-l-tertiary' : 'border-l-secondary'}`}>
      <div>
      <div className="text-xs font-bold uppercase">{ward.name}</div>
      <div className="text-[10px] text-outline">{ward.dominant_source}</div>
      </div>
      <div className="flex items-center gap-3">
      <span className={`font-headline font-bold ${ward.aqi > 300 ? 'text-error' : ward.aqi > 200 ? 'text-tertiary' : 'text-secondary'}`}>{ward.aqi}</span>
      <span className={`material-symbols-outlined text-lg ${ward.aqi > 300 ? 'text-error' : ward.aqi > 200 ? 'text-tertiary' : 'text-secondary'}`} data-icon="dangerous">{ward.aqi > 300 ? 'dangerous' : 'warning'}</span>
      </div>
    </div>
  ))}

</div>
<div className="mt-auto pt-6">
<div className="text-[10px] uppercase tracking-widest text-outline mb-2">Network Health</div>
<div className="flex gap-1 h-1">
<div className="flex-1 bg-secondary rounded-full"></div>
<div className="flex-1 bg-secondary rounded-full"></div>
<div className="flex-1 bg-secondary rounded-full"></div>
<div className="flex-1 bg-secondary rounded-full"></div>
<div className="flex-1 bg-error rounded-full"></div>
</div>
</div>
</div>
</section>
{/* Center Column: Visual Map & Source Analytics */}
<section className="w-1/2 flex flex-col gap-6">
{/* Map Visualization */}
<div className="h-3/5 glass-panel rounded-lg relative overflow-hidden group shadow-2xl">
<div className="w-full h-full absolute inset-0 z-0"><LeafletMap heatmapData={heatmapData} shortestRoute={null} cleanestRoute={null} /></div>
<div className="absolute inset-0 bg-gradient-to-t from-[#020617] via-transparent to-transparent opacity-90 pointer-events-none"></div>
{/* Map Overlays */}
<div className="absolute top-6 left-6 flex flex-col gap-2 pointer-events-none">
<div className="bg-slate-950/80 backdrop-blur-md px-4 py-2 rounded-sm border border-white/10 text-[10px] font-bold tracking-widest uppercase shadow-lg">
                    Choropleth Heatmap: City Wards
                </div>
<div className="flex gap-2">
<span className="px-2 py-0.5 rounded-full bg-error/20 text-error text-[8px] font-bold border border-error/30 shadow-[0_0_10px_rgba(255,110,132,0.2)]">SEVERE</span>
<span className="px-2 py-0.5 rounded-full bg-tertiary/20 text-tertiary text-[8px] font-bold border border-tertiary/30 shadow-[0_0_10px_rgba(255,111,125,0.2)]">POOR</span>
<span className="px-2 py-0.5 rounded-full bg-secondary/20 text-secondary text-[8px] font-bold border border-secondary/30 shadow-[0_0_10px_rgba(105,246,184,0.2)]">STABLE</span>
</div>
</div>
{/* Map Coordinates Cursor HUD */}
<div className="absolute bottom-6 right-6 font-mono text-[10px] text-primary bg-slate-950/80 backdrop-blur-md p-3 border border-primary/30 shadow-lg pointer-events-none">
<div className="flex justify-between gap-6"><span>Z: 14.5</span><span>FR: 60Hz</span></div>
<div className="mt-1 text-on-surface">GRID_LOCK: 28.61, 77.20</div>
</div>
</div>
{/* Source Detection Analysis */}
<div className="h-2/5 glass-panel rounded-lg p-6 flex flex-col shadow-xl">
<div className="flex items-center gap-3 mb-6">
<span className="material-symbols-outlined text-primary" data-icon="psychology">psychology</span>
<h3 className="text-xs font-bold tracking-[0.2em] uppercase text-on-surface">AI Source Detection Analysis</h3>
</div>
<div className="flex-1 flex flex-col justify-center gap-6">
{/* Progress Bar 1 */}
<div className="space-y-2">
<div className="flex justify-between text-[10px] font-bold tracking-widest uppercase">
<span className="flex items-center gap-2 text-tertiary"><span className="material-symbols-outlined text-sm" data-icon="construction">construction</span> Construction Dust</span>
<span>45%</span>
</div>
<div className="h-2 w-full bg-white/5 rounded-full overflow-hidden border border-white/5">
<div className="h-full bg-tertiary w-[45%] shadow-[0_0_15px_rgba(255,111,125,0.6)] transition-all duration-1000"></div>
</div>
</div>
{/* Progress Bar 2 */}
<div className="space-y-2">
<div className="flex justify-between text-[10px] font-bold tracking-widest uppercase">
<span className="flex items-center gap-2 text-error"><span className="material-symbols-outlined text-sm" data-icon="directions_car">directions_car</span> Vehicle Exhaust</span>
<span>35%</span>
</div>
<div className="h-2 w-full bg-white/5 rounded-full overflow-hidden border border-white/5">
<div className="h-full bg-error w-[35%] shadow-[0_0_15px_rgba(255,110,132,0.6)] transition-all duration-1000"></div>
</div>
</div>
{/* Progress Bar 3 */}
<div className="space-y-2">
<div className="flex justify-between text-[10px] font-bold tracking-widest uppercase">
<span className="flex items-center gap-2 text-primary"><span className="material-symbols-outlined text-sm" data-icon="local_fire_department">local_fire_department</span> Biomass Burning</span>
<span>20%</span>
</div>
<div className="h-2 w-full bg-white/5 rounded-full overflow-hidden border border-white/5">
<div className="h-full bg-primary w-[20%] shadow-[0_0_15px_rgba(167,165,255,0.6)] transition-all duration-1000"></div>
</div>
</div>
</div>
</div>
</section>
{/* Right Column: Automated Policy & Action Command */}
<section className="w-1/4 flex flex-col gap-6">
<div className="flex items-center gap-3 border-b border-white/10 pb-4 px-1">
<span className="material-symbols-outlined text-secondary" data-icon="robot_2">robot_2</span>
<h3 className="text-xs font-bold tracking-[0.2em] uppercase text-on-surface">Automated Mitigation Engine</h3>
</div>
<div className="flex-1 flex flex-col gap-5 overflow-y-auto no-scrollbar pb-2">

  {recs.slice(0, 2).map((rec: any, idx) => (
    <div key={rec.id} className={`glass-panel rounded-lg p-5 border border-white/5 border-l-4 relative group transition-all duration-500 hover:shadow-[0_0_30px_rgba(255,110,132,0.3)] ${idx === 0 ? 'border-l-error bg-error/5 shadow-[0_0_20px_rgba(255,110,132,0.15)] hover:bg-error/10' : 'border-l-primary bg-primary/5 shadow-[0_0_20px_rgba(167,165,255,0.15)] hover:bg-primary/10'}`}>
      <div className="flex justify-between mb-3">
      <span className={`text-[9px] font-bold text-white px-2 py-0.5 rounded-sm uppercase tracking-widest shadow-sm ${idx === 0 ? 'bg-error' : 'bg-primary'}`}>{rec.urgency} Response</span>
      <span className="text-[9px] font-mono text-outline">{rec.id}</span>
      </div>
      <p className="text-sm font-medium leading-relaxed mb-6 text-on-surface">
          {rec.action}
      </p>
      <button className={`w-full text-white text-[10px] font-bold tracking-[0.2em] py-3 rounded-sm uppercase hover:brightness-110 transition-all flex items-center justify-center gap-2 shadow-lg active:scale-[0.98] ${idx === 0 ? 'bg-error' : 'bg-primary/50 border border-primary text-primary hover:bg-primary/20 hover:text-white'}`}>
          {idx === 0 ? 'Execute Order' : 'Draft Advisory'}
          <span className="material-symbols-outlined text-sm" data-icon={idx === 0 ? 'gavel' : 'description'}>{idx === 0 ? 'gavel' : 'description'}</span>
      </button>
    </div>
  ))}

{/* Status Summary */}
<div className="mt-auto p-4 bg-white/5 rounded-sm border border-white/10 shadow-lg">
<div className="flex justify-between items-center mb-2">
<span className="text-[10px] uppercase tracking-widest text-slate-400">Engine Integrity</span>
<span className="text-[10px] font-mono text-secondary">{wards.length > 0 ? '99.8%' : 'OFFLINE'}</span>
</div>
<div className="h-1 w-full bg-white/5 rounded-full overflow-hidden">
<div className={`h-full bg-secondary w-full shadow-[0_0_8px_rgba(105,246,184,0.6)] ${wards.length > 0 ? '' : 'hidden'}`}></div>
</div>
</div>
</div>
{/* Global Action Button */}
<button className="w-full group relative overflow-hidden h-16 rounded-sm bg-gradient-to-r from-error to-tertiary p-[1px] shadow-2xl transition-transform active:scale-[0.99]">
<div className="w-full h-full bg-slate-950 rounded-[inherit] flex items-center justify-center gap-3 group-hover:bg-transparent transition-colors duration-300">
<span className="material-symbols-outlined text-error group-hover:text-white transition-colors" data-icon="campaign">campaign</span>
<span className="text-[10px] font-bold tracking-[0.2em] uppercase text-on-surface group-hover:text-white transition-colors">Broadcast SMS Health Advisory</span>
</div>
</button>
</section>
</main>
{/* CLI Status Bar */}
<footer className="fixed bottom-0 left-20 right-0 h-10 bg-slate-950/80 backdrop-blur-xl flex items-center px-6 justify-between text-[9px] font-mono tracking-widest border-t border-white/5 z-30">
<div className="flex items-center gap-8 text-slate-400">
<div className="flex items-center gap-2">
<span className="w-1.5 h-1.5 bg-secondary rounded-full shadow-[0_0_5px_#69f6b8]"></span>
            SYSTEM: ENCRYPTED_CHANNEL_ACTIVE
        </div>
<div>UPTIME: 142:55:01</div>
<div>VER: 4.2.0-SENTINEL</div>
</div>
<div className="flex items-center gap-6 text-primary">
<div className="flex items-center gap-1"><span className="material-symbols-outlined text-[10px]" data-icon="hub">hub</span> NODE: DELHI_CENTRAL_01</div>
<div className="bg-primary/10 border border-primary/20 px-2 py-0.5 rounded-sm text-primary">GOV_AUTH: LEVEL_4</div>
</div>
</footer>

    </div>
  );
}

export default App;
"""

with open(app_path, 'w', encoding='utf-8') as f:
    f.write(react_code)
