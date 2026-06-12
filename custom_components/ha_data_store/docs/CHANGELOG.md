# 更新日志

## 2026-06-11 — 多项功能新增与修复

### 🆕 新增功能

#### 1. 虚拟设备：媒体播放器 & 音响
- 新增 `VirtualMedia` 类 → 媒体虚拟设备（完整影音播放器）
- 新增 `VirtualSpeaker` 类 → 音响虚拟设备（专注音频体验）
- 两个类型均使用 `media_player` 域
- 支持：播放/暂停/停止/开关机、音量控制、音源切换、音效模式、上下曲等
- 新增 `media_player.py` 平台文件，注册 `async_add_media_player` 回调
- `PLATFORMS` 列表新增 `media_player`

#### 2. 属性查询：`attr_daily` 按日分组
- 新增查询类型 `attr_daily`：按天分组返回指定月份属性记录
- 仅支持单表查询
- 日期字段自动从表列检测（优先 `datetime` → `day` → `on_time` 等）
- 支持手动指定 `date_field` 参数
- 前端 API 工具新增 `📅 属性按日分组` 选项
- 新增后端接口 `/api/ha_data_store/table_columns` 获取表列名

### 🐛 Bug 修复

#### 1. `attr_history` 多表查询修复
- **问题**：多选属性表时，逗号分隔的 `attr_type` 被整体当作一个表名处理
- **修复**：拆分后逐个加 `attr_` 前缀分别查询，合并结果
- 单表保持旧返回格式兼容，多表返回按表分组格式

#### 2. `attr_history` 支持 `start`/`end` 日期范围
- **问题**：`start`/`end` 参数虽已提取但未被使用
- **修复**：加入 WHERE 条件，支持 `datetime >= start AND datetime <= end 23:59:59`

#### 3. 传感器小数位数改为3位
- **问题**：传感器数值统一保留2位小数，精度不足
- **修复**：将 `round(value, 2)` 全部改为 `round(value, 3)`
- 修改位置：`_write_env_metric_record` 和采集循环中的数值提取

### 🔧 其他优化

#### 前端 API 工具界面改进
- `attr_daily` 模式下日期字段改为文本输入框，用户可手动填写字段名
- 不影响其他查询类型的下拉选择功能
- 属性类型复选框显示完整表名（`attr_xxx`）
