import os
import json
import time
import threading
import requests
import mimetypes
from datetime import datetime, timezone
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

def load_config():
    config_path = "config.json"
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"  Configuration file {config_path} not found!")
        return None
    except json.JSONDecodeError as e:
        print(f"  Invalid JSON in {config_path}: {e}")
        return None

config = load_config()
if not config:
    print("  Cannot continue without valid configuration")
    exit(1)

SLACK_BOT_TOKEN = config['slack']['bot_token']
TARGET_CHANNELS = config['slack']['target_channel'] if isinstance(config['slack']['target_channel'], list) else [config['slack']['target_channel']]
JSON_FILE = config['output']['json_file']
LOGGING_FILE = "knowledge_base/slack/logging.json"
POLL_INTERVAL = config['monitoring']['poll_interval']
BOT_USER_ID = None

DOWNLOAD_FOLDER = "knowledge_base/slack"
MAX_FILE_SIZE = 25 * 1024 * 1024
SUPPORTED_EXTENSIONS = ['.txt', '.pdf', '.docx', '.json', '.md', '.csv', '.xlsx', '.pptx']

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

client = WebClient(token=SLACK_BOT_TOKEN)

class SimpleSlackMonitor:
    def __init__(self):
        self.last_check_time = datetime.now(timezone.utc).timestamp()
        self.running = False
        self.thread = None
        self.bot_user_id = self.get_bot_user_id()
        
    def get_bot_user_id(self):
        try:
            response = client.auth_test()
            bot_id = response.get('user_id')
            print(f" Bot User ID: {bot_id}")
            return bot_id
        except SlackApiError as e:
            print(f"  Error getting bot user ID: {e}")
            return None
        
    def load_existing_data(self):
        try:
            if os.path.exists(JSON_FILE) and os.path.getsize(JSON_FILE) > 0:
                with open(JSON_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading existing data: {e}")
        return {"events": [], "last_updated": None}
    
    def load_logging_data(self):
        try:
            if os.path.exists(LOGGING_FILE) and os.path.getsize(LOGGING_FILE) > 0:
                with open(LOGGING_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading logging data: {e}")
        return {"messages": [], "last_updated": None, "total_messages": 0}
    
    def save_to_logging(self, message_data):
        try:
            existing_data = self.load_logging_data()
            
            existing_data["messages"].append(message_data)
            existing_data["last_updated"] = datetime.now().isoformat()
            existing_data["total_messages"] = len(existing_data["messages"])
            
            with open(LOGGING_FILE, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, indent=2, ensure_ascii=False)
            
            return True
        except Exception as e:
            print(f"  Error saving to logging: {e}")
            return False
    
    def save_to_json(self, data):
        try:
            existing_data = self.load_existing_data()
            
            existing_data["events"].append(data)
            existing_data["last_updated"] = datetime.now().isoformat()
            
            with open(JSON_FILE, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, indent=2, ensure_ascii=False)
            
            print(f" Data saved to {JSON_FILE}")
            return True
        except Exception as e:
            print(f"  Error saving to JSON: {e}")
            return False
    
    def get_user_info(self, user_id):
        try:
            return {
                'id': user_id,
                'name': f'user_{user_id}',
                'display_name': f'User {user_id}'
            }
        except Exception as e:
            return {'id': user_id, 'name': 'Unknown', 'display_name': 'Unknown'}
    
    def download_file(self, file_info):
        try:
            file_id = file_info.get('id')
            file_name = file_info.get('name', f"file_{file_id}")
            file_size = file_info.get('size', 0)
            file_url = file_info.get('url_private_download') or file_info.get('url_private')
            mimetype = file_info.get('mimetype', '')
            
            print(f"🔄 Attempting to download: {file_name} ({file_size} bytes)")
            
            if file_size > MAX_FILE_SIZE:
                print(f"  File {file_name} is too large ({file_size} bytes > {MAX_FILE_SIZE} bytes)")
                return None
            
            _, ext = os.path.splitext(file_name)
            if ext.lower() not in SUPPORTED_EXTENSIONS:
                print(f"  File {file_name} has unsupported extension: {ext}")
                return None
            
            if not file_url:
                print(f"  No download URL available for {file_name}")
                return None
            
            headers = {'Authorization': f'Bearer {SLACK_BOT_TOKEN}'}
            
            print(f"🌐 Downloading from: {file_url[:50]}...")
            response = requests.get(file_url, headers=headers, stream=True, timeout=30)
            
            if response.status_code == 200:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_filename = f"{timestamp}_{file_name}"
                file_path = os.path.join(DOWNLOAD_FOLDER, safe_filename)
                
                with open(file_path, 'wb') as f:
                    total_size = 0
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                        total_size += len(chunk)
                
                print(f"✅ Downloaded: {file_name} → {file_path} ({total_size} bytes)")
                
                return {
                    'original_name': file_name,
                    'saved_path': file_path,
                    'size': total_size,
                    'mimetype': mimetype,
                    'download_timestamp': datetime.now().isoformat(),
                    'file_id': file_id
                }
            else:
                print(f"  Failed to download {file_name}: HTTP {response.status_code}")
                print(f"    Response: {response.text[:200]}...")
                return None
                
        except Exception as e:
            print(f"  Error downloading file {file_name}: {e}")
            return None
    
    def process_message_files(self, message):
        downloaded_files = []
        
        files = message.get('files', [])
        for file_info in files:
            download_result = self.download_file(file_info)
            if download_result:
                downloaded_files.append({
                    'file_info': file_info,
                    'download_result': download_result
                })
        
        return downloaded_files
    
    def get_recent_messages(self, channel, since_timestamp):
        try:
            response = client.conversations_history(
                channel=channel,
                oldest=since_timestamp,
                limit=50
            )
            return response.get('messages', [])
        except SlackApiError as e:
            print(f"Error getting messages: {e}")
            return []
    
    def log_all_recent_messages(self):
        try:
            for channel in TARGET_CHANNELS:
                messages = self.get_recent_messages(channel, self.last_check_time)
                
                for message in messages:
                    if message.get('user') == self.bot_user_id:
                        continue
                    
                    downloaded_files = self.process_message_files(message)
                    
                    message_data = {
                        # 'message_id': message.get('ts'),
                        # 'channel_id': channel,
                        'timestamp': datetime.now().isoformat(),
                        # 'original_timestamp': message.get('ts'),
                        'user_id': message.get('user'),
                        # 'user_info': self.get_user_info(message.get('user', '')),
                        # 'message_type': message.get('type', 'message'),
                        # 'subtype': message.get('subtype'),
                        'text_usethisforQueries': message.get('text', ''),
                        # 'blocks': message.get('blocks', []),
                        # 'attachments': message.get('attachments', []),
                        # 'files': message.get('files', []),
                        # 'downloaded_files': downloaded_files,
                        # 'reactions': message.get('reactions', []),
                        # 'thread_ts': message.get('thread_ts'),
                        # 'reply_count': message.get('reply_count', 0),
                        # 'reply_users_count': message.get('reply_users_count', 0),
                        # 'latest_reply': message.get('latest_reply'),
                        # 'permalink': f"https://app.slack.com/client/T09CV0AF7A4/{channel}/thread/{channel}-{message.get('ts', '')}",
                        # 'metadata': {
                        #     'has_files': len(message.get('files', [])) > 0,
                        #     'has_reactions': len(message.get('reactions', [])) > 0,
                        #     'has_thread': message.get('thread_ts') is not None,
                        #     'is_edited': 'edited' in message,
                        #     'edited_timestamp': message.get('edited', {}).get('ts') if 'edited' in message else None
                        # },
                        # 'raw_message': message  # Keep full original message for reference
                    }
                    
                    # Save to logging file
                    self.save_to_logging(message_data)
                    
                    file_count = len(downloaded_files)
                    file_info = f" ( {file_count} files downloaded)" if file_count > 0 else ""
                    user_info = self.get_user_info(message.get('user', ''))
                    print(f" [{channel}] Logged message from {user_info['display_name']}: {message_data['text_usethisforQueries'][:50]}...{file_info}")
                    
        except Exception as e:
            print(f"Error logging recent messages: {e}")
    
    def check_for_files_in_history(self, limit=50):
        try:
            print(f" Checking last {limit} messages per channel for files to download...")
            
            total_files_found = 0
            total_files_downloaded = 0
            
            for channel in TARGET_CHANNELS:
                print(f" Checking channel: {channel}")
                
                response = client.conversations_history(
                    channel=channel,
                    limit=limit
                )
                messages = response.get('messages', [])
                
                files_found = 0
                files_downloaded = 0
                
                for message in messages:
                    if message.get('user') == self.bot_user_id:
                        continue
                        
                    files = message.get('files', [])
                    if files:
                        files_found += len(files)
                        print(f" [{channel}] Found {len(files)} file(s) in message: {message.get('text', '')[:50]}...")
                        
                        downloaded_files = self.process_message_files(message)
                        files_downloaded += len(downloaded_files)
                
                print(f" [{channel}] File check: {files_found} files found, {files_downloaded} downloaded")
                total_files_found += files_found
                total_files_downloaded += files_downloaded
            
            print(f" Total across all channels: {total_files_found} files found, {total_files_downloaded} downloaded")
            return total_files_downloaded > 0
            
        except Exception as e:
            print(f"Error checking for files in history: {e}")
            return False
    
    def check_bot_mentions_and_keywords(self):
        try:
            for channel in TARGET_CHANNELS:
                messages = self.get_recent_messages(channel, self.last_check_time)
                
                keywords = ['/aisave', 'save this', 'important', 'remember this', '@ai', '@bot']
                
                for message in messages:
                    message_text = message.get('text', '')
                    message_user = message.get('user', '')
                    message_ts = message.get('ts', '')
                    
                    if message_user == self.bot_user_id:
                        continue
                    
                    trigger_type = None
                    trigger_details = None
                    
                    # 1. Direct bot mention
                    if f"<@{self.bot_user_id}>" in message_text:
                        trigger_type = "bot_mention"
                        trigger_details = "Direct bot mention"
                    
                    # 2. /aisave command (even without slash command setup)
                    elif '/aisave' in message_text.lower():
                        trigger_type = "aisave_command"
                        trigger_details = "Manual /aisave command"
                    
                    # 3. Keyword triggers
                    elif any(keyword.lower() in message_text.lower() for keyword in keywords):
                        trigger_type = "keyword_trigger"
                        matched_keywords = [kw for kw in keywords if kw.lower() in message_text.lower()]
                        trigger_details = f"Keywords: {', '.join(matched_keywords)}"
                    
                    # 4. Messages with specific patterns
                    elif any(pattern in message_text.lower() for pattern in ['todo:', 'note:', 'reminder:']):
                        trigger_type = "pattern_match"
                        trigger_details = "Contains todo/note/reminder pattern"
                    
                    if trigger_type:
                        event_data = {
                            'type': trigger_type,
                            'timestamp': datetime.now().isoformat(),
                            'trigger_details': trigger_details,
                            'message': {
                                'text': message_text,
                                'user_id': message_user,
                                'timestamp': message_ts,
                                'channel': channel,
                                'permalink': f"https://app.slack.com/client/T09CV0AF7A4/{channel}/thread/{channel}-{message_ts}"
                            },
                            'raw_message': message
                        }
                        
                        self.save_to_json(event_data)
                        print(f" [{channel}] {trigger_type} detected: {message_text[:80]}...")
                        
        except Exception as e:
            print(f"Error checking messages: {e}")
    
    def start_monitoring(self):
        if self.running:
            print("Monitoring is already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        print(f" Started comprehensive Slack monitoring for channels: {', '.join(TARGET_CHANNELS)}")
        print(f" Bot User ID: {self.bot_user_id}")
        print(f" Polling interval: {POLL_INTERVAL} seconds")
        print(f" Downloads folder: {DOWNLOAD_FOLDER}")
        print(f" Max file size: {MAX_FILE_SIZE / (1024*1024):.1f} MB")
        print(f" Supported extensions: {', '.join(SUPPORTED_EXTENSIONS)}")
        print(f" Comprehensive logging includes:")
        print(f"   - All message metadata and content")
        print(f"   - File downloads (txt, pdf, docx, json, etc.)")
        print(f"   - User information and reactions")
        print(f"   - Thread and reply information")
        print(f"   - Timestamps and permalinks")
        print(f" Special trigger monitoring:")
        print(f"   - Direct bot mentions (@bot)")
        print(f"   - /aisave commands") 
        print(f"   - Keywords: save this, important, remember this")
        print(f"   - Patterns: todo:, note:, reminder:")
    
    def stop_monitoring(self):
        self.running = False
        if self.thread:
            self.thread.join()
        print("⏹️ Stopped monitoring")
    
    def _monitor_loop(self):
        while self.running:
            try:
                print(f"🔍 [{datetime.now().strftime('%H:%M:%S')}] Checking for new messages...")
                
                self.log_all_recent_messages()
                
                self.check_bot_mentions_and_keywords()
                
                self.last_check_time = datetime.now(timezone.utc).timestamp()
                
                time.sleep(POLL_INTERVAL)
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error in monitoring loop: {e}")
                time.sleep(POLL_INTERVAL)

def main():
    print("🤖 Enhanced Slack Monitor Starting...")
    print(f"📁 Trigger events saved to: {JSON_FILE}")
    print(f"📊 Comprehensive logs saved to: {LOGGING_FILE}")
    print(f"📂 File downloads saved to: {DOWNLOAD_FOLDER}/")
    print(f"📺 Monitoring channels: {', '.join(TARGET_CHANNELS)}")
    
    monitor = SimpleSlackMonitor()
    
    if not monitor.bot_user_id:
        print("Cannot start monitoring without valid bot connection")
        return
    
    print("\n🔍 Checking message history for files to download...")
    files_downloaded = monitor.check_for_files_in_history(100)
    
    if files_downloaded:
        print(f"✅ Downloaded {files_downloaded} files from history!")
    else:
        print("ℹ️ No files found in recent history")
        print("💡 Try uploading a .txt, .pdf, or .json file to test")
    
    print("\n" + "="*50)
    
    try:
        monitor.start_monitoring()
        
        print("\n Monitor is running and will download files automatically!")
        print("   Upload a file to the Slack channel to test")
        print("   Check the slack_downloads/ folder for results")
        print("   Press Ctrl+C to stop")
        
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n Shutting down...")
        monitor.stop_monitoring()

if __name__ == "__main__":
    main()
