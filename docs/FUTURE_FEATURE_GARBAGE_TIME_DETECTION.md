# Future Feature: Garbage Time Detection

## Overview

Add "garbage time" indicators to player statistics to help fantasy owners better evaluate player performance. Garbage time refers to periods when a team has a comfortable lead or is losing by a large margin, leading to increased minutes for reserve players and potentially inflated stats that don't reflect actual competitive performance.

## Use Case Example

A player plays 2 minutes in the first 2 quarters. At halftime, the team is losing by 20+ points. The player then plays the full 24 minutes in the second half with that score differential maintained. While their stat line may look impressive, it's primarily garbage time production.

## Feature Requirements

### 1. Player Box Score Indicator
- Add garbage time flag/label to individual game box scores
- Display in player stats modal when viewing recent games
- Show in matchup projection when analyzing player contributions

### 2. Waiver Wire Integration
- Show garbage time label on last game stats
- Help fantasy owners identify if recent strong performance was garbage time
- Provide context for minute trends

### 3. Visual Indication (Option 3b - Moderate Detection)
- Conservative flagging to avoid false positives
- Include late 3rd quarter blowouts and extended garbage time
- Balance between accuracy and comprehensiveness

## Implementation Approaches

### Approach 1: Heuristic-Based Detection (RECOMMENDED TO START)

**Feasibility: ✅ High - Can implement immediately**

Uses only existing boxscore data to detect garbage time patterns.

#### Detection Criteria

```python
def is_garbage_time_heuristic(player_stats, team_stats, game_stats):
    """
    Detect garbage time based on game flow heuristics.
    
    Args:
        player_stats: Individual player box score
        team_stats: Team total stats for the game
        game_stats: Overall game metadata (final score, etc.)
    
    Returns:
        bool: True if likely garbage time
    """
    final_score_diff = abs(game_stats['home_score'] - game_stats['away_score'])
    is_starter = player_stats['IS_STARTER'] == 1
    minutes_played = player_stats['MIN']
    
    # Criteria for garbage time:
    # 1. Blowout game (15+ point differential)
    if final_score_diff >= 15:
        # Bench player with unusually high minutes in blowout
        if not is_starter and minutes_played > 12:
            return True
        
        # Starter with very low minutes (pulled early)
        if is_starter and minutes_played < 10:
            return True
    
    # 2. Massive blowout (25+ points)
    if final_score_diff >= 25:
        # Check team-level pattern: multiple bench players with high minutes
        if not is_starter and minutes_played > 8:
            return True
    
    return False
```

#### Pros
- ✅ No additional API calls needed
- ✅ Fast implementation (1-2 hours)
- ✅ No impact on cache refresh time
- ✅ Works with current data structure
- ✅ Can flag ~70-80% of garbage time scenarios
- ✅ Zero performance impact

#### Cons
- ⚠️ Less accurate than play-by-play analysis
- ⚠️ Won't catch nuanced cases (player entered in Q3 during developing blowout)
- ⚠️ Might miss games that were close but became garbage time late
- ⚠️ Can't determine exact timing of garbage time start

#### Implementation Details

**Backend Changes:**

1. **Add garbage time detection logic** (`tools/boxscore/garbage_time_detector.py`)
   ```python
   def detect_garbage_time(game_data: dict) -> dict[str, bool]:
       """Analyze game and return garbage time flags per player."""
       pass
   ```

2. **Update boxscore cache** (`tools/boxscore/boxscore_cache.py`)
   - Add `is_garbage_time` field to cached player game data
   - Run detection when saving game data
   - Rebuild existing cache with garbage time flags

3. **Update API models** (`backend/app/models/__init__.py`)
   ```python
   class PlayerBoxScore(BaseModel):
       # ... existing fields ...
       is_garbage_time: Optional[bool] = None
   ```

4. **Update API response** (`backend/app/api/players.py`, `backend/app/api/waiver.py`)
   - Include `is_garbage_time` in player game data
   - Add to waiver wire last game display

**Frontend Changes:**

1. **Update TypeScript types** (`frontend/src/types/api.ts`)
   ```typescript
   export interface PlayerBoxScore {
     // ... existing fields ...
     is_garbage_time?: boolean;
   }
   ```

2. **Add visual indicator** (`frontend/src/components/BoxScoreTable.tsx`)
   - Display "⏱️ Garbage Time" badge for flagged games
   - Use muted/gray styling to de-emphasize stats
   - Add tooltip explaining garbage time

3. **Update waiver wire** (`frontend/src/pages/WaiverWire.tsx`)
   - Show garbage time indicator on last game column
   - Consider filtering or sorting options

**Storage Impact:**
- Adds 1 boolean per player per game (~5-10KB per season)

---

### Approach 2: Play-by-Play Analysis (MORE ACCURATE)

**Feasibility: ⚠️ Medium - Requires significant work**

Fetches detailed play-by-play data to track score differential when player entered.

#### Detection Criteria

```python
def analyze_garbage_time_pbp(game_id: str):
    """
    Analyze play-by-play data to identify garbage time periods.
    
    Tracks:
    - Score differential at every substitution
    - When score differential exceeded threshold (20+ in Q4, 25+ in Q3)
    - Which players were on court during garbage time
    - Percentage of player's minutes in garbage time
    """
    pbp_data = fetch_play_by_play(game_id)
    
    garbage_time_periods = []
    
    for event in pbp_data:
        if is_garbage_time_threshold_met(event):
            garbage_time_periods.append(event['time'])
    
    # Calculate per-player garbage time percentage
    player_garbage_minutes = calculate_player_minutes_in_periods(
        pbp_data, 
        garbage_time_periods
    )
    
    # Flag if >50% of minutes were garbage time
    return {
        player_id: (minutes / total_minutes) > 0.5
        for player_id, minutes in player_garbage_minutes.items()
    }
```

#### Data Source Options

1. **NBA API Direct** (Recommended)
   ```
   https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{GAME_ID}.json
   ```

2. **nba_api library**
   ```python
   from nba_api.stats.endpoints import playbyplayv2
   pbp = playbyplayv2.PlayByPlayV2(game_id=game_id)
   ```

3. **pbpstats package** (Third-party)
   - More parsed data with lineup information
   - May have additional maintenance burden

#### Pros
- ✅ Highly accurate garbage time detection (95%+ accuracy)
- ✅ Can show exactly when garbage time started
- ✅ Perfect for the use case (player entering at halftime during blowout)
- ✅ Can calculate percentage of minutes in garbage time
- ✅ Catches nuanced scenarios (competitive game that became blowout)

#### Cons
- ❌ Additional API call per game (~1,500+ calls for full season)
- ❌ Significantly slower cache refresh (estimate 2-3x longer)
- ❌ More complex implementation (8-10 hours)
- ❌ Larger cache storage requirements (~50-100MB additional per season)
- ❌ Rate limiting concerns with NBA API (need careful throttling)
- ❌ Historical data might not be available for older games

#### Implementation Details

**Backend Changes:**

1. **Create play-by-play fetcher** (`tools/boxscore/pbp_fetcher.py`)
   ```python
   def fetch_play_by_play(game_id: str) -> dict:
       """Fetch PBP data from NBA API."""
       pass
   
   def parse_substitutions(pbp_data: dict) -> list:
       """Extract substitution events with timestamps and score."""
       pass
   
   def calculate_garbage_time_windows(pbp_data: dict) -> list[tuple]:
       """Identify time windows that qualify as garbage time."""
       pass
   ```

2. **Create advanced detector** (`tools/boxscore/garbage_time_detector.py`)
   ```python
   def detect_garbage_time_pbp(game_id: str, player_stats: dict) -> dict:
       """Analyze PBP data for garbage time detection."""
       pbp_data = fetch_play_by_play(game_id)
       garbage_windows = calculate_garbage_time_windows(pbp_data)
       
       return {
           player_id: calculate_player_garbage_pct(player_id, garbage_windows)
           for player_id in player_stats
       }
   ```

3. **Update cache system**
   - Cache play-by-play data separately
   - Store garbage time percentage (not just boolean)
   - Add metadata for garbage time detection version

4. **Update API models**
   ```python
   class PlayerBoxScore(BaseModel):
       # ... existing fields ...
       is_garbage_time: Optional[bool] = None
       garbage_time_pct: Optional[float] = None  # 0.0 to 1.0
       garbage_time_minutes: Optional[float] = None
   ```

**Storage Impact:**
- Play-by-play cache: ~50-100MB per season
- Per-game analysis: ~10-20KB per game
- Total additional storage: ~150-200MB per season

**Performance Impact:**
- Cache refresh time: +2-3x (from ~5min to ~15min for week refresh)
- One-time backfill for historical games: ~2-4 hours

---

## Recommended Implementation Plan

### Phase 1: Quick Win (Heuristic Approach)
**Timeline: 1-2 hours**

1. Implement heuristic detector
2. Add to cache and API
3. Add frontend badges
4. Test with recent games

**Goal:** Get immediate value with minimal investment

### Phase 2: Validation & Refinement
**Timeline: 1-2 weeks of monitoring**

1. Collect user feedback on accuracy
2. Tune heuristic thresholds
3. Measure false positive/negative rates
4. Decide if play-by-play upgrade is needed

### Phase 3: Enhanced Detection (Optional)
**Timeline: 8-10 hours if needed**

1. Implement play-by-play fetcher
2. Migrate detection to PBP analysis
3. Backfill historical games
4. A/B test accuracy improvements

**Goal:** Upgrade only if heuristic proves insufficient

---

## Hybrid Approach (Best of Both Worlds)

**Use heuristics by default, fetch PBP data only for ambiguous cases**

```python
def detect_garbage_time_hybrid(game_id: str, player_stats: dict) -> dict:
    """
    Smart garbage time detection:
    1. Run heuristic check (fast, free)
    2. If game is borderline (12-18 point margin), fetch PBP for accuracy
    3. Cache both heuristic and PBP results
    """
    heuristic_results = detect_garbage_time_heuristic(player_stats)
    
    # Only fetch PBP for ambiguous games
    if is_borderline_blowout(game_stats):
        pbp_results = detect_garbage_time_pbp(game_id, player_stats)
        return pbp_results
    
    return heuristic_results
```

**Benefits:**
- ✅ 95%+ accuracy where it matters
- ✅ Minimal performance impact (only ~20% of games need PBP)
- ✅ Reduces API calls by 80%
- ✅ Best user experience

---

## Technical Considerations

### Rate Limiting
- NBA API has informal rate limits (~3 requests/second)
- Implement exponential backoff
- Use `NBA_API_REQUESTS_PER_SECOND` env var (already exists)

### Cache Strategy
- Store garbage time flags in existing player game cache
- Invalidate and recalculate on detection logic changes
- Version the detection algorithm for cache busting

### Testing
- Create test cases with known garbage time games
- Test borderline scenarios (15-point games)
- Validate against manual analysis of sample games

### UI/UX Considerations
- Don't alarm users - it's informational, not punitive
- Use neutral language ("Limited competitive minutes")
- Provide educational tooltips
- Allow filtering/sorting by garbage time status

---

## Future Enhancements

1. **Garbage Time Stats Exclusion**
   - Calculate "competitive stats" that exclude garbage time
   - Show both full stats and competitive stats
   - Use competitive stats for projections

2. **Reverse Indicator: "Clutch Time"**
   - Flag games where player excelled in close games
   - Valuable counterpoint to garbage time

3. **Historical Trends**
   - Track player's garbage time percentage over season
   - Identify "garbage time specialists" vs "starters only"

4. **Impact on Projections**
   - Discount garbage time stats in season averages
   - Weight competitive minutes more heavily

---

## References

- [How to Access NBA Play-by-Play Data (Medium)](https://jman4190.medium.com/how-to-accessing-live-nba-play-by-play-data-f24e02b0a976)
- [pbpstats Python Package](https://pbpstats.readthedocs.io/)
- [SportsDataIO NBA API](https://sportsdata.io/nba-api)
- [NBA API CDN Documentation](https://github.com/swar/nba_api)

---

## Decision Log

**Date:** November 20, 2025
**Status:** Documented for future implementation
**Recommendation:** Start with Approach 1 (Heuristic), validate with users, optionally upgrade to Approach 2 or Hybrid based on feedback
**Estimated Effort:** 
- Phase 1: 1-2 hours
- Phase 2: Monitoring period
- Phase 3: 8-10 hours (if needed)

