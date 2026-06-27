import os
import httpx
import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from datetime import datetime
from app.api.deps import require_admin
from app.db.admin_models import Profile

router = APIRouter()

# Import real data sources
from app.services.ml_engine import ML_ENGINE

class AgentQuery(BaseModel):
    query: str

class AgentResponse(BaseModel):
    query: str
    analysis: str
    data_sources: List[str]
    confidence: float
    supporting_data: Dict[str, Any]
    timestamp: str
    processing_time_ms: int

def extract_ward_from_query(query: str) -> str:
    """Extract ward name from natural language query"""
    # Common patterns
    patterns = [
        r"in\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
        r"at\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+ward",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, query)
        if match:
            return match.group(1)
    
    return None

async def fetch_ward_data(ward_name: str) -> Dict[str, Any]:
    """Fetch real data for a specific ward"""
    wards_data = list(ML_ENGINE.get_cached_predictions()[0].values()) if ML_ENGINE.get_cached_predictions()[0] else []
    
    for ward in wards_data:
        if ward_name.lower() in ward.get('name', '').lower():
            return ward
    
    return None

async def fetch_complaints_for_ward(ward_name: str) -> List[Dict]:
    """Fetch real complaints from Supabase"""
    SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL", "")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY", "")
    
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/complaints?ward=ilike.%{ward_name}%&select=*",
                headers=headers
            )
            if resp.status_code == 200:
                return resp.json()
    except:
        pass
    
    return []

@router.post("/query", response_model=AgentResponse)
async def agent_query(
    query_data: AgentQuery,
    current_user: Profile = Depends(require_admin)
):
    """
    Enhanced AI Agent with REAL logic - handles general and specific queries.
    Analyzes real data to answer admin queries without requiring ward names.
    """
    start_time = datetime.utcnow()
    query = query_data.query.lower()
    
    data_sources = []
    supporting_data = {}
    analysis = ""
    confidence = 0.0
    
    try:
        # Get real-time data
        wards_data = list(ML_ENGINE.get_cached_predictions()[0].values()) if ML_ENGINE.get_cached_predictions()[0] else []
        
        if not wards_data:
            return AgentResponse(
                query=query_data.query,
                analysis="ML inference data not available. Please wait for system to initialize.",
                data_sources=[],
                confidence=0.0,
                supporting_data={},
                timestamp=datetime.utcnow().isoformat(),
                processing_time_ms=0
            )
        
        data_sources.append("ml_inference_cache")
        
        # Pattern 1: General city-wide analysis
        if any(word in query for word in ['overall', 'city', 'delhi', 'general', 'summary', 'status']):
            avg_aqi = sum(w.get('aqi', 0) for w in wards_data) / len(wards_data)
            critical_zones = [w for w in wards_data if w.get('aqi', 0) > 300]
            unhealthy_zones = [w for w in wards_data if 200 < w.get('aqi', 0) <= 300]
            moderate_zones = [w for w in wards_data if 100 < w.get('aqi', 0) <= 200]
            good_zones = [w for w in wards_data if w.get('aqi', 0) <= 100]
            
            # Find worst ward
            worst_ward = max(wards_data, key=lambda w: w.get('aqi', 0))
            best_ward = min(wards_data, key=lambda w: w.get('aqi', 0))
            
            supporting_data["city_stats"] = {
                "avg_aqi": round(avg_aqi, 1),
                "total_wards": len(wards_data),
                "critical": len(critical_zones),
                "unhealthy": len(unhealthy_zones),
                "moderate": len(moderate_zones),
                "good": len(good_zones),
                "worst_ward": worst_ward.get('name'),
                "worst_aqi": worst_ward.get('aqi'),
                "best_ward": best_ward.get('name'),
                "best_aqi": best_ward.get('aqi')
            }
            
            analysis = f"**City-Wide Air Quality Status:**\n\n"
            analysis += f"Average AQI across {len(wards_data)} wards: {round(avg_aqi, 1)}\n\n"
            analysis += f"**Distribution:**\n"
            analysis += f"• Good (≤100): {len(good_zones)} wards\n"
            analysis += f"• Moderate (101-200): {len(moderate_zones)} wards\n"
            analysis += f"• Unhealthy (201-300): {len(unhealthy_zones)} wards\n"
            analysis += f"• Hazardous (>300): {len(critical_zones)} wards\n\n"
            
            if critical_zones:
                analysis += f"**⚠️ CRITICAL ALERT:** {len(critical_zones)} zones require immediate intervention.\n"
                analysis += f"Worst affected: {worst_ward.get('name')} (AQI: {worst_ward.get('aqi')})\n\n"
            
            analysis += f"**Best performing:** {best_ward.get('name')} (AQI: {best_ward.get('aqi')})\n\n"
            
            # Pollution source analysis
            source_counts = {}
            for w in wards_data:
                source = w.get('dominant_source', 'Unknown')
                source_counts[source] = source_counts.get(source, 0) + 1
            
            if source_counts:
                top_source = max(source_counts, key=source_counts.get)
                analysis += f"**Dominant pollution source:** {top_source} ({source_counts[top_source]} wards)\n"
            
            confidence = 0.95
        
        # Pattern 2: Specific ward query
        elif "why" in query and "aqi" in query and ("high" in query or "bad" in query):
            ward_name = extract_ward_from_query(query_data.query)
            
            if not ward_name:
                # If no ward specified, show top 5 worst
                worst_wards = sorted(wards_data, key=lambda w: w.get('aqi', 0), reverse=True)[:5]
                
                analysis = "**Top 5 Worst AQI Zones:**\n\n"
                for i, w in enumerate(worst_wards, 1):
                    analysis += f"{i}. {w.get('name')} - AQI: {w.get('aqi')} (PM2.5: {w.get('pm25')} µg/m³)\n"
                    analysis += f"   Source: {w.get('dominant_source', 'Unknown')}\n\n"
                
                supporting_data["worst_wards"] = [{"name": w.get('name'), "aqi": w.get('aqi')} for w in worst_wards]
                confidence = 0.90
            else:
                # Specific ward analysis
                ward_data = await fetch_ward_data(ward_name)
                
                if not ward_data:
                    return AgentResponse(
                        query=query_data.query,
                        analysis=f"Ward '{ward_name}' not found in current data.",
                        data_sources=["ml_inference_cache"],
                        confidence=0.0,
                        supporting_data={},
                        timestamp=datetime.utcnow().isoformat(),
                        processing_time_ms=int((datetime.utcnow() - start_time).total_seconds() * 1000)
                    )
                
                supporting_data["ward_data"] = ward_data
                
                # Fetch real complaints
                complaints = await fetch_complaints_for_ward(ward_name)
                if complaints:
                    data_sources.append("supabase_complaints")
                    supporting_data["complaint_count"] = len(complaints)
                
                # Build analysis from REAL data
                aqi = ward_data.get('aqi', 0)
                pm25 = ward_data.get('pm25', 0)
                dominant_source = ward_data.get('dominant_source', 'Unknown')
                
                analysis = f"**{ward_name} Air Quality Analysis:**\n\n"
                analysis += f"Current AQI: {aqi} (PM2.5: {pm25} µg/m³)\n\n"
                
                if aqi > 300:
                    analysis += "⚠️ **HAZARDOUS** - Immediate action required!\n\n"
                elif aqi > 200:
                    analysis += "⚠️ **UNHEALTHY** - Health advisory in effect.\n\n"
                
                analysis += f"**Dominant pollution source:** {dominant_source}\n\n"
                
                if complaints:
                    analysis += f"**Citizen complaints:** {len(complaints)} reports filed\n"
                    
                    # Analyze complaint categories
                    categories = {}
                    for c in complaints:
                        cat = c.get('category', 'Unknown')
                        categories[cat] = categories.get(cat, 0) + 1
                    
                    if categories:
                        top_category = max(categories, key=categories.get)
                        analysis += f"Most common: {top_category} ({categories[top_category]} reports)\n"
                
                confidence = 0.85 if complaints else 0.70
        
        # Pattern 3: Action recommendations
        elif any(word in query for word in ['what', 'action', 'do', 'recommend', 'suggest']):
            critical_zones = [w for w in wards_data if w.get('aqi', 0) > 300]
            critical_zones.sort(key=lambda x: x.get('aqi', 0), reverse=True)
            
            supporting_data["critical_zones"] = critical_zones[:5]
            
            if critical_zones:
                analysis = f"**Immediate Action Required:**\n\n"
                analysis += f"Found {len(critical_zones)} critical zones:\n\n"
                for i, zone in enumerate(critical_zones[:5], 1):
                    analysis += f"{i}. {zone.get('name')} (AQI: {zone.get('aqi')})\n"
                    analysis += f"   Source: {zone.get('dominant_source')}\n\n"
                
                analysis += "**Recommended Actions:**\n"
                analysis += "• Deploy air quality monitoring teams\n"
                analysis += "• Issue public health advisories\n"
                analysis += "• Investigate and mitigate pollution sources\n"
                analysis += "• Implement traffic restrictions if needed\n"
                analysis += "• Monitor vulnerable populations\n"
                
                confidence = 0.90
            else:
                analysis = "**Good News!** No critical zones detected.\n\n"
                analysis += "All areas are within acceptable AQI ranges.\n"
                analysis += "Continue routine monitoring and maintenance."
                confidence = 0.95
        
        # Pattern 4: Complaint statistics
        elif "complaint" in query:
            SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL", "")
            SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY", "")
            
            if SUPABASE_URL and SUPABASE_KEY:
                headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
                
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(
                        f"{SUPABASE_URL}/rest/v1/complaints?select=*",
                        headers=headers
                    )
                    
                    if resp.status_code == 200:
                        complaints = resp.json()
                        
                        data_sources.append("supabase_complaints")
                        supporting_data["total_complaints"] = len(complaints)
                        
                        analysis = f"**Complaint System Status:**\n\n"
                        analysis += f"Total complaints: {len(complaints)}\n\n"
                        
                        if complaints:
                            # Status breakdown
                            status_counts = {}
                            for c in complaints:
                                status = c.get('status', 'Unknown')
                                status_counts[status] = status_counts.get(status, 0) + 1
                            
                            analysis += "**Status breakdown:**\n"
                            for status, count in status_counts.items():
                                analysis += f"• {status}: {count}\n"
                            
                            supporting_data["status_breakdown"] = status_counts
                        else:
                            analysis += "No complaints currently in system.\n"
                        
                        confidence = 0.95
        
        # Pattern 5: Trend analysis
        elif any(word in query for word in ['trend', 'improving', 'worse', 'better', 'change']):
            avg_aqi = sum(w.get('aqi', 0) for w in wards_data) / len(wards_data)
            
            analysis = f"**Current Snapshot:**\n\n"
            analysis += f"Average AQI: {round(avg_aqi, 1)}\n"
            analysis += f"Total wards monitored: {len(wards_data)}\n\n"
            analysis += "**Note:** Historical trend analysis requires time-series data.\n"
            analysis += "Current system provides real-time snapshots.\n"
            analysis += "For trend analysis, data collection over multiple days is needed.\n"
            
            confidence = 0.60
        
        # Default: Provide guidance
        else:
            analysis = "**I can help you with:**\n\n"
            analysis += "• City-wide air quality status and summary\n"
            analysis += "• Specific ward AQI analysis\n"
            analysis += "• Action recommendations for critical zones\n"
            analysis += "• Complaint statistics and trends\n"
            analysis += "• Pollution source analysis\n\n"
            analysis += "**Example queries:**\n"
            analysis += "• 'What is the overall city status?'\n"
            analysis += "• 'Why is AQI high in Dwarka?'\n"
            analysis += "• 'What areas need immediate action?'\n"
            analysis += "• 'How many complaints do we have?'\n"
            confidence = 0.0
        
        processing_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        return AgentResponse(
            query=query_data.query,
            analysis=analysis,
            data_sources=data_sources,
            confidence=confidence,
            supporting_data=supporting_data,
            timestamp=datetime.utcnow().isoformat(),
            processing_time_ms=processing_time_ms
        )
    
    except Exception as e:
        import traceback
        error_detail = f"Agent query failed: {str(e)}\n{traceback.format_exc()}"
        print(f"[AGENT] ERROR: {error_detail}")
        raise HTTPException(status_code=500, detail=error_detail)
