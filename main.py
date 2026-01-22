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

# Load environment variables from .env file
load_dotenv()

# ================= 🔧 CONFIGURATION =================
# 1. API Keys (Loaded from .env)
LIBRARY_ID = os.getenv("ZOTERO_LIBRARY_ID")
API_KEY = os.getenv("ZOTERO_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
S2_API_KEY = os.getenv("S2_API_KEY") # Optional

# 2. Email Configuration
MAIL_HOST = os.getenv("MAIL_HOST")      # e.g., smtp.gmail.com
MAIL_USER = os.getenv("MAIL_USER")      # Your email address
MAIL_PASS = os.getenv("MAIL_PASS")      # Your email app password/token
MAIL_RECEIVER = os.getenv("MAIL_RECEIVER") # Recipient email

# 3. Monitor Settings
# You can also move these to .env or a config.yaml if you want more flexibility
ANCHOR_FOLDER_NAME = "xin" 
MONITOR_KEYWORDS = [
    "Perovskite solar cells"
]
MIN_SCORE = 6        
PUSH_LIMIT = 20      
SEARCH_WINDOW_DAYS = 180  
HISTORY_FILE = "sent_history.json"

# [Zotero Reference Settings]
MAX_ANCHOR_COUNT = 20       # Suggest 15-20 papers to avoid hallucination
ANCHOR_ABSTRACT_LEN = 400   # Truncate abstract to save tokens
# ====================================================

def get_folder_id_by_name(zot, folder_name):
    collections = zot.collections()
    for col in collections:
        if col['data']['name'].lower() == folder_name.lower():
            return col['key']
    return None

def get_anchors_from_folder(zot, folder_name):
    print(f"\n📥 [Step 1] Reading anchor folder '{folder_name}'...")
    fid = get_folder_id_by_name(zot, folder_name)
    if not fid:
        print(f"❌ Error: Folder '{folder_name}' not found in Zotero.")
        return "", 0
    
    # Zotero API limit is 100 per request
    items = zot.collection_items(fid, limit=100) 
    
    anchors = ""
    count = 0
    
    for item in items:
        if count >= MAX_ANCHOR_COUNT:
            break
            
        data = item['data']
        
        # Exclude attachments and notes
        if data.get('itemType') in ['attachment', 'note']:
            continue
            
        title = data.get('title')
        abstract = data.get('abstractNote')

        if title:
            display_abstract = abstract[:ANCHOR_ABSTRACT_LEN] + "..." if abstract else "(No Abstract)"
            anchors += f"- Title: {title}\n  Abstract: {display_abstract}\n\n"
            count += 1

    if count == 0:
        print(f"⚠️ Warning: No valid items found in folder '{folder_name}'.")
    else:
        print(f"✅ Loaded {count} anchor papers as baseline (Limit: {MAX_ANCHOR_COUNT}).")
        
    return anchors, count

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def save_history(new_titles):
    old_history = load_history()
    updated_history = list(set(old_history + new_titles))
    
    # Keep history manageable
    if len(updated_history) > 5000: 
        updated_history = updated_history[-5000:]
        
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(updated_history, f, ensure_ascii=False, indent=2)

def is_recent_paper(item, days_window=30):
    """
    Check if the paper is within the date window.
    """
    title = item.get('title', 'No Title')[:20]
    
    today = datetime.now()
    cutoff_date = today - timedelta(days=days_window)
    cutoff_year = cutoff_date.year

    pub_date_str = item.get('publicationDate')
    if pub_date_str:
        try:
            pub_date = datetime.strptime(pub_date_str, "%Y-%m-%d")
            if pub_date >= cutoff_date:
                return True
            else:
                return False 
        except ValueError:
            pass

    # Fallback to year check if full date is missing
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
    base_url = "https://api.semanticscholar.org/graph/v1/paper/search"
    
    today = datetime.now()
    current_year = today.year
    last_year = current_year - 2
    date_range_param = f"{last_year}-{current_year}"
    
    print(f"\n🔍 [Step 2] Scanning Semantic Scholar (Year: {date_range_param})...")
    print("-" * 80)
    print(f"{'Keyword':<25} | {'Raw':<5} | {'📅Old':<6} | {'📚Read':<6} | {'✅New'}")
    print("-" * 80)
    
    paper_tracker = {} 
    headers = {"User-Agent": "Mozilla/5.0"}
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
                    
                    if not is_recent_paper(item, SEARCH_WINDOW_DAYS):
                        old_filtered += 1
                        continue 
                    
                    clean_key = title.strip().lower()
                    if clean_key in history_set:
                        history_hit += 1
                        continue
                        
                    if clean_key not in paper_tracker:
                        paper_tracker[clean_key] = {
                            'data': item,
                            'hits': {kw} 
                        }
                        new_count += 1
                    else:
                        paper_tracker[clean_key]['hits'].add(kw)
                
                print(f"{kw:<25} | {raw_count:<6} | {old_filtered:<7} | {history_hit:<7} | 🆕 {new_count}")
                time.sleep(1.2)
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
    prompt = f"""
    [Core Research Context (Anchor Papers)]:
    {anchors[:10000]} 
    
    [Target Paper to Evaluate]:
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
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            stream=False
        )
        msg = resp.choices[0].message.content
        score_match = re.search(r"SCORE:\s*(\d+)", msg)
        score = int(score_match.group(1)) if score_match else 0
        
        reason_parts = msg.split("REASON:")
        reason = reason_parts[-1].strip() if len(reason_parts) > 1 else "No reason provided"
        
        return score, reason
    except Exception as e:
        return 0, f"AI Error: {str(e)}"

def send_weekly_report(paper_list):
    if not paper_list:
        print("📭 No papers to report.")
        return

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
        if i == 0: rank_icon = "🥇"; border = "2px solid #f1c40f"
        elif i == 1: rank_icon = "🥈"; border = "2px solid #bdc3c7"
        elif i == 2: rank_icon = "🥉"; border = "2px solid #e67e22"
        else: rank_icon = f"#{i+1}"; border = "1px solid #ddd"

        score = paper.get('score', 0)
        hits = paper.get('hit_count', 1)
        hit_kws = ", ".join(paper.get('hit_keywords', []))
        
        hit_badge = f'<span style="background:#6c757d; color:white; padding:2px 6px; border-radius:4px; font-size:10px; margin-right:5px; vertical-align: text-bottom;">🎯 {hits} hits</span>' if hits > 1 else ""
        venue = paper.get('venue') or "Unknown Journal"
        
        author_list = paper.get('authors', [])
        if author_list:
            author_names = [a['name'] for a in author_list[:3]]
            authors_str = ", ".join(author_names)
            if len(author_list) > 3:
                authors_str += " et al."
        else:
            authors_str = "Unknown Authors"

        pub_date = paper.get('publicationDate') or paper.get('year') or "Recent"

        html += f"""
        <div style="border: {border}; margin-bottom: 20px; border-radius: 8px; overflow: hidden; background: #fff;">
            
            <div style="background: #f8f9fa; padding: 10px 15px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <b style="font-size: 14px;">{rank_icon} Recommended</b>
                    {hit_badge}
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
    print(f"🚀 Starting Research Agent...")
    
    # Initialize Clients
    zot = zotero.Zotero(LIBRARY_ID, 'user', API_KEY)
    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
    
    # 1. Load History
    history_list = load_history()
    history_set = set([t.lower().strip() for t in history_list])
    print(f"📚 History loaded: {len(history_list)} records")

    # 2. Load Anchors
    anchors, count = get_anchors_from_folder(zot, ANCHOR_FOLDER_NAME)
    if count == 0: return

    # 3. Search Candidates
    candidates = search_s2_with_history(MONITOR_KEYWORDS, history_set)
    
    if not candidates:
        print("📭 No new candidates found.")
        return
        
    print(f"\n🧠 [Step 3] AI Scoring (Total {len(candidates)} papers)...")
    
    recommended = []
    total = len(candidates)
    
    # 4. AI Scoring
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

    # 5. Sort and Push
    recommended.sort(key=lambda x: (x['score'], x['hit_count']), reverse=True)
    final_list = recommended[:PUSH_LIMIT]
    
    if final_list:
        success = send_weekly_report(final_list)
        if success:
            print(f"✅ Email sent! Pushed {len(final_list)} papers.")
            
            # Save history ONLY if email is sent
            new_pushed_titles = [p['title'].strip().lower() for p in final_list]
            save_history(new_pushed_titles)
            print(f"💾 History updated: {len(new_pushed_titles)} new records.")
        else:
            print(f"❌ Email failed. History not updated.")
    else:
        print(f"\n🧹 No papers met the score threshold ({MIN_SCORE}+).")

if __name__ == "__main__":
    print(f"📂 Working Directory: {os.getcwd()}")
    if not all([LIBRARY_ID, API_KEY, DEEPSEEK_API_KEY, MAIL_USER, MAIL_PASS]):
        print("❌ Error: Missing configuration. Please check your .env file.")
    else:
        run_weekly_job()
