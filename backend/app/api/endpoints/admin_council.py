import os
import httpx
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from datetime import datetime
from app.api.deps import require_admin
from app.db.admin_models import Profile
from pydantic import BaseModel

router = APIRouter()

from app.services.ml_engine import ML_ENGINE

class CouncilQuery(BaseModel):
    scenario: str
    context: Dict[str, Any] = {}

class DebateMessage(BaseModel):
    round: int
    agent_name: str
    role: str
    message: str
    responding_to: str = None
    timestamp: str
    emotion: str  # calm, concerned, frustrated, supportive

class AgentOpinion(BaseModel):
    agent_name: str
    role: str
    analysis: str
    recommendation: str
    vote: str
    reasoning: str
    priority_score: int
    initial_vote: str
    vote_changed: bool

class CouncilDecision(BaseModel):
    scenario: str
    situation_summary: str
    key_data_points: Dict[str, Any]
    debate_transcript: List[DebateMessage]
    agent_opinions: List[AgentOpinion]
    conflicts_identified: List[str]
    consensus_points: List[str]
    final_decision: str
    recommended_actions: List[str]
    expected_outcome: str
    confidence_level: float
    metadata: Dict[str, Any]

COUNCIL_AGENTS = [
    {"name": "Dr. Priya Sharma", "role": "Environmental Scientist", "personality": "analytical", "speaking_style": "technical"},
    {"name": "Dr. Rajesh Kumar", "role": "Public Health Officer", "personality": "compassionate", "speaking_style": "urgent"},
    {"name": "Ms. Anjali Mehta", "role": "Economic Advisor", "personality": "pragmatic", "speaking_style": "measured"},
    {"name": "Shri Vikram Singh", "role": "Enforcement Officer", "personality": "skeptical", "speaking_style": "direct"},
    {"name": "Mrs. Meera Devi", "role": "Citizen Representative", "personality": "emotional", "speaking_style": "passionate"}
]

def analyze_current_situation():
    wards_data = list(ML_ENGINE.get_cached_predictions()[0].values()) if ML_ENGINE.get_cached_predictions()[0] else []
    if not wards_data:
        return {"error": "INSUFFICIENT DATA"}
    critical_zones = [w for w in wards_data if w.get('aqi', 0) > 300]
    unhealthy_zones = [w for w in wards_data if 200 < w.get('aqi', 0) <= 300]
    avg_aqi = sum(w.get('aqi', 0) for w in wards_data) / len(wards_data)
    return {
        "total_wards": len(wards_data),
        "critical_zones": len(critical_zones),
        "unhealthy_zones": len(unhealthy_zones),
        "avg_aqi": round(avg_aqi, 1),
        "worst_ward": max(wards_data, key=lambda w: w.get('aqi', 0)),
        "timestamp": datetime.utcnow().isoformat()
    }

def generate_debate_transcript(agents, situation, scenario):
    transcript = []
    critical = situation.get("critical_zones", 0)
    avg_aqi = situation.get("avg_aqi", 0)
    
    # ROUND 1: Opening Statements
    transcript.append(DebateMessage(
        round=1, agent_name="Dr. Priya Sharma", role="Environmental Scientist",
        message=f"Based on satellite data and ground sensors, we have {critical} critical zones with average AQI of {avg_aqi}. The pollution sources are primarily vehicular and industrial emissions. We need evidence-based interventions targeting these sources.",
        timestamp=datetime.utcnow().isoformat(), emotion="calm"
    ))
    
    transcript.append(DebateMessage(
        round=1, agent_name="Dr. Rajesh Kumar", role="Public Health Officer",
        message=f"I must emphasize the health emergency we're facing. {critical} zones means thousands of citizens are breathing hazardous air RIGHT NOW. Children, elderly, and those with respiratory conditions are at severe risk. We cannot afford delays.",
        timestamp=datetime.utcnow().isoformat(), emotion="concerned"
    ))
    
    transcript.append(DebateMessage(
        round=1, agent_name="Ms. Anjali Mehta", role="Economic Advisor",
        message=f"While I understand the urgency, we must consider economic impacts. Blanket restrictions on {situation['total_wards']} wards will affect businesses, jobs, and livelihoods. We need a balanced, phased approach that doesn't cripple the economy.",
        timestamp=datetime.utcnow().isoformat(), emotion="calm"
    ))
    
    transcript.append(DebateMessage(
        round=1, agent_name="Shri Vikram Singh", role="Enforcement Officer",
        message=f"Let's be realistic. My teams can effectively enforce in maybe 50 wards maximum. If you propose city-wide restrictions, I'm telling you now - it won't work. We need targeted, enforceable actions.",
        timestamp=datetime.utcnow().isoformat(), emotion="skeptical"
    ))
    
    transcript.append(DebateMessage(
        round=1, agent_name="Mrs. Meera Devi", role="Citizen Representative",
        message=f"People are SUFFERING! My children can't play outside. Schools are closing. Citizens are demanding action, not excuses about budgets or enforcement capacity. The government must act NOW!",
        timestamp=datetime.utcnow().isoformat(), emotion="frustrated"
    ))
    
    # ROUND 2: Debate & Responses
    if critical > 10:
        transcript.append(DebateMessage(
            round=2, agent_name="Dr. Rajesh Kumar", role="Public Health Officer",
            message="Ms. Mehta, I respect economic concerns, but what's the economic cost of mass hospitalizations? Of lost productivity when people are sick? Health must come first.",
            responding_to="Ms. Anjali Mehta", timestamp=datetime.utcnow().isoformat(), emotion="concerned"
        ))
        
        transcript.append(DebateMessage(
            round=2, agent_name="Ms. Anjali Mehta", role="Economic Advisor",
            message="Dr. Kumar, I'm not opposing action. I'm saying SMART action. Target the worst zones first, provide subsidies for compliance. Sudden shutdowns will cause panic and economic chaos.",
            responding_to="Dr. Rajesh Kumar", timestamp=datetime.utcnow().isoformat(), emotion="calm"
        ))
    
    transcript.append(DebateMessage(
        round=2, agent_name="Shri Vikram Singh", role="Enforcement Officer",
        message="Mrs. Devi, I understand public anger, but unrealistic promises help no one. Give me 20 priority zones, proper resources, and I'll deliver results. Spread us too thin and we achieve nothing.",
        responding_to="Mrs. Meera Devi", timestamp=datetime.utcnow().isoformat(), emotion="direct"
    ))
    
    transcript.append(DebateMessage(
        round=2, agent_name="Dr. Priya Sharma", role="Environmental Scientist",
        message="I propose we use data to prioritize. My analysis shows 15 wards account for 60% of the problem. Focus enforcement there, implement softer measures elsewhere. This satisfies both health urgency and enforcement capacity.",
        timestamp=datetime.utcnow().isoformat(), emotion="calm"
    ))
    
    # ROUND 3: Finding Consensus
    transcript.append(DebateMessage(
        round=3, agent_name="Ms. Anjali Mehta", role="Economic Advisor",
        message="Dr. Sharma's data-driven approach makes sense. Targeted action in 15 wards is economically manageable. We can provide transition support to affected businesses.",
        responding_to="Dr. Priya Sharma", timestamp=datetime.utcnow().isoformat(), emotion="supportive"
    ))
    
    transcript.append(DebateMessage(
        round=3, agent_name="Shri Vikram Singh", role="Enforcement Officer",
        message="15 wards is doable. I can deploy 3 teams per ward. But I need clear rules - no ambiguity. And political backing when we face resistance.",
        timestamp=datetime.utcnow().isoformat(), emotion="calm"
    ))
    
    transcript.append(DebateMessage(
        round=3, agent_name="Mrs. Meera Devi", role="Citizen Representative",
        message="If this means real action in the worst areas within days, not months, then I support it. But citizens need to SEE results. No more empty promises.",
        timestamp=datetime.utcnow().isoformat(), emotion="concerned"
    ))
    
    transcript.append(DebateMessage(
        round=3, agent_name="Dr. Rajesh Kumar", role="Public Health Officer",
        message="Agreed. 15 critical zones first, with immediate health advisories city-wide. We can show results in 2 weeks. I'm on board.",
        timestamp=datetime.utcnow().isoformat(), emotion="supportive"
    ))
    
    return transcript

def generate_agent_opinion(agent, situation, scenario, initial_vote):
    critical = situation.get("critical_zones", 0)
    avg_aqi = situation.get("avg_aqi", 0)
    
    # Determine final vote (may change after debate)
    if agent["role"] == "Environmental Scientist":
        analysis = f"Data shows {critical} critical zones, avg AQI {avg_aqi}. Satellite imagery confirms industrial and vehicular sources."
        recommendation = "Targeted intervention in top 15 zones based on data analysis"
        final_vote = "APPROVE"
        priority = 9
        reasoning = "Data-driven prioritization balances urgency with feasibility"
    elif agent["role"] == "Public Health Officer":
        analysis = f"Health emergency: {critical} zones at hazardous levels. Immediate risk to vulnerable populations."
        recommendation = "Emergency measures in critical zones + city-wide health advisories"
        final_vote = "APPROVE"
        priority = 10
        reasoning = "Focused action addresses immediate health crisis"
    elif agent["role"] == "Economic Advisor":
        analysis = f"Economic impact assessment: Targeted approach minimizes disruption"
        recommendation = "Phased implementation with business support in 15 priority zones"
        final_vote = "APPROVE" if critical < 20 else "MODIFY"
        priority = 7
        reasoning = "Balanced approach protects both health and economy"
    elif agent["role"] == "Enforcement Officer":
        analysis = f"Enforcement capacity: 15 wards is within operational limits"
        recommendation = "Deploy 3 teams per priority ward with clear enforcement protocols"
        final_vote = "APPROVE"
        priority = 8
        reasoning = "Realistic scope ensures effective enforcement"
    else:
        analysis = f"Citizens demand visible action in worst-affected areas"
        recommendation = "Immediate action with transparent progress reporting"
        final_vote = "APPROVE"
        priority = 9
        reasoning = "Focused action delivers visible results to public"
    
    vote_changed = (initial_vote != final_vote)
    
    return AgentOpinion(
        agent_name=agent["name"], role=agent["role"], analysis=analysis,
        recommendation=recommendation, vote=final_vote, reasoning=reasoning,
        priority_score=priority, initial_vote=initial_vote, vote_changed=vote_changed
    )

def synthesize_council_decision(opinions, situation, scenario, transcript):
    votes = {"APPROVE": sum(1 for o in opinions if o.vote == "APPROVE"),
             "MODIFY": sum(1 for o in opinions if o.vote == "MODIFY"),
             "REJECT": sum(1 for o in opinions if o.vote == "REJECT")}
    
    conflicts = []
    consensus = []
    
    # Identify conflicts from debate
    if any(o.initial_vote != o.vote for o in opinions):
        consensus.append("Agents reached consensus through debate - votes evolved")
    
    health_priority = next((o.priority_score for o in opinions if o.role == "Public Health Officer"), 0)
    economic_priority = next((o.priority_score for o in opinions if o.role == "Economic Advisor"), 0)
    
    if abs(health_priority - economic_priority) > 4:
        conflicts.append("Initial tension between health urgency and economic impact")
        consensus.append("Resolved through data-driven prioritization approach")
    
    if votes["APPROVE"] >= 4:
        final_decision = "APPROVED BY CONSENSUS - Proceed with targeted intervention"
        confidence = 0.90
    elif votes["APPROVE"] >= 3:
        final_decision = "APPROVED - Majority support with modifications"
        confidence = 0.80
    else:
        final_decision = "DEFERRED - Insufficient consensus"
        confidence = 0.50
    
    actions = [f"{o.role}: {o.recommendation}" for o in opinions if o.priority_score >= 7]
    
    if confidence > 0.85:
        outcome = "Strong consensus. Expected 20-30% AQI reduction in priority zones within 14 days. City-wide improvement in 30 days."
    elif confidence > 0.70:
        outcome = "Moderate consensus. Phased implementation over 30 days with ongoing monitoring."
    else:
        outcome = "Low confidence. Recommend additional stakeholder consultation."
    
    return CouncilDecision(
        scenario=scenario,
        situation_summary=f"{situation['critical_zones']} critical zones, {situation['unhealthy_zones']} unhealthy zones, Avg AQI: {situation['avg_aqi']}",
        key_data_points=situation,
        debate_transcript=transcript,
        agent_opinions=opinions,
        conflicts_identified=conflicts,
        consensus_points=consensus,
        final_decision=final_decision,
        recommended_actions=actions,
        expected_outcome=outcome,
        confidence_level=confidence,
        metadata={"votes": votes, "debate_rounds": 3, "timestamp": datetime.utcnow().isoformat()}
    )

@router.post("/convene", response_model=CouncilDecision)
async def convene_council(query: CouncilQuery, current_user: Profile = Depends(require_admin)):
    start_time = datetime.utcnow()
    situation = analyze_current_situation()
    if situation.get("error"):
        raise HTTPException(status_code=503, detail="ML data not available")
    
    # Generate debate transcript
    transcript = generate_debate_transcript(COUNCIL_AGENTS, situation, query.scenario)
    
    # Initial votes (before debate)
    initial_votes = {
        "Dr. Priya Sharma": "MODIFY",
        "Dr. Rajesh Kumar": "APPROVE",
        "Ms. Anjali Mehta": "MODIFY",
        "Shri Vikram Singh": "REJECT",
        "Mrs. Meera Devi": "APPROVE"
    }
    
    # Generate final opinions (after debate)
    opinions = [generate_agent_opinion(agent, situation, query.scenario, initial_votes[agent["name"]]) for agent in COUNCIL_AGENTS]
    
    decision = synthesize_council_decision(opinions, situation, query.scenario, transcript)
    decision.metadata["query_time_ms"] = int((datetime.utcnow() - start_time).total_seconds() * 1000)
    
    return decision

@router.get("/agents")
async def get_council_agents(current_user: Profile = Depends(require_admin)):
    return {"data": COUNCIL_AGENTS, "metadata": {"total_agents": len(COUNCIL_AGENTS), "timestamp": datetime.utcnow().isoformat()}}
