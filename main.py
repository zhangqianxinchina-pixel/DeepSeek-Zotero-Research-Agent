import requests
import time
import smtplib
import os
import json
import re
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr 
from datetime import datetime, timedelta

# Third-party libraries
from pyzotero import zotero
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables from .env file (for local testing)
load_dotenv()

# ================= 🔧 CONFIGURATION =================
# 1. LLM Settings (The Brain)
# Options: "deepseek" OR "openai"
# Default is "deepseek" if not specified.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek").lower() 

# API Keys (Ensure the corresponding key is set in .env or Secrets)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Model Selection
# - For DeepSeek: "deepseek-chat"
# - For OpenAI: "gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat") 

# 2. Zotero Settings
# LIBRARY_ID is optional; the script will auto-detect it from the API_KEY if missing.
LIBRARY_ID = os.getenv("ZOTERO_LIBRARY_ID") 
API_KEY = os.getenv("ZOTERO_API_KEY")

# 3. Semantic Scholar (Optional but recommended for higher rate limits)
S2_API_KEY = os.getenv("S2_API_KEY")

# 4. Email Configuration
MAIL_HOST = os.getenv("MAIL_HOST")      # e.g., smtp.gmail.com or smtp.qq.com
MAIL_USER = os.getenv("MAIL_USER")      # Your email address
MAIL_PASS = os.getenv("MAIL_PASS")      # App password / Token
MAIL_RECEIVER = os.getenv("MAIL_RECEIVER") # Recipient email address

# 5. Research Monitor Settings
# IMPORTANT: This folder name must match exactly (case-insensitive) with your Zotero folder.
ANCHOR_FOLDER_NAME = "xin" 
MONITOR_KEYWORDS = [
    "Perovskite solar cells"
]
MIN_SCORE = 6               # Minimum AI score (0-10) to include in the report
PUSH_LIMIT = 20             # Maximum number of papers to send in one email
SEARCH_WINDOW_DAYS = 180    # Only scan papers published in the last X days
HISTORY_FILE = "sent_history.json" # Local storage for sent papers to avoid duplicates

# [Reference Settings]
MAX_ANCHOR_COUNT = 20       # Number of papers to read from Zotero to form the context
ANCHOR_ABSTRACT_LEN = 400   # Truncate abstracts to save tokens
# ====================================================

def fetch_user_id(api_key):
    """
    Auto-detects the Zotero User ID using the API Key.
    This simplifies configuration for the user.
    """
    print("🔍 Auto-detecting Zotero User ID from API Key...")
    try:
        url = f"https://api.zotero.org/keys/{api_key}"
        headers = {"Zotero-API-Version": "3"}
        resp = requests.get(url, headers=headers)
        
        if resp.status_code == 200:
            user_id = resp.json().get('userID')
            print(f"✅ Found User ID: {user_id}")
            return user_id
        else:
            print(f"❌ Failed to fetch User ID. Status: {resp.status_code}")
            return None
    except Exception as e:
        print(f"❌ Network error detecting ID: {e}")
        return None

def get_folder_id_by_name(zot, folder_name):
    """
    Finds the Zotero Collection Key (Folder ID) by its human-readable name.
    """
    try:
        collections = zot.collections()
        for col in collections:
            if col['data']['name'].lower() == folder_name.lower():
                return col['key']
        return None
    except Exception as e:
        print(f"❌ Error fetching collections: {e}")
        return None

def get_anchors_from_folder(zot, folder_name):
    """
    Reads papers from the specific Zotero folder to build the research context.
    """
    print(f"\n📥 [Step 1] Reading anchor folder '{folder_name}'...")
    fid = get_folder_id_by_name(zot, folder_name)
    if not fid:
        print(f"❌ Error: Folder '{folder_name}' not found in Zotero.")
        print("   Please check if ANCHOR_FOLDER_NAME in the code matches your Zotero folder name.")
        return "", 0
    
    # Fetch items (Limit set to 100 to avoid timeouts)
    items = zot.collection_items(fid, limit=100) 
    
    anchors = ""
    count = 0
    
    for item in items:
        if count >= MAX_ANCHOR_COUNT:
            break
            
        data = item['data']
        
        # Skip attachments and notes, only keep papers
        if data.get('itemType') in ['attachment', 'note']:
            continue
            
        title = data.get('title')
        abstract = data.get('abstractNote')

        if title:
            # Truncate abstract to save tokens
            display_abstract = abstract[:ANCHOR_ABSTRACT_LEN] + "..." if abstract else "(No Abstract)"
            anchors += f"- Title: {title}\n  Abstract: {display_abstract}\n\n"
            count += 1

    if count == 0:
        print(f"⚠️ Warning: No valid items found in folder '{folder_name}'.")
    else:
        print(f"✅ Loaded {count} anchor papers as baseline.")
        
    return anchors, count

def load_history():
    """Loads the list of previously sent paper titles."""
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def save_history(new_titles):
    """Saves the updated list of sent papers."""
    old_history = load_history()
    # Merge and remove duplicates
    updated_history = list(set(old_history + new_titles))
    
    # Limit history size to prevent indefinite growth
    if len(updated_history) > 5000: 
        updated_history = updated_history[-5000:]
        
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(updated_history, f, ensure_ascii=False, indent=2)

def is_recent_paper(item, days_window=30):
    """
    Filters papers based on the publication date.
    """
    today = datetime.now()
    cutoff_date = today - timedelta(days=days_window)
    cutoff_year = cutoff_date.year

    # 1. Try parsing exact date
    pub_date_str = item.get('publicationDate')
    if pub_date_str:
        try:
            # Supports YYYY-MM-DD
            pub_date = datetime.strptime(pub_date_str, "%Y-%m-%d")
            if pub_date >= cutoff_date:
                return True
            else:
                return False 
        except ValueError:
            pass # Continue if format is not YYYY-MM-DD

    # 2. Fallback to Year check
    pub_year = item.get('year')
    if pub_year:
        try:
            pub_year = int(pub_year)
            if pub_year >= cutoff_year:
                return True
            else:
                return False
        except:
            pass
            
    return False

def search_s2_with_history(keywords_list, history_set):
    """
    Searches Semantic Scholar for new papers and filters out history/old papers.
    """
    base_url = "https://api.semanticscholar.org/graph/v1/paper/search"
    
    today = datetime.now()
    # Search window: Last 2 years (Software handles precise day filtering)
    date_range_param = f"{today.year-2}-{today.year}"
    
    print(f"\n🔍 [Step 2] Scanning Semantic Scholar (Year: {date_range_param})...")
    print("-" * 80)
    print(f"{'Keyword':<25} | {'Raw':<5} | {'📅Old':<6} | {'📚Read':<6} | {'✅New'}")
    print("-" * 80)
    
    paper_tracker = {} 
    headers = {"User-Agent": "ResearchAgent/1.0"}
    if S2_API_KEY: headers['x-api-key'] = S2_API_KEY
    
    for kw in keywords_list:
        params = {
            "query": kw,
            "year": date_range_param,
            "fields": "title,abstract,year,url,venue,publicationDate,authors",
            "sort": "publicationDate:desc", 
            "limit": 100 
        }
        
        try:
            r = requests.get(base_url, params=params, headers=headers, timeout=20)
            if r.status_code == 200:
                data = r.json().get('data', [])
                
                raw_count = len(data)
                old_filtered = 0
                history_hit = 0
                new_count = 0
                
                for item in data:
                    title = item.get('title')
                    if not title or not item.get('abstract'): continue
                    
                    # Date Filter
                    if not is_recent_paper(item, SEARCH_WINDOW_DAYS):
                        old_filtered += 1
                        continue 
                    
                    # History Filter
                    clean_key = title.strip().lower()
                    if clean_key in history_set:
                        history_hit += 1
                        continue
                        
                    # Deduplication
                    if clean_key not in paper_tracker:
                        paper_tracker[clean_key] = {
                            'data': item,
                            'hits': {kw} 
                        }
                        new_count += 1
                    else:
                        paper_tracker[clean_key]['hits'].add(kw)
                
                print(f"{kw:<25} | {raw_count:<6} | {old_filtered:<7} | {history_hit:<7} | 🆕 {new_count}")
                time.sleep(1.0) # Respect API rate limits
            else:
                print(f"{kw:<25} | ❌ Error {r.status_code}")
                
        except Exception as e:
            print(f"{kw:<25} | ⚠️ Net Error: {e}")

    print("-" * 80)
    
    final_candidates = []
    for key, val in paper_tracker.items():
        paper = val['data']
        paper['hit_keywords'] = list(val['hits']) 
        paper['hit_count'] = len(val['hits'])     
        final_candidates.append(paper)
        
    return final_candidates

def ai_score_paper(client, anchors, paper):
    """
    Uses the LLM to score the paper based on relevance to anchors.
    """
    prompt = f"""
    [Core Research Context]:
    {anchors[:10000]} 
    
    [Target Paper]:
    Title: {paper['title']}
    Abstract: {paper['abstract'][:3000]}
    
    [Task]:
    Evaluate the relevance of the Target Paper to the Core Research Context.
    - 10: Essential/Critical match.
    - 6-9: Relevant.
    - 0-5: Irrelevant.
    
    [Output Format]:
    SCORE: <number>
    REASON: <short explanation in English>
    """
    try:
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            stream=False
        )
        msg = resp.choices[0].message.content
        
        # Extract Score
        score_match = re.search(r"SCORE:\s*(\d+)", msg)
        score = int(score_match.group(1)) if score_match else 0
        
        # Extract Reason
        reason_parts = msg.split("REASON:")
        reason = reason_parts[-1].strip() if len(reason_parts) > 1 else "No reason provided"
        
        return score, reason
    except Exception as e:
        return 0, f"AI Error: {str(e)}"

def send_weekly_report(paper_list):
    """
    Generates and sends the HTML email report.
    """
    if not paper_list:
        print("📭 No papers to report.")
        return False

    date_str = datetime.now().strftime("%Y-%m-%d")
    print(f"\n📧 [Step 4] Sending Email Report (Top {len(paper_list)})...")
    
    html = f"""
    <div style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; max-width: 600px; margin: auto; color: #333;">
        <h2 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px;">
            📅 Weekly Literature Digest ({date_str})
        </h2>
        <p style="font-size: 12px; color: #888;">
            Top {len(paper_list)} Selections (Window: Last {SEARCH_WINDOW_DAYS} Days)
        </p>
    """
    
    for i, paper in enumerate(paper_list):
        # Styling for top 3
        if i == 0: rank_icon = "🥇"; border = "2px solid #f1c40f"
        elif i == 1: rank_icon = "🥈"; border = "2px solid #bdc3c7"
        elif i == 2: rank_icon = "🥉"; border = "2px solid #e67e22"
        else: rank_icon = f"#{i+1}"; border = "1px solid #ddd"

        score = paper.get('score', 0)
        hits = paper.get('hit_count', 1)
        hit_kws = ", ".join(paper.get('hit_keywords', []))
        venue = paper.get('venue') or "Unknown Journal"
        pub_date = paper.get('publicationDate') or paper.get('year') or "Recent"
        
        # Format Authors
        author_list = paper.get('authors', [])
        if author_list:
            author_names = [a['name'] for a in author_list[:3]]
            authors_str = ", ".join(author_names)
            if len(author_list) > 3:
                authors_str += " et al."
        else:
            authors_str = "Unknown Authors"

        html += f"""
        <div style="border: {border}; margin-bottom: 20px; border-radius: 8px; overflow: hidden; background: #fff;">
            
            <div style="background: #f8f9fa; padding: 10px 15px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <b style="font-size: 14px;">{rank_icon} Recommended</b>
                    {f'<span style="background:#6c757d; color:white; padding:2px 6px; border-radius:4px; font-size:10px; margin-right:5px; vertical-align: text-bottom;">🎯 {hits} hits</span>' if hits > 1 else ""}
                </div>
                <span style="background: #e74c3c; color: white; padding: 2px 8px; border-radius: 10px; font-weight:bold; font-size: 12px;">{score} / 10</span>
            </div>

            <div style="padding: 15px;">
                <h3 style="margin: 0 0 10px 0; font-size: 16px; line-height: 1.4;">
                    <a href="{paper['url']}" style="text-decoration: none; color: #0366d6;">{paper['title']}</a>
                </h3>

                <div style="font-size: 13px; color: #444; margin-bottom: 12px; line-height: 1.6;">
                    <div style="margin-bottom: 4px;">
                        🏛️ <b>{venue}</b> <span style="color:#888; margin-left:5px;">(📅 {pub_date})</span>
                    </div>
                    <div style="color: #666;">
                        ✍️ {authors_str}
                    </div>
                </div>

                <p style="font-size: 11px; color: #999; margin: 0 0 8px 0;">
                      🏷️ Keywords: {hit_kws}
                </p>

                <div style="background: #f1f8ff; padding: 10px; border-radius: 6px; font-size: 13px; color: #24292e; border-left: 3px solid #0366d6;">
                    💡 <b>AI Comment:</b> {paper['reason']}
                </div>
            </div>
        </div>
        """
    
    html += "<p style='text-align: center; color: #aaa; font-size: 12px; margin-top: 20px;'>Generated by Research Agent</p></div>"

    msg = MIMEText(html, 'html', 'utf-8')
    msg['From'] = formataddr(["ResearchBot", MAIL_USER])
    msg['To'] = Header("Researcher", 'utf-8')
    msg['Subject'] = Header(f"【Weekly】Top {len(paper_list)} Papers ({date_str})", 'utf-8')

    try:
        smtp = smtplib.SMTP_SSL(MAIL_HOST, 465)
        smtp.login(MAIL_USER, MAIL_PASS)
        smtp.sendmail(MAIL_USER, [MAIL_RECEIVER], msg.as_string())
        smtp.quit()
        return True
    except Exception as e:
        print(f"❌ Email Failed: {e}")
        return False

def run_weekly_job():
    print(f"🚀 Starting Research Agent (Provider: {LLM_PROVIDER.upper()})...")
    
    # 1. Initialize Zotero
    # Use global variable to update the ID found by fetch_user_id
    global LIBRARY_ID 
    
    # Auto-detect ID if missing
    if not LIBRARY_ID and API_KEY:
        LIBRARY_ID = fetch_user_id(API_KEY)
        
    if not LIBRARY_ID:
        print("❌ Error: Could not determine Zotero User ID.")
        print("   Please either set ZOTERO_LIBRARY_ID in config/secrets,")
        print("   OR ensure your ZOTERO_API_KEY is correct.")
        return

    try:
        zot = zotero.Zotero(LIBRARY_ID, 'user', API_KEY)
    except Exception as e:
        print(f"❌ Zotero Login Failed: {e}")
        return

    # 2. Initialize LLM Client
    # Supports both OpenAI and DeepSeek based on configuration
    if LLM_PROVIDER == "openai":
        if not OPENAI_API_KEY:
            print("❌ Error: LLM_PROVIDER is 'openai' but OPENAI_API_KEY is missing.")
            return
        client = OpenAI(api_key=OPENAI_API_KEY)
        print(f"🧠 AI Model: OpenAI ({LLM_MODEL})")
    else:
        # Default to DeepSeek
        if not DEEPSEEK_API_KEY:
            print("❌ Error: LLM_PROVIDER is 'deepseek' but DEEPSEEK_API_KEY is missing.")
            return
        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
        print(f"🧠 AI Model: DeepSeek ({LLM_MODEL})")

    # 3. Load History
    history_list = load_history()
    history_set = set([t.lower().strip() for t in history_list])
    print(f"📚 History loaded: {len(history_list)} records")

    # 4. Load Anchors (Context)
    anchors, count = get_anchors_from_folder(zot, ANCHOR_FOLDER_NAME)
    if count == 0: return

    # 5. Search Candidates
    candidates = search_s2_with_history(MONITOR_KEYWORDS, history_set)
    
    if not candidates:
        print("📭 No new candidates found.")
        return
        
    print(f"\n🧠 [Step 3] AI Scoring (Total {len(candidates)} papers)...")
    
    recommended = []
    total = len(candidates)
    
    # 6. AI Scoring Loop
    for i, item in enumerate(candidates):
        print(f"   [{i+1}/{total}] Analyzing: {item['title'][:40]}...", end="")
        score, reason = ai_score_paper(client, anchors, item)
        if score >= MIN_SCORE:
            print(f" -> 🔥 {score}/10")
            item['score'] = score
            item['reason'] = reason
            recommended.append(item)
        else:
            print(f" -> Pass")

    # 7. Sort and Push
    # Sort by Score (Desc) then by Hit Count (Desc)
    recommended.sort(key=lambda x: (x['score'], x['hit_count']), reverse=True)
    final_list = recommended[:PUSH_LIMIT]
    
    if final_list:
        success = send_weekly_report(final_list)
        if success:
            print(f"✅ Email sent! Pushed {len(final_list)} papers.")
            
            # Save history ONLY if email is sent successfully
            new_pushed_titles = [p['title'].strip().lower() for p in final_list]
            save_history(new_pushed_titles)
            print(f"💾 History updated: {len(new_pushed_titles)} new records.")
        else:
            print(f"❌ Email failed. History not updated.")
    else:
        print(f"\n🧹 No papers met the score threshold ({MIN_SCORE}+).")

if __name__ == "__main__":
    print(f"📂 Working Directory: {os.getcwd()}")
    
    # Basic check for essential credentials
    if not all([API_KEY, MAIL_USER, MAIL_PASS]):
        print("❌ Error: Missing critical configuration.")
        print("   Please check ZOTERO_API_KEY, MAIL_USER, and MAIL_PASS in .env or Secrets.")
    else:
        run_weekly_job()
