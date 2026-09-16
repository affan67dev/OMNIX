from datetime import datetime, timezone, timedelta

from backend.services.intelligence_core import (
    ContentState, Event, UserState, diversify, event_fingerprint, og_decision,
    og_health_score, omni_score, rank_candidates, safety_eligible, trust_score,
    update_user_state,
)


def test_event_idempotency_fingerprint_is_stable():
    event = Event('u1', 'like', 'p1', 'feed', session_id='s1', idempotency_key='k1')
    assert event_fingerprint(event) == event_fingerprint(event)


def test_negative_feedback_reduces_topic_affinity():
    state = UserState()
    update_user_state(state, Event('u1', 'like', 'p1', 'feed'), topic='python')
    before = state.short_topics['python']
    update_user_state(state, Event('u1', 'hide', 'p2', 'feed'), topic='python')
    assert state.short_topics['python'] < before


def test_chat_event_has_no_content_field_in_event_contract():
    event = Event('u1', 'chat_interaction', 'thread-1', 'ai')
    assert not hasattr(event, 'message_content')
    event.validate()


def test_ranking_is_deterministic_and_filters_confirmed_abuse():
    user = UserState(long_topics={'tech': 2.0}, short_topics={'tech': 2.0})
    safe = ContentState('a', 'creator-a', topic='tech', quality=.9, creator_quality=.7, freshness=.8)
    unsafe = ContentState('b', 'creator-b', topic='tech', quality=1.0, creator_quality=1.0, freshness=1.0)
    normal = trust_score()
    confirmed = trust_score(confirmed_abuse=True)
    first = rank_candidates(user, [safe, unsafe], {'creator-a': normal, 'creator-b': confirmed})
    second = rank_candidates(user, [safe, unsafe], {'creator-a': normal, 'creator-b': confirmed})
    assert [x.content.content_id for x in first] == [x.content.content_id for x in second] == ['a']
    assert safety_eligible(unsafe, confirmed) is False


def test_diversity_limits_creator_and_topic_concentration():
    items = rank_candidates(UserState(), [
        ContentState('1', 'same', topic='x', quality=.9),
        ContentState('2', 'same', topic='x', quality=.8),
        ContentState('3', 'same', topic='x', quality=.7),
        ContentState('4', 'other', topic='x', quality=.6),
    ])
    selected = diversify(items, max_per_creator=2, max_per_topic=3)
    assert len(selected) == 3
    assert sum(i.content.creator_id == 'same' for i in selected) == 2


def test_omni_score_is_not_raw_popularity():
    high = omni_score({'contribution':1,'authentic_engagement':1,'consistency':1,'community_behavior':1,'trust_integrity':1,'content_quality':1})
    low_trust = omni_score({'contribution':1,'authentic_engagement':1,'consistency':1,'community_behavior':1,'trust_integrity':0,'content_quality':1})
    assert high == 100
    assert low_trust < high


def test_og_health_and_seven_day_grace_transition():
    score = og_health_score({'content_quality':.2,'authenticity':.2,'healthy_engagement':.2,'consistency':.2,'community_behavior':.2,'trust_integrity':.2,'security_safety':.2})
    now = datetime(2026, 9, 16, tzinfo=timezone.utc)
    first = og_decision(score, now=now)
    assert first.state == 'red_grace'
    assert first.blue_tick and first.premium_plus
    after = now + timedelta(days=8)
    final = og_decision(score, grace_started=now, now=after)
    assert final.state == 'red_suspended'
    assert not final.blue_tick and not final.premium_plus


def test_og_compliance_is_hard_override():
    decision = og_decision(100, currently_compliant=False)
    assert decision.state == 'red'
    assert not decision.blue_tick and not decision.premium_plus
