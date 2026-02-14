# API Documentation Template

This template defines the standard structure for backend API documentation in AGENTS.md.

## Document Structure

```markdown
# Backend API Specification

> **Inherits from**: [Root AGENTS.md](../AGENTS.md)

## 目录

- [1. Module Name](#1-module-name)
- [2. Module Name](#2-module-name)
...

## 1. Module Name

Base路径: `/api/v1/module`

### 1.1 Endpoint Name

**接口**: `METHOD /path`

**描述**: Brief description of what this endpoint does

**请求头**:
```
Authorization: Bearer {token}
```
or
```
X-API-Key: {api_key}
```

**请求体**:
```json
{
  "field1": "value",
  "field2": 123
}
```

**请求字段说明**:
- `field1` (type, required/optional): Description
- `field2` (type, required/optional): Description

**响应体**:
```json
{
  "success": true,
  "code": "SUCCESS",
  "message": "操作成功",
  "data": {
    "field": "value"
  }
}
```

**响应字段说明**:
- `field` (type): Description

**错误响应** (status_code):
```json
{
  "success": false,
  "code": "ERROR_CODE",
  "message": "错误信息",
  "data": null
}
```

**权限要求**: Authentication requirements

**业务规则**:
- Rule 1
- Rule 2

---

## 附录A: 统一响应格式

All API endpoints follow unified response format:

```json
{
  "success": bool,
  "code": string,
  "message": string,
  "data": any | null
}
```

### Standard Business Codes

| Code | Meaning | HTTP Status |
|------|---------|-------------|
| `SUCCESS` | Success | 200 |
| `INVALID_INPUT` | Invalid input | 400 |
| `UNAUTHORIZED` | Unauthorized | 401 |
...

## 附录B: 国际化支持

Request headers for locale:
- `Accept-Language: zh-CN` or `en-US`
- `locale: zh` or `en`

## 附录C: 认证方式

### 1. JWT Token (Human Users)
```
Authorization: Bearer {access_token}
```

### 2. API Key (Agents)
```
X-API-Key: {api_key}
```
```

## Field Descriptions Format

Always include:
1. Field name
2. Type (string, int, float, bool, array, object, nullable)
3. Required/Optional status
4. Description with constraints (min/max length, range, format)
5. Example values when helpful

Example:
- `email` (string, optional): User email address, must be valid email format, max 255 characters
- `amount` (float, required): Payment amount, must be > 0, max 100000
- `status` (string, required): Task status, one of: published/in_progress/completed/expired
