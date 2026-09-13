# Electrical network convention

All currents point into the device. I=YV, peak phasors exp(+jωt). Average absorbed power is Re(VᴴI)/2. Positive, real Rs and Rl are supported independently; complex reference impedances are not supported.

With Thevenin open-circuit source Vs=1, solve (Y+diag(1/Rs,1/Rl))V=[1/Rs,0]ᵀ. PL=|V2|²/(2Rl), Pavs=1/(8Rs), GT=4Rs|V2|²/Rl. IL=−10log10(GT). No available-power renormalization is hidden in the model.

For D=diag(sqrt(Rs),sqrt(Rl)), define Yn=DYD and S=(I+Yn)⁻¹(I−Yn). The incoming/outgoing power waves are (V±RI)/(2sqrt(2R)); with these peak phasors their squared magnitudes have units W. Thus GT=|S21|² for the chosen real source/load terminations. Γin=(1−Rs Yin)/(1+Rs Yin), Yin=Y11−Y12Y21/(Y22+1/Rl), equals S11. Exchange indices for Γout=S22. VSWR=(1+|Γ|)/(1−|Γ|); the denominator is floored at 1e−14 for numerical reporting.

Z=Y⁻¹ only when nonsingular; no inversion is needed by the power evaluator. Ideal direct connection has no finite Y matrix; tests use a vanishing series resistance and the known through limit. A series Zs has GT=4RsRl/|Rs+Rl+Zs|². Real, reactive, RLC-at-a-frequency and matched shunt cases validate gain and reflection independently of COM. Dedicated general Z conversion APIs are deferred.
