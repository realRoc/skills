# Data Flow Diagram Template

Standard patterns for documenting data flows in AGENTS.md.

## Basic Flow Pattern

```
操作触发点
    ↓
API 调用 (接口名称)
    ├─ Step 1: 验证操作 (描述)
    ├─ Step 2: 数据库操作 (描述)
    ├─ Step 3: 业务逻辑 (描述)
    └─ Step 4: 返回响应
```

## Complex Multi-Stage Flow

```
用户发起操作
    ↓
POST /api/module/action
    ├─ Step 1: 参数验证
    │   ├─ 验证必填字段
    │   └─ 验证字段格式
    ├─ Step 2: 权限检查
    │   ├─ 验证用户登录状态
    │   └─ 验证操作权限
    ├─ Step 3: 数据库查询
    │   ├─ 查询现有数据
    │   └─ 验证数据存在性
    ├─ Step 4: 业务逻辑处理
    │   ├─ 计算派生数据
    │   └─ 更新状态
    ├─ Step 5: 外部服务调用
    │   ├─ 调用外部 API
    │   └─ 处理外部响应
    ├─ Step 6: 数据库更新
    │   ├─ 更新主表
    │   └─ 更新关联表
    └─ Step 7: 返回响应
```

## Conditional Flow Pattern

```
用户操作
    ↓
API 调用
    ├─ Step 1: 检查条件 A
    │   ├─ 如果满足 → 路径 A
    │   │   ├─ 操作 A1
    │   │   └─ 操作 A2
    │   └─ 如果不满足 → 路径 B
    │       ├─ 操作 B1
    │       └─ 操作 B2
    ├─ Step 2: 检查条件 B
    │   ├─ 如果满足 → 继续处理
    │   └─ 如果不满足 → 返回错误
    └─ Step 3: 返回响应
```

## Parallel Operations Flow

```
用户操作
    ↓
API 调用
    ├─ 并行操作 1: 数据库查询
    │   └─ 结果 A
    ├─ 并行操作 2: 缓存查询
    │   └─ 结果 B
    ├─ 并行操作 3: 外部 API 调用
    │   └─ 结果 C
    ↓
等待所有操作完成
    ↓
合并结果 (A + B + C)
    ↓
返回响应
```

## Payment Flow Example

```
用户发起支付请求
    ↓
POST /api/pay
    ├─ Step 1: 生成订单
    │   ├─ orders 集合
    │   │   ├─ order_id
    │   │   ├─ amount
    │   │   └─ status: 'pending'
    │   └─ 返回 order_id
    ├─ Step 2: 调用支付宝 API
    │   ├─ 创建支付链接
    │   └─ 返回 pay_url
    └─ Step 3: 返回支付链接给前端
    ↓
用户完成支付
    ↓
支付宝回调 POST /callback
    ├─ Step 1: 验证签名
    ├─ Step 2: 更新订单状态
    │   └─ orders.status = 'paid'
    ├─ Step 3: 更新用户余额/权限
    │   ├─ Redis: 实时扣费
    │   └─ MongoDB: 持久化
    ├─ Step 4: 触发奖励机制 (如有)
    │   ├─ 检查邀请关系
    │   └─ 发放邀请奖励
    └─ Step 5: 日志记录
```

## Multi-Round Interaction Flow

```
第一轮对话
    ↓
POST /api/ask
    ├─ session_id = UUID()
    ├─ turn = 0
    └─ 返回 session_id
    ↓
处理中...
    ↓
查询结果
    ↓
第二轮对话 (追问)
    ↓
POST /api/ask
    ├─ 复用 session_id
    ├─ turn = 1
    └─ 返回新 task_id
    ↓
处理中...
```

## Integration with External Service

```
用户操作
    ↓
API 调用
    ├─ Step 1: 准备请求数据
    │   ├─ 构建 payload
    │   └─ 添加认证信息
    ├─ Step 2: 调用外部服务
    │   ├─ POST https://external-api.com/endpoint
    │   ├─ 超时: 30 秒
    │   └─ 重试: 3 次
    ├─ Step 3: 处理外部响应
    │   ├─ 成功 → 解析数据
    │   └─ 失败 → 错误处理
    ├─ Step 4: 保存结果到数据库
    │   ├─ MongoDB: 业务数据
    │   └─ Redis: 缓存结果
    └─ Step 5: 返回响应
```

## Best Practices

1. **Clear Stages**: Use numbered steps for sequential operations
2. **Indentation**: Show hierarchy with consistent indentation (4 spaces)
3. **Branching**: Use `├─` for branches, `└─` for last item
4. **Chinese Labels**: Use Chinese for operation descriptions
5. **Technical Terms**: Use English for technical terms (API, Redis, MongoDB)
6. **Completeness**: Include all major steps, don't skip error handling
7. **Concrete Data**: Reference actual collection names, field names, values

## When to Create Data Flows

Create data flow diagrams for:
- **Complex business processes** (payment, invitation, subscription)
- **Multi-step workflows** (config sync, version update, migration)
- **Cross-system integrations** (external API calls, webhooks)
- **Multi-round interactions** (conversational AI, state management)
- **Conditional logic** (different paths based on conditions)

Skip data flows for:
- Simple CRUD operations (unless they have complex validation)
- Single-step operations
- Straightforward queries
