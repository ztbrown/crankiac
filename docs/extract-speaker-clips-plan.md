# Plan: Extract Speaker Audio Clips Script

## Context

The user wants to generate reference audio clips for speaker enrollment. Currently they have to manually find and extract clips. This script automates it by using transcript data (which already has speaker labels and timestamps) to identify 10-15 clean clips per speaker from specified episodes, then extracting those audio segments to the `data/reference_audio/` directory structure that `enroll-speaker` already expects.

## Approach

Add a new `manage.py` subcommand: `extract-clips`

```bash
python manage.py extract-clips --speakers "Will Menaker,Felix Biederman" --episodes 1004,1005,1006
```

### How It Works

1. Look up episodes by number via `EpisodeRepository.get_by_episode_numbers()`
2. For each episode, get paragraphs via `TranscriptStorage.get_episode_paragraphs()`
3. Filter paragraphs by speaker name, keep only those 10-20 seconds long (good clip length)
4. Sort candidates by duration (prefer clips closest to 15s) and pick top 10-15 per speaker
5. Download audio if not already local (via `AudioDownloader`)
6. Use `torchaudio` (already in deps) to load audio and slice by timestamps
7. Save clips to `data/reference_audio/<Speaker Name>/ep<num>_<start>s.wav`

### Files to Modify

- **`app/transcription/clip_extractor.py`** (new) — `ClipExtractor` class with extraction logic
- **`manage.py`** — register `extract-clips` subcommand

### Implementation Details

**`ClipExtractor`** class:
- `__init__(output_dir="data/reference_audio")`
- `find_clip_candidates(episode_id, speaker_name, min_duration=10, max_duration=20)` — queries `get_episode_paragraphs`, filters by speaker and duration range
- `extract_clips(audio_path, candidates, speaker_name, episode_num)` — uses `torchaudio.load()` with frame offsets to slice audio, saves as WAV
- `run(speakers, episode_numbers, clips_per_speaker=12)` — orchestrator that ties it together

**Audio slicing** with torchaudio (no new deps):
```python
waveform, sr = torchaudio.load(audio_path)
start_frame = int(start_time * sr)
end_frame = int(end_time * sr)
clip = waveform[:, start_frame:end_frame]
torchaudio.save(output_path, clip, sr)
```

**`manage.py`** additions:
- `extract-clips` subparser with `--speakers`, `--episodes`, `--clips-per-speaker` (default 12), `--output-dir` (default `data/reference_audio`)

### Output Structure

```
data/reference_audio/
├── Will Menaker/
│   ├── ep1004_125.3s.wav
│   ├── ep1004_892.1s.wav
│   ├── ep1005_45.0s.wav
│   └── ...  (10-15 clips)
└── Felix Biederman/
    ├── ep1004_234.5s.wav
    └── ...
```

## Verification

1. Run `python manage.py extract-clips --speakers "Will Menaker" --episodes 1004 --clips-per-speaker 3`
2. Check `data/reference_audio/Will Menaker/` has 3 WAV files
3. Play a clip to verify it's clean speech from the correct speaker
4. Run `python manage.py enroll-speaker --name "Will Menaker"` to verify the clips work for enrollment
