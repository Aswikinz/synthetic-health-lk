# Notices for bundled components

nehr-synth is distributed under GPL-3.0-or-later; see LICENSE. Synthetic name,
geography and clinical-module fixtures were authored for this application.

* **Synthea v4.0.0** — The MITRE Corporation, Apache License 2.0.
  Unmodified distribution: https://github.com/synthetichealth/synthea/tree/v4.0.0
  The JAR retains its upstream dependency notices and embedded resources.
  The included module supplies artificial test settings, not clinical guidance.
* **HL7 FHIR Java validator 6.10.4** — HL7, BSD-3-Clause.
  https://github.com/hapifhir/org.hl7.fhir.core/tree/6.10.4
  Embedded third-party notices remain in the unmodified validator JAR.
* **Eclipse Temurin JRE 21.0.12.1+1** — OpenJDK contributors, GPL v2 with
  Classpath Exception. The complete JRE legal directory is retained in the image.
  https://github.com/adoptium/temurin21-binaries/releases/tag/jdk-21.0.12.1%2B1
* **FHIR definition packages** — upstream license and package metadata are
  preserved byte-for-byte in archives listed in ig-lock.json. National packages
  are development artifacts, not a receiver-acceptance certificate. HL7 FHIR
  licensing: https://hl7.org/fhir/R4/license.html
* **Textual** — Textualize, MIT License. https://github.com/Textualize/textual
* **Python** — Python Software Foundation License; the base image retains
  its Python and Debian notices. https://docs.python.org/3/license.html

The PHN checksum was independently implemented from the Regenstrief convention
as documented by OpenMRS. Its independent vectors are attributed to OpenMRS
2.7.0, MPL-2.0 and the OpenMRS Healthcare Disclaimer:
https://github.com/openmrs/openmrs-core/blob/2.7.0/LICENSE
No OpenMRS Java implementation is bundled. No SNOMED-to-ICD map is distributed.
LOINC and UCUM identifiers retain their upstream systems; terminology service
responses and their release versions are external validation evidence.
