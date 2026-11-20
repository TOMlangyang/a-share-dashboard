#!/usr/bin/env python3
"""历史交易日涨跌停回补。仅保存成功获取的数据，不伪造缺失快照。"""
from __future__ import annotations
import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
HISTORY=ROOT/"data"/"history"
TZ=ZoneInfo("Asia/Shanghai")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOG=logging.getLogger("backfill")

def main():
    p=argparse.ArgumentParser(description="回填已收盘交易日股票池")
    p.add_argument("--start",required=True,help="开始日 YYYY-MM-DD")
    p.add_argument("--end",required=True,help="结束日 YYYY-MM-DD")
    p.add_argument("--limit",type=int,default=30,help="单次最多30个交易日")
    a=p.parse_args()
    if not 1<=a.limit<=40:
        p.error("limit 必须在1到40之间")
    start=date.fromisoformat(a.start)
    end=date.fromisoformat(a.end)
    now=datetime.now(TZ)
    cutoff=now.date() if now.time()>=dtime(16,0) else now.date()-timedelta(days=1)
    if end>cutoff or start>end:
        p.error(f"日期范围无效：最晚只能补录到已收盘的 {cutoff}")
    import akshare as ak
    calendar=(ak.calendar_trade_date_hist_sina()
              if hasattr(ak,"calendar_trade_date_hist_sina")
              else ak.tool_trade_date_hist_sina())
    if calendar is None or calendar.empty or "trade_date" not in calendar.columns:
        raise RuntimeError("交易日历不可用，取消回补")
    dates=sorted(date.fromisoformat(str(x)[:10]) for x in calendar.trade_date
                 if start.isoformat()<=str(x)[:10]<=end.isoformat())
    if len(dates)>a.limit:
        p.error(f"区间内有 {len(dates)} 个交易日，超过上限 {a.limit}，请缩小范围")
    LOG.info("回补 %s 至 %s，交易日数=%d",start,end,len(dates))
    done=skipped=0
    failed=[]
    for i,day in enumerate(dates,1):
        path=HISTORY/f"{day.isoformat()}.json"
        if path.exists():
            try:
                d=json.loads(path.read_text(encoding="utf-8"))
                if d.get("status")=="verified" and d.get("date")==day.isoformat():
                    skipped+=1
                    LOG.info("[%d/%d] 已归档 %s，跳过",i,len(dates),day)
                    continue
            except (OSError,ValueError):
                pass
        LOG.info("[%d/%d] 开始采集 %s",i,len(dates),day)
        env=os.environ.copy()
        env["TRADE_DATE"]=day.isoformat()
        try:
            proc=subprocess.run([sys.executable,str(ROOT/"scripts"/"update_data.py")],
                                cwd=ROOT,env=env,capture_output=True,text=True,timeout=100)
            if proc.returncode==0 and path.exists():
                done+=1
                LOG.info("采集成功 %s",day)
            else:
                failed.append(day.isoformat())
                LOG.error("采集失败 %s: %s",day,(proc.stdout+proc.stderr)[-1000:])
        except subprocess.TimeoutExpired:
            failed.append(day.isoformat())
            LOG.error("采集超时 %s",day)
        time.sleep(0.7)
    LOG.info("回补完成：成功=%d，原有=%d，失败=%d；失败日期=%s",
             done,skipped,len(failed),",".join(failed) or "无")
    if failed:
        (ROOT/"data"/"backfill_failures.json").write_text(
            json.dumps({"date_range":[a.start,a.end],"failed":failed,
                        "recorded_at":datetime.now(TZ).isoformat()},ensure_ascii=False,indent=2),
            encoding="utf-8")
    return 2 if failed else 0

if __name__=="__main__":
    sys.exit(main())
