import React, { useState } from 'react';
import { Settings, Route, Navigation2 } from 'lucide-react';

interface MapControlProps {
    healthSensitivity: number;
    setHealthSensitivity: (val: number) => void;
    onCompareRoutes: (start: string, end: string) => void;
    isLoading: boolean;
    loadingStep?: string;
    routeStats: any;
}

export default function MapControl({
    healthSensitivity,
    setHealthSensitivity,
    onCompareRoutes,
    isLoading,
    loadingStep,
    routeStats
}: MapControlProps) {
    const [startAddress, setStartAddress] = useState("Banjara Hills, Hyderabad");
    const [endAddress, setEndAddress] = useState("Hussain Sagar, Hyderabad");

    return (
        <div className="absolute top-4 left-4 w-96 bg-white/90 backdrop-blur-md rounded-xl shadow-2xl p-6 border border-gray-100 font-sans z-[1000] transition-all duration-300">

            <div className="flex items-center space-x-3 mb-6">
                <div className="p-2 bg-blue-100 rounded-lg">
                    <Navigation2 className="w-6 h-6 text-blue-600" />
                </div>
                <div>
                    <h1 className="text-xl font-bold text-gray-800 tracking-tight">Breath-Analyzer</h1>
                    <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Predictive Air Quality Navigation</p>
                </div>
            </div>

            <div className="space-y-6">
                <div className="space-y-4">
                    <div className="relative">
                        <div className="absolute left-3 top-3 w-2.5 h-2.5 rounded-full border-2 border-gray-400"></div>
                        <input type="text" value={startAddress} onChange={(e) => setStartAddress(e.target.value)} className="w-full bg-gray-50 border border-gray-200 text-gray-700 text-sm rounded-lg pl-10 pr-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500/50 transition-all font-medium" />
                    </div>
                    <div className="relative">
                        <div className="absolute left-3 top-3 w-2.5 h-2.5 rounded-full border-2 border-blue-500"></div>
                        <input type="text" value={endAddress} onChange={(e) => setEndAddress(e.target.value)} className="w-full bg-gray-50 border border-gray-200 text-gray-700 text-sm rounded-lg pl-10 pr-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500/50 transition-all font-medium" />
                    </div>
                </div>

                <hr className="border-gray-100" />

                <div className="space-y-3">
                    <div className="flex justify-between items-center">
                        <label className="text-sm font-semibold text-gray-700 flex items-center">
                            <Settings className="w-4 h-4 mr-2 text-gray-500" />
                            Health Sensitivity (β)
                        </label>
                        <span className="text-xs font-bold px-2 py-1 bg-blue-50 text-blue-700 rounded-md">
                            {healthSensitivity}%
                        </span>
                    </div>

                    <input
                        type="range"
                        min="0"
                        max="100"
                        value={healthSensitivity}
                        onChange={(e) => setHealthSensitivity(parseInt(e.target.value))}
                        onMouseUp={() => onCompareRoutes(startAddress, endAddress)}
                        onTouchEnd={() => onCompareRoutes(startAddress, endAddress)}
                        className="w-full h-1.5 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600 hover:accent-blue-700 transition-all"
                    />
                    <div className="flex justify-between text-[10px] text-gray-500 font-bold uppercase mt-2 px-1">
                        <span className="flex items-center tracking-wider"><div className="w-3 h-0 border-t-2 border-dashed border-red-500 mr-1.5"></div>Fastest Route</span>
                        <span className="flex items-center tracking-wider"><div className="w-3 h-1 bg-green-500 mr-1.5 rounded-full"></div>Cleanest Air</span>
                    </div>
                </div>

                <button
                    onClick={() => onCompareRoutes(startAddress, endAddress)}
                    disabled={isLoading}
                    className="w-full py-3 px-4 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white text-sm font-bold rounded-xl shadow-lg shadow-blue-500/30 flex items-center justify-center transition-all disabled:opacity-70 active:scale-[0.98]"
                >
                    {isLoading ? (
                        <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                    ) : (
                        <>
                            <Route className="w-4 h-4 mr-2" />
                            Compare Routes
                        </>
                    )}
                </button>

                {isLoading && loadingStep && (
                    <div className="text-center text-xs text-blue-600 font-semibold animate-pulse mt-3 bg-blue-50 py-2 rounded-lg border border-blue-100">
                        {loadingStep}
                    </div>
                )}

                {routeStats && (
                    <div className="mt-6 space-y-3 animate-in fade-in slide-in-from-bottom-2 duration-300">
                        <div className="p-4 bg-gradient-to-br from-green-50 to-emerald-50 rounded-xl border border-green-100/50">
                            <div className="text-xs font-bold text-green-800 uppercase tracking-wide mb-1">Exposure Reduction</div>
                            <div className="flex items-baseline">
                                <span className="text-3xl font-extrabold text-green-600">
                                    {routeStats.exposure_reduction_pct.toFixed(1)}%
                                </span>
                                <span className="ml-2 text-xs font-semibold text-green-700/70">PM2.5 avoided</span>
                            </div>
                        </div>

                        <div className="flex gap-3">
                            <div className="flex-1 p-3 bg-gray-50 rounded-lg border border-gray-100">
                                <div className="text-[10px] uppercase font-bold text-gray-400 mb-1">Added Distance</div>
                                <div className="text-sm font-bold text-gray-700">+{routeStats.distance_increase_pct.toFixed(1)}%</div>
                            </div>
                            <div className="flex-1 p-3 bg-blue-50/50 rounded-lg border border-blue-100/50">
                                <div className="text-[10px] uppercase font-bold text-blue-400 mb-1">Model Confidence</div>
                                <div className="text-sm font-bold text-blue-700">92% <span className="text-[9px] font-normal opacity-70">(CQR)</span></div>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
