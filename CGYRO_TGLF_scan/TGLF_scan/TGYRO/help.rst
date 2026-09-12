Short Description
-----------------
Runs the steady state TGYRO transport code

Keywords
--------
transport, turbulent, neoclassical, steady-state, core-pedestal, GACODE

Long Description
----------------
TGYRO manages execution of multiple instances of the kinetic neoclassical code NEO and the gyrokinetic code GYRO or the quasiliear code TGLF.
Equilbrium profiles of density and temperature are modified by Newton iteration until measured losses from collisions (NEO) and turbulence (GYRO or TGLF) balance experimental power and density sources.

Typical workflows
-----------------
* Setup of geometry
* Pick what equations to evolve
* Newton solver controls
* Iteration with or without self-consistent EPED1-NN pedestal model
* Profiles scalings and particle sources
* Selection of turbulent TGLF/GYRO/IFS and neoclassical NEO/Chang-Hinton/Hinton-Hazeltine models to use
* Support running and viewing multiple simulations stored on remote server
* Profiles as function of radius or iteration
* Comparison of target, initial and final fluxes
* Fluxes convergence for different iterations

Supported devices
-----------------
* Device independent

Tutorials
---------
* DIII-D
  * `Google docs <https://docs.google.com/document/d/14XXzOqQ0YARZrZsRQMgv7fll_0V6EF-da7RWgchM05E>`_
  * `PDF <https://docs.google.com/document/export?format=pdf&id=14XXzOqQ0YARZrZsRQMgv7fll_0V6EF-da7RWgchM05E&token=AC4w5VjciVWW8p_f8zqcmdvnnzJXMB51rw%3A1554244335314&includes_info_params=true>`_
  * `YouTube video <https://www.youtube.com/watch?v=rjGLHIN8cwI&index=3&list=PLdksEfhRAD67q1fGDlZMAYcWSO8BlhbK5>`_

* ITER
  * `Google docs <https://docs.google.com/document/d/1g3VStisQ1wIrhn__rkDQ4sBiv7VZcOiLZzbDMvKw1Lg/edit?usp=sharing>`_
  * `PDF <https://docs.google.com/document/export?format=pdf&id=1g3VStisQ1wIrhn__rkDQ4sBiv7VZcOiLZzbDMvKw1Lg&token=AC4w5VipgAXUCbfJ2uI9G3tidgRWhSaMFw%3A1554239840631&includes_info_params=true>`_

Relevant publications
---------------------
* `J. Candy, C. Holland, R. Waltz, M. Fahey and E. Belli, Tokamak profile prediction using direct gyrokinetic and neoclassical simulation, Phys. Plasmas 16 (2009) 060704 <http://aip.scitation.org/doi/full/10.1063/1.3167820>`_

External resources
------------------
* `TGYRO on the GA GACODE website <https://fusion.gat.com/theory/Tgyrooverview>`_ (needs GA account)
* `TGYRO on the GitHub GACODE website <http://gafusion.github.io/doc/tgyro.html>`_
