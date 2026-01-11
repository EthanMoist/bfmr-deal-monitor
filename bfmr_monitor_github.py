#!/usr/bin/env python3
"""
BFMR Deal Monitor - GitHub Actions Version
Runs once per invocation (GitHub Actions handles scheduling)
"""

import requests
import json
import smtplib
import os
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path

class BFMRMonitor:
    def __init__(self):
        """Initialize from environment variables"""
        self.api_key = os.getenv('BFMR_API_KEY')
        self.api_secret = os.getenv('BFMR_API_SECRET')
        self.base_url = "https://api.bfmr.com"
        
        self.email_config = {
            'smtp_server': os.getenv('EMAIL_SMTP_SERVER', 'smtp.gmail.com'),
            'smtp_port': int(os.getenv('EMAIL_SMTP_PORT', '587')),
            'from_email': os.getenv('EMAIL_FROM'),
            'to_email': os.getenv('EMAIL_TO'),
            'password': os.getenv('EMAIL_PASSWORD')
        }
        
        # Validate configuration
        if not all([self.api_key, self.api_secret, 
                   self.email_config['from_email'], 
                   self.email_config['password']]):
            raise ValueError("Required environment variables not set")
        
        # File to store deals from last run
        self.last_run_file = Path("last_run_deals.json")
        self.last_run_deals = self.load_last_run_deals()
        
    def load_last_run_deals(self):
        """Load deals from the previous run"""
        if self.last_run_file.exists():
            try:
                with open(self.last_run_file, 'r') as f:
                    data = json.load(f)
                    return set(data.get('deal_ids', []))
            except:
                return set()
        return set()
    
    def save_current_run_deals(self, deal_ids):
        """Save current run's deal IDs for next comparison"""
        with open(self.last_run_file, 'w') as f:
            json.dump({
                'deal_ids': list(deal_ids),
                'timestamp': datetime.now().isoformat()
            }, f, indent=2)
        print(f"💾 Saved {len(deal_ids)} deal IDs to tracking file")
    
    def get_deals(self):
        """Fetch current deals from BFMR API with retry logic"""
        endpoint = f"{self.base_url}/api/v2/deals"
        
        headers = {
            "API-KEY": self.api_key,
            "API-SECRET": self.api_secret,
        }
        
        max_retries = 3
        timeout = 30  # Increased from 10 to 30 seconds
        
        for attempt in range(max_retries):
            try:
                print(f"Trying endpoint: {endpoint} (attempt {attempt + 1}/{max_retries})")
                response = requests.get(endpoint, headers=headers, timeout=timeout)
                print(f"Status code: {response.status_code}")
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 401:
                    print("Authentication failed - check your API credentials")
                    return None
                else:
                    print(f"Unexpected status code: {response.status_code}")
                    if attempt < max_retries - 1:
                        print(f"Retrying in 5 seconds...")
                        time.sleep(5)
                    else:
                        return None
            except requests.exceptions.Timeout:
                print(f"Request timed out after {timeout} seconds")
                if attempt < max_retries - 1:
                    print(f"Retrying in 5 seconds...")
                    time.sleep(5)
                else:
                    print(f"Failed after {max_retries} attempts")
                    return None
            except Exception as e:
                print(f"Error: {e}")
                if attempt < max_retries - 1:
                    print(f"Retrying in 5 seconds...")
                    time.sleep(5)
                else:
                    return None
        
        return None
    
    def format_deal_info(self, deal):
        """Format deal information for email"""
        deal_id = deal.get('deal_id', 'Unknown')
        deal_code = deal.get('deal_code', 'N/A')
        title = deal.get('title', 'No title')
        retail_price = deal.get('retail_price', 'N/A')
        payout_price = deal.get('payout_price', 'N/A')
        retailers = deal.get('retailers', 'Amazon')
        retail_type = deal.get('retail_type', 'N/A')
        closing_at = deal.get('closing_at', 'N/A')
        is_exclusive = deal.get('is_exclusive_deal', False)
        is_bundle = deal.get('is_bundle', False)
        
        # Get URL from first item's retailer links if available
        url = 'N/A'
        items = deal.get('items', [])
        if items and len(items) > 0:
            retailer_links = items[0].get('retailer_links', [])
            if retailer_links and len(retailer_links) > 0:
                url = retailer_links[0].get('url', 'N/A')
        
        # Add prominent warning for exclusive deals
        exclusive_warning = ""
        if is_exclusive:
            exclusive_warning = """
⚠️⚠️⚠️ EXCLUSIVE DEAL - MAY NOT BE VISIBLE ON WEBSITE ⚠️⚠️⚠️
This is an exclusive deal that may not appear on buyformeretail.com
Contact BFMR support if you want access to exclusive deals.
"""
        
        info = f"""{exclusive_warning}
Deal ID: {deal_id}
Deal Code: {deal_code}
Title: {title}
Retailer: {retailers}
Type: {retail_type}
Retail Price: ${retail_price}
Your Payout: ${payout_price}
Closes At: {closing_at}
Exclusive: {"⚠️ YES - May not be accessible" if is_exclusive else "No"}
Bundle: {"Yes" if is_bundle else "No"}
URL: {url}
        """
        return info.strip()
    
    def send_email(self, subject, body):
        """Send email notification"""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.email_config['from_email']
            msg['To'] = self.email_config['to_email']
            msg['Subject'] = subject
            
            msg.attach(MIMEText(body, 'plain'))
            
            with smtplib.SMTP(self.email_config['smtp_server'], 
                            self.email_config['smtp_port']) as server:
                server.starttls()
                server.login(self.email_config['from_email'], 
                           self.email_config['password'])
                server.send_message(msg)
            
            print(f"✅ Email sent: {subject}")
            return True
            
        except Exception as e:
            print(f"❌ Error sending email: {e}")
            return False
    
    def check_for_new_deals(self):
        """Check for new deals and send notifications"""
        print(f"\n{'='*60}")
        print(f"BFMR Deal Check - {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
