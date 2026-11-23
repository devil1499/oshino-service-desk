# 第四部分：模拟数据与 CSV 导入

正式实现已接入 XM 分支，打开侧栏“历史导入”。页面可下载空白模板和 40 条模拟案例；本次已实际导入 40 条，重复上传将提示已导入。操作验收见[第四部分实施与验收](../../03-检查记录/2026-10-31-第四部分实施与验收.md)。

Docker 用户在项目根目录执行 `docker compose --env-file .env.docker up -d --build --wait`，即可安装新增依赖并自动迁移，保留现有数据库。直接使用 WSL Python 的步骤见下文。

这一部分做到：你选一个 CSV 文件，后台把工单一次性存进 PostgreSQL；如果有一条不合格，整批都不存，并告诉你哪条记录有问题。

## 先理解三个东西

| 名词 | 大白话 |
|---|---|
| CSV | 用表头和每行数据组成的文本表格，Excel 也能打开 |
| import_key | 原始数据的唯一编号，相当于“这条数据从哪里来”的身份证 |
| 事务 | 一批写入一起成功；失败时不会留下半批数据 |

`import_key` 和系统工单编号不是同一个东西。前者来自你的 CSV，后者是系统分配的 T000001 一类编号。手动新建的工单没有 import_key，原来的手动流程继续使用。

## 跟写顺序

对照 [文件变化清单](08-接口与文件变化.md)，把第四部分的新文件和修改写进正式工程。

1. `backend/app/models.py`：增加来源编号。
2. `backend/migrations/versions/04_import_key.py`：给现有数据库增加这一列和唯一约束。
3. `backend/app/modules/tickets/import_csv.py`：校验 CSV 并完成导入。
4. `backend/app/main.py`：登记导入接口。
5. `backend/app/demo_data.py`：生成模拟工单。
6. 前端请求工具和 imports API → ImportView.vue → router → AppSidebar.vue（正式工程的导航在这里，不覆盖 App.vue）。
7. 空白模板放在 `frontend/public/import-template.csv`，样例放在 `data/raw/demo-tickets.csv`。

需要理解某行代码时，打开 [逐文件讲解](06-逐文件新增代码与讲解.md)，搜索文件名。

## 安装依赖并升级数据库

以下命令在 WSL Ubuntu 执行，前提是你已经把第四部分参考代码写进正式工程，并完成前三部分的数据库配置。

```bash
cd /mnt/e/oshino
source /mnt/e/oshino/.venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
cd backend
python -m alembic upgrade head
```

`python-multipart` 是本部分增加的运行依赖，FastAPI 接收上传文件需要它。迁移只新增一个允许为空的字段，不删除已有工单。

如果从空数据库开始，还要按第二部分教程生成 `.env`、建立数据库、运行迁移和 `python -m app.seed --username admin --display-name 管理员`。已经有管理员则不要重复创建。

## 准备模拟数据需要的基础配置

启动后端和前端，用管理员登录，在“基础管理”中建立：

- 产品：`演示协作平台`。
- 这个产品下的四个模块：`账号模块`、`账单模块`、`报表模块`、`集成模块`。
- 分类：`账号权限`、`计费订阅`、`功能使用`、`配置集成`、`性能故障`、`服务不可用`、`数据问题`。

七个分类通常已经由管理员初始化命令创建。所有名称必须与 CSV 完全一致，并且处于启用状态。导入不会替你偷偷新建或启用配置。

先使用包内的 40 条样例，验证成功后再生成更多数据：

```bash
cd /mnt/e/oshino/backend
python -m app.demo_data --count 3000 --seed 20261019 --output ../data/raw/demo-3000.csv
```

这个命令不调用模型、不连接数据库，只生成文件。相同种子与条数得到相同内容；已有文件不会被覆盖。相同种子生成的来源编号也相同，所以不能反复导入；要做另一批独立演示数据时使用新的种子。

生成器只是按有限场景模板组合数据，重复模式较多，适合功能测试。评测集需要后续另外设计、人工检查，不能从这里简单复制一份就当独立评测集。

## CSV 每列的意思

| 表头 | 作用 | 能不能自己改 |
|---|---|---|
| import_key | 全库唯一的来源编号，最长 100 字符 | 值可以自定；同一条来源记录保持同一编号 |
| title / description | 标题 / 问题描述 | 内容可以改，分别最多 200 / 10000 字符 |
| customer_name / customer_email | 模拟客户姓名 / 邮箱 | 内容可以改，邮箱必须符合格式 |
| product / module / category | 产品 / 所属模块 / 分类名称 | 必须对应已有启用配置 |
| priority | P1、P2、P3、P4 | 从四种值中选择 |
| status | pending 或 resolved | 仅支持这两种导入状态 |
| solution | 解决方案 | pending 留空；resolved 必填，最多 10000 字符 |

表头英文和顺序是前后端约定，先保持原样。导入负责人统一为当前管理员，时间为本次导入时间，不编造原始创建时间或处理过程；历史导入不能用于计算真实历史处理时长。

文件内有逗号、引号或换行时，必须按 CSV 规则引用。生成器使用标准库 csv 自动处理，不要手动用逗号拼接行。Excel 编辑后选择“CSV UTF-8”保存，不要直接上传 xlsx。

## 启动和验收

后端终端：

```bash
cd /mnt/e/oshino/backend
python -m uvicorn app.main:app --reload --port 8000
```

另开 WSL 终端：

```bash
cd /mnt/e/oshino/frontend
npm ci
npm run typecheck
npm run build
npm run dev
```

管理员打开“导入工单”，选择样例文件，点击“导入工单”，应显示成功导入 40 条。到列表查看详情，应保留描述中的换行、解决方案和 imported 导入记录。

再上传同一文件，应明确提示已经导入。把一条记录的分类改成不存在的名称，并给本批使用未导入过的编号，应收到记录号与错误原因，而且列表总量不增加。

最多 4 MiB、5000 条数据。报错中的“第 N 条记录”不含表头；因为描述能包含换行，它不一定等于文本编辑器的物理行号。若网络超时，先查看列表确认是否已成功提交，保留原编号重新尝试即可让唯一约束防止重复写入。

第四部分结束的标准：能生成文件、成功导入、查回工单；错误文件整批失败；客服没有导入权限；重复编号被拒绝。

依赖安装提示：`npm ci` 需要当前依赖对应的 `package-lock.json`。跟写时还没有锁文件，先在 `frontend` 运行 `npm install`；使用参考包配套锁文件时再运行 `npm ci`。
