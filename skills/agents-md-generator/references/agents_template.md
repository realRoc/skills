# AGENTS.MD Template Structure

This template provides the standard structure for AGENTS.md documentation files.

## Root-Level AGENTS.MD Structure

```markdown
# AI 智能体开发指南

本文档为 AI 提供在 <项目名称> 项目中开发新功能的完整指南。

---

## ⭐️⭐️⭐️ 核心规定:Spec 自动沉淀机制

**【永不删除、替换或遗忘的规定】**

### 1. 自动化原则

在本项目开发中,当用户提供任何开发规范(Spec),AI 必须**主动自动化**地更新到 AGENTS.md,**无需询问用户**。

### 2. 强制通知格式

每次修改 AGENTS.md 后,必须在回复尾部单独一行输出(前后空行):
\`\`\`
喵 ฅ՞•ﻌ•՞ฅ 已完成xxx相关的spec,更新/删除AGENTS.md文件中相关内容。
\`\`\`

### 3. 强制 Git 提交原则(有喵必有汪)

### 4. Spec 定义

### 5. 模块级 Spec 规范(层级化管理)

---

## 项目定位

**项目别名**:
**核心定位**:
**主要职责**:
**不是什么**:

---

## 系统架构理解

### 核心架构模式
### 三层数据存储
### 关键设计模式
### 模块组织

---

## 开发新功能的完整流程

---

## 关键概念和数据流

---

## 系统架构和技术细节

---

## 常见开发场景

**注意**:模块级的开发场景已拆分到各子模块的 AGENTS.md 中:

- **模块 A**:`path/to/module_a/AGENTS.md`
- **模块 B**:`path/to/module_b/AGENTS.md`

---

## 开发最佳实践

---

## 相关文档
```

## Module-Level AGENTS.MD Structure

```markdown
# <模块名称> 模块规范与接口文档

> **继承自**: [根目录 AGENTS.md](../../AGENTS.md)

本文档为 AI 提供在 <模块名称> 模块中开发新功能的完整指南,包含业务规范和完整的 API 接口文档。

---

## 模块定位

**职责**:
**主要功能**:
**核心集合**:

---

## 业务规范

### 规范 1 ⭐️

**背景**:
**核心原则**:
**实现流程**:

### 规范 2 ⭐️

---

## API 接口规范

### 接口总览表

| 接口组 | 接口数量 | 说明 |
|--------|---------|-----|
| 组 1 | N | 描述 |
| 组 2 | M | 描述 |

**总计**: X 个接口

---

### 接口组 1

#### POST /api/path/endpoint

**功能**:
**请求模型**:
**响应模型**:
**认证**:
**业务逻辑**:
**请求示例**:
**响应示例**:
**错误响应**:

---

## 数据模型

### MongoDB 集合

#### collection_name(用途)

\`\`\`python
{
    '_id': ObjectId,
    'field1': type,  # 描述
    'field2': type,  # 描述
}
\`\`\`

**索引**:
- `field1` 单字段索引
- `field1 + field2` 复合索引

### Redis 键设计

| Key 模式 | 用途 | TTL |
|---------|------|-----|
| `pattern::{id}` | 用途 | 时长 |

---

## 外部集成

### 外部服务 A

**Base URL**:
**API 端点**:
**请求格式示例**:
**响应格式**:
**超时设置**:

---

## 完整数据流图

### 流程 A 完整数据流

\`\`\`
用户操作
    ↓
API 调用
    ├─ Step 1:
    ├─ Step 2:
    └─ Step 3:
\`\`\`

---

## 相关文档

- 根目录规范:`AGENTS.md`(根目录)
- 技术文档:
- 脚本文档:
```

## Content Guidelines

### Language
- **Labels**: Chinese (接口、功能、请求体、响应体)
- **Technical Terms**: English (FastAPI, MongoDB, Redis, JWT)
- **Code**: English variable names and comments

### Completeness
- Every API interface must have request/response models
- Every data model must have field descriptions
- Every complex process must have data flow diagram
- Every external integration must have auth and timeout info

### Examples
- Provide concrete JSON examples for all requests/responses
- Use realistic data in examples
- Show both success and error cases
