# 2.3.0 更新

当前主入口已经迁移为 PySide6 QtWidgets + 自定义深色 B 风格。采用免费 PySide6-Essentials，不引入 QFluentWidgets 或付费 UI。详见 README.md / MIGRATION.md / THIRD_PARTY_NOTICES.md。下文为早期方案讨论，不代表当前仍在使用 Tk 界面。

# UI框架与分享打包建议

## UI选择

建议以PySide6（Qt for Python）为基础，用Qt Widgets做桌面界面，用Qt Designer或Qt Creator的官方项目模板搭骨架。它适合当前的表格、筛选、历史、弹窗和桌面窗口场景。

如果希望直接使用现成的Fluent外观，QFluentWidgets提供PySide6分支、导航、主题及常用组件，可以减少外观搭建工作。但其作者要求非商业项目按GPLv3分发，商业用途使用商业授权；“免费分享”不自动等于无需遵守GPL。因此在明确软件分享/开源方式前，不把它作为当前包的依赖。

官方Qt Widgets + 自定义样式仍是可用方案；PySide6本身的LGPLv3/GPLv3/商业许可也需按所用模块和发布方式遵守。

迁移时保留core.py、storage.py、analytics.py，将抓包工作线程从base_ui.py拆成独立模块，再替换界面层。现有SQLite目录、用户映射、回收站、原始快照和统计标记继续使用。2.2.2尚未迁移到Qt，先交付当前功能修复。

来源：
- https://doc.qt.io/qtforpython-6/
- https://doc.qt.io/qtforpython-6/tools/pyside-designer.html
- https://doc.qt.io/qtcreator/creator-tutorial-python-application-qt-widgets.html
- https://github.com/zhiyiYo/PyQt-Fluent-Widgets/tree/PySide6
- https://qfluentwidgets.github.io/zh/pages/about/

## 推荐的第一阶段发布方式

在Windows上用PyInstaller生成目录版程序，压缩整个dist/EtheriaAssistant文件夹分享。接收者不需要安装Python，但实时抓包仍需要可用的dumpcap和Npcap。

先用目录版，便于查看缺失的文件、DLL和授权说明；目录版验证正常后再考虑安装器。正式分发包不得夹带开发者的history.sqlite3、runtime.log或用户抓包。本项目构建配置只选择源代码和列出的资源，不打包个人数据目录。

## 本次准备的构建入口

1. 在Windows上安装64位Python 3.10+（建议使用已验证环境；本程序开发测试为Python3.12），保留py启动器（Qt版不需要Tcl/Tk）。
2. 双击build_windows.cmd。该脚本会在本目录新建.build-venv，安装requirements-build.txt中的PyInstaller，然后运行EtheriaAssistant.spec。首次需要网络下载构建依赖。
3. 成功后运行dist/EtheriaAssistant/EtheriaAssistant.exe。
4. 分享整个dist/EtheriaAssistant文件夹，包括_internal，不单独复制exe。

这只是Windows构建入口和资源配置。本环境是Linux，没有生成或运行Windows EXE；构建结果需要在一台Windows电脑及干净测试环境中验证。PyInstaller应在目标操作系统和匹配位数的Python下构建，不能将这里的Linux打包结果当作Windows程序。

来源：
- https://pyinstaller.org/en/stable/operating-mode.html
- https://pyinstaller.org/en/stable/spec-files.html

## dumpcap如何集成

当前已通过独立子进程调用dumpcap，读取stdout中的pcapng，界面线程不处理网络等待。为了减少迁移风险，短期保留这一方式。

2.2.2新增的自动查找顺序包含：exe同级vendor/dumpcap/dumpcap.exe、程序资源目录vendor/dumpcap/dumpcap.exe、系统PATH和常见Wireshark安装目录。用户保存的有效路径仍优先。

构建配置支持可选的vendor/dumpcap目录：若该目录存在，会将其exe、DLL和其他随附资料一起放到包内同样的相对位置。未提供该目录时，只打包助手，继续使用用户已安装的Wireshark捕获组件。本交付不包含第三方二进制、Npcap安装器或驱动。

随包提供dumpcap时，需先准备同版本和同架构的可用运行组件及依赖DLL，并按Wireshark及其依赖的许可证提供授权文字、版权说明和适当的对应源码获取安排。不要只拷一个dumpcap.exe就假设依赖齐全。实际DLL集合随所选版本变化，应在干净Windows环境验证。

Wireshark官方说明其许可证为GPLv2或更新版本；对应组件的分发需遵守其条款。独立子进程方式不等于忽略组件自身的分发要求。

来源：
- https://www.wireshark.org/docs/wsdg_html_chunked/ChSrcBinary
- https://github.com/wireshark/wireshark/blob/master/doc/man_pages/dumpcap.adoc

## Npcap与dumpcap是两层

dumpcap是用户态捕获程序，Npcap包含Windows抓包驱动。把dumpcap打进目录包，不能替代安装Npcap。

Npcap官网明确说明免费版不得对外再分发；需要将Npcap集成进产品并静默安装时，应使用相应OEM再分发授权。对当前分享阶段，建议让接收者自行从Npcap官方获取安装器，或使用已有的合规安装；助手检测到后复用，不自动替换。

未来若改成直接调用Npcap/libpcap接口，可以减少dumpcap依赖，但仍有Npcap驱动、部署和授权要求，也需要重新验证捕获、停止、接口枚举等行为。当前优先完成统计与胜负验证，不重写捕获链。

来源：
- https://npcap.com/
- https://npcap.com/oem/redist
- https://npcap.com/guide/

## 当前发布流程（2.10.0）

在已更新到main且没有未提交修改的Windows x64工作目录中运行build_windows.cmd。脚本安装构建依赖，执行完整回归，构建目录版，并启动冻结后的EXE做独立临时数据库检查。全部成功后输出release/EtheriaAssistant-2.10.0-windows-x64.zip、SHA256SUMS.txt及release.json；不生成假冒Windows程序的Linux包。

默认仅包含运行所需映射、图片和发布说明；不再将mapping_evidence.json、VALIDATION.md、RESULT_VALIDATION.md或结算候选分析带入二进制资源。构建后的目录还会检查数据库、日志、抓包和驱动排除规则。

需要发布GitHub Release时，先安装GitHub CLI（https://cli.github.com/）并完成gh auth login，然后运行publish_release.cmd。脚本校验版本、源码提交和ZIP校验和，将准确构建提交作为v版本标签目标；已有版本拒绝覆盖。该操作在本机执行，不启动GitHub Actions，不改变仓库可见性。当前私有仓库的Release也只有有访问权限的人能下载；可另行分享ZIP，但不要在分享包中放凭据。

源码版更新器不能升级冻结EXE，目录版需关闭程序后完整替换程序目录；个人历史和映射在LocalAppData，不随替换删除。

### 可选随包dumpcap

默认发布包走官方安装入口，暂不自动下载或捆绑dumpcap。若之后准备好一组经确认可再分发的Windows x64 dumpcap运行库，可放到vendor/dumpcap并使用build_windows.cmd --with-capture。

必须提供capture_manifest.json，记录version、对应Wireshark源码source_url，以及files对象（相对文件名→SHA256）；其中必须列出dumpcap.exe、COPYING.txt、SOURCE.txt及实际所需DLL、依赖许可文字。COPYING.txt是组件许可，SOURCE.txt说明对应版本源码和依赖的获取方式。清单仅证明文件与审查版本一致，不替代许可证要求及干净Windows环境依赖验证。

构建只收清单文件并校验哈希及EXE/DLL的x64架构，禁止路径越界、其他EXE和Npcap/WinPcap安装器、驱动、Packet.dll/wpcap.dll。不要从本机系统目录拷出Npcap文件。现有可选vendor目录不会再被默认整目录打包。dumpcap通过独立子进程调用，Npcap驱动仍由接收者从官方安装。

### iOS暂缓

Qt for Python现有iOS部署工具，但当前Windows目录包、dumpcap进程与Npcap驱动无法直接搬到iPhone。需要macOS/Xcode签名部署、触控布局及另行设计手机端采集链路；本阶段先维护Windows发布版。

## 可下载便携目录版

build_portable.py可在Linux等主机交叉编译portable_launcher.c为真正的Windows x64 GUI PE，配合官方Windows嵌入式Python3.14.8和Windows版PySide6/Shiboken6.12.0组装目录版。需安装构建工具ziglang==0.14.1及pefile，把脚本INPUTS列出的三个官方文件放在inputs目录，再运行python build_portable.py --inputs 路径 --output 全新输出目录。输入必须通过固定SHA256校验；输出不接受与已有目录混合。

这是应用自带Windows解释器的EXE入口，不是把Linux可执行文件改后缀，也不是Windows实机测试的替代。启动器只依赖Windows系统DLL，Qt及C++运行库保留为独立文件。最终ZIP包含运行资源、许可证、BUILD_MANIFEST.json，外侧SHA256SUMS.txt核对整个包。用户只需解压并双击入口EXE，保留_internal；实时捕获继续复用系统Wireshark与Npcap。
