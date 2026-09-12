Short Description
-----------------
Run the TGYRO code to get inputs for and then run TGLF at various radii

Keywords
--------
Experimental fluxes, Reduced model, Gyrokinetic fluxes

Long Description
----------------
This module orchestrates the running of various GACODE pieces: profiles_gen, TGYRO, TGLF, to start from an experimental power balance calculation, and then perform a sensitivity analysis of TGLF at various radii either to investigate straight sensitivity or to calculate particle D and V from TGLF.

Typical workflows
-----------------
This module is used to:

* calculate radial profiles of TGLF growth rates and fluxes
* calculate radial profiles of TGLF particle D and V
* calculate TGLF sensitivity to input parameters at various radii

Supported devices
-----------------
* Any device for which profiles_gen processing of power balance is available, which includes TRANSP, ONETWO, ASTRA, etc.

Tutorials
---------
* `Google docs <https://docs.google.com/document/d/1ggFvm3IfqqTRs1EqJiXS7mGbfOAmUPnd1MrZTOhh8xM>`_
* `PDF <https://docs.google.com/document/d/1ggFvm3IfqqTRs1EqJiXS7mGbfOAmUPnd1MrZTOhh8xM/export?format=pdf>`_
* `YouTube Video <https://www.youtube.com/watch?v=rjGLHIN8cwI&index=3&list=PLdksEfhRAD67q1fGDlZMAYcWSO8BlhbK5>`_

Relevant publications
---------------------
* See the TGLF module publications

External resources
------------------
* `TGLF on the GA GACODE website <https://fusion.gat.com/theory/Tglfoverview>`_ (needs GA account)
* `TGLF on the GitHub GACODE website <http://gafusion.github.io/doc/tglf.html>`_
