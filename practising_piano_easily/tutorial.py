"""Offline chord course data; quiz IDs and answers never depend on UI language."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Example:
    symbol: str
    notes: tuple[int, ...]
    level: int = 1


@dataclass(frozen=True)
class Quiz:
    question: str
    options: tuple[str, ...]
    answer: int
    explanation: str


@dataclass(frozen=True)
class Lesson:
    id: str
    markdown: str
    examples: tuple[Example, ...]
    quizzes: tuple[Quiz, ...]

    @property
    def title(self):
        return self.markdown.splitlines()[0].removeprefix("# ")


_ACTIVITIES = (
    ("start", (Example("C", (60, 64, 67)), Example("Cm", (60, 63, 67))), (
        Quiz("第一次学习 C 和弦，更有用的做法是？", ("只记屏幕上的手形", "先说 C E G，再找键、弹奏并听", "立刻练所有高级和弦"), 1, "把符号、音名、位置和声音连起来。教程里的‘已读’不等于技能已掌握。"),
    )),
    ("keyboard", (Example("C", (60, 64, 67)), Example("F", (53, 57, 60))), (
        Quiz("从 E 向上走一个半音，得到哪个音？", ("F", "F#", "G"), 0, "E 和 F 之间没有黑键，两者相隔一个半音。B 到 C 也是如此。"),
        Quiz("在 F 大调里，第四个音应写成什么？", ("A#", "Bb", "B"), 1, "F G A Bb C D E 每个字母用一次。A# 与 Bb 同键，但调内拼写应为 Bb。"),
    )),
    ("intervals", (Example("C", (60, 64, 67)), Example("F#", (54, 58, 61))), (
        Quiz("从 F# 向上构成大三度，正确音名是？", ("A", "A#", "Bb"), 1, "字母先数 F G A，三度必须是 A 类音；再确定四个半音，所以是 A#。"),
        Quiz("C–D# 与 C–Eb 弹在相同的键上，所以音程名称也相同吗？", ("相同，都叫小三度", "不同，分别是增二度和小三度"), 1, "音程名称同时看字母跨度与半音数，不能只数键。"),
    )),
    ("triads", (Example("C", (60, 64, 67)), Example("Cm", (60, 63, 67)), Example("Am", (57, 60, 64))), (
        Quiz("把 C 大三和弦改成 C 小三和弦，只需改哪个音？", ("C 改成 B", "E 改成 Eb", "G 改成 Gb"), 1, "C E G → C Eb G，三音降低半音，根音和五音保留。"),
        Quiz("D 大三和弦的组成音是哪组？", ("D F A", "D F# A", "D G A"), 1, "从 D 量大三度得到 F#，纯五度得到 A。不能在所有根音上都只隔一个白键。"),
    )),
    ("inversions", (Example("C/E", (52, 55, 60)), Example("C/G", (55, 60, 64)), Example("Cmaj7/B", (47, 48, 52, 55), 3)), (
        Quiz("左手 C3，右手 E4 G4 C5，整个和弦是什么位置？", ("原位", "第一转位", "第二转位"), 0, "要看左右手合起来的最低音。最低是 C，所以是原位。"),
        Quiz("C/D 一定是 C 和弦的某个转位吗？", ("是，所有斜线和弦都是转位", "不是，D 不属于 C 三和弦"), 1, "斜线规定低音；只有低音属于和弦组成音时，才按三音、五音、七音判断相应转位。"),
    )),
    ("sevenths", (Example("Cmaj7", (60, 64, 67, 71), 3), Example("C7", (60, 64, 67, 70), 3), Example("Cm7", (60, 63, 67, 70), 3)), (
        Quiz("Cmaj7 与 C7 的区别在哪里？", ("三音 E / Eb", "七音 B / Bb", "根音 C / B"), 1, "两者都是 C E G 起底；maj7 加 B，7 加 Bb。"),
        Quiz("把 Cm7 的五音降低半音，得到什么？", ("Cm7b5", "Cdim7", "Cmaj7"), 0, "C Eb G Bb → C Eb Gb Bb。减七 Cdim7 还要把 Bb 降为 Bbb。"),
    )),
    ("diatonic", (Example("F", (53, 57, 60)), Example("Am7", (57, 60, 64, 67), 3), Example("C7", (60, 64, 67, 70), 3)), (
        Quiz("F 大调的 iii7 是什么？", ("Am7", "A7", "Abmaj7"), 0, "F G A Bb C D E，从第三级 A 开始隔一个音取一次：A C E G。"),
        Quiz("C 大调里，G7 最常见的属功能目标是什么？", ("回到 C 主和弦", "必须去 Am", "不能回 C"), 0, "G7 中的 B 常向 C，F 常向 E，形成常见 V7–I 解决；具体音乐可以偏离这个走向。"),
    )),
    ("minor", (Example("Am", (57, 60, 64)), Example("E7", (52, 56, 59, 62), 3), Example("Fm", (53, 56, 60))), (
        Quiz("A 小调里 Em 变为 E7，关键的升高音是？", ("G → G#", "B → C", "E → F"), 0, "G# 距 A 一个半音，是导音；E7 还加入七音 D。自然小调中的 G 本身并没有错。"),
        Quiz("C–A7–Dm–G7 中，A7 的常见解释是？", ("C 大调的调内 vi", "Dm 的副属和弦 V7/ii", "一定已经转到 A 大调"), 1, "A7 的 C# 是调外音，它常引向 Dm。一个调外和弦并不能单独证明全曲已经转调。"),
    )),
    ("colors", (Example("Csus4", (60, 65, 67), 5), Example("Cadd9", (60, 64, 67, 74), 5), Example("C9", (60, 64, 67, 70, 74), 6)), (
        Quiz("Cadd9 与 C9 最关键的区别是？", ("C9 还包含小七音 Bb", "Cadd9 没有三音 E", "两者完全相同"), 0, "add9 只在三和弦上加九音；C9 含属七结构再加九音。"),
        Quiz("C13 的实际排列必须同时弹出七个不同音吗？", ("必须，少一个就不是", "不必，实际排列可省略部分音"), 1, "先分清理论音与实际排列。常优先保留 E、Bb、A 等表明性质和色彩的音，再结合低音和乐队分工处理其余音。"),
    )),
    ("practice", (Example("C", (48, 52, 55)), Example("G/B", (47, 50, 55)), Example("Am", (45, 48, 52)), Example("F/A", (45, 48, 53))), (
        Quiz("比较两组 voicing 时，总移动量更小就一定更好听吗？", ("是，这是唯一标准", "不是，还与旋律、节奏和表达目的有关"), 1, "移动量是客观指标，可帮助比较弹奏方案，但不能替你评价音乐审美。"),
        Quiz("一次练习中同一题连续答错，更有效的下一步是？", ("盲目提速", "说出根音、三音、五音并定位差异，再慢弹", "跳到更高级别"), 1, "先确认是认键、构成还是低音判断出了问题。准确建立后再逐渐提速。"),
    )),
)


def load_lessons(locale="zh_CN") -> tuple[Lesson, ...]:
    filename = "chord_tutorial_ja.md" if locale == "ja" else "chord_tutorial_zh.md"
    text = Path(__file__).with_name("content").joinpath(filename).read_text(encoding="utf-8")
    sections = text.strip().removeprefix("# ").split("\n# ")
    if len(sections) != len(_ACTIVITIES):
        raise ValueError("Tutorial chapter/activity count mismatch")
    return tuple(Lesson(id, "# " + body, examples, quizzes)
                 for body, (id, examples, quizzes) in zip(sections, _ACTIVITIES))
