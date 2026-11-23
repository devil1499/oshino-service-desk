# 第十三部分：LangGraph 知识库问答 Agent

目标：用户可以围绕已发布知识连续提问；系统查资料、必要时追问或补查一次，给出可追溯的回答。先完成第六部分的知识检索与第七部分的模型调用，再学习本部分。

本目录保留可单独运行的流程练习；正式工程已接入 `backend/app/modules/qa/`、`frontend/src/views/KnowledgeChatView.vue` 和 PostgreSQL 会话表。练习测试使用模拟资料，不会调用付费接口；正式工程的自动化测试也使用模拟模型，但会执行实际数据库和知识索引路径。真实模型效果仍要按验收清单单独验证。

| 阅读顺序 | 文件 | 做什么 |
|---|---|---|
| 1 | [主教程](13-知识库问答Agent.md) | 理解范围、数据流和跟写顺序 |
| 2 | [流程代码](qa_graph.py) | 完整的 LangGraph 节点、分支、引用校验 |
| 3 | [逐文件讲解与接入](14-逐文件讲解与业务接入.md) | 区分固定语法与可改内容，跟写正式工程的模型、检索、会话、页面 |
| 4 | [测试代码](test_qa_graph.py) | 验证正常回答、追问、次数限制、错误和引用 |
| 5 | [人工验收](15-验收清单.md) | 验证真实模型、资料、权限和刷新恢复 |

## 先运行流程练习

在 WSL 中单独创建学习环境，避免改变正式项目依赖：

```bash
cd /mnt/e/oshino
python3 -m venv /tmp/oshino-qa-study
source /tmp/oshino-qa-study/bin/activate
python -m pip install -r docs/01-教程/13-知识库问答Agent/requirements.txt
cd docs/01-教程/13-知识库问答Agent
python -m unittest -v test_qa_graph
```

预期运行 8 项测试。环境中的 Python 需为 3.12；`/tmp` 环境用于学习，重启清理后可重建。正式后端依赖已包含 `langgraph==1.2.16`。

## 正式工程从哪里看

1. 打开 `backend/app/modules/qa/graph.py`：每次提问如何决定追问、检索、补查或回答。
2. 打开 `backend/app/modules/qa/adapters.py`：如何连接已有聊天模型、Embedding 和知识索引。
3. 打开 `backend/app/modules/qa/service.py`：如何保存会话、限制并发、记录失败和复核引用。
4. 打开 `backend/app/modules/qa/router.py`：四个登录后才能使用的问答接口。
5. 打开 `frontend/src/views/KnowledgeChatView.vue`：新建会话、提问、查看出处及刷新恢复。

页面入口在侧边栏“工单管理”上方，名称为“智能助手”。先在知识库发布文档并重建知识索引，再在页面选择同一产品创建会话。配置 `backend/.env.chat` 与 `backend/.env.retrieval` 后才能运行真实问答；不要把密钥写入教程或 Git。

不要在业务页面显示测试中的“检查角色绑定”作为固定回答。它只是测试样本。

相关学习：[知识库切分、清洗与向量化速查](../06-08-知识库与AI建议/19-知识库切分清洗与向量化速查.md)。
