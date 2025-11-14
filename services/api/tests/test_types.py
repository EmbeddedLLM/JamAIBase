from datetime import datetime, timezone

import pytest
from pydantic import BaseModel, Field, ValidationError

from owl.types import DatetimeUTC, LanguageCodeList, SanitisedNonEmptyStr
from owl.utils.dates import now_iso
from owl.utils.test import TEXTS


class IdTest(BaseModel):
    id: SanitisedNonEmptyStr = Field()


GOOD_IDS = [
    pytest.param("Hello", id="Simple word"),
    pytest.param("Hello World", id="Words with space"),
    pytest.param(" Hello", id="Leading space"),
    pytest.param("Hello ", id="Trailing space"),
    pytest.param(" Hello ", id="Leading and trailing space"),
    pytest.param("\nHello", id="Leading newline"),
    pytest.param("Hello\n", id="Trailing newline"),
    pytest.param("\nHello\n", id="Leading and trailing newline"),
    # \u00A0 is NBSP
    pytest.param("\u00a0NBSP at start", id="Leading Non-Breaking Space"),
    pytest.param("NBSP at end\u00a0", id="Trailing Non-Breaking Space"),
    pytest.param("H", id="Single character"),
    pytest.param("1", id="Single number"),
    pytest.param("?", id="Single symbol"),
    pytest.param("123", id="Numbers"),
    pytest.param("!@#$", id="Symbols"),
    pytest.param("😊", id="Single emoji"),
    pytest.param("你好", id="CJK characters"),
    pytest.param("مرحبا", id="Arabic characters"),
    pytest.param("Привет", id="Cyrillic/Russian characters"),
    pytest.param("Hello 😊 World", id="Text with emoji"),
    pytest.param("Text with  multiple   spaces", id="Internal multiple spaces"),
    pytest.param("Test-123_ABC", id="Text with symbols"),
    pytest.param("a-b_c=d+e*f/g\\h|i[j]k{l}m;n:o'p\"q,r.s<t>u?v", id="Complex symbols"),
] + [pytest.param(text, id=lang) for lang, text in TEXTS.items()]

BAD_IDS = [
    pytest.param("", id="Empty string"),
    pytest.param(" ", id="Single space"),
    pytest.param("  ", id="Multiple spaces"),
    pytest.param("\t", id="Tab only"),
    pytest.param("\n", id="Newline only"),
    pytest.param("Text\tnewlines", id="Internal tab"),
    pytest.param("Text\nwith\nnewlines", id="Internal newlines"),
    pytest.param(" Hello\nWorld ", id="Leading space, trailing space, internal newline"),
    # \u00A0 is NBSP
    pytest.param("Okay\u00a0NBSP\u00a0Okay", id="Internal Non-Breaking Space"),
    pytest.param("█ ▄ ▀", id="Block elements"),
    pytest.param("─ │ ┌ ┐", id="Box drawing"),
    pytest.param("⠲⠳⠴⠵", id="Braille"),
]


@pytest.mark.parametrize("value", GOOD_IDS)
def test_id_string_good(value: str):
    item = IdTest(id=value)
    assert item.id == value.strip()


@pytest.mark.parametrize("value", BAD_IDS)
def test_id_string_bad(value: str):
    with pytest.raises(ValidationError):
        IdTest(id=value)


def test_string_normalisation():
    # ---
    #
    # Zalgo text
    assert IdTest(id="H̵̛͕̞̦̰̜͍̰̥̟͆̏͂̌͑ͅä̷͔̟͓̬̯̟͍̭͉͈̮͙̣̯̬͚̞̭̍̀̾͠m̴̡̧̛̝̯̹̗̹̤̲̺̟̥̈̏͊̔̑̍͆̌̀̚͝͝b̴̢̢̫̝̠̗̼̬̻̮̺̭͔̘͑̆̎̚ư̵̧̡̥̙̭̿̈̀̒̐̊͒͑r̷̡̡̲̼̖͎̫̮̜͇̬͌͘g̷̹͍͎̬͕͓͕̐̃̈́̓̆̚͝ẻ̵̡̼̬̥̹͇̭͔̯̉͛̈́̕r̸̮̖̻̮̣̗͚͖̝̂͌̾̓̀̿̔̀͋̈́͌̈́̋͜").id == "Hämbưrgẻr"
    #
    #
    # ---
    # Arabic
    assert IdTest(id="مَرْحَبًا بِكُمْ").id == "مرحبا بكم"
    # ---
    # Thai
    assert IdTest(id="สวัสดีครับ คามุย อิอิ").id == "สวสดครบ คามย ออ"


def test_datetime_utc():
    class DatetimeTest(BaseModel):
        dt: DatetimeUTC = Field()

    now = now_iso("Asia/Kuala_Lumpur")
    d = DatetimeTest(dt=now)
    assert isinstance(d.dt, datetime)
    assert d.dt.tzinfo is timezone.utc
    assert datetime.fromisoformat(now) == d.dt


def test_language_list():
    class TestModel(BaseModel):
        lang: LanguageCodeList

    model = TestModel(lang=["en", "FR", "zh-cn", "ZH-sg"])
    assert set(model.lang) == {"en", "fr", "zh-CN", "zh-SG"}

    model = TestModel(lang=["en", "mul"])
    assert set(model.lang) == {"en", "fr", "es", "zh", "ko", "ja", "it"}

    with pytest.raises(ValidationError):
        TestModel(lang=["xx"])
