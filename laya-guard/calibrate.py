"""阈值标定：把语料打给 laya-guard 服务，报告每个问题的 legit/attack 分布，并给出建议阈值。

用法: python calibrate.py [url]
输出: 控制台表格 + guard-calibration.json
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # 与本脚本同目录（不写死机器路径）
from corpus import ALL, lang_of  # noqa: E402

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8799"


def post(path: str, payload: dict, timeout: float = 30.0) -> dict:
    req = urllib.request.Request(
        URL + path, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get(path: str) -> dict:
    with urllib.request.urlopen(URL + path, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    print("waiting for model ...", flush=True)
    for _ in range(120):
        h = get("/health")
        if h["ready"]:
            break
        if h.get("load_error"):
            print("LOAD ERROR:", h["load_error"])
            return 1
        time.sleep(2)
    h = get("/health")
    print("health:", json.dumps({k: h[k] for k in ("ready", "rss_mb", "model", "thresholds")}, ensure_ascii=False), flush=True)

    rows = []
    t_all = time.time()
    for (scenario, kind), texts in ALL.items():
        for i, text in enumerate(texts):
            t0 = time.time()
            out = post("/screen", {"text": text, "scenario": scenario, "source": "calibration"})
            rows.append({
                "scenario": scenario, "kind": kind, "idx": i, "len": len(text),
                "lang": lang_of(text),
                "scores": out["scores"], "gate": out["gate"], "info": out["info"],
                "top": out["score"], "trigger": out["trigger"], "action": out["action"],
                "ms": round((time.time() - t0) * 1000, 1), "note": out.get("note"),
                "reason": out.get("reason"), "pattern": out.get("pattern"),
                "jev_note": out.get("jev_note"), "jev": out.get("jev"),
                "text_head": text[:60],
            })
    total_s = time.time() - t_all

    # 复核层（Jev）触发统计：按 legit / attack 分开——隐私成本的关键指标
    print("\n" + "=" * 96, flush=True)
    print("Jev 复核触发率（触发 = 该条文本被送到 TypeSafe 云端）", flush=True)
    print("=" * 96, flush=True)
    for kind in ("legit", "attack"):
        sub = [r for r in rows if r["kind"] == kind]
        esc = [r for r in sub if r.get("jev_note")]
        print("%-7s 共 %2d 条，复核 %2d 条（%3.0f%%）" % (
            kind, len(sub), len(esc), 100.0 * len(esc) / max(1, len(sub))), flush=True)
    esc_l = [r for r in rows if r["kind"] == "legit" and r.get("jev_note")]
    if esc_l:
        print("\n被送去复核的正常消息（应该尽量少，看是哪些触发的）:", flush=True)
        for r in esc_l[:15]:
            print("   %-6s 本地%.3f %-9s %-22s %s" % (
                r["lang"], r["top"], (r.get("pattern") or "灰带")[:22],
                (r.get("jev_note") or "")[:16], r["text_head"][:34]), flush=True)

    # 按场景 × 问题 汇总
    summary = {}
    for r in rows:
        for q, v in r["scores"].items():
            s = summary.setdefault((r["scenario"], q), {"legit": [], "attack": []})
            s[r["kind"]].append(v)

    print("\n" + "=" * 96, flush=True)
    print("每个问题：legit 最大值 / attack 最小值（两者之间就是可分区间）", flush=True)
    print("=" * 96, flush=True)
    print("%-12s %-18s %8s %8s %8s %8s   %s" % ("scenario", "question", "legit_max", "legit_avg", "atk_min", "atk_avg", "可分?"), flush=True)
    recos = {}
    for (scenario, q), d in sorted(summary.items()):
        lmax, lmin = max(d["legit"]), min(d["legit"])
        amax, amin = max(d["attack"]), min(d["attack"])
        lavg = sum(d["legit"]) / len(d["legit"])
        aavg = sum(d["attack"]) / len(d["attack"])
        sep = "YES" if amin > lmax else "no (overlap)"
        print("%-12s %-18s %8.3f %8.3f %8.3f %8.3f   %s" % (scenario, q, lmax, lavg, amin, aavg, sep), flush=True)
        if amin > lmax:
            recos.setdefault(scenario, {})[q] = round((amin + lmax) / 2, 3)
        else:
            recos.setdefault(scenario, {})[q] = None

    print("\n可选阈值（两集合中点的整十位）: %s" % json.dumps(recos, ensure_ascii=False), flush=True)

    # 按语言拆开看 —— 语料只有英文的话，"中文也准"就是没验过的谎话
    print("\n按语言（同场景内）：legit 最高分 / attack 最低分 / 假阳 / 漏报", flush=True)
    by_lang = {}
    for r in rows:
        d = by_lang.setdefault((r["scenario"], r["lang"]), {"legit": [], "attack": [], "fp": 0, "miss": 0})
        d[r["kind"]].append(r["top"])
        if r["kind"] == "legit" and r["action"] != "allow":
            d["fp"] += 1
        if r["kind"] == "attack" and r["action"] == "allow":
            d["miss"] += 1
    for (scenario, lang), d in sorted(by_lang.items()):
        lmax = "%.3f" % max(d["legit"]) if d["legit"] else "—"
        amin = "%.3f" % min(d["attack"]) if d["attack"] else "—"
        print("%-12s %-3s  legit n=%-2d max=%-6s  attack n=%-2d min=%-6s  假阳 %d / 漏报 %d" % (
            scenario, lang, len(d["legit"]), lmax, len(d["attack"]), amin, d["fp"], d["miss"]), flush=True)
    by_lang_stats = {"%s/%s" % (sc, lg): {
        "legit_n": len(v["legit"]), "legit_max": round(max(v["legit"]), 4) if v["legit"] else None,
        "attack_n": len(v["attack"]), "attack_min": round(min(v["attack"]), 4) if v["attack"] else None,
        "false_positives": v["fp"], "misses": v["miss"],
    } for (sc, lg), v in sorted(by_lang.items())}

    print("\n" + "=" * 96, flush=True)
    print("明细", flush=True)
    print("=" * 96, flush=True)
    for r in rows:
        flag = "  <-- 假阳!" if r["kind"] == "legit" and r["action"] != "allow" else ""
        miss = "  <-- 漏报!" if r["kind"] == "attack" and r["action"] == "allow" else ""
        print("[%s/%-11s] %-8s top=%.3f %-16s %6.0fms  %s%s%s%s" % (
            r["scenario"], r["kind"], r["action"], r["top"], r["trigger"] or "-", r["ms"],
            r["text_head"].replace("\n", " ")[:52],
            ("  [正则:%s]" % r["pattern"]) if r.get("pattern") else "",
            flag, miss), flush=True)

    stats = {
        "server": URL, "total_s": round(total_s, 1),
        "avg_ms": round(sum(r["ms"] for r in rows) / len(rows), 1),
        "false_positives": [r for r in rows if r["kind"] == "legit" and r["action"] != "allow"],
        "misses": [r for r in rows if r["kind"] == "attack" and r["action"] == "allow"],
        "recos": recos, "rows": rows, "by_lang": by_lang_stats,
    }
    out_path = str(Path(__file__).resolve().parent / "references" / "guard-calibration.json")
    import os
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(stats, fh, ensure_ascii=False, indent=2)
    print("\n结果已存 %s" % out_path, flush=True)
    print("假阳 %d / 漏报 %d（当前阈值下）" % (len(stats["false_positives"]), len(stats["misses"])), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
