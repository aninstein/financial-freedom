"""Descriptive statistics over dated, unadjusted cached daily closes; no forecasts."""
from __future__ import annotations

import calendar
import hashlib
import json
import math
import statistics
from collections import defaultdict
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

VERSION = 'historical-descriptive-v1'


def stats(values):
    return {'observations':len(values), 'mean_return':statistics.mean(values) if values else None,
            'median_return':statistics.median(values) if values else None,
            'positive_fraction':sum(v>0 for v in values)/len(values) if values else None}


def analyze(db, instrument_id, years=5):
    instrument_id = instrument_id.strip().upper()
    years = min(10,max(1,int(years)))
    zone = 'America/New_York' if instrument_id.startswith('US:') or instrument_id in {'INDEX:SPX','INDEX:DJIA','INDEX:NASDAQ'} else 'Asia/Shanghai'
    today = datetime.now(ZoneInfo(zone)).date()
    start = date(today.year-years,today.month,min(today.day,calendar.monthrange(today.year-years,today.month)[1]))
    with db() as c:
        rows = c.execute("SELECT bar_time,open,high,low,close,provider,received_at FROM bars WHERE instrument_id=? AND interval='1d' AND adjustment='none' AND bar_time>=? AND bar_time<? ORDER BY bar_time",(instrument_id,start.isoformat(),today.isoformat())).fetchall()
    valid, rejected = [],0
    for row in rows:
        try:
            stamp = date.fromisoformat(row['bar_time'][:10]); close=float(row['close'])
            if not math.isfinite(close) or close<=0: raise ValueError()
            valid.append((stamp,close))
        except (ValueError,TypeError): rejected+=1
    gaps=[]
    if len(valid)<61: gaps.append('不足61根完整日线，部分趋势和相关性统计不可计算。')
    if len({d.year for d,_ in valid})<3: gaps.append('少于三个自然年的样本，月度季节性样本不足。')
    if rejected: gaps.append(f'已排除{rejected}条无效收盘价。')
    dates=[d for d,_ in valid]; closes=[v for _,v in valid]
    returns=[closes[i]/closes[i-1]-1 for i in range(1,len(closes))]
    peak=closes[0] if closes else 0; drawdown=0
    for v in closes:
        peak=max(peak,v); drawdown=min(drawdown,v/peak-1)
    horizons=[{'sessions':n,'return':closes[-1]/closes[-n-1]-1 if len(closes)>n else None} for n in (5,20,60,120,252)]
    ma={str(n):statistics.mean(closes[-n:]) if len(closes)>=n else None for n in (20,60,120,250)}
    trend = 'insufficient'
    if ma['20'] and ma['60']:
        trend = 'upward' if closes[-1]>ma['20']>ma['60'] else ('downward' if closes[-1]<ma['20']<ma['60'] else 'mixed')
    monthly_ends={}
    for d,v in valid: monthly_ends[(d.year,d.month)]=(d,v)
    seasonal=defaultdict(list); monthly=[]
    for (year,month),(d,v) in sorted(monthly_ends.items()):
        prev=(year-1,12) if month==1 else (year,month-1)
        # Current month is unfinished; a missing preceding month is never interpolated.
        if (year,month)>=(today.year,today.month) or prev not in monthly_ends: continue
        value=v/monthly_ends[prev][1]-1
        monthly.append({'month':f'{year}-{month:02d}','return':value,'last_observed_session':d.isoformat()})
        seasonal[month].append(value)
    weekdays=defaultdict(list)
    for d,r in zip(dates[1:],returns):
        weekdays[d.weekday()].append(r)
    correlations=[]
    for lag in (5,20,60):
        n=len(returns)-lag; coefficient=None
        if n>=max(60,lag*3):
            x,y=returns[:-lag],returns[lag:]; mx,my=statistics.mean(x),statistics.mean(y)
            denominator=math.sqrt(sum((v-mx)**2 for v in x)*sum((v-my)**2 for v in y))
            if denominator: coefficient=sum((a-mx)*(b-my) for a,b in zip(x,y))/denominator
        correlations.append({'lag_sessions':lag,'pairs':max(n,0),'return_autocorrelation':coefficient})
    sample=[{'date':d.isoformat(),'close':v} for d,v in valid]
    return {'instrument_id':instrument_id,'method_version':VERSION,'years_requested':years,
            'state':'available' if len(valid)>=20 else 'insufficient','observations':len(valid),
            'first_bar':dates[0].isoformat() if dates else None,'last_bar':dates[-1].isoformat() if dates else None,
            'latest_close':closes[-1] if closes else None,'trend':trend,'moving_averages':ma,'horizons':horizons,
            'annualized_volatility_20d':statistics.stdev(returns[-20:])*math.sqrt(252) if len(returns)>=20 else None,
            'max_drawdown':drawdown if closes else None,'sample_return':closes[-1]/closes[0]-1 if len(closes)>1 else None,
            'monthly_returns':monthly,'seasonality':[{'month':m,**stats(seasonal[m]),'sample_sufficient':len(seasonal[m])>=3} for m in range(1,13)],
            'weekday_returns':[{'weekday':n,**stats(weekdays[n])} for n in range(5)],'return_autocorrelation':correlations,
            'source':sorted({r['provider'] for r in rows}),'received_at':max((r['received_at'] for r in rows),default=None),
            'sample_hash':hashlib.sha256(json.dumps(sample,sort_keys=True).encode()).hexdigest(),
            'data_gaps':gaps,'method_note':'阶段收益按交易观测根数；均线、回撤与波动基于收盘价。月收益为相邻自然月最后观测收盘价之比，跳过本月和缺失前月。日线完整性未由交易所逐日核验；非复权、非含分红总回报。年化波动按252日。',
            'interpretation_note':'季节性与收益自相关只描述历史样本，不是预测、胜率承诺或自动交易信号。缺失交易日、除权除息、幸存者偏差和多重比较均会影响统计。'}
