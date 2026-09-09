# COM convention

Reference: [Automatic extraction and design of SAW resonator COM parameters via PSO-P matrix joint optimization](https://www.sciencedirect.com/science/article/pii/S0041624X26001125), displayed COM equations; [The Extraction of Coupling-of-Modes Parameters in a Layered Piezoelectric Substrate and Its Application to a Double-Mode SAW Filter](https://pmc.ncbi.nlm.nih.gov/articles/PMC10745400/), Eq. (4), for P-matrix limiting checks. These are model references, not sources of the hypothetical numeric parameters.

Use exp(+jωt), x increasing left to right, peak voltage V and terminal current I into the transducer. R,S are forward/backward complex acoustic envelopes. The acoustic average power flux is |R|²−|S|² in this normalization.

```
dR/dx = −jδ R + jκ S + jα V
dS/dx = −jκ* R + jδ S − jα* V
dI/dx = −2jα* R − 2jα S + jω C V
δ = ω/v − 2π/λ − jγ
```

For gaps, replace δ by ω/v−jγ and set κ=α=C=0. γ is an amplitude attenuation coefficient, obtained from dB per wavelength by ln(10)/(20λ). κ,δ,γ: m⁻¹; α: sqrt(Siemens)/m; C: F/m; v: m/s. Material phases enter complex κ and α explicitly. Aperture scales C linearly and α by its square root. Metallization and thickness are fixed metadata, without a claimed physical interpolation.

For constant V, let A be the 2×2 acoustic differential matrix, b=(jα,−jα*)ᵀ, c=(−2jα*,−2jα). Define T=exp(AL), F=∫exp(Ax)dx, H=∫(L−x)exp(Ax)dx. Then u(L)=Tu(0)+FbV and I=cFu(0)+(cHb+jωCL)V. Since A²=(|κ|²−δ²)I, entire hyperbolic functions give T,F,H. Taylor limits avoid division by zero at synchronism; no inverse(A) is used.

Eliminate S(0) from S(L) to form [S(0),R(L),I]ᵀ=P[R(0),S(L),V]ᵀ. Outgoing waves of adjacent blocks equal incoming waves. External acoustic incoming waves are zero (radiating ends). A global linear solve eliminates 18 internal acoustic amplitudes. Electrical center ground selects Vc=0; floating uses Yext=Yee−Yec Ycc⁻¹ Yce.

Phase registry: each periodic block uses its local envelope origin and busbar voltage convention. At the boundary its amplitudes are connected directly; gaps carry exp(−jωL/v−γL). This is an explicit idealized registry, not a derived electrode-edge layout. A calibrated provider and actual electrode polarity/offset mapping are required before fabrication.

Independent analytic limits: lossless κ=0 at synchronism gives P13=P23=jαL for real α and P33=2α²L²+jωCL. A synchronous lossless reflector gives P11=j tanh(κL), P12=sech(κL) for real positive κ. Tests also compare the full augmented differential-system exponential, its split-length product, and electrical reciprocity/passivity. Finite dissipation and outgoing acoustic radiation account for electrical conductance.

Diagnostics report minimum Hermitian conductance eigenvalue and absolute reciprocity residual. Singular solves and nonfinite/nonpassive results fail explicitly. Very large κL overflow is not stabilized by section subdivision in this prototype; default ranges keep κL modest. General block condition-number logging remains future work.
