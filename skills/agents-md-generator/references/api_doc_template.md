# API Documentation Template

Standard format for documenting API interfaces in AGENTS.md.

## Complete Interface Template

```markdown
#### POST /api/module/endpoint

**功能**: 简短功能描述(中文)

**请求模型**: `RequestModelName`
- `field1`: type(必需/可选) - 字段描述
- `field2`: type(必需/可选) - 字段描述,约束条件
- `field3`: type(可选,默认值) - 字段描述

**响应模型**: `ResponseModelName`
- `result_field1`: type - 字段描述
- `result_field2`: type - 字段描述

**认证**: 需要登录(`get_current_user`) / 使用 API Key(`get_bot_user`)

**业务逻辑**:
1. Step 1 描述
2. Step 2 描述
3. Step 3 描述

**请求示例**:
\`\`\`json
{
  "field1": "value1",
  "field2": 123,
  "field3": true
}
\`\`\`

**响应示例**:
\`\`\`json
{
  "code": 0,
  "result": {
    "result_field1": "value",
    "result_field2": 456
  }
}
\`\`\`

**错误响应**:
\`\`\`json
{
  "code": 405,
  "result": {
    "message": "错误描述"
  }
}
\`\`\`
```

## Field Documentation Standards

### Type Notation
- `str` - String
- `int` - Integer
- `float` - Floating point number
- `bool` - Boolean
- `List[type]` - Array of type
- `dict` - Object/Dictionary
- `ObjectId` - MongoDB ObjectId

### Required/Optional Notation
- `field: str(必需)` - Required field
- `field: str(可选)` - Optional field
- `field: str(可选,默认值 "default")` - Optional with default

### Constraint Documentation
- Value ranges: `age: int(1-120)`
- String length: `name: str(max 255 characters)`
- Enum values: `status: str('pending'|'active'|'completed')`
- Format: `email: str(valid email format)`

## Interface Group Organization

Group related interfaces together:

```markdown
### 用户管理接口

#### POST /api/users/create
...

#### GET /api/users/list
...

#### DELETE /api/users/{user_id}
...

### 认证接口

#### POST /api/auth/login
...

#### POST /api/auth/logout
...
```

## Special Cases

### File Upload Interfaces
```markdown
**请求**:
- Content-Type: multipart/form-data
- Fields:
  - `file`: File(必需) - 上传的文件
  - `metadata`: JSON string(可选) - 文件元数据
```

### Streaming Interfaces
```markdown
**响应**:
- Content-Type: text/event-stream
- Events:
  - `status`: 状态更新
  - `data`: 数据片段
  - `done`: 完成信号
```

### Pagination Interfaces
```markdown
**请求模型**:
- `limit`: int(可选,默认 20) - 每页数量
- `offset`: int(可选,默认 0) - 偏移量

**响应模型**:
- `items`: List[ItemModel] - 结果列表
- `total`: int - 总数量
- `has_more`: bool - 是否还有更多
```
