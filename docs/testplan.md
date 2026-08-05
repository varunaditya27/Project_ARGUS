# ARGUS Acceptance Test Plan

## What this plan is for

The system must enroll a person correctly, recognize them while masked, reject strangers, survive restarts, and explain uncertain results instead of forcing every face into a match.

---

## Functional Test Cases

| ID | What we test | Expected result | Method |
|---|---|---|---|
| AT-01 | Enroll one clear unmasked photograph | The person and their original template are stored successfully | Automated |
| AT-02 | Generate masks using MaskTheFace and RWMFD | Configured mask variants are created and linked to the same identity | Automated |
| AT-03 | Upload an image with no face | Enrollment is rejected with a useful message | Automated |
| AT-04 | Upload an image containing two or more faces | Enrollment asks for a single-person photograph | Automated |
| AT-05 | Upload a damaged, unsupported or oversized file | The file is rejected without crashing the application | Automated |
| AT-07 | Show an enrolled person wearing a mask | The correct identity is returned when the score and margin pass | Automated and manual |
| AT-08 | Show a person who was never enrolled | The result is `UNKNOWN`, not simply the nearest identity | Automated |
| AT-09 | Provide a blurred, small or ambiguous face | The result becomes `HUMAN_REVIEW` with a clear reason | Automated |
| AT-10 | Show several people in one frame | Each detected face receives its own box and decision | Automated and manual |
| AT-11 | Delete an identity | Its records and Chroma vectors are no longer searchable | Automated |
| AT-12 | Stop Chroma or PostgreSQL | Recognition fails clearly without producing a guessed match | Automated |