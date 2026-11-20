#!/usr/bin/env python3
"""收盘后更新沪深主板普通A股涨跌停看板。失败时不覆盖上一份已成功快照。"""
from __future__ import annotations
import json
import logging
import os
import re
import sys
from collections import Counter
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
TZ = ZoneInfo('Asia/Shanghai')
LOG = logging.getLogger('market')
VALID_PREFIXES = ('600','601','603','605','000','001','002','003')


def eligible(code, name):
    """严格代码白名单 + 名称黑名单；仍以交易所个股状态为准。"""
    code = str(code).strip().zfill(6)
    name = str(name or '').strip().upper()
    if not re.fullmatch(r'\d{6}', code) or not code.startswith(VALID_PREFIXES):
        return False
    if re.search(r'\*?ST|退市|退\b|PT|^N[\u4e00-\u9fff]|^C[\u4e00-\u9fff]', name):
        return False
    # 新上市前5个交易日可能不设涨跌幅限制，数据源涨停池有误时还应人工核验。
    return True


def num(v, default=None):
    try:
        if v is None or str(v).lower() in ('nan', 'none', '--', ''):
            return default
        n = float(str(v).replace(',', '').replace('%', ''))
        if n != n or n in (float('inf'), float('-inf')):
            return default
        return n
    except (ValueError, TypeError):
        return default


def intnum(v, default=0):
    val = num(v)
    return max(0, int(val)) if val is not None else default


def grab(r, *fields):
    for field in fields:
        if field in r and r[field] is not None:
            return r[field]
    return None


def hhmmss(v):
    s = str(v or '').strip()
    if not s or s.lower() in ('nan','none','0','--'):
        return ''
    if ':' in s:
        parts = s.split(':')
        return ':'.join(parts[:2]) if len(parts) > 1 else ''
    s = ''.join(x for x in s if x.isdigit())
    if len(s) in (3,4,5,6):
        return s.zfill(6)[:2] + ':' + s.zfill(6)[2:4]
    return ''


def nm_stat(stat, streak):
    s = str(stat or '').strip()
    match = re.search(r'(\d+)\s*(?:天|个交易日|[/／-])\s*(\d+)\s*(?:板)?', s)
    if match:
        n, m = map(int, match.groups())
        if 0 < m <= n <= 100:
            return n, m
    # Some sources only supply streak count. Do not make up an N日M板 pattern.
    if streak and streak >= 1:
        return streak, streak
    return None, None


def validate_pool(df, label):
    if df is None or df.empty:
        raise RuntimeError(f'{label}数据为空：不发布不完整快照')
    if not {'代码','名称'}.issubset(set(df.columns)):
        raise RuntimeError(f'{label}字段不符合预期: {list(df.columns)}')
    return df


def normalize(df, kind):
    rows = []
    for r in df.to_dict('records'):
        code = str(grab(r,'代码','code') or '').strip().zfill(6)
        name = str(grab(r,'名称','name') or '').strip()
        if not eligible(code, name):
            continue
        price = num(grab(r,'最新价','现价','收盘价','price'))
        pct = num(grab(r,'涨跌幅','change_pct'))
        if price is None or price <= 0 or pct is None:
            continue
        if kind == 'up' and pct < 8:
            continue
        if kind == 'down' and pct > -8:
            continue
        streak = intnum(grab(r,'连板数','连续涨停','连续跌停','continuous'))
        if kind == 'up' and streak < 1: streak = 1
        n, m = nm_stat(grab(r,'涨停统计','limit_stat'), streak) if kind == 'up' else (None,None)
        industry = str(grab(r,'所属行业','industry','sector') or '行业待核实').strip()
        item = {
            'code':code,'name':name,'price':price,'pct':pct,'industry':industry,
            'sector':industry,'themes':[],'streak':streak,'n_days':n,'m_boards':m,
            'board_type':'', 'first_time':hhmmss(grab(r,'首次封板时间','首次涨停时间')),
            'last_time':hhmmss(grab(r,'最后封板时间','最后涨停时间','最后跌停时间')),
            'seal_amount':num(grab(r,'封板资金','封单资金','封单金额')),
            'turnover':num(grab(r,'换手率')), 'break_times':intnum(grab(r,'炸板次数','开板次数')),
            'reason':'暂无经独立核实的直接涨跌停原因', 'reason_level':'pending',
            'reason_source':'', 'kind':kind,
        }
        rows.append(item)
    return list({r['code']:r for r in rows}.values())


def enrich_reasons(ups, day):
    """第三方公开盘面归因是补充而非事实认证；失败不制造原因。"""
    try:
        import levistock as lk
        raw = lk.stock_zt_pool_cls() if day == datetime.now(TZ).date() else lk.limit_up_his_kph(date=day.isoformat())
        mapping = {}
        for entry in raw or []:
            code = ''.join(c for c in str(entry.get('secu_code') or entry.get('code') or '') if c.isdigit())[-6:]
            reason = str(entry.get('up_reason') or entry.get('reason') or '').strip()
            themes = entry.get('themes') or entry.get('concepts') or ''
            if code and reason:
                mapping[code] = (reason, themes)
        for row in ups:
            if row['code'] in mapping:
                reason, themes = mapping[row['code']]
                row['reason'] = reason[:450]
                row['reason_level'] = 'market' # 必须与公告证实区分
                row['reason_source'] = '财联社/开盘红（第三方市场归因）'
                row['themes'] = [str(x).strip() for x in (themes if isinstance(themes,list) else re.split(r'[、,/，|]',str(themes))) if str(x).strip()][:6]
                if row['themes']:
                    row['sector'] = row['themes'][0]
        LOG.info('原因覆盖率: %s/%s',sum(x['reason_level']=='market' for x in ups), len(ups))
    except Exception as exc:
        LOG.warning('原因补充来源不可用（不会伪造原因）: %s',exc)


def trade_day_checked(day):
    import akshare as ak
    dates = (ak.calendar_trade_date_hist_sina() if hasattr(ak, 'calendar_trade_date_hist_sina') else ak.tool_trade_date_hist_sina())
    if dates is None or dates.empty or 'trade_date' not in dates.columns:
        raise RuntimeError('交易日历核验失败，不使用简单工作日代替')
    return day.isoformat() in set(dates.trade_date.astype(str).str[:10])


def snapshots():
    history = DATA / 'history'
    files = sorted(history.glob('????-??-??.json'), reverse=True)
    result = []
    for p in files:
        try:
            d = json.loads(p.read_text(encoding='utf-8'))
            if d.get('status') == 'verified':
                result.append({'date':d['date'], **d['summary']})
        except (OSError, ValueError):
            continue
    return result


def atomic_json(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    temp.replace(path)


def run():
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    import akshare as ak
    now = datetime.now(TZ)
    # 首次安装和盘前部署也应该显示最近一个已收盘交易日，不使用演示样本。
    # 显式 TRADE_DATE 可用于历史回补，但禁止使用未来或未收盘的数据。
    cutoff = now.date() if now.time() >= time(16,0) else now.date() - timedelta(days=1)
    if os.environ.get('TRADE_DATE'):
        day = date.fromisoformat(os.environ['TRADE_DATE'])
        if day > cutoff:
            raise RuntimeError('TRADE_DATE 尚未到收盘可核实时间，拒绝发布')
        if not trade_day_checked(day):
            raise RuntimeError('TRADE_DATE 非交易日')
    else:
        calendar = (ak.calendar_trade_date_hist_sina() if hasattr(ak, 'calendar_trade_date_hist_sina') else ak.tool_trade_date_hist_sina())
        if calendar is None or calendar.empty or 'trade_date' not in calendar.columns:
            raise RuntimeError('无法核实交易日历，拒绝自动推断')
        tradable_dates = [
            date.fromisoformat(str(x)[:10]) for x in calendar.trade_date
            if str(x)[:10] <= cutoff.isoformat()
        ]
        if not tradable_dates:
            raise RuntimeError('交易日历无有效的已收盘交易日')
        day = max(tradable_dates)
    LOG.info('最新可发布收盘交易日为 %s；当前北京时间 %s', day, now.isoformat(timespec='seconds'))
    # 已保存的同日快照不必重新拉取；每日16点之后仍会运行一次正式更新。
    stamp = day.strftime('%Y%m%d')
    # 主要来源全部成功后才入库，杜绝只抓到一部分就发布。
    up_df = validate_pool(ak.stock_zt_pool_em(date=stamp),'涨停池')
    down_df = ak.stock_zt_pool_dtgc_em(date=stamp)
    if down_df is None or not {'代码','名称'}.issubset(set(down_df.columns)):
        raise RuntimeError('跌停池不可用或字段变化：不发布')
    try:
        broken_df = ak.stock_zt_pool_zbgc_em(date=stamp)
        if broken_df is None or not {'代码','名称'}.issubset(set(broken_df.columns)):
            broken_df = None
    except Exception as exc:
        broken_df = None
        LOG.warning('炸板池不可用: %s', exc)
    ups = normalize(up_df,'up')
    downs = normalize(down_df,'down')
    broken = normalize(broken_df,'broken') if broken_df is not None else []
    if not ups:
        raise RuntimeError('过滤后涨停池为空，可能是接口故障：不覆盖既有数据')
    enrich_reasons(ups, day)
    ups.sort(key=lambda x:(-x['streak'],x['first_time'] or '99:99', x['code']))
    downs.sort(key=lambda x:(-x['streak'],x['pct'],x['code']))
    industries = Counter(x['sector'] for x in ups)
    summary = {
        'up':len(ups),'down':len(downs),'broken':len(broken) if broken_df is not None else None,
        'first':sum(x['streak']==1 for x in ups),'second':sum(x['streak']==2 for x in ups),
        'third_plus':sum(x['streak']>=3 for x in ups), 'max_streak':max(x['streak'] for x in ups),
    }
    payload = {
        'schema_version':1,'status':'verified','date':day.isoformat(),
        'updated_at':now.isoformat(timespec='seconds'),
        'market_scope':'仅沪深主板普通A股，排除全部ST/创业板/科创板/北交所/停牌等',
        'source':'AKShare/东方财富涨跌停池；可选财联社/开盘红市场原因',
        'notes':['收盘池数据口径；未逐笔核验收盘竞价封单，不代表交易所出具的官方封板认证',
                 '原因属于市场归因，并非证明股价因果；暂无来源时标注待核实',
                 '仅代码和名称过滤可能遗漏个别当日风险警示/新股特殊状态，需对接交易所状态清单做最终复核'],
        'summary':summary,'sectors':[{'name':k,'count':v} for k,v in industries.most_common()],
        'stocks':{'up':ups,'down':downs,'broken':broken},
    }
    # 先保存快照，再生成可选择的历史索引。
    atomic_json(DATA/'history'/f'{day.isoformat()}.json',payload)
    # 历史补录不得覆盖较新的主页面快照。
    latest_path = DATA/'latest.json'
    latest_day = ''
    if latest_path.exists():
        try:
            latest_day = str(json.loads(latest_path.read_text(encoding='utf-8')).get('date',''))
        except (OSError, ValueError):
            latest_day = ''
    if not latest_day or day.isoformat() >= latest_day:
        atomic_json(latest_path,payload)
    else:
        LOG.info('历史数据 %s 已归档，主页继续显示 %s', day, latest_day)
    atomic_json(DATA/'history_index.json',{'dates':[p['date'] for p in snapshots()], 'trend':snapshots()})
    LOG.info('数据更新成功：%s 涨停=%d 跌停=%d 炸板=%s',day,len(ups),len(downs),len(broken) if broken_df is not None else '缺失')


if __name__ == '__main__':
    try:
        run()
    except Exception as exc:
        logging.exception('更新失败，保留前次快照：%s',exc)
        sys.exit(1)
