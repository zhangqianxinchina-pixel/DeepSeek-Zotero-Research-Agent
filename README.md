# 🧪 DeepSeek Zotero Research Agent

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://www.python.org/)

**Stop drowning in irrelevant papers. Let AI filter the noise for you.**

This is an automated research assistant that acts as a personalized literature filter. It connects your **Zotero** library with **Semantic Scholar** and uses **Large Language Models (DeepSeek or OpenAI)** to intelligently score and recommend the latest papers in your specific domain.

> **Key Difference:** Unlike generic keyword alerts, this agent **reads your existing papers** to understand your specific research context, resulting in highly relevant recommendations.

---

## ✨ Key Features

- **🧠 Context-Aware**: Reads a specific "Anchor Folder" in your Zotero to understand *exactly* what you are working on.
- **🔍 Wide Scanning**: Monitors Semantic Scholar for the latest publications (default: last 180 days).
- **🤖 Dual Brain Support**: Supports both **DeepSeek** (Cost-effective) and **OpenAI GPT-4o** (High performance).
- **📧 Weekly Digest**: Sends a beautifully formatted HTML email report with top-ranked papers.
- **💾 Smart Memory**: Automatically commits history to the repository to ensure **no duplicate emails**.
- **☁️ Serverless**: Runs entirely on **GitHub Actions**. No local server required.

---

## 🚀 Quick Start (No Coding Required)

Follow these 5 steps to set up your personal agent in 10 minutes.

### Step 1: Fork this Repository
Click the **Fork** button at the top-right corner of this page. This creates your own private copy of the code.

### Step 2: Prepare Zotero
1.  Open your Zotero Desktop App.
2.  Create a new Collection (Folder), e.g., name it `Research_Focus`.
3.  **Drag and drop 10-20 high-quality papers** (PDFs or entries) that represent your current research interest into this folder.
4.  *Note: You don't need to find any ID numbers. Just remember the folder name.*

### Step 3: Customize Configuration
Open `main.py` in your forked repository, click the **Edit (Pencil)** icon, and modify the top section:

```python
# ================= 🔧 CONFIGURATION =================
# 1. LLM Provider (Choose "deepseek" or "openai")
LLM_PROVIDER = "deepseek" 

# 2. Monitor Settings
# MUST match your Zotero folder name exactly!
ANCHOR_FOLDER_NAME = "Research_Focus" 

# Search Keywords
MONITOR_KEYWORDS = [
    "Perovskite solar cells",
    "Photo-catalysis"
]

# Email Settings
MIN_SCORE = 6               # Minimum AI score (0-10) to send email
PUSH_LIMIT = 20             # Max papers per email

```

Commit your changes.

### Step 4: Set Up Secrets (Crucial!)

Go to your GitHub repository: **Settings** -> **Secrets and variables** -> **Actions** -> **New repository secret**.

Add the following secrets. **(Variable names must be exact/uppercase)**:

| Secret Name | Description |
| --- | --- |
| `ZOTERO_API_KEY` | Get it from [Zotero API Settings](https://www.zotero.org/settings/keys/new). |
| `DEEPSEEK_API_KEY` | (If using DeepSeek) Your `sk-...` key. |
| `OPENAI_API_KEY` | (If using OpenAI) Your `sk-...` key. |
| `MAIL_HOST` | SMTP server (e.g., `smtp.qq.com` or `smtp.gmail.com`). |
| `MAIL_USER` | Your email address (sender). |
| `MAIL_PASS` | Your email **App Password** (NOT your login password). |
| `MAIL_RECEIVER` | The email address to receive the report. |
| `S2_API_KEY` | (Optional) Semantic Scholar API Key for higher rate limits. |

> **Note:** You do **NOT** need to set `ZOTERO_LIBRARY_ID`. The script will auto-detect it from your API Key.

### Step 5: Activate & Run

1. Go to the **Actions** tab in your repository.
2. Click **"Weekly Research Monitor"** on the left sidebar.
3. Click **Run workflow** (button might be on the right).
4. Wait for the run to finish (Green checkmark ✅).
5. Check your email inbox!

---

## 📅 Schedule & Automation

By default, the agent runs **every Monday at 08:00 Beijing Time** (UTC 00:00).

To change the schedule, edit `.github/workflows/weekly_report.yml`:

```yaml
on:
  schedule:
    # Format: 'Minute Hour Day Month DayOfWeek' (in UTC)
    - cron: '0 0 * * 1' 

```

---

## 🛠️ Local Installation (For Developers)

If you prefer to run it on your local machine:

1. **Clone the repo**
```bash
git clone [https://github.com/zhangqianxinchina-pixel/DeepSeek-Zotero-Research-Agent.git](https://github.com/zhangqianxinchina-pixel/DeepSeek-Zotero-Research-Agent.git)
cd DeepSeek-Zotero-Research-Agent

```


2. **Install dependencies**
```bash
pip install -r requirements.txt

```


3. **Configure Environment**
Create a `.env` file in the root directory (use the format below):
```ini
ZOTERO_API_KEY=your_key
DEEPSEEK_API_KEY=your_key
MAIL_HOST=smtp.gmail.com
MAIL_USER=xxx@gmail.com
MAIL_PASS=xxx
MAIL_RECEIVER=xxx@gmail.com

```


4. **Run**
```bash
python main.py

```



---

## ❓ FAQ

**Q: My Zotero folder isn't being found.**
A: Check if `ANCHOR_FOLDER_NAME` in `main.py` matches your Zotero folder name exactly (it's case-insensitive, but spelling matters).

**Q: I'm not receiving emails.**
A: Check the "Actions" tab log. If it says "Email sent!", check your Spam folder. If it fails, verify your `MAIL_PASS` (App Password) in Secrets.

**Q: Can I keep my research interests private?**
A: Yes! Just keep your forked repository **Private**. GitHub Actions still works for private repos.

---

## 🤝 Contributing

Contributions are welcome! If you have ideas for new features (e.g., Slack integration, multiple Zotero folders), feel free to open an issue or submit a pull request.

## 📄 License

This project is licensed under the MIT License.
