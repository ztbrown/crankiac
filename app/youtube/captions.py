"""YouTube caption fetching for episodes with YouTube URLs."""
import os
import tempfile
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)

from app.youtube.timestamp import extract_video_id


@dataclass
class CaptionSegment:
    """A segment of caption text with timing information."""
    text: str
    start_time: Decimal
    duration: Decimal

    @property
    def end_time(self) -> Decimal:
        """Calculate end time from start + duration."""
        return self.start_time + self.duration


@dataclass
class CaptionResult:
    """Result of fetching captions for a video."""
    video_id: str
    segments: list[CaptionSegment]
    language: str
    is_auto_generated: bool
    source: str  # 'youtube_captions' or 'whisper_fallback'


class CaptionFetchError(Exception):
    """Error fetching captions from YouTube."""
    pass


class YouTubeCaptionClient:
    """Client for fetching YouTube auto-generated captions."""

    def __init__(self, whisper_model: str = "base"):
        """
        Initialize the caption client.

        Args:
            whisper_model: Whisper model to use for fallback transcription.
        """
        self.whisper_model = whisper_model

    def fetch_captions(
        self,
        youtube_url: str,
        languages: list[str] = None,
        fallback_to_whisper: bool = True,
    ) -> Optional[CaptionResult]:
        """
        Fetch captions for a YouTube video.

        First attempts to get auto-generated captions. If unavailable and
        fallback_to_whisper is True, downloads a sample of audio and
        transcribes with Whisper.

        Args:
            youtube_url: Full YouTube URL or video ID.
            languages: Preferred languages in order (default: ['en']).
            fallback_to_whisper: Whether to transcribe audio if no captions.

        Returns:
            CaptionResult with segments, or None if completely unavailable.

        Raises:
            CaptionFetchError: If video is unavailable or other fatal error.
        """
        video_id = extract_video_id(youtube_url)
        if not video_id:
            # Maybe it's already a video ID
            if len(youtube_url) == 11 and youtube_url.isalnum():
                video_id = youtube_url
            else:
                raise CaptionFetchError(f"Could not extract video ID from: {youtube_url}")

        if languages is None:
            languages = ['en']

        # Try to fetch YouTube captions
        result = self._fetch_youtube_captions(video_id, languages)
        if result:
            return result

        # Fallback to Whisper transcription if enabled
        if fallback_to_whisper:
            return self._transcribe_with_whisper(video_id)

        return None

    def _fetch_youtube_captions(
        self,
        video_id: str,
        languages: list[str],
    ) -> Optional[CaptionResult]:
        """
        Fetch captions directly from YouTube.

        Args:
            video_id: YouTube video ID.
            languages: Preferred languages.

        Returns:
            CaptionResult or None if no captions available.
        """
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

            # Try to find auto-generated transcript first (better for our use case)
            transcript = None
            is_auto = False

            # First, try auto-generated transcripts
            for lang in languages:
                try:
                    transcript = transcript_list.find_generated_transcript([lang])
                    is_auto = True
                    break
                except NoTranscriptFound:
                    continue

            # If no auto-generated, try manual transcripts
            if transcript is None:
                for lang in languages:
                    try:
                        transcript = transcript_list.find_manually_created_transcript([lang])
                        is_auto = False
                        break
                    except NoTranscriptFound:
                        continue

            if transcript is None:
                return None

            # Fetch the actual transcript data
            data = transcript.fetch()

            segments = [
                CaptionSegment(
                    text=item['text'],
                    start_time=Decimal(str(item['start'])),
                    duration=Decimal(str(item['duration'])),
                )
                for item in data
            ]

            return CaptionResult(
                video_id=video_id,
                segments=segments,
                language=transcript.language_code,
                is_auto_generated=is_auto,
                source='youtube_captions',
            )

        except VideoUnavailable:
            raise CaptionFetchError(f"Video {video_id} is unavailable")
        except TranscriptsDisabled:
            return None  # No captions available, can fallback
        except NoTranscriptFound:
            return None  # No captions in requested languages
        except Exception as e:
            # Log but don't raise - allow fallback
            print(f"Warning: Error fetching captions for {video_id}: {e}")
            return None

    def _transcribe_with_whisper(self, video_id: str) -> Optional[CaptionResult]:
        """
        Download audio sample and transcribe with Whisper.

        Args:
            video_id: YouTube video ID.

        Returns:
            CaptionResult from Whisper transcription, or None on failure.
        """
        try:
            import yt_dlp
            import whisper
        except ImportError as e:
            print(f"Warning: Missing dependency for Whisper fallback: {e}")
            return None

        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = os.path.join(tmpdir, f"{video_id}.mp3")

            # Download audio (first 5 minutes for sample)
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': audio_path.replace('.mp3', '.%(ext)s'),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'quiet': True,
                'no_warnings': True,
                # Download only first 5 minutes as sample
                'download_ranges': lambda info, ydl: [{'start_time': 0, 'end_time': 300}],
            }

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
            except Exception as e:
                print(f"Warning: Failed to download audio for {video_id}: {e}")
                return None

            # Check if audio file was created
            if not os.path.exists(audio_path):
                # Try with different extension
                for ext in ['.m4a', '.webm', '.opus']:
                    alt_path = audio_path.replace('.mp3', ext)
                    if os.path.exists(alt_path):
                        audio_path = alt_path
                        break
                else:
                    print(f"Warning: Audio file not found for {video_id}")
                    return None

            # Transcribe with Whisper
            try:
                model = whisper.load_model(self.whisper_model)
                result = model.transcribe(audio_path, word_timestamps=True)
            except Exception as e:
                print(f"Warning: Whisper transcription failed for {video_id}: {e}")
                return None

            # Convert Whisper segments to CaptionSegments
            segments = []
            for segment in result.get('segments', []):
                segments.append(CaptionSegment(
                    text=segment['text'].strip(),
                    start_time=Decimal(str(segment['start'])),
                    duration=Decimal(str(segment['end'] - segment['start'])),
                ))

            return CaptionResult(
                video_id=video_id,
                segments=segments,
                language='en',
                is_auto_generated=True,
                source='whisper_fallback',
            )


def fetch_captions_for_video(
    youtube_url: str,
    fallback_to_whisper: bool = True,
    whisper_model: str = "base",
) -> Optional[CaptionResult]:
    """
    Convenience function to fetch captions for a single video.

    Args:
        youtube_url: YouTube video URL.
        fallback_to_whisper: Whether to use Whisper if no captions.
        whisper_model: Whisper model for fallback transcription.

    Returns:
        CaptionResult or None if unavailable.
    """
    client = YouTubeCaptionClient(whisper_model=whisper_model)
    return client.fetch_captions(
        youtube_url,
        fallback_to_whisper=fallback_to_whisper,
    )


def captions_to_word_segments(result: CaptionResult) -> list[dict]:
    """
    Convert caption segments to word-level segments.

    Splits caption text into words and approximates word timestamps
    by distributing them evenly across the segment duration.

    Args:
        result: CaptionResult with phrase-level segments.

    Returns:
        List of dicts with word, start_time, end_time, segment_index.
    """
    word_segments = []
    segment_index = 0

    for caption in result.segments:
        words = caption.text.split()
        if not words:
            continue

        # Distribute time evenly across words
        duration_per_word = caption.duration / len(words)
        current_time = caption.start_time

        for word in words:
            # Clean up word (remove punctuation at edges but keep contractions)
            cleaned_word = word.strip()
            if not cleaned_word:
                continue

            word_segments.append({
                'word': cleaned_word,
                'start_time': current_time,
                'end_time': current_time + duration_per_word,
                'segment_index': segment_index,
            })

            current_time += duration_per_word
            segment_index += 1

    return word_segments


def store_captions_for_episode(episode_id: int, result: CaptionResult) -> int:
    """
    Store caption segments as transcript data for an episode.

    Converts caption phrases to word-level segments and stores them
    in the transcript_segments table.

    Args:
        episode_id: Database ID of the episode.
        result: CaptionResult to store.

    Returns:
        Number of word segments stored.
    """
    from app.db.models import TranscriptSegment
    from app.transcription.storage import TranscriptStorage

    word_segments = captions_to_word_segments(result)

    segments = [
        TranscriptSegment(
            id=None,
            episode_id=episode_id,
            word=ws['word'],
            start_time=ws['start_time'],
            end_time=ws['end_time'],
            segment_index=ws['segment_index'],
            speaker=None,  # YouTube captions don't have speaker info
        )
        for ws in word_segments
    ]

    storage = TranscriptStorage()
    return storage.bulk_insert(segments)
