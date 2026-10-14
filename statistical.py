import math
def wilson_lower(wins, samples, z=1.64):
    """One-sided empirical lower bound; even a perfect sample is not certainty."""
    n=int(samples)
    if n<=0:
        return 0.0
    p=max(0.0,min(1.0,float(wins)/n))
    zz=float(z)**2
    return max(0.0,(p+zz/(2*n)-float(z)*math.sqrt(p*(1-p)/n+zz/(4*n*n)))/(1+zz/n))