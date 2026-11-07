#!/usr/bin/env python3
"""Fetch the latest same-day Science shortlist for editorial handoff.

Requires the official GitHub CLI (gh) and an authenticated session:
  gh auth login
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


DEFAULT_REPOSITORY = "Aaron-Z13/learningos-news"
WORKFLOW = "science-collector.yml"
TIMEZONE = ZoneInfo("Asia/Shanghai")


class HandoffError(RuntimeError):
    pass


def run_gh(*args: str) -> str:
    try:
        result = subprocess.run(
            ["gh", *args],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise HandoffError("未找到 gh CLI，请先安装 GitHub CLI。") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise HandoffError(f"GitHub API/gh CLI 调用失败：{detail[:500]}")
    return result.stdout


def load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HandoffError(f"无法读取 {label}：{exc}") from exc
    if not isinstance(value, dict):
        raise HandoffError(f"{label} 不是 JSON 对象。")
    return value


def local_date_from_iso(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HandoffError(f"日期格式无效：{value!r}") from exc
    return parsed.astimezone(TIMEZONE).date().isoformat()


def list_successful_runs(repository: str) -> list[dict]:
    raw = run_gh(
        "run",
        "list",
        "--repo",
        repository,
        "--workflow",
        WORKFLOW,
        "--status",
        "success",
        "--limit",
        "20",
        "--json",
        "databaseId,createdAt,updatedAt,headBranch,event,status,conclusion",
    )
    try:
        runs = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HandoffError("无法解析 GitHub Actions Run 列表。") from exc
    return [run for run in runs if isinstance(run, dict)]


def download_shortlist(repository: str, run_id: int, directory: Path) -> tuple[Path, Path]:
    run_gh(
        "run",
        "download",
        str(run_id),
        "--repo",
        repository,
        "--name",
        "science-shortlist",
        "--dir",
        str(directory),
    )
    shortlist_path = directory / "science-shortlist.json"
    metadata_path = directory / "science-shortlist-run.json"
    if not shortlist_path.exists() or not metadata_path.exists():
        raise HandoffError(
            f"Run {run_id} 的 science-shortlist Artifact 缺少 "
            "science-shortlist.json 或 science-shortlist-run.json。"
        )
    return shortlist_path, metadata_path


def validate_handoff(
    run: dict,
    shortlist: dict,
    metadata: dict,
    target_date: str,
) -> dict:
    run_id = int(run.get("databaseId", 0))
    if run_id <= 0:
        raise HandoffError("GitHub Run ID 无效。")

    collector_run_id = metadata.get("collectorRunId")
    shortlist_run_id = metadata.get("shortlistRunId")
    attempt = metadata.get("collectorRunAttempt")
    if collector_run_id != run_id or shortlist_run_id != run_id:
        raise HandoffError(
            f"Artifact 来源不匹配：Run {run_id}，"
            f"metadata collectorRunId={collector_run_id!r}，"
            f"shortlistRunId={shortlist_run_id!r}。"
        )
    if not isinstance(attempt, int) or attempt <= 0:
        raise HandoffError("collectorRunAttempt 不是有效正整数。")

    collected_at = metadata.get("collectorCollectedAt")
    if not isinstance(collected_at, str) or local_date_from_iso(collected_at) != target_date:
        raise HandoffError(
            f"采集日期不是目标日期 {target_date}：{collected_at!r}"
        )

    collector_status = metadata.get("collectorStatus")
    if collector_status not in {"complete", "partial"}:
        raise HandoffError(f"采集状态无效：{collector_status!r}")

    source = shortlist.get("source")
    statistics = shortlist.get("statistics")
    papers = shortlist.get("papers")
    if not isinstance(source, dict) or not isinstance(statistics, dict) or not isinstance(papers, list):
        raise HandoffError("science-shortlist.json 缺少有效 source/statistics/papers。")
    if source.get("collectorStatus") != collector_status:
        raise HandoffError("Shortlist 与运行元数据的 collectorStatus 不一致。")
    if source.get("collectorCollectedAt") != collected_at:
        raise HandoffError("Shortlist 与运行元数据的采集时间不一致。")

    candidate_count = source.get("collectorCount")
    shortlist_count = statistics.get("selected")
    if not isinstance(candidate_count, int) or candidate_count < 0:
        raise HandoffError("候选数量无效。")
    if not isinstance(shortlist_count, int) or shortlist_count != len(papers):
        raise HandoffError("初筛数量与 papers 数量不一致。")

    abstract_rate = statistics.get("abstractFetchRate")
    if not isinstance(abstract_rate, (int, float)) or not 0 <= abstract_rate <= 1:
        raise HandoffError("摘要获取率无效。")

    return {
        "sourceRun": {
            "repository": run.get("headBranch") and run.get("headBranch") or "main",
            "runId": run_id,
            "runAttempt": attempt,
            "workflow": WORKFLOW,
            "event": run.get("event"),
            "createdAt": run.get("createdAt"),
            "updatedAt": run.get("updatedAt"),
        },
        "collection": {
            "date": target_date,
            "collectedAt": collected_at,
            "status": collector_status,
            "candidateCount": candidate_count,
        },
        "shortlisting": {
            "selectedCount": shortlist_count,
            "abstractFetchRate": abstract_rate,
            "sourceErrors": statistics.get("sourceErrors", []),
            "bySubject": statistics.get("bySubject", {}),
            "scoreDistribution": statistics.get("scoreDistribution", {}),
        },
        "papers": papers,
        "handoffNote": "仅供编辑审查；未生成、未发布新闻。",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="获取当天 Science 编辑资料")
    parser.add_argument("--repo", default=DEFAULT_REPOSITORY)
    parser.add_argument("--date", help="目标北京时间日期，格式 YYYY-MM-DD；默认今天")
    parser.add_argument("--output", default="editorial-input.json")
    args = parser.parse_args()

    target_date = args.date or datetime.now(TIMEZONE).date().isoformat()
    try:
        datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        print("日期格式必须是 YYYY-MM-DD。", file=sys.stderr)
        return 2

    try:
        runs = list_successful_runs(args.repo)
        with tempfile.TemporaryDirectory(prefix="learningos-science-handoff-") as temp:
            root = Path(temp)
            candidates = []
            for run in runs:
                try:
                    run_date = local_date_from_iso(str(run.get("createdAt", "")))
                except HandoffError:
                    continue
                if run_date != target_date:
                    continue
                run_dir = root / str(run.get("databaseId"))
                run_dir.mkdir()
                shortlist_path, metadata_path = download_shortlist(
                    args.repo, int(run["databaseId"]), run_dir
                )
                shortlist = load_json(shortlist_path, "science-shortlist.json")
                metadata = load_json(metadata_path, "science-shortlist-run.json")
                try:
                    handoff = validate_handoff(run, shortlist, metadata, target_date)
                except HandoffError:
                    continue
                handoff["repository"] = args.repo
                handoff["generatedAt"] = datetime.now(TIMEZONE).isoformat()
                candidates.append(handoff)
                break

            if not candidates:
                raise HandoffError("无可用编辑资料")

            Path(args.output).write_text(
                json.dumps(candidates[0], ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(
                json.dumps(
                    {
                        "status": "ready",
                        "output": args.output,
                        "runId": candidates[0]["sourceRun"]["runId"],
                        "candidateCount": candidates[0]["collection"]["candidateCount"],
                        "shortlistCount": candidates[0]["shortlisting"]["selectedCount"],
                        "abstractFetchRate": candidates[0]["shortlisting"]["abstractFetchRate"],
                    },
                    ensure_ascii=False,
                )
            )
            return 0
    except HandoffError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
