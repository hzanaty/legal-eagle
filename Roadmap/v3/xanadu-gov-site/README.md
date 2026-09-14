# Xanadu Government Demo Site

Static fictional Ministry of Human Resources website used as controlled input for the Legal Eagle demo.

## Run locally

From this directory:

```bash
python3 -m http.server 8000 --directory public
```

Open `http://localhost:8000/`.

## Demo data design

- `social-insurance-contribution-reform.html` is the original confirmed legal change.
- `social-insurance-rate-countdown.html` is a later reminder of the same change.
- Both repeat Royal Decree No. 18/2026, Social Insurance Act No. 7/2025 Article 14, and the 12 September 2026 effective date to support deterministic announcement grouping.
- Other articles deliberately range from relevant-but-not-new to obvious noise.
- Every navigation and “Read full notice” link resolves to a real static page.
- The MoU article uses an AI-generated flags-and-documents image with no people.
- The SAP–Xanadu MoU provides the spoken transition into the Autonomous LPM and Legal Eagle demonstration.

All content and institutions are fictional and intended only for demonstration.
