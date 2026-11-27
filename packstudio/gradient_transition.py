"""Monotonic transition mapping shared by rendering and the curve preview."""
def transition_value(t,midpoint=50,width=100,mode='linear',steps=8,curve=((0.,0.),(1.,1.))):
    if t<=0:return 0.
    if t>=1:return 1.
    midpoint=max(.01,min(.99,midpoint/100))
    t=.5*t/midpoint if t<=midpoint else .5+.5*(t-midpoint)/(1-midpoint)
    span=max(0,min(100,width))/100
    t=float(t>=.5) if span==0 else max(0.,min(1.,(t-.5)/span+.5))
    if mode=='smooth':return t*t*(3-2*t)
    if mode=='steps':
        levels=max(2,min(256,int(steps)));return round(t*(levels-1))/(levels-1)
    if mode=='curve':
        for (x0,y0),(x1,y1) in zip(curve,curve[1:]):
            if x0<=t<=x1:return y0+(y1-y0)*(t-x0)/max(1e-9,x1-x0)
    return t
