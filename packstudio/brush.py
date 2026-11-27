"""Pixel-aligned square brush footprints, shared by all canvas views."""
def stroke_points(a,b,size=1):
    size=max(1,min(128,int(size)));offset=size//2
    dx,dy=b[0]-a[0],b[1]-a[1];steps=max(abs(dx),abs(dy),1)
    for i in range(steps+1):
        x,y=round(a[0]+dx*i/steps),round(a[1]+dy*i/steps)
        for sy in range(y-offset,y-offset+size):
            for sx in range(x-offset,x-offset+size):yield sx,sy
