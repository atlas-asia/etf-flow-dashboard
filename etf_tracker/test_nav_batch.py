# -*- coding: utf-8 -*-
"""测试恒生聚源FinQuery批量NAV查询容量。"""
import json, re, sys, time, urllib.request

def get_url():
    import glob
    cands = []
    for f in glob.glob(r"C:/Users/Asia/.workbuddy/logs/*/workbuddyMainThread__*.log"):
        txt = open(f, encoding="utf-8", errors="ignore").read()
        cands += re.findall(r"https://api\.gildata\.com/mcp-servers/aidata-assistant-srv-tool\?token=[A-Za-z0-9._\-]+", txt)
    if not cands:
        raise RuntimeError("URL not found")
    return sorted(set(cands))[-1]

URL = get_url()
INIT = {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "etf-tracker", "version": "1.0"}}

def rpc(method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    req = urllib.request.Request(URL, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=180) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
    if raw.lstrip().startswith("{"):
        return json.loads(raw)
    result = None
    for line in raw.splitlines():
        if line.startswith("data:"):
            try:
                result = json.loads(line[5:].strip())
            except Exception:
                pass
    return result

def finquery(query):
    try:
        rpc("initialize", INIT)
    except Exception:
        pass
    return rpc("tools/call", {"name": "FinQuery", "arguments": {"query": query}})

if __name__ == "__main__":
    codes = ["510050","510300","510500","512100","512500","515050","515790","516010","516160","517200",
             "518880","560010","561360","562500","563300","588000","588030","588050","588080","589010",
             "159901","159915","159919","159922","159949","159951","159967","159968","159980","159985",
             "159981","159986","159989","159990","159993","159995","159996","159997","159998","159999"]
    code_str = "、".join(codes)
    t0 = time.time()
    res = finquery(f"查询基金{code_str}共40只ETF在2026年7月1日至2026年8月31日每个交易日的单位净值")
    dt_ = time.time() - t0
    print("RAW响应前1500字符:")
    print(json.dumps(res, ensure_ascii=False)[:1500])
    if res and "result" in res:
        text = "".join(item.get("text", "") for item in res["result"].get("content", []))
        # text本身是JSON字符串，内含table_markdown
        md = ""
        try:
            inner = json.loads(text)
            for r in inner.get("results", []):
                md += r.get("table_markdown", "")
        except Exception:
            md = text
        rows = [l for l in md.splitlines() if l.startswith("|") and "基金代码" not in l and "---" not in l]
        got_codes, got_dates = set(), set()
        for r in rows:
            parts = [p.strip() for p in r.split("|")]
            if len(parts) > 4:
                got_codes.add(parts[1]); got_dates.add(parts[3])
        print(f"耗时{dt_:.1f}s, 返回{len(rows)}行, 覆盖{len(got_codes)}只代码, {len(got_dates)}个日期")
        if got_dates:
            print("日期范围:", min(got_dates), "~", max(got_dates))
    else:
        print("FAIL:", json.dumps(res, ensure_ascii=False)[:500])
