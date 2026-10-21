# Third-party notices

practising piano easily uses unmodified third-party libraries. Their licenses and copyrights remain with their respective authors. Installed distribution metadata and available license files are retained in the subdirectories beside this file. The LGPL v3 and GPL v3 texts are included verbatim from PySide's v6.8.3 source tree.

## Qt / PySide6 / Shiboken 6.8.3

This application uses the LGPL v3 option for the applicable Qt/PySide components. The libraries are dynamically loaded from `_internal`, not statically linked into application code. No restriction is imposed on replacing or modifying these libraries, or reverse engineering for debugging those modifications. Application source and build instructions are included in `Source`.

- [Qt for Python licensing](https://doc.qt.io/qtforpython-6/licenses.html)
- [PySide/Shiboken 6.8.3 source tree](https://github.com/pyside/pyside-setup/tree/v6.8.3)
- [Qt 6.8.3 source archives](https://download.qt.io/archive/qt/6.8/6.8.3/submodules/)
- [Qt Base 6.8.3 source](https://download.qt.io/archive/qt/6.8/6.8.3/submodules/qtbase-everywhere-src-6.8.3.tar.xz)
- [Qt PDF / WebEngine 6.8.3 source, including third-party code](https://download.qt.io/archive/qt/6.8/6.8.3/submodules/qtwebengine-everywhere-src-6.8.3.tar.xz)

Qt PDF includes PDFium and other third-party components. The Qt 6.8 attribution documents are preserved in `Qt-attributions` together with their original source URLs. The installed version is 6.8.3; Qt's online 6.8 documentation may describe a later patch release. Exact corresponding sources are linked above.

## Other components

Python is covered by the Python Software Foundation license and incorporated notices. NumPy, Mido, python-rtmidi/RtMidi, sounddevice/PortAudio, CFFI and their dependencies retain their own license texts. NumPy's wheel license includes the numerical libraries it bundles. PyInstaller's license has a bootloader exception; its metadata and license files are also included as build-tool provenance, not as an application runtime dependency.

External scores, downloaded audio, user imports, credentials and personal practice data are not bundled. The included traditional/classical-theme beginner arrangements and original exercises are identified in the application and project documentation. A third-party score does not become openly licensed by being imported.
