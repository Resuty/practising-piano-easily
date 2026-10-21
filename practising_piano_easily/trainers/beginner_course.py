"""Progressive piano lessons, beginner arrangements and an exact-pitch score follower."""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ScoreStep:
    right: tuple[int, ...] = ()
    left: tuple[int, ...] = ()
    beats: float = 1

    def __post_init__(self):
        if self.beats not in (0.5, 1, 1.5, 2, 3, 4) or not self.notes or any(not 21 <= note <= 108 for note in self.notes):
            raise ValueError("A score step needs piano pitches and a supported note duration")
        if len(self.notes) != len(self.right) + len(self.left):
            raise ValueError("The same pitch cannot belong to both hands")

    @property
    def notes(self) -> frozenset[int]:
        return frozenset(self.right + self.left)


@dataclass(frozen=True)
class PianoLesson:
    id: str
    title: str
    instructions: str
    steps: tuple[ScoreStep, ...]

    def __post_init__(self):
        beat = 0
        for step in self.steps:
            if beat % 4 + step.beats > 4:
                raise ValueError("Notes crossing a bar need ties; split this exercise instead")
            beat += step.beats
        if not self.steps or beat % 4:
            raise ValueError("A lesson must contain complete 4/4 bars")


LESSONS = (
    PianoLesson("find_c", "01 找到中央 C：高音谱表的起点",
        "先找到两颗黑键左边的 C。中央 C 在本软件显示为 C4（MIDI 60）。\n"
        "上方是右手用的高音谱表，中央 C 画在五线谱下面的一条短加线上。高音谱表最下方一条线是 E4。\n"
        "先看黄色目标键，再看蓝色音符，按 C4、D4、E4、C4。每个空心、没有符干的音符是全音符，占 4 拍。\n"
        "跟弹模式先练音高，不限时间。弹对后松开琴键，才进入下一组；每组弹一次即可。",
        tuple(ScoreStep((note,), beats=4) for note in (60, 62, 64, 60))),
    PianoLesson("right_five", "02 右手五指：C D E F G",
        "右手拇指放 C4，食指 D4，中指 E4，无名指 F4，小指 G4；手保持自然放松。\n"
        "沿琴键一步步走，观察谱面上的音符也在相邻线与间之间移动。黑色实心音头加符干的是四分音符，占 1 拍。\n"
        "4/4 表示每小节有四拍，以四分音符为一拍。可以慢数 1、2、3、4，但软件不会因慢弹扣分。",
        tuple(ScoreStep((note,)) for note in (60, 62, 64, 65, 67, 64, 62, 60))),
    PianoLesson("left_bass", "03 左手读谱：低音区的 C 与 A",
        "下方是低音谱表，最下方一条线是 G2，最上方一条线是 A3。先用琴键标签找到 C3 和 A2。\n"
        "只弹左手；另一只手对应的谱表会显示休止符。空心音头加符干的是二分音符，占 2 拍。\n"
        "依次弹 C3、G3、A2、E3，再重复一次。必须弹在谱面写出的八度：C4 不代替这里的 C3。",
        tuple(ScoreStep(left=(note,), beats=2) for note in (48, 55, 45, 52, 48, 55, 45, 52))),
    PianoLesson("c_chord", "04 第一个和弦：C E G",
        "C 大三和弦由 C、E、G 组成。这一课把三个音放在右手的 C4、E4、G4，可先尝试 1、3、5 指。\n"
        "谱面上竖直对齐的三个音要一起弹。你可以先慢慢放好一个音，再补另外两个；缺音时软件会等待。\n"
        "多按的键会标红，松开多余音即可继续。目标全部正确后，请松开三个音，再弹下一组。",
        (ScoreStep((60, 64, 67), beats=4),) * 2),
    PianoLesson("am_chord", "05 小三和弦：A C E",
        "Am 小三和弦由 A、C、E 组成。这次右手弹 A3、C4、E4，最低的 A 比中央 C 低。\n"
        "高音谱表下方会出现更多短加线，音越低，加线越往下；先对照琴键和音名，不用一次背完所有位置。\n"
        "先试听 C 与 Am 的差别，再按这份乐谱慢练。音准和放松比速度更重要。",
        (ScoreStep((57, 60, 64), beats=4),) * 2),
    PianoLesson("two_hands", "06 双手配合：C 与 Am 的四小节",
        "这是一段原创四小节练习：C、Am、C、Am。右手弹和弦，左手弹对应的低音 C3 或 A2。\n"
        "两行谱表共用同一个时间位置：竖直对齐的左右手音符属于同一组，要一起按住。\n"
        "可以先放左手，再补右手；软件会一直等到这组音齐全。熟悉后自己慢数四拍，再松开换下一小节。",
        (ScoreStep((60, 64, 67), (48,), 4), ScoreStep((57, 60, 64), (45,), 4)) * 2),
    PianoLesson("white_key_walk", "07 原创小曲《白键小路》：读谱走完四小节",
        "这段原创右手小曲只用 C 大调白键。先跟随蓝色位置弹完第一小节，再逐小节连起来。\n"
        "音符在谱面上升高时，琴键通常向右；下降时向左。相同的音符也要先松开再重新按下。\n"
        "熟悉后可以关闭音名提示，按自己的节奏弹。提示始终可随时打开，没有独立测试或隔天复测要求。",
        tuple(ScoreStep((note,)) for note in (60, 62, 64, 67, 69, 67, 64, 62, 65, 64, 62, 60, 62, 64, 62, 60))),
)


def _melody(text: str, hand="right") -> tuple[ScoreStep, ...]:
    """Compact authored notation: C4:2 is a half note; bars are checked at import."""
    steps = []
    for bar in text.split("|"):
        measure = []
        for token in bar.split():
            match = re.fullmatch(r"([A-G])([2-6])(?::(0\.5|1|1\.5|2|3|4))?", token)
            if not match:
                raise ValueError(f"Invalid authored note: {token}")
            letter, octave, duration = match.groups()
            note = (int(octave) + 1) * 12 + {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[letter]
            measure.append(ScoreStep(**{hand: (note,)}, beats=float(duration or 1)))
        if sum(step.beats for step in measure) != 4:
            raise ValueError(f"Incomplete authored bar: {bar}")
        steps.extend(measure)
    return tuple(steps)


LESSONS += (
    PianoLesson("left_five", "08 左手五指：从 C3 向上读谱",
        "左手小指放 C3、无名指 D3、中指 E3、食指 F3、拇指 G3。指号和右手相反。\n"
        "先认低音谱表上的 C3 和 G3，再把中间的音逐个补齐；不要把左手弹成 C4。\n"
        "上行时小指到拇指，下行时反过来。保持手腕自然，不追求速度。",
        _melody("C3 D3 E3 F3 | G3 F3 E3 D3 | C3 E3 G3 E3 | C3:4", "left")),
    PianoLesson("read_thirds", "09 线到线、间到间：二度与三度",
        "C→D 是相邻二度，谱面从线走到间；C→E 是三度，会跨过一个位置。\n"
        "先弹相邻音，再弹 C E G；用眼睛比较音符的距离，而不只是读下面的字母。\n"
        "同一个音需要松开后再按；第二遍可关掉音名提示，随时也能重新打开。",
        _melody("C4 D4 E4 F4 | C4 E4 G4 E4 | D4 F4 A4 F4 | E4 G4 C5:2")),
    PianoLesson("long_short", "10 一拍、两拍、四拍：长短音",
        "四分音符数一拍，二分音符数两拍，全音符数四拍。先听完整谱例，再自己数拍。\n"
        "每小节仍是四拍，长音并不等于多弹几次。谱上的同音重复才需要再次按键。\n"
        "本模式只检测音高。请自己保持长音的拍数，软件不会因慢弹或时值不准扣分。",
        _melody("C4 D4 E4:2 | F4:2 G4:2 | E4 F4 G4 E4 | C4:4")),
    PianoLesson("eighth_dotted", "11 半拍与附点：认八分音符",
        "带一条符尾的八分音符占半拍：一拍可以数成“1 和”。附点四分音符占一拍半。\n"
        "第一小节八个音，共四拍；第二小节的长短组合数成“1 和 2”和“和”。\n"
        "先试听，再慢慢找音。跟弹不评节奏，节奏请通过听和数拍练习。",
        _melody("C4:0.5 D4:0.5 E4:0.5 F4:0.5 G4:0.5 F4:0.5 E4:0.5 D4:0.5 | C4:1.5 D4:0.5 E4:2 | G4:1.5 E4:0.5 D4:1.5 E4:0.5 | C4:4")),
    PianoLesson("f_chord", "12 F 大三和弦：F A C",
        "F 大三和弦由 F、A、C 组成。这一课右手弹 F3 A3 C4，可试 1、3、5 指。\n"
        "前两组只弹右手；后两组加入左手 F2。左手低音和右手最低音不是同一八度。\n"
        "手够不到时先分手慢练，不要硬撑手掌。缺音时会等待，错音可直接改。",
        (ScoreStep((53, 57, 60), beats=4),) * 2 + (ScoreStep((53, 57, 60), (41,), 4),) * 2),
    PianoLesson("g_chord", "13 G 大三和弦：G B D",
        "G 和弦由 G、B、D 组成，右手弹 G3 B3 D4。B 在 C4 左边，是一个白键。\n"
        "先记住三个音之间“隔一个白键”的形状，再看谱面上的三个三度叠置。\n"
        "后两小节加入左手 G2。三和弦名称取决于音程，不是所有隔白键的形状都叫大和弦。",
        (ScoreStep((55, 59, 62), beats=4),) * 2 + (ScoreStep((55, 59, 62), (43,), 4),) * 2),
    PianoLesson("dm_chord", "14 Dm 小三和弦：D F A",
        "Dm 由 D、F、A 组成，右手 D4 F4 A4。D 到 F 是小三度，F 到 A 是大三度。\n"
        "对比已学的 C 和 Am，边试听边感受大小和弦色彩，不用把情绪词当成固定答案。\n"
        "先读单音，再把它们叠起来；后两组加上左手 D3。",
        (ScoreStep((62, 65, 69), beats=4),) * 2 + (ScoreStep((62, 65, 69), (50,), 4),) * 2),
    PianoLesson("em_chord", "15 Em 小三和弦：E G B",
        "Em 由 E、G、B 组成；这里右手弹 E4 G4 B4。先找到 B4，它在 C5 左边。\n"
        "E→G 是小三度，G→B 是大三度。只用白键也能弹出小三和弦。\n"
        "后两组加入左手 E3，注意上下谱表的音高对应。",
        (ScoreStep((64, 67, 71), beats=4),) * 2 + (ScoreStep((64, 67, 71), (52,), 4),) * 2),
    PianoLesson("primary_cadence", "16 C F G C：第一次和弦进行",
        "C 大调的 C、F、G 分别是 I、IV、V 级和弦；回到 C 时可听到结束感。\n"
        "本课四小节一轮，重复两轮。先看下一小节的根音，再移动右手。\n"
        "换和弦前松开本组。慢慢找齐也可以，不要求一次同时落下所有手指。",
        tuple(ScoreStep(right, (left,), 4) for right, left in
              (((60, 64, 67), 48), ((53, 57, 60), 41), ((55, 59, 62), 43), ((60, 64, 67), 48))) * 2),
    PianoLesson("c_first_inversion", "17 C 第一转位：E G C",
        "把 C E G 的最低 C 移高一个八度，得到 E G C。组成音没变，仍是 C 和弦。\n"
        "本课在 C4 E4 G4 与 E4 G4 C5 之间切换，听最低音变化。\n"
        "乐谱跟弹要求谱面实际八度；自由和弦练习若想接受两种排列，请选择任意转位。",
        (ScoreStep((60, 64, 67), beats=4), ScoreStep((64, 67, 72), beats=4)) * 2),
    PianoLesson("c_second_inversion", "18 C 第二转位：G C E",
        "第二转位把 G 放在最下方。这里使用 G3 C4 E4，手不必移到很高的位置。\n"
        "比较原位 C4 E4 G4、第一转位 E4 G4 C5、第二转位 G3 C4 E4。\n"
        "C、E、G 始终是和弦的组成音；“根音”和“当前最低音”要分开理解。",
        (ScoreStep((60, 64, 67), beats=4), ScoreStep((64, 67, 72), beats=4),
         ScoreStep((55, 60, 64), beats=4), ScoreStep((60, 64, 67), beats=4))),
    PianoLesson("common_tones", "19 C 与 Am：少移动的和弦连接",
        "C 是 C E G，Am 是 A C E，两者共有 C 和 E。用 C4 E4 A4 作为 Am 的转位。\n"
        "这样右手从 C4 E4 G4 到 C4 E4 A4 只改变一个音，手位更接近。\n"
        "本入门跟谱仍需每组松开再按；这里练的是找位置，不把它当成连奏或保留音检测。",
        (ScoreStep((60, 64, 67), (48,), 4), ScoreStep((60, 64, 69), (45,), 4)) * 2),
    PianoLesson("broken_c", "20 分解和弦：把 C E G 依次弹开",
        "同时弹叫柱式和弦，依次弹叫分解和弦。把右手放在 C4 E4 G4 三个位置。\n"
        "每个音一拍，依次 C E G E，重复后上到 C5，再回到中央 C。\n"
        "先保持手放松，最后的 C5 需要移动手位，不要强行把手张得很大。",
        _melody("C4 E4 G4 E4 | C4 E4 G4 E4 | E4 G4 C5 G4 | E4 G4 C4:2")),
    PianoLesson("broken_am", "21 分解和弦：Am 与 C 的对话",
        "先把 A3 C4 E4 依次弹开，再换成 C4 E4 G4。注意两个和弦有共同音。\n"
        "两个小节为一句：前半句向上，后半句向下。试听后尝试让句尾放松。\n"
        "手指建议只作参考；软件检查按键与八度，不判断用了哪根手指。",
        _melody("A3 C4 E4 C4 | A3 E4 C4:2 | C4 E4 G4 E4 | C4 G4 E4:2")),
    PianoLesson("left_broken", "22 左手伴奏：根音与五音交替",
        "左手 C3→G3、A2→E3、F2→C3、G2→D3，分别是四个和弦的根音与五音。\n"
        "每个音占两拍，先用左手单练。音域变化时移动前臂，不要只扭手腕。\n"
        "这种低音能帮助建立和声方向；学会后再去练习曲区找双手版本。",
        _melody("C3:2 G3:2 | A2:2 E3:2 | F2:2 C3:2 | G2:2 D3:2 | C3:4", "left")),
    PianoLesson("dominant_seventh", "23 G7 到 C：听到回家的方向",
        "G7 是 G B D F，比 G 和弦多了 F。这里右手弹 B3 D4 F4，左手补根音 G2。\n"
        "G7 转 C 时，B3 向上到 C4、F4 向下到 E4，留意半音与全音的靠近感。\n"
        "先听，再按谱慢练。这里省略右手 G，但双手合起来仍具备 G7 四个组成音。",
        (ScoreStep((59, 62, 65), (43,), 4), ScoreStep((60, 64, 67), (48,), 4)) * 2),
    PianoLesson("soft_sevenths", "24 Cmaj7 与 Am7：入门七和弦",
        "Cmaj7 是 C E G B；Am7 是 A C E G。七和弦是三和弦上再叠一个三度。\n"
        "右手分别弹 E4 G4 B4、C4 E4 G4，左手补 C3、A2，避免单手跨度过大。\n"
        "听完两轮后可进入练习曲区，自选旋律、分解和弦或双手曲目。课程不强制限时或复测。",
        (ScoreStep((64, 67, 71), (48,), 4), ScoreStep((60, 64, 67), (45,), 4)) * 2),
)


PIECES = (
    PianoLesson("song_twinkle", "S01 小星星 · 单手旋律",
        "传统旋律《Ah! vous dirai-je, maman》的 C 大调入门改编，不含歌词。全曲十二小节。\n"
        "先学会前四小节，再听中间四小节的重复；最后四小节回到开头。G 到 A 需要留意手位。\n"
        "四分音符一拍，二分音符两拍。每四小节自动换谱行，可用谱行按钮提前查看后面的内容。",
        _melody("C4 C4 G4 G4 | A4 A4 G4:2 | F4 F4 E4 E4 | D4 D4 C4:2 | "
                "G4 G4 F4 F4 | E4 E4 D4:2 | G4 G4 F4 F4 | E4 E4 D4:2 | "
                "C4 C4 G4 G4 | A4 A4 G4:2 | F4 F4 E4 E4 | D4 D4 C4:2")),
    PianoLesson("song_mary", "S02 玛丽有只小羊羔 · 五指旋律",
        "传统儿歌旋律的 C 大调入门改编，不含歌词。只使用 C4 到 G4，适合刚开始读谱。\n"
        "重复的 E 或 D 都要松开再弹；注意二分音符不是连续按两次。\n"
        "第一句和第二句结尾不同。跟弹不评节奏，可先把每个音弹对。",
        _melody("E4 D4 C4 D4 | E4 E4 E4:2 | D4 D4 D4:2 | E4 G4 G4:2 | "
                "E4 D4 C4 D4 | E4 E4 E4 E4 | D4 D4 E4 D4 | C4:4")),
    PianoLesson("song_frere", "S03 两只老虎 / Frère Jacques · 八分音符",
        "法国传统轮唱旋律的单手 C 大调改编，不含歌词。这份谱只弹一个声部，不做轮唱。\n"
        "第 5、6 小节的 G A G F 是四个八分音符，合计两拍；后面 E、C 各一拍。\n"
        "尾句 C4 G3 C4 需要把右手向左移动。先看八度再按键，不用赶速度。",
        _melody("C4 D4 E4 C4 | C4 D4 E4 C4 | E4 F4 G4:2 | E4 F4 G4:2 | "
                "G4:0.5 A4:0.5 G4:0.5 F4:0.5 E4 C4 | G4:0.5 A4:0.5 G4:0.5 F4:0.5 E4 C4 | "
                "C4 G3 C4:2 | C4 G3 C4:2")),
    PianoLesson("song_ode", "S04 欢乐颂 · 主题旋律（非完整交响曲）",
        "贝多芬《第九交响曲》欢乐颂主题的 C 大调单手入门改编。这里是十六小节主题，不是原作全曲。\n"
        "相同音较多，要重新按键。第 4 小节的 E 为附点四分音符，一拍半，后面的 D 为半拍。\n"
        "第 9 小节开始是对比乐句；先分四小节读，再连起来听完整主题。",
        _melody("E4 E4 F4 G4 | G4 F4 E4 D4 | C4 C4 D4 E4 | E4:1.5 D4:0.5 D4:2 | "
                "E4 E4 F4 G4 | G4 F4 E4 D4 | C4 C4 D4 E4 | D4:1.5 C4:0.5 C4:2 | "
                "D4 D4 E4 C4 | D4 E4:0.5 F4:0.5 E4 C4 | D4 E4:0.5 F4:0.5 E4 D4 | C4 D4 G3:2 | "
                "E4 E4 F4 G4 | G4 F4 E4 D4 | C4 C4 D4 E4 | D4:1.5 C4:0.5 C4:2")),
    PianoLesson("song_morning", "S05 原创《晨光》· 五指小曲",
        "原创八小节右手小曲，练习相邻音与三度跳进。全曲只用 C4 D4 E4 F4 G4。\n"
        "每四小节是一句，第二句和第一句相似但结尾更安定。先试听，再跟蓝色位置慢练。\n"
        "保持手型自然；不以快慢判断完成，只要按对并松开就能继续。",
        _melody("C4 E4 G4 E4 | F4 E4 D4:2 | E4 F4 G4 E4 | D4 E4 C4:2 | "
                "C4 D4 E4 G4 | F4 E4 D4:2 | E4 G4 F4 D4 | C4:4")),
    PianoLesson("song_steps", "S06 原创《台阶》· 上下行与高音 C",
        "原创八小节右手练习曲，逐步走到 C5，再沿白键回来。\n"
        "这不是固定五指位置；手位需移动，先慢慢找音，不要硬伸手指。\n"
        "观察谱面从线到间的连续上行，与 G4 到 C5 的跳进有什么不同。",
        _melody("C4 D4 E4 F4 | G4 A4 B4 C5 | C5 B4 A4 G4 | F4 E4 D4:2 | "
                "E4 F4 G4 A4 | G4 E4 C5:2 | A4 G4 E4 D4 | C4:4")),
    PianoLesson("song_echo", "S07 原创《回声》· 左右手问答",
        "原创八小节：右手先问，左手在低一个八度的位置回答，不需要同时弹。\n"
        "出现休止符的那只手保持放松。先认清每句属于上方还是下方谱表。\n"
        "两只手轮流练相同音型，帮助把低音谱表与高音谱表联系起来。",
        _melody("C4 E4 G4:2 | F4 E4 C4:2") + _melody("C3 E3 G3:2 | F3 E3 C3:2", "left") +
        _melody("D4 F4 A4:2 | G4 E4 C4:2") + _melody("D3 F3 G3:2 | C3:4", "left")),
    PianoLesson("song_am_river", "S08 原创《小调河流》· A 小调分解旋律",
        "原创八小节，围绕 A C E 与 D F A 展开。全是白键，但中心音是 A。\n"
        "右手从 A3 开始，注意中央 C 下方的加线；上行到 A4 时要调整手位。\n"
        "结尾落在 A3，听它与 C 大调练习曲不同的归属感。",
        _melody("A3 C4 E4 C4 | A3 B3 C4 E4 | D4 F4 A4 F4 | E4 C4 B3:2 | "
                "A3 C4 E4 G4 | F4 E4 D4 C4 | B3 C4 E4 B3 | A3:4")),
    PianoLesson("song_bass_path", "S09 原创《低音散步》· 左手旋律",
        "原创八小节左手曲，练低音谱表 C3 到 C4。右手休息。\n"
        "C4 会出现在低音谱表上方的短加线上；它和第一课的中央 C 是同一颗键。\n"
        "后四小节走向 G2，先辨认八度，再慢慢按。",
        _melody("C3 D3 E3 G3 | A3 G3 E3:2 | F3 A3 C4 A3 | G3 E3 C3:2 | "
                "A2 C3 E3 C3 | F2 A2 C3 A2 | G2 B2 D3 G3 | C3:4", "left")),
    PianoLesson("song_four_homes", "S10 原创《四扇窗》· 双手柱式和弦",
        "原创八小节双手和声小曲，依次 C、Am、F、G，再 C、Dm、G7、C。\n"
        "右手选择接近的转位，左手弹根音。先分别读两行，再补齐每一组。\n"
        "这里以整小节为一组；熟悉后自行数四拍再松开，软件不评时值。",
        tuple(ScoreStep(right, (left,), 4) for right, left in (
            ((60, 64, 67), 48), ((60, 64, 69), 45), ((60, 65, 69), 41), ((59, 62, 67), 43),
            ((60, 64, 67), 48), ((62, 65, 69), 50), ((59, 62, 65), 43), ((60, 64, 67), 48)))),
    PianoLesson("song_lantern", "S11 原创《灯火》· 双手两拍和声",
        "原创八小节，每小节两组双手和声。左手是低音，右手是两音或三音的简化排列。\n"
        "先看左手 C3→G3 等五度移动，再读右手。不要求很快同时落键，可慢慢补齐。\n"
        "这是柱式双手练习，不是独立旋律配长低音；每组正确后请松开全部按键。",
        tuple(ScoreStep(right, (left,), 2) for right, left in (
            ((60, 64), 48), ((64, 67), 55), ((60, 64), 45), ((60, 64), 52),
            ((60, 65), 41), ((65, 69), 48), ((59, 62), 43), ((62, 67), 50),
            ((60, 64), 48), ((64, 67), 55), ((62, 65), 50), ((65, 69), 45),
            ((59, 65), 43), ((59, 62), 50), ((60, 64, 67), 48), ((60, 64, 67), 48)))),
    PianoLesson("song_evening", "S12 原创《晚风》· 七和弦色彩",
        "原创十二小节双手和弦小曲，练 Cmaj7、Am7、Dm7、G7 的近距离排列。\n"
        "每一组的四个组成音分在两只手，右手不必张开七度。先听颜色，再找键。\n"
        "这一首适合完成第 24 课后练；允许提示和纠正，没有速度门槛。",
        tuple(ScoreStep(right, (left,), 4) for right, left in (
            ((64, 67, 71), 48), ((60, 64, 67), 45), ((60, 65, 69), 50), ((59, 62, 65), 43),
            ((64, 67, 71), 48), ((60, 64, 67), 45), ((60, 65, 69), 50), ((59, 62, 65), 43),
            ((64, 67, 71), 48), ((60, 64, 67), 45), ((59, 62, 65), 43), ((60, 64, 67), 48)))),
)


def completed_lessons(database) -> set[str]:
    return {row[0] for row in database.connection.execute(
        "SELECT DISTINCT question FROM attempts WHERE trainer_type='beginner_course'"
    )}


def next_lesson_index(database) -> int:
    completed = completed_lessons(database)
    return next((index for index, lesson in enumerate(LESSONS) if lesson.id not in completed), len(LESSONS) - 1)


class ScoreFollower:
    """A chord's fingers may arrive separately; a complete release separates score steps."""

    def __init__(self, lesson: PianoLesson):
        self.lesson = lesson
        self.index = 0
        self.matched = False
        self.mistakes = 0
        self.previous_notes: frozenset[int] = frozenset()

    @property
    def finished(self) -> bool:
        return self.index == len(self.lesson.steps)

    @property
    def expected(self) -> frozenset[int]:
        return frozenset() if self.finished else self.lesson.steps[self.index].notes

    def update(self, notes: frozenset[int]) -> str:
        if self.finished:
            return "finished"
        previous = self.previous_notes
        self.previous_notes = frozenset(notes)
        if self.matched:
            if notes:
                return "release"
            self.index += 1
            self.matched = False
            return "finished" if self.finished else "advanced"
        extra = notes - self.expected
        self.mistakes += len(extra - previous)
        if notes == self.expected:
            self.matched = True
            return "matched"
        return "extra" if extra else "waiting"
