Short Description
-----------------
Local/remote execution of PROFILES_GEN preprocessor to GACODE suite tools

Keywords
--------
GACODE, statefile, input.gacode

Long Description
----------------
Runs the GACODE utility profiles_gen to convert various inputs into the GACODE standard file input.gacode

PROFILES_GEN converts various common plasma description files into the format read by the GACODE tools such as GYRO, CGYRO, TGYRO, TGLF and NEO

This module also includes the ability to reorder the ions in the file, as well as add and remove ions.

* Generate GACODE-compatible profiles from EPED run (dead-start or blend with existing input.gacode)
* Allows (parallel) execution of NEO at multiple radii using experimental input profiles
* Generate synthetic CER file from NEO run
* GUI for batch execution on series of equilibria, statefile, and CER files
* Check/enforce quasineutrality
* Reorder the ion species

Typical workflows
-----------------
1) Start with input.gacode

   * Load from disk or OMFIT tree

2) Start with statefile and (optional) gfile

   * Load statefile from disk or OMFIT tree
   * Run profiles_gen to create input.gacode

3) Start with statefile and (optional) gfile from TRANSP TRXPL

   * Enable TRXPL
   * Fill out TRANSP run information
   * Extract statefile
   * Run profiles_gen to create input.gacode

Supported devices
-----------------
* Device independent

Tutorials
---------
Included in TGYRO, TGLF and GYRO tutorials

External resources
------------------
* `input gacode on GitHub GACODE website <http://gafusion.github.io/doc/input_gacode.html>`_
