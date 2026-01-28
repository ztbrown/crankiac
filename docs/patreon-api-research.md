# Patreon API Research: YouTube URLs and Tier Information

Research task: cr-kczn
Date: 2026-01-28

## Executive Summary

The Patreon API exposes both YouTube embed URLs and tier/access information directly in the post response. No HTML parsing is required for YouTube URLs when videos are embedded via Patreon's embed feature.

## Findings

### 1. YouTube Embed URLs

**Yes, the Patreon API exposes YouTube URLs directly.**

The current client uses the internal API (`https://www.patreon.com/api/posts`). Posts with embedded videos have an `embed` object containing:

```json
{
  "embed": {
    "url": "https://www.youtube.com/watch?v=VIDEO_ID",
    "domain": "youtube.com",
    "html": "<iframe ...></iframe>",
    "subject": "Video Title",
    "description": "Video description text"
  }
}
```

**Key fields:**
- `embed.url` - Direct YouTube URL (or other video platform URL)
- `embed.domain` - Platform identifier (e.g., "youtube.com", "vimeo.com")
- `embed.html` - Full embed iframe HTML (can be parsed as fallback)

**Note:** All embed sub-fields are `null` for non-video posts.

### 2. Free vs Premium Tier Indicators

**Internal API (current implementation):**

Uses `min_cents_pledged_to_view` field:
- `0` or `null` = Public/free content (anyone can view)
- `> 0` = Premium content (requires minimum pledge amount in cents)

**OAuth v2 API (alternative):**

Uses these fields:
- `is_public` (boolean) - `true` = viewable by anyone, `false` = patrons only
- `is_paid` (boolean) - `true` = pay-per-post content
- `tiers` (relationship) - List of tier IDs that have access (when restricted)

### 3. HTML Parsing Not Required

When creators embed YouTube videos using Patreon's embed feature, the URL is available directly in `embed.url`. HTML parsing is only needed if:
- Creator manually pastes YouTube links in the post content
- Creator uses raw HTML instead of Patreon's embed feature

For manual links in content, would need to parse `content` field with regex:
```python
# Pattern for YouTube URLs in content HTML
r'(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})'
```

### 4. Implementation Recommendations

**To add YouTube URL and tier info to the current client:**

1. **Update field request** in `get_episodes()`:
```python
params = {
    "include": "audio,audio_preview",
    "fields[post]": "title,published_at,post_file,audio,embed,min_cents_pledged_to_view",
    # ... other params
}
```

2. **Update `PatreonEpisode` dataclass:**
```python
@dataclass
class PatreonEpisode:
    id: str
    title: str
    audio_url: Optional[str]
    published_at: Optional[str]
    duration_seconds: Optional[int]
    embed_url: Optional[str]      # NEW: YouTube or other embed URL
    is_free: bool                 # NEW: True if min_cents_pledged_to_view == 0
```

3. **Extract data from response:**
```python
attrs = post.get("attributes", {})
embed = attrs.get("embed", {}) or {}

embed_url = embed.get("url")  # YouTube URL if present
min_cents = attrs.get("min_cents_pledged_to_view", 0) or 0
is_free = min_cents == 0
```

### 5. API Endpoint Reference

**Internal API (current):**
- Base: `https://www.patreon.com/api`
- Posts: `GET /posts?filter[campaign_id]=...`
- Auth: `session_id` cookie

**OAuth v2 API (alternative):**
- Base: `https://www.patreon.com/api/oauth2/v2`
- Posts: `GET /campaigns/{campaign_id}/posts`
- Fields: `fields[post]=title,content,is_public,embed_url,embed_data`
- Auth: OAuth 2.0 access token

## Sources

- Patreon API official docs: https://docs.patreon.com/
- Reverse-engineered API documentation: https://github.com/oxguy3/patreon-api
- Patreon developer forum: https://www.patreondevelopers.com/

## Next Steps

This research unblocks cr-iqu4 (Enhance Patreon client to fetch YouTube URLs and tier status). The implementation should:

1. Add `embed` and `min_cents_pledged_to_view` to the fields request
2. Update `PatreonEpisode` with new fields
3. Modify episode sync to store this data in the database
4. Update the existing `youtube_url` matching logic to prefer Patreon's direct embed URL over YouTube RSS matching
