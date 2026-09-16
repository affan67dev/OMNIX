from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any, Mapping, Sequence

EVENTS = {
    'view','watch','completion','rewatch','like','comment','save','share','follow','unfollow',
    'search','skip','hide','not_interested','mute','block','report','story_view','reel_view',
    'chat_interaction','notification_interaction','create','session_start'
}
NEGATIVE_EVENTS = {'skip','hide','not_interested','mute','block','report','unfollow'}
SURFACES = {'feed','reels','stories','discovery','search','notifications','suggestions','ai'}

@dataclass(frozen=True)
class Event:
    user_id: str
    event_type: str
    object_id: str | None = None
    surface: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    session_id: str | None = None
    duration_ms: int | None = None
    value: float | None = None
    idempotency_key: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    def validate(self) -> None:
        if self.event_type not in EVENTS: raise ValueError('unsupported event_type')
        if self.surface is not None and self.surface not in SURFACES: raise ValueError('unsupported surface')
        if self.duration_ms is not None and (self.duration_ms < 0 or self.duration_ms > 86_400_000): raise ValueError('invalid duration_ms')
        if self.idempotency_key and len(self.idempotency_key) > 200: raise ValueError('idempotency_key too long')

@dataclass
class UserState:
    short_topics: dict[str, float] = field(default_factory=dict)
    long_topics: dict[str, float] = field(default_factory=dict)
    format_affinity: dict[str, float] = field(default_factory=dict)
    creator_affinity: dict[str, float] = field(default_factory=dict)
    relationship_affinity: dict[str, float] = field(default_factory=dict)
    recent_negative: dict[str, float] = field(default_factory=dict)
    session_intent: dict[str, float] = field(default_factory=dict)

@dataclass(frozen=True)
class ContentState:
    content_id: str
    creator_id: str
    topic: str | None = None
    language: str | None = None
    format: str | None = None
    freshness: float = 0.0
    quality: float = 0.5
    creator_quality: float = 0.5
    safety_state: str = 'eligible'
    semantic: tuple[str, ...] = ()

@dataclass(frozen=True)
class TrustDecision:
    risk: float
    state: str
    reasons: tuple[str, ...]
    confirmed_abuse: bool = False

@dataclass(frozen=True)
class RankedItem:
    content: ContentState
    score: float
    signals: Mapping[str, float]

@dataclass(frozen=True)
class OGDecision:
    score: float
    state: str
    reason_codes: tuple[str, ...]
    grace_until: datetime | None
    blue_tick: bool
    premium_plus: bool

@dataclass(frozen=True)
class StreakDecision:
    current_streak: int
    used_freeze: bool
    eligible: bool
    reason: str


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def event_fingerprint(event: Event) -> str:
    raw = '|'.join(str(x) for x in (event.user_id, event.event_type, event.object_id, event.surface, event.session_id, event.idempotency_key))
    return sha256(raw.encode()).hexdigest()


def update_user_state(state: UserState, event: Event, topic: str | None = None, fmt: str | None = None, creator_id: str | None = None) -> UserState:
    event.validate()
    direction = -1.0 if event.event_type in NEGATIVE_EVENTS else 1.0
    strength = 1.0
    if event.event_type == 'watch': strength = _clamp((event.duration_ms or 0) / 60_000, 0.0, 2.0)
    elif event.event_type == 'completion': strength = 1.4
    elif event.event_type in {'save','share','comment'}: strength = 1.8
    elif event.event_type in NEGATIVE_EVENTS: strength = 2.0
    decay = 0.82
    if topic:
        state.short_topics[topic] = state.short_topics.get(topic, 0.0) * decay + direction * strength
        state.long_topics[topic] = state.long_topics.get(topic, 0.0) * 0.995 + direction * strength * 0.15
        if event.event_type in NEGATIVE_EVENTS: state.recent_negative[topic] = state.recent_negative.get(topic, 0.0) * decay + abs(strength)
    if fmt: state.format_affinity[fmt] = state.format_affinity.get(fmt, 0.0) * decay + direction * strength
    if creator_id: state.creator_affinity[creator_id] = state.creator_affinity.get(creator_id, 0.0) * decay + direction * strength
    if event.surface: state.session_intent[event.surface] = state.session_intent.get(event.surface, 0.0) * decay + 1.0
    return state


def session_intent_score(state: UserState, topic: str | None, fmt: str | None) -> float:
    return state.short_topics.get(topic or '', 0.0) * .55 + state.long_topics.get(topic or '', 0.0) * .20 + state.format_affinity.get(fmt or '', 0.0) * .25


def trust_score(*, reciprocal_ratio: float = 0.0, burstiness: float = 0.0, cluster_concentration: float = 0.0, report_rate: float = 0.0, persistence: float = 0.0, corroboration: float = 0.0, confirmed_abuse: bool = False) -> TrustDecision:
    if confirmed_abuse: return TrustDecision(1.0, 'confirmed', ('confirmed_abuse',), True)
    raw = _clamp(.30 * reciprocal_ratio + .25 * burstiness + .20 * cluster_concentration + .15 * report_rate + .10 * persistence + .20 * corroboration)
    if raw >= .75 and persistence >= .60 and corroboration >= .35: return TrustDecision(raw, 'review', ('coordinated_pattern','persistent','corroborated'))
    if raw >= .45: return TrustDecision(raw, 'suspicious', ('risk_signal',))
    return TrustDecision(raw, 'normal', ())


def safety_eligible(content: ContentState, trust: TrustDecision) -> bool:
    return content.safety_state == 'eligible' and not trust.confirmed_abuse


def rank_candidates(user: UserState, candidates: Sequence[ContentState], trust_by_creator: Mapping[str, TrustDecision] | None = None, recent_ids: set[str] | None = None) -> list[RankedItem]:
    trust_by_creator = trust_by_creator or {}; recent_ids = recent_ids or set(); ranked: list[RankedItem] = []
    for c in candidates:
        trust = trust_by_creator.get(c.creator_id, TrustDecision(0.0, 'normal', ()))
        if not safety_eligible(c, trust): continue
        relevance = _clamp(.6 * session_intent_score(user, c.topic, c.format) / 3 + .4 * user.long_topics.get(c.topic or '', 0.0) / 5)
        relationship = _clamp(user.relationship_affinity.get(c.creator_id, 0.0) / 5); creator = _clamp(c.creator_quality); quality = _clamp(c.quality); freshness = _clamp(c.freshness)
        negative = _clamp(user.recent_negative.get(c.topic or '', 0.0) / 5); repetition = 1.0 if c.content_id in recent_ids else 0.0; risk = trust.risk
        meaningful = _clamp(.45 * quality + .25 * creator + .15 * relevance + .15 * relationship); exploration = .12 * (1.0 - creator) * (.5 + .5 * freshness)
        score = .30 * relevance + .20 * meaningful + .15 * relationship + .10 * quality + .08 * creator + .08 * freshness + exploration - .20 * negative - .12 * repetition - .30 * risk
        ranked.append(RankedItem(c, score, {'relevance':relevance,'meaningful':meaningful,'relationship':relationship,'quality':quality,'creator_quality':creator,'freshness':freshness,'exploration':exploration,'negative':negative,'repetition':repetition,'risk':risk}))
    ranked.sort(key=lambda x: (-round(x.score, 9), x.content.content_id)); return ranked


def diversify(items: Sequence[RankedItem], max_per_creator: int = 2, max_per_topic: int = 3) -> list[RankedItem]:
    out=[]; creators={}; topics={}
    for item in items:
        c=item.content.creator_id; t=item.content.topic or ''
        if creators.get(c,0)>=max_per_creator or topics.get(t,0)>=max_per_topic: continue
        creators[c]=creators.get(c,0)+1; topics[t]=topics.get(t,0)+1; out.append(item)
    return out


def omni_score(dimensions: Mapping[str, float]) -> float:
    weights={'contribution':.20,'authentic_engagement':.18,'consistency':.15,'community_behavior':.18,'trust_integrity':.20,'content_quality':.09}
    return round(_clamp(sum(_clamp(dimensions.get(k,0.0))*w for k,w in weights.items()))*100,2)


def og_health_score(dimensions: Mapping[str, float], confirmed_safety_violation: bool = False) -> float:
    if confirmed_safety_violation: return 0.0
    weights={'content_quality':.20,'authenticity':.15,'healthy_engagement':.15,'consistency':.10,'community_behavior':.15,'trust_integrity':.15,'security_safety':.10}
    return round(_clamp(sum(_clamp(dimensions.get(k,0.0))*w for k,w in weights.items()))*100,2)


def og_decision(score: float, *, currently_compliant: bool = True, grace_started: datetime | None = None, now: datetime | None = None, recovered: bool = False) -> OGDecision:
    now=now or datetime.now(timezone.utc)
    if not currently_compliant: return OGDecision(score,'red',('compliance_hold',),None,False,False)
    if score>=80: return OGDecision(score,'green',('health_green',),None,True,True)
    if score>=50: return OGDecision(score,'yellow',('health_below_80',),None,True,True)
    if recovered: return OGDecision(score,'yellow',('recovered',),None,True,True)
    if grace_started is None: return OGDecision(score,'red_grace',('health_below_50',),now+timedelta(days=7),True,True)
    if now < grace_started+timedelta(days=7): return OGDecision(score,'red_grace',('grace_active',),grace_started+timedelta(days=7),True,True)
    return OGDecision(score,'red_suspended',('grace_expired',),grace_started+timedelta(days=7),False,False)


def streak_decision(*, current_streak: int, last_meaningful_at: datetime | None, now: datetime | None = None, freeze_available: bool = False, integrity_blocked: bool = False, meaningful_today: bool = False) -> StreakDecision:
    now=now or datetime.now(timezone.utc)
    if integrity_blocked: return StreakDecision(current_streak,False,False,'integrity_blocked')
    if meaningful_today: return StreakDecision(current_streak+1,False,True,'meaningful_activity')
    if last_meaningful_at is None: return StreakDecision(current_streak,False,False,'no_prior_activity')
    elapsed=now-last_meaningful_at
    if elapsed <= timedelta(days=1, hours=6): return StreakDecision(current_streak,False,True,'within_window')
    if elapsed <= timedelta(days=2) and freeze_available: return StreakDecision(current_streak,True,True,'freeze_consumed')
    return StreakDecision(0,False,False,'streak_broken')
