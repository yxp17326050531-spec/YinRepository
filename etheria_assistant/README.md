# 伊瑟 · 对局助手 2.4.0

源码持续维护于 `yxp17326050531-spec/YinRepository` 的 `etheria-desktop` 分支。首次用 `setup_git.cmd` 安装到 Git 工作目录，之后通过 `update.cmd` 增量更新。

本机运行的 PySide6 对局助手。界面按 B 预览调整为蓝黑底、青色强调、蓝/红双方标题、黄色速度和紧凑角色行；窄窗口上下排列队伍。

## 一次安装，以后增量更新

下载仓库中的 `etheria_assistant/setup_git.cmd` 并双击。需要 Git for Windows、Python 3.10+ 和私有仓库访问权限；Git 首次访问可能打开浏览器登录 GitHub。脚本只克隆 `etheria-desktop` 分支，并在 `checkout/etheria_assistant` 内安装依赖。

安装完成后：

- 启动：`checkout/etheria_assistant/start.cmd`。
- 更新：先关闭程序，双击同目录 `update.cmd`，完成后再启动。
- 日常更新只拉取改动；依赖未变化就不重复安装；有新提交时自动运行本机回归测试。
- 源码有本地改动或 Git 历史分叉时停止更新，保留现有文件。更新不会自动解决冲突。
- 程序和更新器共用锁，防止本版运行期间修改源码。升级旧版前仍需自己关闭旧程序。

若是直接下载的源码目录，可先运行 `install_windows.cmd` 和 `start.cmd`；这种非 Git 目录不能增量更新。推荐通过 `setup_git.cmd` 安装一次。

## 本版行为

- A 固定为己方，B 固定为敌方；界面显示“己方 / 敌方”。
- 0x6004 结算 field 1：382=己方胜利、383=己方失败。只关联同来源、精确开场时间的当前对局；未知、无关联或冲突结算保持未知。
- 自动结果存入 SQLite，实时界面、历史、统计和导出统一读取；旧版保存的可关联结算也会重放补录。
- 删除手动胜负、敌我选择；“对局分类”只维护模式与赛季。已有旧手动记录保留，自动结算优先。
- 对位与搭配总览使用己方 A 的样本；完整统计默认己方，可切换双方。
- 点击角色名继续维护精确 ID 名称；皮肤 ID 单独维护。本场配装修正、映射、历史多选删除/恢复、库存与导出保留。

对局类型仍由用户分类；未知结算不当作失败。现有结算代码适用已确认的样本，不猜测其他代码、退赛、断线或平局。矩阵显示观测到的效果，不能推算完整点数。

## 数据

沿用 `%LOCALAPPDATA%\EtheriaAssistant\history.sqlite3`、用户映射和日志，与源码目录分开。更新、重新克隆不会删除它们。Wireshark/dumpcap 与 Npcap 沿用本机安装，不重复下载驱动。统计来自本地观测，不是全服数据。

`UI_PREVIEW.png` 是本版程序离屏运行截图（示例数据），不是生成式设计图。当前没有游戏角色头像资源。

## 开发与验证

`python -m unittest discover -v`。无图形 Linux 环境用 `QT_QPA_PLATFORM=offscreen`。44+ 项协议、SQLite、Qt、结算和 Git 更新回归；Windows 实机抓包和 DPI 尚未在当前环境验证。

后续直接修改本仓库的 `etheria-desktop` 分支；不要每次生成完整压缩包。可选 `build_windows.cmd` 仍可制作 EXE，日常迭代无需执行。
