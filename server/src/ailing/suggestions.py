"""Topic ideas, so a topic doesn't have to be thought up from nothing. The owner still picks
(docs/brief.md, design principle 10); these are only offered.

Each idea is an everyday situation with a handful of Thai words it's likely to need. For Thai,
ideas are ordered by how many of those words the deck already knows, so the ones most likely to
clear the coverage floor on the first try come first. Spanish counts the 10,000 most common words as
known, so everyday words fit every idea equally and Spanish keeps the order below. Ideas already
added as topics (or added and removed) aren't offered again; topics are shared by both languages.
"""

from dataclasses import dataclass

from ailing.coverage import Checker
from ailing.languages import Code


@dataclass(frozen=True)
class Idea:
    name: str
    words: tuple[str, ...]


IDEAS = (
    Idea("Ordering street food", ("กิน", "อร่อย", "เผ็ด", "จาน", "ใส่", "ไม่")),
    Idea("At a coffee shop", ("กาแฟ", "เย็น", "หวาน", "แก้ว", "นม", "น้ำแข็ง")),
    Idea("Taking a Grab ride", ("รถ", "ไป", "เลี้ยว", "ซ้าย", "ขวา", "จอด")),
    Idea("Shopping at the market", ("ตลาด", "เท่าไร", "ลด", "แพง", "ถูก", "กิโล")),
    Idea("Checking into a hotel", ("โรงแรม", "ห้อง", "จอง", "คืน", "กุญแจ", "ชั้น")),
    Idea("At the pharmacy", ("ยา", "ปวด", "หัว", "ท้อง", "เม็ด", "กิน")),
    Idea("Asking for directions", ("ที่ไหน", "ไกล", "ใกล้", "ตรงไป", "เลี้ยว", "ถนน")),
    Idea("At 7-Eleven", ("ถุง", "อุ่น", "จ่าย", "บัตร", "ทอน", "น้ำ")),
    Idea("Getting a massage", ("นวด", "เจ็บ", "แรง", "เบา", "ไหล่", "ขา")),
    Idea("Talking about the weather", ("อากาศ", "ร้อน", "ฝน", "ตก", "หนาว", "วันนี้")),
    Idea("Meeting someone new", ("ชื่อ", "มาจาก", "ทำงาน", "อายุ", "ยินดี", "รู้จัก")),
    Idea("Ordering food delivery", ("สั่ง", "ส่ง", "บ้าน", "นาที", "ที่อยู่", "โทร")),
    Idea("Seeing a doctor", ("หมอ", "ป่วย", "ไข้", "ไอ", "โรงพยาบาล", "เจ็บ")),
    Idea("Getting a haircut", ("ตัด", "ผม", "สั้น", "ยาว", "ข้าง", "สระ")),
    Idea("Renting a scooter", ("เช่า", "รถ", "วัน", "น้ำมัน", "หมวก", "ขับ")),
    Idea("Buying a SIM card", ("ซิม", "โทรศัพท์", "เน็ต", "เดือน", "เติม", "เบอร์")),
    Idea("At the bank", ("ธนาคาร", "เงิน", "โอน", "บัญชี", "แลก", "บัตร")),
    Idea("Taking the BTS", ("รถไฟฟ้า", "สถานี", "ตั๋ว", "เปลี่ยน", "สาย", "ลง")),
    Idea("Planning a beach trip", ("เที่ยว", "ทะเล", "พัก", "ไป", "กี่วัน", "สวย")),
    Idea("Dropping off laundry", ("ซัก", "ผ้า", "เสื้อ", "รีด", "แห้ง", "พรุ่งนี้")),
    Idea("Talking about family", ("พ่อ", "แม่", "พี่", "น้อง", "ลูก", "ครอบครัว")),
    Idea("Making weekend plans with a friend", ("ว่าง", "หนัง", "นัด", "กี่โมง", "เจอ", "ด้วยกัน")),
    Idea("Visiting a temple", ("วัด", "พระ", "รองเท้า", "ถอด", "ไหว้", "สวย")),
    Idea("Cooking at home", ("ทำ", "กับข้าว", "ผัด", "ไข่", "หมู", "ผัก")),
    Idea("Buying fruit", ("ผลไม้", "มะม่วง", "หวาน", "สุก", "ลูก", "กิโล")),
    Idea("At the gym", ("วิ่ง", "เหนื่อย", "หนัก", "ชั่วโมง", "ทุกวัน", "ออกกำลังกาย")),
    Idea("Talking about work", ("งาน", "บริษัท", "ประชุม", "เลิก", "เหนื่อย", "หัวหน้า")),
    Idea("Buying clothes", ("เสื้อ", "ไซส์", "ลอง", "ใหญ่", "เล็ก", "สี")),
    Idea("Talking about hobbies", ("ชอบ", "เล่น", "ดนตรี", "อ่าน", "หนังสือ", "ว่าง")),
    Idea("Ordering at a restaurant", ("เมนู", "สั่ง", "น้ำ", "เช็คบิล", "อร่อย", "จาน")),
)


@dataclass(frozen=True)
class Suggestion:
    name: str
    fit: float  # the share of the idea's words the deck knows


def suggest(lexicon: Checker, taken: set[str], language: Code = "th") -> list[Suggestion]:
    """Ideas not already taken (names compared ignoring case), best fit first; ties keep the order
    above."""
    taken = {name.casefold() for name in taken}
    ideas = [idea for idea in IDEAS if idea.name.casefold() not in taken]
    if language != "th":
        return [Suggestion(idea.name, 1.0) for idea in ideas]
    scored = [Suggestion(idea.name, _fit(idea, lexicon)) for idea in ideas]
    return sorted(scored, key=lambda s: -s.fit)


def _fit(idea: Idea, lexicon: Checker) -> float:
    known = sum(1 for word in idea.words if lexicon.status(word) == "known")
    return round(known / len(idea.words), 2)
