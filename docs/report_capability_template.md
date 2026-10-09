# 后续实验报告：模型能力与技术债

计划见 [PLAN-capability.md](PLAN-capability.md)，第 13 节是运行前确定的实施决定。数据在 `docs/data/capability/`。本文件由 `python3 -m harness capability report` 从 `docs/report_capability_template.md` 生成，表格中的数字都来自日志。

## 结论摘要

{{summary}}

## 1. 执行情况

花费按 API 官方价折算，实际计入 claude.ai 套餐的 Claude Code 用量。合计 {{total_spend}} 美元（含阶段 1）；正式会话 {{sessions}} 个，加上阶段 1 共 {{sessions_all}} 个。

{{blocks}}

{{execution_notes}}

## 2. 能力指标

“单次成功成本”= (实现 + 调试花费) ÷ 通过数。V0 是原始网站，6 个探针各做一次。

{{capability}}

## 3. 代码状态

每行是同一类状态的平均值。“k” 是生产者已尝试的 backlog 项数。

{{states}}

## 4. 维护

{{maint}}

## 5. 接手方：同一份 Sonnet 债务，不同模型（E1）

R 是不维护的状态，MS 是同一状态经 Sonnet 维护后的版本。溢价 π = R 上的单次成功成本 ÷ MS 上的单次成功成本 − 1，β = π / k。区间为 90% bootstrap 区间（按“重复 × 探针”配对重抽）。

{{e1}}

{{e1_notes}}

## 6. 自己维护是否回本（E2）

模型先维护 Sonnet 的代码，再在维护后的版本上做探针。m 是一次维护（补测试 + 代码整理）的平均花费，c₀ 是维护后状态上的单次成功成本，N* = √(4(m/c₀)/β) 是单次维护回本所需的最少剩余项数；β 的区间含 0 或为负时，N* 为 ∞。

{{e2}}

## 7. 生产方：不同模型留下的债务（E3）

各模型从 V0 起不维护地做 B01–B29。最后一列是 Sonnet 接手这些代码时的溢价（对照为 Sonnet 维护后的版本）。

{{e3}}

## 8. 单一模型工作流（E4）

同一个模型写代码、维护、接手。

{{e4}}

## 9. 生产者 × 接手者矩阵（E5，维护者固定为 Sonnet，k = 29）

格中是溢价 π。

{{e5}}

{{e5_notes}}

## 10. 判定

{{verdict}}

## 11. 局限

{{limits}}
