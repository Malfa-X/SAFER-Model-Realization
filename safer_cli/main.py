"""
SAFER CLI — command-line interface for the SAFER risk assessment framework.

Entry point: `safer` (registered in pyproject.toml [project.scripts])

Commands:
    safer generate   — generate a synthetic dataset
    safer score      — batch-score a CSV file
    safer score-one  — score a single software record from JSON
    safer report     — print a summary of results
    safer analyze    — fetch data from GitHub and score a repository automatically
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from safer_model.generator import generate_and_save
from safer_model.io import load_csv, load_json, results_to_csv, results_to_dataframe
from safer_model.scorer import SAFERScorer


@click.group()
@click.version_option(version="1.0.0", prog_name="safer")
def cli() -> None:
    """SAFER: Software Analysis Framework for Evaluating Risk (arXiv:2408.02876v2)"""


# ── safer generate ─────────────────────────────────────────────────────────────

@cli.command("generate")
@click.option(
    "--samples", "-n",
    default=9000,
    show_default=True,
    help="Number of synthetic records to generate.",
)
@click.option(
    "--seed", "-s",
    default=42,
    show_default=True,
    help="Random seed for reproducibility. Use -1 for non-deterministic.",
)
@click.option(
    "--output", "-o",
    default="data/sample_dataset.csv",
    show_default=True,
    help="Output CSV file path.",
)
def generate(samples: int, seed: int, output: str) -> None:
    """Generate a synthetic software dataset matching the paper's Appendix criteria."""
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    actual_seed = None if seed == -1 else seed
    click.echo(f"Generating {samples} records (seed={actual_seed}) → {out_path}")
    df = generate_and_save(str(out_path), n=samples, seed=actual_seed)
    click.echo(f"Done. {len(df)} records written to {out_path}")


# ── safer score ────────────────────────────────────────────────────────────────

@cli.command("score")
@click.option(
    "--input", "-i", "input_path",
    required=True,
    help="Input CSV file (Table III format).",
)
@click.option(
    "--output", "-o", "output_path",
    default=None,
    help="Output CSV file for results. Defaults to <input>_results.csv.",
)
@click.option(
    "--format", "-f", "fmt",
    type=click.Choice(["csv", "json"]),
    default="csv",
    show_default=True,
    help="Output format.",
)
@click.option(
    "--dep-sensitivity",
    default=1.0,
    show_default=True,
    help="Dependency sensitivity multiplier (Section VI-A).",
)
def score(
    input_path: str,
    output_path: str | None,
    fmt: str,
    dep_sensitivity: float,
) -> None:
    """Batch-score a CSV dataset. Registries are built from the full input file."""
    from safer_model.config import SAFERConfig

    in_path = Path(input_path)
    if not in_path.exists():
        click.echo(f"Error: input file '{in_path}' not found.", err=True)
        sys.exit(1)

    click.echo(f"Loading records from {in_path} …")
    records = load_csv(in_path)
    click.echo(f"  {len(records)} records loaded.")

    config = SAFERConfig(dep_sensitivity=dep_sensitivity)
    scorer = SAFERScorer(records=records, config=config)

    click.echo("Scoring …")
    results = scorer.score_all()

    # Determine output path
    if output_path is None:
        stem = in_path.stem
        output_path = str(in_path.parent / f"{stem}_results.csv")

    if fmt == "csv":
        results_to_csv(results, output_path)
        click.echo(f"Results written to {output_path}")
    else:
        out = json.dumps([r.model_dump() for r in results], indent=2)
        if output_path:
            Path(output_path).write_text(out)
            click.echo(f"Results written to {output_path}")
        else:
            click.echo(out)

    # Print quick band summary
    _print_band_summary(results)


# ── safer score-one ────────────────────────────────────────────────────────────

@cli.command("score-one")
@click.option(
    "--json", "-j", "json_str",
    required=True,
    help="JSON string representing a single SoftwareRecord.",
)
@click.option(
    "--pretty/--no-pretty",
    default=True,
    show_default=True,
    help="Pretty-print the JSON output.",
)
def score_one(json_str: str, pretty: bool) -> None:
    """Score a single software record from a JSON string (standalone mode)."""
    try:
        record = load_json(json_str)
    except Exception as exc:
        click.echo(f"Error parsing record: {exc}", err=True)
        sys.exit(1)

    scorer = SAFERScorer()
    result = scorer.score(record)

    indent = 2 if pretty else None
    click.echo(json.dumps(result.model_dump(), indent=indent))


# ── safer report ──────────────────────────────────────────────────────────────

@cli.command("report")
@click.option(
    "--input", "-i", "input_path",
    required=True,
    help="Results CSV file (output of `safer score`).",
)
def report(input_path: str) -> None:
    """Print a summary table of risk bands and score statistics from a results CSV."""
    import pandas as pd

    in_path = Path(input_path)
    if not in_path.exists():
        click.echo(f"Error: file '{in_path}' not found.", err=True)
        sys.exit(1)

    df = pd.read_csv(in_path)

    click.echo("\n── SAFER Risk Assessment Report ──────────────────────────────────")
    click.echo(f"  Records: {len(df)}\n")

    if "band" in df.columns:
        click.echo("Risk Band Distribution:")
        band_counts = df["band"].value_counts()
        for band in ["Low", "Moderate", "High", "Critical"]:
            count = band_counts.get(band, 0)
            pct = 100 * count / len(df)
            bar = "█" * int(pct / 2)
            click.echo(f"  {band:<10} {count:5d}  ({pct:5.1f}%)  {bar}")

    if "r_fp" in df.columns:
        click.echo(f"\nR_FP Statistics:")
        click.echo(f"  mean   = {df['r_fp'].mean():.4f}")
        click.echo(f"  median = {df['r_fp'].median():.4f}")
        click.echo(f"  std    = {df['r_fp'].std():.4f}")
        click.echo(f"  min    = {df['r_fp'].min():.4f}")
        click.echo(f"  max    = {df['r_fp'].max():.4f}")

    click.echo("─────────────────────────────────────────────────────────────────\n")


# ── safer analyze ──────────────────────────────────────────────────────────────

@cli.command("analyze")
@click.argument("repo")
@click.option(
    "--token", "-t",
    default=None,
    envvar="GITHUB_TOKEN",
    help="GitHub Personal Access Token (or set GITHUB_TOKEN env var).",
)
@click.option(
    "--context", "-c",
    type=click.Choice(["0.2", "0.3", "0.5"]),
    default="0.5",
    show_default=True,
    help="Software context: 0.2=security, 0.3=automation, 0.5=other.",
)
@click.option(
    "--pkg-name", "-p",
    default=None,
    help=(
        "Override the package registry name when it differs from the GitHub repo name. "
        "E.g. for repo 'vercel/next.js' the npm package is 'next'."
    ),
)
@click.option(
    "--output", "-o", "output_dir",
    default=".",
    show_default=True,
    help="Directory to write output files.",
)
@click.option(
    "--format", "-f", "formats",
    type=click.Choice(["json", "md", "csv"]),
    multiple=True,
    default=["json"],
    show_default=True,
    help="Output format(s). May be specified multiple times.",
)
@click.option(
    "--ref", "-r",
    default=None,
    help=(
        "Git ref (tag, branch, or commit SHA) to analyse a specific historical "
        "version, e.g. --ref v4.3.1 or --ref abc1234. "
        "Omit to analyse the current HEAD."
    ),
)
@click.option(
    "--pretty/--no-pretty",
    default=True,
    show_default=True,
    help="Pretty-print JSON output.",
)
def analyze(
    repo: str,
    token: str | None,
    context: str,
    pkg_name: str | None,
    output_dir: str,
    formats: tuple[str, ...],
    ref: str | None,
    pretty: bool,
) -> None:
    """Fetch data from GitHub and score REPO with SAFER.

    REPO must be in 'owner/repo' format, e.g. ultralytics/ultralytics or expressjs/express.

    For npm packages whose registry name differs from the GitHub repo name,
    use --pkg-name to specify the correct name (e.g. --pkg-name next for vercel/next.js).

    Use --ref to analyse a specific historical version (tag, branch, or commit SHA).

    Output files are written to the output directory with the naming scheme:
    {owner}_{repo}_safer_result.json / .md / .csv
    (when --ref is given: {owner}_{repo}_{ref}_safer_result.json / .md / .csv)
    """
    import warnings
    from pathlib import Path

    from safer_model.fetcher import GitHubFetcher
    from safer_model.scorer import SAFERScorer

    ctx_val = float(context)

    # ── Fetch ──────────────────────────────────────────────────────────────────
    ref_label = f" @ {ref}" if ref else ""
    click.echo(f"Fetching data for {repo}{ref_label} …")
    fetcher = GitHubFetcher(token=token)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        record, raw = fetcher.fetch(repo, context=ctx_val, pkg_name=pkg_name, ref=ref)

    for w in caught:
        click.echo(f"  [warn] {w.message}", err=True)

    click.echo(f"  language      : {raw['language']}")
    click.echo(f"  registry      : {raw.get('registry', 'github')}  (pkg: {raw.get('pkg_name', '')})")
    click.echo(f"  stars         : {raw['stars']}")
    click.echo(f"  forks         : {raw['forks']}")
    click.echo(f"  downloads/mo  : {raw['downloads']:,}")
    click.echo(f"  code lines    : {raw['code_length_est']:,}")
    click.echo(f"  dependencies  : {raw['dependencies']}")
    click.echo(f"  coverage      : {raw['code_coverage']:.0%}")
    click.echo(f"  known vulns   : {raw['known_vulnerabilities']}")
    click.echo(f"  unresolved    : {raw['unresolved_vulnerabilities']}")
    click.echo(f"  update freq   : {raw['update_frequency']:.3f}")
    click.echo(f"  years active  : {raw['years_active']}")

    # ── Score ──────────────────────────────────────────────────────────────────
    click.echo("\nScoring …")
    scorer = SAFERScorer()
    result = scorer.score(record)

    band_colors = {
        "Low": "green",
        "Moderate": "yellow",
        "High": "red",
        "Critical": "bright_red",
    }
    band_str = click.style(result.band.value, fg=band_colors.get(result.band.value, "white"), bold=True)
    click.echo(f"\n  R_FP = {result.r_fp:.4f}  →  {band_str}\n")

    # ── Write output files ─────────────────────────────────────────────────────
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    # Include sanitised ref in filename when analysing a historical version
    ref_suffix = f"_{ref.replace('/', '-')}" if ref else ""
    stem = repo.replace("/", "_") + ref_suffix

    written: list[str] = []

    if "json" in formats:
        payload = {**result.model_dump(), "raw_data": raw}
        indent = 2 if pretty else None
        json_text = json.dumps(payload, indent=indent, default=str)
        json_file = out_path / f"{stem}_safer_result.json"
        json_file.write_text(json_text, encoding="utf-8")
        written.append(str(json_file))

    if "md" in formats:
        md_text = _build_markdown_report(repo, result, raw, ref=ref)
        md_file = out_path / f"{stem}_safer_report.md"
        md_file.write_text(md_text, encoding="utf-8")
        written.append(str(md_file))

    if "csv" in formats:
        from safer_model.io import results_to_csv
        csv_file = out_path / f"{stem}_safer_result.csv"
        results_to_csv([result], csv_file)
        written.append(str(csv_file))

    click.echo("Output files:")
    for f in written:
        click.echo(f"  {f}")


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _build_markdown_report(
    repo: str,
    result: "SAFERResult",
    raw: dict,
    ref: str | None = None,
) -> str:
    """Generate a human-readable Markdown risk report."""
    from datetime import datetime, timezone
    from safer_model.schemas.output import SAFERResult  # noqa: F811

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    band = result.band.value
    band_emoji = {"Low": "🟢", "Moderate": "🟡", "High": "🔴", "Critical": "🚨"}.get(band, "")

    ref_label = f"@{ref}" if ref else ""
    ref_date_str = raw.get("ref_date", "")

    lines = [
        f"# SAFER 风险分析报告：{repo}{ref_label}",
        "",
        f"> 生成时间：{now}",
        *(([f"> 分析版本：`{ref}`（提交时间：{ref_date_str[:10]}）"]) if ref else []),
        "",
        "---",
        "",
        "## 总结",
        "",
        f"| 指标 | 值 |",
        f"|------|---|",
        f"| **风险等级** | {band_emoji} **{band}** |",
        f"| **R_FP 最终分数** | `{result.r_fp:.4f}` |",
        f"| **R_F（惩罚前）** | `{result.r_f:.4f}` |",
        f"| **惩罚项 P** | `{result.penalty:.4f}` |",
        "",
        "---",
        "",
        "## 采集数据",
        "",
        "| 字段 | 值 |",
        "|------|---|",
        f"| 主要语言 | {raw.get('language', 'N/A')} |",
        f"| GitHub Stars | {raw.get('stars', 0):,} |",
        f"| GitHub Forks | {raw.get('forks', 0):,} |",
        f"| 月下载量 | {raw.get('downloads', 0):,} |",
        f"| 估算代码行数 | {raw.get('code_length_est', 0):,} |",
        f"| 依赖数量 | {raw.get('dependencies', 0)} |",
        f"| 测试覆盖率 | {raw.get('code_coverage', 0.0):.0%} |",
        f"| 已知漏洞 | {raw.get('known_vulnerabilities', 0)} |",
        f"| 未修复漏洞 | {raw.get('unresolved_vulnerabilities', 0)} |",
        f"| 更新频率 | {raw.get('update_frequency', 0.0):.3f} |",
        f"| 活跃年限 | {raw.get('years_active', 0.0)} 年 |",
        f"| 发布版本数 | {raw.get('release_count', 0)} |",
        "",
        "---",
        "",
        "## 中间分数",
        "",
        "| 组件 | 分数 | 说明 |",
        "|------|-----|------|",
        f"| R_CD（依赖风险） | `{result.r_cd:.4f}` | 依赖数 × 灵敏度 |",
        f"| R_CS（代码规格风险） | `{result.r_cs:.4f}` | w_LC × 代码行数 |",
        f"| R_PL（语言风险） | `{result.r_pl:.4f}` | 语言经验不足程度 |",
        f"| R_DEV（开发者风险） | `{result.r_dev:.4f}` | 综合开发者能力风险 |",
        f"| R_PB（发布者风险） | `{result.r_pb:.4f}` | 发布历史与频率 |",
        f"| R_UR（用户风险） | `{result.r_ur:.4f}` | 社区信任度反向指标 |",
        "",
        "### 权重",
        "",
        "| 权重 | 值 | 说明 |",
        "|------|---|------|",
        f"| w_DEV | `{result.w_dev:.4f}` | 开发者参与者权重（与 Fork 数成反比） |",
        f"| w_PB | `{result.w_pb:.4f}` | 发布者参与者权重 |",
        f"| w_UR | `{result.w_ur:.4f}` | 用户参与者权重 |",
        f"| w_LC | `{result.w_lc:.4f}` | 历史漏洞率 |",
        f"| e_db | `{result.e_db:.4f}` | 开发者专业度 |",
        "",
        "---",
        "",
        "## 诊断建议",
        "",
    ]

    # Auto-generate diagnostic tips
    tips: list[str] = []

    if result.r_cs > 5.0:
        tips.append(
            "**R_CS 偏高**：开发者历史漏洞率（w_LC）较大，建议检查该组织其他仓库是否存在重复 CVE 模式。"
        )
    if result.r_pb > 0.5:
        tips.append(
            "**R_PB 偏高**：发布更新频率偏低或发布历史较短，建议确认最新版本是否及时修复了安全问题。"
        )
    if result.r_ur > 0.8:
        tips.append(
            "**R_UR 偏高**：相对下载量而言 Star 数偏低，该包可能主要作为间接依赖被引入，需留意供应链风险。"
        )
    if result.penalty > 0.05:
        tips.append(
            f"**惩罚项已触发**（P = {result.penalty:.4f}）：存在未修复漏洞，建议检查 Dependabot 告警并及时升级。"
        )
    if raw.get("known_vulnerabilities", 0) == 0 and not raw.get("_token_used"):
        tips.append(
            "**漏洞数据为 0**：未提供 GitHub Token，无法查询安全通告。"
            "请使用 `--token` 参数获取真实漏洞数量。"
        )
    if result.band.value in ("High", "Critical"):
        tips.append(
            f"**风险等级 {result.band.value}**：在集成到生产环境前，建议进行完整的安全审查。"
        )

    if not tips:
        tips.append("未发现显著风险信号，维持常规监控即可。")

    for tip in tips:
        lines.append(f"- {tip}")

    lines += [
        "",
        "---",
        "",
        "## 风险等级说明",
        "",
        "| 等级 | R_FP 范围 | 建议措施 |",
        "|------|---------|---------|",
        "| 🟢 Low（低） | [0.00, 0.25) | 可用于生产；持续监控安全通告 |",
        "| 🟡 Moderate（中） | [0.25, 0.50) | 审查未修复漏洞；跟踪更新频率 |",
        "| 🔴 High（高） | [0.50, 0.75) | 集成前需进行安全审查 |",
        "| 🚨 Critical（严重） | [0.75, 1.00] | 未经审计不得使用 |",
        "",
        "---",
        "",
        "*由 [SAFER Model](https://arxiv.org/abs/2408.02876v2) 自动生成*",
    ]

    return "\n".join(lines)


def _print_band_summary(results: list) -> None:
    from collections import Counter
    bands = Counter(r.band.value for r in results)
    click.echo("\nRisk Band Summary:")
    for band in ["Low", "Moderate", "High", "Critical"]:
        count = bands.get(band, 0)
        click.echo(f"  {band:<10} {count}")
    click.echo()


if __name__ == "__main__":
    cli()
