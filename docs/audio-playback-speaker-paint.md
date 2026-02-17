# Plan: Audio Playback + Quick Speaker Assignment

## Context

The transcript editor works but the speaker assignment workflow is slow (select text → modal → type name → confirm) and there's no way to hear the audio while editing. Both features already have backend support — audio streaming with Range/seek (`/api/audio/stream/<patreon_id>`) and an episode speakers endpoint (`/api/transcripts/episode/<id>/speakers` returning `known_speakers` + `episode_speakers`).

**No API changes needed.** All work is in the three frontend files.

## Files to Modify

- `app/ui/static/editor.html` — add audio player bar + speaker palette markup
- `app/ui/static/editor.js` — new methods + modify existing ones
- `app/ui/static/editor.css` — audio player, timestamps, palette, paint-mode styles

## Feature 1: Audio Playback

**Sticky audio player bar at bottom of viewport.**

1. **Store episode metadata** — save `this.episodes` array from loadEpisodes, look up `patreon_id` on episode change
2. **Check audio availability** — `GET /api/audio/info/<patreon_id>` on episode load; if available, set `<audio>` src to stream URL and show player
3. **Player UI** — play/pause button, current time, seek bar (range input), duration. Dark bar, fixed bottom.
4. **Click paragraph to seek** — `audioElement.currentTime = paragraph.start_time`, auto-play
5. **Show timestamps** — `mm:ss` span next to each speaker label using `paragraph.start_time`
6. **Highlight active paragraph** — `timeupdate` event checks which paragraph's time range contains `currentTime`, adds `.audio-active` class, smooth-scrolls into view
7. **Adjust toast position** — move toasts above the audio bar when it's visible (`body.has-audio-player`)

## Feature 2: Quick Speaker Assignment (Paint Mode)

**Speaker palette toolbar with click-to-assign.**

1. **Speaker palette** — bar below mode toggle showing buttons for each speaker (known + episode-specific). Only visible in speaker mode with an episode loaded.
2. **Load episode speakers** — `GET /api/transcripts/episode/<id>/speakers` on episode change. Merge known + episode speakers, cross-reference with `this.speakers` for IDs.
3. **Arm/disarm** — click speaker button to "arm" it (highlighted blue). Click again to disarm. Only one armed at a time.
4. **Paint mode** — when armed: container gets `paint-mode` class (crosshair cursor, `user-select: none`, hover highlight on paragraphs)
5. **Click paragraph to assign** — uses `segment_ids[0]` and `segment_ids[last]` for the assign-speaker API. Speaker stays armed for rapid painting. Transcript reloads after each assignment.
6. **Guard existing selection** — `handleTextSelection` returns early if `this.armedSpeaker` is set, preventing the modal from opening in paint mode.

## Click Handler Priority

Single consolidated click on `.paragraph`:
1. Armed speaker → assign speaker (paint mode)
2. Audio available + no text selected → seek audio
3. Text selected via mouseup → existing speaker dialog (only if not armed)

## Implementation Steps

1. **editor.js**: Add new state (`episodes`, `currentPatreonId`, `audioAvailable`, `armedSpeaker`, `episodeSpeakers`), `formatTime` utility
2. **editor.html**: Add audio player bar markup + speaker palette markup
3. **editor.css**: All new styles (audio player, timestamps, active paragraph, speaker palette, paint mode, toast offset)
4. **editor.js**: Audio methods — `initAudioElements`, `attachAudioListeners`, `checkAudioAvailability`, `showAudioPlayer`/`hideAudioPlayer`, `togglePlayPause`, `handleTimeUpdate`, `highlightActiveParagraph`, `seekToTime`
5. **editor.js**: Speaker palette methods — `loadEpisodeSpeakers`, `renderSpeakerPalette`, `toggleArmedSpeaker`, `handleParagraphPaint`
6. **editor.js**: Modify `loadEpisodes`, `handleEpisodeChange`, `renderTranscript` (timestamps + consolidated click handler), `setMode` (palette visibility), `handleTextSelection` (paint mode guard)

## Verification

1. Start the Flask app and open `/editor`
2. Select an episode that has audio in `downloads/audio/`
3. Verify: audio player appears at bottom, play/pause works, seek bar works
4. Verify: paragraphs show timestamps, clicking a paragraph seeks and plays audio
5. Verify: active paragraph highlights as audio plays
6. Switch to speaker mode — verify speaker palette appears with buttons
7. Click a speaker button — verify it highlights, cursor becomes crosshair
8. Click a paragraph — verify speaker is assigned (toast confirms), paragraph updates
9. Click another paragraph — verify speaker is still armed (rapid painting works)
10. Click armed speaker button again — verify it disarms
11. Switch to edit mode — verify palette hides and paint mode disengages
12. Select text in speaker mode with no armed speaker — verify existing modal flow still works
