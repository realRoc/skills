# MCP & ClawdBot 模块规范与接口文档

> **继承自**: [根目录 AGENTS.md](../../AGENTS.md)

本文档为 AI 提供在 MCP 模块(特别是 ClawdBot 子模块)中开发新功能的完整指南,包含业务规范和完整的 API 接口文档。

---

## 模块定位

**职责**:作为 MCP(Model Context Protocol)服务的网关,处理外部智能体服务的调用,特别是 ClawdBot 相关的订阅、支付、IM 配置等功能。

**主要功能**:
- ClawdBot 订阅管理(Waiting List、订阅购买)
- IM 配置管理(飞书、Slack、Discord 等)
- 云服务器实例管理(分配、重装、重启)
- 邀请拉新活动(活动 b、c、d)
- 系统版本管理
- Bot API 调用接口

**核心集合**:
- `clawdbot_im_config`:IM 渠道配置
- `clawdbot_versions`:系统版本元数据
- `clawdbot_waitlist`:等候队列
- `orders`:订单记录(`is_clawdbot=True` 标识 ClawdBot 订单)
- `invite_reward`:邀请奖励记录
- `invite_info`:邀请人统计
- `bot_api_keys`:Bot API Key 管理

---

## ClawdBot 业务规范

### ClawdBot 多渠道配置全量同步机制 ⭐️

**背景**:ClawdBot 支持用户在多个 IM 渠道(飞书、Slack、Discord 等)接入同一个 AI 助手。一个用户只分配一台云服务器实例(server_id),所有渠道共享同一台机器。

**核心原则**:
1. **一用户一机器**:一个 `username` 只对应一个 `server_id`,所有 IM 配置共享该机器
2. **全量配置同步**:每次调用 Lighthouse 服务时,必须传递用户所有渠道的完整配置(不只是当前修改的渠道)
3. **serverId 传递**:如果用户已有机器(`existing_server_id` 存在),必须在请求中包含 `serverId` 字段
4. **⭐️ 飞书凭证验证**:保存或更新飞书配置前,调用飞书 API 验证 `app_id` 和 `app_secret` 是否有效

**飞书凭证验证机制** ⭐️:

**验证函数**:`verify_feishu_credentials(app_id: str, app_secret: str) -> tuple[bool, str]`

**验证流程**:
1. 调用飞书 API:`https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal`
2. 请求参数:`{"app_id": "...", "app_secret": "..."}`
3. 验证成功:飞书返回 `{"code": 0, "tenant_access_token": "..."}`
4. 验证失败:飞书返回 `{"code": 非0, "msg": "错误信息"}`

**应用位置**:
- `saveIMConfig` 接口:验证字段不为空后立即验证
- `updateIMConfig` 接口:验证所有配置字段后批量验证
- `restartWithLatestConfig` 接口:从数据库读取配置后验证 ⭐️

**验证失败处理**:
- 错误码:`ResponseCode.other_error`
- 错误消息:`"App ID或secret错误,请核实!"`
- 日志事件:
  - 成功:`feishu_credentials_verified`
  - 失败:`feishu_credentials_verification_failed`
  - 异常:`feishu_credentials_verification_error`
  - 保存时验证失败:`clawdbot_save_im_config_validation_failed`
  - 更新时验证失败:`clawdbot_update_im_config_validation_failed`
  - 重启时验证失败:`clawdbot_restart_with_latest_config_validation_failed` ⭐️

**超时设置**:10 秒(避免验证请求长时间阻塞)

### ClawdBot 邀请拉新活动体系 ⭐️

**背景**:ClawdBot 支持多种邀请拉新活动,通过邀请好友注册/购买来获得不同类型的奖励。

#### 活动体系总览

| 活动代码 | 活动名称 | 注册事件 | 奖励触发点 | 被邀请人奖励 | 邀请人奖励 |
|---------|---------|---------|-----------|------------|-----------|
| `'b'` | 现金返利活动 | `register_cash` | 被邀请人支付任意订单 | 无 | 首购返 30%,复购返 10% |
| `'c'` | ClawdBot 拉新活动 | `register_clawdbot_c` | 被邀请人首笔 ClawdBot 付款 | 20 元代金券(30 天有效) | 返现 30% |
| `'d'` | ClawdBot 0 元认领活动 | `register_clawdbot_d` | 被邀请人首笔 ClawdBot 付款(含 0 元认领) | 无 | ClawdBot 实例延长 3 天 |

#### 活动 d 实现细节(ClawdBot 0 元认领活动)⭐️

**设计目标**:降低用户试用门槛,通过 0 元认领吸引新用户,邀请人通过成功邀请获得实例时长延长。

**奖励结算机制**:
- **触发条件**:被邀请人首次完成 ClawdBot 订单支付(包括 0 元认领订单)
- **奖励内容**:邀请人的 `clawdbot_vip_expire_time` 延长 3 天(259200 秒)

**补充触发机制(click_free_share)** ⭐️:

除了首笔 ClawdBot 付款触发奖励外,还支持通过用户主动分享触发奖励。

**触发条件**:
- 用户在前端调用 `/userLog` 接口
- `page='clawdbot'` 且 `event='click_free_share'`
- ⭐️ **用户必须通过活动 d 注册**(`invite_reward` 中存在 `event='register_clawdbot_d'` 记录)
- 该用户有邀请人(从 `invite_reward` 的 `register_from` 字段提取)

**防重复机制**:
- Redis 键:`clawdbot_free_share_rewarded::{username}`
- 单个用户只能给上游邀请人增加一次 3 天时长
- TTL:365 天

**⭐️ 与支付奖励的互斥关系**:
- **click_free_share 奖励优先**:如果用户已通过分享触发奖励,后续支付时不再触发奖励
- **支付奖励检查**:`rebate_invite_clawdbot_d` 函数会检查 `invite_reward` 中是否存在 `event='clawdbot_free_share_d'` 记录
- **互斥原因**:避免同一个被邀请人给邀请人重复奖励(只能选择分享或支付之一)

### ClawdBot 系统版本管理 ⭐️

**背景**:ClawdBot 支持系统版本管理,用户可以查询当前系统版本和最新版本,了解更新说明。

**核心设计**:
1. **版本号格式**:使用语义化版本号(如 `v1.0.0`、`v2.0.0`)
2. **默认版本**:如果用户配置中没有 `system_version` 字段,默认为 `v1.0.0`
3. **版本元数据**:存储在 `clawdbot_versions` 集合中,包含版本号、更新说明、发布时间等
4. **用户版本**:存储在 `clawdbot_im_config` 集合的 `system_version` 字段中

---

## API 接口规范

### 接口总览表

| 接口组 | 接口数量 | 说明 |
|--------|---------|-----|
| 等候队列 | 2 | joinWaitlist, getWaitlistInfo |
| 订阅支付 | 4 | clawdbot_pay, get_clawdbot_coupons, check_clawdbot_paid, getClawdBotPaymentHistory |
| 邀请拉新 | 4 | get_free_clawdbot_invite_link, get_free_clawdbot_invitee_list, get_free_clawdbot_vip_time, check_clawdbot_free_share |
| IM 配置 | 4 | save_im_config, update_im_config, get_im_configs, delete_im_config |
| 模型配置 | 3 | get_model_configs, update_model_config, delete_model_config |
| 实例管理 | 3 | reboot_instance, restart_with_latest_config, migrate_clawdbot |
| 系统版本 | 1 | get_system_version |
| Bot API | 5 | createBotApiKey, listBotApiKeys, revokeBotApiKey, botAskAgents, botCheckTask |

**总计**:26 个接口

---

### 等候队列接口

#### POST /api/engine/clawdbot/joinWaitlist

**功能**:加入 ClawdBot 等候队列

**请求模型**:`JoinWaitlistRequestModel`
- `phonenumber`:str(可选) - 手机号
- `email`:str(可选) - 邮箱
- `task_description`:str(必需) - 希望完成的任务
- `phone_country_code`:str(可选,默认 +86) - 国家代码

**响应模型**:`JoinWaitlistResponseModel`
- `queue_number`:int - 排队编号
- `message`:str - 提示消息

**认证**:需要登录(`get_current_user`)

**业务逻辑**:
1. 查询用户已有排队记录
2. 如未排队,生成新的 queue_number(起始 528)
3. 保存到 clawdbot_waitlist 集合
4. 返回排队编号

**请求示例**:
```json
{
  "phonenumber": "13800138000",
  "email": "user@example.com",
  "task_description": "我想用 ClawdBot 来管理我的团队任务",
  "phone_country_code": "+86"
}
```

**响应示例**:
```json
{
  "code": 0,
  "result": {
    "queue_number": 528,
    "message": "您已成功加入等候队列,排队编号:528"
  }
}
```

#### POST /api/engine/clawdbot/getWaitlistInfo

**功能**:查询用户在等候队列中的状态

**请求**:无参数

**响应模型**:`WaitlistInfoResponseModel`
- `is_in_waitlist`:bool - 是否在等候队列中
- `queue_number`:int - 排队编号(如果在队列中)
- `message`:str - 提示消息

**认证**:需要登录(`get_current_user`)

**响应示例**:
```json
{
  "code": 0,
  "result": {
    "is_in_waitlist": true,
    "queue_number": 528,
    "message": "您当前排队编号:528"
  }
}
```

---

### 订阅支付接口

#### POST /api/engine/clawdbot/pay

**功能**:创建 ClawdBot 订阅支付订单

**请求模型**:`ClawdBotPayRequestModel`
- `coupon_code`:str(可选) - 优惠券代码

**响应模型**:`ClawdBotPayResponseModel`
- `pay_url`:str - 支付链接
- `order_id`:str - 订单 ID
- `amount`:float - 支付金额
- `message`:str - 提示消息

**认证**:需要登录(`get_current_user`)

**业务逻辑**:
1. 检查用户是否已订阅(避免重复购买)
2. 验证优惠券(如提供)
3. 生成订单(orders 集合,`is_clawdbot=True`)
4. 调用支付宝 API 创建支付链接
5. 返回支付链接

**请求示例**:
```json
{
  "coupon_code": "WELCOME2024"
}
```

**响应示例**:
```json
{
  "code": 0,
  "result": {
    "pay_url": "https://openapi.alipay.com/gateway.do?...",
    "order_id": "ord_abc123",
    "amount": 99.0,
    "message": "订单创建成功,请完成支付"
  }
}
```

#### POST /api/engine/clawdbot/getClawdBotCoupons

**功能**:获取可用的 ClawdBot 优惠券列表

**请求**:无参数

**响应模型**:`ClawdBotCouponsResponseModel`
- `coupons`:List[CouponModel] - 优惠券列表
  - `code`:str - 优惠券代码
  - `discount`:float - 折扣金额
  - `expire_time`:float - 过期时间戳
  - `description`:str - 描述

**认证**:需要登录(`get_current_user`)

**响应示例**:
```json
{
  "code": 0,
  "result": {
    "coupons": [
      {
        "code": "WELCOME2024",
        "discount": 20.0,
        "expire_time": 1735660800.0,
        "description": "新用户专享 20 元优惠"
      }
    ]
  }
}
```

#### POST /api/engine/clawdbot/checkClawdBotPaid

**功能**:检查用户是否已支付 ClawdBot 订阅

**请求**:无参数

**响应模型**:`CheckClawdBotPaidResponseModel`
- `is_paid`:bool - 是否已支付
- `vip_expire_time`:float - VIP 到期时间戳(如果已支付)
- `message`:str - 提示消息

**认证**:需要登录(`get_current_user`)

**响应示例**:
```json
{
  "code": 0,
  "result": {
    "is_paid": true,
    "vip_expire_time": 1738425600.0,
    "message": "您的 ClawdBot 订阅有效期至 2026-02-01"
  }
}
```

#### POST /api/engine/clawdbot/getClawdBotPaymentHistory

**功能**:获取用户的 ClawdBot 支付历史记录

**请求**:无参数

**响应模型**:`ClawdBotPaymentHistoryResponseModel`
- `payments`:List[PaymentRecordModel] - 支付记录列表
  - `order_id`:str - 订单 ID
  - `amount`:float - 支付金额
  - `status`:str - 订单状态(pending/paid/cancelled)
  - `create_time`:float - 创建时间戳
  - `pay_time`:float - 支付时间戳(如果已支付)

**认证**:需要登录(`get_current_user`)

**响应示例**:
```json
{
  "code": 0,
  "result": {
    "payments": [
      {
        "order_id": "ord_abc123",
        "amount": 99.0,
        "status": "paid",
        "create_time": 1707897600.0,
        "pay_time": 1707898000.0
      }
    ]
  }
}
```

---

### 邀请拉新接口

#### POST /api/engine/clawdbot/getFreeClawdBotInviteLink

**功能**:获取活动 d(0 元认领)的邀请链接

**请求**:无参数

**响应模型**:`FreeClawdBotInviteLinkResponseModel`
- `invite_link`:str - 邀请链接
- `invite_code`:str - 邀请码
- `message`:str - 提示消息

**认证**:需要登录(`get_current_user`)

**业务逻辑**:
1. 生成/查询用户的邀请码
2. 构建邀请链接(包含 `invite_event_name=d` 参数)
3. 返回邀请链接

**响应示例**:
```json
{
  "code": 0,
  "result": {
    "invite_link": "https://teamo.ai/register?invite_code=ABC123&invite_event_name=d",
    "invite_code": "ABC123",
    "message": "邀请链接生成成功"
  }
}
```

#### POST /api/engine/clawdbot/getFreeClawdBotInviteeList

**功能**:获取通过活动 d 邀请的用户列表

**请求**:无参数

**响应模型**:`FreeClawdBotInviteeListResponseModel`
- `invitees`:List[InviteeModel] - 被邀请人列表
  - `username`:str - 被邀请人用户名
  - `register_time`:float - 注册时间戳
  - `has_paid`:bool - 是否已支付
  - `reward_status`:str - 奖励状态(pending/rewarded)

**认证**:需要登录(`get_current_user`)

**响应示例**:
```json
{
  "code": 0,
  "result": {
    "invitees": [
      {
        "username": "alice",
        "register_time": 1707897600.0,
        "has_paid": true,
        "reward_status": "rewarded"
      }
    ]
  }
}
```

#### POST /api/engine/clawdbot/getFreeClawdBotVipTime

**功能**:获取用户通过活动 d 累计获得的 VIP 时长

**请求**:无参数

**响应模型**:`FreeClawdBotVipTimeResponseModel`
- `total_days`:int - 累计获得天数
- `total_invitees`:int - 成功邀请人数
- `message`:str - 提示消息

**认证**:需要登录(`get_current_user`)

**响应示例**:
```json
{
  "code": 0,
  "result": {
    "total_days": 9,
    "total_invitees": 3,
    "message": "您已通过邀请获得 9 天 VIP 时长"
  }
}
```

#### POST /api/engine/clawdbot/checkClawdBotFreeShare

**功能**:检查用户是否已通过 click_free_share 触发奖励

**请求**:无参数

**响应模型**:`CheckClawdBotFreeShareResponseModel`
- `has_shared`:bool - 是否已分享
- `message`:str - 提示消息

**认证**:需要登录(`get_current_user`)

**业务逻辑**:
1. 检查 Redis 键 `clawdbot_free_share_rewarded::{username}`
2. 如果存在,返回 `has_shared=true`

**响应示例**:
```json
{
  "code": 0,
  "result": {
    "has_shared": true,
    "message": "您已完成分享并获得奖励"
  }
}
```

---

### IM 配置接口

#### POST /api/engine/clawdbot/saveIMConfig

**功能**:保存 IM 渠道配置(首次创建,调用 allocate-reset)

**请求模型**:`SaveIMConfigRequestModel`
- `im_type`:str(必需) - IM 类型('feishu'、'slack'、'discord')
- `app_id`:str(必需) - 应用 ID
- `app_secret`:str(必需) - 应用密钥
- `default_model`:str(可选) - 默认模型
- `model_env`:dict(可选) - 模型环境变量

**响应模型**:`SaveIMConfigResponseModel`
- `server_id`:int - 服务器 ID
- `instance_id`:str - 实例 ID
- `public_ip`:str - 公网 IP
- `message`:str - 提示消息

**认证**:需要登录(`get_current_user`)

**业务逻辑**:
1. 验证必填字段(im_type、app_id、app_secret)
2. ⭐️ **飞书配置验证**(如果 im_type='feishu'):调用 `verify_feishu_credentials()`
3. 查询用户所有现有配置
4. 提取已有 server_id(所有配置共用同一个)
5. 构建全量配置数组(现有配置 + 当前要保存的配置)
6. 调用 Lighthouse `/api/instances/allocate-reset` 接口
7. 保存/更新 MongoDB 配置
8. 更新用户状态 `clawdbot_config_completed = True`

**请求示例**:
```json
{
  "im_type": "feishu",
  "app_id": "cli_a1b2c3d4e5f6",
  "app_secret": "abc123xyz789",
  "default_model": "claude-sonnet-4.5",
  "model_env": {
    "ANTHROPIC_API_KEY": "sk-ant-xxx"
  }
}
```

**响应示例**:
```json
{
  "code": 0,
  "result": {
    "server_id": 100,
    "instance_id": "lhins-abc123",
    "public_ip": "1.2.3.4",
    "message": "IM 配置保存成功,实例正在初始化"
  }
}
```

**错误响应**:
```json
{
  "code": 405,
  "result": {
    "message": "App ID或secret错误,请核实!"
  }
}
```

#### POST /api/engine/clawdbot/updateIMConfig

**功能**:批量更新 IM 配置(调用 reconfigure)

**请求模型**:`UpdateIMConfigRequestModel`
- `configs`:List[IMConfigModel](必需) - IM 配置列表
  - `im_type`:str - IM 类型
  - `app_id`:str - 应用 ID
  - `app_secret`:str - 应用密钥

**响应模型**:`UpdateIMConfigResponseModel`
- `message`:str - 提示消息

**认证**:需要登录(`get_current_user`)

**业务逻辑**:
1. 验证订阅状态(用户必须有有效订阅)
2. 验证 server_id 存在(如果没有机器,返回错误)
3. ⭐️ **飞书配置验证**(如果包含飞书配置):批量调用 `verify_feishu_credentials()`
4. 构建全量配置请求(包括 `serverId`)
5. 调用 Lighthouse `/api/instances/reconfigure` 接口
6. 批量更新 MongoDB 配置

**请求示例**:
```json
{
  "configs": [
    {
      "im_type": "feishu",
      "app_id": "cli_new123",
      "app_secret": "new_secret"
    },
    {
      "im_type": "slack",
      "app_id": "xoxb-xxx",
      "app_secret": "slack_secret"
    }
  ]
}
```

**响应示例**:
```json
{
  "code": 0,
  "result": {
    "message": "IM 配置更新成功,服务将在 1-2 分钟内重启生效"
  }
}
```

#### POST /api/engine/clawdbot/getIMConfigs

**功能**:获取用户的所有 IM 配置

**请求**:无参数

**响应模型**:`GetIMConfigsResponseModel`
- `configs`:List[IMConfigModel] - IM 配置列表
  - `im_type`:str - IM 类型
  - `app_id`:str - 应用 ID
  - `app_secret`:str - 应用密钥(脱敏显示)
  - `server_id`:int - 服务器 ID
  - `instance_id`:str - 实例 ID
  - `public_ip`:str - 公网 IP
  - `system_version`:str - 系统版本

**认证**:需要登录(`get_current_user`)

**响应示例**:
```json
{
  "code": 0,
  "result": {
    "configs": [
      {
        "im_type": "feishu",
        "app_id": "cli_a1b2c3d4e5f6",
        "app_secret": "abc1****234z",
        "server_id": 100,
        "instance_id": "lhins-abc123",
        "public_ip": "1.2.3.4",
        "system_version": "v2.0.0"
      }
    ]
  }
}
```

#### POST /api/engine/clawdbot/deleteIMConfig

**功能**:删除指定的 IM 配置

**请求模型**:`DeleteIMConfigRequestModel`
- `im_type`:str(必需) - 要删除的 IM 类型

**响应模型**:`MsgResponseModel`
- `message`:str - 提示消息

**认证**:需要登录(`get_current_user`)

**业务逻辑**:
1. 验证 IM 配置存在
2. 删除 MongoDB 中的配置记录
3. 如果删除后用户没有任何 IM 配置,释放服务器实例

**请求示例**:
```json
{
  "im_type": "feishu"
}
```

**响应示例**:
```json
{
  "code": 0,
  "result": {
    "message": "IM 配置删除成功"
  }
}
```

---

### 模型配置接口

#### POST /api/engine/clawdbot/getModelConfigs

**功能**:获取用户的模型配置(API Keys、环境变量)

**请求**:无参数

**响应模型**:`GetModelConfigsResponseModel`
- `default_model`:str - 默认模型
- `model_keys`:dict - 模型 API Keys(脱敏显示)
- `model_env`:dict - 环境变量(脱敏显示)

**认证**:需要登录(`get_current_user`)

**响应示例**:
```json
{
  "code": 0,
  "result": {
    "default_model": "claude-sonnet-4.5",
    "model_keys": {
      "anthropic": "sk-a****xyz"
    },
    "model_env": {
      "ANTHROPIC_API_KEY": "sk-a****xyz"
    }
  }
}
```

#### POST /api/engine/clawdbot/updateModelConfig

**功能**:更新模型配置

**请求模型**:`UpdateModelConfigRequestModel`
- `default_model`:str(可选) - 默认模型
- `model_keys`:dict(可选) - 模型 API Keys
- `model_env`:dict(可选) - 环境变量

**响应模型**:`MsgResponseModel`
- `message`:str - 提示消息

**认证**:需要登录(`get_current_user`)

**业务逻辑**:
1. 验证订阅状态
2. 更新 MongoDB 配置
3. 调用 Lighthouse `/api/instances/reconfigure` 接口应用新配置

**请求示例**:
```json
{
  "default_model": "claude-opus-4.6",
  "model_keys": {
    "anthropic": "sk-ant-new-key"
  }
}
```

**响应示例**:
```json
{
  "code": 0,
  "result": {
    "message": "模型配置更新成功"
  }
}
```

#### POST /api/engine/clawdbot/deleteModelConfig

**功能**:删除指定的模型配置

**请求模型**:`DeleteModelConfigRequestModel`
- `model_key_name`:str(必需) - 要删除的 API Key 名称

**响应模型**:`MsgResponseModel`
- `message`:str - 提示消息

**认证**:需要登录(`get_current_user`)

**请求示例**:
```json
{
  "model_key_name": "anthropic"
}
```

**响应示例**:
```json
{
  "code": 0,
  "result": {
    "message": "模型配置删除成功"
  }
}
```

---

### 实例管理接口

#### POST /api/engine/clawdbot/rebootInstance

**功能**:仅重启实例(不重新应用配置)

**请求**:无参数

**响应模型**:`MsgResponseModel`
- `message`:str - 提示消息

**认证**:需要登录(`get_current_user`)

**业务逻辑**:
1. 验证订阅状态
2. 查询用户的 server_id
3. 调用 Lighthouse `/api/instances/reboot` 接口

**响应示例**:
```json
{
  "code": 0,
  "result": {
    "message": "实例重启成功,预计 1-2 分钟内恢复服务"
  }
}
```

#### POST /api/engine/clawdbot/restartWithLatestConfig

**功能**:基于数据库中的最新配置重启服务 ⭐️

**请求**:无参数

**响应模型**:`MsgResponseModel`
- `message`:str - 提示消息

**认证**:需要登录(`get_current_user`)

**业务逻辑**:
1. 验证订阅状态
2. 查询数据库中的所有 IM 配置
3. 验证 server_id 存在
4. ⭐️ **验证飞书凭证**(如果存在飞书配置):调用 `verify_feishu_credentials()`
5. 构建全量配置请求(从数据库读取)
6. 调用 Lighthouse `/api/instances/reconfigure` 接口
7. ⭐️ **更新系统版本号**:将用户的 `system_version` 更新为最新版本

**响应示例**:
```json
{
  "code": 0,
  "result": {
    "message": "服务重启成功,配置已应用,系统版本已更新至 v2.0.0"
  }
}
```

**错误响应**(凭证验证失败):
```json
{
  "code": 405,
  "result": {
    "message": "App ID或secret错误,请核实!"
  }
}
```

#### POST /api/engine/clawdbot/migrateClawdBot

**功能**:迁移 ClawdBot 实例到新服务器

**请求模型**:`MigrateClawdBotRequestModel`
- `target_region`:str(可选) - 目标地域

**响应模型**:`MsgResponseModel`
- `message`:str - 提示消息

**认证**:需要登录(`get_current_user`)

**业务逻辑**:
1. 验证订阅状态
2. 备份当前配置
3. 调用 Lighthouse 迁移接口
4. 更新 MongoDB 中的实例信息

**请求示例**:
```json
{
  "target_region": "us-west-2"
}
```

**响应示例**:
```json
{
  "code": 0,
  "result": {
    "message": "实例迁移成功,新实例 IP: 5.6.7.8"
  }
}
```

---

### 系统版本接口

#### POST /api/engine/clawdbot/getSystemVersion

**功能**:获取当前系统版本和最新版本信息

**请求**:无参数

**响应模型**:`GetSystemVersionResponseModel`
- `current_version`:str - 用户当前系统版本
- `current_release_notes`:list - 当前版本的更新说明
- `latest_version`:str - 系统最新版本
- `latest_release_notes`:list - 最新版本的更新说明
- `has_update`:bool - 是否有可更新版本
- `message`:str - 提示消息

**认证**:需要登录(`get_current_user`)

**业务逻辑**:
1. 查询用户的 `clawdbot_im_config`,获取 `system_version`(默认 `v1.0.0`)
2. 查询系统最新版本(`is_latest=True`)
3. 查询当前版本的更新说明
4. 判断是否有可更新版本(`current_version != latest_version`)

**响应示例**:
```json
{
  "code": 0,
  "result": {
    "current_version": "v1.0.0",
    "current_release_notes": [
      "初始版本",
      "支持飞书机器人接入",
      "支持 Claude Opus 4.5 模型"
    ],
    "latest_version": "v2.0.0",
    "latest_release_notes": [
      "修复联网搜索失败的问题",
      "新增文件传输 skill,可支持直接在飞书内发送文件",
      "修复部分卡死的 bug"
    ],
    "has_update": true,
    "message": "有新版本可用"
  }
}
```

---

### Bot API 接口

#### POST /api/createBotApiKey

**功能**:创建 Bot API Key(人类用户管理接口,使用 JWT Token 认证)

**请求模型**:`CreateBotApiKeyRequestModel`
- `name`:str(必需) - API Key 名称(如 "My Slack Bot")

**响应模型**:`CreateBotApiKeyResponseModel`
- `api_key`:str - API Key(仅此一次显示,⚠️ 请妥善保存)
- `api_key_prefix`:str - API Key 前缀(用于展示,如 "sk-abc...xyz")
- `name`:str - API Key 名称
- `create_time`:float - 创建时间戳
- `message`:str - 提示消息

**认证**:需要登录(`get_current_user`)

**业务逻辑**:
1. 生成 API Key(`sk-` + 32 字节 URL 安全随机字符串)
2. 计算 SHA256 哈希值(不存储明文)
3. 提取前缀(前 10 位 + "..." + 后 6 位)
4. 保存到 `bot_api_keys` 集合
5. 返回明文 API Key(仅此一次)

**请求示例**:
```json
{
  "name": "Slack Bot"
}
```

**响应示例**:
```json
{
  "code": 0,
  "result": {
    "api_key": "sk-abc123xyz789defghi...",
    "api_key_prefix": "sk-abc123...234xyz",
    "name": "Slack Bot",
    "create_time": 1707897600.0,
    "message": "API Key 创建成功,请妥善保存,不会再次显示"
  }
}
```

#### POST /api/listBotApiKeys

**功能**:列出用户的所有 API Keys(人类用户管理接口,使用 JWT Token 认证)

**请求**:无参数

**响应模型**:`ListBotApiKeysResponseModel`
- `api_keys`:List[BotApiKeyModel] - API Key 列表
  - `api_key_prefix`:str - API Key 前缀(脱敏)
  - `name`:str - API Key 名称
  - `permissions`:list - 权限列表
  - `is_active`:bool - 是否激活
  - `create_time`:float - 创建时间戳
  - `last_used_time`:float - 最后使用时间戳

**认证**:需要登录(`get_current_user`)

**响应示例**:
```json
{
  "code": 0,
  "result": {
    "api_keys": [
      {
        "api_key_prefix": "sk-abc123...234xyz",
        "name": "Slack Bot",
        "permissions": ["ask_agents", "check_task"],
        "is_active": true,
        "create_time": 1707897600.0,
        "last_used_time": 1707900000.0
      }
    ]
  }
}
```

#### POST /api/revokeBotApiKey

**功能**:撤销(禁用)API Key(人类用户管理接口,使用 JWT Token 认证)

**请求模型**:`RevokeBotApiKeyRequestModel`
- `api_key_prefix`:str(必需) - 要撤销的 API Key 前缀

**响应模型**:`MsgResponseModel`
- `message`:str - 提示消息

**认证**:需要登录(`get_current_user`)

**业务逻辑**:
1. 查询 API Key(根据 prefix 和 username)
2. 更新 `is_active = False`
3. 记录撤销日志

**请求示例**:
```json
{
  "api_key_prefix": "sk-abc123...234xyz"
}
```

**响应示例**:
```json
{
  "code": 0,
  "result": {
    "message": "API Key 撤销成功"
  }
}
```

#### POST /api/bot/askAgents

**功能**:Bot 发起任务(使用 Bearer API Key 认证)

**请求模型**:`BotAskAgentsRequestModel`
- `query`:str(必需) - 用户问题
- `session_group_id`:str(可选) - 会话 ID(多轮对话时复用)
- `project_id`:str(可选) - 项目 ID

**响应模型**:`BotAskAgentsResponseModel`
- `task_id`:str - 任务 ID(question_id)
- `session_group_id`:str - 会话 ID(用于多轮对话)
- `turn`:int - 当前轮次
- `message`:str - 提示消息

**认证**:使用 Bearer API Key(`get_bot_user`)

**业务逻辑**:
1. 从 Authorization 头提取 API Key
2. 验证 API Key 有效性,获取绑定的用户
3. 如果提供 session_group_id,查询 turn(追问);否则生成新 session_group_id 和 turn=0
4. 自动生成 question_id、conv_id
5. 调用现有 `askAgents` 逻辑
6. 返回 task_id 和 session_group_id

**请求示例**(新对话):
```http
POST /api/bot/askAgents
Authorization: Bearer sk-abc123xyz789...
Content-Type: application/json

{
  "query": "请分析这个 PDF 文件",
  "project_id": "proj_123"
}
```

**请求示例**(追问):
```http
POST /api/bot/askAgents
Authorization: Bearer sk-abc123xyz789...
Content-Type: application/json

{
  "query": "能详细说明第二个问题吗?",
  "session_group_id": "sgid_abc123"
}
```

**响应示例**:
```json
{
  "code": 0,
  "result": {
    "task_id": "qid_abc123",
    "session_group_id": "sgid_abc123",
    "turn": 0,
    "message": "任务已创建,请使用 task_id 查询结果"
  }
}
```

#### POST /api/bot/checkTask

**功能**:Bot 查询任务状态(使用 Bearer API Key 认证)

**请求模型**:`BotCheckTaskRequestModel`
- `task_id`:str(必需) - 任务 ID(question_id)

**响应模型**:`BotCheckTaskResponseModel`
- `state`:str - 任务状态(running/stopped/limit/completed)
- `result`:dict(可选) - 任务结果(仅当 state=completed 时)
  - `answer`:str - 最后一个 agent 的回答
  - `documents`:list - 引用文档列表(is_teamo_cited=True)
- `message`:str - 提示消息

**认证**:使用 Bearer API Key(`get_bot_user`)

**业务逻辑**:
1. 从 Authorization 头提取 API Key
2. 验证 API Key 有效性,获取绑定的用户
3. 查询 `question_history` 获取任务状态
4. 映射状态:STREAMING/working → running,USER_STOP/cancelled → stopped,BATTERY_LIMIT/PARALLEL_LIMIT → limit,SUCCESS/FAIL/completed → completed
5. 如果 state=completed,提取最后一个 mcp_assistant 的 answer 和文档

**请求示例**:
```http
POST /api/bot/checkTask
Authorization: Bearer sk-abc123xyz789...
Content-Type: application/json

{
  "task_id": "qid_abc123"
}
```

**响应示例**(运行中):
```json
{
  "code": 0,
  "result": {
    "state": "running",
    "message": "任务正在执行中"
  }
}
```

**响应示例**(已完成):
```json
{
  "code": 0,
  "result": {
    "state": "completed",
    "result": {
      "answer": "根据 PDF 文件分析,主要发现以下三点:...",
      "documents": [
        {
          "doc_id": "doc_123",
          "title": "report.pdf",
          "url": "https://..."
        }
      ]
    },
    "message": "任务已完成"
  }
}
```

---

## 数据模型

### MongoDB 集合

#### clawdbot_waitlist(等候队列)

```python
{
    '_id': ObjectId,
    'username': str,            # 用户名
    'phonenumber': str,         # 手机号(可选)
    'email': str,               # 邮箱(可选)
    'task_description': str,    # 希望完成的任务
    'phone_country_code': str,  # 国家代码(如 +86)
    'queue_number': int,        # 排队编号(唯一)
    'create_time': float,       # 创建时间戳
}
```

**索引**:
- `username` 单字段索引
- `queue_number` 唯一索引

#### clawdbot_im_config(IM 渠道配置)

```python
{
    '_id': ObjectId,
    'username': str,                    # 用户名
    'im_type': str,                     # IM 类型('feishu')
    'app_id': str,                      # 应用 ID
    'app_secret': str,                  # 应用密钥
    'server_id': int,                   # 云服务器 ID(用户级唯一)
    'region': str,                      # 地域
    'instance_id': str,                 # 实例 ID
    'instance_name': str,               # 实例名称
    'public_ip': str,                   # 公网 IP
    'private_ip': str,                  # 内网 IP
    'blueprint_id': str,                # 镜像 ID
    'reset_request_id': str,            # 重装请求 ID
    'system_version': str,              # 系统版本(默认 v1.0.0)
    'default_model': str,               # 默认模型
    'model_keys': dict,                 # 模型 API Keys
    'model_env': dict,                  # 环境变量
    'create_time': float,               # 创建时间
    'update_time': float,               # 更新时间
    'act_completed': bool,              # 人工激活是否完成
    'show_act_notice': bool,            # 是否显示激活完成通知
}
```

**索引**:
- `username + im_type` 复合索引
- `server_id` 单字段索引

#### clawdbot_versions(系统版本元数据)

```python
{
    '_id': ObjectId,
    'version': str,                     # 版本号(如 v2.0.0)
    'release_notes': list,              # 更新说明列表
    'release_time': float,              # 发布时间戳
    'is_latest': bool,                  # 是否为最新版本
}
```

**索引**:
- `version` 唯一索引
- `is_latest + release_time` 复合索引

#### bot_api_keys(Bot API Key 管理)

```python
{
    '_id': ObjectId,
    'api_key': str,                     # API Key 的 SHA256 哈希值(不存储明文)
    'api_key_prefix': str,              # API Key 前缀(用于展示,如 "sk-abc...xyz")
    'username': str,                    # 绑定的用户名
    'name': str,                        # API Key 名称(用户自定义)
    'permissions': list,                # 权限列表(['ask_agents', 'check_task'])
    'is_active': bool,                  # 是否激活
    'create_time': float,               # 创建时间戳
    'last_used_time': float,            # 最后使用时间戳
    'expire_time': float,               # 过期时间(-1 表示永不过期)
}
```

**索引**:
- `api_key` 唯一索引
- `username + is_active` 复合索引

### Redis 键设计

| Key 模式 | 用途 | TTL |
|---------|------|-----|
| `clawdbot_free_share_rewarded::{username}` | 活动 d 分享奖励防重复 | 365 天 |

---

## 外部集成

### Lighthouse 云服务(百积木基础设施)

**Base URL**:`config.clawdbot.lighthouse_api_url`

**API 端点**:

| 端点 | 方法 | 用途 |
|------|------|-----|
| /api/instances/allocate-reset | POST | 首次分配 + 重装系统 |
| /api/instances/reconfigure | POST | 覆盖配置 + 重启服务 |
| /api/instances/reboot | POST | 仅重启实例 |

**请求格式示例**(allocate-reset):
```json
{
    "teamoUserId": "user123",
    "serverId": 100,              // 可选,已有机器时传递
    "feishuAppId": "cli_xxx",
    "feishuSecret": "xxx",
    "defaultModel": "minimax",
    "env": {...}
}
```

**响应格式**:
```json
{
    "serverId": 100,
    "instanceId": "lhins-xxx",
    "publicIp": "1.2.3.4",
    "privateIp": "10.0.0.1",
    ...
}
```

**超时设置**:300 秒

### 飞书开放平台

**验证接口**:
- URL:https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal
- 超时:10 秒
- 请求:`{"app_id": "...", "app_secret": "..."}`
- 成功:`{"code": 0, "tenant_access_token": "..."}`

### 支付宝支付

**支付流程**:
1. 调用 `/api/engine/clawdbot/pay` 创建订单
2. 返回支付链接
3. 用户完成支付
4. 支付宝回调 `/alicallback`
5. 更新用户订阅信息 + 触发邀请奖励

---

## 完整数据流图

### 订阅支付完整数据流

```
用户发起支付请求
    ↓
POST /api/engine/clawdbot/pay
    ├─ 生成订单(orders 集合,is_clawdbot=True)
    ├─ 订单字段:
    │   ├─ username
    │   ├─ price_id: CLAWDBOT_PRICE_ID
    │   ├─ amount: CLAWDBOT_PRICE (99 元)
    │   ├─ status: 'pending'
    │   └─ create_time
    ├─ 调用支付宝 API(创建支付链接)
    └─ 返回支付链接
    ↓
用户完成支付
    ↓
支付宝回调 POST /alicallback
    ├─ Step 1: 验证签名
    ├─ Step 2: 更新订单状态(orders.status = 'paid')
    ├─ Step 3: 更新用户订阅信息
    │   ├─ user.clawdbot_vip_expire_time = now + 30天
    │   ├─ user.clawdbot_price_id = CLAWDBOT_PRICE_ID
    │   ├─ user.clawdbot_extension_status = 0
    │   └─ user.clawdbot_config_completed = False
    ├─ Step 4: 检查邀请人
    │   ├─ 查询 invite_reward(event='register_clawdbot_c' 或 'register_clawdbot_d')
    │   ├─ 如果有 → 触发邀请奖励流程
    │   │   ├─ 活动 c: rebate_invite_clawdbot_c()
    │   │   │   ├─ 计算返现金额(实付 × 30%)
    │   │   │   ├─ 更新 bounty_amount(可提现余额)
    │   │   │   ├─ 插入 invite_reward(event='clawdbot_rebate_c')
    │   │   │   └─ 更新 invite_info 统计
    │   │   └─ 活动 d: rebate_invite_clawdbot_d()
    │   │       ├─ 检查是否已通过分享触发奖励
    │   │       ├─ 如果未触发 → 邀请人实例延长 3 天
    │   │       ├─ 更新 user.clawdbot_vip_expire_time
    │   │       ├─ 插入 invite_reward(event='clawdbot_purchase_d')
    │   │       └─ 更新 invite_info 统计
    │   └─ 如果没有 → 跳过
    └─ Step 5: 日志记录(clawdbot_payment_success)
```

### IM 配置完整数据流(saveIMConfig 接口)

```
前端提交 IM 配置
    ↓
POST /api/engine/clawdbot/saveIMConfig
    ├─ Step 1: 验证必填字段(im_type、app_id、app_secret)
    ├─ Step 2: 飞书配置验证(如果 im_type='feishu')
    │   ├─ 调用 verify_feishu_credentials(app_id, app_secret)
    │   ├─ POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal
    │   ├─ 验证成功 → 继续
    │   └─ 验证失败 → 返回错误 "App ID或secret错误,请核实!"
    ├─ Step 3: 查询用户所有现有配置
    │   └─ db.clawdbot_im_config.find({'username': username})
    ├─ Step 4: 检查是否已有云服务器
    │   ├─ 如果有 → existing_server_id = configs[0]['server_id']
    │   └─ 如果没有 → existing_server_id = None
    ├─ Step 5: 构建完整配置数组
    │   ├─ 包含所有现有渠道的配置
    │   └─ 加上当前要保存的配置
    ├─ Step 6: 调用 Lighthouse 服务
    │   ├─ POST {LIGHTHOUSE_URL}/api/instances/allocate-reset
    │   ├─ 请求体:
    │   │   ├─ teamoUserId: username
    │   │   ├─ serverId: existing_server_id(如有)
    │   │   ├─ feishuAppId: app_id
    │   │   ├─ feishuSecret: app_secret
    │   │   ├─ defaultModel: default_model
    │   │   └─ env: model_env
    │   └─ 响应: serverId, instanceId, publicIp, ...
    ├─ Step 7: 保存/更新 MongoDB
    │   ├─ 如果返回的 serverId 与原有不同 → 更新所有配置的 server_id
    │   └─ upsert 当前渠道配置到 clawdbot_im_config
    ├─ Step 8: 更新用户状态
    │   └─ user.clawdbot_config_completed = True
    └─ Step 9: 返回成功响应
```

### 邀请拉新数据流(活动 d - 0元认领)

**注册阶段**:
```
新用户注册(invite_event_name='d')
    ↓
插入 invite_reward(event='register_clawdbot_d')
    ├─ register_from: 邀请人 username
    ├─ register_username: 被邀请人 username
    ├─ event: 'register_clawdbot_d'
    └─ time: 注册时间戳
    ↓
更新 invite_info 统计
    └─ total_invite_d_users += 1
```

**奖励触发(方式 1:点击分享)**:
```
用户调用 /userLog(page='clawdbot', event='click_free_share')
    ↓
验证条件
    ├─ 用户通过活动 d 注册?
    ├─ 用户有邀请人?
    ├─ 用户未触发过奖励?(Redis 检查)
    └─ 全部通过 → 继续
    ↓
发放奖励
    ├─ 邀请人实例延长 3 天
    │   └─ user.clawdbot_vip_expire_time += 86400 × 3
    ├─ 插入 invite_reward(event='clawdbot_free_share_d')
    ├─ 更新 invite_info 统计
    │   ├─ total_clawdbot_d_days += 3
    │   └─ total_clawdbot_d_count += 1
    └─ 设置 Redis 防重复标记
        └─ clawdbot_free_share_rewarded::{username} = 1(365 天)
```

**奖励触发(方式 2:首笔支付)**:
```
被邀请人首笔 ClawdBot 付款
    ↓
rebate_invite_clawdbot_d() 检查
    ├─ 是否已通过分享触发奖励?
    │   └─ 查询 invite_reward(event='clawdbot_free_share_d')
    ├─ 如果已触发 → 跳过
    └─ 如果未触发 → 发放奖励
        ├─ 邀请人实例延长 3 天
        ├─ 插入 invite_reward(event='clawdbot_purchase_d')
        └─ 更新 invite_info 统计
```

**互斥关系**:
- 分享奖励优先:如果用户已通过分享触发,支付时不再触发
- 单个用户只能触发一次奖励(3 天)

### 系统版本更新流程

```
开发者发布新版本
    ↓
更新 clawdbot_versions 集合
    ├─ 新版本: is_latest=True
    └─ 旧版本: is_latest=False
    ↓
用户查询最新版本
    ↓
GET /api/engine/clawdbot/getSystemVersion
    ├─ 查询用户当前版本(从 im_config 读取)
    ├─ 查询最新版本(is_latest=True)
    └─ 返回: current_version, latest_version, has_update
    ↓
用户触发更新
    ↓
POST /api/engine/clawdbot/restartWithLatestConfig
    ├─ Step 1: 查询所有 IM 配置
    ├─ Step 2: 飞书配置验证(如果有)⭐️
    ├─ Step 3: 调用 Lighthouse 重启服务
    │   └─ POST /api/instances/reconfigure
    ├─ Step 4: 更新用户版本记录
    │   ├─ 查询最新版本
    │   └─ update_many({'username': username}, {'$set': {'system_version': latest_version}})
    ├─ Step 5: 日志记录(clawdbot_system_version_updated)
    └─ Step 6: 返回成功
```

### Bot API 调用流程

**单轮对话**:
```
Bot 调用 /api/bot/askAgents
    ├─ Authorization: Bearer sk-abc123...
    ├─ 请求: {"query": "请分析这个 PDF"}
    ↓
get_bot_user() 认证
    ├─ 提取 API Key
    ├─ 计算 SHA256 哈希
    ├─ 查询 bot_api_keys(验证有效性)
    ├─ 更新 last_used_time
    └─ 返回绑定的 User 对象
    ↓
生成任务
    ├─ session_group_id = UUID()
    ├─ question_id = UUID()
    ├─ conv_id = UUID()
    ├─ turn = 0
    └─ 调用 askAgents 逻辑
    ↓
返回响应
    └─ {"task_id": "qid_xxx", "session_group_id": "sgid_xxx", "turn": 0}
```

**轮询结果**:
```
Bot 调用 /api/bot/checkTask
    ├─ Authorization: Bearer sk-abc123...
    ├─ 请求: {"task_id": "qid_xxx"}
    ↓
get_bot_user() 认证
    └─ 验证 API Key
    ↓
查询任务状态
    ├─ 查询 question_history(question_id)
    ├─ 映射状态:
    │   ├─ STREAMING/working → running
    │   ├─ USER_STOP/cancelled → stopped
    │   ├─ BATTERY_LIMIT/PARALLEL_LIMIT → limit
    │   └─ SUCCESS/FAIL/completed → completed
    └─ 如果 completed → 提取最后一个 mcp_assistant 的 answer + 文档
    ↓
返回响应
    └─ {"state": "running"} 或 {"state": "completed", "result": {...}}
```

**多轮对话**:
```
Bot 第二轮调用 /api/bot/askAgents
    ├─ 请求: {"query": "详细说明第二个问题", "session_group_id": "sgid_xxx"}
    ↓
查询 turn
    ├─ 查询 question_history(session_group_id)
    ├─ 计算 max(turn) + 1
    └─ turn = 1
    ↓
生成任务
    ├─ 复用 session_group_id
    ├─ 新的 question_id
    ├─ 新的 conv_id
    └─ turn = 1
    ↓
返回响应
    └─ {"task_id": "qid_yyy", "session_group_id": "sgid_xxx", "turn": 1}
```

---

## 相关文档

- 根目录规范:`AGENTS.md`(根目录)
- 技术文档:ClawdBot 技术设计文档
- 脚本文档:
  - `scripts/init_clawdbot_versions.py` - 版本管理脚本
  - `scripts/create_bot_api_key.py` - Bot API Key 创建脚本
  - `scripts/create_bot_api_keys_indexes.py` - 索引创建脚本
