# Claude Session Manager

[English](./README.md) | **中文**

一个用于管理 Claude Code 会话的 skill：列出会话并查看元数据，或按条件清理无用会话。单个 skill，两个子命令——`list` 和 `clean`。

## 安装

```bash
cp -r sessions ~/.claude/skills/
```

然后在 Claude Code 里：

```
/sessions                    # 列出会话（默认）
/sessions list               # 显式写 list
/sessions clean              # 清理（默认 empty 模式）
```

## 过滤器语法（`list` 和 `clean` 共用）

多个过滤器之间取交集（AND），顺序无关。

| 过滤器 | 含义 |
|---|---|
| `unnamed` | 没改过名字的会话（没用过 `/rename`）。 |
| `size>10MB` / `size<100KB` / `size>=1G` / `size<=50k` | 按会话总大小比较（jsonl + 子目录）。单位后缀可选、大小写不敏感：`B` / `K` / `KB` / `M` / `MB` / `G` / `GB`。无后缀 = 字节。 |
| `age>30d` / `age<7d` / `age>=1w` / `age<=1m` | 距离最后活跃时间。单位：`h` 小时、`d` 天、`w` 周、`m` 月（30 天）。 |

脚本会在做任何事之前检查下列情况：

- **过滤器格式错误** —— 例如 `size>10xyz` → 提示有效单位
- **不可能的区间** —— 例如 `size>10MB size<1MB` → 指出矛盾
- **`clean` 模式混用** —— 例如 `clean empty 0fa7` → 解释规则

## `/sessions list [过滤器...] [--project SUBSTR]`

列出会话，可选过滤。

```
/sessions                              # 全部会话
/sessions unnamed                      # 只看未命名
/sessions size>10M age>30d             # 又大又老
/sessions list size<100K               # 小的会话（开头的 `list` 可选）
/sessions --project myapp              # cwd 包含 "myapp"
/sessions unnamed size>1M --project myapp
```

输出：一个 Markdown 表格，字段包括名字、ID（前 8 位）、项目、最后活跃时间、大小、消息数。约定：

- 当前项目：项目名前加 `>`
- 当前会话：名字后加 `(current)`
- 已命名的会话：名字前加 `*`

表格之后是汇总行：N 个会话共 X，其中 M 个已命名，K 个未命名。

## `/sessions clean [参数...]`

删除会话。三种互斥模式——脚本从参数自动识别，不允许混用。

### 1. Empty 模式（默认）

无参数，或仅 `empty`。删除未命名且 ≤ 10KB 的会话。清理中断的空会话的安全默认值。

```
/sessions clean
/sessions clean empty
```

### 2. 目标模式

一个或多个会话 ID 或名字（空格分隔）。多个目标之间取并集（OR）。

每个 query 的匹配优先级：

1. **ID 前缀** —— 例如 `0fa7` 匹配 `0fa78bf1-...`
2. **名字精确匹配**（大小写不敏感）
3. **名字子串匹配**（大小写不敏感）

如果一个 query 匹配多个会话，Claude 会让你挑选要删哪些。

```
/sessions clean 0fa7
/sessions clean my-debug abc12345 another-name
```

### 3. 过滤器模式

`unnamed`、`size{op}N`、`age{op}N` 的任意组合，全部取交集。

```
/sessions clean unnamed
/sessions clean unnamed size>10MB age>30d
/sessions clean size>1MB size<100MB              # 用两个边界做区间查询
/sessions clean age>30d unnamed                  # 顺序无关
```

## 安全措施

- 每次删除都会通过 `AskUserQuestion` 显示完整清单和总大小，必须明确确认。
- **当前会话**永远从候选里排除（通过 `cwd` + 最后活跃时间识别）。
- 含糊的目标会触发多选确认。

## 会删除什么

每个会话只动两个路径：

- `~/.claude/projects/<project-dir>/<session-id>.jsonl` —— 对话日志
- `~/.claude/projects/<project-dir>/<session-id>/` —— UUID 子目录（planner 状态、todos 等），若存在

**不会动**：

- `~/.claude/projects/<project-dir>/memory/` —— 项目级 memory（`MEMORY.md` 和它引用的 `.md` 文件）完整保留。**删 session 不会丢 memory。**
- 同一项目下其他会话 —— 每个会话都是独立的 `<uuid>.jsonl` + `<uuid>/` 组合。

## 运行环境

- Python 3.13+
- Claude Code CLI

## 许可证

MIT
