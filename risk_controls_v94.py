"""V9.4 adaptive risk release. 2% is a ceiling, not a requirement."""
def adaptive_risk_fraction(decision, max_fraction=.02, consecutive_losses=0):
    max_fraction=min(max(float(max_fraction),0.0),.02)
    if consecutive_losses >= 3:
        return 0.0, "CONSECUTIVE LOSS LOCK"
    if getattr(decision,"signal","WAIT") not in {"BUY","SELL"}:
        return 0.0, "NO QUALIFIED SIGNAL"
    s=abs(float(getattr(decision,"score",0.0)))
    confirmations=sum(m.signal==decision.signal for m in getattr(decision,"modules",()))
    if confirmations >= 3 and s >= .45: frac=max_fraction
    elif confirmations >= 2 and s >= .28: frac=min(max_fraction,.01)
    else: frac=min(max_fraction,.005)
    return frac, "ADAPTIVE QUALIFIED RISK"
