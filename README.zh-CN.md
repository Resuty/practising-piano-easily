# practising piano easily

使用 MIDI 键盘、交互五线谱和下落提示练习认键、和弦与读谱的 Windows 桌面软件。

[日本語](README.md)

## 功能

- 24 节新手课程、12 首练习曲、10 章和弦教程与自测
- 先显示目标，允许逐音补齐和原地纠正的和弦练习
- 五线谱与下落提示同步，默认四小节练习，可选演示、反复与左右手分练
- 本地 MIDI 导入，PDF 可选；按来源许可搜索和导入在线乐谱
- 听力训练、和声分析、声部连接比较和和弦进行 MIDI 导出
- 本地学习记录、设置保存及中英日界面切换

没有 MIDI 键盘时，也能点击屏幕琴键试用。正常跟弹音色使用键盘自身音源，内置试听与演示使用简易合成音。

## 从源码启动

需要 Windows 10/11 x64 和 Python 3.11+，在项目根目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m practising_piano_easily.app
```

安装依赖后也可双击 `start.bat`。右上角可切换简体中文、日本語和 English。源码版新用户默认中文，Windows 发布版新用户默认日文，已有语言选择会保留。

## Windows 运行包

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -X utf8 packaging/build_portfolio.py
```

输出为 `exports/portfolio/practising-piano-easily-windows.zip`。完整解压后运行 `practising-piano-easily.exe`，无需另外安装 Python。必须保留同目录的 `_internal` 文件夹。程序未签名，请遵守运行环境的安全策略。

## 测试与设计

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

源码按理论核心、练习模型、MIDI、音频、分析、学习记录和 UI 分层。详见 [设计](docs/ARCHITECTURE.md)、[理论模型](docs/MUSIC_THEORY.md)、[练习判定](docs/TRAINING_MODEL.md)和[构建说明](packaging/BUILD.md)。

## 数据与使用边界

源码版数据保存在 `data/`，新 Windows 运行包数据保存在 `%LOCALAPPDATA%/practising-piano-easily/`；已有安装可能继续使用旧位置，以保留记录。源码导出和运行包不含个人数据库、导入曲谱、音频、账号配置或旧 Git 历史。

主要检测音高和八度，不评持键时长、节奏、运指或演奏表现。不做 PDF 光学识谱。MIDI 重绘谱和音域分手不是原谱的完整还原。和弦、调性分析仅提供候选。

在线资源须遵守原站许可和访问要求。第三方乐谱与音频不随项目分发；依赖库的许可保存在 [第三方说明](packaging/THIRD_PARTY.md)中。
