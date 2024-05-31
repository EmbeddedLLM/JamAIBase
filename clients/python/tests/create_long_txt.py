from pathlib import Path

from jamaibase import JamAI, protocol
from jamaibase.utils.io import dumps_file

tests_dir = Path(__file__).parent.resolve()


content = (
    "The 77th British Academy Film Awards, more commonly known as the BAFTAs, were held on 18 February 2024, honouring the best national and foreign films of 2023."
    "第77届英国电影学院奖（The 77th British Academy Film Awards）是英国电影和电视艺术学院以兹奖励2023年电影的奖项。"
    "77-а церемонія вручення нагород Британською академією телебачення та кіномистецтва, більш відома як БАФТА, відбудеться 18 лютого 2024."
    'טקס פרסי האקדמיה הבריטית לקולנוע ה-77, ידוע יותר בשם פרס באפט"א לקולנוע, הוא טקס שיתקיים ב-18 בפברואר 2024'
)

dumps_file(content * 100, str(tests_dir / "txt" / "bafta.txt"))
