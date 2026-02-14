#!/bin/bash
set -e

# 配置
LOCAL_SKILLS_DIR="$HOME/.claude/skills"
REPO_SKILLS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/skills"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔍 Detecting changes between local and repository skills...${NC}\n"

# 存储结果
NEW_SKILLS=()
MODIFIED_SKILLS=()
UNCHANGED_SKILLS=()

# 遍历本地 skills
for local_skill in "$LOCAL_SKILLS_DIR"/*; do
  # 跳过非目录和符号链接
  if [[ ! -d "$local_skill" ]] || [[ -L "$local_skill" ]]; then
    continue
  fi

  skill_name=$(basename "$local_skill")
  repo_skill="$REPO_SKILLS_DIR/$skill_name"

  # 检查是否为新 skill
  if [[ ! -d "$repo_skill" ]]; then
    NEW_SKILLS+=("$skill_name")
    echo -e "${GREEN}✨ NEW: $skill_name${NC}"
  else
    # 检查是否有修改
    if ! diff -qr "$local_skill" "$repo_skill" > /dev/null 2>&1; then
      MODIFIED_SKILLS+=("$skill_name")
      echo -e "${YELLOW}📝 MODIFIED: $skill_name${NC}"
      # 显示详细差异
      echo "   Changes:"
      diff -rq "$local_skill" "$repo_skill" | sed 's/^/   /'
    else
      UNCHANGED_SKILLS+=("$skill_name")
    fi
  fi
done

# 输出汇总
echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}New skills: ${#NEW_SKILLS[@]}${NC}"
for skill in "${NEW_SKILLS[@]}"; do echo "  • $skill"; done

echo -e "${YELLOW}Modified skills: ${#MODIFIED_SKILLS[@]}${NC}"
for skill in "${MODIFIED_SKILLS[@]}"; do echo "  • $skill"; done

echo -e "Unchanged skills: ${#UNCHANGED_SKILLS[@]}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

# 导出变量供其他脚本使用
export NEW_SKILLS_LIST="${NEW_SKILLS[*]}"
export MODIFIED_SKILLS_LIST="${MODIFIED_SKILLS[*]}"
