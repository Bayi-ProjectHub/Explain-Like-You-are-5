# 讲解师 Explain Like You're 5

通过 *选术语、难度、语言 -> 用户自主研究 -> 用户录制讲解 -> AI分析并给出反馈建议*，在扩展用户知识面的同时，帮助用户在多语言的情境下，提升短时间内自主学习能力，以及表达和演讲能力。

Given a term in a field, the user is required to conduct research on their own, and explain the term in front of camera. This system would analyse the record and offer feedback based on thats.
In this process, while expanding and deepening users' knowledge, it would effectively improve user's ability on self learning, expressing and presenting under multiple languages.

## Devloping

具体开发请查看 docs/DEVELOPMENT.md

### 初次 clone
1. 安装 uv 环境管理器 (ask GPT)，之后运行所有代码都通过 uv
2. 在该项目的终端中运行 `uv sync` 拉取 dependencies
3. 开始开发吧!!

### 修改与提交
- 切换到你的工作分支，或新建一个分支
    ```bash 
    git switch video # 切换至已存在的分支
    git switch -c my-new-branch # 新建分支
    ```

- 更改后，在本地测试后，提交：
    ```bash
    git add .
    git commit -m "简短描述改动了什么"
    git push # 如果是新分支，git push -u origin my-new-branch
    ```