---
name: agents-md-generator
description: Generate comprehensive AGENTS.md documentation for backend projects with complete API specifications, business rules, data models, and data flows. Use when (1) Creating AGENTS.md from existing CLAUDE.md, (2) Documenting backend API modules with FastAPI routes, (3) Migrating documentation to AGENTS.md/CLAUDE.md symlink structure, (4) Adding complete API interface documentation to existing specs, (5) Creating module-level AGENTS.md for specific features (mcp, teamo_code, file_system, etc.)
---

# AGENTS.MD Generator

Generate comprehensive AGENTS.md documentation for backend projects following the AGENTS.md/CLAUDE.md symlink pattern.

## Core Workflow

### 1. Understand the Scope

Ask the user to clarify:
- **Target module**: Root directory, specific module (mcp, teamo_code, etc.), or multiple modules
- **Source materials**: Existing CLAUDE.md, API route files, technical design docs
- **API count**: How many interfaces need documentation (affects detail level)
- **Content to preserve**: Existing business rules, specs, or guidelines to keep
- **Content to remove**: Deprecated features, unused patterns (e.g., Ralph Loop)

### 2. Read Source Materials

Read all relevant source files:
- Existing CLAUDE.md or AGENTS.md (if exists)
- API route files (e.g., `clawdbot.py`, `router.py`)
- Related business spec documents
- Data model definitions

Use Read tool to load files into context. For large codebases, use Grep to find specific patterns first.

### 3. Generate AGENTS.md Content

Follow the template structure in `references/agents_template.md`:

**Required Sections**:
1. **Module Overview** - Responsibilities, main features, core collections
2. **Business Specifications** - Domain-specific rules, workflows, special mechanisms
3. **API Interface Documentation** - Complete interface specs (see `references/api_doc_template.md`)
4. **Data Models** - MongoDB collections, PostgreSQL tables, Redis keys
5. **External Integrations** - Third-party APIs, external services
6. **Complete Data Flows** - End-to-end process diagrams (see `references/data_flow_template.md`)

**Content Priorities**:
- **Completeness over brevity**: Include all interfaces, all fields, all business rules
- **Accuracy over idealism**: Document actual behavior, not desired behavior
- **Concrete examples**: Provide JSON request/response samples for every interface
- **Chinese + English**: Chinese labels (接口、功能、请求体) with English technical terms

### 4. Create Symlink Structure

After creating AGENTS.md:

1. **Backup**: `cp CLAUDE.md CLAUDE.md.backup`
2. **Delete**: `rm CLAUDE.md`
3. **Symlink**: `ln -s AGENTS.md CLAUDE.md`
4. **Verify**: `ls -la CLAUDE.md` should show `CLAUDE.md -> AGENTS.md`

Use the Bash tool for these operations.

### 5. Validate and Test

**Structure Validation**:
- ✅ YAML frontmatter removed (AGENTS.md uses standard Markdown)
- ✅ All code blocks properly fenced with language tags
- ✅ All tables properly formatted
- ✅ All internal links work (e.g., `[Section](#section)`)

**Content Validation**:
- ✅ Every API interface has request/response models
- ✅ Every data model has field descriptions and indexes
- ✅ Every external integration has API endpoints and auth
- ✅ Every data flow has clear start and end points

**Symlink Validation**:
```bash
# Verify symlink
ls -la CLAUDE.md

# Verify content match
diff CLAUDE.md AGENTS.md
# Expected: No output (files are identical via symlink)
```

### 6. Git Commit

Follow the project's Git commit standards:

```bash
git add AGENTS.md CLAUDE.md CLAUDE.md.backup
git commit -m "docs: 创建 <模块名称> AGENTS.md 并设置 CLAUDE.md 软链接

- 创建 AGENTS.md (完整的模块规范文档)
- 包含 <X> 个接口的完整文档
- 包含业务规范 (<业务规范名称>)
- 包含数据模型和外部集成说明
- 创建软链接 CLAUDE.md -> AGENTS.md
- 备份原 CLAUDE.md 为 CLAUDE.md.backup

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

## API Documentation Standards

### Interface Template

For each API interface, document:

**Basic Info**:
- HTTP method and path
- Functionality description (Chinese)
- Authentication requirements

**Request**:
- Request model name and fields
- Field types, constraints, required/optional
- Request example (JSON)

**Response**:
- Response model name and fields
- Field types and descriptions
- Success response example (JSON)
- Error response examples (JSON)

**Business Logic** (if complex):
- Step-by-step flow
- Validation rules
- Side effects

See `references/api_doc_template.md` for detailed examples.

## Data Flow Documentation

Use ASCII diagrams with clear stages:

```
用户操作
    ↓
API 调用 (接口名称)
    ├─ Step 1: 验证 (描述)
    ├─ Step 2: 数据库操作 (描述)
    │   ├─ 查询 xxx
    │   └─ 更新 yyy
    ├─ Step 3: 外部服务调用 (描述)
    └─ Step 4: 返回响应
```

For complex flows, break into multiple sub-diagrams. See `references/data_flow_template.md` for examples.

## Best Practices

### Progressive Disclosure

**Root AGENTS.md**: Global specs, cross-module patterns, project overview
**Module AGENTS.md**: Module-specific specs, API docs, detailed flows

Reference module docs from root:
```markdown
请参考对应模块的文档获取详细的开发指南:
- **MCP 模块**: `wowchat/mcp/AGENTS.md`
- **Teamo Code 模块**: `wowchat/teamo_code/AGENTS.md`
```

### Spec Auto-Deposition

Update Spec auto-deposition mechanism to use AGENTS.md:

```markdown
每次修改 AGENTS.md 后,必须在回复尾部单独一行输出(前后空行):
\`\`\`
喵 ฅ՞•ﻌ•՞ฅ 已完成xxx相关的spec,更新/删除AGENTS.md文件中相关内容。
\`\`\`
```

For module-level updates:
```markdown
喵 ฅ՞•ﻌ•՞ฅ 已完成xxx相关的spec,更新/删除<模块路径>/AGENTS.md文件中相关内容。
```

### Content Removal

When migrating from CLAUDE.md to AGENTS.md, remove:
- ❌ Deprecated features (e.g., Ralph Loop if not used)
- ❌ Experiment-only code patterns
- ❌ Duplicate specifications across files

Preserve:
- ✅ All core business rules
- ✅ All active API specifications
- ✅ All data model definitions
- ✅ All integration patterns

## Common Patterns

### Multi-Module Documentation

For projects with multiple modules, create hierarchy:

```
/AGENTS.md (root - global specs)
/CLAUDE.md -> AGENTS.md (symlink)

/wowchat/mcp/AGENTS.md (module specs)
/wowchat/mcp/CLAUDE.md -> AGENTS.md (symlink)

/wowchat/teamo_code/AGENTS.md (module specs)
/wowchat/teamo_code/CLAUDE.md -> AGENTS.md (symlink)
```

### API Count Guidelines

- **< 10 interfaces**: Include all details in main AGENTS.md
- **10-30 interfaces**: Group by function, use interface overview table
- **> 30 interfaces**: Consider splitting into multiple module AGENTS.md files

### External Integration Documentation

For each external service, document:
- Base URL and API endpoints table
- Authentication method (API Key, OAuth, etc.)
- Request/response format examples
- Timeout settings
- Error handling patterns

See MCP module example for Lighthouse, Feishu, Alipay integrations.

## Error Prevention

**Common Mistakes**:
- ❌ Forgetting to backup CLAUDE.md before creating symlink
- ❌ Including YAML frontmatter (only needed in SKILL.md, not AGENTS.md)
- ❌ Incomplete API documentation (missing request/response models)
- ❌ Missing data flow diagrams for complex processes
- ❌ Not testing symlinks with `ls -la`

**Validation Checklist**:
- [ ] AGENTS.md created with all required sections
- [ ] CLAUDE.md.backup exists
- [ ] CLAUDE.md symlink verified (`ls -la CLAUDE.md` shows `-> AGENTS.md`)
- [ ] `cat CLAUDE.md` shows AGENTS.md content
- [ ] All API interfaces documented
- [ ] All data models documented
- [ ] All data flows documented
- [ ] Git committed with proper message

## References

- **Template Structure**: See `references/agents_template.md`
- **API Documentation**: See `references/api_doc_template.md`
- **Data Flow Diagrams**: See `references/data_flow_template.md`
- **Complete Example**: See `assets/example_mcp_agents.md`
