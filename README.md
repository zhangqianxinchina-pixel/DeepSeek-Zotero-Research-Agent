# 🚀 DeepSeek Zotero Research Agent

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/)

An automated research assistant that acts as a personalized literature filter. It connects your **Zotero** library with **Semantic Scholar** and uses **DeepSeek (LLM)** to intelligently score and recommend the latest papers in your specific domain.

> **Stop drowning in papers. Let AI filter them for you.**

## ✨ Features

- **📚 Context-Aware**: Reads your Zotero "Anchor Folder" to understand your specific research interests.
- **🔍 Automated Monitoring**: Scans Semantic Scholar for the latest papers (last 180 days) based on your keywords.
- **🧠 AI Scoring**: Uses DeepSeek (or any OpenAI-compatible LLM) to score papers (0-10) based on relevance to your anchor papers.
- **📧 Weekly Digest**: Sends a beautifully formatted HTML email report with the top-ranked papers.
- **🛡️ History Tracking**: Automatically avoids recommending the same paper twice.

## 🛠️ Prerequisites

- Python 3.8+
- A Zotero Account & API Key
- DeepSeek API Key (or OpenAI Key)
- An email account for sending reports (SMTP enabled)

## 📦 Installation

1. **Clone the repository**
   ```bash
   git clone [https://github.com/YOUR_USERNAME/DeepSeek-Zotero-Research-Agent.git](https://github.com/YOUR_USERNAME/DeepSeek-Zotero-Research-Agent.git)
   cd DeepSeek-Zotero-Research-Agent
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configuration**
   Create a `.env` file in the root directory and fill in your credentials:
   ```ini
   # Zotero Config
   ZOTERO_LIBRARY_ID=1234567
   ZOTERO_API_KEY=your_zotero_key

   # LLM Config (DeepSeek)
   DEEPSEEK_API_KEY=sk-xxxxxxxx
   
   # Semantic Scholar (Optional but recommended)
   S2_API_KEY=your_s2_key

   # Email Config
   MAIL_HOST=smtp.gmail.com
   MAIL_USER=your_email@gmail.com
   MAIL_PASS=your_email_auth_code
   MAIL_RECEIVER=receiver_email@example.com
   ```

4. **Customize Logic (Optional)**
   Edit the configuration section in `main.py` to change:
   - `MONITOR_KEYWORDS`: Your search topics (e.g., "photobiocatalysis").
   - `ANCHOR_FOLDER_NAME`: The folder in Zotero containing your "Gold Standard" papers.
   - `MIN_SCORE`: Minimum AI score to trigger an email.

## 🚀 Usage

Run the script manually or set it up as a cron job/scheduled task:

```bash
python main.py
```

## 🤝 Contribution

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is licensed under the MIT License.