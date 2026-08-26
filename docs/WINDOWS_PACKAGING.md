# Windows packaging

The intended distributable is `DotaSupportDraft.exe`. The current PyInstaller spec is a **packaging contract**, not evidence that a release executable was created.

Before publishing, DOTA-002+ must pin a Windows build environment, install PyInstaller, build the spec, smoke-test the produced executable on a clean Windows machine, collect app assets, and establish code signing/release versioning where appropriate. Nuitka remains an alternative after a measured packaging evaluation.

