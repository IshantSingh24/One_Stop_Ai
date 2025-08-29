import os
import time
import io
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SERVICE_ACCOUNT_FILE = 'credentials.json'

SCOPES = ['https://www.googleapis.com/auth/drive']

POLL_INTERVAL = 30
DOWNLOAD_FOLDER = 'knowledge_base/drive'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

creds = None
if os.path.exists(SERVICE_ACCOUNT_FILE):
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
else:
    print("Error: Service account key file not found.")
    exit()

try:
    service = build('drive', 'v3', credentials=creds)

    def get_all_files():
        all_files = []
        page_token = None
        
        while True:
            results = service.files().list(
                pageSize=1000,
                fields="nextPageToken, files(id, name, createdTime, mimeType, size)",
                pageToken=page_token
            ).execute()
            
            files = results.get('files', [])
            all_files.extend(files)
            
            page_token = results.get('nextPageToken')
            if not page_token:
                break
                
        return all_files

    def download_file(file_id, file_name, mime_type):
        try:
            print(f"Downloading: {file_name}")
            
            if mime_type.startswith('application/vnd.google-apps'):
                export_formats = {
                    'application/vnd.google-apps.document': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    'application/vnd.google-apps.spreadsheet': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    'application/vnd.google-apps.presentation': 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
                }
                
                if mime_type in export_formats:
                    request = service.files().export_media(fileId=file_id, mimeType=export_formats[mime_type])
                    if mime_type == 'application/vnd.google-apps.document':
                        file_name += '.docx'
                    elif mime_type == 'application/vnd.google-apps.spreadsheet':
                        file_name += '.xlsx'
                    elif mime_type == 'application/vnd.google-apps.presentation':
                        file_name += '.pptx'
                else:
                    print(f"Cannot download {file_name}: Unsupported Google Workspace file type")
                    return False
            else:
                request = service.files().get_media(fileId=file_id)
            
            file_path = os.path.join(DOWNLOAD_FOLDER, file_name)
            fh = io.FileIO(file_path, 'wb')
            downloader = MediaIoBaseDownload(fh, request)
            
            done = False
            while done is False:
                status, done = downloader.next_chunk()
                if status:
                    print(f"Download progress: {int(status.progress() * 100)}%")
            
            print(f"Successfully downloaded: {file_name}")
            return True
            
        except Exception as e:
            print(f"Error downloading {file_name}: {e}")
            return False

    def monitor_drive():
        print("Starting Google Drive monitoring...")
        print(f"Checking for new files every {POLL_INTERVAL} seconds")
        print(f"Downloads will be saved to: {DOWNLOAD_FOLDER}")
        print("Press Ctrl+C to stop monitoring\n")
        
        known_files = set()
        try:
            initial_files = get_all_files()
            for file in initial_files:
                known_files.add(file['id'])
            print(f"Found {len(known_files)} existing files in Drive")
        except Exception as e:
            print(f"Error getting initial file list: {e}")
            return
        
        while True:
            try:
                print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Checking for new files...")
                
                current_files = get_all_files()
                current_file_ids = {file['id'] for file in current_files}
                
                new_file_ids = current_file_ids - known_files
                
                if new_file_ids:
                    print(f"Found {len(new_file_ids)} new file(s)!")
                    
                    for file in current_files:
                        if file['id'] in new_file_ids:
                            print(f"\nNew file detected: {file['name']}")
                            print(f"Created: {file.get('createdTime', 'Unknown')}")
                            print(f"Type: {file.get('mimeType', 'Unknown')}")
                            
                            success = download_file(file['id'], file['name'], file.get('mimeType', ''))
                            if success:
                                known_files.add(file['id'])
                else:
                    print("No new files found")
                
                print(f"Waiting {POLL_INTERVAL} seconds before next check...")
                time.sleep(POLL_INTERVAL)
                
            except KeyboardInterrupt:
                print("\n\nMonitoring stopped by user")
                break
            except Exception as e:
                print(f"Error during monitoring: {e}")
                print(f"Retrying in {POLL_INTERVAL} seconds...")
                time.sleep(POLL_INTERVAL)

    print("Listing current files from Google Drive...")
    try:
        results = service.files().list(
            pageSize=10, fields="nextPageToken, files(id, name, createdTime)").execute()
        
        items = results.get('files', [])

        if not items:
            print('No files found.')
            print('Did you remember to share a file or folder with the service account email?')
        else:
            print('Recent files:')
            for item in items:
                print(f"- {item['name']} (ID: {item['id']}) - Created: {item.get('createdTime', 'Unknown')}")
    except Exception as e:
        print(f"Error listing files: {e}")

    print("\n" + "="*50)
    monitor_drive()

except Exception as e:
    print(f"An error occurred: {e}")