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

1. 在Windows上安装64位Python 3.10+（建议使用已验证环境；本程序开发测试为Python3.12），保留py启动器和Tcl/Tk。
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
