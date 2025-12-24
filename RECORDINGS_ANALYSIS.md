# Recordings Database Analysis Plan

**Date:** December 24, 2025
**Branch:** recordings-database-fix
**Status:** Analysis phase - NO CODE CHANGES YET

## Problem Statement

**210 recordings from today missing from database** (212 on disk, only 2 in database)

### Current Situation
- Files ARE being saved to `/data/uploads/.../activity/`
- Database tracking is incomplete
- Only 2 out of 212 recordings from today are in `activity_events` table

### Key Observations
1. Reference implementation (camera.pahwa.net) has 292 recordings tracked correctly
2. Both cameras use same firmware: `V0_0_00_117RC_svn1356`
3. Reference camera sends `/activity/stop` events → recordings have `end_timestamp`
4. Current camera does NOT send stop events → recordings missing `end_timestamp`

## Root Cause Analysis Needed

### Event Ordering Scenarios (from user's note)

**Scenario A:** Activity start → File upload
1. Activity start event received → DB row created
2. File upload received → DB row updated with file paths

**Scenario B:** File upload → Activity start
1. File upload received → DB row created
2. Activity start event received → DB row updated with start time

### Questions to Answer

1. **How does reference implementation handle both scenarios?**
   - Check `enhanced_config_server.py` event/upload handling
   - Check `local_mqtt_processor.py` activity event handling
   - Look for notes/comments explaining the logic

2. **What changed in EMQX version?**
   - Compare event handling between reference and current
   - Check if MQTT topic structure changed
   - Verify event_id matching logic

3. **Why are most uploads not tracked?**
   - Is `get_event_by_id()` failing to find events?
   - Is the event_id parsing incorrect?
   - Are activity start events being created at all?

4. **Database update logic**
   - When is a new row created vs updated?
   - How is event_id uniqueness handled?
   - What happens if event doesn't exist when upload arrives?

## Files to Analyze

### Reference Implementation (`/home/spahwa/camera-project/`)
- [ ] `servers/enhanced_config_server.py` - File upload handling
- [ ] `servers/local_mqtt_processor.py` - MQTT event processing
- [ ] `servers/database_manager.py` - Database operations
- [ ] Any README or documentation about event ordering
- [ ] Look for comments explaining upload/event sync logic

### Current Implementation
- [ ] `servers/enhanced_config_server.py` - Compare with reference
- [ ] `servers/local_mqtt_processor.py` - Compare with reference
- [ ] `servers/database_manager.py` - Compare with reference
- [ ] Identify differences in event handling

## Analysis Tasks (Tonight - NO CODE CHANGES)

### 1. Document Reference Implementation Logic
- [ ] Read through reference config server upload handler
- [ ] Document how it handles event_id lookup
- [ ] Document database create vs update logic
- [ ] Note any special cases or edge conditions

### 2. Compare Implementations
- [ ] Create side-by-side comparison of key functions
- [ ] Identify missing logic in current version
- [ ] Note any structural differences

### 3. Verify Event Flow
- [ ] Check MQTT topic patterns in both implementations
- [ ] Verify event_id extraction from filenames
- [ ] Check if activity events are being created at all

### 4. Database State Analysis
- [ ] Count how many activity_events exist (start events)
- [ ] Count how many have file paths
- [ ] Identify the gap and what's missing

### 5. Create Fix Plan
- [ ] Document what needs to be changed
- [ ] Ensure fix handles both event ordering scenarios
- [ ] Ensure fix is repeatable (not manual database edits)
- [ ] Plan testing approach

## Expected Deliverables for Tomorrow

1. **Analysis Document**
   - Detailed comparison of reference vs current
   - Root cause identification
   - Specific code differences

2. **Fix Plan**
   - Exact changes needed
   - Test cases to verify
   - Migration approach for existing data (if needed)

3. **Questions for User** (if any)
   - Clarifications needed before implementing
   - Configuration decisions

## Notes

- Camera firmware identical between reference and current
- Reference works correctly → logic exists, just may be missing in current
- Focus on `enhanced_config_server.py` upload handling
- Look for comments like "handle case when event doesn't exist yet"
- Event ordering is key issue mentioned by user

## Success Criteria

Tomorrow's fix should:
1. ✅ Track ALL uploaded recordings in database
2. ✅ Handle upload-before-event scenario
3. ✅ Handle event-before-upload scenario
4. ✅ Work for future recordings automatically
5. ✅ Be repeatable (no manual database edits)

---

**Status:** Ready for overnight analysis
**Next Session:** Implement fix based on analysis findings
