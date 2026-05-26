# Codex 需求文档：伊瑟 BP 截图录入与统计推荐工具

## 项目目标

开发一个 Python 桌面程序，用于从《伊瑟》PVP/RTA 历史对局截图中录入 BP 数据，并逐步积累本地数据库，用于统计玩家 BP 习惯和生成选人建议。

程序不追求完全自动识别，核心目标是：

```text
截图导入
→ 自由调整识别框
→ 裁剪角色头像
→ 本地模板识别
→ OpenAI 视觉 API 兜底
→ 人工确认
→ 保存对局数据库
→ 统计 Pick率/Ban率/胜率/顺位胜率
→ 给出选人建议
```

## 技术栈要求

使用 Python 实现。

推荐：

- Python 3.11+
- PySide6
- opencv-python
- Pillow
- numpy
- imagehash
- requests
- sqlite3

桌面 UI 使用：PySide6

数据库使用：SQLite

打包目标：后续可用 PyInstaller 打包为 Windows EXE

## 项目结构

```text
yise_bp_recorder/
├─ app.py
├─ requirements.txt
├─ README.md
├─ ui/
│  ├─ main_window.py
│  ├─ canvas_widget.py
│  ├─ result_panel.py
│  └─ stats_panel.py
├─ core/
│  ├─ cropper.py
│  ├─ recognizer.py
│  ├─ vision_api.py
│  ├─ database.py
│  ├─ stats.py
│  └─ recommender.py
├─ data/
│  ├─ roles.json
│  ├─ rules.json
│  ├─ default_layout.json
│  └─ yise_bp.sqlite
├─ templates/
│  └─ README.md
├─ samples/
│  └─ README.md
└─ exports/
```

## 输入数据

### 1. roles.json

角色基础表，格式：

```json
[
  {
    "id": 30151,
    "name": "弥瑟亚",
    "rare": 5,
    "type": 5,
    "avatar": "https://..."
  }
]
```

### 2. rules.json

玩家规则表，格式：

```json
{
  "30151": {
    "name": "弥瑟亚",
    "tierRaw": "T1",
    "tierScore": 88,
    "tags": ["输出", "核心"],
    "counters": [],
    "counteredBy": []
  }
}
```

### 3. 截图

支持导入：

- `.png`
- `.jpg`
- `.jpeg`

截图类型主要是历史对局列表，一张图可能包含 5 行对局。

## UI 功能要求

### 主窗口布局

- 左侧：工具栏
- 中间：截图画布
- 右侧：识别结果与人工确认
- 底部：当前小框预览、保存模板、状态信息

### 画布功能

必须支持：

1. 鼠标滚轮缩放截图
2. 鼠标拖动画布
3. 行框自由拖动
4. 行框自由缩放
5. 小头像槽位框自由拖动
6. 小头像槽位框自由缩放
7. 背景图缩放时，框位置不能错乱
8. 坐标保存为原图坐标，不保存屏幕显示坐标

### 框类型

每行对局包含：

- `left_preban`
- `left_pick_1`
- `left_pick_2`
- `left_pick_3`
- `left_pick_4`
- `left_pick_5`
- `left_large`
- `right_large`
- `right_pick_1`
- `right_pick_2`
- `right_pick_3`
- `right_pick_4`
- `right_pick_5`
- `right_preban`
- `left_win_marker`
- `right_win_marker`

注意：玩家头像、段位徽章、玩家名字、分数不需要识别。

## 坐标模板功能

需要支持：

1. 保存当前 layout 为 JSON
2. 加载 layout JSON
3. 默认提供一份 `default_layout.json`
4. 支持多分辨率模板

layout 格式：

```json
{
  "imageWidth": 1920,
  "imageHeight": 1080,
  "rows": [
    {
      "rowIndex": 1,
      "rect": [0, 0, 100, 100]
    }
  ],
  "slots": {
    "left_preban": [0, 0, 50, 50],
    "left_pick_1": [50, 0, 50, 50]
  }
}
```

slot 坐标以每一行 row rect 为相对坐标。

## 裁剪功能

对每个 slot 裁剪小图：

```text
原图
→ 根据 row rect 和 slot rect 裁剪
→ 去除边框/等级/星级干扰，优先保留头像中心区域
→ 输出 crop image
```

支持保存当前选中的小框截图：

```text
选择一个 slot
→ 手动选择正确角色
→ 点击“保存为该角色模板”
→ 保存到 templates/{role_id}/skin_xxx.png
```

## 本地模板识别

每个角色可以有多个模板：

```text
templates/
├─ 30151/
│  ├─ official.png
│  ├─ skin_001.png
│  └─ skin_002.png
├─ 31801/
│  ├─ official.png
│  └─ skin_001.png
```

识别时：

```text
一个 crop
→ 和所有模板比较
→ 返回 Top 5 候选
```

相似度算法建议：

1. pHash 距离
2. 灰度 SSIM 或近似结构相似度
3. 颜色直方图
4. 边缘特征

最终输出：

```json
[
  {
    "roleId": 30151,
    "roleName": "弥瑟亚",
    "score": 0.93,
    "source": "local_template"
  }
]
```

置信度规则：

- `>= 0.90` 自动通过
- `0.70 - 0.90` 需要人工确认
- `< 0.70` 建议调用视觉 API

## OpenAI 视觉 API 兜底

从环境变量读取：

- `OPENAI_API_KEY`
- `OPENAI_MODEL`

默认模型：

```text
gpt-5.4-mini
```

API 只用于本地识别失败或低置信度的 slot。

输入给模型时，不要发整张截图。应该发送：

- 当前小头像 crop
- 或当前一行 contact sheet

模型必须返回 JSON：

```json
{
  "candidates": [
    {
      "name": "弥瑟亚",
      "confidence": 0.82
    }
  ],
  "uncertain": true
}
```

再由程序把 name 匹配到 `roles.json` 的角色 ID。

## 人工确认功能

右侧结果面板需要显示每一行：

- 左预Ban
- 左Pick1-5
- 左大图
- 右大图
- 右Pick1-5
- 右预Ban
- 胜利方

每个 slot 显示：

- 裁剪图
- 识别角色名
- 置信度
- 下拉框手动选择角色
- 按钮：保存为该角色模板

必须支持：

1. 手动修正角色
2. 手动设置胜利方 `left` / `right` / `unknown`
3. 保存单行对局
4. 保存全部已确认对局

## 数据库设计

使用 SQLite。

### matches 表

```sql
CREATE TABLE matches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT,
  source_image TEXT,
  rank INTEGER,
  winner TEXT,
  my_position TEXT,
  note TEXT
);
```

### match_slots 表

```sql
CREATE TABLE match_slots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  match_id INTEGER,
  side TEXT,
  slot_type TEXT,
  slot_order INTEGER,
  role_id INTEGER,
  role_name TEXT,
  confidence REAL,
  source TEXT,
  manual_confirmed INTEGER
);
```

`side`：

- `left`
- `right`

`slot_type`：

- `preban`
- `pick`
- `large`
- `finalban`

## 统计功能

基于数据库计算：

1. 角色 Pick 次数
2. 角色 Pick 率
3. 角色 PreBan 次数
4. 角色 PreBan 率
5. 角色胜率
6. Pick1 胜率
7. Pick2 胜率
8. Pick3 胜率
9. Pick4 胜率
10. Pick5 胜率
11. 先手/后手胜率
12. 面对某角色时的胜率
13. 与某角色同队时的胜率

输出为表格，可导出 CSV。

## 推荐算法

实现一个初版 recommender。

输入：

```json
{
  "rank": 15,
  "myPicks": [30151],
  "enemyPicks": [31801, 32451],
  "myPreBans": [],
  "enemyPreBans": [],
  "currentPickOrder": 3
}
```

输出 Top 5 推荐：

```json
[
  {
    "roleId": 32251,
    "roleName": "玄骊",
    "score": 86.5,
    "reasons": [
      "玩家T度较高",
      "当前顺位历史胜率较高",
      "面对敌方阵容样本表现较好"
    ],
    "stats": {
      "pickRate": 0.21,
      "winRate": 0.56,
      "sampleSize": 42
    }
  }
]
```

评分公式初版：

```text
score =
  tierScore * 0.30
+ overallWinRateScore * 0.20
+ pickOrderWinRateScore * 0.20
+ enemyConditionScore * 0.20
+ officialApiBonus * 0.10
- lowSamplePenalty
```

如果样本少于 10 局，必须降权。

## 官方 API 融合

保留调用官方 `/predict` 的能力，但只作为加分项。

如果官方推荐角色在候选中：

- `+5` 到 `+10` 分

不能让官方 API 单独决定推荐结果。

## 验收标准

### 阶段 1：UI 和坐标

必须做到：

1. 能打开截图
2. 能缩放拖动画布
3. 能拖拽/缩放行框
4. 能拖拽/缩放小头像框
5. 能保存和加载 `layout.json`

### 阶段 2：裁剪和模板

必须做到：

1. 能预览每个 slot 的裁剪图
2. 能把裁剪图保存到 `templates/{role_id}/`
3. 一个角色可以保存多个模板

### 阶段 3：本地识别

必须做到：

1. 能加载 `templates/`
2. 能对当前行进行本地模板识别
3. 能返回 Top 5 候选
4. 能显示置信度

### 阶段 4：人工确认和数据库

必须做到：

1. 能人工修正识别结果
2. 能保存单行对局到 SQLite
3. 能查看已保存对局

### 阶段 5：统计和推荐

必须做到：

1. 能统计 Pick率、Ban率、胜率、顺位胜率
2. 能导出 CSV
3. 能根据当前 BP 状态给出 Top 5 推荐
