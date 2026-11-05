"""Frozen small candidate set; all forecasts use training observations only."""
import warnings
import numpy as np
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tools.sm_exceptions import ConvergenceWarning

MODELS=['seasonal_naive','lagged_ols','holt_winters']

def validate(y):
    y=np.asarray(y,dtype=float)
    if y.ndim!=1 or len(y)<12 or not np.isfinite(y).all() or (y<=0).any():
        raise ValueError('At least 12 finite positive quarterly observations required')
    return y

def features(logs,t):
    # Index zero is Q1; no current-quarter or future observed values.
    q=t%4+1
    return np.array([1,logs[t-1],logs[t-4],q==2,q==3,q==4],dtype=float)

def forecast(y,model,horizon=1):
    y=validate(y)
    if not isinstance(horizon,int) or isinstance(horizon,bool) or horizon<1:raise ValueError('Positive integer horizon required')
    if model not in MODELS:raise ValueError('Unknown model')
    extra={}
    if model=='seasonal_naive':
        values=list(y)
        for _ in range(horizon):values.append(values[-4])
        out=np.array(values[-horizon:])
    elif model=='lagged_ols':
        logs=list(np.log(y));x=np.array([features(logs,t) for t in range(4,len(logs))])
        beta,_,rank,_=np.linalg.lstsq(x,np.array(logs[4:]),rcond=None)
        if rank!=6:raise ValueError('Rank-deficient revenue regression')
        for _ in range(horizon):logs.append(float(features(logs,len(logs))@beta))
        out=np.exp(logs[-horizon:])
        extra={'coefficients':beta.tolist(),'condition_number':float(np.linalg.cond(x)),
               'log_retransform':'exp fitted log level; no mean bias adjustment'}
    else:
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter('always')
            fit=ExponentialSmoothing(y,trend='add',damped_trend=True,seasonal='add',seasonal_periods=4,initialization_method='estimated').fit(optimized=True,use_brute=True)
        bad=[str(w.message) for w in captured if issubclass(w.category,ConvergenceWarning)]
        if bad:raise RuntimeError('Holt-Winters convergence failure: '+'; '.join(bad))
        out=np.asarray(fit.forecast(horizon))
        extra={'optimizer_success':bool(fit.mle_retvals.get('success',True)),
               'warnings':[str(w.message) for w in captured]}
        if not extra['optimizer_success']:raise RuntimeError('Optimizer did not converge')
    if not np.isfinite(out).all() or (out<=0).any():raise ValueError('Nonpositive/nonfinite forecast: review model')
    return out,extra

def metrics(actual,pred):
    a=np.asarray(actual,dtype=float);p=np.asarray(pred,dtype=float)
    if a.ndim!=1 or p.ndim!=1 or a.shape!=p.shape or a.size==0 or (a<=0).any() or not np.isfinite(a).all() or not np.isfinite(p).all():raise ValueError('Invalid metric inputs')
    e=p-a
    return dict(n=int(a.size),mae=float(np.abs(e).mean()),rmse=float(np.sqrt((e**2).mean())),mape_pct=float((np.abs(e)/a).mean()*100),bias=float(e.mean()))

def profit_regression(revenue,profit,future_revenue):
    # An accounting association used for a conditional projection, not causality.
    r=np.asarray(revenue,dtype=float);p=np.asarray(profit,dtype=float)
    future=np.asarray(future_revenue,dtype=float)
    if r.ndim!=1 or p.ndim!=1 or future.ndim!=1 or len(r)!=len(p) or len(r)<12 or len(future)==0:
        raise ValueError('At least 12 paired observations and 1-D future revenue required')
    if not all(np.isfinite(x).all() for x in [r,p,future]) or (r<=0).any() or (future<=0).any():
        raise ValueError('Finite inputs and positive revenues required')
    x=np.column_stack([np.ones(len(r)),r])
    beta,_,rank,_=np.linalg.lstsq(x,p,rcond=None)
    if rank!=2:raise ValueError('Rank-deficient profit regression')
    residual=p-x@beta
    total=float(np.sum((p-p.mean())**2))
    r2=None if total==0 else float(1-np.sum(residual**2)/total)
    projected=beta[0]+beta[1]*future
    if not np.isfinite(projected).all():raise ValueError('Nonfinite profit projection')
    return projected,dict(intercept=float(beta[0]),revenue_coefficient=float(beta[1]),n=len(r),r2=r2)

PROFIT_MODELS=['level_ols_12','trailing_margin_4','delta_ols_12']

def conditional_profit(rows,future_revenue,method):
    """Project profits from known financials; no realized future revenue input."""
    future=np.asarray(future_revenue,dtype=float)
    if future.ndim!=1 or len(future)==0 or not np.isfinite(future).all() or (future<=0).any():raise ValueError('Positive finite future revenues required')
    if len(rows)<13:raise ValueError('At least 13 ordered quarterly rows required')
    revenue=np.array([x['revenue'] for x in rows],dtype=float)
    profit=np.array([x['operating_profit'] for x in rows],dtype=float)
    if not np.isfinite(revenue).all() or not np.isfinite(profit).all() or (revenue<=0).any():raise ValueError('Invalid profit history')
    if method=='level_ols_12':return profit_regression(revenue[-12:],profit[-12:],future)
    if method=='trailing_margin_4':
        margin=float(profit[-4:].sum()/revenue[-4:].sum())
        return future*margin,dict(trailing_margin=margin)
    if method!='delta_ols_12':raise ValueError('Unknown conditional profit model')
    dr=np.diff(revenue[-13:]);dp=np.diff(profit[-13:])
    x=np.column_stack([np.ones(12),dr])
    coef,_,rank,_=np.linalg.lstsq(x,dp,rcond=None)
    if rank!=2:raise ValueError('Rank-deficient profit change regression')
    projected=[];previous_r=revenue[-1];previous_p=profit[-1]
    for value in future:
        previous_p=previous_p+coef[0]+coef[1]*(value-previous_r)
        projected.append(float(previous_p));previous_r=value
    if not np.isfinite(projected).all():raise ValueError('Nonfinite profit projection')
    return np.array(projected),dict(change_intercept=float(coef[0]),change_revenue_coefficient=float(coef[1]))


def revenue_forecast(y,method,horizon=1):
    """The equally weighted blend is fixed; no fit to evaluation outcomes."""
    if method=='equal_blend':
        left,_=forecast(y,'lagged_ols',horizon);right,_=forecast(y,'holt_winters',horizon)
        return (left+right)/2,dict(weights={'lagged_ols':.5,'holt_winters':.5})
    return forecast(y,method,horizon)
