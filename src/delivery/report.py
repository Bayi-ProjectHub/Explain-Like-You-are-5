"""Keep the native clocks and link observations by their overlap in playback time."""

from ..audio.schemas import TranscriptionResult
from .schemas import DeliveryEvidence, DeliveryReport, ReportMoment, SpeechExcerpt, TimelineSync


def build_delivery_report(evidence: DeliveryEvidence, transcript: TranscriptionResult) -> DeliveryReport:
    visual = evidence.visual
    audio_shift = evidence.audio_offset_seconds
    video_shift = visual.video_offset_seconds if visual else 0.0
    video_in_audio = round(video_shift - audio_shift, 6)

    def overlapping_speech(start: float, end: float) -> list[SpeechExcerpt]:
        excerpts = []
        for segment in transcript.segments:
            if segment.words:
                matches = [word for word in segment.words if word.start < end and word.end > start]
                if matches:
                    excerpts.append(SpeechExcerpt(segment_id=segment.id, precision="word",
                                                  start=matches[0].start, end=matches[-1].end,
                                                  text="".join(word.text for word in matches).strip()))
            elif segment.start < end and segment.end > start and segment.text:
                excerpts.append(SpeechExcerpt(segment_id=segment.id, precision="segment",
                                              start=segment.start, end=segment.end, text=segment.text))
        return excerpts

    audio = []
    for item in evidence.audio:
        speech = overlapping_speech(item.start, item.end)
        item.transcript_ids = [excerpt.segment_id for excerpt in speech]
        kind = "quiet" if "quiet_seconds" in item.metrics else "pace"
        audio.append(ReportMoment(id=item.id, start=item.start, end=item.end, kind=kind, metrics=item.metrics, speech=speech))

    video = []
    if visual:
        for item in [*visual.windows, *visual.events]:
            start = round(item.start + video_in_audio, 6)
            end = round(item.end + video_in_audio, 6)
            speech = overlapping_speech(start, end)
            item.transcript_ids = [excerpt.segment_id for excerpt in speech]
        for event in visual.events:
            start = round(event.start + video_in_audio, 6)
            end = round(event.end + video_in_audio, 6)
            links = [item.id for item in [*evidence.audio, *evidence.audio_levels]
                     if item.start < end and item.end > start]
            video.append(ReportMoment(id=event.id, start=event.start, end=event.end, kind=event.kind,
                                      metrics=event.metrics, measurements=event.measurements,
                                      speech=overlapping_speech(start, end), audio_refs=links))

    return DeliveryReport(
        sync=TimelineSync(audio_to_playback_seconds=audio_shift, video_to_playback_seconds=video_shift),
        video=video, audio=audio, audio_levels=evidence.audio_levels, transcript=transcript,
    )
