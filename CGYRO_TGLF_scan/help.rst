Short Description
-----------------
统一管理 CGYRO / TGLF 输入准备、计算运行、结果绘图和工程模板

Keywords
--------
CGYRO, TGLF, GACODE, scans, plotting, templates

Long Description
----------------
The default panel is ``GUIS/main``. It organizes Transfer tool, CGYRO, TGLF,
multi-profile calculations, execution settings, result collection, plotting,
input differences and GitHub templates. Advanced module GUIs remain available.

Prepare and validate CGYRO input through Transfer tool before running from
the workbench. Changing the transferred input or its upstream profiles invalidates
the handoff. Only a submitted/executed run can be collected. Collection archives
the loaded results without resubmitting the scan.

When a TGLF destination already has an input, the workbench displays parameter
differences and waits for an explicit keep/replace choice. It does not merge model
parameters automatically. Replacement archives the old input and its associated
results together. A stale preview cannot overwrite newer inputs. These records
are stored under ``PROJECT_STATE`` and kept with the user's project, not the code
template. Opening the workbench never submits computations or polls a server.

TGYRO-generated local inputs remain stored by radius. The TGLF page lets the user
compare and adopt one as the current single-file input. Radial scans use private
inputs and keep the existing single-file input and results, including on failure.

Execution checks validate configured fields and prerequisites. They do not probe
the solver installation or choose hardware resources automatically. Legacy TGLF
batch scheduling still uses the existing backend.

Compare saved CGYRO linear scans and TGLF spectra or integrated flux scans in
the workbench's plotting page or ``GUIS/CGYRO_vs_TGLF``. The legacy
``GUIS/CGYRO_vs_CGYRO`` shortcut opens the same panel in CGYRO mode.

Panel order
-----------

1. **Cases**: choose the run, source dimension, radii, pairings, and scan values.
2. **Plot**: choose spectra, a growth-rate ratio, CGYRO eigenfunctions, or a
   TGLF flux view. Only applicable controls are shown.
3. **Style**: choose font/line sizes, figure dimensions, grid/log axes,
   legend placement and legend ordering.
4. **Export & checks**: inspect selection messages, export spectra, or show
   the CGYRO status map. Figures can be saved through the figure toolbar.

The Plot and Check selection buttons are above the tabs. In TGLF-only mode,
choose Linear spectra or Integrated flux before choosing the source data.

Selection and data behavior
---------------------------

* Radial and parameter checkboxes follow the underlying keys, not their
  position in a changing list. Selections are retained separately per run
  and TGLF source; a new source starts with an explicit selection.
* The averaging fraction is between 0 and 1: 0.02 requests the final 2% of
  the saved frequency samples (with the existing minimum-tail convention).
* Raw, /ky and /ky-squared display scalings are mutually exclusive.
  Gamma ratios always use gamma itself. Scaling at ky=0 is undefined and
  is displayed as missing, not infinity or zero.
* Model-difference panels require one reference curve in at least one model
  on each page. The difference is normalized to abs(CGYRO), retaining the
  existing 1e-6 denominator floor. CGYRO relative time fluctuation is the
  population standard deviation divided by the absolute mean. It is not
  a standard error or a model-difference estimate.
* Negative gamma and signed omega are retained. Log axes cannot show
  nonpositive values. TGLF has no CGYRO time-fluctuation estimate; no zero
  error curve is invented for it.
* TGLF labels include radius, parameter and mode. In 2D views, para1/para2
  selects the varying scan parameter; the other parameter is held fixed.
* Export creates a new folder and records the normalization and averaging
  settings. Exported omega/gamma values precede display /ky scaling.
  Opening the GUI does not read frequency arrays or launch any solver.

CGYRO self-comparison details
----------------------------

* A blank growth-rate reference uses the first valid selected scan value.
  Explicit references and ky requests snap to the nearest saved value;
  duplicate ky matches count once. Invalid ky input produces an error.
* Spectra-only uses two panels. The optional fluctuation panels share case
  colors with the frequency/growth-rate panels. Legends are finalized once
  per page, using two columns for long lists and automatic height when needed.
* The peak marker selects maximum raw gamma before /ky display scaling.
  Signed spectra, population standard deviations and main-ion scaling retain
  the existing conventions. Saved sample counts must match frequency arrays.
* Single-ky scans preserve missing grid points as gaps. 3D scans use surfaces
  only for complete rectangular grids; incomplete or one-point scans show
  saved points. All 3D pages belong to the OMFIT figure notebook.
* Eigenfunction selection reads balloon data only for the selected ky. Saved
  complex fields are interpolated onto a common theta grid without amplitude
  renormalization. Missing E-parallel data is explicitly labelled; no
  second-derivative reconstruction or extra inductive term is added.
* Raw spectrum export is independent of the selected plot view and writes
  spectrum tables plus metadata.json in a new directory. Existing exports
  remain intact. Missing/filtered samples are recorded in the metadata.

Code organization
-----------------

``GUIS`` and ``PLOTS`` contain short OMFIT entry scripts. The
``LIB/OMFITlib_compare_*`` libraries separate settings, widgets, cases,
data access, numerical helpers, figure styling, spectra, TGLF flux plots,
CGYRO self-comparison, status checks and dispatch/export. Libraries use
explicit imports and are registered in the project save manifest.

The CGYRO self-comparison implementation uses these files:

* ``OMFITlib_compare_cgyro.py``: OMFIT entry, data preparation and page grouping.
* ``OMFITlib_compare_cgyro_selection.py``: settings, parsing and legacy selections.
* ``OMFITlib_compare_cgyro_data.py``: spectra, statistics, scan grids and ratios.
* ``OMFITlib_compare_cgyro_eigen.py``: saved balloon-field extraction and selection.
* ``OMFITlib_compare_cgyro_render.py``: five views, shared colors and page layout.
* ``OMFITlib_compare_cgyro_export.py``: raw spectrum tables and export metadata.

Only the entry depends on OMFIT's FigureNotebook global; the other libraries
can be tested with ordinary Python, NumPy and Matplotlib. New files must be
registered in both the full project and standalone module OMFITsave.txt files.

Validation limits
-----------------

The refactor is tested with saved setting structures, synthetic data,
OMFIT boundary doubles and Matplotlib. Full OMFIT desktop integration,
site-specific solver versions and physical convergence must be verified
in the target environment. Historical calculation results are preserved;
they were not recomputed by this UI/code refactor.
