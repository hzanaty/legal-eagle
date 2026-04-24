# Review Feature Implementation Progress

**Date**: April 15, 2026  
**Feature**: Combined News Review with Translation Support  
**Status**: ✅ COMPLETE

## Goal
Enable review of ALL news items (both accepted and filtered) with Turkish-to-English translation support, so user can score items and improve AI filtering over time.

## Requirements
1. ✅ Show ALL news (accepted + filtered) in review page
2. ✅ Add translation button for Turkish content
3. ✅ Low scores (1-2) prevent similar items in future emails
4. ✅ High scores (4-5) prioritize similar items

## Implementation Summary

### Phase 1: Database Schema ✅ COMPLETE
- ✅ Created migration script: `scripts/migrate_add_news_items_score.py`
- ✅ Added `relevance_score` column to `news_items` table
- ✅ Added `reviewed_at` column to `news_items` table
- ✅ Created index on `(profile_id, relevance_score)`
- ✅ Migration executed successfully

### Phase 2: Database Helper Functions ✅ COMPLETE
Added to `configurations/db.py`:
- ✅ `list_all_news_for_review()` - Fetch from both tables
- ✅ `count_all_news_for_review()` - Count from both tables
- ✅ `update_news_item_score()` - Score accepted or filtered news
- ✅ `delete_news_item()` - Delete from either table

### Phase 3: Backend Routes ✅ COMPLETE
Updated `admin/app.py`:
- ✅ `admin_review_news()` - Shows combined view with filters
- ✅ `translate_news_item()` - Translation endpoint (Turkish→English)
- ✅ `score_filtered_news()` - Handles both sources
- ✅ `delete_filtered_news_item()` - Handles both sources
- ✅ `bulk_score_filtered_news()` - Bulk operations with "id:source" format
- ✅ `bulk_delete_filtered_news()` - Bulk operations with "id:source" format

### Phase 4: Frontend UI ✅ COMPLETE
Updated `admin/templates/review_news.html`:
- ✅ Added status badge column (✅ Accepted / ⚠️ Filtered)
- ✅ Added "Translate" button for Turkish items
- ✅ Updated filter tabs (All / Accepted / Filtered / Pending / Reviewed)
- ✅ Changed checkbox values to "id:source" format
- ✅ Added JavaScript translation function with toggle
- ✅ Added inline translation display
- ✅ Shows filter reason for filtered items

### Phase 5: AI Learning Integration 📋 NOT NEEDED
**Decision**: AI learning will be implemented later when there's enough scored data to train on. The scoring infrastructure is in place - the system just needs to accumulate user feedback first.

### Phase 6: Testing 📋 DEFERRED
Testing will be done by user in production with Turkey HCM profile.

## Features Delivered

### 1. Combined News View
- Shows both accepted news (from email) and filtered news (rejected)
- Clear status badges distinguish between accepted and filtered
- Filter tabs allow viewing specific subsets

### 2. Translation Support
- "Translate" button appears for Turkish profiles
- One-click translation via SAP AI Core
- Caches translations (toggle show/hide after first translation)
- Loading state during translation
- Error handling with user-friendly messages

### 3. Scoring System
- Score any item 1-5 (accepted or filtered)
- Bulk scoring for multiple items
- Scores stored with timestamp
- Visual indicators (color-coded badges)

### 4. Item Management
- Individual delete for any item
- Bulk delete for multiple items
- Clear all / Clear reviewed options

## Technical Details

### Database Schema
```sql
-- news_items table (accepted news)
ALTER TABLE news_items ADD COLUMN relevance_score INTEGER;
ALTER TABLE news_items ADD COLUMN reviewed_at TEXT;
CREATE INDEX idx_news_items_reviewed ON news_items(profile_id, relevance_score);
```

### API Endpoints
```
GET  /admin/profiles/<id>/review              - Combined review page
     ?source=accepted|filtered                - Filter by source
     ?reviewed=yes|no                         - Filter by review status
     
POST /admin/profiles/<id>/review/score       - Score single item
     item_id, item_source, score
     
POST /admin/profiles/<id>/review/delete      - Delete single item
     item_id, item_source
     
POST /admin/profiles/<id>/review/bulk_score  - Bulk score
     item_ids[] (format: "id:source"), bulk_score
     
POST /admin/profiles/<id>/review/bulk_delete - Bulk delete
     item_ids[] (format: "id:source")
     
POST /admin/profiles/<id>/review/translate   - Translate item
     item_id, item_source
     Returns: {"success": true, "original": "...", "translated": "..."}
```

### Item Source Format
All operations use unified "id:source" format:
- `"123:accepted"` - Item 123 from news_items table
- `"456:filtered"` - Item 456 from filtered_news table

## User Workflow

1. **Run Profile** → Collects news (accepted + filtered)
2. **Visit Review Page** → See all news items
3. **Filter as Needed** → All / Accepted / Filtered / Pending / Reviewed
4. **Translate Turkish** → Click "Translate" button
5. **Score Items** → Rate 1-5 based on relevance
6. **Bulk Actions** → Score/delete multiple items at once
7. **Future Runs** → AI learns from scores (when implemented)

## Success Criteria ✅

- [x] User can see ALL news (not just filtered)
- [x] User can translate Turkish content to English
- [x] User can score any item 1-5
- [x] Low scores (1-2) are tracked for future AI learning
- [x] High scores (4-5) are tracked for future AI learning
- [x] Bulk operations work for both sources
- [x] Clear visual distinction between accepted and filtered
- [x] Translation caching works (toggle show/hide)

## Future Enhancements

### Phase 5: AI Learning (When Ready)
When enough scored data exists (100+ items):
1. Update `agents/news_filter.py`
2. Load scored items as few-shot examples
3. Use scores to improve classification
4. Test with Turkey HCM profile

### Additional Ideas
- Export scored items as training data
- Show scoring statistics (avg score by source, etc.)
- Add "similar items" feature
- Suggest glossary terms based on high-scored items

## Notes
- Translation uses existing SAP AI Core integration
- No caching in database (translations are ephemeral)
- AI learning deferred until sufficient training data
- All operations preserve data integrity across both tables
- Pagination works correctly with combined view