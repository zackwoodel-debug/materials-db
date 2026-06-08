# Physics primer

## What XRR measures

X-ray reflectometry (XRR) shines a collimated beam of X-rays at a flat surface and records how much is reflected as a function of the angle of incidence, expressed through the momentum transfer Q = 4π sin θ / λ. Each buried interface between materials of different electron density reflects a small fraction of the beam. The reflected waves from all interfaces interfere, producing oscillations in the reflectivity curve whose period is inversely proportional to layer thickness and whose envelope encodes the electron density contrast and interfacial roughness. A single measurement can therefore recover the thickness, density, and roughness of every layer in a thin-film stack without destroying the sample.

## The Parratt stack model

The stack is modelled as a sequence of laterally uniform slabs, each described by three numbers:

```
  Air / vacuum
  -------------  interface 0
  Layer 1  (SLD1, d1, s1)
  -------------  interface 1
  Layer 2  (SLD2, d2, s2)
  -------------  interface 2
  Substrate (semi-infinite)
```

SLD (scattering length density) measures how strongly a layer scatters X-rays; for X-rays it equals the electron density times the classical electron radius and is tabulated from bulk mass density and chemical formula. d is the physical thickness of the layer in ångströms, and s is the root-mean-square roughness of the lower interface, which smears the sharp reflection coefficient via the Nevot-Croce factor exp(−2 k_zj k_z(j+1) σ²).

## Recursion in plain terms

Start at the deepest interface and work upward. At each step, the reflected amplitude depends on the amplitude coming back from below.

The recursion combines the local Fresnel reflection coefficient at the current interface with the phase accumulated while the wave travels through the layer above it. After propagating through all layers in this bottom-up pass, the amplitude at the top interface is squared to give the measured reflectivity R.
