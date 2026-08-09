from dataclasses import dataclass


@dataclass(frozen=True)
class Meeting:
    type: str  # e.g. "Class", "Lecture", "Lab"
    time: str  # e.g. "11:30 am - 1:20 pm", or "TBA"
    days: str  # e.g. "MWF", "T", or "TBA"
    schedule_type: str  # e.g. "Lecture", "Laboratory"


@dataclass(frozen=True)
class Section:
    crn: str
    subject: str
    course_number: str
    section_code: str
    title: str
    meetings: tuple[Meeting, ...] = ()


@dataclass(frozen=True)
class SeatInfo:
    capacity: int
    actual: int
    remaining: int
    waitlist_capacity: int
    waitlist_actual: int
    waitlist_remaining: int

    @property
    def is_open(self) -> bool:
        return self.remaining > 0
