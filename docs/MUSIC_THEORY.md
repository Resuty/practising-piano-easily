# Music Theory Model

- `Note` 保留 letter 与 accidental；`F#` 与 `Gb` 拼写不同，pitch class 相同。
- MIDI pitch 是带八度的 0–127 整数；pitch class 是对 12 取模的声音等价类。
- Interval 同时保存 semitone distance 和 letter steps，以便 transpose 得到正确拼写。
- `Chord` 分开 root、triad quality、seventh、extension、alterations、added tones、suspension 与 slash bass。
- 和弦的 theoretical tones 与 practical required tones 分离。Extended chord 练习允许省略 5th 和中间 extension，但保留 root、3rd/suspension、7th、最高 extension 和 alteration。
- Parser 支持 `maj7/M7/Δ7`、`min/m`、`dim/°`、`aug/+`、`ø/m7b5` 并输出 canonical notation。Slash bass 只规定最低音，不改变 chord identity。
- 对和声分析，确定事实与 possible interpretation 必须分开。

## Scales and harmony

Major、natural minor、harmonic minor 和 ascending melodic minor 通过 scale pattern 与 letter degree 生成，不使用固定升降号映射。Diatonic triads/sevenths 由音阶三度叠置推导。Minor key 的 natural-minor diatonic dominant 与 raised-7th functional dominant 作为两个明确结果。

Harmony analysis 先标记 diatonic/chromatic 事实，再单独列出 `Possible interpretation`。当前支持 secondary dominant、major-key modal interchange（iv/bIII/bVI/bVII）、secondary leading-tone diminished、tritone substitution、backdoor dominant、common-tone diminished 与上行 chromatic passing diminished。同一和弦可同时显示多个 possible interpretation。
