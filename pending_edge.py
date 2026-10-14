def clamp(x,a=0.0,b=1.0):return max(a,min(b,float(x)))

class PendingEdge:
    def __init__(self,cfg):self.cfg=cfg
    def pending_edge(self,plan,quality,activation,perf,regime,external_bias=0.0):
            rr=max(.05,min(8.0,float(getattr(plan,'rr',0.0) or 0.0)))
            q=clamp(float(quality)/100.0); a=clamp(float(activation)/100.0)
            structural=('H1' in str(getattr(plan,'key','')).upper() or 'H4' in str(getattr(plan,'key','')).upper() or 'STRUCTURAL' in str(getattr(plan,'reason','')).upper())
            # Structural H1/H4 candidates are quality-first. Activation is deliberately
            # a weak term there: a nearer mediocre zone must not beat a materially
            # stronger structural thesis just because it is easier to trigger.
            if structural:
                technical=clamp(.25+.46*q+.035*a+.07+max(-.05,min(.05,float(external_bias)*.05)),.15,.84)
            else:
                technical=clamp(.25+.38*q+.12*a+max(-.05,min(.05,float(external_bias)*.05)),.15,.82)
            n=int((perf or {}).get('samples',0) or 0)
            empirical=float((perf or {}).get('regularized_win_rate',(perf or {}).get('win_rate',.5)))
            conf=clamp(float((perf or {}).get('confidence',0) or 0))
            p=clamp(technical*(1-.40*conf)+empirical*(.40*conf),.12,.86)
            ev=p*rr-(1-p)
            activation_proxy=clamp(.05+.90*a)
            joint_ev=ev*activation_proxy
            if structural:
                utility=100*clamp(.72*q+.05*a+.15*clamp((ev+1)/3)+.08*clamp((joint_ev+1)/3))
            else:
                utility=100*clamp(.50*q+.20*a+.17*clamp((ev+1)/3)+.13*clamp((joint_ev+1)/3))
            return {'p_success_proxy':p,'activation_proxy':activation_proxy,'ev_r':ev,'joint_ev_r':joint_ev,
                    'utility':utility,'empirical_samples':n, 'calibrated':False,
                    'evidence_state':'HEURÍSTICO / SIN PROBABILIDAD VALIDADA',
                    'disclosure':'Un proxy de score no es una probabilidad estimada con datos fuera de muestra.'}
