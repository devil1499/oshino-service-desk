# 第五部分：Embedding 与 Milvus 混合检索

这一部分做到：打开一个工单，点击“检索相似案例”，系统返回最多五条可参考的历史工单，可以点开出处和阅读解决方案。

## 先用大白话理解流程

```text
当前工单的标题和问题
          ↓
Embedding 把文字转换成一串数字
          ↓
语义向量搜索 + 中文关键词 BM25 搜索
          ↓
RRF 把两个排名合并
          ↓
核对数据库中案例仍有效，再显示给客服
```

Embedding 负责把文字变成向量，不负责写回复。Milvus 保存向量并查找邻近内容。BM25 帮你找到产品词、错误码等词汇相近的内容。RRF 按名次合并两个检索结果，分数不是正确率。

PostgreSQL 仍保存完整工单，Milvus 是可以重建的检索副本。只有 resolved 或 closed 且有方案的工单才进入正式索引，待处理工单不会作为有效解决案例。

## 跟写顺序

1. `backend/app/core/retrieval_settings.py`：独立读取模型和向量库配置。
2. `backend/app/integrations/embeddings.py`：调用远程 Embedding 并校验响应。
3. `backend/app/integrations/case_index.py`：创建集合、写入、中文 BM25、混合查询。
4. `backend/app/modules/analysis/cases.py`：生成检索摘录和内容指纹。
5. `backend/app/rebuild_cases.py`：把现有有效案例整体写进索引。
6. `backend/app/modules/analysis/router.py`：连接工单、模型、索引和结果核对。
7. `backend/app/main.py`：登记相似案例接口。
8. 前端 analysis.ts → SimilarCases.vue → TicketDetailView.vue。

完整变化见 [文件清单](08-接口与文件变化.md)，每个文件的代码和说明见 [逐文件讲解](06-逐文件新增代码与讲解.md)。

## 当前正式工程的本地模型配置

本机已使用 Windows Ollama 的 `qwen3-embedding:0.6b`，1024 维。Docker 后端配置如下：

```dotenv
MILVUS_DB_PATH=/mnt/e/oshino/data/milvus/cases.db
MODEL_BASE_URL=http://host.docker.internal:11434/v1
MODEL_API_KEY=ollama
EMBEDDING_MODEL=qwen3-embedding:0.6b
EMBEDDING_DIMENSIONS=1024
```

`ollama` 是 SDK 要求的占位字符串，本地服务不使用它鉴权。Compose 会把 MILVUS_DB_PATH 覆盖为容器内 `/app/data/milvus/cases.db`。先打开 Ollama，再启动 Docker。预热与重建命令见[第五部分实施与验收](../../03-检查记录/2026-10-31-第五部分实施与验收.md)。

该配置用于 Docker 后端；云服务是下面的可选方案，模型名、地址与密钥要成套替换，更换模型后重新建立索引。

## 安装并填写配置

```bash
cd /mnt/e/oshino
source /mnt/e/oshino/.venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
```

本部分增加 OpenAI 兼容接口 SDK、PyMilvus、Milvus Lite 和 jieba。它们都在 WSL 虚拟环境中使用，不能用 Windows Python 运行这个 Linux 虚拟环境。

把示例 `backend/.env.retrieval.example` 的内容写进你自己的 `backend/.env.retrieval`。这是新增配置文件，保留原来的 `.env`。不要把示例文件改成保存真实密钥的文件。

```dotenv
MILVUS_DB_PATH=/mnt/e/oshino/data/milvus/cases.db
MODEL_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
MODEL_API_KEY=在本地编辑器填写你自己的密钥
EMBEDDING_MODEL=qwen3.7-text-embedding-flash
EMBEDDING_DIMENSIONS=1024
```

上面的密钥文字是说明，不能照抄当真实密钥。密钥、服务地域和地址必须匹配你的百炼账号；不要把密钥写到聊天、源码或终端命令参数里。模型名称和维度需要被你使用的服务支持。示例沿用原设计选定的模型；公开支持情况见 [百炼模型说明](https://help.aliyun.com/zh/model-studio/qwen3-7-text-embedding-flash)。

`MILVUS_DB_PATH` 必须是 WSL 绝对路径并以 `.db` 结尾。当前 Lite 版本会管理这个路径下的本地存储，不能把它当普通可编辑文本。旁边的 `cases.db.index.json` 保存构建时间、模型、维度等信息，不保存密钥。

项目的 .gitignore 已加入 `.env.retrieval` 和 `data/milvus/`，跟写时把这些规则加进你自己的 `.gitignore`，保留原有规则。

使用 Docker 时，按[第五部分实施与验收](../../03-检查记录/2026-10-31-第五部分实施与验收.md)中的命令重建；不要让 WSL 与容器同时访问同一 Milvus 文件。

## 第一次建立索引

先完成第四部分，确保有已解决工单。停止正在运行的后端，再执行：

```bash
cd /mnt/e/oshino/backend
python -m app.rebuild_cases
```

命令会读取 PostgreSQL，有效案例每十条调用一次 Embedding，再写进 Milvus。终端只显示进度，不输出密钥或工单全文。模型 API 会按服务商规则计费，先用 40 条样例验证配置。

成功后才写“索引完整”的标记。配置缺失、模型失败、维度错误等都会报错；不会用全零向量或空结果冒充成功。

以后导入新案例、修改案例内容、变更模型/地址/维度后，需要停后端并重新建立索引：

```bash
python -m app.rebuild_cases --replace
```

`--replace` 会替换 ticket_cases 派生索引，PostgreSQL 工单不受影响。构建失败后索引保持未就绪状态，修正原因后重新运行同一命令。这个学习版本使用显式全量重建，暂不自动同步每次工单变动。

Milvus Lite 的存储由单进程使用；本版本按一个 Uvicorn 工作进程运行，重建时要先停止后端。不要同时启动多个后端或重建任务访问同一文件。[Milvus Lite 官方说明](https://github.com/milvus-io/milvus-lite)

## 运行与验收

```bash
cd /mnt/e/oshino/backend
python -m uvicorn app.main:app --reload --port 8000
```

前端仍按第四部分启动。在工单详情的相似案例区域点击“检索相似案例”，检查：

1. 返回最多五条，能点开真实工单，方案来自 PostgreSQL。
2. 不出现当前工单自己，也不出现没有有效方案的待处理案例。
3. 先查同产品模块；不满五条才补同分类，页面说明是否扩大范围。
4. 缺少索引时出现“索引尚未完整建立”，不会出现成功的空列表。
5. 已索引的案例内容被修改后，再检索会跳过旧候选并提示重建。

`stale_count` 只统计本次检索遇到的失效候选，不表示整个索引的失效总量。新完成的案例不会自动出现，需重建。模型名称、端点或维度变化会被检测到；如果服务商悄悄替换同名模型，你仍需要主动重建。

## 哪些是固定，哪些能改

| 位置 | 固定写法 | 项目可以改的内容 |
|---|---|---|
| Embedding 请求 | SDK 的 embeddings.create、input、model、dimensions | 账号支持的模型、向量维度、服务地址 |
| Milvus schema | add_field、FLOAT_VECTOR、SPARSE_FLOAT_VECTOR、BM25 | 字段名可设计，但读写查询必须一起改并重建 |
| 中文分词 | analyzer_params={"tokenizer": "jieba"} 是当前已验证配置 | 分词策略变化需重新建索引 |
| 检索 | hybrid_search、AnnSearchRequest、RRFRanker 是库 API | 当前每路 20 条、RRF 的 60、最终 5 条是检索参数 |
| 页面 | defineProps、ref、v-if、v-for 是 Vue 写法 | 标题、按钮文字、样式可以改 |

当前检索摘录包含完整标题、问题前 3000 字符和方案前 3000 字符，查询只用标题和问题前 3000 字符；完整文本仍保存在数据库。这是控制检索输入大小的明确规则。单独的客户姓名和邮箱不进入向量请求；问题正文中若写入这些信息，本版本不会自动识别并删除。

接口有 30 秒模型请求超时且不自动重试，前端等待上限 60 秒。不要把失败捕获后改成空数组；那会让用户误认为没有历史案例。

中文 BM25 配置参考 [Jieba 官方说明](https://milvus.io/docs/jieba-tokenizer.md)。本环境实测 Lite 3.2.2 使用 tokenizer=jieba，旧示例中的 type=chinese 在这个版本报错，因此教程按实际版本编写。

第五部分结束的标准：模型配置正确、索引完整、能返回有出处的案例，错误能够准确显示。真实远程模型可用性与检索质量还要用你自己的凭据和独立评测数据验证。
