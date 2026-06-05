# HA 数据统一存储系统 (ha_data_store)

Home Assistant 自定义集成，提供**数据采集、存储、对外 API 服务**一体化能力。

---

## 功能总览

| 模块 | 说明 |
|---|---|
| 📡 设备类 | 监听开关状态，记录开关机时间、时长、电量 |
| 🌡️ 传感器类 | 定时采集温湿度/PM2.5/CO2/功率/通用传感器，支持整分钟模式 |
| 📊 属性提取 | 提取实体属性中的数组/字段，独立建表存储 |
| 📁 实体→JSON | HA 实体状态实时导出为 JSON 文件 |
| 📄 JSON→实体 | 监听 JSON 文件变化，生成 HA 实体 |
| 🌐 API→实体 | 定时请求外部 API，JSON 响应转 HA 实体 |
| 🔑 密钥管理 | API Key 鉴权，管理页面密码保护 |
| 📈 系统监控 | 6 大类健康状态实时监控 |

---

## 访问入口

```
http://你的HA地址:8123/api/ha_data_store/db_viewer
```

- **同网段限制**：仅和 HA 同一子网的设备可访问
- **登录保护**：需要管理员密码（默认 `admin`，首次请修改）

---

## API 接口

### 数据查询

```
GET /api/ha_data_store/query?type=xxx&key=你的APIKey
```

| type | 说明 | 必需参数 |
|---|---|---|
| `device_history` | 设备开关记录 | entity_id, date(可选), room(可选) |
| `device_summary` | 设备汇总统计 | entity_id, date/month/year(可选) |
| `env_history` | 环境历史 | entity_id, metric |
| `env_latest` | 环境最新值 | entity_id, metric |
| `attr_history` | 属性历史 | attr_type, entity_id |
| `attr_latest` | 属性最新值 | attr_type, entity_id |
| `entities` | 实体列表 | 无 |

**通用参数**：`limit`(默认500)、`offset`、`order_by`(排序字段)、`fields`(返回字段)、`key`(API Key)

### 其他接口

| 接口 | 说明 |
|---|---|
| `GET /api/ha_data_store/stats` | 数据统计（各行数+磁盘大小） |
| `GET /api/ha_data_store/attr_types` | 属性类型列表 |
| `GET /api/ha_data_store/entity_state?entity_id=xxx` | 实体状态+属性树 |
| `GET /api/ha_data_store/config` | 实体配置列表 |

### 管理接口（仅限局域网）

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/ha_data_store/db_viewer` | GET | 管理页面 |
| `/api/ha_data_store/apikey` | GET/POST/DELETE | 密钥管理 |
| `/api/ha_data_store/apikey/settings` | POST | 修改管理员密码 |
| `/api/ha_data_store/db_viewer/data?table=xxx` | GET | 表数据分页 |
| `/api/ha_data_store/db_viewer/update` | POST/DELETE | 编辑/删除单元格 |

---

## 配置格式

### 设备类
```
房间, 设备名称, 实体ID, 电量传感器ID
厨房, 烧水壶, input_boolean.shao_shui_hu, sensor.xxx
```
房间、设备名称、电量传感器均为选配。

### 传感器类
```
指标: 房间, 实体ID, 频率(分钟), int
power: 客厅, sensor.power, 10, int
sensor: 卧室, sensor.illuminance, 15
```
`int` 表示整分钟采集（如 10,int = 每 0/10/20/30/40/50 分采集）。
`sensor` 指标支持非数值 state（如光照度、AQI 等）。

### 属性提取
在管理页面中按步骤配置：加载实体 → 选择数组 → 字段映射 → 保存。

---

## 安全架构

```
外部网络                    局域网
    │                         │
    │  query?key=xxx          │  db_viewer（管理页）
    │  ✅ 允许               │  ⚠️ 同网段+密码
    │                         │
    │  db_viewer              │  密钥管理 → 需密码
    │  ❌ 拒绝                │  修改密码 → 需旧密码
```

| 控制开关 | 作用 |
|---|---|
| `switch.ha_data_store_api` | API访问控制 — OFF 全部拒绝 |
| `switch.ha_data_store_db_browse` | 数据库浏览 — OFF 禁止查看数据 |
| `switch.ha_data_store_db_modify` | 数据库修改 — OFF 禁止写入 |

---

## 实体列表

| 实体 ID | 名称 | 说明 |
|---|---|---|
| `sensor.ha_data_store_info` | 统一存储系统信息 | 全量监控数据属性 |
| `switch.ha_data_store_api` | API访问控制 | 总开关 |
| `switch.ha_data_store_db_browse` | 数据库浏览 | 控制数据查看 |
| `switch.ha_data_store_db_modify` | 数据库修改 | 控制数据写入 |

---

## 数据库表结构

| 表名 | 说明 |
|---|---|
| `entity_configs` | 实体配置 |
| `device_history` | 设备开关记录 |
| `env_*` | 环境数据（按指标分表） |
| `attr_*` | 属性数据（按类型分表） |
| `api_keys` | API 密钥 |
| `api_settings` | 设置（管理员密码） |

---

## 外网访问

推荐 Cloudflare Tunnel 零配置穿透：

```
https://ha.你的域名.com/api/ha_data_store/query?type=xxx&key=你的Key
```

内外网同一地址，自动 HTTPS。详见 HA Add-on `cloudflared`。
