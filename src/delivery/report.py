"""Combine local video observations, audio measurements and recognized speech."""

from ..audio.schemas import TranscriptionResult
from .schemas import DeliveryEvidence, DeliveryReport, ReportMoment, SpeechExcerpt


def build_delivery_report(evidence: DeliveryEvidence, transcript: TranscriptionResult) -> DeliveryReport:
    offset = evidence.audio_offset_seconds
    timed_segments = [
        (segment, [
            (round(word.start + offset, 3), round(word.end + offset, 3), word.text)
            for word in segment.words
        ]) for segment in transcript.segments
    ]

    def overlapping_speech(start: float, end: float) -> list[SpeechExcerpt]:
        excerpts = []
        for segment, timed_words in timed_segments:
            if timed_words:
                matches = [(a, b, text) for a, b, text in timed_words if a < end and b > start]
                if matches:
                    excerpts.append(SpeechExcerpt(segment_id=segment.id, precision="word",
                                                  start=matches[0][0], end=matches[-1][1],
                                                  text="".join(text for _, _, text in matches).strip()))
            else:
                a, b = round(segment.start + offset, 3), round(segment.end + offset, 3)
                if a < end and b > start and segment.text:
                    excerpts.append(SpeechExcerpt(segment_id=segment.id, precision="segment",
                                                  start=a, end=b, text=segment.text))
        return excerpts

    timeline = []
    for item in evidence.audio:
        speech = overlapping_speech(item.start, item.end)
        item.transcript_ids = [excerpt.segment_id for excerpt in speech]
        kind = "quiet" if "quiet_seconds" in item.metrics else "pace"
        timeline.append(ReportMoment(start=item.start, end=item.end, kind=kind, metrics=item.metrics, speech=speech))
    if evidence.visual:
        for window in evidence.visual.windows:
            window.transcript_ids = [excerpt.segment_id for excerpt in overlapping_speech(window.start, window.end)]
        for event in evidence.visual.events:
            speech = overlapping_speech(event.start, event.end)
            event.transcript_ids = [excerpt.segment_id for excerpt in speech]
            timeline.append(ReportMoment(start=event.start, end=event.end, kind=event.kind,
                                         metrics=event.metrics, speech=speech))
    return DeliveryReport(timeline=sorted(timeline, key=lambda item: (item.start, item.end, item.kind)))
