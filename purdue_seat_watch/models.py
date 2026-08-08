from dataclasses import dataclass


@dataclass(frozen=True)
class Section:
    crn: str
    subject: str
    course_number: str
    section_code: str
    title: str


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
