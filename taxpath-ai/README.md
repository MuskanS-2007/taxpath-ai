# TaxPath AI — Hackathon Prototype

An explainable tax reconciliation and guidance prototype for IMPACTX Challenge 08. **Not an official tax-filing service. All demo data and rules are synthetic.**

## Included
- PDF/TXT/CSV upload + local server-side extraction of amounts, dates and line items
- Corrected-document versioning and supersession lineage
- Reconciliation API with tolerance, possible extra-zero detection and referral classification
- Internal document-total check that states which figure was used
- Synthetic rulebook, calculation endpoint and mid-event rule change
- Explicit referral triggers
- Privacy log scan (financial values intentionally excluded from application event logs)
- 25 seeded stress-test cases
- Responsive React dashboard
- Browser voice input/output
- UI language selection: English, Hindi, Telugu, Tamil, Kannada, Malayalam, Marathi, Bengali

## Run locally
### Backend
```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
API docs: `http://localhost:8000/docs`

### Frontend
```bash
cd frontend
npm install
npm run dev
```
Open the Vite URL (normally `http://localhost:5173`).

## Deploy
### Backend — Render
Create a new Web Service using the `backend` directory. Build command: `pip install -r requirements.txt`; start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

> SQLite and uploaded files on many free cloud instances are ephemeral. For a judging prototype this is acceptable for a session; for production, replace with Postgres/object storage.

### Frontend — Vercel/Netlify
Deploy the `frontend` directory and set:
`VITE_API_URL=https://YOUR-BACKEND-URL`
Then run `npm run build`.

## Judge demo
1. Upload `employer_statement_v1.txt` as `employer_statement`.
2. Upload `employer_statement_v2_corrected.txt` with the same kind. V1 becomes superseded.
3. Open `/docs` and try `/reconcile` with `{"values":{"payslips":600000,"corrected_statement":612000,"prefill":600000},"tolerance":1}`.
4. Try extra-zero detection with 75000 vs 750000.
5. Upload `internal_total_error.txt` and call `/document/check-total/{id}`.
6. Call `/rules/change` to change the synthetic deduction limit and show affected sections.
7. Run Privacy Audit and Stress Test from the UI.
8. Select an Indian language and demonstrate browser speech input/output.

## Important limitations
- This is a hackathon prototype, not tax/legal advice and not an official Income Tax product.
- It intentionally does not use or claim current Indian tax rules.
- PDF extraction works for text PDFs. Scanned-image PDFs need an OCR module; do not silently trust OCR values without user confirmation.
- Browser speech recognition/synthesis support varies by browser, OS and language. Typed interaction is the fallback.
- The multilingual strings are prototype UI strings; tax terminology should be reviewed by fluent/domain-qualified speakers before real use.
- Do not upload real PAN, Aadhaar, bank, salary or taxpayer documents during the demo.
