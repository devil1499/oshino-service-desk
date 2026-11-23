"""生成可复现的流程演示数据；不把模板数据当作独立评测集。"""

import argparse
import csv
import random
from pathlib import Path

FIELDS = [
    "import_key",
    "title",
    "description",
    "customer_name",
    "customer_email",
    "product",
    "module",
    "category",
    "priority",
    "status",
    "solution",
]
SCENARIOS = [
    ("账号模块", "账号权限", "P2", "E401 登录失败", "角色绑定失效后无法登录", "重新绑定正确角色并验证登录成功"),
    (
        "账号模块",
        "账号权限",
        "P3",
        "邀请链接过期",
        "新员工打开邀请链接提示已过期",
        "撤销旧邀请，重新发送并确认在有效期内完成激活",
    ),
    (
        "账单模块",
        "计费订阅",
        "P3",
        "订阅账单金额不符",
        "账单人数与当前席位数不一致",
        "核对计费周期与席位变更记录，按本周期实际用量解释费用",
    ),
    (
        "账单模块",
        "计费订阅",
        "P2",
        "付款后订阅未生效",
        "付款完成后仍然显示免费版",
        "核实支付流水后补偿订阅状态，确认权益恢复",
    ),
    (
        "报表模块",
        "功能使用",
        "P4",
        "如何导出报表",
        "用户不清楚日期范围和导出入口",
        "指导选择日期范围并点击导出，确认下载文件完整",
    ),
    (
        "集成模块",
        "配置集成",
        "P2",
        "Webhook 签名失败",
        "回调返回 E403，业务数据无法同步",
        "核对签名算法和时间戳，更新接收端配置后重放测试事件",
    ),
    (
        "报表模块",
        "性能故障",
        "P2",
        "报表查询超时",
        "筛选大量历史记录时查询超过等待时间",
        "缩小日期范围定位慢查询，优化对应索引并验证响应时间",
    ),
    (
        "集成模块",
        "服务不可用",
        "P1",
        "接口 E503 不可用",
        "所有请求返回 E503，多个用户无法完成业务",
        "确认依赖服务故障，恢复服务并通过探针和业务请求验证",
    ),
    (
        "报表模块",
        "数据问题",
        "P2",
        "报表缺少昨日数据",
        "昨日已完成的业务没有进入报表",
        "检查同步任务断点，补跑缺失批次并核对源表总量",
    ),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 SaaS 售后模拟 CSV，不连接数据库或模型")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20261018)
    args = parser.parse_args()
    if not 1 <= args.count <= 5000:
        parser.error("count 必须在 1 到 5000 之间")
    if args.output.exists():
        parser.error("输出文件已存在，请选择新文件名")
    rng = random.Random(args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        for number in range(1, args.count + 1):
            module, category, priority, title, description, solution = rng.choice(SCENARIOS)
            status = "pending" if number % 5 == 0 else "resolved"
            writer.writerow(
                {
                    "import_key": f"demo-{args.seed}-{number:05d}",
                    "title": f"模拟：{title}（样本 {number}）",
                    "description": f"模拟组织 {number} 反馈：{description}。\n客服已核对发生时间与操作步骤。",
                    "customer_name": f"模拟客户{number}",
                    "customer_email": f"demo{number}@example.com",
                    "product": "演示协作平台",
                    "module": module,
                    "category": category,
                    "priority": priority,
                    "status": status,
                    "solution": solution if status == "resolved" else "",
                }
            )
    print(f"已生成 {args.count} 条模拟工单：{args.output}")
    print("请先建立产品“演示协作平台”，及账号、账单、报表、集成四个模块（名称带“模块”）。")
    print("分类使用管理员初始化时建立的七个默认分类；这些模板数据仅用于流程演示。")


if __name__ == "__main__":
    main()
