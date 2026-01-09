#!/usr/bin/env python3
"""
BFMR Deal Monitor - GitHub Actions Version
Runs once per invocation (GitHub Actions handles scheduling)
"""

import requests
import json
import smtplib
import os
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
    
    def get_deals(self):
        """Fetch current deals from BFMR API"""
        endpoint = f"{self.base_url}/api/v2/deals"
        
        headers = {
            "API-KEY": self.api_key,
            "API-SECRET": self.api_secret,
        }
        
        try:
            print(f"Trying endpoint: {endpoint}")
            response = requests.get(endpoint, headers=headers, timeout=10)
            print(f"Status code: {response.status_code}")
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                print("Authentication failed - check your API credentials")
                return None
            else:
                print(f"Unexpected status code: {response.status_code}")
                return None
        except Exception as e:
            print(f"Error: {e}")
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
        print(f"{'='*60}\n")
        
        deals_data = self.get_deals()
        
        if not deals_data:
            print("⚠️  Could not fetch deals")
            return
        
        # Extract deals from response
        deals = deals_data
        if isinstance(deals_data, dict):
            deals = deals_data.get('deals', deals_data.get('data', []))
        
        print(f"📊 Total deals found: {len(deals) if deals else 0}")
        
        if not deals:
            print("No deals currently available")
            return
        
        # Find Amazon deals and compare to last run
        amazon_deals = []
        current_amazon_ids = set()
        new_or_returning_deals = []
        exclusive_count = 0
        
        for deal in deals:
            deal_id = str(deal.get('deal_id', ''))
            retailers = deal.get('retailers', '').lower()
            
            # Check if it's an Amazon deal
            if 'amazon' in retailers:
                amazon_deals.append(deal)
                current_amazon_ids.add(deal_id)
                
                if deal.get('is_exclusive_deal', False):
                    exclusive_count += 1
                
                # Check if it's new or returning (wasn't in last run)
                if deal_id and deal_id not in self.last_run_deals:
                    new_or_returning_deals.append(deal)
        
        print(f"📦 Amazon deals found now: {len(amazon_deals)}")
        print(f"⚠️  Exclusive deals: {exclusive_count}")
        print(f"📦 Amazon deals in last run: {len(self.last_run_deals)}")
        
        # Save current deals for next comparison
        self.save_current_run_deals(current_amazon_ids)
        
        if new_or_returning_deals:
            # Count exclusive vs regular in new deals
            new_exclusive = sum(1 for d in new_or_returning_deals if d.get('is_exclusive_deal', False))
            new_regular = len(new_or_returning_deals) - new_exclusive
            
            print(f"\n🎉 Found {len(new_or_returning_deals)} NEW or RETURNING Amazon deal(s)!")
            print(f"   - Regular deals: {new_regular}")
            print(f"   - Exclusive deals: {new_exclusive}")
            
            # Build email with summary
            email_body = f"Found {len(new_or_returning_deals)} new/returning Amazon deal(s) on BFMR:\n"
            email_body += f"  • {new_regular} regular deal(s)\n"
            email_body += f"  • {new_exclusive} exclusive deal(s) ⚠️\n\n"
            
            if new_exclusive > 0:
                email_body += "⚠️ NOTE: Exclusive deals may not be visible on the BFMR website.\n"
                email_body += "Contact BFMR support if you want access to exclusive deals.\n\n"
            
            email_body += "(These deals were not available in the last check 5 minutes ago)\n\n"
            email_body += "=" * 60 + "\n\n"
            
            for deal in new_or_returning_deals:
                email_body += self.format_deal_info(deal)
                email_body += "\n\n" + "=" * 60 + "\n\n"
            
            email_body += f"\nView all deals: https://www.buyformeretail.com/deals\n"
            email_body += f"Checked at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            
            # Send email
            subject = f"🚨 {len(new_or_returning_deals)} New/Returning Amazon Deal(s)"
            if new_exclusive > 0:
                subject += f" ({new_exclusive} Exclusive ⚠️)"
            
            self.send_email(subject, email_body)
            
            print(f"✅ Updated tracking file with {len(current_amazon_ids)} current Amazon deals")
        else:
            print("✓ No new or returning Amazon deals (same as last run)")
        
        # Show which deals disappeared
        disappeared = self.last_run_deals - current_amazon_ids
        if disappeared:
            print(f"📉 {len(disappeared)} deal(s) disappeared since last run")
        
        print(f"\n{'='*60}\n")


def main():
    """Main function"""
    try:
        monitor = BFMRMonitor()
        monitor.check_for_new_deals()
        return 0
    except ValueError as e:
        print(f"❌ Configuration Error: {e}")
        print("\nRequired GitHub Secrets:")
        print("  - BFMR_API_KEY")
        print("  - BFMR_API_SECRET")
        print("  - EMAIL_FROM")
        print("  - EMAIL_TO")  
        print("  - EMAIL_PASSWORD")
        return 1
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
