# 第三方组件说明

本源码包不包含第三方二进制运行库、商业图标包或驱动。深色样式与文字占位由本项目实现；Windows 使用系统字体，无额外字体分发。

## 游戏图片

assets目录包含用户要求从其提供的《伊瑟》游戏图鉴截图中裁取的角色头像、智壳和矩阵图标，供本助手按名称展示。仅包含小幅游戏图片，不包含账号、库存信息或原始截图。游戏名称、角色及图片版权归各自权利人所有；本项目的代码许可不授予这些游戏素材的版权。

## Qt for Python / PySide6-Essentials / Shiboken6

运行时由 requirements.txt 从 Python 包索引安装。官方项目与许可说明：

- https://doc.qt.io/qtforpython-6/
- https://doc.qt.io/qtforpython-6/licenses.html
- https://www.qt.io/licensing/open-source-lgpl-obligations

请在对外分发 Qt 二进制之前保留相应版权、许可文件，检查所使用模块及各组件的许可和源码提供要求。安装免费开源版不等于可以删除分发义务。PyInstaller 一目录模式保持 Qt 动态库为独立文件。

## PyInstaller（仅构建时）

- https://pyinstaller.org/
- https://pyinstaller.org/en/stable/license.html

## dumpcap / Wireshark / Npcap（外部捕获组件）

本包默认调用用户已安装的 dumpcap，未捆绑该程序、DLL 或驱动。已有安装可以复用。可选 vendor/dumpcap 目录仅为构建入口，并非获得第三方重新分发许可。

- https://www.wireshark.org/docs/wsdg_html_chunked/ChSrcBinary
- https://npcap.com/

Npcap 免费安装器不要直接打入分享包。若之后计划包含第三方抓包程序或驱动，应先单独评估相应的许可、依赖和分发方案。
