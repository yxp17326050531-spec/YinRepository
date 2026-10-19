# 伊瑟 · 对局助手 — Windows 发布版

将ZIP完整解压到一个普通文件夹，双击EtheriaAssistant.exe。必须保留_internal文件夹，不要只复制EXE。接收者无需安装Python、Git或开发依赖。

## 首次使用

- 离线导入：直接点击“导入抓包”，选择pcap/pcapng文件，无需抓包驱动。
- 实时监听：先安装Windows版Wireshark及其官方安装流程提供的Npcap，然后进入设置，点击“重新检测 dumpcap”，选择正在联网的网卡并保存。
- 已安装Wireshark/Npcap：直接复用，不必重复安装，也不必打开Wireshark界面。
- 设置里有官方安装入口：https://www.wireshark.org/download.html ，https://npcap.com/ 。默认包不包含Npcap安装器、驱动或dumpcap运行库。

## 数据与更新

数据位于本机%LOCALAPPDATA%\EtheriaAssistant，与EXE分开；替换整个程序文件夹不删除历史或自定义映射。更新前先关闭助手，把新版解压到新文件夹再启动；不要将两个版本的_internal混用。源码版update.cmd用于Git安装，不能更新冻结EXE目录。

此版本支持Windows x64。未提供代码签名；不能把源码测试通过当作所有Windows电脑上的抓包验证。首次分享建议先在一台Windows机器检查启动、头像、离线导入、实时监听和停止。

## 已知范围

首页显示双方八名角色和十四项开场属性；未知值显示—。未确认的胜方保持待确认，可逐场校正；没有证据时不按A/B方向猜测。没有实时战斗过程或选人阶段完整敌方属性的承诺。iOS版本暂未推进。

## 组件说明

PySide6/Qt、Shiboken和Python运行库随目录提供，相关许可见licenses及_internal中的组件元数据；THIRD_PARTY_NOTICES.md列出官方许可与源码入口。游戏名称与图片版权归相应权利人。Npcap驱动由用户从官方安装。
