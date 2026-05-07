# SAFER — 软件风险评估分析框架

本项目是 **SAFER** 风险评分模型的 Python 实现，论文来源：
[arXiv:2408.02876v2](https://arxiv.org/abs/2408.02876)
（《提升软件信任度：开源软件风险评估的整体方法》）。

SAFER 通过综合开发者声誉、发布者可靠性、用户评价、漏洞暴露程度以及部署上下文，
将软件包的可信度量化为单一分数 **R_FP ∈ [0, 1]**，
并映射至 **低风险 / 中风险 / 高风险 / 严重风险** 四个风险等级。

---

## 目录

1. [本项目如何实现论文](#本项目如何实现论文)
2. [安装](#安装)
3. [快速开始](#快速开始)
4. [逐步分析 GitHub 软件包](#逐步分析-github-软件包)
   - [第一步：从 GitHub 与包注册表收集数据](#第一步从-github-与包注册表收集数据)
   - [第二步：构建 SoftwareRecord](#第二步构建-softwarerecord)
   - [第三步：评分与结果解读](#第三步评分与结果解读)
5. [命令行工作流](#命令行工作流)
   - [自动化分析（safer analyze）](#自动化分析safer-analyze)
   - [对单个包评分](#对单个包评分)
   - [批量评分 CSV 文件](#批量评分-csv-文件)
   - [生成合成数据集](#生成合成数据集)
6. [REST API](#rest-api)
7. [批量分析——对比多个软件包](#批量分析对比多个软件包)
8. [结果字段参考](#结果字段参考)
9. [结果解读](#结果解读)
10. [配置与调优](#配置与调优)
11. [字段映射速查表](#字段映射速查表)
12. [项目内部结构](#项目内部结构)

---

## 本项目如何实现论文

论文（arXiv:2408.02876v2，第 V 节）定义了 19 个公式，分为三个演员风险段、一个惩罚因子和最终评分。
本项目将每个公式实现为独立的 Python 纯函数，存放在 `safer_model/formulas/` 下对应的模块中：

| 论文内容 | 公式 | 对应源文件 |
|---|---|---|
| 开发者风险（R_CD、R_CS、R_PL 及各权重） | 公式 1–9 | `safer_model/formulas/developer.py` |
| 发布者风险（R_PB） | 公式 10 | `safer_model/formulas/publisher.py` |
| 用户指示风险（R_UR） | 公式 11 | `safer_model/formulas/user.py` |
| 惩罚因子（P、上下文 C_TXT） | 公式 12–14 | `safer_model/formulas/penalty.py` |
| 演员权重 + 最终评分（R_F、R_FP） | 公式 15–19 | `safer_model/formulas/final_score.py` |
| 风险等级阈值 | 第 V-G 节 | `safer_model/bands.py` |
| 可调参数 | 第 VI 节 | `safer_model/config.py` |

论文附录中的 Table IX 完整工作示例已原样复现为集成测试
`tests/integration/test_worked_example.py`，对所有中间值进行精确断言（容差 ±0.1 %）。

### 计算流水线

```
SoftwareRecord
      │
      ▼
┌─────────────────────────────────────────────────────────────────┐
│  SAFERScorer  (scorer.py)                                       │
│                                                                 │
│  步骤 1  解析演员历史（注册表或内联）                            │
│  步骤 2  聚合跨数据集 Σ 统计量                                  │
│  步骤 3  公式 1–4    R_CD、R_CS、R_PL                          │
│  步骤 4  公式 6–9    w_CD、w_CS、w_PL                          │
│  步骤 5  公式 5      R_DEV（加权求和）                          │
│  步骤 6  公式 10     R_PB                                       │
│  步骤 7  公式 11     R_UR                                       │
│  步骤 8  公式 12–14  惩罚项 P                                   │
│  步骤 9  公式 15–19  w_DEV、w_PB、w_UR → R_F → R_FP           │
└─────────────────────────────────────────────────────────────────┘
      │
      ▼
SAFERResult  →  风险等级分类（bands.py）
```

### 两种运行模式

**数据集模式** — 在构造时传入全量记录，自动构建注册表，跨包的 Σ 统计量（`w_lc`、`e_db`、`r_pl`、`r_pb`）均从整个数据集中推导，与论文评估一致。

```python
scorer = SAFERScorer(records=records)   # 自动构建 DeveloperRegistry + PublisherRegistry
results = scorer.score_all()
```

**独立模式** — 每条 `SoftwareRecord` 内嵌预填充的 `DeveloperHistory` / `PublisherHistory`，无需注册表。适用于单包评分、API 调用和 `safer analyze` 命令。

```python
scorer = SAFERScorer()                  # 不构建注册表
result = scorer.score(record)
```

---

## 安装

```bash
# 克隆仓库并以可编辑模式安装（推荐用于开发）
git clone https://github.com/your-org/safer-model-realization.git
cd "safer-model-realization"
pip install -e .

# 验证安装
safer --version
```

**环境要求：** Python ≥ 3.11，pip ≥ 21。

REST API 的可选依赖：
```bash
pip install -e ".[dev]"   # 安装 pytest、httpx（用于 API 测试）
```

---

## 快速开始

```python
from safer_model.schemas.input import SoftwareRecord, DeveloperHistory, PublisherHistory
from safer_model.scorer import SAFERScorer

record = SoftwareRecord(
    software_id="psf/requests",
    code_length=4200,          # 代码行数（cloc / tokei 统计）
    language="Python",
    dependencies=5,            # requirements.txt / setup.py 中的依赖数量
    code_coverage=0.85,        # Codecov 徽章值（0–1）
    known_vulnerabilities=8,   # GitHub Security Advisories 中的已知漏洞数
    unresolved_vulnerabilities=1,
    update_frequency=0.9,      # 标准化发布频率（见下文说明）
    forks=9400,
    downloads=30_000_000,      # PyPI 月下载量
    rating=51_000,             # GitHub Star 数
    context=0.5,               # 0.2=安全软件, 0.3=自动化软件, 0.5=通用软件
    developer_histories=[
        DeveloperHistory(
            developer_id="psf",
            total_vulnerabilities=8,
            total_software_count=12,
            software_same_lang_count=10,
            years_same_lang=14.0,
            years_total=14.0,
        )
    ],
    publisher_histories=[
        PublisherHistory(
            publisher_id="psf",
            software_published_count=12,
            years_publishing=14.0,
        )
    ],
)

scorer = SAFERScorer()
result = scorer.score(record)

print(f"R_FP = {result.r_fp:.4f}  →  {result.band.value}")
# R_FP = 0.1234  →  Low
```

---

## 逐步分析 GitHub 软件包

以下各节以 **`psf/requests`** Python 库为具体示例逐步讲解。
所有数据点均直接对应 `SoftwareRecord` 的各字段。

---

### 第一步：从 GitHub 与包注册表收集数据

#### 1a. 仓库元数据（GitHub REST API v3）

```bash
# 安装 GitHub CLI，或使用 curl 配合个人访问令牌
gh api repos/psf/requests
```

返回的关键字段：

| JSON 键 | SAFER 字段 | 说明 |
|---|---|---|
| `stargazers_count` | `rating` | GitHub Star 数，作为用户满意度信号 |
| `forks_count` | `forks` | 社区 Fork 数，代理开发者信任权重 |
| `language` | `language` | 主要编程语言 |
| `pushed_at` 与 `created_at` | 用于推导 `update_frequency` | 见 1c |

```python
import requests as http_lib   # 重命名以避免与被测包名冲突

resp = http_lib.get(
    "https://api.github.com/repos/psf/requests",
    headers={"Authorization": "token YOUR_PAT"},
)
repo = resp.json()

stars = repo["stargazers_count"]    # → rating
forks = repo["forks_count"]         # → forks
language = repo["language"]         # → language
```

#### 1b. 下载量（PyPI / npm）

**PyPI（Python 包）：**
```python
resp = http_lib.get("https://pypistats.org/api/packages/requests/recent")
downloads = resp.json()["data"]["last_month"]   # → downloads
```

**npm（JavaScript 包）：**
```python
pkg = "lodash"
resp = http_lib.get(f"https://api.npmjs.org/downloads/point/last-month/{pkg}")
downloads = resp.json()["downloads"]            # → downloads
```

**无下载 API 时：** 可使用 Traffic API 中的 GitHub 克隆次数
（`GET /repos/{owner}/{repo}/traffic/clones`，需要 push 权限），
或以 `stargazers_count` 作为下限代理值。

#### 1c. 更新频率

`update_frequency` ∈ (0, 1] 衡量软件包的维护活跃程度。
计算方式为*实际发布周期数*与*已过日历周期数*之比，上限为 1：

```python
from datetime import datetime, timezone

# 方案 A — 使用 PyPI 发布历史
resp = http_lib.get("https://pypi.org/pypi/requests/json")
releases = resp.json()["releases"]
release_count = len([v for v, files in releases.items() if files])

created_year = 2011   # requests 首次发布年份
years_active = datetime.now(timezone.utc).year - created_year
releases_per_year = release_count / max(years_active, 1)

# 标准化：假设每年约 4 次发布为"完全活跃"（可按实际基准调整）
update_frequency = min(releases_per_year / 4.0, 1.0)
```

#### 1d. 代码行数

克隆仓库后在本地运行 **cloc** 或 **tokei**：
```bash
git clone --depth 1 https://github.com/psf/requests.git /tmp/requests
cloc /tmp/requests/requests --json | python -c \
  "import json,sys; d=json.load(sys.stdin); print(d['SUM']['code'])"
```

若仓库发布了相关徽章或 CI 报告，也可直接读取。

#### 1e. 依赖数量

```python
# PyPI：统计 install_requires 条目数
resp = http_lib.get("https://pypi.org/pypi/requests/json")
requires = resp.json()["info"].get("requires_dist") or []
dependencies = len([r for r in requires if "extra ==" not in r])
```

npm 包：
```python
resp = http_lib.get("https://registry.npmjs.org/lodash/latest")
pkg_json = resp.json()
dependencies = len(pkg_json.get("dependencies", {}))
```

#### 1f. 漏洞数据（GitHub Security Advisories）

```bash
# 使用 GraphQL 查询该包的安全通告
gh api graphql -f query='
  query {
    securityVulnerabilities(ecosystem: PIP, package: "requests", first: 100) {
      totalCount
      nodes { severity advisory { withdrawnAt } }
    }
  }
'
```

```python
resp = http_lib.post(
    "https://api.github.com/graphql",
    json={"query": """
        query($pkg: String!) {
          securityVulnerabilities(ecosystem: PIP, package: $pkg, first: 100) {
            totalCount
            nodes { severity advisory { withdrawnAt } }
          }
        }
    """, "variables": {"pkg": "requests"}},
    headers={"Authorization": "bearer YOUR_PAT"},
)
vulns = resp.json()["data"]["securityVulnerabilities"]

known_vulnerabilities = vulns["totalCount"]
# 未修复漏洞 = 尚未撤回的通告（尚无修复版本发布）
unresolved_vulnerabilities = sum(
    1 for v in vulns["nodes"] if v["advisory"]["withdrawnAt"] is None
)
```

也可通过 Dependabot 获取您自己 Fork 中的告警：
```bash
gh api repos/YOUR_ORG/YOUR_FORK/dependabot/alerts --paginate \
  | python -c "
import json, sys
alerts = json.load(sys.stdin)
known = len(alerts)
unresolved = sum(1 for a in alerts if a['state'] == 'open')
print(known, unresolved)
"
```

#### 1g. 代码覆盖率

查看仓库 README 中的徽章或 CI 配置，获取 Codecov / Coveralls 数值。
大多数 Python 项目会在 `https://codecov.io/gh/{owner}/{repo}` 发布覆盖率：

```python
resp = http_lib.get("https://codecov.io/api/gh/psf/requests")
coverage = resp.json()["repo"]["stats"]["coverage"] / 100.0   # → code_coverage
```

若无覆盖率数据，使用 `0.0`（保守假设）。

#### 1h. 开发者历史

`DeveloperHistory` 记录维护者**跨所有包**的历史记录，而非仅限于当前包。
跨包聚合正是 SAFER 模型获取跨数据集信号的关键所在。

```python
# 列出发布机构的所有公开仓库
resp = http_lib.get(
    "https://api.github.com/orgs/psf/repos?per_page=100&type=public",
    headers={"Authorization": "token YOUR_PAT"},
)
repos = resp.json()

total_software_count = len(repos)
# 统计同语言仓库数量
software_same_lang_count = sum(1 for r in repos if r.get("language") == "Python")

# 汇总所有仓库的漏洞数（简化版：使用已知漏洞数 × 比例；生产环境建议对每个仓库重复步骤 1f）
total_vulnerabilities = known_vulnerabilities   # 下限：至少包含目标包的漏洞

# 经验年限：取最早仓库的创建时间
from datetime import datetime, timezone
dates = [datetime.fromisoformat(r["created_at"].rstrip("Z")) for r in repos]
earliest = min(dates)
years_total = (datetime.now(timezone.utc).replace(tzinfo=None) - earliest).days / 365.25
years_same_lang = years_total   # 保守估计：假设所有经验均为主语言
```

#### 1i. 发布者历史

```python
publisher_history = PublisherHistory(
    publisher_id="psf",
    software_published_count=total_software_count,
    years_publishing=years_total,
)
```

#### 1j. 选择上下文值

| 部署场景 | `context` 值 |
|---|---|
| 安全工具、认证库、密码学库 | `0.2`（最严格） |
| CI/CD 自动化、构建工具 | `0.3` |
| 通用工具、数据处理 | `0.5` |

不确定时使用 `0.2`——框架默认采用最严格的评估。

---

### 第二步：构建 SoftwareRecord

```python
from safer_model.schemas.input import SoftwareRecord, DeveloperHistory, PublisherHistory

record = SoftwareRecord(
    software_id="psf/requests",
    # 代码属性
    code_length=4200,
    language="Python",
    dependencies=5,
    code_coverage=0.85,
    # 漏洞数据
    known_vulnerabilities=8,
    unresolved_vulnerabilities=1,
    # 发布 / 版本属性
    update_frequency=0.75,
    forks=9400,
    downloads=30_000_000,
    rating=51_000,
    # 上下文
    context=0.5,
    # 参与者历史（来自步骤 1h–1i）
    developer_histories=[
        DeveloperHistory(
            developer_id="psf",
            total_vulnerabilities=8,
            total_software_count=42,
            software_same_lang_count=38,
            years_same_lang=14.0,
            years_total=14.0,
        )
    ],
    publisher_histories=[
        PublisherHistory(
            publisher_id="psf",
            software_published_count=42,
            years_publishing=14.0,
        )
    ],
)
```

---

### 第三步：评分与结果解读

```python
from safer_model.scorer import SAFERScorer

scorer = SAFERScorer()            # 独立模式——使用内联历史记录
result = scorer.score(record)

print(f"风险等级 : {result.band.value}")
print(f"R_FP     : {result.r_fp:.4f}")
print()
print("── 中间分数 ──────────────────────────────")
print(f"  R_CD  （依赖风险）    : {result.r_cd:.2f}")
print(f"  R_CS  （代码规格风险）: {result.r_cs:.2f}")
print(f"  R_PL  （语言风险）    : {result.r_pl:.4f}")
print(f"  R_DEV （开发者风险）  : {result.r_dev:.2f}")
print(f"  R_PB  （发布者风险）  : {result.r_pb:.4f}")
print(f"  R_UR  （用户风险）    : {result.r_ur:.4f}")
print(f"  惩罚项               : {result.penalty:.4f}")
print(f"  R_F   （惩罚前分数）  : {result.r_f:.4f}")
```

`psf/requests` 的示例输出：
```
风险等级 : Low
R_FP     : 0.0731

── 中间分数 ──────────────────────────────
  R_CD  （依赖风险）    : 5.00
  R_CS  （代码规格风险）: 1.52
  R_PL  （语言风险）    : 0.0000
  R_DEV （开发者风险）  : 1.43
  R_PB  （发布者风险）  : 0.0356
  R_UR  （用户风险）    : 0.9983
  惩罚项               : 0.0119
  R_F   （惩罚前分数）  : 0.0731
```

---

## 命令行工作流

### 自动化分析（`safer analyze`）

最核心的命令——从 GitHub、PyPI、npm API 自动采集所有所需字段，评分后写出报告，无需手动收集数据。

```bash
safer analyze REPO [OPTIONS]
```

| 选项 | 默认值 | 说明 |
|---|---|---|
| `REPO` | *(必填)* | `owner/repo` 格式，如 `psf/requests` |
| `-t / --token` | `$GITHUB_TOKEN` | GitHub 个人访问令牌，用于漏洞和开发者历史查询 |
| `-c / --context` | `0.5` | 部署上下文：`0.2` = 安全软件 · `0.3` = 自动化工具 · `0.5` = 通用软件 |
| `-p / --pkg-name` | *(自动)* | 当包注册表名称与仓库名不同时指定（如 `vercel/next.js` 对应 `next`） |
| `-o / --output` | `.` | 输出文件目录 |
| `-f / --format` | `json` | 输出格式：`json` `md` `csv`，可多次指定以输出多种格式 |
| `-r / --ref` | *(HEAD)* | git tag、分支或 commit SHA，用于分析历史版本 |
| `--pretty / --no-pretty` | pretty | 是否美化打印 JSON 输出 |

**使用示例：**

```bash
# 最简用法：评分当前 HEAD，将 JSON 写到当前目录
safer analyze psf/requests --token $GITHUB_TOKEN

# 安全库——最严格上下文，输出 JSON + Markdown 报告
safer analyze hashicorp/vault --token $GITHUB_TOKEN \
  --context 0.2 --format json --format md

# 分析特定历史版本标签
safer analyze pallets/flask --ref 3.0.0 \
  --format json --format md --output ./reports

# npm 包（注册表名与仓库名不同）
safer analyze vercel/next.js --pkg-name next --token $GITHUB_TOKEN

# 同时输出三种格式到自定义目录
safer analyze ultralytics/ultralytics --token $GITHUB_TOKEN \
  --format json --format md --format csv --output ./reports

# 无 Token 模式——跳过漏洞数据和 GitHub 组织历史查询
safer analyze chalk/chalk --format json
```

输出文件命名规则：
- 当前 HEAD：`{owner}_{repo}_safer_result.json` / `_safer_report.md` / `_safer_result.csv`
- 指定版本（如 `--ref v1.2.3`）：`{owner}_{repo}_v1.2.3_safer_result.json`（同理）

---

### 对单个包评分

将收集到的数据构造为 JSON 并传递给 `safer score-one`：

```bash
# --pretty / --no-pretty 控制 JSON 缩进格式（默认：美化输出）
safer score-one --json '{
  "software_id": "psf/requests",
  "code_length": 4200,
  "language": "Python",
  "dependencies": 5,
  "code_coverage": 0.85,
  "known_vulnerabilities": 8,
  "unresolved_vulnerabilities": 1,
  "update_frequency": 0.75,
  "forks": 9400,
  "downloads": 30000000,
  "rating": 51000,
  "context": 0.5,
  "developer_histories": [{
    "developer_id": "psf",
    "total_vulnerabilities": 8,
    "total_software_count": 42,
    "software_same_lang_count": 38,
    "years_same_lang": 14.0,
    "years_total": 14.0
  }],
  "publisher_histories": [{
    "publisher_id": "psf",
    "software_published_count": 42,
    "years_publishing": 14.0
  }]
}'
```

输出（格式化 JSON）：
```json
{
  "software_id": "psf/requests",
  "r_fp": 0.0731,
  "band": "Low",
  "r_cd": 5.0,
  "r_cs": 1.52,
  ...
}
```

### 批量评分 CSV 文件

准备一个每行代表一个包的 CSV 文件（论文中的 Table III 格式），然后：

```bash
safer score --input packages.csv --output results.csv

# 所有选项：
#   -i / --input TEXT          输入 CSV 文件（必填）
#   -o / --output TEXT         输出文件路径（默认：<input>_results.csv）
#   -f / --format [csv|json]   输出格式（默认：csv）
#   --dep-sensitivity FLOAT    依赖风险放大系数，对应论文第 VI-A 节（默认：1.0）

# 打印结果文件的风险等级汇总
safer report --input results.csv
```

CSV 列名必须严格匹配：

```
software_id,code_length,language,dependencies,code_coverage,
known_vulnerabilities,unresolved_vulnerabilities,update_frequency,
forks,downloads,rating,context,developer,publisher,year
```

`developer` 和 `publisher` 为字符串 ID；评分器会自动构建注册表以计算跨包聚合统计。

### 生成合成数据集

```bash
# 生成 500 条记录，自定义随机种子
safer generate --samples 500 --seed 7 --output data/test.csv

# 立即对其评分
safer score --input data/test.csv
```

---

## REST API

启动服务：

```bash
uvicorn safer_api.app:create_app --factory --reload --port 8000
```

交互式文档：`http://localhost:8000/docs`

### 对单个包评分

```bash
curl -s -X POST http://localhost:8000/score \
  -H "Content-Type: application/json" \
  -d '{
    "software_id": "psf/requests",
    "code_length": 4200,
    "language": "Python",
    "dependencies": 5,
    "code_coverage": 0.85,
    "known_vulnerabilities": 8,
    "unresolved_vulnerabilities": 1,
    "update_frequency": 0.75,
    "forks": 9400,
    "downloads": 30000000,
    "rating": 51000,
    "context": 0.5,
    "developer_histories": [{
      "developer_id": "psf",
      "total_vulnerabilities": 8,
      "total_software_count": 42,
      "software_same_lang_count": 38,
      "years_same_lang": 14.0,
      "years_total": 14.0
    }],
    "publisher_histories": [{
      "publisher_id": "psf",
      "software_published_count": 42,
      "years_publishing": 14.0
    }]
  }' | python -m json.tool
```

### 批量评分（数据集模式）

```bash
curl -s -X POST http://localhost:8000/score/batch \
  -H "Content-Type: application/json" \
  -d '[...SoftwareRecord 对象数组...]' | python -m json.tool
```

批量模式会从提交的记录中自动构建 DeveloperRegistry 和 PublisherRegistry，
无需手动预先计算 `total_vulnerabilities` 或 `years_total`。

---

## 批量分析——对比多个软件包

SAFER 最有价值的用途是对一组候选包进行排名。
数据集模式从完整候选列表中构建注册表，每个包的开发者/发布者历史均从同组其他包中推导。

```python
import pandas as pd
from safer_model.io import load_csv, results_to_dataframe
from safer_model.scorer import SAFERScorer

# 加载 packages.csv（每行一个包）
records = load_csv("packages.csv")

# 数据集模式：从完整列表构建注册表
scorer = SAFERScorer(records=records)
results = scorer.score_all()

# 转换为 DataFrame 进行分析
df = results_to_dataframe(results)
df_sorted = df.sort_values("r_fp")

print(df_sorted[["software_id", "r_fp", "band"]].to_string(index=False))
```

示例输出：
```
   software_id    r_fp      band
  psf/requests  0.0731       Low
     numpy/numpy  0.1043       Low
  pallets/flask  0.2871  Moderate
  django/django  0.3102  Moderate
```

---

## 结果字段参考

| 字段 | 对应公式 | 说明 |
|---|---|---|
| `r_fp` | 公式 19 | **最终风险分数**（0 = 无风险，1 = 最高风险） |
| `band` | 第 V-G 节 | 风险等级分类 |
| `r_f` | 公式 15 | 惩罚前分数（当 `r_f ≤ 0.5` 时等于 `r_fp`） |
| `penalty` | 公式 12 | 惩罚项 P = 1 − C_TXT^V_UP |
| `r_dev` | 公式 5 | 开发者风险（无上界；由公式 15 的 Sigmoid 归一化） |
| `r_pb` | 公式 10 | 发布者风险 |
| `r_ur` | 公式 11 | 用户指示风险（1 − Stars/下载量） |
| `r_cd` | 公式 1 | 代码依赖风险（= 依赖数 × 灵敏度） |
| `r_cs` | 公式 2 | 代码规格风险（= w_LC × 代码行数） |
| `r_pl` | 公式 4 | 编程语言经验风险 |
| `w_dev` | 公式 17 | 开发者参与者权重（与 Fork 数成反比） |
| `w_pb` | 公式 18 | 发布者参与者权重（Laplace 平滑漏洞比率） |
| `w_ur` | 公式 16 | 用户参与者权重（1 − w_DEV − w_PB） |
| `w_lc` | 公式 3 | 开发者跨包历史漏洞率 |
| `e_db` | 公式 8 | 开发者在目标语言上的专业程度 |
| `w_cd` | 公式 6 | 代码依赖子权重（1 − 覆盖率） |
| `w_cs` | 公式 7 | 代码规格子权重（exp(−E_DB)） |
| `w_pl` | 公式 9 | 编程语言子权重 |

---

## 结果解读

### 风险等级

| 等级 | R_FP 范围 | 建议措施 |
|---|---|---|
| **低风险（Low）** | [0.00, 0.25) | 可用于生产环境；持续监控安全通告 |
| **中风险（Moderate）** | [0.25, 0.50) | 审查未修复漏洞；跟踪更新频率 |
| **高风险（High）** | [0.50, 0.75) | 集成前需进行安全审查 |
| **严重风险（Critical）** | [0.75, 1.00] | 未经彻底审计和缓解措施前不得使用 |

### 诊断信号

**`r_cs` 偏高**（代码规格风险高）
: 该开发者相对其产出量具有较高的历史漏洞率（`w_lc` 偏大）。
建议检查其他包是否存在反复出现的 CVE 模式。

**`r_pb` 偏高**（发布者风险高）
: 更新不频繁（`update_frequency` ≪ 1）或新发布者发布包数量较少。
请检查发布历史和问题响应时间。

**`r_ur` 偏高**（用户风险高）
: 相对下载量而言 Star 数偏低——高下载量配合低社区认可度，
可能表明该依赖是被间接引入而非主动选择的。

**`r_fp > r_f`**（惩罚项已触发）
: `r_f > 0.5` 触发了惩罚机制。在高风险上下文中，未修复漏洞占比
（`V_U / V_T`）不可忽视。建议检查 Dependabot 告警。

---

## 配置与调优

通过 `SAFERConfig` 覆盖默认值：

```python
from safer_model.config import SAFERConfig
from safer_model.scorer import SAFERScorer

config = SAFERConfig(
    # 在供应链敏感环境中放大依赖风险
    dep_sensitivity=2.0,

    # 将未知上下文视为自动化软件（而非安全软件）
    unknown_context=0.3,

    # 降低惩罚阈值——在 R_F > 0.4 时触发惩罚（默认 0.5）
    penalty_threshold=0.4,
)

scorer = SAFERScorer(config=config)
```

### 自定义风险等级阈值（论文第 VI-D 节）

```python
from safer_model.schemas.output import RiskBand

config = SAFERConfig(
    risk_band_thresholds=[
        (RiskBand.LOW,      0.00, 0.20),   # 更严格的低风险区间
        (RiskBand.MODERATE, 0.20, 0.40),
        (RiskBand.HIGH,     0.40, 0.70),
        (RiskBand.CRITICAL, 0.70, 1.01),
    ]
)
```

> **注意：** 自定义阈值会导致不同组织之间的分数不可比较
>（见论文第 VI 节）。对外发布分数时请保留默认阈值。

---

## 字段映射速查表

GitHub / 注册表 API 响应到 `SoftwareRecord` 字段的快速映射：

| `SoftwareRecord` 字段 | 数据来源 | API / 命令 |
|---|---|---|
| `rating` | GitHub Star 数 | `repo.stargazers_count` |
| `forks` | GitHub Fork 数 | `repo.forks_count` |
| `language` | GitHub 主要语言 | `repo.language` |
| `downloads` | PyPI 月下载量 | `pypistats.org/api/packages/{pkg}/recent` |
| `downloads` | npm 月下载量 | `api.npmjs.org/downloads/point/last-month/{pkg}` |
| `update_frequency` | 发布频率 | 从 PyPI/npm 发布历史计算（见步骤 1c） |
| `dependencies` | 包清单 | `requires_dist`（PyPI）· `dependencies`（npm） |
| `code_length` | 代码行数 | 在克隆仓库上运行 `cloc` 或 `tokei` |
| `code_coverage` | CI 徽章 | Codecov / Coveralls API |
| `known_vulnerabilities` | GitHub 安全通告 | GraphQL `securityVulnerabilities` |
| `unresolved_vulnerabilities` | Dependabot 告警 | `GET /repos/{owner}/{repo}/dependabot/alerts` |
| `DeveloperHistory.total_software_count` | 组织仓库数 | `GET /orgs/{org}/repos` |
| `DeveloperHistory.years_total` | 组织创建日期 | `org.created_at` |
| `PublisherHistory.software_published_count` | 组织仓库数 | 同上 |
| `PublisherHistory.years_publishing` | 组织创建日期 | `org.created_at` |

---

## 项目内部结构

```
SAFER Model Realization/
│
├── safer_model/                    # 核心模型包
│   ├── __init__.py                 # 公开 API 导出
│   ├── config.py                   # SAFERConfig — 可调参数（对应论文第 VI 节）
│   ├── constants.py                # 固定常量（Sigmoid 参数、上下文值）
│   ├── bands.py                    # 风险等级分类器（第 V-G 节阈值）
│   ├── scorer.py                   # SAFERScorer — 9 步计算流水线编排
│   ├── registry.py                 # DeveloperRegistry / PublisherRegistry
│   ├── fetcher.py                  # GitHubFetcher — 从 API 自动采集数据
│   ├── generator.py                # 合成数据集生成器（对应论文附录）
│   ├── io.py                       # CSV / JSON I/O 工具
│   │
│   ├── formulas/                   # 每个风险组件一个模块
│   │   ├── developer.py            # 公式 1–9 ：R_CD、R_CS、R_PL、各权重、R_DEV
│   │   ├── publisher.py            # 公式 10  ：R_PB
│   │   ├── user.py                 # 公式 11  ：R_UR
│   │   ├── penalty.py              # 公式 12–14：惩罚项 P、上下文 C_TXT
│   │   └── final_score.py          # 公式 15–19：演员权重、R_F、R_FP
│   │
│   └── schemas/
│       ├── input.py                # SoftwareRecord、DeveloperHistory、PublisherHistory
│       └── output.py               # SAFERResult、RiskBand
│
├── safer_cli/
│   └── main.py                     # Click CLI：generate / score / score-one / report / analyze
│
├── safer_api/
│   ├── app.py                      # FastAPI 应用工厂
│   └── routes.py                   # GET /health · POST /score · POST /score/batch
│
├── tests/
│   ├── conftest.py                 # 测试夹具：论文 Table IX 工作示例数据
│   ├── unit/                       # 公式单元测试（每个 formulas/ 模块对应一个文件）
│   └── integration/                # 端到端测试：工作示例 + CLI 测试
│
├── pyproject.toml                  # 包元数据和 CLI 入口点
└── requirements.txt                # 运行时依赖
```

---

## 运行测试

```bash
pytest                          # 全部 106 个测试
pytest tests/unit/              # 仅运行公式单元测试
pytest tests/integration/       # 工作示例 + CLI 集成测试
pytest -v tests/integration/test_worked_example.py   # 论文 Table IX 基准测试
```

---

## 引用

```bibtex
@misc{safer2024,
  title  = {Elevating Software Trust: A Holistic Approach to Open-Source Risk Assessment},
  author = {…},
  year   = {2024},
  eprint = {2408.02876},
  archivePrefix = {arXiv},
}
```
