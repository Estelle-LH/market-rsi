"""Audit score stability across already-opened hourly Final sessions.

This is a diagnostic only.  It never trains, opens a new evaluation period, or
contacts a provider.  The audit compares one-hour scores with deterministic
four-hour and same-date blocks while preserving the frozen v4 model outputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path


ARMS = ("baseline", "fresh", "archive", "compact")


def load_json(path: Path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def session_name(path: Path) -> str:
    return path.stem.removeprefix("final-")


def load_sessions(run: Path):
    rows = []
    for path in sorted(run.glob("final-20??-??-??T??.json")):
        session = session_name(path)
        timestamp = datetime.strptime(session, "%Y-%m-%dT%H")
        scores = load_json(path)
        if set(scores) != set(ARMS):
            raise ValueError(f"{path}: expected exactly {ARMS}")
        dates = {scores[arm]["date"] for arm in ARMS}
        ns = {scores[arm]["n"] for arm in ARMS}
        caches = {scores[arm]["cache_sha256"] for arm in ARMS}
        zeros = {scores[arm]["zero_labels"] for arm in ARMS}
        if dates != {session} or len(ns) != 1 or len(caches) != 1 or len(zeros) != 1:
            raise ValueError(f"{path}: arms do not share identical evaluation rows")
        header_path = run / "data" / session / "header.json"
        header = load_json(header_path)
        if header["shape"][0] != next(iter(ns)):
            raise ValueError(f"{header_path}: row count differs from score")
        rows.append({
            "session": session,
            "timestamp": timestamp,
            "date": session[:10],
            "n": next(iter(ns)),
            "zero_labels": next(iter(zeros)),
            "market_hashes": header["market_hashes"],
            "source": str(path),
            "source_sha256": file_sha256(path),
            "header": str(header_path),
            "header_sha256": file_sha256(header_path),
            "scores": scores,
        })
    if len(rows) < 20:
        raise ValueError("at least 20 already-opened Final sessions are required")
    return rows


def contiguous(rows) -> bool:
    return all(right["timestamp"] - left["timestamp"] == timedelta(hours=1)
               for left, right in zip(rows, rows[1:]))


def make_blocks(sessions):
    by_date = defaultdict(list)
    for row in sessions:
        by_date[row["date"]].append(row)
    for rows in by_date.values():
        rows.sort(key=lambda item: item["timestamp"])

    blocks = {"one_hour": [], "four_hour": [], "same_date_five_hour": []}
    for row in sessions:
        blocks["one_hour"].append({"id": row["session"], "sessions": [row]})
    for date, rows in sorted(by_date.items()):
        if len(rows) != 5 or not contiguous(rows):
            raise ValueError(f"{date}: expected five consecutive opened Final hours")
        blocks["four_hour"].append({
            "id": f"{date}:{rows[0]['session'][-2:]}-{rows[3]['session'][-2:]}",
            "sessions": rows[:4],
            "selection": "fixed earliest four consecutive hours; fifth hour excluded",
        })
        blocks["same_date_five_hour"].append({
            "id": date,
            "sessions": rows,
            "selection": "all five opened consecutive hours on the date",
        })
    return blocks


def aggregate(block):
    rows = block["sessions"]
    total_n = sum(row["n"] for row in rows)
    result = {
        "id": block["id"],
        "sessions": [row["session"] for row in rows],
        "hours": len(rows),
        "rows": total_n,
        "zero_label_fraction": sum(row["zero_labels"] for row in rows) / total_n,
        "unique_market_hashes": len({value for row in rows for value in row["market_hashes"]}),
        "arms": {},
    }
    if "selection" in block:
        result["selection"] = block["selection"]
    for arm in ARMS:
        metrics = [row["scores"][arm] for row in rows]
        result["arms"][arm] = {
            "equal_session_mse": statistics.fmean(item["candidate_mse"] for item in metrics),
            "row_weighted_mse": sum(item["candidate_mse"] * item["n"] for item in metrics) / total_n,
            "equal_session_calibration_slope": statistics.fmean(
                item["calibration_slope"] for item in metrics),
            "equal_session_pearson_ic": statistics.fmean(item["pearson_ic"] for item in metrics),
            "hour_wins_vs_baseline": sum(
                row["scores"][arm]["candidate_mse"]
                < row["scores"]["baseline"]["candidate_mse"] for row in rows),
        }
    base = result["arms"]["baseline"]["equal_session_mse"]
    for arm in ARMS:
        score = result["arms"][arm]["equal_session_mse"]
        result["arms"][arm]["relative_improvement_vs_baseline"] = 1.0 - score / base
    fresh = result["arms"]["fresh"]["equal_session_mse"]
    archive = result["arms"]["archive"]["equal_session_mse"]
    result["archive_relative_improvement_vs_fresh"] = 1.0 - archive / fresh
    result["ranking"] = sorted(ARMS,
        key=lambda arm: result["arms"][arm]["equal_session_mse"])
    return result


def summarize(groups):
    summary = {}
    for unit, blocks in groups.items():
        comparisons = [block["archive_relative_improvement_vs_fresh"] for block in blocks]
        improvements = {
            arm: [block["arms"][arm]["relative_improvement_vs_baseline"] for block in blocks]
            for arm in ARMS
        }
        summary[unit] = {
            "blocks": len(blocks),
            "hours_per_block": sorted({block["hours"] for block in blocks}),
            "archive_wins_vs_fresh": sum(value > 0 for value in comparisons),
            "archive_ties_vs_fresh": sum(math.isclose(value, 0.0, abs_tol=1e-15)
                                         for value in comparisons),
            "archive_vs_fresh_mean_relative_improvement": statistics.fmean(comparisons),
            "archive_vs_fresh_stdev": statistics.stdev(comparisons)
                if len(comparisons) > 1 else 0.0,
            "relative_improvement_vs_baseline": {
                arm: {
                    "mean": statistics.fmean(values),
                    "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
                    "min": min(values),
                    "max": max(values),
                    "positive_blocks": sum(value > 0 for value in values),
                }
                for arm, values in improvements.items()
            },
        }
    return summary


def pct(value: float) -> str:
    return f"{100.0 * value:+.2f}%"


def render_report(audit) -> str:
    summary = audit["summary"]
    lines = [
        "# V4 已打开 Final 的反馈块稳定性审计",
        "",
        "## 这次检查什么",
        "",
        "只使用 v4 已经打开的 20 个 Final 小时，不训练、不调用模型、不打开新数据。",
        "比较单小时、每个日期固定的连续 4 小时、以及同一日期已有的连续 5 小时。",
        "现有 Final 每个日期只有 5 个已选小时，因此本报告**没有真正的 24 小时全日证据**。",
        "",
        "## 汇总",
        "",
        "| 单位 | 块数 | Archive 赢 Fresh | Archive 相对 Fresh 平均 | 波动（标准差） |",
        "|---|---:|---:|---:|---:|",
    ]
    for unit in ("one_hour", "four_hour", "same_date_five_hour"):
        item = summary[unit]
        lines.append(
            f"| {unit} | {item['blocks']} | {item['archive_wins_vs_fresh']}/{item['blocks']} "
            f"| {pct(item['archive_vs_fresh_mean_relative_improvement'])} "
            f"| {pct(item['archive_vs_fresh_stdev'])} |")
    lines += ["", "## 每个日期的 5 小时块", "",
              "| 日期 | Baseline MSE | Fresh vs Base | Archive vs Base | Archive vs Fresh | Compact vs Base | 排名 |",
              "|---|---:|---:|---:|---:|---:|---|"]
    for block in audit["blocks"]["same_date_five_hour"]:
        arms = block["arms"]
        lines.append(
            f"| {block['id']} | {arms['baseline']['equal_session_mse']:.8g} "
            f"| {pct(arms['fresh']['relative_improvement_vs_baseline'])} "
            f"| {pct(arms['archive']['relative_improvement_vs_baseline'])} "
            f"| {pct(block['archive_relative_improvement_vs_fresh'])} "
            f"| {pct(arms['compact']['relative_improvement_vs_baseline'])} "
            f"| {' < '.join(block['ranking'])} |")
    lines += [
        "",
        "## 结论边界",
        "",
        "- 这是已经打开数据上的 post-hoc 诊断，不能作为新的 promotion evidence。",
        "- 四小时块固定取每个日期最早的四个连续小时；没有根据分数选择窗口。",
        "- 五小时日期块比一小时更接近独立反馈单位，但仍不是完整 UTC 日。",
        "- 下一版必须先冻结真正的多小时或跨日期 block 规则，再打开新 Dev/Final。",
        "",
    ]
    return "\n".join(lines)


def audit(run: Path, output: Path):
    if output.exists():
        raise FileExistsError(f"refusing to overwrite {output}")
    sessions = load_sessions(run)
    blocks = make_blocks(sessions)
    aggregated = {unit: [aggregate(block) for block in values]
                  for unit, values in blocks.items()}
    result = {
        "schema": "market_rsi_opened_final_block_stability_v1",
        "run": str(run),
        "diagnostic_only": True,
        "provider_calls": 0,
        "new_evaluation_sessions_opened": 0,
        "full_utc_day_available": False,
        "full_utc_day_reason": "v4 Final contains five consecutive selected hours per date, not 24",
        "source_manifest": [{key: row[key] for key in
            ("session", "source", "source_sha256", "header", "header_sha256")}
            for row in sessions],
        "blocks": aggregated,
        "summary": summarize(aggregated),
    }
    output.mkdir(parents=True)
    write_json(output / "audit.json", result)
    (output / "report.md").write_text(render_report(result), encoding="utf-8")
    write_json(output / "complete.json", {
        "complete": True,
        "audit_sha256": file_sha256(output / "audit.json"),
        "report_sha256": file_sha256(output / "report.md"),
        "provider_calls": 0,
        "new_evaluation_sessions_opened": 0,
    })
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.run, args.output)
    print(json.dumps({"complete": True, "summary": result["summary"]}, sort_keys=True))


if __name__ == "__main__":
    main()
