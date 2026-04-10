import json
import csv
from datetime import datetime
from collections import defaultdict

def extract_instagram_nodes(file_path):
    """Robust bracket-counting parser to handle messy, unclosed, or garbage-filled text files."""
    nodes = []
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        text = f.read()

    search_str = '"node":'
    idx = 0
    
    while True:
        idx = text.find(search_str, idx)
        if idx == -1: break
            
        start_brace = text.find('{', idx)
        if start_brace == -1: break
            
        brace_count = 0
        end_brace = -1
        in_string = False
        escape = False

        for i in range(start_brace, len(text)):
            char = text[i]
            if escape:
                escape = False
                continue
            if char == '\\':
                escape = True
            elif char == '"':
                in_string = not in_string
            elif not in_string:
                if char == '{': brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_brace = i
                        break

        if end_brace != -1:
            json_str = text[start_brace:end_brace+1]
            try:
                nodes.append(json.loads(json_str))
            except json.JSONDecodeError:
                pass # Skip corrupted blocks
                
        idx = start_brace + 1
        
    return nodes

def process_and_save_data(input_file):
    print(f"Scanning '{input_file}' for post and collaborator data...")
    nodes = extract_instagram_nodes(input_file)
    
    unique_posts = {}
    collaborators_db = defaultdict(lambda: {
        'Username': '', 'Full_Name': '', 'Is_Verified': False, 
        'Coauthored_Posts': 0, 'Tagged_Posts': 0, 'Post_Shortcodes': []
    })
    
    for node in nodes:
        media = node.get('media', node)
        pk = media.get('pk') or media.get('id')
        if not pk or pk in unique_posts:
            continue
            
        # --- 1. POST DATA EXTRACTION ---
        code = media.get('code', '')
        url = f"https://www.instagram.com/p/{code}/" if code else ""
        
        taken_at = media.get('taken_at')
        if taken_at:
            dt = datetime.fromtimestamp(taken_at)
            date_str, time_str = dt.strftime('%Y-%m-%d'), dt.strftime('%H:%M:%S')
        else:
            date_str, time_str = "", ""
            
        caption_dict = media.get('caption') or {}
        text = caption_dict.get('text', '').replace('\n', ' | ')
        
        likes = media.get('like_count') or media.get('fb_like_count') or 0
        comments = media.get('comment_count', 0)
        views = media.get('view_count', '')
        media_type = media.get('product_type', media.get('media_type', ''))
        is_paid = media.get('is_paid_partnership', False)
        
        # --- 2. COLLABORATOR / TAG EXTRACTION ---
        coauthors_list = media.get('coauthor_producers') or []
        for coauthor in coauthors_list:
            uid = coauthor.get('id') or coauthor.get('pk')
            # Skip if the coauthor is Freshlabels themselves
            if uid and coauthor.get('username') != 'freshlabels':
                collaborators_db[uid]['Username'] = coauthor.get('username', '')
                collaborators_db[uid]['Full_Name'] = coauthor.get('full_name', '')
                collaborators_db[uid]['Is_Verified'] = coauthor.get('is_verified', False)
                collaborators_db[uid]['Coauthored_Posts'] += 1
                collaborators_db[uid]['Post_Shortcodes'].append(code)

        usertags_list = (media.get('usertags') or {}).get('in', [])
        for tag in usertags_list:
            user = tag.get('user', {})
            uid = user.get('id') or user.get('pk')
            if uid and user.get('username') != 'freshlabels':
                collaborators_db[uid]['Username'] = user.get('username', '')
                collaborators_db[uid]['Full_Name'] = user.get('full_name', '')
                collaborators_db[uid]['Is_Verified'] = user.get('is_verified', False)
                collaborators_db[uid]['Tagged_Posts'] += 1
                if code not in collaborators_db[uid]['Post_Shortcodes']:
                    collaborators_db[uid]['Post_Shortcodes'].append(code)

        # Save to post dictionary
        unique_posts[pk] = {
            'Post_ID': pk, 'Shortcode': code, 'URL': url, 'Date': date_str, 'Time': time_str,
            'Format_Type': media_type, 'Likes': likes, 'Comments': comments, 'Views': views,
            'Is_Paid_Partnership': is_paid, 
            'Total_Collaborators': len(coauthors_list) + len(usertags_list),
            'Caption': text
        }

    # --- 3. EXPORT TO CSV ---
    if not unique_posts:
        print("No valid posts found.")
        return

    # Export Posts
    with open('freshlabels_posts.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=unique_posts[list(unique_posts.keys())[0]].keys())
        writer.writeheader()
        writer.writerows(unique_posts.values())

    # Export Collaborators
    collab_headers = ['User_ID', 'Username', 'Full_Name', 'Is_Verified', 'Coauthored_Posts', 'Tagged_Posts', 'Total_Appearances', 'Post_Shortcodes']
    with open('freshlabels_collaborators.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=collab_headers)
        writer.writeheader()
        for uid, data in collaborators_db.items():
            writer.writerow({
                'User_ID': uid,
                'Username': data['Username'],
                'Full_Name': data['Full_Name'],
                'Is_Verified': data['Is_Verified'],
                'Coauthored_Posts': data['Coauthored_Posts'],
                'Tagged_Posts': data['Tagged_Posts'],
                'Total_Appearances': data['Coauthored_Posts'] + data['Tagged_Posts'],
                'Post_Shortcodes': " | ".join(data['Post_Shortcodes'])
            })
            
    print(f"Success! Exported {len(unique_posts)} posts and {len(collaborators_db)} unique collaborators/influencers.")

if __name__ == "__main__":
    process_and_save_data('ig_raw_data_freshlabels.txt')