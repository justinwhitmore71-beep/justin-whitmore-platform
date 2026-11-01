# Multi-User AI Recruitment Platform

A multi-tenant recruitment operating platform supporting three independent users:
1. **Justin Murrel Whitmore** (User + Administrator)
2. **Işıl** (Prague / Remote • English C2 & Native Turkish • Customer Support / Onboarding / Teaching)
3. **Lindsey Whitmore** (Leave-Malta Remote-First Europe • iGaming, Player Ops, AML, RG, KYC, Fraud & Payments)

---

## 1. System Architecture & Tenant Isolation Guarantees

- **Strict Server-Side Isolation**: Shared vacancies pool (`vacancies`), strictly user-scoped matches (`user_job_matches`), private encrypted/isolated document vaults (`data/vault/user_<id>/`), and separate browser profile directories (`data/browser_profiles/user_<id>_session/`).
- **Zero Cross-User Data Leaks**: Users cannot view or query each other's CVs, notes, or applications.
- **Privacy-Preserving Administrator Console**: Admin (Justin) can monitor system health, scraper telemetry, job discovery logs, and aggregate counts, but **cannot view private CVs or notes without an explicit, revocable user assistance grant**.
- **Onboarding Verification Gates**: For Işıl and Lindsey, preliminary dates, titles, and tools are flagged with `"verified": false`. Live CV and application generation is hard-locked until the candidate logs in, verifies the details, and clicks **Confirm & Verify Profile**.
- **Automated Scheduling (Part 12)**: Configurable per-user schedule (`08:00`, `08:30`, `09:00`, `09:30`, `16:00`). Runs via APScheduler locally or via Cloud Scheduler webhook (`/api/internal/cron/tick`) in the cloud.

---

## 2. Default Bootstrap Credentials

Initial bootstrap passwords generated locally in [`data/bootstrap_credentials.json`](file:///c:/Users/Justin/Desktop/The%20Simple%20Proof/job_assistant/data/bootstrap_credentials.json):

| Account | Username | Email | Role | Verification Status |
| :--- | :--- | :--- | :--- | :--- |
| **Justin Whitmore** | `justin` | `justinwhitmore71@gmail.com` | User + Admin | Active & Verified |
| **Işıl** | `isil` | *(set upon verification)* | User | Active (Verification Pending) |
| **Lindsey Whitmore** | `lindsey` | *(set upon verification)* | User | Active (Verification Pending) |

*(Passwords can be changed immediately after sign-in under the **Privacy & Security** tab, or via single-use password recovery).*

---

## 3. Web Portal & Dashboard

### Launching the Local Portal
Double-click **`Job Dashboard.bat`** on your Desktop or run:
```bash
python job_assistant/cli.py dashboard
```
Open **`http://127.0.0.1:5000`** in your browser.

### Key Capabilities in the Portal:
1. **Personal Dashboard View**:
   - 8 Pipeline metric cards (New Jobs, Best Matches, Saved, Awaiting Approval, Submitted, Interviews, Follow-ups Due, Rejections).
   - Real-time search filters by Match Score, Status, Remote Type, Category, Seniority, Location, Company, and Salary.
2. **Profile, CV Vault & Schedule Tab**:
   - Master CV uploader supporting `.pdf`, `.docx`, `.md`, and `.txt` with automatic verbatim skill extraction into the user's private vault.
   - Onboarding verification checklist.
   - Interactive preferences editor (Ranked Destinations, Excluded Countries, Target Salary, Timezone, and Discovery Times).
3. **Privacy & Security Tab**:
   - Password change and token recovery.
   - User-controlled administrator assistance grants (grant temporary 24h access for profile setup or document review, revocable anytime).
4. **Administrator Console (Justin only)**:
   - Live telemetry across all accounts, scraper runs, audit logs, and system health.

---

## 4. Daily Command-Line Interface (CLI)

```bash
# 1. Run discovery sweep for all accounts or a specific user
python job_assistant/cli.py --user all scan
python job_assistant/cli.py --user isil scan
python job_assistant/cli.py --user lindsey scan

# 2. List opportunities for a specific user
python job_assistant/cli.py --user isil list --min-score 75
python job_assistant/cli.py --user lindsey list --min-score 80
python job_assistant/cli.py --user justin list --min-score 85

# 3. Inspect a vacancy and view personalized score explanation & gap analysis
python job_assistant/cli.py --user lindsey inspect <match_id>

# 4. Generate tailored application package into the user's private vault
python job_assistant/cli.py --user justin prepare <match_id>

# 5. Update pipeline status
python job_assistant/cli.py --user isil update <match_id> applied --notes "Applied via company portal"

# 6. View pipeline statistics across all accounts
python job_assistant/cli.py --user all stats

# 7. Create a compressed backup of the SQLite database and vaults
python job_assistant/cli.py backup
```

---

## 5. Automated Verification & Testing

Run the automated pytest suite:
```bash
python -m pytest job_assistant/tests/test_multiuser_platform.py -v
```
Tests verify:
- Authentication, CSRF tokens, and password reset replay prevention.
- Strict cross-tenant isolation (Işıl and Lindsey cannot query or modify Justin's data, and vice versa).
- Privacy-preserving admin controls (Admin blocked from reading private CVs without explicit user grants).
- Lindsey's Leave-Malta scoring (Malta on-site jobs demoted/blocked; remote EU jobs prioritized).
- Işıl's work-authorization guardrails (no French/EU work-auth assumed; preliminary fields locked).
- Justin's legacy data preservation (all 217+ original jobs and applications preserved).

---

## 6. Remote Deployment (Cloud Run & Firebase)

The platform is containerized and cloud-ready:
- **`deploy/Dockerfile`**: Production container with Gunicorn and Python 3.11.
- **`deploy/requirements.txt`**: Core dependencies + optional Firebase/GCS packages.
- **`deploy/firebase.json`**, **`firestore.rules`**, **`storage.rules`**: Production rules enforcing per-user UID isolation.
- **Cloud Scheduler Webhook**: Endpoint `/api/internal/cron/tick` triggers automated daily cycles without needing your local computer on.
